from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from database import Database
from domain_hunter.types import SourceDomain


class SourceDomainCleanupTests(unittest.TestCase):
    def test_clear_old_source_domains_keeps_today(self) -> None:
        asyncio.run(self._run_cleanup_test())

    def test_clear_source_domains_can_target_today_tld(self) -> None:
        asyncio.run(self._run_clear_current_tld_test())

    def test_init_adds_job_progress_columns_to_existing_database(self) -> None:
        asyncio.run(self._run_job_progress_migration_test())

    async def _run_cleanup_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "sources.sqlite3")
            await db.init()
            await db.upsert_source_domains([SourceDomain("old.com", "com")], source_date="2026-07-05")
            await db.upsert_source_domains([SourceDomain("today.com", "com")], source_date="2026-07-06")

            await db.clear_old_source_domains("2026-07-06")

            domains = await db.list_source_domains("2026-07-06")
            old_domains = await db.list_source_domains("2026-07-05")
            self.assertEqual(domains, ["today.com"])
            self.assertEqual(old_domains, [])

    async def _run_clear_current_tld_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "sources.sqlite3")
            await db.init()
            await db.upsert_source_domains(
                [SourceDomain("old-com.com", "com"), SourceDomain("keep-ai.ai", "ai")],
                source_date="2026-07-06",
            )

            await db.clear_source_domains("2026-07-06", tlds=["com"])

            self.assertEqual(await db.list_source_domains("2026-07-06", tlds=["com"]), [])
            self.assertEqual(await db.list_source_domains("2026-07-06", tlds=["ai"]), ["keep-ai.ai"])

    async def _run_job_progress_migration_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sources.sqlite3"
            import sqlite3

            con = sqlite3.connect(path)
            con.execute(
                """
                CREATE TABLE jobs (
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
                )
                """
            )
            con.commit()
            con.close()

            db = Database(path)
            await db.init()
            job_id = await db.create_job("api")
            await db.update_job_progress(job_id, "crawl", "抓取第 1 页", 1, 20)
            job = await db.get_job(job_id)

            self.assertIsNotNone(job)
            self.assertEqual(job.stage, "crawl")
            self.assertEqual(job.current_step, 1)


if __name__ == "__main__":
    unittest.main()
