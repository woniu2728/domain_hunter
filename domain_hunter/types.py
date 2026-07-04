from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class DomainCandidate:
    domain: str
    tld: str
    length: int
    deleted_date: date
    status: str = "deleted"


@dataclass(frozen=True)
class ScoreResult:
    domain: str
    brand_score: int
    dictionary_score: int
    trend_score: int
    total_score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class AvailabilityResult:
    domain: str
    available: bool
    provider: str
    raw_status: str


@dataclass(frozen=True)
class HistoryResult:
    domain: str
    archive: bool
    spam: bool
    notes: str


@dataclass(frozen=True)
class AppConfig:
    app_env: str = "local"
    database_url: str = "runtime/database/domain_hunter.sqlite3"
    data_dir: str = "runtime/data"
    cache_dir: str = "runtime/cache"
    zone_sources: list[dict[str, Any]] = field(default_factory=list)
    filter_min_length: int = 4
    filter_max_length: int = 12
    filter_letters_only: bool = True
    filter_require_vowel: bool = True
    filter_no_digits: bool = True
    filter_no_hyphen: bool = True
    filter_max_consecutive_consonants: int = 3
    availability_provider: str = "mock"
    availability_concurrency: int = 10
    availability_timeout_seconds: int = 12
    wayback_enabled: bool = True
    wayback_timeout_seconds: int = 12
    top_candidates: int = 200
    min_score: int = 40
    schedule_enabled: bool = False
    schedule_hour: int = 2
    schedule_minute: int = 0
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    email_from: str = ""
    email_to: str = ""
    send_empty_report: bool = False

    def masked(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        for key in ("smtp_password",):
            if data.get(key):
                data[key] = "********"
        data["zone_sources"] = [
            {**source, "bearer_token": "********" if source.get("bearer_token") else ""}
            for source in self.zone_sources
        ]
        return data


@dataclass(frozen=True)
class JobSummary:
    id: int
    status: str
    source: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    total_deleted: int
    total_filtered: int
    total_scored: int
    total_available: int
