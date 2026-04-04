"""
Main GUI window with tabbed pages, i18n menu, and shared session.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QStatusBar, QMenuBar, QMenu,
)
from PySide6.QtGui import QAction, QActionGroup

from src.config.app_config import AppPaths, ConnectionConfig
from src.ui.i18n import t, get_lang, set_lang, load_saved_lang
from src.ui.session import SessionManager
from src.ui.page_connection import ConnectionPage
from src.ui.page_scan import ScanPage
from src.ui.page_tasks import TasksPage
from src.ui.page_preview import PreviewPage
from src.ui.page_execute import ExecutePage
from src.ui.page_history import HistoryPage


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(1100, 750)

        self.paths = AppPaths()
        self.paths.ensure_all()

        # Shared session (persistent connection)
        self.session = SessionManager(self)
        self.conn_config: ConnectionConfig | None = None
        self.scan_result = None

        self._init_ui()
        self._apply_language()

    # ── UI setup ──

    def _init_ui(self):
        # Menu bar with language switcher
        self._build_menu()

        # Tabs
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.page_conn = ConnectionPage(self)
        self.page_scan = ScanPage(self)
        self.page_tasks = TasksPage(self)
        self.page_preview = PreviewPage(self)
        self.page_execute = ExecutePage(self)
        self.page_history = HistoryPage(self)

        self.tabs.addTab(self.page_conn, "")
        self.tabs.addTab(self.page_scan, "")
        self.tabs.addTab(self.page_tasks, "")
        self.tabs.addTab(self.page_preview, "")
        self.tabs.addTab(self.page_execute, "")
        self.tabs.addTab(self.page_history, "")

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Signals
        self.page_conn.connection_ready.connect(self._on_connection_ready)
        self.page_scan.scan_complete.connect(self._on_scan_complete)
        self.page_tasks.tasks_confirmed.connect(self._on_tasks_confirmed)
        self.page_execute.execution_complete.connect(self._on_execution_complete)

        self.session.connected.connect(self._on_session_connected)
        self.session.disconnected.connect(self._on_session_disconnected)
        self.session.connection_lost.connect(self._on_session_lost)

    def _build_menu(self):
        menu_bar = self.menuBar()
        lang_menu = menu_bar.addMenu(t("menu.language"))

        group = QActionGroup(self)
        group.setExclusive(True)

        current = get_lang()
        for code, label_key in [("zh_CN", "menu.lang_zh"), ("en", "menu.lang_en"), ("ja", "menu.lang_ja")]:
            action = QAction(t(label_key), self, checkable=True)
            action.setChecked(code == current)
            action.triggered.connect(lambda checked, c=code: self._switch_language(c))
            group.addAction(action)
            lang_menu.addAction(action)

        self._lang_menu = lang_menu
        self._lang_group = group

    # ── Language ──

    def _switch_language(self, lang_code: str):
        set_lang(lang_code)
        self._apply_language()
        # Notify all pages
        for page in [self.page_conn, self.page_scan, self.page_tasks,
                      self.page_preview, self.page_execute, self.page_history]:
            if hasattr(page, "retranslate"):
                page.retranslate()

    def _apply_language(self):
        self.setWindowTitle(t("window.title"))
        tab_keys = ["tab.connection", "tab.scan", "tab.tasks",
                     "tab.preview", "tab.execute", "tab.history"]
        for i, key in enumerate(tab_keys):
            self.tabs.setTabText(i, t(key))
        self.status_bar.showMessage(t("common.ready"))
        # Re-build menu text
        self._lang_menu.setTitle(t("menu.language"))
        for action in self._lang_group.actions():
            for code, lk in [("zh_CN", "menu.lang_zh"), ("en", "menu.lang_en"), ("ja", "menu.lang_ja")]:
                if action.isChecked() or t(lk) == action.text() or action.text() in ("简体中文", "English", "日本語", "簡体中国語"):
                    pass  # Labels are language-independent; keep as-is
            # Language names are always shown in their own script, no need to translate

    # ── Session signals ──

    def _on_session_connected(self, info: str):
        self.status_bar.showMessage(t("conn.status_active", info=info))

    def _on_session_disconnected(self):
        self.status_bar.showMessage(t("conn.status_disconnected"))

    def _on_session_lost(self, err: str):
        self.status_bar.showMessage(f"Connection lost: {err}")

    # ── Page signals ──

    def _on_connection_ready(self, config: ConnectionConfig):
        self.conn_config = config
        self.page_scan.set_session(self.session)
        self.tabs.setCurrentIndex(1)

    def _on_scan_complete(self, scan_result):
        self.scan_result = scan_result
        self.status_bar.showMessage(t("scan.complete", n=len(scan_result.tables), time=scan_result.scan_time))
        self.page_tasks.set_scan_result(scan_result, self.conn_config)
        self.tabs.setCurrentIndex(2)

    def _on_tasks_confirmed(self, plan):
        self.page_preview.set_plan(plan, self.conn_config, self.scan_result, self.session)
        self.tabs.setCurrentIndex(3)

    def _on_execution_complete(self):
        self.page_history.refresh()
        self.status_bar.showMessage(t("exec.status_ok"))


def run_gui():
    """Launch the GUI application."""
    load_saved_lang()
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
