from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config as app_config
from backend.services.config_service import ConfigService
from database import Database


class ConfigServiceTests(unittest.TestCase):
    def test_runtime_dir_switch_derives_paths_and_copies_business_settings(self) -> None:
        asyncio.run(self._run_runtime_dir_test())

    async def _run_runtime_dir_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_file = Path(tmpdir) / "app_settings.json"
            initial_runtime = Path(tmpdir) / "runtime-a"
            next_runtime = Path(tmpdir) / "runtime-b"

            with patch.object(app_config, "RUNTIME_SETTINGS_PATH", settings_file):
                app_config.save_runtime_settings({"runtime_dir": str(initial_runtime)})
                db = Database(app_config.get_settings().database_url)
                await db.init()
                service = ConfigService(db)
                await service.update_config({"min_score": 55})

                updated = await service.update_config({"runtime_dir": str(next_runtime), "top_candidates": 25})

                self.assertEqual(updated.runtime_dir, str(next_runtime))
                self.assertEqual(updated.database_url, str(next_runtime / "database" / "domain_hunter.sqlite3"))
                self.assertEqual(updated.data_dir, str(next_runtime / "data"))
                self.assertEqual(updated.cache_dir, str(next_runtime / "cache"))
                self.assertEqual(updated.min_score, 55)
                self.assertEqual(updated.top_candidates, 25)


if __name__ == "__main__":
    unittest.main()
