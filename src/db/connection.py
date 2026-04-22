"""
Database connection manager (multi-dialect, SQLAlchemy-backed).

Supported dialects (see src.config.app_config.SUPPORTED_DIALECTS):
- mysql      — PyMySQL driver; covers MySQL 5.7/8.x, MariaDB 10/11,
               Aurora MySQL, Percona Server.
- postgresql — psycopg2-binary driver; covers PG 12–16, Aurora PG,
               Cloud SQL for Postgres, TimescaleDB core.
- oracle     — python-oracledb in *thin* mode (no Instant Client
               needed on the bastion host); covers 12c / 19c / 21c /
               23ai, Autonomous DB, Exadata.
- sqlite     — stdlib sqlite3; single-file or :memory:.

The public API is unchanged from the pymysql-only v3.0.x implementation —
callers such as batch_runner, row_builder, cleanup_runner, and scripts
continue to work without modification.

Design:
- One SQLAlchemy Engine per DatabaseManager instance
- NullPool: we keep the "explicit connect / disconnect, one connection per
  batch operation" semantics that suit bastion-host single-credential flows
- Dialect-aware schema inspection via sqlalchemy.inspect
- Dialect-aware identifier quoting via engine.dialect.identifier_preparer
"""

from __future__ import annotations

import os
import sys
from fnmatch import fnmatch
from typing import Any

from loguru import logger
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from src.config.app_config import ConnectionConfig


# Logger setup - keep console only for bastion host transparency
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>",
)


