from __future__ import annotations

from typing import Iterable
import re

from domain_hunter.types import ScoreResult

try:
    from wordfreq import zipf_frequency
except Exception:  # pragma: no cover - optional dependency fallback
    zipf_frequency = None  # type: ignore[assignment]


AI_KEYWORDS = {
    "ai",
    "agent",
    "bot",
    "data",
    "cloud",
    "prompt",
    "model",
    "neural",
    "auto",
}
COMMON_WORDS = {
    "app",
    "bank",
    "base",
    "bolt",
    "care",
    "cart",
    "code",
    "desk",
    "flow",
    "forge",
    "fund",
    "grid",
    "host",
    "hub",
    "labs",
    "link",
    "mint",
    "nova",
    "pay",
    "pixel",
    "shop",
    "sync",
    "vault",
    "wave",
}
VOWELS = set("aeiou")


def score_domain(domain: str) -> ScoreResult:
    label = domain.lower().removesuffix(".com")
    brand_score = 0
    dictionary_score = 0
    trend_score = 0
    reasons: list[str] = []

    if len(label) <= 8:
        brand_score += 20
        reasons.append("short")
    if label.isalpha():
        brand_score += 20
        reasons.append("letters-only")
    if any(keyword in label for keyword in AI_KEYWORDS):
        trend_score += 15
        reasons.append("ai-keyword")
    if _looks_pronounceable(label):
        brand_score += 15
        reasons.append("pronounceable")
    if _is_dictionary_word(label):
        dictionary_score += 30
        reasons.append("dictionary")
    if _looks_like_two_words(label):
        dictionary_score += 20
        reasons.append("two-word")
    if any(char.isdigit() for char in label):
        brand_score -= 30
        reasons.append("digit-penalty")
    if "-" in label:
        brand_score -= 50
        reasons.append("hyphen-penalty")

    total_score = max(0, brand_score + dictionary_score + trend_score)
    return ScoreResult(
        domain=domain,
        brand_score=brand_score,
        dictionary_score=dictionary_score,
        trend_score=trend_score,
        total_score=total_score,
        reasons=tuple(reasons),
    )


def score_domains(domains: Iterable[str]) -> list[ScoreResult]:
    return sorted((score_domain(domain) for domain in domains), key=lambda item: item.total_score, reverse=True)


def _looks_pronounceable(label: str) -> bool:
    if not label or not any(char in VOWELS for char in label):
        return False
    return re.search(r"[aeiou][bcdfghjklmnpqrstvwxyz]|[bcdfghjklmnpqrstvwxyz][aeiou]", label) is not None


def _is_dictionary_word(label: str) -> bool:
    if label in COMMON_WORDS:
        return True
    if zipf_frequency is None:
        return False
    return zipf_frequency(label, "en") >= 3.5


def _looks_like_two_words(label: str) -> bool:
    for index in range(3, len(label) - 2):
        left = label[:index]
        right = label[index:]
        if _is_dictionary_word(left) and _is_dictionary_word(right):
            return True
    return False
