from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
import gzip
import shutil

import httpx


def _is_http_url(value: str) -> bool:
    return urlparse(value).scheme in {"http", "https"}


async def download_zone(url_or_path: str, destination: Path, bearer_token: str | None = None) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _is_http_url(url_or_path):
        headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("GET", url_or_path, headers=headers) as response:
                response.raise_for_status()
                with destination.open("wb") as file:
                    async for chunk in response.aiter_bytes():
                        file.write(chunk)
        return destination

    source = Path(url_or_path)
    if not source.exists():
        raise FileNotFoundError(f"Zone source does not exist: {source}")
    shutil.copyfile(source, destination)
    return destination


def load_zone_domains(path: Path, tld: str = "com") -> set[str]:
    opener = gzip.open if path.suffix == ".gz" else open
    domains: set[str] = set()
    suffix = f".{tld.lower()}"

    with opener(path, "rt", encoding="utf-8", errors="ignore") as file:
        for line in file:
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            first = stripped.split()[0].rstrip(".").lower()
            if first == tld:
                continue
            if first.endswith(suffix):
                domains.add(first)
    return domains
