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


class EmailApiTests(unittest.TestCase):
    def test_test_email_requires_smtp_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "email.sqlite3")
            asyncio.run(db.init())
            original_db = api_main._db
            api_main._db = lambda: db
            try:
                with TestClient(api_main.app) as client:
                    response = client.post("/api/config/test-email")
            finally:
                api_main._db = original_db

        self.assertEqual(response.status_code, 400)
        self.assertIn("SMTP", response.json()["detail"])

    def test_test_email_uses_saved_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "email.sqlite3")
            asyncio.run(db.init())
            asyncio.run(
                ConfigService(db).update_config(
                    {
                        "smtp_host": "smtp.example.com",
                        "email_from": "from@example.com",
                        "email_to": "to@example.com",
                    }
                )
            )
            original_db = api_main._db
            api_main._db = lambda: db
            try:
                with patch("backend.main.send_test_email", AsyncMock(return_value=None)) as send:
                    with TestClient(api_main.app) as client:
                        response = client.post("/api/config/test-email")
            finally:
                api_main._db = original_db

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "sent"})
        send.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
