from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

from checker import check_availability, check_history
from config import get_settings
from database import Database
from diff import diff_deleted_domains
from domain_hunter.types import AppConfig, DomainCandidate, ScoreResult
from downloader import download_zone, load_zone_domains
from filters import DefaultDomainFilter, filter_domains
from notifier import notify_results
from scorer.ai_score import score_domains_for_config


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
            await self.db.upsert_zone_diff(deleted, diff_date=date.today().isoformat(), source=source)

            filtered = filter_domains(deleted, filters=(self._domain_filter(),))
            counts["total_filtered"] = len(filtered)

            threshold = self.config.min_score if min_score is None else min_score
            candidate_limit = self.config.top_candidates if top is None else top
            scored = await score_domains_for_config(filtered, self.config)
            scores = [score for score in scored if score.total_score >= threshold]
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
                tld=_domain_tld(score.domain),
                length=len(_domain_label(score.domain)),
                deleted_date=date.today(),
            )
            for score in scores
        ]
        await self.db.upsert_domains(candidates)
        await self.db.upsert_scores(scores)

    def _domain_filter(self) -> DefaultDomainFilter:
        return DefaultDomainFilter(
            min_length=self.config.filter_min_length,
            max_length=self.config.filter_max_length,
            allowed_tlds=self._allowed_tlds(),
            letters_only=self.config.filter_letters_only,
            require_vowel=self.config.filter_require_vowel,
            no_digits=self.config.filter_no_digits,
            no_hyphen=self.config.filter_no_hyphen,
            max_consecutive_consonants=self.config.filter_max_consecutive_consonants,
        )

    def _allowed_tlds(self) -> tuple[str, ...]:
        enabled_tlds = tuple(
            str(source.get("tld", "")).strip().lower().lstrip(".")
            for source in self.config.zone_sources
            if source.get("enabled") and source.get("tld")
        )
        return tuple(tld for tld in enabled_tlds if tld)


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

    deleted_from_sources = await load_deleted_from_zone_sources(config, settings.data_dir)
    if deleted_from_sources:
        return deleted_from_sources

    return set()


async def load_deleted_from_zone_sources(config: AppConfig, data_dir: Path) -> set[str]:
    deleted: set[str] = set()
    today = date.today()
    yesterday = today - timedelta(days=1)
    for source in _enabled_zone_sources(config):
        tld = source["tld"]
        today_path = _zone_path(data_dir, tld, today, source["zone_url"])
        yesterday_path = _matching_yesterday_path(data_dir, tld, yesterday)
        await download_zone(source["zone_url"], today_path, source.get("bearer_token") or None)
        if not yesterday_path:
            continue
        today_domains = load_zone_domains(today_path, tld=tld)
        yesterday_domains = load_zone_domains(yesterday_path, tld=tld)
        deleted.update(diff_deleted_domains(yesterday_domains, today_domains))
    return deleted


def _enabled_zone_sources(config: AppConfig) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for source in config.zone_sources:
        tld = str(source.get("tld", "")).strip().lower().lstrip(".")
        zone_url = str(source.get("zone_url", "")).strip()
        if source.get("enabled") and tld and zone_url:
            sources.append(
                {
                    "tld": tld,
                    "zone_url": zone_url,
                    "bearer_token": str(source.get("bearer_token", "")),
                }
            )
    return sources


def _zone_path(data_dir: Path, tld: str, day: date, zone_url: str) -> Path:
    suffix = ".gz" if urlparse(zone_url).path.lower().endswith(".gz") else ".txt"
    return data_dir / "zones" / tld / f"{day.isoformat()}{suffix}"


def _matching_yesterday_path(data_dir: Path, tld: str, day: date) -> Path | None:
    base = data_dir / "zones" / tld
    for suffix in (".txt", ".gz"):
        path = base / f"{day.isoformat()}{suffix}"
        if path.exists():
            return path
    return None


def _domain_label(domain: str) -> str:
    return domain.rsplit(".", 1)[0]


def _domain_tld(domain: str) -> str:
    return domain.rsplit(".", 1)[1] if "." in domain else ""
