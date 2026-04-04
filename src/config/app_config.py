"""
Application configuration management.

Handles .env file loading, connection profiles, and application-wide settings.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class ConnectionConfig:
    """Database connection parameters."""

    host: str = "localhost"
    port: int = 3306
    user: str = ""
    password: str = ""
    database: str = ""
    charset: str = "utf8mb4"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConnectionConfig:
        return cls(
            host=str(data.get("host", "localhost")),
            port=int(data.get("port", 3306)),
            user=str(data.get("user", "")),
            password=str(data.get("password", "")),
            database=str(data.get("database", "")),
            charset=str(data.get("charset", "utf8mb4")),
        )

    @classmethod
    def from_env(cls) -> ConnectionConfig:
        return cls(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", ""),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", ""),
            charset=os.getenv("DB_CHARSET", "utf8mb4"),
        )

    def display_safe(self) -> str:
        return f"{self.user}@{self.host}:{self.port}/{self.database}"


@dataclass
class AppPaths:
    """Standard directory paths for the application."""

    root: Path = field(default_factory=lambda: PROJECT_ROOT)

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def preview_dir(self) -> Path:
        return self.root / "data" / "preview"

    @property
    def export_dir(self) -> Path:
        return self.root / "data" / "export"

    @property
    def output_dir(self) -> Path:
        return self.root / "data" / "output"

    @property
    def metadata_cache_dir(self) -> Path:
        return self.root / "metadata_cache"

    @property
    def plans_dir(self) -> Path:
        return self.root / "plans"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def cleanup_sql_dir(self) -> Path:
        return self.root / "sql" / "cleanup"

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    def ensure_all(self) -> None:
        for d in [
            self.data_dir, self.preview_dir, self.export_dir,
            self.output_dir, self.metadata_cache_dir, self.plans_dir,
            self.reports_dir, self.cleanup_sql_dir, self.config_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)


# Connection profiles saved on disk

PROFILES_FILE = PROJECT_ROOT / "config" / "connection_profiles.json"


def load_connection_profiles() -> dict[str, ConnectionConfig]:
    """Load saved connection profiles from JSON."""
    if not PROFILES_FILE.exists():
        return {}
    with PROFILES_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return {name: ConnectionConfig.from_dict(cfg) for name, cfg in data.items()}


def save_connection_profiles(profiles: dict[str, ConnectionConfig]) -> None:
    """Save connection profiles to JSON."""
    PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {name: cfg.to_dict() for name, cfg in profiles.items()}
    with PROFILES_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_dotenv_file(env_file: str = ".env") -> None:
    """Load a .env file with override, tolerating missing python-dotenv."""
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        return

    env_path = Path(env_file)
    if not env_path.is_absolute():
        env_path = PROJECT_ROOT / env_path

    load_dotenv(env_path, override=True, encoding="utf-8-sig")
