from __future__ import annotations

from dataclasses import asdict, fields
from typing import Any

from config import RUNTIME_SETTING_KEYS, get_settings, save_runtime_settings
from database import Database
from domain_hunter.types import AppConfig


SECRET_KEYS = {"smtp_password", "czds_bearer_token"}


class ConfigService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get_config(self) -> AppConfig:
        settings = get_settings()
        defaults = AppConfig(
            app_env=settings.app_env,
            database_url=str(settings.database_url),
            data_dir=str(settings.data_dir),
            cache_dir=str(settings.cache_dir),
        )
        stored = await self.db.get_settings()
        data = asdict(defaults)
        data.update({key: value for key, value in stored.items() if key in data})
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
            if key in SECRET_KEYS and (value is None or value == "" or value == "********"):
                continue
            coerced = _coerce_value(key, value, current_data[key])
            if key in RUNTIME_SETTING_KEYS:
                runtime_updates[key] = str(coerced)
            else:
                updates[key] = coerced

        if runtime_updates:
            save_runtime_settings(runtime_updates)
        if updates:
            await self.db.set_settings(updates, secret_keys=SECRET_KEYS)
        return await self.get_config()


def _coerce_value(key: str, value: Any, current_value: Any) -> Any:
    if isinstance(current_value, bool):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current_value, int):
        return int(value)
    return "" if value is None else str(value)
