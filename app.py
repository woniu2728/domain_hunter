from __future__ import annotations

from typing import Optional
import asyncio

import typer
from rich.console import Console

from backend.services.config_service import ConfigService
from backend.services.crawl_runner_service import CrawlRunnerService
from backend.services.pipeline_service import PipelineService
from config import get_settings
from database import Database


cli = typer.Typer(help="Discover deleted, high-value domains from ExpiredDomains.net.")
console = Console()


@cli.command("init-db")
def init_db() -> None:
    asyncio.run(_init_db())


@cli.command("run")
def run(
    tld: Optional[str] = typer.Option(None, help="Optional TLD to crawl and process."),
    top: Optional[int] = typer.Option(None, help="Number of candidates to query."),
    min_score: Optional[int] = typer.Option(None, help="Minimum score before availability query."),
) -> None:
    asyncio.run(
        run_pipeline(
            tld=tld,
            top=top,
            min_score=min_score,
        )
    )


@cli.command("schedule")
def schedule(hour: int = 2, minute: int = 0) -> None:
    from scheduler import start_scheduler

    start_scheduler(hour=hour, minute=minute)


async def _init_db() -> None:
    settings = get_settings()
    settings.ensure_dirs()
    await Database(settings.database_url).init()
    console.print(f"Initialized database: {settings.database_url}")


async def run_pipeline(
    tld: str | None = None,
    top: int | None = None,
    min_score: int | None = None,
) -> None:
    settings = get_settings()
    settings.ensure_dirs()
    db = Database(settings.database_url)
    await db.init()
    config = await ConfigService(db).get_config()
    await CrawlRunnerService(db, config).crawl_enabled_tlds(tld=tld)
    service = PipelineService(db, config)
    result = await service.run(
        tld=tld,
        top=top,
        min_score=min_score,
        source="cli",
    )

    console.print(f"Job: {result.job_id}")
    console.print(f"Deleted domains: {result.total_deleted}")
    console.print(f"After filters: {result.total_filtered}")
    console.print(f"Scored candidates: {result.total_scored}")
    console.print(f"Available candidates: {result.total_available}")
    console.print(f"Notified candidates: {result.notified}")


if __name__ == "__main__":
    cli()
