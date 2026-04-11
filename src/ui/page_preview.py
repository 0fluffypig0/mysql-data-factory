"""
Page 4: Preview & Confirm — uses shared session, i18n.
V3.0: tkinter version.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from src.config.app_config import ConnectionConfig
from src.execute.preflight import run_preflight_check
from src.generate.row_builder import generate_preview, resolve_start_values
from src.metadata.models import DatabaseScanResult
from src.plan.models import CampaignPlan, TaskItem
from src.sample.selector import normalize_sample_for_csv, select_by_pk, select_top_rows
from src.ui.i18n import t
from src.ui.session import SessionManager


class PreviewPage(ttk.Frame):
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.plan: CampaignPlan | None = None
        self.conn_config: ConnectionConfig | None = None
        self.scan_result: DatabaseScanResult | None = None
        self._session: SessionManager | None = None
        self._init_ui()

    def _init_ui(self):
        self._lbl_summary = ttk.Label(self, text=t("preview.no_plan"), font=("", 12, "bold"))
        self._lbl_summary.pack(fill=tk.X, padx=10, pady=5)

        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        self._btn_refresh = ttk.Button(btn_frame, text=t("preview.refresh"), command=self._refresh_preview)
        self._btn_refresh.pack(side=tk.LEFT, padx=3)
        self._btn_execute = ttk.Button(btn_frame, text=t("preview.execute"), command=self._execute)
        self._btn_execute.pack(side=tk.LEFT, padx=3)

    def retranslate(self):
        self._btn_refresh.config(text=t("preview.refresh"))
        self._btn_execute.config(text=t("preview.execute"))
        if not self.plan:
            self._lbl_summary.config(text=t("preview.no_plan"))

    def set_plan(self, plan, conn_config, scan_result, session=None):
        self.plan = plan
        self.conn_config = conn_config
        self.scan_result = scan_result
        if session:
            self._session = session
        self._lbl_summary.config(
            text=t("preview.summary", cid=plan.campaign_id,
                   tables=plan.table_count, rows=f"{plan.total_rows:,}"))
        self._refresh_preview()

    def _refresh_preview(self):
        if not self.plan:
            return
        # Clear old tabs
        for tab_id in self._notebook.tabs():
            self._notebook.forget(tab_id)
        for task in self.plan.tasks:
            tab = self._build_tab(task)
            self._notebook.add(tab, text=task.table_name)

    def _build_tab(self, task: TaskItem) -> ttk.Frame:
        frame = ttk.Frame(self._notebook)

        meta = self.scan_result.tables.get(task.table_name) if self.scan_result else None
        lines = [f"Table: {task.table_name}", f"Mode: {task.mode}",
                 f"Rows: {task.row_count:,}  |  Batch: {task.batch_size}",
                 f"PK Mode: {task.pk_config.mode}",
                 f"Sample: {task.sample_method} ({task.sample_pk_value or task.sample_where or 'first row'})"]
        if meta:
            lines.append(f"PK Columns: {meta.pk_display}")
            lines.append(f"Current max PK: {meta.max_pk_value or '(unknown)'}")
        if task.marker_column and task.marker_value:
            lines.append(f"Marker: {task.marker_column} = {task.marker_value}")

        info_text = tk.Text(frame, height=6, wrap=tk.WORD, state=tk.NORMAL)
        info_text.insert(tk.END, "\n".join(lines))
        info_text.config(state=tk.DISABLED)
        info_text.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(frame, text=t("preview.first_rows")).pack(anchor=tk.W, padx=5)

        # Preview table
        try:
            rows = self._gen_preview(task, meta)
            if rows:
                cols = list(rows[0].keys())
                tree = ttk.Treeview(frame, columns=cols, show="headings", height=5)
                for col in cols:
                    tree.heading(col, text=col)
                    tree.column(col, width=100)
                for row in rows:
                    vals = []
                    for c in cols:
                        v = str(row.get(c, ""))
                        if len(v) > 50:
                            v = v[:50] + "..."
                        vals.append(v)
                    tree.insert("", tk.END, values=vals)
                tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            else:
                ttk.Label(frame, text="No preview data").pack(padx=5)
        except Exception as exc:
            ttk.Label(frame, text=f"Error: {exc}").pack(padx=5)

        return frame

    def _gen_preview(self, task, meta):
        session = self._session or self.main_window.session
        if session and session.ensure_connected():
            db = session.db
        else:
            from src.db.connection import DatabaseManager
            db = DatabaseManager(config=self.conn_config)
            if not db.connect():
                return []

        pk_cols = meta.primary_key_columns if meta else []
        if task.sample_pk_value and pk_cols:
            sample = select_by_pk(db, task.table_name, pk_cols, [task.sample_pk_value])
        else:
            results = select_top_rows(db, task.table_name, limit=1)
            sample = results[0] if results else None
        if not sample:
            return []
        tmpl = normalize_sample_for_csv(sample.row_data)
        col_order = sample.column_order or list(tmpl.keys())
        if not pk_cols and col_order:
            pk_cols = [col_order[0]]
        uq = [c for c in (meta.unique_key_columns if meta else []) if c not in pk_cols]
        sv = resolve_start_values(db, task.table_name, tmpl, pk_cols + uq)
        if task.pk_config.mode in ("fixed_start", "explicit_range") and task.pk_config.start_value is not None:
            for col in pk_cols:
                sv[col] = task.pk_config.start_value
        return generate_preview(col_order, tmpl, pk_cols, uq, sv, count=5,
                                marker_column=task.marker_column, marker_value=task.marker_value)

    def _execute(self):
        if not self.plan:
            return
        if not messagebox.askyesno(
            t("preview.confirm_title"),
            t("preview.confirm_msg", tables=self.plan.table_count,
              rows=f"{self.plan.total_rows:,}", cid=self.plan.campaign_id)
        ):
            return

        # ── Preflight PK conflict check ──
        session = self._session or self.main_window.session
        shared_db = session.db if session and session.is_connected else None

        preflight = run_preflight_check(
            self.plan, self.conn_config, self.scan_result, db=shared_db
        )
        if preflight.error:
            messagebox.showwarning(t("common.error"), preflight.error)
            return

        if preflight.has_conflicts:
            msg_lines = [t("conflict.found"), ""]
            for c in preflight.conflicts:
                if c.conflict_count <= 0:
                    continue
                msg_lines.append(t("conflict.table_hdr",
                                   table=c.table_name, pk=c.pk_column, n=c.conflict_count))
                msg_lines.append(t("conflict.range_info",
                                   start=c.planned_start, end=c.planned_end))
                if c.conflict_samples:
                    samples = ", ".join(c.conflict_samples[:5])
                    msg_lines.append(t("conflict.samples", vals=samples))
                msg_lines.append("")
            msg_lines.append(t("conflict.ask_continue"))

            if not messagebox.askyesno(t("conflict.title"), "\n".join(msg_lines)):
                messagebox.showinfo(t("common.info"), t("conflict.abort"))
                return

        # ── Proceed to execution ──
        mw = self.main_window
        mw.page_execute.start_execution(self.plan, self.conn_config, self.scan_result)
        mw.notebook.select(4)
