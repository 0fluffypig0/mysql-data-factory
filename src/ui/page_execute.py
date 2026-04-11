"""
Page 5: Execution & Logs — with i18n and JST timestamps.
V3.0: tkinter version.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from src.config.app_config import AppPaths, ConnectionConfig
from src.execute.progress import ProgressSnapshot
from src.metadata.models import DatabaseScanResult
from src.plan.models import CampaignPlan
from src.ui.i18n import t
from src.utils.timezone import now_jst_str
from src.workflow.campaign_runner import RunResult, run_campaign


class ExecutePage(ttk.Frame):
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.on_execution_complete = None  # callback()
        self._pending_snap: ProgressSnapshot | None = None
        self._init_ui()
        self._start_throttle_timer()

    def _init_ui(self):
        # Status
        self._lbl_status = ttk.Label(self, text=t("exec.no_exec"), font=("", 12, "bold"))
        self._lbl_status.pack(fill=tk.X, padx=10, pady=5)

        # Overall progress
        self._progress_var = tk.DoubleVar()
        self._progress_bar = ttk.Progressbar(self, variable=self._progress_var, maximum=100)
        self._progress_bar.pack(fill=tk.X, padx=10, pady=2)
        self._lbl_progress = ttk.Label(self, text="")
        self._lbl_progress.pack(fill=tk.X, padx=10)

        # Detail panel
        detail_frame = ttk.LabelFrame(self, text=t("exec.detail_title"))
        detail_frame.pack(fill=tk.X, padx=10, pady=5)
        self._detail_frame = detail_frame

        row1 = ttk.Frame(detail_frame)
        row1.pack(fill=tk.X, padx=5, pady=1)
        self._lbl_phase = ttk.Label(row1, text="", font=("", 10, "bold"))
        self._lbl_phase.pack(side=tk.LEFT)
        self._lbl_table_detail = ttk.Label(row1, text="")
        self._lbl_table_detail.pack(side=tk.LEFT, padx=10)

        row2 = ttk.Frame(detail_frame)
        row2.pack(fill=tk.X, padx=5, pady=1)
        self._lbl_rows = ttk.Label(row2, text="")
        self._lbl_rows.pack(side=tk.LEFT, padx=5)
        self._lbl_chunk = ttk.Label(row2, text="")
        self._lbl_chunk.pack(side=tk.LEFT, padx=5)
        self._lbl_batch = ttk.Label(row2, text="")
        self._lbl_batch.pack(side=tk.LEFT, padx=5)

        row3 = ttk.Frame(detail_frame)
        row3.pack(fill=tk.X, padx=5, pady=1)
        self._lbl_speed = ttk.Label(row3, text="", foreground="#0066cc")
        self._lbl_speed.pack(side=tk.LEFT, padx=5)
        self._lbl_eta = ttk.Label(row3, text="", foreground="#0066cc")
        self._lbl_eta.pack(side=tk.LEFT, padx=5)

        self._detail_progress_var = tk.DoubleVar()
        self._detail_bar = ttk.Progressbar(detail_frame, variable=self._detail_progress_var, maximum=100)
        self._detail_bar.pack(fill=tk.X, padx=5, pady=2)

        # Results table
        result_frame = ttk.LabelFrame(self, text=t("exec.results"))
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self._result_frame = result_frame

        columns = ("table", "status", "attempted", "inserted", "failed", "pkrange")
        self._result_tree = ttk.Treeview(result_frame, columns=columns, show="headings", height=8)
        headers = [t("exec.col_table"), t("exec.col_status"), t("exec.col_attempted"),
                   t("exec.col_inserted"), t("exec.col_failed"), t("exec.col_pkrange")]
        for col, hdr in zip(columns, headers):
            self._result_tree.heading(col, text=hdr)
            self._result_tree.column(col, width=100)
        self._result_tree.column("table", width=180)
        self._result_tree.column("pkrange", width=200)
        self._result_tree.pack(fill=tk.BOTH, expand=True)

        # Log output
        log_frame = ttk.LabelFrame(self, text=t("exec.log"))
        log_frame.pack(fill=tk.BOTH, padx=10, pady=5)
        self._log_frame = log_frame

        self._log_text = tk.Text(log_frame, height=8, state=tk.DISABLED, wrap=tk.WORD)
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_scroll.set)
        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Bottom
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=10, pady=5)
        self._btn_stop = ttk.Button(bottom, text=t("exec.stop"), state=tk.DISABLED)
        self._btn_stop.pack(side=tk.LEFT, padx=3)
        self._lbl_paths = ttk.Label(bottom, text="", wraplength=600)
        self._lbl_paths.pack(side=tk.LEFT, padx=10)

    def retranslate(self):
        self._lbl_status.config(text=t("exec.no_exec"))
        self._detail_frame.config(text=t("exec.detail_title"))
        self._result_frame.config(text=t("exec.results"))
        self._log_frame.config(text=t("exec.log"))
        self._btn_stop.config(text=t("exec.stop"))
        headers = [t("exec.col_table"), t("exec.col_status"), t("exec.col_attempted"),
                   t("exec.col_inserted"), t("exec.col_failed"), t("exec.col_pkrange")]
        for col, hdr in zip(("table", "status", "attempted", "inserted", "failed", "pkrange"), headers):
            self._result_tree.heading(col, text=hdr)

    def _log(self, msg: str):
        self._log_text.config(state=tk.NORMAL)
        self._log_text.insert(tk.END, msg + "\n")
        self._log_text.see(tk.END)
        self._log_text.config(state=tk.DISABLED)

    def _start_throttle_timer(self):
        """Flush pending detail snapshot every 300ms."""
        self._flush_detail()
        self.after(300, self._start_throttle_timer)

    def _flush_detail(self):
        snap = self._pending_snap
        if snap is None:
            return
        self._pending_snap = None

        phase_labels = {"sample": "SAMPLE", "generate": "GENERATE",
                        "insert": "INSERT", "done": "DONE"}
        self._lbl_phase.config(text=phase_labels.get(snap.phase, snap.phase.upper()))
        self._lbl_table_detail.config(text=snap.table_name)

        if snap.phase == "generate":
            self._lbl_rows.config(text=f"Generated: {snap.generated_rows:,} / {snap.total_rows:,}")
            self._lbl_chunk.config(text=f"Chunk: {snap.chunk_idx} / {snap.total_chunks}")
            self._lbl_batch.config(text="")
            total = snap.total_chunks or 1
            self._detail_progress_var.set(snap.chunk_idx / total * 100)
        elif snap.phase == "insert":
            self._lbl_rows.config(text=f"Inserted: {snap.inserted_rows:,} / {snap.total_rows:,}")
            self._lbl_chunk.config(text=f"Chunk: {snap.chunk_idx} / {snap.total_chunks}")
            self._lbl_batch.config(text=f"Batch: {snap.batch_idx} / {snap.total_batches}")
            total = snap.total_batches or 1
            self._detail_progress_var.set(snap.batch_idx / total * 100)
        else:
            self._lbl_rows.config(text="")
            self._lbl_chunk.config(text="")
            self._lbl_batch.config(text="")

        self._lbl_speed.config(text=f"Speed: {snap.speed_str()}")
        self._lbl_eta.config(text=f"ETA: {snap.eta_str()}")

    def start_execution(self, plan: CampaignPlan, conn_config: ConnectionConfig,
                        scan_result: DatabaseScanResult | None):
        self._lbl_status.config(text=t("exec.running", cid=plan.campaign_id))
        self._progress_var.set(0)
        for item in self._result_tree.get_children():
            self._result_tree.delete(item)
        self._log_text.config(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.config(state=tk.DISABLED)
        self._btn_stop.config(state=tk.NORMAL)
        self._log(f"[{now_jst_str()}] Starting campaign {plan.campaign_id}")

        paths = AppPaths()
        session = self.main_window.session
        shared_db = session.db if session and session.is_connected else None

        def _worker():
            try:
                result = run_campaign(
                    plan=plan, conn_config=conn_config, paths=paths,
                    scan_result=scan_result,
                    progress_callback=self._on_progress_thread,
                    db=shared_db,
                    detail_callback=self._on_detail_thread,
                )
                self.after(0, lambda: self._on_finished(result))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self._on_error(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_progress_thread(self, task_idx, total, phase, detail):
        self.after(0, lambda: self._on_progress(task_idx, total, phase, detail))

    def _on_detail_thread(self, snap: ProgressSnapshot):
        self._pending_snap = snap
        if snap.log_line:
            self.after(0, lambda line=snap.log_line: self._log(f"[{now_jst_str()}] {line}"))

    def _on_progress(self, task_idx: int, total: int, phase: str, detail: str):
        if total > 0:
            self._progress_var.set(task_idx / total * 100)
        self._lbl_progress.config(
            text=t("exec.progress", idx=task_idx, total=total, phase=phase, detail=detail))

    def _on_finished(self, run_result: RunResult):
        # Flush last snapshot
        if self._pending_snap is not None:
            self._flush_detail()
        self._pending_snap = None
        self._btn_stop.config(state=tk.DISABLED)

        all_ok = all(r.status == "completed" for r in run_result.reports)
        status_key = "exec.status_ok" if all_ok else "exec.status_err"
        self._lbl_status.config(
            text=t("exec.complete", cid=run_result.campaign_id, status=t(status_key)),
            foreground="green" if all_ok else "orange")
        self._log(f"[{now_jst_str()}] Finished: {t(status_key)}")

        for item in self._result_tree.get_children():
            self._result_tree.delete(item)
        for report in run_result.reports:
            pk_range = (f"{report.pk_range_start} ~ {report.pk_range_end}"
                        if report.pk_range_start else "(n/a)")
            self._result_tree.insert("", tk.END, values=(
                report.table_name, report.status,
                str(report.total_rows_attempted), str(report.total_rows_inserted),
                str(report.failed_batches), pk_range,
            ))

        paths = AppPaths()
        self._lbl_paths.config(
            text=f"Reports: {paths.reports_dir}\n"
                 f"Cleanup SQL: {paths.cleanup_sql_dir}\n"
                 f"Output data: {paths.output_dir}")

        if self.on_execution_complete:
            self.on_execution_complete()

    def _on_error(self, error_msg: str):
        self._pending_snap = None
        self._btn_stop.config(state=tk.DISABLED)
        self._lbl_status.config(text=f"{t('common.error')}: {error_msg}", foreground="red")
        self._log(f"[{now_jst_str()}] [ERROR] {error_msg}")
