from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urljoin

from config import get_settings
from crawler.expireddomains_parser import parse_deleted_domains
from crawler.types import CrawlResult, CrawlerAccount, CrawlerProxy


BASE_URL = "https://www.expireddomains.net"


class CrawlBlockedError(RuntimeError):
    pass


class ExpiredDomainsCrawler:
    def __init__(
        self,
        account: CrawlerAccount,
        proxy: CrawlerProxy | None = None,
        request_delay_seconds: int = 12,
        snapshot_dir: Path | None = None,
    ) -> None:
        self.account = account
        self.proxy = proxy
        self.request_delay_seconds = max(0, request_delay_seconds)
        settings = get_settings()
        self.snapshot_dir = snapshot_dir or settings.data_dir / "snapshots"

    async def test_proxy(self) -> None:
        await asyncio.to_thread(self._fetch_html, BASE_URL)

    async def test_login(self) -> None:
        html = await asyncio.to_thread(self._fetch_html, f"{BASE_URL}/login/")
        if "captcha" in html.lower():
            raise CrawlBlockedError("登录页出现验证码，需要人工处理。")

    async def crawl_tld(self, tld: str, max_pages: int, run_id: int | None = None) -> CrawlResult:
        clean_tld = tld.strip().lower().lstrip(".")
        url = build_deleted_url(clean_tld)
        all_available = []
        domains_seen = 0
        pages_fetched = 0
        for page_index in range(max(1, max_pages)):
            html = await asyncio.to_thread(self._fetch_html, url)
            pages_fetched += 1
            self._save_snapshot(html, clean_tld, page_index + 1, run_id)
            available, seen, next_url = parse_deleted_domains(html, clean_tld)
            domains_seen += seen
            all_available.extend(available)
            if not next_url:
                break
            url = urljoin(BASE_URL, next_url)
            if self.request_delay_seconds:
                await asyncio.sleep(self.request_delay_seconds)
        return CrawlResult(
            tld=clean_tld,
            pages_fetched=pages_fetched,
            domains_seen=domains_seen,
            available_domains=all_available,
        )

    def _fetch_html(self, url: str) -> str:
        try:
            from scrapling.fetchers import StealthyFetcher
        except Exception as exc:  # pragma: no cover - depends on optional install details
            raise RuntimeError("Scrapling fetcher 不可用，请安装 scrapling[fetchers] 并执行 scrapling install。") from exc

        kwargs = {
            "headless": True,
            "network_idle": True,
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy.url
        response = StealthyFetcher.fetch(url, **kwargs)
        status = int(getattr(response, "status", getattr(response, "status_code", 200)) or 200)
        if status in {403, 429}:
            raise CrawlBlockedError(f"访问受限，HTTP {status}")
        html = getattr(response, "text", None) or str(response)
        return str(html)

    def _save_snapshot(self, html: str, tld: str, page: int, run_id: int | None) -> None:
        if run_id is None:
            return
        target_dir = self.snapshot_dir / str(run_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / f"{tld}-{page}.html").write_text(html, encoding="utf-8")


def build_deleted_url(tld: str) -> str:
    clean_tld = tld.strip().lower().lstrip(".")
    if clean_tld:
        return f"{BASE_URL}/deleted-{clean_tld}-domains/"
    return f"{BASE_URL}/deleted-domains/"
