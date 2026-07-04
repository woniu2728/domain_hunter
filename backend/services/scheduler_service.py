from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.services.config_service import ConfigService
from backend.services.pipeline_service import PipelineService
from database import Database
from domain_hunter.types import AppConfig


SCHEDULE_JOB_ID = "domain-hunter-daily-run"


class SchedulerService:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        self.db_factory = None

    async def start(self, db_factory) -> None:
        self.db_factory = db_factory
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def reload(self, config: AppConfig | None = None) -> None:
        if self.db_factory is None:
            return
        db = self.db_factory()
        await db.init()
        active_config = config or await ConfigService(db).get_config()
        self.scheduler.remove_job(SCHEDULE_JOB_ID) if self.scheduler.get_job(SCHEDULE_JOB_ID) else None
        if not active_config.schedule_enabled:
            return
        self.scheduler.add_job(
            self.run_once,
            "cron",
            id=SCHEDULE_JOB_ID,
            hour=active_config.schedule_hour,
            minute=active_config.schedule_minute,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    async def run_once(self) -> None:
        if self.db_factory is None:
            return
        db: Database = self.db_factory()
        await db.init()
        if await db.has_running_job():
            return
        config = await ConfigService(db).get_config()
        if not config.schedule_enabled or not _has_enabled_zone_source(config.zone_sources):
            return
        job_id = await db.create_job("schedule")
        await PipelineService(db, config).run(source="schedule", create_job=False, job_id=job_id)


def _has_enabled_zone_source(sources: list[dict]) -> bool:
    return any(source.get("enabled") and source.get("tld") and source.get("zone_url") for source in sources)


scheduler_service = SchedulerService()
