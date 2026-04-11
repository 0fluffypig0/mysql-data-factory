"""
Session manager for persistent database connections.

Holds a single long-lived connection that all GUI pages share.
Designed for bastion host environments where credentials are one-time-use.

V3.0: Pure Python (no Qt dependency).
"""

from __future__ import annotations

from typing import Callable

from src.config.app_config import ConnectionConfig
from src.db.connection import DatabaseManager
from src.utils.timezone import now_jst_str


class SessionManager:
    """
    Singleton-style session that holds a persistent DB connection.

    Callbacks:
        on_connected(str)       - called with display info after successful connect
        on_disconnected()       - called when connection is closed
        on_connection_lost(str) - called when a keep-alive check fails
    """

    def __init__(self):
        self._config: ConnectionConfig | None = None
        self._db: DatabaseManager | None = None
        self._connected_at: str = ""

        # Callbacks (set by main window)
        self.on_connected: Callable[[str], None] | None = None
        self.on_disconnected: Callable[[], None] | None = None
        self.on_connection_lost: Callable[[str], None] | None = None

    # ── Properties ──

    @property
    def config(self) -> ConnectionConfig | None:
        return self._config

    @property
    def db(self) -> DatabaseManager | None:
        return self._db

    @property
    def is_connected(self) -> bool:
        return self._db is not None and self._db.conn is not None

    @property
    def connected_at(self) -> str:
        return self._connected_at

    @property
    def status_text(self) -> str:
        if not self.is_connected:
            return ""
        return self._config.display_safe() if self._config else ""

    # ── Actions ──

    def connect(self, config: ConnectionConfig) -> bool:
        self._close_quietly()
        self._config = config
        db = DatabaseManager(config=config)
        if db.connect():
            self._db = db
            self._connected_at = now_jst_str()
            if self.on_connected:
                self.on_connected(config.display_safe())
            return True
        else:
            self._db = None
            return False

    def disconnect(self) -> None:
        self._close_quietly()
        if self.on_disconnected:
            self.on_disconnected()

    def reconnect(self) -> bool:
        if self._config is None:
            return False
        return self.connect(self._config)

    def check_alive(self) -> bool:
        if not self.is_connected:
            return False
        try:
            self._db.query("SELECT 1")
            return True
        except Exception as exc:
            if self.on_connection_lost:
                self.on_connection_lost(str(exc))
            return False

    def ensure_connected(self) -> bool:
        if self.check_alive():
            return True
        if self._config:
            return self.reconnect()
        return False

    # ── Internal ──

    def _close_quietly(self) -> None:
        if self._db is not None:
            try:
                self._db.disconnect()
            except Exception:
                pass
            self._db = None
        self._connected_at = ""
