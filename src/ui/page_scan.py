"""
Page 2: Database Scan — uses shared session, JST timestamps, i18n.
V3.0: tkinter version.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox

from src.config.app_config import AppPaths
from src.metadata.models import DatabaseScanResult
from src.metadata.scanner import scan_database, save_scan_result, load_scan_result, list_cached_databases
from src.ui.i18n import t
from src.ui.session import SessionManager
from src.utils.timezone import now_jst_str


class ScanPage(ttk.Frame):
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self._session: SessionManager | None = None
        self.scan_result: DatabaseScanResult | None = None
        self.on_scan_complete = None  # callback(scan_result)
        self._init_ui()

    def set_session(self, session: SessionManager):
        self._session = session
        self._btn_scan.config(state=tk.NORMAL)

    def _init_ui(self):
        ctrl = ttk.Frame(self)
        ctrl.pack(fill=tk.X, padx=10, pady=5)

        self._btn_scan = ttk.Button(ctrl, text=t("scan.btn_scan"), command=self._start_scan, state=tk.DISABLED)
        self._btn_scan.pack(side=tk.LEFT, padx=3)
        self._btn_load_cache = ttk.Button(ctrl, text=t("scan.btn_load_cache"), command=self._load_cached)
        self._btn_load_cache.pack(side=tk.LEFT, padx=3)
        self._btn_use = ttk.Button(ctrl, text=t("scan.btn_use"), command=self._use_result, state=tk.DISABLED)
        self._btn_use.pack(side=tk.LEFT, padx=3)

        self._progress_var = tk.DoubleVar()
        self._progress_bar = ttk.Progressbar(self, variable=self._progress_var, maximum=100)
        self._progress_bar.pack(fill=tk.X, padx=10, pady=2)

        self._lbl_progress = ttk.Label(self, text="")
        self._lbl_progress.pack(fill=tk.X, padx=10)

        # Treeview for scan results
        columns = ("table", "rows", "pk", "unique", "json", "time", "marker")
        self._tree = ttk.Treeview(self, columns=columns, show="headings", height=20)
        headers = [t("scan.col_table"), t("scan.col_rows"), t("scan.col_pk"),
                   t("scan.col_unique"), t("scan.col_json"), t("scan.col_time"), t("scan.col_marker")]
        for col, hdr in zip(columns, headers):
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=120)
        self._tree.column("table", width=200)

        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=5)

    def retranslate(self):
        self._btn_scan.config(text=t("scan.btn_scan"))
        self._btn_load_cache.config(text=t("scan.btn_load_cache"))
        self._btn_use.config(text=t("scan.btn_use"))
        headers = [t("scan.col_table"), t("scan.col_rows"), t("scan.col_pk"),
                   t("scan.col_unique"), t("scan.col_json"), t("scan.col_time"), t("scan.col_marker")]
        for col, hdr in zip(("table", "rows", "pk", "unique", "json", "time", "marker"), headers):
            self._tree.heading(col, text=hdr)

    def _start_scan(self):
        if not self._session:
            return
        self._btn_scan.config(state=tk.DISABLED)
        self._lbl_progress.config(text=t("scan.scanning"))
        self._progress_var.set(0)

        def _worker():
            try:
                if not self._session.ensure_connected():
                    self.after(0, lambda: self._on_error("Database connection lost"))
                    return
                result = scan_database(self._session.db, progress_callback=self._on_progress_thread)
                result.scan_time = now_jst_str()
                self.after(0, lambda: self._on_finished(result))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self._on_error(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_progress_thread(self, current, total, table_name):
        # Schedule UI update on main thread
        self.after(0, lambda c=current, t_=total, n=table_name: self._on_progress(c, t_, n))

    def _on_progress(self, c, total, name):
        if total > 0:
            self._progress_var.set(c / total * 100)
        self._lbl_progress.config(text=t("scan.progress", c=c, t=total, name=name))

    def _on_finished(self, result: DatabaseScanResult):
        self.scan_result = result
        self._btn_scan.config(state=tk.NORMAL)
        self._btn_use.config(state=tk.NORMAL)
        self._lbl_progress.config(text=t("scan.complete", n=len(result.tables), time=result.scan_time))
        save_scan_result(result, AppPaths().metadata_cache_dir)
        self._populate_table(result)

    def _on_error(self, msg):
        self._btn_scan.config(state=tk.NORMAL)
        self._lbl_progress.config(text=f"{t('scan.error')}: {msg}")
        messagebox.showerror(t("scan.error"), msg)

    def _load_cached(self):
        paths = AppPaths()
        db_name = ""
        if self._session and self._session.config:
            db_name = self._session.config.database
        if not db_name:
            cached = list_cached_databases(paths.metadata_cache_dir)
            if not cached:
                messagebox.showinfo(t("scan.no_cache"), t("scan.no_cache_msg"))
                return
            db_name = cached[0]
        result = load_scan_result(paths.metadata_cache_dir, db_name)
        if result:
            self.scan_result = result
            self._btn_use.config(state=tk.NORMAL)
            self._lbl_progress.config(text=t("scan.loaded_cache", n=len(result.tables), time=result.scan_time))
            self._populate_table(result)
        else:
            messagebox.showinfo(t("scan.no_cache"), t("scan.no_cache_msg"))

    def _use_result(self):
        if self.scan_result and self.on_scan_complete:
            self.on_scan_complete(self.scan_result)

    def _populate_table(self, result: DatabaseScanResult):
        for item in self._tree.get_children():
            self._tree.delete(item)
        for name in sorted(result.tables.keys()):
            meta = result.tables[name]
            self._tree.insert("", tk.END, values=(
                name,
                str(meta.row_count),
                ", ".join(meta.primary_key_columns),
                ", ".join(meta.unique_key_columns),
                ", ".join(meta.json_columns),
                ", ".join(meta.time_columns),
                ", ".join(meta.marker_columns),
            ))
