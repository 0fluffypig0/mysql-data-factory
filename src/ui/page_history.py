"""
Page 6: History & Cleanup — with i18n, enhanced Report columns, and JST timestamps.
V3.0: tkinter version.
"""

from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from src.config.app_config import AppPaths, ConnectionConfig
from src.execute.cleanup_runner import (
    CleanupPlan, CleanupTarget, CleanupReport, execute_cleanup,
)
from src.report.history import (
    list_plans, list_reports, list_cleanup_sql, load_report,
)
from src.ui.i18n import t
from src.utils.timezone import format_jst


class CleanupConfirmDialog(tk.Toplevel):
    """High-safety confirmation dialog for cleanup."""

    def __init__(self, parent, db_name: str, campaign_ids: list[str],
                 table_infos: list[dict]):
        super().__init__(parent)
        self.title(t("hist.confirm_dialog_title"))
        self.geometry("720x600")
        self.resizable(True, True)
        self.result = False
        self.transient(parent)
        self.grab_set()

        # Warning
        warn = ttk.Label(self, text=t("hist.confirm_warning"),
                         foreground="red", font=("", 11, "bold"), wraplength=680)
        warn.pack(padx=10, pady=10)

        # Summary
        total_rows = sum(ti.get("estimated_rows", 0) for ti in table_infos)
        summary = ttk.LabelFrame(self, text=t("hist.confirm_info_group"))
        summary.pack(fill=tk.X, padx=10, pady=5)

        is_batch = len(campaign_ids) > 1
        campaign_display = campaign_ids[0] if campaign_ids else ""
        if is_batch:
            campaign_display = f"{t('hist.campaign_multiple')}  ({len(campaign_ids)})"

        rows_to_show = [
            (t("hist.confirm_db"), db_name),
            (t("hist.confirm_campaign"), campaign_display),
            (t("hist.confirm_tables_count"), str(len(table_infos))),
            (t("hist.confirm_total_rows"), f"{total_rows:,}"),
        ]
        if is_batch:
            rows_to_show.insert(2, (t("hist.confirm_campaigns_count"), str(len(campaign_ids))))

        for label, value in rows_to_show:
            row = ttk.Frame(summary)
            row.pack(fill=tk.X, padx=5, pady=1)
            ttk.Label(row, text=label, width=20, anchor=tk.E).pack(side=tk.LEFT)
            ttk.Label(row, text=value).pack(side=tk.LEFT, padx=5)

        if is_batch:
            cid_list_frame = ttk.Frame(summary)
            cid_list_frame.pack(fill=tk.X, padx=5, pady=2)
            ttk.Label(cid_list_frame, text=t("hist.confirm_campaigns_list"),
                      width=20, anchor=tk.NE).pack(side=tk.LEFT, anchor=tk.N)
            lst = tk.Text(cid_list_frame, height=min(5, len(campaign_ids)),
                          wrap=tk.WORD, font=("", 9))
            lst.insert(tk.END, "\n".join(campaign_ids))
            lst.config(state=tk.DISABLED)
            lst.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Per-table details (scrollable)
        canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        for ti in table_infos:
            est = ti.get("estimated_rows", 0)
            grp = ttk.LabelFrame(scroll_frame,
                                 text=f"{ti['table_name']}  ({t('hist.confirm_est_rows')} {est:,})")
            grp.pack(fill=tk.X, padx=5, pady=3)

            for label, value in [
                (t("hist.confirm_pk_col"), ti.get("pk_column", "")),
                (t("hist.confirm_pk_start"), str(ti.get("pk_start", ""))),
                (t("hist.confirm_pk_end"), str(ti.get("pk_end", ""))),
            ]:
                row = ttk.Frame(grp)
                row.pack(fill=tk.X, padx=5, pady=1)
                ttk.Label(row, text=label, width=16, anchor=tk.E).pack(side=tk.LEFT)
                ttk.Label(row, text=value).pack(side=tk.LEFT, padx=5)

            sample_rows = ti.get("sample_rows", [])
            if sample_rows:
                ttk.Label(grp, text=t("hist.confirm_sample_group")).pack(anchor=tk.W, padx=5)
                headers = list(sample_rows[0].keys())
                tree = ttk.Treeview(grp, columns=headers, show="headings", height=min(5, len(sample_rows)))
                for h in headers:
                    tree.heading(h, text=h)
                    tree.column(h, width=80)
                for sr in sample_rows:
                    tree.insert("", tk.END, values=[str(sr.get(h, "")) for h in headers])
                tree.pack(fill=tk.X, padx=5, pady=2)
            else:
                ttk.Label(grp, text=t("hist.confirm_no_sample")).pack(padx=5)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text=t("hist.confirm_cancel_btn"),
                   command=self._cancel).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text=t("hist.confirm_delete_btn"),
                   command=self._confirm).pack(side=tk.RIGHT, padx=5)

    def _confirm(self):
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()

    def show(self) -> bool:
        self.wait_window()
        return self.result


