from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Callable

from backend.services.config_service import ConfigService
from backend.services.crawl_runner_service import CrawlRunnerService
from backend.services.pipeline_service import PipelineService
from database import Database
from notifier import notify_job_failure


class JobRunnerService:
    def __init__(self) -> None:
        self.db_factory: Callable[[], Database] | None = None
        self.current_task: asyncio.Task | None = None
        self.current_job_id: int | None = None

    def start(self, db_factory: Callable[[], Database]) -> None:
        self.db_factory = db_factory

    async def shutdown(self) -> None:
        await self.cancel_running("服务关闭，任务已取消")

    async def cleanup_stale_running(self, reason: str = "服务启动时清理未完成任务") -> None:
        db = self._db()
        await db.init()
        await db.cancel_running_jobs(reason)

    async def restart(self, source: str = "api", payload: dict | None = None) -> int:
        db = self._db()
        await db.init()
        config = await ConfigService(db).get_config()
        if not _has_enabled_crawler_config(config):
            raise ValueError("请先配置可用账号并启用至少一个后缀爬取计划。")

        await self.cancel_running("任务被新的配置重启")
        job_id = await db.create_job(source)
        self.current_job_id = job_id
        self.current_task = asyncio.create_task(self._run(job_id, source, payload or {}))
        return job_id

    async def start_if_idle(self, source: str = "schedule", payload: dict | None = None) -> int | None:
        db = self._db()
        await db.init()
        if await db.has_running_job():
            return None
        config = await ConfigService(db).get_config()
        if not _has_enabled_crawler_config(config):
            return None
        job_id = await db.create_job(source)
        self.current_job_id = job_id
        self.current_task = asyncio.create_task(self._run(job_id, source, payload or {}))
        return job_id

    async def cancel_running(self, reason: str) -> None:
        db = self._db()
        await db.init()
        await db.cancel_running_jobs(reason)
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.current_task
        self.current_task = None
        self.current_job_id = None

    async def _run(self, job_id: int, source: str, payload: dict) -> None:
        try:
            success = await self._run_attempt(job_id, source, payload)
            if source != "schedule" or success:
                return

            db = self._db()
            await db.init()
            config = await ConfigService(db).get_config()
            max_attempts = max(1, config.failure_retry_count + 1)
            delay_seconds = max(0, config.failure_retry_delay_seconds)

            for attempt in range(2, max_attempts + 1):
                last_job = await db.get_job(job_id)
                if last_job is None or last_job.status != "failed":
                    return
                if delay_seconds:
                    await asyncio.sleep(delay_seconds)
                retry_job_id = await db.create_job("schedule-retry")
                self.current_job_id = retry_job_id
                success = await self._run_attempt(retry_job_id, "schedule-retry", payload)
                job_id = retry_job_id
                if success:
                    return

            final_job = await db.get_job(job_id)
            if final_job and final_job.status == "failed":
                latest_config = await ConfigService(db).get_config()
                with suppress(Exception):
                    await notify_job_failure(
                        latest_config,
                        job_id=final_job.id,
                        source=final_job.source,
                        error=final_job.error or "未知错误",
                        attempt=max_attempts,
                        max_attempts=max_attempts,
                    )
        finally:
            self.current_task = None
            self.current_job_id = None

    async def _run_attempt(self, job_id: int, source: str, payload: dict) -> bool:
        db = self._db()
        await db.init()
        config = await ConfigService(db).get_config()
        tld = str(payload.get("tld", "")).strip().lower().lstrip(".") or None
        service = PipelineService(db, config)
        try:
            await CrawlRunnerService(db, config).crawl_enabled_tlds(tld=tld)
            await service.run(
                tld=tld,
                source=source,
                top=_optional_int(payload.get("top")),
                min_score=_optional_int(payload.get("min_score")),
                create_job=False,
                job_id=job_id,
            )
            return True
        except asyncio.CancelledError:
            await db.cancel_job_if_running(job_id, "任务被取消")
            raise
        except Exception as exc:
            job = await db.get_job(job_id)
            if job and job.status == "running":
                await db.finish_job(
                    job_id,
                    "failed",
                    total_deleted=0,
                    total_filtered=0,
                    total_scored=0,
                    total_available=0,
                    error=str(exc),
                )
            return False

    def _db(self) -> Database:
        if self.db_factory is None:
            raise RuntimeError("Job runner has not started")
        return self.db_factory()


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _has_enabled_crawler_config(config) -> bool:
    has_account = any(
        account.get("enabled", True) and account.get("username") and account.get("password")
        for account in config.expireddomains_accounts
    )
    has_tld = any(
        schedule.get("enabled", True) and schedule.get("tld")
        for schedule in config.expireddomains_tld_schedules
    )
    return has_account and has_tld


job_runner_service = JobRunnerService()
