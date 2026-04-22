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
from urllib.parse import quote_plus

from src.utils.runtime_paths import get_app_root


PROJECT_ROOT = get_app_root()


# Supported database dialects. Adding one here requires (a) SQLAlchemy driver
# available, (b) build_sqlalchemy_url branch, (c) DatabaseManager schema
# inspection verified against its quirks.
SUPPORTED_DIALECTS = ("mysql", "postgresql", "oracle", "sqlite")


# ─────────────────────────────────────────────
# Per-dialect UI metadata
#
# This drives the Connection page dropdown labels and the info panel that
# explains which real engines each dialect choice covers. The GUI reads this
# instead of hard-coding engine lists, so adding/removing a dialect is a
# single-file change.
#
# Schema:
#   label         : short display label for the dropdown (compact, ~30 chars)
#   default_port  : port pre-filled when the user picks this dialect; 0 = N/A
#   needs_network : True → host/port/user/password are enabled
#                   False → SQLite-style file connection, network fields hidden
#   driver        : python driver name — shown to ops/infra engineers
#   engines       : friendly list of real products this dialect maps to
#                   (for the info panel — NOT just for documentation)
#   fast_path     : one-line description of the high-throughput insert path,
#                   or "" if none
#   i18n_hint_key : optional extra hint shown only for this dialect
#                   (e.g. Oracle service_name vs SID, SQLite file path format)
# ─────────────────────────────────────────────
DIALECT_INFO: dict[str, dict[str, Any]] = {
    "mysql": {
        "label": "MySQL / MariaDB / Aurora MySQL",
        "default_port": 3306,
        "needs_network": True,
        "driver": "PyMySQL + cryptography",
        "engines": [
            "MySQL 5.7 / 8.0 / 8.4",
            "MariaDB 10.x / 11.x",
            "Amazon Aurora MySQL",
            "Percona Server",
        ],
        "fast_path": "LOAD DATA LOCAL INFILE (requires server-side local_infile=ON)",
        "i18n_hint_key": "",
    },
    "postgresql": {
        "label": "PostgreSQL / Aurora PG / Timescale",
        "default_port": 5432,
        "needs_network": True,
        "driver": "psycopg2-binary",
        "engines": [
            "PostgreSQL 12 / 13 / 14 / 15 / 16",
            "Amazon Aurora PostgreSQL",
            "Google Cloud SQL for PostgreSQL",
            "TimescaleDB (core subset)",
        ],
        "fast_path": "INSERT path (COPY FROM STDIN not yet implemented for this backend)",
        "i18n_hint_key": "",
    },
    "oracle": {
        "label": "Oracle Database (12c+)",
        "default_port": 1521,
        "needs_network": True,
        "driver": "python-oracledb (thin mode — no Instant Client needed)",
        "engines": [
            "Oracle Database 12c / 19c / 21c / 23ai",
            "Oracle Autonomous Database",
            "Oracle Exadata",
        ],
        "fast_path": "INSERT path (array DML)",
        "i18n_hint_key": "conn.oracle_hint",
    },
    "sqlite": {
        "label": "SQLite (single file)",
        "default_port": 0,
        "needs_network": False,
        "driver": "stdlib sqlite3",
        "engines": [
            "SQLite 3.x file (.db / .sqlite / .sqlite3)",
            "In-memory (:memory:) for ephemeral test runs",
        ],
        "fast_path": "INSERT path (single writer — not for concurrent workloads)",
        "i18n_hint_key": "conn.sqlite_hint",
    },
}


def get_dialect_label(dialect: str) -> str:
    """Human-friendly dropdown label for a dialect, with fallback to the id."""
    info = DIALECT_INFO.get((dialect or "").lower())
    return info["label"] if info else dialect


def resolve_dialect_from_label(label: str) -> str:
    """Reverse of get_dialect_label — match a dropdown label back to dialect id."""
    for k, v in DIALECT_INFO.items():
        if v["label"] == label:
            return k
    return (label or "mysql").lower()