class HistoryPage(ttk.Frame):
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.paths = AppPaths()
        self._init_ui()
        self.refresh()

    def _init_ui(self):
        paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # ── Top: tabbed history browser ──
        self._history_notebook = ttk.Notebook(paned)

        # Plans tab
        plans_frame = ttk.Frame(self._history_notebook)
        self._plans_tree = self._make_tree(plans_frame,
                                           ("campaign", "db", "status", "time"),
                                           selectmode="extended")
        self._plans_tree.bind("<<TreeviewSelect>>", self._on_plan_clicked)
        self._history_notebook.add(plans_frame, text=t("hist.plans_tab"))

        # Reports tab
        reports_frame = ttk.Frame(self._history_notebook)
        report_cols = ("time", "db", "table", "mode", "rows", "pk_col", "pk_start", "pk_end",
                       "campaign", "report", "cleanup")
        self._reports_tree = self._make_tree(reports_frame, report_cols,
                                             selectmode="extended")
        self._reports_tree.bind("<<TreeviewSelect>>", self._on_report_clicked)
        self._history_notebook.add(reports_frame, text=t("hist.reports_tab"))
        # Store path data per report row
        self._report_data: dict[str, dict] = {}

        # Cleanup SQL tab
        cleanup_frame = ttk.Frame(self._history_notebook)
        self._cleanup_tree = self._make_tree(cleanup_frame, ("campaign", "file"))
        self._cleanup_tree.bind("<<TreeviewSelect>>", self._on_cleanup_sql_clicked)
        self._history_notebook.add(cleanup_frame, text=t("hist.cleanup_tab"))

        paned.add(self._history_notebook, weight=2)

        # ── Bottom: detail + cleanup ──
        bottom = ttk.Frame(paned)

        detail_frame = ttk.LabelFrame(bottom, text=t("hist.detail"))
        detail_frame.pack(fill=tk.BOTH, expand=True, pady=3)
        self._detail_frame = detail_frame
        self._detail_text = tk.Text(detail_frame, height=8, state=tk.DISABLED, wrap=tk.WORD)
        self._detail_text.pack(fill=tk.BOTH, expand=True)

        cleanup_frame2 = ttk.LabelFrame(bottom, text=t("hist.cleanup_ops"))
        cleanup_frame2.pack(fill=tk.X, pady=3)
        self._cleanup_frame = cleanup_frame2

        # Batch-selection hint
        self._lbl_batch_hint = ttk.Label(cleanup_frame2, text=t("hist.batch_hint"),
                                          foreground="#555", wraplength=900)
        self._lbl_batch_hint.pack(fill=tk.X, padx=5, pady=(4, 0))

        # Row 1: campaign_id + selected count
        row = ttk.Frame(cleanup_frame2)
        row.pack(fill=tk.X, padx=5, pady=5)
        self._lbl_campaign_id = ttk.Label(row, text=t("hist.campaign_id"))
        self._lbl_campaign_id.pack(side=tk.LEFT)
        self._campaign_var = tk.StringVar()
        ttk.Entry(row, textvariable=self._campaign_var, width=30).pack(side=tk.LEFT, padx=5)
        self._lbl_selected_count = ttk.Label(row, text=t("hist.selected_count", n=0),
                                              foreground="#06c")
        self._lbl_selected_count.pack(side=tk.LEFT, padx=15)

        # Row 2: action buttons
        btn_row = ttk.Frame(cleanup_frame2)
        btn_row.pack(fill=tk.X, padx=5, pady=3)
        self._btn_refresh = ttk.Button(btn_row, text=t("hist.refresh"), command=self.refresh)
        self._btn_refresh.pack(side=tk.LEFT, padx=3)
        self._btn_select_all = ttk.Button(btn_row, text=t("hist.select_all"),
                                           command=self._select_all_current_tab)
        self._btn_select_all.pack(side=tk.LEFT, padx=3)
        self._btn_deselect_all = ttk.Button(btn_row, text=t("hist.deselect_all"),
                                             command=self._deselect_all)
        self._btn_deselect_all.pack(side=tk.LEFT, padx=3)
        self._btn_dry_run = ttk.Button(btn_row, text=t("hist.dry_run"),
                                        command=lambda: self._run_cleanup(dry_run=True))
        self._btn_dry_run.pack(side=tk.LEFT, padx=3)
        self._btn_execute_cleanup = ttk.Button(btn_row, text=t("hist.execute_cleanup"),
                                                command=lambda: self._run_cleanup(dry_run=False))
        self._btn_execute_cleanup.pack(side=tk.LEFT, padx=3)

        paned.add(bottom, weight=1)

    def _make_tree(self, parent, columns, selectmode: str = "browse") -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=columns, show="headings",
                            height=8, selectmode=selectmode)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=100)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        return tree

    def retranslate(self):
        self._history_notebook.tab(0, text=t("hist.plans_tab"))
        self._history_notebook.tab(1, text=t("hist.reports_tab"))
        self._history_notebook.tab(2, text=t("hist.cleanup_tab"))
        self._detail_frame.config(text=t("hist.detail"))
        self._cleanup_frame.config(text=t("hist.cleanup_ops"))
        self._lbl_batch_hint.config(text=t("hist.batch_hint"))
        self._lbl_campaign_id.config(text=t("hist.campaign_id"))
        self._btn_refresh.config(text=t("hist.refresh"))
        self._btn_select_all.config(text=t("hist.select_all"))
        self._btn_deselect_all.config(text=t("hist.deselect_all"))
        self._btn_dry_run.config(text=t("hist.dry_run"))
        self._btn_execute_cleanup.config(text=t("hist.execute_cleanup"))
        self._update_selection_count()

        plan_hdrs = [t("hist.col_campaign"), t("hist.col_db"), t("hist.col_status"), t("hist.col_time")]
        for col, hdr in zip(("campaign", "db", "status", "time"), plan_hdrs):
            self._plans_tree.heading(col, text=hdr)

        report_cols = ("time", "db", "table", "mode", "rows", "pk_col", "pk_start", "pk_end",
                       "campaign", "report", "cleanup")
        report_hdrs = [t("hist.col_time"), t("hist.col_db"), t("hist.col_table"),
                       t("hist.col_mode"), t("hist.col_rows"),
                       t("hist.col_pk_col"), t("hist.col_pk_start"), t("hist.col_pk_end"),
                       t("hist.col_campaign"), t("hist.col_report"), t("hist.col_cleanup")]
        for col, hdr in zip(report_cols, report_hdrs):
            self._reports_tree.heading(col, text=hdr)

        for col, hdr in zip(("campaign", "file"), [t("hist.col_campaign"), "File"]):
            self._cleanup_tree.heading(col, text=hdr)

    def refresh(self):
        self._populate_plans()
        self._populate_reports()
        self._populate_cleanup_sql()

    def _populate_plans(self):
        for item in self._plans_tree.get_children():
            self._plans_tree.delete(item)
        for entry in list_plans(self.paths.plans_dir):
            self._plans_tree.insert("", tk.END, values=(
                entry.campaign_id, entry.db_name, entry.status, format_jst(entry.created_at)))

    def _populate_reports(self):
        for item in self._reports_tree.get_children():
            self._reports_tree.delete(item)
        self._report_data.clear()
        for entry in list_reports(self.paths.reports_dir, self.paths.cleanup_sql_dir):
            rows_str = f"{entry.rows_inserted}/{entry.rows_attempted}"
            cleanup_label = "YES" if entry.cleanup_sql_path else "-"
            report_label = entry.report_path.split("/")[-1].split("\\")[-1] if entry.report_path else "-"
            iid = self._reports_tree.insert("", tk.END, values=(
                format_jst(entry.created_at), entry.db_name, entry.table_name,
                entry.mode or "insert", rows_str,
                entry.pk_columns, entry.pk_start, entry.pk_end,
                entry.campaign_id, report_label, cleanup_label))
            self._report_data[iid] = {
                "report_path": entry.report_path,
                "cleanup_sql_path": entry.cleanup_sql_path,
                "campaign_id": entry.campaign_id,
            }

    def _populate_cleanup_sql(self):
        for item in self._cleanup_tree.get_children():
            self._cleanup_tree.delete(item)
        for entry in list_cleanup_sql(self.paths.cleanup_sql_dir):
            self._cleanup_tree.insert("", tk.END, values=(entry.campaign_id, entry.summary))

    def _set_detail(self, text: str):
        self._detail_text.config(state=tk.NORMAL)
        self._detail_text.delete("1.0", tk.END)
        self._detail_text.insert(tk.END, text)
        self._detail_text.config(state=tk.DISABLED)

    def _on_plan_clicked(self, event=None):
        sel = self._plans_tree.selection()
        self._update_selection_count()
        if not sel:
            return
        # Detail pane shows the last-clicked row; campaign field stays single unless multi-sel.
        vals = self._plans_tree.item(sel[-1], "values")
        campaign_id = vals[0]
        plan_path = self.paths.plans_dir / f"campaign_{campaign_id}.json"
        if plan_path.exists():
            data = load_report(plan_path)
            self._set_detail(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        if len(sel) == 1:
            self._campaign_var.set(campaign_id)
        else:
            self._campaign_var.set(t("hist.campaign_multiple"))

    def _on_report_clicked(self, event=None):
        sel = self._reports_tree.selection()
        self._update_selection_count()
        if not sel:
            return
        iid = sel[-1]
        meta = self._report_data.get(iid, {})
        report_path = meta.get("report_path", "")
        cleanup_path = meta.get("cleanup_sql_path", "")
        campaign_id = meta.get("campaign_id", "")
        from pathlib import Path
        if report_path and Path(report_path).exists():
            data = load_report(Path(report_path))
            lines = [json.dumps(data, indent=2, ensure_ascii=False, default=str)]
            if cleanup_path:
                lines.append(f"\n--- Cleanup SQL path ---\n{cleanup_path}")
            self._set_detail("\n".join(lines))
        # Collapse campaign_var to single id if all selected rows share one campaign.
        if len(sel) == 1:
            if campaign_id:
                self._campaign_var.set(campaign_id)
        else:
            cids = {self._report_data.get(i, {}).get("campaign_id", "") for i in sel}
            cids.discard("")
            if len(cids) == 1:
                self._campaign_var.set(next(iter(cids)))
            else:
                self._campaign_var.set(t("hist.campaign_multiple"))

    def _on_cleanup_sql_clicked(self, event=None):
        sel = self._cleanup_tree.selection()
        self._update_selection_count()
        if not sel:
            return
        vals = self._cleanup_tree.item(sel[-1], "values")
        cid = vals[0]
        sql_path = self.paths.cleanup_sql_dir / f"cleanup_{cid}.sql"
        if sql_path.exists():
            self._set_detail(sql_path.read_text(encoding="utf-8"))
            self._campaign_var.set(cid)

    # ── Batch selection helpers ───────────────────────────────
    def _current_tree(self) -> ttk.Treeview | None:
        """Return the tree in the currently focused history tab."""
        try:
            idx = self._history_notebook.index(self._history_notebook.select())
        except tk.TclError:
            return None
        return [self._plans_tree, self._reports_tree, self._cleanup_tree][idx] \
            if 0 <= idx < 3 else None

    def _select_all_current_tab(self):
        tree = self._current_tree()
        if tree is None:
            return
        tree.selection_set(tree.get_children())
        self._update_selection_count()

    def _deselect_all(self):
        for tree in (self._plans_tree, self._reports_tree, self._cleanup_tree):
            tree.selection_remove(tree.selection())
        self._campaign_var.set("")
        self._update_selection_count()

    def _update_selection_count(self):
        n = len(self._plans_tree.selection()) + len(self._reports_tree.selection())
        self._lbl_selected_count.config(text=t("hist.selected_count", n=n))

    def _collect_report_files(self) -> list:
        """
        Gather report JSON paths based on (in priority order):
          1. Reports tab multi-selection (most granular)
          2. Plans tab multi-selection (expands to all reports per campaign)
          3. Campaign ID entered in the text box (single-campaign fallback)
        """
        from pathlib import Path

        # 1. Reports tab selection
        reports_sel = self._reports_tree.selection()
        if reports_sel:
            out = []
            for iid in reports_sel:
                rp = self._report_data.get(iid, {}).get("report_path", "")
                if rp and Path(rp).exists():
                    out.append(Path(rp))
            return out

        # 2. Plans tab selection
        plans_sel = self._plans_tree.selection()
        if plans_sel:
            seen = set()
            out = []
            for iid in plans_sel:
                vals = self._plans_tree.item(iid, "values")
                if not vals:
                    continue
                cid = vals[0]
                for rp in self.paths.reports_dir.glob(f"report_{cid}_*.json"):
                    key = rp.resolve()
                    if key not in seen:
                        seen.add(key)
                        out.append(rp)
            return out

        # 3. Text box fallback
        cid = self._campaign_var.get().strip()
        if cid and cid != t("hist.campaign_multiple"):
            return list(self.paths.reports_dir.glob(f"report_{cid}_*.json"))

        return []

    def _run_cleanup(self, dry_run: bool):
        report_files = self._collect_report_files()
        if not report_files:
            messagebox.showwarning(t("common.warning"), t("hist.no_selection"))
            return

        # Build plan from all gathered reports.
        campaign_ids_seen: list[str] = []
        report_data_list: list[dict] = []
        targets: list[CleanupTarget] = []
        for rp in report_files:
            data = load_report(rp)
            table_name = data.get("table_name", "")
            pk_start = data.get("pk_range_start", "")
            pk_end = data.get("pk_range_end", "")
            pk_cols = data.get("pk_columns", [])
            pk_column = pk_cols[0] if pk_cols else ""
            cid = data.get("campaign_id", "")
            if cid and cid not in campaign_ids_seen:
                campaign_ids_seen.append(cid)
            if table_name and pk_start and pk_end and pk_column:
                targets.append(CleanupTarget(
                    table_name=table_name, pk_column=pk_column,
                    pk_range_start=pk_start, pk_range_end=pk_end,
                    campaign_id=cid,
                ))
                report_data_list.append(data)

        if not targets:
            messagebox.showwarning(t("common.warning"), t("hist.no_targets"))
            return

        # Plan-level campaign_id: single cid if all targets share one, otherwise
        # a synthetic batch id so the cleanup report file has a unique name.
        if len(campaign_ids_seen) == 1:
            plan_cid = campaign_ids_seen[0]
        else:
            from datetime import datetime as _dt
            plan_cid = f"batch_{_dt.now().strftime('%Y%m%d_%H%M%S')}"

        plan = CleanupPlan(campaign_id=plan_cid)
        for tg in targets:
            plan.add_target(tg)

        conn_config: ConnectionConfig | None = self.main_window.conn_config
        if conn_config is None:
            messagebox.showwarning(t("common.warning"), t("hist.no_conn"))
            return

        db_name = conn_config.database
        if report_data_list:
            db_name = report_data_list[0].get("db_name", db_name) or db_name

        # Build per-table info with one shared connection.
        table_infos = []
        from src.db.connection import DatabaseManager
        _db = DatabaseManager(config=conn_config)
        db_connected = _db.connect()
        try:
            for target in plan.targets:
                ti = {
                    "table_name": target.table_name,
                    "pk_column": target.pk_column,
                    "pk_start": target.pk_range_start,
                    "pk_end": target.pk_range_end,
                    "estimated_rows": 0,
                    "sample_rows": [],
                }
                if db_connected:
                    try:
                        where = target.build_where_clause(_db.dialect_name)
                        qt = _db.quote_identifier(target.table_name)
                        count_rows = _db.query(
                            f"SELECT COUNT(*) FROM {qt} WHERE {where}")
                        ti["estimated_rows"] = int(count_rows[0][0]) if count_rows else 0
                        ti["sample_rows"] = _db.query_dicts(
                            f"SELECT * FROM {qt} WHERE {where} LIMIT 5")
                    except Exception:
                        pass
                table_infos.append(ti)
        finally:
            if db_connected:
                _db.disconnect()

        # Confirmation dialog for non-dry-run
        if not dry_run:
            dlg = CleanupConfirmDialog(self, db_name=db_name,
                                        campaign_ids=campaign_ids_seen or [plan_cid],
                                        table_infos=table_infos)
            if not dlg.show():
                return

        def _worker():
            try:
                report = execute_cleanup(conn_config, plan, dry_run)
                self.after(0, lambda: self._on_cleanup_finished(report))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self._on_cleanup_error(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_cleanup_finished(self, report: CleanupReport):
        report.save(self.paths.reports_dir)
        self._set_detail(report.to_json())
        mode = "DRY-RUN" if report.dry_run else "EXECUTED"
        lines = [f"[{mode}] Campaign: {report.campaign_id}\n"]
        for d in report.details:
            tname = d.get("table_name", "?")
            rows = d.get("rows_affected", 0)
            ok = d.get("success", True)
            status = "OK" if ok else f"ERROR: {d.get('error', '')}"
            lines.append(f"  {tname}: {rows:,} rows  [{status}]")
        lines.append(f"\nTotal deleted: {report.total_rows_deleted:,} rows")
        messagebox.showinfo(t("common.info"), "\n".join(lines))
        self.refresh()

    def _on_cleanup_error(self, error_msg: str):
        messagebox.showerror(t("common.error"), error_msg)
