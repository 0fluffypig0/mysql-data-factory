"""
Page 5: Execution & Logs — with i18n and JST timestamps.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Signal, QThread, QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QProgressBar, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView,
)

from src.config.app_config import AppPaths, ConnectionConfig
from src.execute.progress import ProgressSnapshot
from src.metadata.models import DatabaseScanResult
from src.plan.models import CampaignPlan
from src.ui.i18n import t
from src.utils.timezone import now_jst_str
from src.workflow.campaign_runner import RunResult, run_campaign


class CampaignWorker(QObject):
    """Worker for background campaign execution."""
    progress = Signal(int, int, str, str)  # task_idx, total, phase, detail
    detail_progress = Signal(object)       # ProgressSnapshot
    log_message = Signal(str)
    finished = Signal(object)  # RunResult
    error = Signal(str)

    def __init__(self, plan: CampaignPlan, conn_config: ConnectionConfig,
                 paths: AppPaths, scan_result=None, db=None):
        super().__init__()
        self.plan = plan
        self.conn_config = conn_config
        self.paths = paths
        self.scan_result = scan_result
        self.db = db

    def run(self):
        try:
            result = run_campaign(
                plan=self.plan,
                conn_config=self.conn_config,
                paths=self.paths,
                scan_result=self.scan_result,
                progress_callback=self._on_progress,
                db=self.db,
                detail_callback=self._on_detail,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))

    def _on_progress(self, task_idx, total, phase, detail):
        self.progress.emit(task_idx, total, phase, detail)
        self.log_message.emit(f"[{task_idx}/{total}] {phase}: {detail}")

    def _on_detail(self, snap: ProgressSnapshot):
        self.detail_progress.emit(snap)


class ExecutePage(QWidget):
    execution_complete = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Status
        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.lbl_status)

        # Progress
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        self.lbl_progress = QLabel("")
        layout.addWidget(self.lbl_progress)

        # Detail panel (fine-grained progress)
        self.detail_group = QGroupBox()
        detail_layout = QVBoxLayout()
        detail_layout.setSpacing(2)

        row1 = QHBoxLayout()
        self.lbl_phase = QLabel("")
        self.lbl_phase.setStyleSheet("font-weight: bold;")
        self.lbl_table_detail = QLabel("")
        row1.addWidget(self.lbl_phase)
        row1.addWidget(self.lbl_table_detail)
        row1.addStretch()
        detail_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.lbl_rows = QLabel("")
        self.lbl_chunk = QLabel("")
        self.lbl_batch = QLabel("")
        for lbl in (self.lbl_rows, self.lbl_chunk, self.lbl_batch):
            lbl.setStyleSheet("color: #444; font-size: 12px;")
            row2.addWidget(lbl)
        row2.addStretch()
        detail_layout.addLayout(row2)

        row3 = QHBoxLayout()
        self.lbl_speed = QLabel("")
        self.lbl_eta = QLabel("")
        for lbl in (self.lbl_speed, self.lbl_eta):
            lbl.setStyleSheet("color: #0066cc; font-size: 12px;")
            row3.addWidget(lbl)
        row3.addStretch()
        detail_layout.addLayout(row3)

        self.detail_bar = QProgressBar()
        self.detail_bar.setMaximumHeight(12)
        self.detail_bar.setTextVisible(False)
        detail_layout.addWidget(self.detail_bar)

        self.detail_group.setLayout(detail_layout)
        layout.addWidget(self.detail_group)

        # Throttle: buffer latest snapshot, flush to UI every 300ms
        self._pending_snap: object = None
        self._throttle_timer = QTimer(self)
        self._throttle_timer.setInterval(300)
        self._throttle_timer.timeout.connect(self._flush_detail)

        # Results table
        self.result_group = QGroupBox()
        result_layout = QVBoxLayout()
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(6)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        result_layout.addWidget(self.result_table)
        self.result_group.setLayout(result_layout)
        layout.addWidget(self.result_group)

        # Log output
        self.log_group = QGroupBox()
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        log_layout.addWidget(self.log_text)
        self.log_group.setLayout(log_layout)
        layout.addWidget(self.log_group)

        # Bottom controls
        btn_layout = QHBoxLayout()
        self.btn_stop = QPushButton()
        self.btn_stop.setEnabled(False)
        self.lbl_paths = QLabel("")
        self.lbl_paths.setWordWrap(True)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.lbl_paths)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.retranslate()

    def retranslate(self):
        self.lbl_status.setText(t("exec.no_exec"))
        self.detail_group.setTitle(t("exec.detail_title"))
        self.result_group.setTitle(t("exec.results"))
        self.log_group.setTitle(t("exec.log"))
        self.btn_stop.setText(t("exec.stop"))
        self.result_table.setHorizontalHeaderLabels([
            t("exec.col_table"), t("exec.col_status"),
            t("exec.col_attempted"), t("exec.col_inserted"),
            t("exec.col_failed"), t("exec.col_pkrange"),
        ])

    def start_execution(self, plan: CampaignPlan, conn_config: ConnectionConfig,
                        scan_result: DatabaseScanResult | None):
        self.lbl_status.setText(t("exec.running", cid=plan.campaign_id))
        self.lbl_status.setStyleSheet("font-weight: bold; font-size: 14px; color: #333;")
        self.progress_bar.setValue(0)
        self.result_table.setRowCount(0)
        self.log_text.clear()
        self.btn_stop.setEnabled(True)
        self.log_text.append(f"[{now_jst_str()}] Starting campaign {plan.campaign_id}")

        paths = AppPaths()
        mw = self.window()
        shared_db = getattr(mw, 'session', None)
        shared_db = shared_db.db if shared_db is not None else None
        self._worker = CampaignWorker(plan, conn_config, paths, scan_result, db=shared_db)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.detail_progress.connect(self._on_detail_progress)
        self._worker.log_message.connect(self.log_text.append)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)

        self._pending_snap = None
        self._throttle_timer.start()
        self._thread.start()

    def _on_detail_progress(self, snap):
        """Buffer latest snapshot; actual UI update happens in _flush_detail."""
        self._pending_snap = snap
        # Also emit log line immediately if present (key events only)
        if snap.log_line:
            self.log_text.append(f"[{now_jst_str()}] {snap.log_line}")

    def _flush_detail(self):
        """Called by QTimer every 300ms — update detail panel from buffered snapshot."""
        snap = self._pending_snap
        if snap is None:
            return
        self._pending_snap = None

        phase_labels = {"sample": "Sample", "generate": "Generate",
                        "insert": "Insert", "done": "Done"}
        self.lbl_phase.setText(phase_labels.get(snap.phase, snap.phase).upper())
        self.lbl_table_detail.setText(snap.table_name)

        if snap.phase == "generate":
            self.lbl_rows.setText(
                f"Generated: {snap.generated_rows:,} / {snap.total_rows:,}")
            self.lbl_chunk.setText(
                f"Chunk: {snap.chunk_idx} / {snap.total_chunks}")
            self.lbl_batch.setText("")
            self.detail_bar.setMaximum(snap.total_chunks or 1)
            self.detail_bar.setValue(snap.chunk_idx)
        elif snap.phase == "insert":
            self.lbl_rows.setText(
                f"Inserted: {snap.inserted_rows:,} / {snap.total_rows:,}")
            self.lbl_chunk.setText(
                f"Chunk: {snap.chunk_idx} / {snap.total_chunks}")
            self.lbl_batch.setText(
                f"Batch: {snap.batch_idx} / {snap.total_batches}")
            self.detail_bar.setMaximum(snap.total_batches or 1)
            self.detail_bar.setValue(snap.batch_idx)
        else:
            self.lbl_rows.setText("")
            self.lbl_chunk.setText("")
            self.lbl_batch.setText("")

        self.lbl_speed.setText(f"Speed: {snap.speed_str()}")
        self.lbl_eta.setText(f"ETA: {snap.eta_str()}")

    def _on_progress(self, task_idx: int, total: int, phase: str, detail: str):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(task_idx)
        self.lbl_progress.setText(t("exec.progress", idx=task_idx, total=total,
                                     phase=phase, detail=detail))

    def _on_finished(self, run_result: RunResult):
        self._throttle_timer.stop()
        # Flush the last buffered snapshot BEFORE clearing it so detail panel shows final values
        if self._pending_snap is not None:
            self._flush_detail()
        self._pending_snap = None
        self.btn_stop.setEnabled(False)
        all_ok = all(r.status == "completed" for r in run_result.reports)
        status_key = "exec.status_ok" if all_ok else "exec.status_err"
        self.lbl_status.setText(
            t("exec.complete", cid=run_result.campaign_id, status=t(status_key))
        )
        color = "green" if all_ok else "orange"
        self.lbl_status.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {color};")
        self.log_text.append(f"[{now_jst_str()}] Finished: {t(status_key)}")

        self.result_table.setRowCount(0)
        for report in run_result.reports:
            row_idx = self.result_table.rowCount()
            self.result_table.insertRow(row_idx)
            self.result_table.setItem(row_idx, 0, QTableWidgetItem(report.table_name))
            self.result_table.setItem(row_idx, 1, QTableWidgetItem(report.status))
            self.result_table.setItem(row_idx, 2, QTableWidgetItem(str(report.total_rows_attempted)))
            self.result_table.setItem(row_idx, 3, QTableWidgetItem(str(report.total_rows_inserted)))
            self.result_table.setItem(row_idx, 4, QTableWidgetItem(str(report.failed_batches)))
            pk_range = (f"{report.pk_range_start} ~ {report.pk_range_end}"
                        if report.pk_range_start else "(n/a)")
            self.result_table.setItem(row_idx, 5, QTableWidgetItem(pk_range))

        paths = AppPaths()
        self.lbl_paths.setText(
            f"Reports: {paths.reports_dir}\n"
            f"Cleanup SQL: {paths.cleanup_sql_dir}\n"
            f"Output data: {paths.output_dir}"
        )

        self.execution_complete.emit()

    def _on_error(self, error_msg: str):
        self._throttle_timer.stop()
        self._pending_snap = None
        self.btn_stop.setEnabled(False)
        self.lbl_status.setText(f"{t('common.error')}: {error_msg}")
        self.lbl_status.setStyleSheet("font-weight: bold; font-size: 14px; color: red;")
        self.log_text.append(f"[{now_jst_str()}] [ERROR] {error_msg}")
