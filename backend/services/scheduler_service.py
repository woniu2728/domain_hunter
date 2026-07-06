from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.services.config_service import ConfigService
from backend.services.job_runner_service import job_runner_service
from database import Database
from domain_hunter.types import AppConfig


SCHEDULE_JOB_PREFIX = "expireddomains"
SCHEDULE_JOB_ID = "expireddomains-daily-run"


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
        for job in list(self.scheduler.get_jobs()):
            if job.id.startswith(f"{SCHEDULE_JOB_PREFIX}-"):
                self.scheduler.remove_job(job.id)
        if not active_config.schedule_enabled:
            return
        for schedule in _enabled_tld_schedules(active_config):
            tld = str(schedule["tld"]).strip().lower().lstrip(".")
            self.scheduler.add_job(
                self.run_once,
                "cron",
                id=f"{SCHEDULE_JOB_PREFIX}-{tld}-daily",
                hour=int(schedule.get("crawl_hour", 2)),
                minute=int(schedule.get("crawl_minute", 0)),
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                kwargs={"tld": tld},
            )

    async def run_once(self, tld: str | None = None) -> None:
        if self.db_factory is None:
            return
        db: Database = self.db_factory()
        await db.init()
        config = await ConfigService(db).get_config()
        if not config.schedule_enabled or not _enabled_tld_schedules(config):
            return
        await job_runner_service.start_if_idle(source="schedule", payload={"tld": tld} if tld else {})


def _enabled_tld_schedules(config: AppConfig) -> list[dict]:
    return [
        schedule
        for schedule in config.expireddomains_tld_schedules
        if schedule.get("enabled", True) and schedule.get("tld")
    ]


scheduler_service = SchedulerService()
