from __future__ import annotations

import asyncio
from datetime import date
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import backend.main as api_main
from database import Database
from domain_hunter.types import SourceDomain


class PreviewApiTests(unittest.TestCase):
    def test_preview_reads_source_domains_with_temporary_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "preview.sqlite3")
            asyncio.run(db.init())
            asyncio.run(
                db.upsert_source_domains(
                    [
                        SourceDomain("flowmint.com", "com"),
                        SourceDomain("validname.net", "net"),
                        SourceDomain("bad-123.net", "net"),
                    ],
                    source_date=date.today().isoformat(),
                )
            )

            original_db = api_main._db
            api_main._db = lambda: db
            try:
                with TestClient(api_main.app) as client:
                    response = client.post(
                        "/api/domains/preview",
                        json={
                            "tlds": "net",
                            "source_limit": 100,
                            "filter_min_length": 4,
                            "filter_max_length": 12,
                            "filter_letters_only": True,
                            "filter_require_vowel": True,
                            "filter_no_digits": True,
                            "filter_no_hyphen": True,
                            "filter_max_consecutive_consonants": 3,
                            "top_candidates": 10,
                            "min_score": 40,
                        },
                    )
            finally:
                api_main._db = original_db

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_source"], 2)
        self.assertEqual(data["total_filtered"], 1)
        self.assertEqual(data["items"][0]["domain"], "validname.net")
        self.assertEqual(data["items"][0]["status"], "preview")


if __name__ == "__main__":
    unittest.main()
