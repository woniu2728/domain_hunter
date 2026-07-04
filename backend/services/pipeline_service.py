from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from checker import check_availability, check_history
from config import get_settings
from database import Database
from diff import diff_deleted_domains
from domain_hunter.types import AppConfig, DomainCandidate, ScoreResult
from downloader import download_zone, load_zone_domains
from filters import filter_domains
from notifier import notify_results
from scorer import score_domains


@dataclass(frozen=True)
class PipelineResult:
    job_id: int | None
    total_deleted: int
    total_filtered: int
    total_scored: int
    total_available: int
    notified: int


class PipelineService:
    def __init__(self, db: Database, config: AppConfig) -> None:
        self.db = db
        self.config = config

    async def run(
        self,
        today_zone: Path | None = None,
        yesterday_zone: Path | None = None,
        deleted_file: Path | None = None,
        deleted_domains: set[str] | None = None,
        source: str = "manual",
        top: int | None = None,
        min_score: int | None = None,
        create_job: bool = True,
        job_id: int | None = None,
    ) -> PipelineResult:
        await self.db.init()
        if job_id is None and create_job:
            job_id = await self.db.create_job(source)
        counts = {
            "total_deleted": 0,
            "total_filtered": 0,
            "total_scored": 0,
            "total_available": 0,
        }

        try:
            deleted = deleted_domains or await load_deleted_domains(today_zone, yesterday_zone, deleted_file, self.config)
            counts["total_deleted"] = len(deleted)

            filtered = filter_domains(deleted)
            counts["total_filtered"] = len(filtered)

            threshold = self.config.min_score if min_score is None else min_score
            candidate_limit = self.config.top_candidates if top is None else top
            scores = [score for score in score_domains(filtered) if score.total_score >= threshold]
            limited_scores = scores[:candidate_limit]
            counts["total_scored"] = len(limited_scores)

            await self._save_scores(limited_scores)

            availability = await check_availability(
                [score.domain for score in limited_scores],
                provider=self.config.availability_provider,
                concurrency=self.config.availability_concurrency,
                timeout_seconds=self.config.availability_timeout_seconds,
            )
            available_domains = [item.domain for item in availability if item.available]
            counts["total_available"] = len(available_domains)
            for item in availability:
                await self.db.update_status(item.domain, "available" if item.available else "registered")

            histories = await check_history(
                available_domains,
                enabled=self.config.wayback_enabled,
                timeout_seconds=self.config.wayback_timeout_seconds,
            )
            await self.db.upsert_history(histories)
            clean_domains = {history.domain for history in histories if not history.spam}
            final_scores = [score for score in limited_scores if score.domain in clean_domains]

            await notify_results(final_scores, histories, self.config)

            if job_id is not None:
                await self.db.finish_job(job_id, "success", error=None, **counts)
            return PipelineResult(job_id=job_id, notified=len(final_scores), **counts)
        except Exception as exc:
            if job_id is not None:
                await self.db.finish_job(job_id, "failed", error=str(exc), **counts)
            raise

    async def _save_scores(self, scores: list[ScoreResult]) -> None:
        candidates = [
            DomainCandidate(
                domain=score.domain,
                tld="com",
                length=len(score.domain.removesuffix(".com")),
                deleted_date=date.today(),
            )
            for score in scores
        ]
        await self.db.upsert_domains(candidates)
        await self.db.upsert_scores(scores)


async def load_deleted_domains(
    today_zone: Path | None,
    yesterday_zone: Path | None,
    deleted_file: Path | None,
    config: AppConfig,
) -> set[str]:
    settings = get_settings()
    if deleted_file:
        return {
            line.strip().lower()
            for line in deleted_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    if today_zone and yesterday_zone:
        today = load_zone_domains(today_zone)
        yesterday = load_zone_domains(yesterday_zone)
        return diff_deleted_domains(yesterday, today)

    if config.czds_zone_url:
        today_path = settings.data_dir / f"com-zone-{date.today().isoformat()}.txt"
        await download_zone(config.czds_zone_url, today_path, config.czds_bearer_token or None)
        raise ValueError(
            "Downloaded today's zone. Provide yesterday zone or run with deleted_file after computing a diff."
        )

    raise ValueError("Provide deleted_file or both today_zone and yesterday_zone.")
