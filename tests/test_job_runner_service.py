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

    def test_cleanup_stale_running_cancels_existing_jobs(self) -> None:
        asyncio.run(self._run_cleanup_stale_running_test())

    def test_scheduled_job_retries_and_notifies_after_final_failure(self) -> None:
        asyncio.run(self._run_schedule_retry_failure_test())

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

    async def _run_cleanup_stale_running_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "jobs.sqlite3")
            await db.init()
            job_id = await db.create_job("schedule")
            runner = JobRunnerService()
            runner.start(lambda: db)

            await runner.cleanup_stale_running()

            job = await db.get_job(job_id)
            self.assertEqual(job.status, "cancelled")
            self.assertEqual(job.error, "服务启动时清理未完成任务")

    async def _run_schedule_retry_failure_test(self) -> None:
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
                    ],
                    "failure_retry_count": 2,
                    "failure_retry_delay_seconds": 0,
                    "smtp_host": "smtp.example.com",
                    "email_from": "from@example.com",
                    "email_to": "to@example.com",
                }
            )
            runner = JobRunnerService()
            runner.start(lambda: db)

            with patch("backend.services.job_runner_service.PipelineService") as pipeline:
                pipeline.return_value.run = AsyncMock(side_effect=RuntimeError("boom"))
                with patch("backend.services.job_runner_service.notify_job_failure", AsyncMock(return_value=None)) as notify:
                    job_id = await runner.start_if_idle(source="schedule")
                    await runner.current_task

            jobs = await db.list_jobs()
            self.assertEqual(job_id, 1)
            self.assertEqual([job.status for job in reversed(jobs)], ["failed", "failed", "failed"])
            self.assertEqual([job.source for job in reversed(jobs)], ["schedule", "schedule-retry", "schedule-retry"])
            self.assertEqual(pipeline.return_value.run.await_count, 3)
            notify.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
