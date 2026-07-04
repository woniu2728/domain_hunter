from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from domain_hunter.types import AppConfig
from notifier.notify import notify_job_failure


class NotifyTests(unittest.TestCase):
    def test_notify_job_failure_sends_email_when_configured(self) -> None:
        config = AppConfig(
            smtp_host="smtp.example.com",
            email_from="from@example.com",
            email_to="to@example.com",
            smtp_username="user",
            smtp_password="pass",
        )
        smtp = MagicMock()

        with patch("notifier.notify.smtplib.SMTP") as smtp_cls:
            smtp_cls.return_value.__enter__.return_value = smtp
            self.run_async(notify_job_failure(config, job_id=7, source="schedule", error="boom", attempt=3, max_attempts=3))

        smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=20)
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("user", "pass")
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["Subject"], "Domain Hunter - Task Failed #7")
        self.assertIn("boom", message.get_content())
        self.assertIn("3/3", message.get_content())

    def test_notify_job_failure_skips_when_email_is_not_configured(self) -> None:
        with patch("notifier.notify.smtplib.SMTP") as smtp_cls:
            self.run_async(notify_job_failure(AppConfig(), job_id=7, source="schedule", error="boom", attempt=1, max_attempts=1))

        smtp_cls.assert_not_called()

    def run_async(self, awaitable) -> None:
        import asyncio

        asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()
