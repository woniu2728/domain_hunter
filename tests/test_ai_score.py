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
                        "content": (
                            '{"scores":['
                            '{"domain":"flowmint.com","score":91,"reason":"简短好记，品牌感强"},'
                            '{"domain":"validname.net","score":82,"reason":"含义清晰，适合工具站"}'
                            "]}"
                        )
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=response)):
            scores = await score_domains_for_config(["flowmint.com", "validname.net"], config)

        self.assertEqual(scores[0].total_score, 91)
        self.assertEqual(scores[0].reasons, ("简短好记，品牌感强",))

    async def test_falls_back_to_default_score_when_llm_fails(self) -> None:
        config = AppConfig(llm_base_url="https://llm.example/v1", llm_api_key="key", llm_model_id="model")

        with patch("httpx.AsyncClient.post", AsyncMock(side_effect=RuntimeError("boom"))):
            scores = await score_domains_for_config(["flowmint.com"], config)

        self.assertEqual(scores[0].total_score, 100)
        self.assertEqual(scores[0].reasons, ("大模型不可用，使用默认评分。",))

    async def test_uses_one_llm_request_for_all_domains(self) -> None:
        config = AppConfig(llm_base_url="https://llm.example/v1", llm_api_key="key", llm_model_id="model")
        domains = [f"brand{i}.com" for i in range(75)]
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"scores":['
                        + ",".join(f'{{"domain":"{domain}","score":80,"reason":"中文原因"}}' for domain in domains)
                        + "]}"
                    }
                }
            ]
        }

        post = AsyncMock(return_value=response)
        with patch("httpx.AsyncClient.post", post):
            scores = await score_domains_for_config(domains, config)

        self.assertEqual(len(scores), 75)
        self.assertEqual(post.await_count, 1)

    async def test_uses_configured_prompt(self) -> None:
        config = AppConfig(
            llm_base_url="https://llm.example/v1",
            llm_api_key="key",
            llm_model_id="model",
            llm_prompt="自定义中文评分规则",
        )
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": '{"scores":[{"domain":"flowmint.com","score":90,"reason":"中文原因"}]}'}}]
        }
        post = AsyncMock(return_value=response)

        with patch("httpx.AsyncClient.post", post):
            await score_domains_for_config(["flowmint.com"], config)

        payload = post.await_args.kwargs["json"]
        self.assertEqual(payload["messages"][0]["content"], "自定义中文评分规则")


if __name__ == "__main__":
    unittest.main()
