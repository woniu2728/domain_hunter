from __future__ import annotations

from collections.abc import Iterable
import json
import re

import httpx

from domain_hunter.types import AppConfig, ScoreResult
from scorer.brand_score import score_domains


BATCH_SIZE = 50


async def score_domains_for_config(domains: Iterable[str], config: AppConfig) -> list[ScoreResult]:
    domain_list = list(domains)
    if not _llm_enabled(config):
        return score_domains(domain_list)
    try:
        return await _score_domains_with_llm(domain_list, config)
    except Exception:
        return score_domains(domain_list)


async def test_llm_scoring(config: AppConfig, domain: str = "flowmint.com") -> ScoreResult:
    if not _llm_enabled(config):
        raise ValueError("请先配置 Base URL、API Key 和 Model ID。")
    return (await _score_domains_with_llm([domain], config))[0]


async def _score_domains_with_llm(domains: list[str], config: AppConfig) -> list[ScoreResult]:
    scores: list[ScoreResult] = []
    async with httpx.AsyncClient(timeout=60) as client:
        for batch in _chunks(domains, BATCH_SIZE):
            scores.extend(await _score_batch(client, batch, config))
    return sorted(scores, key=lambda item: item.total_score, reverse=True)


async def _score_batch(client: httpx.AsyncClient, domains: list[str], config: AppConfig) -> list[ScoreResult]:
    response = await client.post(
        _chat_completions_url(config.llm_base_url),
        headers={"Authorization": f"Bearer {config.llm_api_key}", "Content-Type": "application/json"},
        json={
            "model": config.llm_model_id,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You score deleted domains for brandability. "
                        "Return only valid JSON, no markdown. "
                        "Score each domain from 0 to 100. Consider memorability, length, pronunciation, "
                        "commercial intent, clarity, and spam risk."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Return JSON in this exact shape: "
                        '{"scores":[{"domain":"example.com","score":80,"reason":"brief reason"}]}. '
                        f"Domains: {', '.join(domains)}"
                    ),
                },
            ],
        },
    )
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return _parse_scores(content, domains)


def _parse_scores(content: str, expected_domains: list[str]) -> list[ScoreResult]:
    parsed = json.loads(_strip_code_fence(content))
    rows = parsed.get("scores") if isinstance(parsed, dict) else parsed
    if not isinstance(rows, list):
        raise ValueError("LLM score response must contain a scores list")

    by_domain: dict[str, ScoreResult] = {}
    expected = {domain.lower() for domain in expected_domains}
    for row in rows:
        if not isinstance(row, dict):
            continue
        domain = str(row.get("domain", "")).strip().lower()
        if domain not in expected:
            continue
        score = _clamp_score(row.get("score"))
        reason = str(row.get("reason", "")).strip()
        reasons = ("ai-score", reason) if reason else ("ai-score",)
        by_domain[domain] = ScoreResult(
            domain=domain,
            brand_score=score,
            dictionary_score=0,
            trend_score=0,
            total_score=score,
            reasons=reasons,
        )

    if set(by_domain) != expected:
        missing = sorted(expected - set(by_domain))
        raise ValueError(f"LLM score response missing domains: {', '.join(missing)}")
    return [by_domain[domain.lower()] for domain in expected_domains]


def _llm_enabled(config: AppConfig) -> bool:
    return bool(config.llm_base_url.strip() and config.llm_api_key.strip() and config.llm_model_id.strip())


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _strip_code_fence(content: str) -> str:
    stripped = content.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
    return match.group(1).strip() if match else stripped


def _clamp_score(value: object) -> int:
    score = int(float(value))
    return max(0, min(100, score))


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]