@dataclass
class ConnectionConfig:
    """Database connection parameters (multi-dialect)."""

    # "mysql" uses pymysql driver; "sqlite" uses the stdlib sqlite3 module.
    dialect: str = "mysql"
    host: str = "localhost"
    port: int = 3306
    user: str = ""
    password: str = ""
    # For sqlite, `database` is a file path (absolute, or relative to project root).
    # For `:memory:` SQLite, pass the literal string ":memory:".
    database: str = ""
    charset: str = "utf8mb4"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConnectionConfig:
        return cls(
            dialect=str(data.get("dialect", "mysql")).lower(),
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
            dialect=os.getenv("DB_DIALECT", "mysql").lower(),
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", ""),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", ""),
            charset=os.getenv("DB_CHARSET", "utf8mb4"),
        )

    def build_sqlalchemy_url(self) -> str:
        """
        Build the SQLAlchemy connection URL for this config.

        Per-dialect notes:
        - MySQL: always request ``local_infile=1`` so LOAD DATA LOCAL INFILE
          can opportunistically work when the server allows it.
        - PostgreSQL: plain psycopg2 URL; default UTF-8 client encoding.
        - Oracle: python-oracledb in "thin" mode — pure Python, no Instant
          Client install required on the bastion host. The ``database`` field
          is passed through as the service name (the modern Oracle
          convention, also accepted by Easy Connect).
        - SQLite: relative paths resolved against PROJECT_ROOT so the app
          behaves the same whether launched via script, exe, or IDE.
        """
        d = (self.dialect or "mysql").lower()
        if d == "mysql":
            # SQLAlchemy url-quoting rules: only user/password need escaping.
            user_q = quote_plus(self.user or "")
            pass_q = quote_plus(self.password or "")
            auth = f"{user_q}:{pass_q}@" if user_q or pass_q else ""
            host_port = f"{self.host}:{self.port}"
            db = self.database or ""
            charset = self.charset or "utf8mb4"
            return (
                f"mysql+pymysql://{auth}{host_port}/{db}"
                f"?charset={charset}&local_infile=1"
            )
        if d == "postgresql":
            # psycopg2-binary. No extra flags — default UTF-8 encoding is
            # what this tool round-trips through everywhere else.
            user_q = quote_plus(self.user or "")
            pass_q = quote_plus(self.password or "")
            auth = f"{user_q}:{pass_q}@" if user_q or pass_q else ""
            host_port = f"{self.host}:{self.port}"
            db = self.database or ""
            return f"postgresql+psycopg2://{auth}{host_port}/{db}"
        if d == "oracle":
            # Thin-mode oracledb. service_name is the modern Oracle convention
            # and also works for Easy Connect strings. URL-encode it so rare
            # punctuation in service names doesn't break the URL parser.
            user_q = quote_plus(self.user or "")
            pass_q = quote_plus(self.password or "")
            auth = f"{user_q}:{pass_q}@" if user_q or pass_q else ""
            host_port = f"{self.host}:{self.port}"
            svc = quote_plus(self.database or "")
            return f"oracle+oracledb://{auth}{host_port}/?service_name={svc}"
        if d == "sqlite":
            db = (self.database or "").strip()
            if not db:
                return "sqlite:///:memory:"
            if db == ":memory:":
                return "sqlite:///:memory:"
            p = Path(db)
            if not p.is_absolute():
                p = PROJECT_ROOT / p
            # SQLAlchemy wants forward slashes even on Windows.
            return "sqlite:///" + str(p).replace("\\", "/")
        raise ValueError(
            f"Unsupported dialect: {d!r}. "
            f"Supported dialects: {', '.join(SUPPORTED_DIALECTS)}"
        )

    def display_safe(self) -> str:
        d = (self.dialect or "mysql").lower()
        if d == "sqlite":
            return f"sqlite://{self.database or ':memory:'}"
        if d == "oracle":
            # For Oracle the "database" field is a service name, not a path —
            # show it explicitly so nobody interprets it as a filesystem DB.
            return (
                f"oracle://{self.user}@{self.host}:{self.port}"
                f"/?service_name={self.database}"
            )
        return f"{d}://{self.user}@{self.host}:{self.port}/{self.database}"

    def is_sqlite(self) -> bool:
        return (self.dialect or "mysql").lower() == "sqlite"

    def is_mysql(self) -> bool:
        return (self.dialect or "mysql").lower() == "mysql"

    def quote_identifier(self, name: str) -> str:
        """
        Dialect-correct identifier quoting for pre-connection SQL construction.

        Call sites that build SQL strings before opening a DatabaseManager
        (e.g. batch_runner building an INSERT template) use this instead of
        hard-coding MySQL backticks.

        MySQL → `name`, SQLite / generic → "name".
        For safety we also escape any embedded quote character.
        """
        if self.is_mysql():
            escaped = name.replace("`", "``")
            return f"`{escaped}`"
        escaped = name.replace('"', '""')
        return f'"{escaped}"'


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
