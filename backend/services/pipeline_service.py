from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from database import Database
from domain_hunter.types import AppConfig, DomainCandidate, ScoreResult, SourceDomain
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
        deleted_domains: set[str] | None = None,
        tld: str | None = None,
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
            source_rows = await self._source_rows(deleted_domains, tld)
            source_status_by_domain = {row.domain: row.source_status for row in source_rows}
            deleted = {row.domain for row in source_rows}
            counts["total_deleted"] = len(deleted)

            filtered = sorted(deleted)
            counts["total_filtered"] = len(filtered)

            candidate_limit = self.config.top_candidates if top is None else top
            scored = await score_domains_for_config(filtered, self.config)
            limited_scores = scored[:candidate_limit]
            counts["total_scored"] = len(limited_scores)
            counts["total_available"] = sum(
                1 for score in limited_scores if source_status_by_domain.get(score.domain, "available") == "available"
            )

            await self.db.clear_candidates(tlds=[tld.strip().lower().lstrip(".")] if tld else None)
            await self._save_scores(limited_scores, source_status_by_domain)

            await notify_results(limited_scores, [], self.config)

            if job_id is not None:
                await self.db.finish_job(job_id, "success", error=None, **counts)
            return PipelineResult(job_id=job_id, notified=len(limited_scores), **counts)
        except Exception as exc:
            if job_id is not None:
                await self.db.finish_job(job_id, "failed", error=str(exc), **counts)
            raise

    async def _save_scores(self, scores: list[ScoreResult], source_status_by_domain: dict[str, str]) -> None:
        candidates = [
            DomainCandidate(
                domain=score.domain,
                tld=_domain_tld(score.domain),
                length=len(_domain_label(score.domain)),
                deleted_date=date.today(),
                status=source_status_by_domain.get(score.domain, "available"),
            )
            for score in scores
        ]
        await self.db.upsert_domains(candidates)
        await self.db.upsert_scores(scores)

    async def _source_rows(self, deleted_domains: set[str] | None, tld: str | None) -> list[SourceDomain]:
        if deleted_domains is not None:
            return [
                SourceDomain(
                    domain=domain,
                    tld=_domain_tld(domain),
                    source_status="available",
                    dropped_date=date.today().isoformat(),
                )
                for domain in deleted_domains
            ]
        return await self.db.list_source_domain_rows(
            source_date=date.today().isoformat(),
            tlds=[tld] if tld else None,
            limit=50000,
        )


def _domain_label(domain: str) -> str:
    return domain.rsplit(".", 1)[0]


def _domain_tld(domain: str) -> str:
    return domain.rsplit(".", 1)[1] if "." in domain else ""
