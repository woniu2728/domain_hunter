from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from backend.services.config_service import ConfigService
from backend.services.scheduler_service import SCHEDULE_JOB_ID, SchedulerService
from database import Database


class SchedulerServiceTests(unittest.TestCase):
    def test_reload_registers_and_removes_daily_job(self) -> None:
        asyncio.run(self._run_reload_test())

    async def _run_reload_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "scheduler.sqlite3")
            await db.init()

            service = SchedulerService()
            await service.start(lambda: db)
            try:
                config = await ConfigService(db).update_config(
                    {
                        "schedule_enabled": True,
                        "schedule_hour": 3,
                        "schedule_minute": 15,
                    }
                )
                await service.reload(config)

                job = service.scheduler.get_job(SCHEDULE_JOB_ID)
                self.assertIsNotNone(job)
                self.assertIn("cron", str(job.trigger))
                self.assertIn("hour='3'", str(job.trigger))
                self.assertIn("minute='15'", str(job.trigger))

                config = await ConfigService(db).update_config({"schedule_enabled": False})
                await service.reload(config)

                self.assertIsNone(service.scheduler.get_job(SCHEDULE_JOB_ID))
            finally:
                service.shutdown()


if __name__ == "__main__":
    unittest.main()
