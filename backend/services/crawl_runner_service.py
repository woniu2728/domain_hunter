from __future__ import annotations

from datetime import date, timedelta

from backend.services.config_service import ConfigService
from crawler.account_pool import select_account, select_proxy
from crawler.expireddomains import ExpiredDomainsCrawler
from database import Database
from domain_hunter.types import AppConfig


class CrawlRunnerService:
    def __init__(self, db: Database, config: AppConfig) -> None:
        self.db = db
        self.config = config

    async def crawl_enabled_tlds(self, tld: str | None = None) -> list[str]:
        schedules = _enabled_schedules(self.config, tld)
        if not schedules:
            raise ValueError("请先配置并启用至少一个后缀爬取计划。")
        if self.config.expireddomains_cleanup_enabled:
            keep_days = max(1, self.config.expireddomains_keep_days)
            keep_from = (date.today() - timedelta(days=keep_days - 1)).isoformat()
            await self.db.clear_old_source_domains(keep_from)

        crawled_tlds: list[str] = []
        for schedule in schedules:
            await self.crawl_tld(schedule)
            crawled_tlds.append(str(schedule["tld"]))
        return crawled_tlds

    async def crawl_tld(self, schedule: dict) -> None:
        account = select_account(self.config.expireddomains_accounts)
        proxy = select_proxy(account, self.config.expireddomains_proxies, self.config.expireddomains_default_proxy_id)
        tld = str(schedule["tld"])
        run_id = await self.db.create_crawler_run(
            provider="expireddomains",
            tld=tld,
            account_id=account.id,
            proxy_id=proxy.id if proxy else "",
        )
        crawler = ExpiredDomainsCrawler(
            account=account,
            proxy=proxy,
            request_delay_seconds=int(schedule.get("request_delay_seconds", 12)),
        )
        try:
            result = await crawler.crawl_tld(
                tld,
                max_pages=int(schedule.get("max_pages", 20)),
                run_id=run_id,
                max_length=int(schedule.get("filter_max_length", 0) or 0) or None,
                allow_digits=bool(schedule.get("filter_allow_digits", True)),
            )
            today = date.today().isoformat()
            await self.db.clear_source_domains(today, tlds=[tld])
            await self.db.upsert_source_domains(result.available_domains, source_date=today)
            await self.db.finish_crawler_run(
                run_id,
                "success",
                pages_fetched=result.pages_fetched,
                domains_seen=result.domains_seen,
                available_seen=len(result.available_domains),
                error=None,
            )
        except Exception as exc:
            await self.db.finish_crawler_run(
                run_id,
                "failed",
                pages_fetched=0,
                domains_seen=0,
                available_seen=0,
                error=str(exc),
            )
            raise


async def test_account(db: Database, account_id: str) -> None:
    config = await ConfigService(db).get_config()
    account = _find_account(config, account_id)
    proxy = select_proxy(account, config.expireddomains_proxies, config.expireddomains_default_proxy_id)
    await ExpiredDomainsCrawler(account, proxy).test_login()


async def verify_account_email_code(db: Database, account_id: str, code: str) -> None:
    config = await ConfigService(db).get_config()
    account = _find_account(config, account_id)
    proxy = select_proxy(account, config.expireddomains_proxies, config.expireddomains_default_proxy_id)
    await ExpiredDomainsCrawler(account, proxy).verify_email_code(code)


async def test_proxy(db: Database, proxy_id: str) -> None:
    config = await ConfigService(db).get_config()
    proxy = _find_proxy(config, proxy_id)
    account = _first_account(config)
    await ExpiredDomainsCrawler(account, proxy).test_proxy()


async def test_fetch_first_page(db: Database, tld: str) -> dict:
    config = await ConfigService(db).get_config()
    schedule = _schedule_for_tld(config, tld) or {
        "tld": tld,
        "max_pages": 1,
        "request_delay_seconds": 0,
    }
    account = select_account(config.expireddomains_accounts)
    proxy = select_proxy(account, config.expireddomains_proxies, config.expireddomains_default_proxy_id)
    crawler = ExpiredDomainsCrawler(account, proxy, request_delay_seconds=0)
    result = await crawler.crawl_tld(
        str(schedule["tld"]),
        max_pages=1,
        max_length=int(schedule.get("filter_max_length", 0) or 0) or None,
        allow_digits=bool(schedule.get("filter_allow_digits", True)),
    )
    return {
        "tld": result.tld,
        "pages_fetched": result.pages_fetched,
        "domains_seen": result.domains_seen,
        "available_seen": len(result.available_domains),
        "items": [domain.__dict__ for domain in result.available_domains[:20]],
    }


def _enabled_schedules(config: AppConfig, tld: str | None = None) -> list[dict]:
    requested = tld.strip().lower().lstrip(".") if tld else ""
    return [
        schedule
        for schedule in config.expireddomains_tld_schedules
        if schedule.get("enabled", True)
        and schedule.get("tld")
        and (not requested or str(schedule.get("tld", "")).lower().lstrip(".") == requested)
    ]


def _schedule_for_tld(config: AppConfig, tld: str) -> dict | None:
    clean = tld.strip().lower().lstrip(".")
    for schedule in config.expireddomains_tld_schedules:
        if str(schedule.get("tld", "")).strip().lower().lstrip(".") == clean:
            return schedule
    return None


def _find_account(config: AppConfig, account_id: str):
    for account in config.expireddomains_accounts:
        if str(account.get("id", "")) == account_id:
            return select_account([account])
    raise ValueError("账号不存在。")


def _find_proxy(config: AppConfig, proxy_id: str):
    for proxy in config.expireddomains_proxies:
        if str(proxy.get("id", "")) == proxy_id:
            from crawler.types import CrawlerProxy

            return CrawlerProxy(id=proxy_id, name=str(proxy.get("name", proxy_id)), url=str(proxy.get("url", "")))
    raise ValueError("代理不存在。")


def _first_account(config: AppConfig):
    try:
        return select_account(config.expireddomains_accounts)
    except ValueError:
        from crawler.types import CrawlerAccount

        return CrawlerAccount(id="proxy-test", username="", password="")
