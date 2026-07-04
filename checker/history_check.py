from __future__ import annotations

from typing import Iterable
import asyncio

import httpx

from domain_hunter.types import HistoryResult


SPAM_KEYWORDS = {
    "casino",
    "bet",
    "bonus",
    "poker",
    "porn",
    "adult",
    "loan",
    "payday",
    "viagra",
    "cialis",
}


async def check_history(
    domains: Iterable[str],
    enabled: bool = True,
    timeout_seconds: int = 12,
    concurrency: int = 5,
) -> list[HistoryResult]:
    domain_list = list(domains)
    if not enabled:
        return [HistoryResult(domain=domain, archive=False, spam=False, notes="wayback disabled") for domain in domain_list]

    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        tasks = [_check_one(client, semaphore, domain) for domain in domain_list]
        return list(await asyncio.gather(*tasks))


async def _check_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    domain: str,
) -> HistoryResult:
    params = {
        "url": f"{domain}/*",
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype",
        "filter": "statuscode:200",
        "limit": "25",
    }
    async with semaphore:
        try:
            response = await client.get("https://web.archive.org/cdx", params=params)
            response.raise_for_status()
            rows = response.json()
        except Exception as exc:
            return HistoryResult(domain=domain, archive=False, spam=False, notes=f"wayback error: {exc}")

    if not isinstance(rows, list) or len(rows) <= 1:
        return HistoryResult(domain=domain, archive=False, spam=False, notes="no archive")

    text = " ".join(str(item).lower() for row in rows[1:] for item in row)
    matched = sorted(keyword for keyword in SPAM_KEYWORDS if keyword in text)
    if matched:
        return HistoryResult(domain=domain, archive=True, spam=True, notes="spam keywords: " + ", ".join(matched))
    return HistoryResult(domain=domain, archive=True, spam=False, notes=f"{len(rows) - 1} snapshots sampled")
