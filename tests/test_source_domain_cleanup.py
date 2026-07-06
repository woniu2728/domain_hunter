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


if __name__ == "__main__":
    unittest.main()
