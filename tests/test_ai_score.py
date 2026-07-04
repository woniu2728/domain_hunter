from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

from domain_hunter.types import AppConfig
from scorer.ai_score import score_domains_for_config


class AiScoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_scores_with_openai_compatible_response(self) -> None:
        config = AppConfig(llm_base_url="https://llm.example/v1", llm_api_key="key", llm_model_id="model")
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"scores":[{"domain":"flowmint.com","score":91,"reason":"brandable"}]}'
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=response)):
            scores = await score_domains_for_config(["flowmint.com"], config)

        self.assertEqual(scores[0].total_score, 91)
        self.assertEqual(scores[0].reasons, ("ai-score", "brandable"))

    async def test_falls_back_to_local_scoring_when_llm_fails(self) -> None:
        config = AppConfig(llm_base_url="https://llm.example/v1", llm_api_key="key", llm_model_id="model")

        with patch("httpx.AsyncClient.post", AsyncMock(side_effect=RuntimeError("boom"))):
            scores = await score_domains_for_config(["flowmint.com"], config)

        self.assertGreaterEqual(scores[0].total_score, 70)
        self.assertIn("two-word", scores[0].reasons)


if __name__ == "__main__":
    unittest.main()
