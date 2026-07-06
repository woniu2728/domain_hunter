from __future__ import annotations

from dataclasses import dataclass

from domain_hunter.types import SourceDomain


@dataclass(frozen=True)
class CrawlerAccount:
    id: str
    username: str
    password: str
    proxy_id: str = ""


@dataclass(frozen=True)
class CrawlerProxy:
    id: str
    name: str
    url: str


@dataclass(frozen=True)
class CrawlResult:
    tld: str
    pages_fetched: int
    domains_seen: int
    available_domains: list[SourceDomain]
