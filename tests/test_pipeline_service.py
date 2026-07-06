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


if __name__ == "__main__":
    unittest.main()
