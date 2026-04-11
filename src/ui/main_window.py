"""
Main GUI window with tabbed pages, i18n menu, and shared session.
V3.0: tkinter version — zero external GUI dependencies.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

from src.config.app_config import AppPaths, ConnectionConfig
from src.ui.i18n import t, get_lang, set_lang, load_saved_lang
from src.ui.session import SessionManager
from src.ui.page_connection import ConnectionPage
from src.ui.page_scan import ScanPage
from src.ui.page_tasks import TasksPage
from src.ui.page_preview import PreviewPage
from src.ui.page_execute import ExecutePage
from src.ui.page_history import HistoryPage


class MainWindow:
    """Main application window."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.minsize(1100, 750)

        self.paths = AppPaths()
        self.paths.ensure_all()

        # Shared session
        self.session = SessionManager()
        self.conn_config: ConnectionConfig | None = None
        self.scan_result = None

        self._init_ui()
        self._apply_language()

        # Wire session callbacks
        self.session.on_connected = self._on_session_connected
        self.session.on_disconnected = self._on_session_disconnected
        self.session.on_connection_lost = self._on_session_lost

    def _init_ui(self):
        # ── Menu bar ──
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        self._lang_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t("menu.language"), menu=self._lang_menu)
        self._lang_var = tk.StringVar(value=get_lang())
        for code, label in [("zh_CN", "简体中文"), ("en", "English"), ("ja", "日本語")]:
            self._lang_menu.add_radiobutton(
                label=label, variable=self._lang_var, value=code,
                command=lambda c=code: self._switch_language(c))

        # ── Notebook (tabs) ──
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.page_conn = ConnectionPage(self.notebook, self)
        self.page_scan = ScanPage(self.notebook, self)
        self.page_tasks = TasksPage(self.notebook, self)
        self.page_preview = PreviewPage(self.notebook, self)
        self.page_execute = ExecutePage(self.notebook, self)
        self.page_history = HistoryPage(self.notebook, self)

        self.notebook.add(self.page_conn, text="")
        self.notebook.add(self.page_scan, text="")
        self.notebook.add(self.page_tasks, text="")
        self.notebook.add(self.page_preview, text="")
        self.notebook.add(self.page_execute, text="")
        self.notebook.add(self.page_history, text="")

        # ── Status bar ──
        self._status_var = tk.StringVar(value=t("common.ready"))
        self._status_bar = ttk.Label(self.root, textvariable=self._status_var,
                                     relief=tk.SUNKEN, anchor=tk.W)
        self._status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # ── Wire page callbacks ──
        self.page_conn.on_connection_ready = self._on_connection_ready
        self.page_scan.on_scan_complete = self._on_scan_complete
        self.page_tasks.on_tasks_confirmed = self._on_tasks_confirmed
        self.page_execute.on_execution_complete = self._on_execution_complete

    # ── Language ──

    def _switch_language(self, lang_code: str):
        set_lang(lang_code)
        self._apply_language()
        for page in [self.page_conn, self.page_scan, self.page_tasks,
                      self.page_preview, self.page_execute, self.page_history]:
            if hasattr(page, "retranslate"):
                page.retranslate()

    def _apply_language(self):
        self.root.title(t("window.title"))
        tab_keys = ["tab.connection", "tab.scan", "tab.tasks",
                     "tab.preview", "tab.execute", "tab.history"]
        for i, key in enumerate(tab_keys):
            self.notebook.tab(i, text=t(key))
        self._status_var.set(t("common.ready"))

    # ── Session callbacks ──

    def _on_session_connected(self, info: str):
        self._status_var.set(t("conn.status_active", info=info))

    def _on_session_disconnected(self):
        self._status_var.set(t("conn.status_disconnected"))

    def _on_session_lost(self, err: str):
        self._status_var.set(f"Connection lost: {err}")

    # ── Page callbacks ──

    def _on_connection_ready(self, config: ConnectionConfig):
        self.conn_config = config
        self.page_scan.set_session(self.session)
        self.notebook.select(1)

    def _on_scan_complete(self, scan_result):
        self.scan_result = scan_result
        self._status_var.set(t("scan.complete", n=len(scan_result.tables), time=scan_result.scan_time))
        self.page_tasks.set_scan_result(scan_result, self.conn_config)
        self.notebook.select(2)

    def _on_tasks_confirmed(self, plan):
        self.page_preview.set_plan(plan, self.conn_config, self.scan_result, self.session)
        self.notebook.select(3)

    def _on_execution_complete(self):
        self.page_history.refresh()
        self._status_var.set(t("exec.status_ok"))

    def run(self):
        self.root.mainloop()


def run_gui():
    """Launch the GUI application."""
    load_saved_lang()
    app = MainWindow()
    app.run()