class DatabaseManager:
    """
    Multi-dialect database access class.

    Design: explicit connect/disconnect, no connection pool (NullPool).
    Each batch operation gets its own short-lived connection.
    """

    def __init__(self, config: ConnectionConfig | None = None, database: str | None = None):
        if config:
            self._config = config
            self.dialect = (config.dialect or "mysql").lower()
            self.host = config.host
            self.port = config.port
            self.user = config.user
            self.password = config.password
            self.database = database or config.database
            self.charset = config.charset
            # If caller overrode database, build an override config
            if database and database != config.database:
                self._config = ConnectionConfig.from_dict({**config.to_dict(), "database": database})
        else:
            # Fallback to env vars for backward compatibility.
            from dotenv import load_dotenv

            load_dotenv(encoding="utf-8-sig")
            self.dialect = os.getenv("DB_DIALECT", "mysql").lower()
            self.host = os.getenv("DB_HOST", "localhost")
            self.port = int(os.getenv("DB_PORT", "3306"))
            self.user = os.getenv("DB_USER", "")
            self.password = os.getenv("DB_PASSWORD", "")
            self.database = database or os.getenv("DB_NAME", "")
            self.charset = os.getenv("DB_CHARSET", "utf8mb4")
            self._config = ConnectionConfig(
                dialect=self.dialect, host=self.host, port=self.port,
                user=self.user, password=self.password,
                database=self.database, charset=self.charset,
            )

        self.engine: Engine | None = None
        self.conn = None  # sqlalchemy.engine.Connection; keeps attribute name for BC

    # ── Connection lifecycle ──

    def connect(self) -> bool:
        try:
            url = self._config.build_sqlalchemy_url()
            # NullPool keeps the "one-connection-per-op" semantics of the old
            # pymysql flow. future=True uses 2.0-style Connection API.
            self.engine = create_engine(url, poolclass=NullPool, future=True)
            self.conn = self.engine.connect()
            # Probe to confirm
            self.conn.execute(text("SELECT 1"))
            logger.success(f"Connected to {self._config.display_safe()}")
            return True
        except Exception as exc:
            logger.error(f"Connection failed: {exc}")
            self._close_quietly()
            return False

    def _close_quietly(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
        if self.engine is not None:
            try:
                self.engine.dispose()
            except Exception:
                pass
            self.engine = None

    def disconnect(self) -> None:
        if self.conn is not None or self.engine is not None:
            self._close_quietly()
            logger.info("Database connection closed")

    # ── Public dialect helpers ──

    @property
    def dialect_name(self) -> str:
        """Canonical dialect name: 'mysql', 'postgresql', 'oracle', or 'sqlite'."""
        if self.engine is not None:
            return self.engine.dialect.name
        return (self.dialect or "mysql").lower()

    def is_mysql(self) -> bool:
        return self.dialect_name == "mysql"

    def is_sqlite(self) -> bool:
        return self.dialect_name == "sqlite"

    def quote_identifier(self, name: str) -> str:
        """
        Produce a dialect-correct quoted identifier.

        MySQL → `name`, SQLite → "name", PostgreSQL → "name".
        Used by callers that build raw SQL strings (batch insert, cleanup, etc).
        """
        if self.engine is not None:
            return self.engine.dialect.identifier_preparer.quote(name)
        # Fallback when called before connect(): guess by configured dialect.
        if self.is_mysql():
            return f"`{name}`"
        return f'"{name}"'

    # ── Query helpers (public API — unchanged signatures) ──

    def _ensure_conn(self) -> None:
        if self.conn is None:
            raise RuntimeError(
                "Database connection is not established. "
                "Call DatabaseManager.connect() first, or check that "
                ".env has valid DB_DIALECT / DB_HOST / DB_USER / DB_PASSWORD / DB_NAME."
            )

    def query(self, sql: str, params: tuple | None = None) -> list[tuple]:
        """Run SELECT and return rows as tuples."""
        self._ensure_conn()
        stmt, bind = _prepare_stmt(sql, params)
        result = self.conn.execute(stmt, bind)
        return [tuple(row) for row in result]

    def query_dicts(self, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """Run SELECT and return rows as dicts keyed by column name."""
        self._ensure_conn()
        stmt, bind = _prepare_stmt(sql, params)
        result = self.conn.execute(stmt, bind)
        return [dict(row._mapping) for row in result]

    def execute(self, sql: str, params: tuple | None = None) -> int:
        """Run a DML statement; returns rowcount. Commits on success."""
        self._ensure_conn()
        stmt, bind = _prepare_stmt(sql, params)
        try:
            result = self.conn.execute(stmt, bind)
            self.conn.commit()
            return int(result.rowcount or 0)
        except Exception:
            self.conn.rollback()
            raise

    def executemany(self, sql: str, params_list: list[tuple]) -> int:
        """Run a DML statement over many rows; returns total rowcount."""
        self._ensure_conn()
        if not params_list:
            return 0
        stmt, binds = _prepare_many(sql, params_list)
        try:
            result = self.conn.execute(stmt, binds)
            self.conn.commit()
            # SQLAlchemy reports -1 for multi-row DML on some drivers; fall back
            # to the caller-supplied count in that case.
            rc = result.rowcount
            return int(rc) if rc is not None and rc >= 0 else len(params_list)
        except Exception:
            self.conn.rollback()
            raise

    def to_dict_list(self, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """Alias for query_dicts (kept for backward compatibility)."""
        return self.query_dicts(sql, params)

    # ── Schema inspection (dialect-aware) ──

    def _inspector(self):
        """
        Return an Inspector bound to the open connection (not the engine).

        Reflecting on the engine would open a fresh connection from the pool,
        which for SQLite ':memory:' is a brand-new database — tables created
        by callers via this.conn wouldn't be visible. Inspecting the live
        connection fixes that and costs nothing on MySQL/Postgres.
        """
        self._ensure_conn()
        return inspect(self.conn)

    def show_tables(self) -> list[str]:
        """List all user tables in the current database/schema."""
        insp = self._inspector()
        return sorted(insp.get_table_names())

    def table_exists(self, table_name: str) -> bool:
        insp = self._inspector()
        return insp.has_table(table_name)

    def describe_table(self, table_name: str) -> list[tuple]:
        """
        Return a MySQL-DESCRIBE-like list of tuples:
          (field, type, null, key, default, extra)
        Works for any supported dialect via SQLAlchemy reflection.
        """
        insp = self._inspector()
        cols = insp.get_columns(table_name)
        try:
            pk = set(insp.get_pk_constraint(table_name).get("constrained_columns", []) or [])
        except Exception:
            pk = set()
        try:
            uniques = {
                c for uc in (insp.get_unique_constraints(table_name) or [])
                for c in (uc.get("column_names") or [])
            }
            for idx in (insp.get_indexes(table_name) or []):
                if idx.get("unique"):
                    for c in (idx.get("column_names") or []):
                        if c:
                            uniques.add(c)
        except Exception:
            uniques = set()

        rows: list[tuple] = []
        for c in cols:
            name = c["name"]
            dtype = str(c.get("type") or "").lower()
            nullable = "YES" if c.get("nullable", True) else "NO"
            key = "PRI" if name in pk else ("UNI" if name in uniques else "")
            default = c.get("default")
            extra = "auto_increment" if c.get("autoincrement") else ""
            rows.append((name, dtype, nullable, key, default, extra))
        return rows

    def get_column_names(self, table_name: str) -> list[str]:
        """Ordered column list matching INSERT / LOAD DATA column order."""
        insp = self._inspector()
        return [c["name"] for c in insp.get_columns(table_name)]

    def get_column_info(self, table_name: str) -> list[dict[str, Any]]:
        """Detailed column info, normalized across dialects."""
        insp = self._inspector()
        cols = insp.get_columns(table_name)
        try:
            pk = set(insp.get_pk_constraint(table_name).get("constrained_columns", []) or [])
        except Exception:
            pk = set()

        out: list[dict[str, Any]] = []
        for c in cols:
            t = c.get("type")
            type_str = str(t) if t is not None else ""
            name = c["name"]
            # Best-effort field extraction; reflection dialects may or may not
            # populate every field. None is OK downstream.
            out.append({
                "COLUMN_NAME": name,
                "DATA_TYPE": type_str.split("(")[0].lower(),
                "COLUMN_TYPE": type_str.lower(),
                "IS_NULLABLE": "YES" if c.get("nullable", True) else "NO",
                "COLUMN_DEFAULT": c.get("default"),
                "COLUMN_KEY": "PRI" if name in pk else "",
                "EXTRA": "auto_increment" if c.get("autoincrement") else "",
                "CHARACTER_MAXIMUM_LENGTH": getattr(t, "length", None),
                "NUMERIC_PRECISION": getattr(t, "precision", None),
                "NUMERIC_SCALE": getattr(t, "scale", None),
            })
        return out

    def get_first_column_name(self, table_name: str) -> str | None:
        names = self.get_column_names(table_name)
        return names[0] if names else None

    def get_primary_key_columns(self, table_name: str) -> list[str]:
        insp = self._inspector()
        try:
            return list(insp.get_pk_constraint(table_name).get("constrained_columns", []) or [])
        except Exception:
            return []

    def get_unique_key_columns(self, table_name: str) -> list[str]:
        """Non-PK unique-key columns; distinct and sorted."""
        insp = self._inspector()
        names: set[str] = set()
        try:
            pk = set(insp.get_pk_constraint(table_name).get("constrained_columns", []) or [])
        except Exception:
            pk = set()
        try:
            for uc in (insp.get_unique_constraints(table_name) or []):
                for c in (uc.get("column_names") or []):
                    if c and c not in pk:
                        names.add(c)
        except Exception:
            pass
        try:
            for idx in (insp.get_indexes(table_name) or []):
                if idx.get("unique") and idx.get("name") != "PRIMARY":
                    for c in (idx.get("column_names") or []):
                        if c and c not in pk:
                            names.add(c)
        except Exception:
            pass
        return sorted(names)

    def get_json_columns(self, table_name: str) -> list[str]:
        """
        Columns declared as JSON type.

        SQLite has no native JSON type; the TEXT-with-JSON1 convention isn't
        reliably detectable via reflection, so SQLite returns []. Callers
        handle JSON serialization per-row.
        """
        if self.is_sqlite():
            return []
        insp = self._inspector()
        out: list[str] = []
        for c in insp.get_columns(table_name):
            t = str(c.get("type") or "").upper()
            if "JSON" in t:
                out.append(c["name"])
        return out

    def get_auto_increment_columns(self, table_name: str) -> list[str]:
        """Auto-increment columns (MySQL AUTO_INCREMENT, SQLite INTEGER PRIMARY KEY)."""
        insp = self._inspector()
        out: list[str] = []
        for c in insp.get_columns(table_name):
            if c.get("autoincrement"):
                out.append(c["name"])
        # SQLite reflection doesn't always mark INTEGER PRIMARY KEY as
        # autoincrement. Check the PK constraint with an INTEGER-typed single-
        # column PK as a heuristic.
        if self.is_sqlite() and not out:
            try:
                pk_cols = list(insp.get_pk_constraint(table_name).get("constrained_columns", []) or [])
                if len(pk_cols) == 1:
                    for c in insp.get_columns(table_name):
                        if c["name"] == pk_cols[0]:
                            if "INT" in str(c.get("type") or "").upper():
                                out.append(pk_cols[0])
                            break
            except Exception:
                pass
        return out

    def get_max_pk_value(self, table_name: str, column_name: str) -> Any:
        """Get the maximum value of a column (typically PK)."""
        q = self.quote_identifier
        rows = self.query(f"SELECT MAX({q(column_name)}) FROM {q(table_name)}")
        if not rows or rows[0][0] is None:
            return None
        return rows[0][0]

    def count_rows(self, table_name: str) -> int:
        q = self.quote_identifier
        rows = self.query(f"SELECT COUNT(*) FROM {q(table_name)}")
        return int(rows[0][0])

    def check_local_infile(self) -> bool:
        """
        True when server-side LOAD DATA LOCAL INFILE fast path is usable.

        Only meaningful for MySQL. Always False for SQLite (no such concept)
        and for non-MySQL dialects so the fast path cleanly falls back.
        """
        if not self.is_mysql() or self.conn is None:
            return False
        try:
            rows = self.query("SHOW VARIABLES LIKE 'local_infile'")
            if rows:
                return str(rows[0][1]).upper() == "ON"
        except Exception as exc:
            logger.warning(f"Could not check local_infile variable: {exc}")
        return False

    # ── Context manager ──

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


# ── SQL string → SQLAlchemy text() adapter ──
#
# The legacy API accepted raw SQL with %s / ? placeholders and a tuple of
# params. SQLAlchemy uses :name placeholders and a dict. We translate one to
# the other at the boundary so call sites don't have to change.

def _prepare_stmt(sql: str, params: tuple | None):
    """
    Convert a raw SQL string + positional params tuple into a SQLAlchemy
    text() statement + bind-param dict.

    Accepts MySQL-style `%s` and generic `?`. Literal `%%` is preserved.
    """
    params = params or ()
    if not params:
        return text(sql), {}
    new_sql, bind = _substitute_placeholders(sql, params)
    return text(new_sql), bind


def _prepare_many(sql: str, params_list: list[tuple]):
    """
    Like _prepare_stmt but for executemany — returns a list of bind dicts.

    All rows must have the same placeholder count.
    """
    if not params_list:
        return text(sql), []
    # Use first row to build the placeholder-renamed SQL
    new_sql, first_bind = _substitute_placeholders(sql, params_list[0])
    keys = list(first_bind.keys())
    all_binds: list[dict[str, Any]] = [first_bind]
    for row in params_list[1:]:
        if len(row) != len(keys):
            raise ValueError(
                f"executemany: row has {len(row)} params but SQL expects {len(keys)}"
            )
        all_binds.append({k: v for k, v in zip(keys, row)})
    return text(new_sql), all_binds


def _substitute_placeholders(sql: str, params: tuple) -> tuple[str, dict[str, Any]]:
    """
    Replace %s / ? placeholders with :p0, :p1, ... and return the bind dict.
    """
    out: list[str] = []
    i = 0
    n = len(sql)
    param_idx = 0
    binds: dict[str, Any] = {}
    while i < n:
        ch = sql[i]
        # Escape sequence %% — emit single % and skip both chars
        if ch == "%" and i + 1 < n and sql[i + 1] == "%":
            out.append("%")
            i += 2
            continue
        # MySQL-style %s placeholder
        if ch == "%" and i + 1 < n and sql[i + 1] == "s":
            if param_idx >= len(params):
                raise ValueError(
                    f"SQL has more placeholders than params ({len(params)})"
                )
            key = f"p{param_idx}"
            out.append(f":{key}")
            binds[key] = params[param_idx]
            param_idx += 1
            i += 2
            continue
        # Generic ? placeholder
        if ch == "?":
            if param_idx >= len(params):
                raise ValueError(
                    f"SQL has more placeholders than params ({len(params)})"
                )
            key = f"p{param_idx}"
            out.append(f":{key}")
            binds[key] = params[param_idx]
            param_idx += 1
            i += 1
            continue
        out.append(ch)
        i += 1

    if param_idx < len(params):
        raise ValueError(
            f"SQL has {param_idx} placeholders but {len(params)} params provided"
        )

    return "".join(out), binds
