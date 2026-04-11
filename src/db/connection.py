"""
Database connection manager.

Refactored from V1.1 DatabaseManager. Keeps the same explicit,
short-connection design suitable for bastion host environments.
"""

from __future__ import annotations

import sys
from typing import Any

import pymysql
from loguru import logger

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
    MySQL database access class.

    Design: explicit connect/disconnect, no auto-reconnect, no connection pool.
    Each batch operation gets its own short-lived connection.
    """

    def __init__(self, config: ConnectionConfig | None = None, database: str | None = None):
        if config:
            self.host = config.host
            self.port = config.port
            self.user = config.user
            self.password = config.password
            self.database = database or config.database
            self.charset = config.charset
        else:
            # Fallback to env vars for backward compatibility
            import os
            from dotenv import load_dotenv
            load_dotenv(encoding="utf-8-sig")
            self.host = os.getenv("DB_HOST", "localhost")
            self.port = int(os.getenv("DB_PORT", "3306"))
            self.user = os.getenv("DB_USER", "")
            self.password = os.getenv("DB_PASSWORD", "")
            self.database = database or os.getenv("DB_NAME", "")
            self.charset = os.getenv("DB_CHARSET", "utf8mb4")

        self.conn: pymysql.Connection | None = None

    def connect(self) -> bool:
        try:
            self.conn = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset=self.charset,
            )
            logger.success(f"Connected to database: {self.database}")
            return True
        except Exception as exc:
            logger.error(f"Connection failed: {exc}")
            self.conn = None
            return False

    def disconnect(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None
            logger.info("Database connection closed")

    def query(self, sql: str, params: tuple | None = None) -> list[tuple]:
        if self.conn is None:
            raise RuntimeError("Database connection is not established.")
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params or ())
            return list(cursor.fetchall())

    def query_dicts(self, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        if self.conn is None:
            raise RuntimeError("Database connection is not established.")
        with self.conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(sql, params or ())
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def execute(self, sql: str, params: tuple | None = None) -> int:
        if self.conn is None:
            raise RuntimeError("Database connection is not established.")
        try:
            with self.conn.cursor() as cursor:
                affected_rows = cursor.execute(sql, params or ())
            self.conn.commit()
            return int(affected_rows)
        except Exception:
            self.conn.rollback()
            raise

    def executemany(self, sql: str, params_list: list[tuple]) -> int:
        if self.conn is None:
            raise RuntimeError("Database connection is not established.")
        if not params_list:
            return 0
        try:
            with self.conn.cursor() as cursor:
                affected_rows = cursor.executemany(sql, params_list)
            self.conn.commit()
            return int(affected_rows)
        except Exception:
            self.conn.rollback()
            raise

    def to_dict_list(self, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """Execute SQL and return results as a list of dicts (replaces to_dataframe)."""
        return self.query_dicts(sql, params)

    # Schema inspection methods

    def show_tables(self) -> list[str]:
        rows = self.query("SHOW TABLES")
        return [str(row[0]) for row in rows]

    def table_exists(self, table_name: str) -> bool:
        rows = self.query("SHOW TABLES LIKE %s", (table_name,))
        return bool(rows)

    def describe_table(self, table_name: str) -> list[tuple]:
        return self.query(f"DESCRIBE `{table_name}`")

    def get_column_names(self, table_name: str) -> list[str]:
        rows = self.query(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """,
            (self.database, table_name),
        )
        return [str(row[0]) for row in rows]

    def get_column_info(self, table_name: str) -> list[dict[str, Any]]:
        """Get detailed column information from INFORMATION_SCHEMA."""
        rows = self.query_dicts(
            """
            SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, IS_NULLABLE,
                   COLUMN_DEFAULT, COLUMN_KEY, EXTRA, CHARACTER_MAXIMUM_LENGTH,
                   NUMERIC_PRECISION, NUMERIC_SCALE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """,
            (self.database, table_name),
        )
        return rows

    def get_first_column_name(self, table_name: str) -> str | None:
        column_names = self.get_column_names(table_name)
        return column_names[0] if column_names else None

    def get_primary_key_columns(self, table_name: str) -> list[str]:
        rows = self.query(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
              AND CONSTRAINT_NAME = 'PRIMARY'
            ORDER BY ORDINAL_POSITION
            """,
            (self.database, table_name),
        )
        return [str(row[0]) for row in rows]

    def get_unique_key_columns(self, table_name: str) -> list[str]:
        rows = self.query(
            """
            SELECT DISTINCT COLUMN_NAME
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
              AND NON_UNIQUE = 0 AND INDEX_NAME <> 'PRIMARY'
            ORDER BY COLUMN_NAME
            """,
            (self.database, table_name),
        )
        return [str(row[0]) for row in rows]

    def get_json_columns(self, table_name: str) -> list[str]:
        rows = self.query(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
              AND DATA_TYPE = 'json'
            ORDER BY ORDINAL_POSITION
            """,
            (self.database, table_name),
        )
        return [str(row[0]) for row in rows]

    def get_auto_increment_columns(self, table_name: str) -> list[str]:
        rows = self.query(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
              AND EXTRA LIKE '%%auto_increment%%'
            """,
            (self.database, table_name),
        )
        return [str(row[0]) for row in rows]

    def get_max_pk_value(self, table_name: str, column_name: str) -> Any:
        """Get the maximum value of a column (typically PK)."""
        rows = self.query(f"SELECT MAX(`{column_name}`) FROM `{table_name}`")
        if not rows or rows[0][0] is None:
            return None
        return rows[0][0]

    def count_rows(self, table_name: str) -> int:
        rows = self.query(f"SELECT COUNT(*) FROM `{table_name}`")
        return int(rows[0][0])

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
