from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.services.config_service import ConfigService
from backend.services.job_runner_service import JobRunnerService
from database import Database


class JobRunnerServiceTests(unittest.TestCase):
    def test_restart_cancels_running_job_and_creates_new_job(self) -> None:
        asyncio.run(self._run_restart_test())

    async def _run_restart_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "jobs.sqlite3")
            await db.init()
            await ConfigService(db).update_config(
                {
                    "zone_sources": [
                        {
                            "tld": "com",
                            "zone_url": str(Path(tmpdir) / "today.txt"),
                            "bearer_token": "",
                            "enabled": True,
                        }
                    ]
                }
            )
            old_job_id = await db.create_job("api")
            runner = JobRunnerService()
            runner.start(lambda: db)

            with patch("backend.services.job_runner_service.PipelineService") as pipeline:
                pipeline.return_value.run = AsyncMock(return_value=None)
                new_job_id = await runner.restart(source="api")
                await runner.current_task

            self.assertNotEqual(old_job_id, new_job_id)
            old_job = await db.get_job(old_job_id)
            new_job = await db.get_job(new_job_id)
            self.assertEqual(old_job.status, "cancelled")
            self.assertEqual(old_job.error, "任务被新的配置重启")
            self.assertEqual(new_job.status, "running")


if __name__ == "__main__":
    unittest.main()
