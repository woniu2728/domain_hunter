from __future__ import annotations

from dataclasses import asdict, fields
from typing import Any

from config import RUNTIME_SETTING_KEYS, get_settings, save_runtime_settings
from database import Database
from domain_hunter.types import AppConfig


SECRET_KEYS = {"smtp_password", "llm_api_key"}
SUPPORTED_CRAWL_TLDS = {"com", "ai", "io", "me"}


class ConfigService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get_config(self) -> AppConfig:
        settings = get_settings()
        defaults = AppConfig(
            app_env=settings.app_env,
            runtime_dir=str(settings.runtime_dir),
            database_url=str(settings.database_url),
            data_dir=str(settings.data_dir),
            cache_dir=str(settings.cache_dir),
        )
        stored = await self.db.get_settings()
        data = asdict(defaults)
        data.update({key: value for key, value in stored.items() if key in data})
        data["expireddomains_tld_schedules"] = _normalize_tld_schedules(data.get("expireddomains_tld_schedules", []))
        return AppConfig(**data)

    async def public_config(self) -> dict[str, Any]:
        return (await self.get_config()).masked()

    async def update_config(self, payload: dict[str, Any]) -> AppConfig:
        current = await self.get_config()
        current_data = asdict(current)
        allowed = {field.name for field in fields(AppConfig)}
        updates: dict[str, Any] = {}
        runtime_updates: dict[str, str] = {}

        for key, value in payload.items():
            if key not in allowed:
                continue
            if key in {"database_url", "data_dir", "cache_dir"}:
                continue
            if key in SECRET_KEYS and (value is None or value == "" or value == "********"):
                continue
            if key == "expireddomains_accounts":
                updates[key] = _merge_accounts(value, current.expireddomains_accounts)
                continue
            if key == "expireddomains_proxies":
                updates[key] = _merge_proxies(value, current.expireddomains_proxies)
                continue
            if key == "expireddomains_tld_schedules":
                updates[key] = _normalize_tld_schedules(value)
                continue
            coerced = _coerce_value(key, value, current_data[key])
            if key in RUNTIME_SETTING_KEYS:
                runtime_updates[key] = str(coerced)
            else:
                updates[key] = coerced

        target_db = self.db
        if runtime_updates:
            save_runtime_settings(runtime_updates)
            settings = get_settings()
            target_db = Database(settings.database_url)
            await target_db.init()
            updates = _portable_settings(current_data) | updates
        if updates:
            await target_db.set_settings(updates, secret_keys=SECRET_KEYS)
        return await ConfigService(target_db).get_config()


def _coerce_value(key: str, value: Any, current_value: Any) -> Any:
    if isinstance(current_value, bool):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current_value, int):
        return int(value)
    if isinstance(current_value, list):
        return value if isinstance(value, list) else []
    if isinstance(current_value, dict):
        return value if isinstance(value, dict) else {}
    return "" if value is None else str(value)


def _portable_settings(current_data: dict[str, Any]) -> dict[str, Any]:
    runtime_keys = RUNTIME_SETTING_KEYS | {"app_env", "database_url", "data_dir", "cache_dir"}
    return {
        key: value
        for key, value in current_data.items()
        if key not in runtime_keys and key not in SECRET_KEYS
    }


def _merge_accounts(value: Any, current_accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    current_by_id = {str(account.get("id", "")): account for account in current_accounts if account.get("id")}
    merged: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        username = str(item.get("username", "")).strip()
        if not username:
            continue
        account_id = str(item.get("id", "")).strip() or f"acc-{index}"
        password = str(item.get("password", ""))
        if password == "********":
            password = str(current_by_id.get(account_id, {}).get("password", ""))
        merged.append(
            {
                "id": account_id,
                "username": username,
                "password": password,
                "proxy_id": str(item.get("proxy_id", "")).strip(),
                "enabled": bool(item.get("enabled", True)),
                "status": str(item.get("status", "healthy") or "healthy"),
                "last_error": str(item.get("last_error", "")),
                "last_used_at": str(item.get("last_used_at", "")),
            }
        )
    return merged


def _merge_proxies(value: Any, current_proxies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    current_by_id = {str(proxy.get("id", "")): proxy for proxy in current_proxies if proxy.get("id")}
    merged: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip() or f"Proxy {index}"
        proxy_id = str(item.get("id", "")).strip() or f"proxy-{index}"
        url = str(item.get("url", ""))
        if url == "********":
            url = str(current_by_id.get(proxy_id, {}).get("url", ""))
        merged.append(
            {
                "id": proxy_id,
                "name": name,
                "url": url,
                "enabled": bool(item.get("enabled", True)),
                "status": str(item.get("status", "healthy") or "healthy"),
                "last_error": str(item.get("last_error", "")),
                "last_used_at": str(item.get("last_used_at", "")),
            }
        )
    return merged


def _normalize_tld_schedules(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    schedules: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        tld = str(item.get("tld", "")).strip().lower().lstrip(".")
        if not tld or tld not in SUPPORTED_CRAWL_TLDS:
            continue
        schedules.append(
            {
                "tld": tld,
                "enabled": bool(item.get("enabled", True)),
                "crawl_hour": _int_range(item.get("crawl_hour", 2), 0, 23),
                "crawl_minute": _int_range(item.get("crawl_minute", 0), 0, 59),
                "timezone": str(item.get("timezone", "Asia/Shanghai") or "Asia/Shanghai"),
                "max_pages": max(1, int(item.get("max_pages", 20) or 20)),
                "request_delay_seconds": max(0, _int_value(item.get("request_delay_seconds", 12), 12)),
                "filter_max_length": max(1, _int_value(item.get("filter_max_length", 5), 5)),
                "filter_allow_digits": bool(item.get("filter_allow_digits", False)),
            }
        )
    return schedules


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _int_range(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return min(maximum, max(minimum, number))
