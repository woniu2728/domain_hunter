from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import backend.main as api_main
from backend.services.config_service import ConfigService
from database import Database
from domain_hunter.types import ScoreResult


class LlmApiTests(unittest.TestCase):
    def test_test_llm_requires_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "llm.sqlite3")
            asyncio.run(db.init())
            original_db = api_main._db
            api_main._db = lambda: db
            try:
                with TestClient(api_main.app) as client:
                    response = client.post("/api/config/test-llm")
            finally:
                api_main._db = original_db

        self.assertEqual(response.status_code, 400)
        self.assertIn("Base URL", response.json()["detail"])

    def test_test_llm_returns_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "llm.sqlite3")
            asyncio.run(db.init())
            asyncio.run(
                ConfigService(db).update_config(
                    {
                        "llm_base_url": "https://llm.example/v1",
                        "llm_api_key": "key",
                        "llm_model_id": "model",
                    }
                )
            )
            original_db = api_main._db
            api_main._db = lambda: db
            score = ScoreResult("flowmint.com", 88, 0, 0, 88, ("ai-score", "brandable"))
            try:
                with patch("backend.main.test_llm_scoring", AsyncMock(return_value=score)) as test_llm:
                    with TestClient(api_main.app) as client:
                        response = client.post("/api/config/test-llm")
            finally:
                api_main._db = original_db

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["score"], 88)
        test_llm.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
