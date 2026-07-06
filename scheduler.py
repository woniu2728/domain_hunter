from __future__ import annotations

import asyncio

from apscheduler.schedulers.blocking import BlockingScheduler

from backend.services.config_service import ConfigService
from backend.services.crawl_runner_service import CrawlRunnerService
from backend.services.pipeline_service import PipelineService
from config import get_settings
from database import Database


def start_scheduler(hour: int = 2, minute: int = 0) -> None:
    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(lambda: asyncio.run(_scheduled_run()), "cron", hour=hour, minute=minute)
    scheduler.start()


async def _scheduled_run() -> None:
    settings = get_settings()
    settings.ensure_dirs()
    db = Database(settings.database_url)
    await db.init()
    config = await ConfigService(db).get_config()
    await CrawlRunnerService(db, config).crawl_enabled_tlds()
    await PipelineService(db, config).run(source="schedule")
