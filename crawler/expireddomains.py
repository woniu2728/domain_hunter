from __future__ import annotations

import asyncio
import re
from hashlib import sha1
from pathlib import Path
from urllib.parse import urlencode, urljoin

from config import get_settings
from crawler.expireddomains_parser import parse_deleted_domains
from crawler.types import CrawlResult, CrawlerAccount, CrawlerProxy


BASE_URL = "https://www.expireddomains.net"
MEMBER_BASE_URL = "https://member.expireddomains.net"
SUPPORTED_TLD_IDS = {
    "com": 2,
    "ai": 26,
    "io": 125,
    "me": 268,
}


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
        self.session_dir = settings.cache_dir / "expireddomains_sessions" / self._session_key()

    async def test_proxy(self) -> None:
        await asyncio.to_thread(self._fetch_html, BASE_URL)

    async def test_login(self) -> None:
        html = await asyncio.to_thread(self._fetch_html, build_deleted_url("com"))
        if "captcha" in html.lower():
            raise CrawlBlockedError("登录页出现验证码，需要人工处理。")
        if _looks_like_email_auth_page(html):
            raise CrawlBlockedError("ExpiredDomains.net 要求邮箱验证码验证，请提交邮件验证码后重试。")
        if _looks_like_login_page(html):
            raise CrawlBlockedError("登录失败，请检查 ExpiredDomains.net 账号密码。")

    async def verify_email_code(self, code: str) -> None:
        clean_code = code.strip()
        if not clean_code:
            raise ValueError("验证码不能为空。")
        await asyncio.to_thread(self._fetch_html, build_deleted_url("com"), self._verify_email_if_needed(clean_code))

    async def crawl_tld(
        self,
        tld: str,
        max_pages: int,
        run_id: int | None = None,
        max_length: int | None = None,
        allow_digits: bool = True,
    ) -> CrawlResult:
        clean_tld = tld.strip().lower().lstrip(".")
        url = build_deleted_url(clean_tld, max_length=max_length, allow_digits=allow_digits)
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

    def _fetch_html(self, url: str, page_action=None) -> str:
        try:
            from scrapling.fetchers import StealthyFetcher
        except Exception as exc:  # pragma: no cover - depends on optional install details
            raise RuntimeError("Scrapling fetcher 不可用，请安装 scrapling[fetchers] 并执行 scrapling install。") from exc

        kwargs = {
            "headless": True,
            "network_idle": True,
            "user_data_dir": str(self.session_dir),
            "page_action": page_action or self._login_if_needed,
            "wait": 1000,
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy.url
        self.session_dir.mkdir(parents=True, exist_ok=True)
        response = StealthyFetcher.fetch(url, **kwargs)
        status = int(getattr(response, "status", getattr(response, "status_code", 200)) or 200)
        if status in {403, 429}:
            raise CrawlBlockedError(f"访问受限，HTTP {status}")
        body = getattr(response, "body", None)
        if isinstance(body, bytes):
            return body.decode(getattr(response, "encoding", None) or "utf-8", errors="replace")
        html = getattr(response, "html_content", None)
        if html:
            return str(html)
        text = getattr(response, "text", None)
        return str(text or response)

    def _login_if_needed(self, page) -> None:
        if not _is_login_url(page.url) and not _looks_like_login_page(page.content()):
            return

        username_selector = 'input[name="login"], input[name="username"], input[name="user"], input[type="text"]'
        password_selector = 'input[name="password"], input[name="pass"], input[type="password"]'
        try:
            page.wait_for_selector(password_selector, timeout=8000)
            password = page.locator(password_selector).first
            form = password.locator("xpath=ancestor::form[1]")
            form.locator(username_selector).first.fill(self.account.username)
            password.fill(self.account.password)
            with page.expect_navigation(wait_until="networkidle", timeout=20000):
                form.locator('button[type="submit"], input[type="submit"]').first.click()
        except Exception as exc:
            raise CrawlBlockedError("登录表单提交失败，可能出现验证码或页面结构变化。") from exc

        content = page.content()
        if "captcha" in content.lower():
            raise CrawlBlockedError("登录页出现验证码，需要人工处理。")
        if _is_login_url(page.url) or _looks_like_login_page(content):
            raise CrawlBlockedError("登录失败，请检查 ExpiredDomains.net 账号密码。")

    def _verify_email_if_needed(self, code: str):
        def verify(page) -> None:
            self._login_if_needed(page)
            content = page.content()
            if not _looks_like_email_auth_page(content):
                return
            try:
                page.wait_for_selector('input[name="secret_code"]', timeout=8000)
                page.locator('input[name="secret_code"]').first.fill(code)
                remember = page.locator('input[name="rememberme"]')
                if remember.count():
                    remember.first.check()
                with page.expect_navigation(wait_until="networkidle", timeout=20000):
                    page.locator('button[type="submit"], input[type="submit"], button').filter(has_text="Verify").first.click()
            except Exception as exc:
                raise CrawlBlockedError("邮箱验证码提交失败，请确认验证码是否正确或是否已过期。") from exc
            if _looks_like_email_auth_page(page.content()):
                raise CrawlBlockedError("邮箱验证码验证失败，请确认验证码是否正确或是否已过期。")

        return verify

    def _save_snapshot(self, html: str, tld: str, page: int, run_id: int | None) -> None:
        if run_id is None:
            return
        target_dir = self.snapshot_dir / str(run_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / f"{tld}-{page}.html").write_text(html, encoding="utf-8")

    def _session_key(self) -> str:
        identity = f"{self.account.id}:{self.account.username}:{self.proxy.id if self.proxy else 'direct'}"
        return sha1(identity.encode("utf-8")).hexdigest()[:16]


def build_deleted_url(tld: str, max_length: int | None = None, allow_digits: bool = True) -> str:
    clean_tld = tld.strip().lower().lstrip(".")
    if clean_tld not in SUPPORTED_TLD_IDS:
        raise ValueError("当前仅支持 com、ai、io、me 后缀。")
    params: list[tuple[str, str | int]] = [("o", "changes"), ("r", "d"), ("ftlds[]", SUPPORTED_TLD_IDS[clean_tld])]
    if max_length is not None and max_length > 0:
        params.append(("fmaxhost", int(max_length)))
    if not allow_digits:
        params.append(("fnumhost", 1))
    query = urlencode(params, safe="[]")
    return f"{MEMBER_BASE_URL}/domains/combinedexpired/?{query}#listing"


def _is_login_url(url: str) -> bool:
    return "/login" in url.lower()


def _looks_like_login_page(html: str) -> bool:
    lowered = html.lower()
    return bool(re.search(r"<input[^>]+type=[\"']?password", lowered)) and ("login" in lowered or "username" in lowered)


def _looks_like_email_auth_page(html: str) -> bool:
    lowered = html.lower()
    return "emailauth" in lowered and ("secret_code" in lowered or "multi factor authentication" in lowered or "verify code" in lowered)
