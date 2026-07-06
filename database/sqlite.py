from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import json

import aiosqlite

from domain_hunter.types import DomainCandidate, HistoryResult, JobSummary, ScoreResult, SourceDomain


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL UNIQUE,
    tld TEXT NOT NULL,
    length INTEGER NOT NULL,
    deleted_date TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS score (
    domain_id INTEGER PRIMARY KEY,
    brand_score INTEGER NOT NULL,
    dictionary_score INTEGER NOT NULL,
    trend_score INTEGER NOT NULL,
    total_score INTEGER NOT NULL,
    reasons TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(domain_id) REFERENCES domains(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS history (
    domain_id INTEGER PRIMARY KEY,
    archive INTEGER NOT NULL,
    spam INTEGER NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(domain_id) REFERENCES domains(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    value_type TEXT NOT NULL,
    is_secret INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error TEXT,
    total_deleted INTEGER NOT NULL DEFAULT 0,
    total_filtered INTEGER NOT NULL DEFAULT 0,
    total_scored INTEGER NOT NULL DEFAULT 0,
    total_available INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_one_running_job
ON jobs(status)
WHERE status = 'running';

CREATE TABLE IF NOT EXISTS zone_diff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    tld TEXT NOT NULL,
    diff_date TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'zone',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(domain, diff_date)
);

CREATE TABLE IF NOT EXISTS deleted_domain_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    tld TEXT NOT NULL,
    provider TEXT NOT NULL,
    source_status TEXT NOT NULL,
    dropped_date TEXT,
    source_date TEXT NOT NULL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(domain, provider, source_date)
);

CREATE TABLE IF NOT EXISTS crawler_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    tld TEXT NOT NULL,
    account_id TEXT,
    proxy_id TEXT,
    status TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    pages_fetched INTEGER NOT NULL DEFAULT 0,
    domains_seen INTEGER NOT NULL DEFAULT 0,
    available_seen INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def upsert_domains(self, candidates: Iterable[DomainCandidate]) -> None:
        rows = [
            (
                candidate.domain,
                candidate.tld,
                candidate.length,
                candidate.deleted_date.isoformat(),
                candidate.status,
            )
            for candidate in candidates
        ]
        if not rows:
            return
        async with aiosqlite.connect(self.path) as db:
            await db.executemany(
                """
                INSERT INTO domains(domain, tld, length, deleted_date, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    tld=excluded.tld,
                    length=excluded.length,
                    deleted_date=excluded.deleted_date,
                    status=excluded.status,
                    updated_at=CURRENT_TIMESTAMP
                """,
                rows,
            )
            await db.commit()

    async def upsert_scores(self, scores: Iterable[ScoreResult]) -> None:
        rows = [
            (
                score.domain,
                score.brand_score,
                score.dictionary_score,
                score.trend_score,
                score.total_score,
                ", ".join(score.reasons),
            )
            for score in scores
        ]
        if not rows:
            return
        async with aiosqlite.connect(self.path) as db:
            await db.executemany(
                """
                INSERT INTO score(domain_id, brand_score, dictionary_score, trend_score, total_score, reasons)
                SELECT id, ?, ?, ?, ?, ? FROM domains WHERE domain = ?
                ON CONFLICT(domain_id) DO UPDATE SET
                    brand_score=excluded.brand_score,
                    dictionary_score=excluded.dictionary_score,
                    trend_score=excluded.trend_score,
                    total_score=excluded.total_score,
                    reasons=excluded.reasons,
                    created_at=CURRENT_TIMESTAMP
                """,
                [
                    (
                        brand_score,
                        dictionary_score,
                        trend_score,
                        total_score,
                        reasons,
                        domain,
                    )
                    for domain, brand_score, dictionary_score, trend_score, total_score, reasons in rows
                ],
            )
            await db.commit()

    async def upsert_history(self, histories: Iterable[HistoryResult]) -> None:
        rows = [
            (
                history.domain,
                int(history.archive),
                int(history.spam),
                history.notes,
            )
            for history in histories
        ]
        if not rows:
            return
        async with aiosqlite.connect(self.path) as db:
            await db.executemany(
                """
                INSERT INTO history(domain_id, archive, spam, notes)
                SELECT id, ?, ?, ? FROM domains WHERE domain = ?
                ON CONFLICT(domain_id) DO UPDATE SET
                    archive=excluded.archive,
                    spam=excluded.spam,
                    notes=excluded.notes,
                    checked_at=CURRENT_TIMESTAMP
                """,
                [(archive, spam, notes, domain) for domain, archive, spam, notes in rows],
            )
            await db.commit()

    async def update_status(self, domain: str, status: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE domains SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE domain = ?",
                (status, domain),
            )
            await db.commit()

    async def upsert_zone_diff(self, domains: Iterable[str], diff_date: str, source: str = "zone") -> None:
        rows = [
            (
                domain,
                domain.rsplit(".", 1)[1] if "." in domain else "",
                diff_date,
                source,
            )
            for domain in domains
        ]
        if not rows:
            return
        async with aiosqlite.connect(self.path) as db:
            await db.executemany(
                """
                INSERT INTO zone_diff(domain, tld, diff_date, source)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(domain, diff_date) DO UPDATE SET
                    tld=excluded.tld,
                    source=excluded.source
                """,
                rows,
            )
            await db.commit()

    async def upsert_source_domains(
        self,
        domains: Iterable[SourceDomain],
        source_date: str,
        provider: str = "expireddomains",
    ) -> None:
        rows = [
            (
                item.domain,
                item.tld,
                provider,
                item.source_status,
                item.dropped_date,
                source_date,
                json.dumps(item.metrics),
            )
            for item in domains
        ]
        if not rows:
            return
        async with aiosqlite.connect(self.path) as db:
            await db.executemany(
                """
                INSERT INTO deleted_domain_sources(domain, tld, provider, source_status, dropped_date, source_date, metrics_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(domain, provider, source_date) DO UPDATE SET
                    tld=excluded.tld,
                    source_status=excluded.source_status,
                    dropped_date=excluded.dropped_date,
                    metrics_json=excluded.metrics_json,
                    last_seen_at=CURRENT_TIMESTAMP
                """,
                rows,
            )
            await db.commit()

    async def clear_old_source_domains(self, keep_from_date: str, provider: str = "expireddomains") -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM deleted_domain_sources WHERE provider = ? AND source_date < ?",
                (provider, keep_from_date),
            )
            await db.commit()

    async def clear_source_domains(
        self,
        source_date: str,
        provider: str = "expireddomains",
        tlds: list[str] | None = None,
    ) -> None:
        clauses = ["provider = ?", "source_date = ?"]
        params: list[Any] = [provider, source_date]
        if tlds:
            placeholders = ", ".join("?" for _ in tlds)
            clauses.append(f"tld IN ({placeholders})")
            params.extend(tlds)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                f"DELETE FROM deleted_domain_sources WHERE {' AND '.join(clauses)}",
                tuple(params),
            )
            await db.commit()

    async def clear_candidates(self, tlds: list[str] | None = None) -> None:
        clauses: list[str] = []
        params: list[Any] = []
        if tlds:
            placeholders = ", ".join("?" for _ in tlds)
            clauses.append(f"tld IN ({placeholders})")
            params.extend(tlds)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        async with aiosqlite.connect(self.path) as db:
            ids = [row[0] for row in await db.execute_fetchall(f"SELECT id FROM domains {where}", tuple(params))]
            if not ids:
                return
            placeholders = ", ".join("?" for _ in ids)
            await db.execute(f"DELETE FROM score WHERE domain_id IN ({placeholders})", tuple(ids))
            await db.execute(f"DELETE FROM history WHERE domain_id IN ({placeholders})", tuple(ids))
            await db.execute(f"DELETE FROM domains WHERE id IN ({placeholders})", tuple(ids))
            await db.commit()

    async def list_source_domains(
        self,
        source_date: str,
        limit: int = 5000,
        tlds: list[str] | None = None,
        search: str | None = None,
        provider: str = "expireddomains",
    ) -> list[str]:
        clauses = ["provider = ?", "source_date = ?"]
        params: list[Any] = [provider, source_date]
        if tlds:
            placeholders = ", ".join("?" for _ in tlds)
            clauses.append(f"tld IN ({placeholders})")
            params.extend(tlds)
        if search:
            clauses.append("domain LIKE ?")
            params.append(f"%{search}%")
        params.append(limit)
        async with aiosqlite.connect(self.path) as db:
            rows = await db.execute_fetchall(
                f"""
                SELECT domain
                FROM deleted_domain_sources
                WHERE {' AND '.join(clauses)}
                ORDER BY domain ASC
                LIMIT ?
                """,
                tuple(params),
            )
        return [row[0] for row in rows]

    async def list_source_domain_rows(
        self,
        source_date: str,
        limit: int = 5000,
        tlds: list[str] | None = None,
        search: str | None = None,
        provider: str = "expireddomains",
    ) -> list[SourceDomain]:
        clauses = ["provider = ?", "source_date = ?", "source_status = 'available'"]
        params: list[Any] = [provider, source_date]
        if tlds:
            placeholders = ", ".join("?" for _ in tlds)
            clauses.append(f"tld IN ({placeholders})")
            params.extend(tlds)
        if search:
            clauses.append("domain LIKE ?")
            params.append(f"%{search}%")
        params.append(limit)
        async with aiosqlite.connect(self.path) as db:
            rows = await db.execute_fetchall(
                f"""
                SELECT domain, tld, source_status, dropped_date, metrics_json
                FROM deleted_domain_sources
                WHERE {' AND '.join(clauses)}
                ORDER BY domain ASC
                LIMIT ?
                """,
                tuple(params),
            )
        return [
            SourceDomain(
                domain=row[0],
                tld=row[1],
                source_status=row[2],
                dropped_date=row[3],
                metrics=json.loads(row[4] or "{}"),
            )
            for row in rows
        ]

    async def source_domain_stats(self, source_date: str, provider: str = "expireddomains") -> dict[str, int]:
        async with aiosqlite.connect(self.path) as db:
            total = (
                await db.execute_fetchall(
                    "SELECT COUNT(DISTINCT domain) FROM deleted_domain_sources WHERE provider = ? AND source_date = ?",
                    (provider, source_date),
                )
            )[0][0]
            tlds = (
                await db.execute_fetchall(
                    "SELECT COUNT(DISTINCT tld) FROM deleted_domain_sources WHERE provider = ? AND source_date = ?",
                    (provider, source_date),
                )
            )[0][0]
        return {"deleted_domains": total, "deleted_tlds": tlds}

    async def create_crawler_run(self, provider: str, tld: str, account_id: str = "", proxy_id: str = "") -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                INSERT INTO crawler_runs(provider, tld, account_id, proxy_id, status, started_at)
                VALUES (?, ?, ?, ?, 'running', CURRENT_TIMESTAMP)
                """,
                (provider, tld, account_id, proxy_id),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def finish_crawler_run(
        self,
        run_id: int,
        status: str,
        pages_fetched: int,
        domains_seen: int,
        available_seen: int,
        error: str | None = None,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                UPDATE crawler_runs
                SET status = ?,
                    finished_at = CURRENT_TIMESTAMP,
                    pages_fetched = ?,
                    domains_seen = ?,
                    available_seen = ?,
                    error = ?
                WHERE id = ?
                """,
                (status, pages_fetched, domains_seen, available_seen, error, run_id),
            )
            await db.commit()

    async def crawler_run_stats(self) -> dict[str, int]:
        async with aiosqlite.connect(self.path) as db:
            today_runs = (
                await db.execute_fetchall(
                    "SELECT COUNT(*) FROM crawler_runs WHERE date(started_at) = date('now')"
                )
            )[0][0]
            failed_runs = (
                await db.execute_fetchall(
                    "SELECT COUNT(*) FROM crawler_runs WHERE status = 'failed'"
                )
            )[0][0]
        return {"crawler_runs": today_runs, "crawler_failed_runs": failed_runs}

    async def list_zone_diff_domains(
        self,
        limit: int = 5000,
        tlds: list[str] | None = None,
        search: str | None = None,
    ) -> list[str]:
        clauses: list[str] = []
        params: list[Any] = []
        if tlds:
            placeholders = ", ".join("?" for _ in tlds)
            clauses.append(f"tld IN ({placeholders})")
            params.extend(tlds)
        if search:
            clauses.append("domain LIKE ?")
            params.append(f"%{search}%")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        async with aiosqlite.connect(self.path) as db:
            rows = await db.execute_fetchall(
                f"""
                SELECT domain
                FROM zone_diff
                {where}
                GROUP BY domain
                ORDER BY MAX(diff_date) DESC, domain ASC
                LIMIT ?
                """,
                tuple(params),
            )
        return [row[0] for row in rows]

    async def zone_diff_stats(self) -> dict[str, int]:
        async with aiosqlite.connect(self.path) as db:
            total = (await db.execute_fetchall("SELECT COUNT(DISTINCT domain) FROM zone_diff"))[0][0]
            tlds = (await db.execute_fetchall("SELECT COUNT(DISTINCT tld) FROM zone_diff"))[0][0]
        return {"deleted_domains": total, "deleted_tlds": tlds}

    async def get_settings(self) -> dict[str, Any]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall("SELECT key, value, value_type FROM settings")
        return {row["key"]: _decode_setting(row["value"], row["value_type"]) for row in rows}

    async def set_settings(self, values: dict[str, Any], secret_keys: set[str] | None = None) -> None:
        if not values:
            return
        secrets = secret_keys or set()
        rows = [
            (
                key,
                json.dumps(value),
                _setting_type(value),
                int(key in secrets),
            )
            for key, value in values.items()
        ]
        async with aiosqlite.connect(self.path) as db:
            await db.executemany(
                """
                INSERT INTO settings(key, value, value_type, is_secret)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    value_type=excluded.value_type,
                    is_secret=excluded.is_secret,
                    updated_at=CURRENT_TIMESTAMP
                """,
                rows,
            )
            await db.commit()

    async def create_job(self, source: str) -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "INSERT INTO jobs(status, source, started_at) VALUES ('running', ?, CURRENT_TIMESTAMP)",
                (source,),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def has_running_job(self) -> bool:
        async with aiosqlite.connect(self.path) as db:
            row = (await db.execute_fetchall("SELECT COUNT(*) FROM jobs WHERE status = 'running'"))[0]
        return int(row[0]) > 0

    async def cancel_running_jobs(self, reason: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                UPDATE jobs
                SET status = 'cancelled',
                    finished_at = CURRENT_TIMESTAMP,
                    error = ?
                WHERE status = 'running'
                """,
                (reason,),
            )
            await db.commit()

    async def cancel_job_if_running(self, job_id: int, reason: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                UPDATE jobs
                SET status = 'cancelled',
                    finished_at = CURRENT_TIMESTAMP,
                    error = ?
                WHERE id = ? AND status = 'running'
                """,
                (reason, job_id),
            )
            await db.commit()

    async def finish_job(
        self,
        job_id: int,
        status: str,
        total_deleted: int,
        total_filtered: int,
        total_scored: int,
        total_available: int,
        error: str | None = None,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                UPDATE jobs
                SET status = ?,
                    finished_at = CURRENT_TIMESTAMP,
                    error = ?,
                    total_deleted = ?,
                    total_filtered = ?,
                    total_scored = ?,
                    total_available = ?
                WHERE id = ?
                """,
                (status, error, total_deleted, total_filtered, total_scored, total_available, job_id),
            )
            await db.commit()

    async def list_jobs(self, limit: int = 50) -> list[JobSummary]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                """
                SELECT id, status, source, started_at, finished_at, error,
                       total_deleted, total_filtered, total_scored, total_available
                FROM jobs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
        return [_job_from_row(row) for row in rows]

    async def get_job(self, job_id: int) -> JobSummary | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                """
                SELECT id, status, source, started_at, finished_at, error,
                       total_deleted, total_filtered, total_scored, total_available
                FROM jobs
                WHERE id = ?
                """,
                (job_id,),
            )
        return _job_from_row(rows[0]) if rows else None

    async def list_candidates(
        self,
        limit: int = 100,
        status: str | None = None,
        search: str | None = None,
        tld: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("d.status = ?")
            params.append(status)
        if search:
            clauses.append("d.domain LIKE ?")
            params.append(f"%{search}%")
        if tld:
            clauses.append("d.tld = ?")
            params.append(tld.strip().lower().lstrip("."))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)

        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                f"""
                SELECT d.domain, d.tld, d.length, d.deleted_date, d.status,
                       s.brand_score, s.dictionary_score, s.trend_score, s.total_score, s.reasons
                FROM domains d
                LEFT JOIN score s ON s.domain_id = d.id
                {where}
                ORDER BY COALESCE(s.total_score, 0) DESC, d.updated_at DESC
                LIMIT ?
                """,
                tuple(params),
            )
        return [dict(row) for row in rows]

    async def stats(self) -> dict[str, int]:
        async with aiosqlite.connect(self.path) as db:
            domains = (await db.execute_fetchall("SELECT COUNT(*) FROM domains"))[0][0]
            available = (await db.execute_fetchall("SELECT COUNT(*) FROM domains WHERE status = 'available'"))[0][0]
            spam = (await db.execute_fetchall("SELECT COUNT(*) FROM history WHERE spam = 1"))[0][0]
            jobs = (await db.execute_fetchall("SELECT COUNT(*) FROM jobs"))[0][0]
        return {"domains": domains, "available": available, "spam": spam, "jobs": jobs}


def _setting_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, list):
        return "json"
    if isinstance(value, dict):
        return "json"
    return "str"


def _decode_setting(value: str, value_type: str) -> Any:
    decoded = json.loads(value)
    if value_type == "bool":
        return bool(decoded)
    if value_type == "int":
        return int(decoded)
    if value_type == "json":
        return decoded
    return str(decoded)


def _job_from_row(row: aiosqlite.Row) -> JobSummary:
    return JobSummary(
        id=row["id"],
        status=row["status"],
        source=row["source"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error=row["error"],
        total_deleted=row["total_deleted"],
        total_filtered=row["total_filtered"],
        total_scored=row["total_scored"],
        total_available=row["total_available"],
    )
