from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from backend.services.pipeline_service import PipelineService
from database import Database
from domain_hunter.types import AppConfig, ScoreResult, SourceDomain


class PipelineServiceTests(unittest.TestCase):
    def test_pipeline_uses_source_status_without_second_checks(self) -> None:
        asyncio.run(self._run_pipeline_uses_source_status_without_second_checks())

    def test_pipeline_replaces_previous_candidates_after_success(self) -> None:
        asyncio.run(self._run_pipeline_replaces_previous_candidates_after_success())

    async def _run_pipeline_uses_source_status_without_second_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "pipeline.sqlite3")
            await db.init()
            await db.upsert_source_domains(
                [SourceDomain("flowmint.com", "com", source_status="available")],
                source_date=date.today().isoformat(),
            )
            config = AppConfig(expireddomains_tld_schedules=[{"tld": "com", "enabled": True}])
            score = ScoreResult("flowmint.com", 100, 0, 0, 100, ("默认评分",))

            with patch("backend.services.pipeline_service.score_domains_for_config", AsyncMock(return_value=[score])):
                result = await PipelineService(db, config).run(create_job=False)

            candidates = await db.list_candidates(limit=10)
            self.assertEqual(result.total_available, 1)
            self.assertEqual(candidates[0]["domain"], "flowmint.com")
            self.assertEqual(candidates[0]["status"], "available")

    async def _run_pipeline_replaces_previous_candidates_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "pipeline.sqlite3")
            await db.init()
            await db.upsert_source_domains(
                [SourceDomain("oldname.com", "com", source_status="available")],
                source_date=date.today().isoformat(),
            )
            old_score = ScoreResult("oldname.com", 100, 0, 0, 100, ("旧结果",))
            config = AppConfig(expireddomains_tld_schedules=[{"tld": "com", "enabled": True}])
            with patch("backend.services.pipeline_service.score_domains_for_config", AsyncMock(return_value=[old_score])):
                await PipelineService(db, config).run(create_job=False, tld="com")

            await db.clear_source_domains(date.today().isoformat(), tlds=["com"])
            await db.upsert_source_domains(
                [SourceDomain("newname.com", "com", source_status="available")],
                source_date=date.today().isoformat(),
            )
            new_score = ScoreResult("newname.com", 100, 0, 0, 100, ("新结果",))
            with patch("backend.services.pipeline_service.score_domains_for_config", AsyncMock(return_value=[new_score])):
                await PipelineService(db, config).run(create_job=False, tld="com")

            candidates = await db.list_candidates(limit=10)
            self.assertEqual([candidate["domain"] for candidate in candidates], ["newname.com"])


if __name__ == "__main__":
    unittest.main()
