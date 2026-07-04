from __future__ import annotations

from pathlib import Path
from typing import Optional
import asyncio

import typer
from rich.console import Console

from backend.services.config_service import ConfigService
from backend.services.pipeline_service import PipelineService
from config import get_settings
from database import Database


cli = typer.Typer(help="Discover deleted, high-value .com domains.")
console = Console()


@cli.command("init-db")
def init_db() -> None:
    asyncio.run(_init_db())


@cli.command("run")
def run(
    today_zone: Optional[Path] = typer.Option(None, help="Path to today's .com zone file."),
    yesterday_zone: Optional[Path] = typer.Option(None, help="Path to yesterday's .com zone file."),
    deleted_file: Optional[Path] = typer.Option(None, help="Optional file containing deleted domains, one per line."),
    top: Optional[int] = typer.Option(None, help="Number of candidates to query."),
    min_score: Optional[int] = typer.Option(None, help="Minimum score before availability query."),
) -> None:
    asyncio.run(
        run_pipeline(
            today_zone=today_zone,
            yesterday_zone=yesterday_zone,
            deleted_file=deleted_file,
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
    today_zone: Path | None = None,
    yesterday_zone: Path | None = None,
    deleted_file: Path | None = None,
    top: int | None = None,
    min_score: int | None = None,
) -> None:
    settings = get_settings()
    settings.ensure_dirs()
    db = Database(settings.database_url)
    await db.init()
    config = await ConfigService(db).get_config()
    service = PipelineService(db, config)
    result = await service.run(
        today_zone=today_zone,
        yesterday_zone=yesterday_zone,
        deleted_file=deleted_file,
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
