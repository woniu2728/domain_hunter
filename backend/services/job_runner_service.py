from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path
from typing import Callable

from backend.services.config_service import ConfigService
from backend.services.pipeline_service import PipelineService
from database import Database
from domain_hunter.types import AppConfig


class JobRunnerService:
    def __init__(self) -> None:
        self.db_factory: Callable[[], Database] | None = None
        self.current_task: asyncio.Task | None = None
        self.current_job_id: int | None = None

    def start(self, db_factory: Callable[[], Database]) -> None:
        self.db_factory = db_factory

    async def shutdown(self) -> None:
        await self.cancel_running("服务关闭，任务已取消")

    async def restart(self, source: str = "api", payload: dict | None = None) -> int:
        db = self._db()
        await db.init()
        config = await ConfigService(db).get_config()
        if not _has_enabled_zone_source(config.zone_sources):
            raise ValueError("请先在配置中添加启用的 Zone 来源。")

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
        if not _has_enabled_zone_source(config.zone_sources):
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
        db = self._db()
        await db.init()
        config = await ConfigService(db).get_config()
        service = PipelineService(db, config)
        deleted_file = Path(payload["deleted_file"]) if payload.get("deleted_file") else None
        try:
            await service.run(
                deleted_file=deleted_file,
                source=source,
                top=_optional_int(payload.get("top")),
                min_score=_optional_int(payload.get("min_score")),
                create_job=False,
                job_id=job_id,
            )
        except asyncio.CancelledError:
            await db.cancel_job_if_running(job_id, "任务被取消")
            raise
        finally:
            if self.current_job_id == job_id:
                self.current_task = None
                self.current_job_id = None

    def _db(self) -> Database:
        if self.db_factory is None:
            raise RuntimeError("Job runner has not started")
        return self.db_factory()


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _has_enabled_zone_source(sources: list[dict]) -> bool:
    return any(source.get("enabled") and source.get("tld") and source.get("zone_url") for source in sources)


job_runner_service = JobRunnerService()
