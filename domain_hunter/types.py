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
class SourceDomain:
    domain: str
    tld: str
    source_status: str = "available"
    dropped_date: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AppConfig:
    app_env: str = "local"
    runtime_dir: str = "runtime"
    database_url: str = "runtime/database/domain_hunter.sqlite3"
    data_dir: str = "runtime/data"
    cache_dir: str = "runtime/cache"
    source_type: str = "expireddomains"
    expireddomains_accounts: list[dict[str, Any]] = field(default_factory=list)
    expireddomains_proxies: list[dict[str, Any]] = field(default_factory=list)
    expireddomains_default_proxy_id: str = ""
    expireddomains_tld_schedules: list[dict[str, Any]] = field(default_factory=list)
    expireddomains_cleanup_enabled: bool = True
    expireddomains_keep_days: int = 1
    top_candidates: int = 200
    min_score: int = 40
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model_id: str = ""
    llm_prompt: str = ""
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
    failure_retry_count: int = 2
    failure_retry_delay_seconds: int = 300

    def masked(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        for key in ("smtp_password", "llm_api_key"):
            if data.get(key):
                data[key] = "********"
        data["expireddomains_accounts"] = [
            {**account, "password": "********" if account.get("password") else ""}
            for account in self.expireddomains_accounts
        ]
        data["expireddomains_proxies"] = [
            {**proxy, "url": "********" if proxy.get("url") else ""}
            for proxy in self.expireddomains_proxies
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
    stage: str
    progress_message: str
    current_step: int
    total_steps: int
    total_deleted: int
    total_filtered: int
    total_scored: int
    total_available: int
