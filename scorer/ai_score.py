from __future__ import annotations

from collections.abc import Iterable
import json
import re

import httpx

from domain_hunter.types import AppConfig, ScoreResult


DEFAULT_SCORE_REASON = "大模型不可用，使用默认评分。"
DEFAULT_LLM_PROMPT = (
    "你是域名投资筛选助手。只返回合法 JSON，不要 Markdown。"
    "请为每个已删除域名按 0 到 100 评分，考虑品牌感、长度、发音、商业价值、清晰度和垃圾风险。"
    "reason 必须使用简体中文，简短说明评分原因。"
)


async def score_domains_for_config(domains: Iterable[str], config: AppConfig) -> list[ScoreResult]:
    domain_list = list(domains)
    if not _llm_enabled(config):
        return _default_scores(domain_list)
    try:
        return await _score_domains_with_llm(domain_list, config)
    except Exception:
        return _default_scores(domain_list)


async def test_llm_scoring(config: AppConfig, domain: str = "flowmint.com") -> ScoreResult:
    if not _llm_enabled(config):
        raise ValueError("请先配置 Base URL、API Key 和 Model ID。")
    return (await _score_domains_with_llm([domain], config))[0]


async def _score_domains_with_llm(domains: list[str], config: AppConfig) -> list[ScoreResult]:
    async with httpx.AsyncClient(timeout=60) as client:
        scores = await _score_batch(client, domains, config)
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
                    "content": _llm_prompt(config),
                },
                {
                    "role": "user",
                    "content": (
                        "按这个结构返回 JSON："
                        '{"scores":[{"domain":"example.com","score":80,"reason":"简短中文原因"}]}。'
                        "必须为下面所有域名输出评分，不要遗漏："
                        f"{', '.join(domains)}"
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
        reasons = (reason,) if reason else ("大模型评分",)
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


def _default_scores(domains: list[str]) -> list[ScoreResult]:
    return [
        ScoreResult(
            domain=domain,
            brand_score=100,
            dictionary_score=0,
            trend_score=0,
            total_score=100,
            reasons=(DEFAULT_SCORE_REASON,),
        )
        for domain in domains
    ]


def _llm_enabled(config: AppConfig) -> bool:
    return bool(config.llm_base_url.strip() and config.llm_api_key.strip() and config.llm_model_id.strip())


def _llm_prompt(config: AppConfig) -> str:
    return config.llm_prompt.strip() or DEFAULT_LLM_PROMPT


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
