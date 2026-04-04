"""
Page 4: Preview & Confirm — uses shared session, i18n.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QMessageBox,
)

from src.config.app_config import ConnectionConfig
from src.execute.preflight import run_preflight_check
from src.generate.row_builder import generate_preview, resolve_start_values
from src.metadata.models import DatabaseScanResult
from src.plan.models import CampaignPlan, TaskItem
from src.sample.selector import normalize_sample_for_csv, select_by_pk, select_top_rows
from src.ui.i18n import t
from src.ui.session import SessionManager


class PreviewPage(QWidget):
    confirmed = Signal(object, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plan: CampaignPlan | None = None
        self.conn_config: ConnectionConfig | None = None
        self.scan_result: DatabaseScanResult | None = None
        self._session: SessionManager | None = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        self.lbl_summary = QLabel(t("preview.no_plan"))
        self.lbl_summary.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.lbl_summary)

        self.preview_tabs = QTabWidget()
        layout.addWidget(self.preview_tabs)

        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self._refresh_preview)
        self.btn_execute = QPushButton()
        self.btn_execute.clicked.connect(self._execute)
        self.btn_execute.setStyleSheet("font-weight: bold; background-color: #4CAF50; color: white;")
        btn_layout.addWidget(self.btn_refresh); btn_layout.addWidget(self.btn_execute); btn_layout.addStretch()
        layout.addLayout(btn_layout)
        self.retranslate()

    def retranslate(self):
        self.btn_refresh.setText(t("preview.refresh"))
        self.btn_execute.setText(t("preview.execute"))
        if not self.plan:
            self.lbl_summary.setText(t("preview.no_plan"))

    def set_plan(self, plan, conn_config, scan_result, session=None):
        self.plan = plan
        self.conn_config = conn_config
        self.scan_result = scan_result
        if session:
            self._session = session
        self.lbl_summary.setText(t("preview.summary", cid=plan.campaign_id,
                                    tables=plan.table_count, rows=f"{plan.total_rows:,}"))
        self._refresh_preview()

    def _refresh_preview(self):
        if not self.plan: return
        self.preview_tabs.clear()
        for task in self.plan.tasks:
            tab = self._build_tab(task)
            self.preview_tabs.addTab(tab, task.table_name)

    def _build_tab(self, task: TaskItem) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        info = QTextEdit(); info.setReadOnly(True); info.setMaximumHeight(120)
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
        info.setPlainText("\n".join(lines))
        layout.addWidget(info)

        layout.addWidget(QLabel(t("preview.first_rows")))
        preview_table = QTableWidget()
        try:
            rows = self._gen_preview(task, meta)
            if rows:
                cols = list(rows[0].keys())
                preview_table.setColumnCount(len(cols))
                preview_table.setHorizontalHeaderLabels(cols)
                preview_table.setRowCount(len(rows))
                for ri, row in enumerate(rows):
                    for ci, col in enumerate(cols):
                        v = str(row.get(col, ""))
                        if len(v) > 50: v = v[:50] + "..."
                        preview_table.setItem(ri, ci, QTableWidgetItem(v))
                preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        except Exception as exc:
            preview_table.setRowCount(1); preview_table.setColumnCount(1)
            preview_table.setItem(0, 0, QTableWidgetItem(f"Error: {exc}"))
        layout.addWidget(preview_table)
        return widget

    def _gen_preview(self, task, meta):
        # Use shared session if available
        session = self._session or (self.window().session if hasattr(self.window(), 'session') else None)
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
        if not sample: return []
        tmpl = normalize_sample_for_csv(sample.row_data)
        col_order = sample.column_order or list(tmpl.keys())
        if not pk_cols and col_order: pk_cols = [col_order[0]]
        uq = [c for c in (meta.unique_key_columns if meta else []) if c not in pk_cols]
        sv = resolve_start_values(db, task.table_name, tmpl, pk_cols + uq)
        # Apply pk_config overrides: fixed_start / explicit_range must bypass DB MAX
        if task.pk_config.mode in ("fixed_start", "explicit_range") and task.pk_config.start_value is not None:
            for col in pk_cols:
                sv[col] = task.pk_config.start_value
        # Do NOT disconnect — shared session
        return generate_preview(col_order, tmpl, pk_cols, uq, sv, count=5,
                                 marker_column=task.marker_column, marker_value=task.marker_value)

    def _execute(self):
        if not self.plan: return
        reply = QMessageBox.question(self, t("preview.confirm_title"),
            t("preview.confirm_msg", tables=self.plan.table_count,
              rows=f"{self.plan.total_rows:,}", cid=self.plan.campaign_id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        # ── Preflight PK conflict check ──
        session = self._session or (self.window().session if hasattr(self.window(), 'session') else None)
        shared_db = session.db if session and session.is_connected else None

        preflight = run_preflight_check(
            self.plan, self.conn_config, self.scan_result, db=shared_db
        )
        if preflight.error:
            QMessageBox.warning(self, t("common.error"), preflight.error)
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

            reply2 = QMessageBox.warning(
                self, t("conflict.title"), "\n".join(msg_lines),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,  # default = No
            )
            if reply2 != QMessageBox.StandardButton.Yes:
                QMessageBox.information(self, t("common.info"), t("conflict.abort"))
                return

        # ── Proceed to execution ──
        mw = self.window()
        if hasattr(mw, 'page_execute'):
            mw.page_execute.start_execution(self.plan, self.conn_config, self.scan_result)
            mw.tabs.setCurrentIndex(4)
