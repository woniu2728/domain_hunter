from __future__ import annotations

import asyncio
from datetime import date, timedelta
import tempfile
import unittest
from pathlib import Path

from backend.services.pipeline_service import load_deleted_from_zone_sources
from domain_hunter.types import AppConfig


class ZoneDownloadSkipTests(unittest.TestCase):
    def test_skips_download_when_today_zone_is_valid(self) -> None:
        asyncio.run(self._run_skip_test())

    async def _run_skip_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            zone_dir = data_dir / "zones" / "com"
            zone_dir.mkdir(parents=True)

            today = date.today()
            yesterday = today - timedelta(days=1)
            today_path = zone_dir / f"{today.isoformat()}.txt"
            yesterday_path = zone_dir / f"{yesterday.isoformat()}.txt"
            source_path = Path(tmpdir) / "source.txt"

            today_path.write_text("alpha.com. NS ns1.example.\n", encoding="utf-8")
            yesterday_path.write_text("alpha.com. NS ns1.example.\nbravo.com. NS ns1.example.\n", encoding="utf-8")
            source_path.write_text("source-overwrite.com. NS ns1.example.\n", encoding="utf-8")

            config = AppConfig(
                zone_sources=[
                    {
                        "tld": "com",
                        "zone_url": str(source_path),
                        "bearer_token": "",
                        "enabled": True,
                    }
                ]
            )

            deleted = await load_deleted_from_zone_sources(config, data_dir)

            self.assertEqual(deleted, {"bravo.com"})
            self.assertIn("alpha.com", today_path.read_text(encoding="utf-8"))
            self.assertNotIn("source-overwrite.com", today_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
