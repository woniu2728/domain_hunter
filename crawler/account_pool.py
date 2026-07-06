from __future__ import annotations

from crawler.types import CrawlerAccount, CrawlerProxy


def select_account(accounts: list[dict]) -> CrawlerAccount:
    for account in accounts:
        if not account.get("enabled", True):
            continue
        if str(account.get("status", "healthy")) not in {"healthy", "cooldown"}:
            continue
        username = str(account.get("username", "")).strip()
        password = str(account.get("password", ""))
        if username and password:
            return CrawlerAccount(
                id=str(account.get("id", "")),
                username=username,
                password=password,
                proxy_id=str(account.get("proxy_id", "")),
            )
    raise ValueError("没有可用的 ExpiredDomains.net 账号。")


def select_proxy(account: CrawlerAccount, proxies: list[dict], default_proxy_id: str = "") -> CrawlerProxy | None:
    target_id = account.proxy_id or default_proxy_id
    if not target_id:
        return None
    for proxy in proxies:
        if str(proxy.get("id", "")) != target_id:
            continue
        if not proxy.get("enabled", True):
            return None
        if str(proxy.get("status", "healthy")) not in {"healthy", "cooldown"}:
            return None
        url = str(proxy.get("url", "")).strip()
        if not url:
            return None
        return CrawlerProxy(id=target_id, name=str(proxy.get("name", target_id)), url=url)
    return None
