from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import json

import aiosqlite

from domain_hunter.types import DomainCandidate, HistoryResult, JobSummary, ScoreResult


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
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("d.status = ?")
            params.append(status)
        if search:
            clauses.append("d.domain LIKE ?")
            params.append(f"%{search}%")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)

        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                f"""
                SELECT d.domain, d.tld, d.length, d.deleted_date, d.status,
                       s.brand_score, s.dictionary_score, s.trend_score, s.total_score, s.reasons,
                       h.archive, h.spam, h.notes
                FROM domains d
                LEFT JOIN score s ON s.domain_id = d.id
                LEFT JOIN history h ON h.domain_id = d.id
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
