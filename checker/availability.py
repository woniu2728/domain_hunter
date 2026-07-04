from __future__ import annotations

from typing import Iterable
import asyncio

import httpx

from domain_hunter.types import AvailabilityResult


async def check_availability(
    domains: Iterable[str],
    provider: str = "mock",
    concurrency: int = 10,
    timeout_seconds: int = 12,
) -> list[AvailabilityResult]:
    if provider == "mock":
        return [
            AvailabilityResult(domain=domain, available=True, provider="mock", raw_status="assumed_available")
            for domain in domains
        ]
    if provider != "rdap":
        raise ValueError(f"Unsupported availability provider: {provider}")

    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        tasks = [_check_rdap(client, semaphore, domain) for domain in domains]
        return list(await asyncio.gather(*tasks))


async def _check_rdap(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    domain: str,
) -> AvailabilityResult:
    url = f"https://rdap.verisign.com/com/v1/domain/{domain}"
    async with semaphore:
        try:
            response = await client.get(url)
        except httpx.HTTPError as exc:
            return AvailabilityResult(domain=domain, available=False, provider="rdap", raw_status=str(exc))

    if response.status_code == 404:
        return AvailabilityResult(domain=domain, available=True, provider="rdap", raw_status="404")
    if response.status_code == 200:
        return AvailabilityResult(domain=domain, available=False, provider="rdap", raw_status="200")
    return AvailabilityResult(
        domain=domain,
        available=False,
        provider="rdap",
        raw_status=str(response.status_code),
    )
