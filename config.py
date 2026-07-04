from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from dotenv import load_dotenv
import os


load_dotenv()


RUNTIME_SETTINGS_PATH = Path("runtime/app_settings.json")
RUNTIME_SETTING_KEYS = {"data_dir", "cache_dir", "database_url"}
DEFAULT_RUNTIME_SETTINGS = {
    "app_env": "local",
    "data_dir": "runtime/data",
    "cache_dir": "runtime/cache",
    "database_url": "runtime/database/domain_hunter.sqlite3",
}


@dataclass(frozen=True)
class Settings:
    app_env: str
    data_dir: Path
    cache_dir: Path
    database_url: Path

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.database_url.parent.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    values = load_runtime_settings()

    return Settings(
        app_env=values["app_env"],
        data_dir=Path(values["data_dir"]),
        cache_dir=Path(values["cache_dir"]),
        database_url=Path(values["database_url"]),
    )


def load_runtime_settings() -> dict[str, str]:
    values = DEFAULT_RUNTIME_SETTINGS.copy()
    if RUNTIME_SETTINGS_PATH.exists():
        raw = json.loads(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
        values.update({key: str(value) for key, value in raw.items() if key in RUNTIME_SETTING_KEYS})
    return values


def save_runtime_settings(updates: dict[str, str]) -> None:
    current = load_runtime_settings()
    current.update({key: value for key, value in updates.items() if key in RUNTIME_SETTING_KEYS})
    RUNTIME_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_SETTINGS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
