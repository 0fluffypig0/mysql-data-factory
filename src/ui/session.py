"""
Session manager for persistent database connections.

Holds a single long-lived connection that all GUI pages share.
Designed for bastion host environments where credentials are one-time-use.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from src.config.app_config import ConnectionConfig
from src.db.connection import DatabaseManager
from src.utils.timezone import now_jst_str


class SessionManager(QObject):
    """
    Singleton-style session that holds a persistent DB connection.

    Signals:
        connected(str)      - emitted with display info after successful connect
        disconnected()      - emitted when connection is closed
        connection_lost(str) - emitted when a keep-alive check fails
    """

    connected = Signal(str)       # display_safe info
    disconnected = Signal()
    connection_lost = Signal(str)  # error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: ConnectionConfig | None = None
        self._db: DatabaseManager | None = None
        self._connected_at: str = ""

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
        """
        Establish (or replace) the persistent connection.
        Returns True on success.
        """
        # Close existing if any
        self._close_quietly()

        self._config = config
        db = DatabaseManager(config=config)
        if db.connect():
            self._db = db
            self._connected_at = now_jst_str()
            self.connected.emit(config.display_safe())
            return True
        else:
            self._db = None
            return False

    def disconnect(self) -> None:
        """Explicitly close the connection."""
        self._close_quietly()
        self.disconnected.emit()

    def reconnect(self) -> bool:
        """Reconnect using the same config."""
        if self._config is None:
            return False
        return self.connect(self._config)

    def check_alive(self) -> bool:
        """
        Lightweight keep-alive check.
        Returns True if the connection is still usable.
        """
        if not self.is_connected:
            return False
        try:
            self._db.query("SELECT 1")
            return True
        except Exception as exc:
            self.connection_lost.emit(str(exc))
            return False

    def ensure_connected(self) -> bool:
        """Check alive; if dead, try one reconnect."""
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
