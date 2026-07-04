from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, call, patch

from fastapi.testclient import TestClient

import backend.main as api_main


class JobsApiTests(unittest.TestCase):
    def test_stop_job_cancels_running_task(self) -> None:
        with patch("backend.main.job_runner_service.cancel_running", AsyncMock(return_value=None)) as cancel:
            with TestClient(api_main.app) as client:
                response = client.post("/api/jobs/stop")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "cancelled"})
        self.assertIn(call("用户手动停止任务"), cancel.await_args_list)


if __name__ == "__main__":
    unittest.main()
