"""
Page 6: History & Cleanup — with i18n, enhanced Report columns, and JST timestamps.
"""

from __future__ import annotations

import json

from PySide6.QtCore import Signal, Qt, QThread, QObject
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QTabWidget, QMessageBox, QLineEdit,
    QFormLayout, QSplitter, QDialog, QDialogButtonBox,
    QScrollArea, QFrame,
)

from src.config.app_config import AppPaths, ConnectionConfig
from src.execute.cleanup_runner import (
    CleanupPlan, CleanupTarget, CleanupReport, execute_cleanup,
)
from src.report.history import (
    list_plans, list_reports, list_cleanup_sql, load_report,
)
from src.ui.i18n import t
from src.utils.timezone import format_jst


class CleanupConfirmDialog(QDialog):
    """
    High-safety confirmation dialog for cleanup.
    Shows ALL tables in the campaign, each with its own PK range,
    estimated row count, and sample preview.

    table_infos: list of dicts with keys:
        table_name, pk_column, pk_start, pk_end,
        estimated_rows, sample_rows (list[dict])
    """

    def __init__(self, parent, db_name: str, campaign_id: str,
                 table_infos: list[dict]):
        super().__init__(parent)
        self.setWindowTitle(t("hist.confirm_dialog_title"))
        self.setMinimumWidth(680)
        self.setMinimumHeight(540)

        layout = QVBoxLayout(self)

        # Warning banner
        warn = QLabel(t("hist.confirm_warning"))
        warn.setStyleSheet("color: red; font-weight: bold; font-size: 13px;")
        warn.setWordWrap(True)
        layout.addWidget(warn)

        # Top summary group
        total_rows = sum(ti.get("estimated_rows", 0) for ti in table_infos)
        summary_group = QGroupBox(t("hist.confirm_info_group"))
        form = QFormLayout(summary_group)
        form.addRow(t("hist.confirm_db"),       QLabel(db_name))
        form.addRow(t("hist.confirm_campaign"), QLabel(campaign_id))
        form.addRow(t("hist.confirm_tables_count"),
                    QLabel(str(len(table_infos))))
        total_lbl = QLabel(str(total_rows))
        total_lbl.setStyleSheet("font-weight: bold; color: #cc4400;")
        form.addRow(t("hist.confirm_total_rows"), total_lbl)
        layout.addWidget(summary_group)

        # Scrollable area for per-table blocks
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(8)

        for ti in table_infos:
            est = ti.get("estimated_rows", 0)
            grp = QGroupBox(
                f"{ti['table_name']}  "
                f"({t('hist.confirm_est_rows')} {est:,})"
            )
            grp_layout = QVBoxLayout(grp)

            # Per-table metadata
            meta_form = QFormLayout()
            meta_form.addRow(t("hist.confirm_pk_col"),   QLabel(ti.get("pk_column", "")))
            meta_form.addRow(t("hist.confirm_pk_start"), QLabel(str(ti.get("pk_start", ""))))
            meta_form.addRow(t("hist.confirm_pk_end"),   QLabel(str(ti.get("pk_end", ""))))
            grp_layout.addLayout(meta_form)

            # Sample rows
            sample_rows = ti.get("sample_rows", [])
            if sample_rows:
                headers = list(sample_rows[0].keys())
                tbl = QTableWidget(len(sample_rows), len(headers))
                tbl.setHorizontalHeaderLabels(headers)
                tbl.horizontalHeader().setSectionResizeMode(
                    QHeaderView.ResizeMode.ResizeToContents)
                tbl.setMaximumHeight(140)
                tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                for r, row in enumerate(sample_rows):
                    for c, h in enumerate(headers):
                        tbl.setItem(r, c, QTableWidgetItem(str(row.get(h, ""))))
                grp_layout.addWidget(QLabel(t("hist.confirm_sample_group")))
                grp_layout.addWidget(tbl)
            else:
                grp_layout.addWidget(QLabel(t("hist.confirm_no_sample")))

            scroll_layout.addWidget(grp)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # Buttons
        btns = QDialogButtonBox()
        self._confirm_btn = QPushButton(t("hist.confirm_delete_btn"))
        self._confirm_btn.setStyleSheet(
            "background-color: #cc0000; color: white; font-weight: bold; padding: 4px 16px;")
        cancel_btn = QPushButton(t("hist.confirm_cancel_btn"))
        btns.addButton(self._confirm_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        btns.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)


class CleanupWorker(QObject):
    """Worker for background cleanup execution."""
    progress = Signal(int, int, str, int)
    finished = Signal(object)  # CleanupReport
    error = Signal(str)

    def __init__(self, conn_config: ConnectionConfig, plan: CleanupPlan, dry_run: bool):
        super().__init__()
        self.conn_config = conn_config
        self.plan = plan
        self.dry_run = dry_run

    def run(self):
        try:
            report = execute_cleanup(
                self.conn_config, self.plan, self.dry_run,
                progress_callback=self._on_progress,
            )
            self.finished.emit(report)
        except Exception as exc:
            self.error.emit(str(exc))

    def _on_progress(self, current, total, table_name, count):
        self.progress.emit(current, total, table_name, count)

class HistoryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.paths = AppPaths()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Top: tabbed history browser ──
        history_tabs = QTabWidget()
        self.history_tabs = history_tabs

        # Plans tab
        plans_widget = QWidget()
        plans_layout = QVBoxLayout(plans_widget)
        self.plans_table = QTableWidget()
        self.plans_table.setColumnCount(4)
        self.plans_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.plans_table.cellClicked.connect(self._on_plan_clicked)
        self.plans_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        plans_layout.addWidget(self.plans_table)
        history_tabs.addTab(plans_widget, "")

        # Reports tab — enhanced columns
        reports_widget = QWidget()
        reports_layout = QVBoxLayout(reports_widget)
        self.reports_table = QTableWidget()
        self.reports_table.setColumnCount(11)
        self.reports_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.reports_table.cellClicked.connect(self._on_report_clicked)
        self.reports_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        reports_layout.addWidget(self.reports_table)
        history_tabs.addTab(reports_widget, "")

        # Cleanup SQL tab
        cleanup_widget = QWidget()
        cleanup_layout = QVBoxLayout(cleanup_widget)
        self.cleanup_table = QTableWidget()
        self.cleanup_table.setColumnCount(2)
        self.cleanup_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.cleanup_table.cellClicked.connect(self._on_cleanup_sql_clicked)
        self.cleanup_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        cleanup_layout.addWidget(self.cleanup_table)
        history_tabs.addTab(cleanup_widget, "")

        splitter.addWidget(history_tabs)

        # ── Bottom: detail view + cleanup controls ──
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)

        # Detail viewer
        self.detail_group = QGroupBox()
        detail_layout = QVBoxLayout()
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(180)
        detail_layout.addWidget(self.detail_text)
        self.detail_group.setLayout(detail_layout)
        bottom_layout.addWidget(self.detail_group)

        # Cleanup controls
        self.cleanup_group = QGroupBox()
        cleanup_ctrl_layout = QFormLayout()
        self.cleanup_campaign_input = QLineEdit()
        self.cleanup_campaign_input.setPlaceholderText("campaign_id")
        self.lbl_campaign_id = QLabel()
        cleanup_ctrl_layout.addRow(self.lbl_campaign_id, self.cleanup_campaign_input)
        self.cleanup_group.setLayout(cleanup_ctrl_layout)
        bottom_layout.addWidget(self.cleanup_group)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton()
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_dry_run = QPushButton()
        self.btn_dry_run.clicked.connect(lambda: self._run_cleanup(dry_run=True))
        self.btn_execute_cleanup = QPushButton()
        self.btn_execute_cleanup.setStyleSheet("color: red; font-weight: bold;")
        self.btn_execute_cleanup.clicked.connect(lambda: self._run_cleanup(dry_run=False))
        btn_row.addWidget(self.btn_refresh)
        btn_row.addWidget(self.btn_dry_run)
        btn_row.addWidget(self.btn_execute_cleanup)
        btn_row.addStretch()
        bottom_layout.addLayout(btn_row)

        splitter.addWidget(bottom)
        layout.addWidget(splitter)

        self.retranslate()
        self.refresh()

    def retranslate(self):
        self.history_tabs.setTabText(0, t("hist.plans_tab"))
        self.history_tabs.setTabText(1, t("hist.reports_tab"))
        self.history_tabs.setTabText(2, t("hist.cleanup_tab"))
        self.detail_group.setTitle(t("hist.detail"))
        self.cleanup_group.setTitle(t("hist.cleanup_ops"))
        self.lbl_campaign_id.setText(t("hist.campaign_id"))
        self.btn_refresh.setText(t("hist.refresh"))
        self.btn_dry_run.setText(t("hist.dry_run"))
        self.btn_execute_cleanup.setText(t("hist.execute_cleanup"))
        # Plans table headers
        self.plans_table.setHorizontalHeaderLabels([
            t("hist.col_campaign"), t("hist.col_db"),
            t("hist.col_status"), t("hist.col_time"),
        ])
        # Reports table headers — 11 cols
        self.reports_table.setHorizontalHeaderLabels([
            t("hist.col_time"), t("hist.col_db"), t("hist.col_table"),
            t("hist.col_mode"), t("hist.col_rows"),
            t("hist.col_pk_col"), t("hist.col_pk_start"), t("hist.col_pk_end"),
            t("hist.col_campaign"), t("hist.col_report"), t("hist.col_cleanup"),
        ])
        # Cleanup SQL table headers
        self.cleanup_table.setHorizontalHeaderLabels([
            t("hist.col_campaign"), "File",
        ])

    def refresh(self):
        self._populate_plans()
        self._populate_reports()
        self._populate_cleanup_sql()

    def _make_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(str(text))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _populate_plans(self):
        self.plans_table.setRowCount(0)
        for entry in list_plans(self.paths.plans_dir):
            row = self.plans_table.rowCount()
            self.plans_table.insertRow(row)
            self.plans_table.setItem(row, 0, self._make_item(entry.campaign_id))
            self.plans_table.setItem(row, 1, self._make_item(entry.db_name))
            self.plans_table.setItem(row, 2, self._make_item(entry.status))
            self.plans_table.setItem(row, 3, self._make_item(format_jst(entry.created_at)))

    def _populate_reports(self):
        self.reports_table.setRowCount(0)
        for entry in list_reports(self.paths.reports_dir, self.paths.cleanup_sql_dir):
            row = self.reports_table.rowCount()
            self.reports_table.insertRow(row)
            rows_str = f"{entry.rows_inserted}/{entry.rows_attempted}"
            cleanup_label = "YES" if entry.cleanup_sql_path else "-"
            report_label = entry.report_path.split("/")[-1].split("\\")[-1] if entry.report_path else "-"
            self.reports_table.setItem(row, 0, self._make_item(format_jst(entry.created_at)))
            self.reports_table.setItem(row, 1, self._make_item(entry.db_name))
            self.reports_table.setItem(row, 2, self._make_item(entry.table_name))
            self.reports_table.setItem(row, 3, self._make_item(entry.mode or "insert"))
            self.reports_table.setItem(row, 4, self._make_item(rows_str))
            self.reports_table.setItem(row, 5, self._make_item(entry.pk_columns))
            self.reports_table.setItem(row, 6, self._make_item(entry.pk_start))
            self.reports_table.setItem(row, 7, self._make_item(entry.pk_end))
            self.reports_table.setItem(row, 8, self._make_item(entry.campaign_id))
            self.reports_table.setItem(row, 9, self._make_item(report_label))
            self.reports_table.setItem(row, 10, self._make_item(cleanup_label))
            # Store full paths in hidden data
            self.reports_table.item(row, 9).setData(Qt.ItemDataRole.UserRole, entry.report_path)
            self.reports_table.item(row, 10).setData(Qt.ItemDataRole.UserRole, entry.cleanup_sql_path)

    def _populate_cleanup_sql(self):
        self.cleanup_table.setRowCount(0)
        for entry in list_cleanup_sql(self.paths.cleanup_sql_dir):
            row = self.cleanup_table.rowCount()
            self.cleanup_table.insertRow(row)
            self.cleanup_table.setItem(row, 0, self._make_item(entry.campaign_id))
            self.cleanup_table.setItem(row, 1, self._make_item(entry.summary))

    def _on_plan_clicked(self, row, col):
        item = self.plans_table.item(row, 0)
        if item:
            campaign_id = item.text()
            plan_path = self.paths.plans_dir / f"campaign_{campaign_id}.json"
            if plan_path.exists():
                data = load_report(plan_path)
                self.detail_text.setPlainText(
                    json.dumps(data, indent=2, ensure_ascii=False, default=str)
                )
                self.cleanup_campaign_input.setText(campaign_id)

    def _on_report_clicked(self, row, col):
        report_item = self.reports_table.item(row, 9)
        cid_item = self.reports_table.item(row, 8)
        if report_item:
            report_path = report_item.data(Qt.ItemDataRole.UserRole) or ""
            cleanup_path = ""
            cleanup_item = self.reports_table.item(row, 10)
            if cleanup_item:
                cleanup_path = cleanup_item.data(Qt.ItemDataRole.UserRole) or ""
            from pathlib import Path
            if report_path and Path(report_path).exists():
                data = load_report(Path(report_path))
                # Build readable summary
                lines = [json.dumps(data, indent=2, ensure_ascii=False, default=str)]
                if cleanup_path:
                    lines.append(f"\n--- Cleanup SQL path ---\n{cleanup_path}")
                self.detail_text.setPlainText("\n".join(lines))
            if cid_item:
                self.cleanup_campaign_input.setText(cid_item.text())

    def _on_cleanup_sql_clicked(self, row, col):
        item = self.cleanup_table.item(row, 0)
        if item:
            cid = item.text()
            sql_path = self.paths.cleanup_sql_dir / f"cleanup_{cid}.sql"
            if sql_path.exists():
                self.detail_text.setPlainText(sql_path.read_text(encoding="utf-8"))
                self.cleanup_campaign_input.setText(cid)

    def _run_cleanup(self, dry_run: bool):
        campaign_id = self.cleanup_campaign_input.text().strip()
        if not campaign_id:
            QMessageBox.warning(self, t("common.warning"), t("hist.no_campaign"))
            return

        sql_path = self.paths.cleanup_sql_dir / f"cleanup_{campaign_id}.sql"
        if not sql_path.exists():
            QMessageBox.warning(self, t("common.warning"),
                                t("hist.no_sql", cid=campaign_id))
            return

        plan = CleanupPlan(campaign_id=campaign_id)
        report_data_list = []
        for report_file in self.paths.reports_dir.glob(f"report_{campaign_id}_*.json"):
            data = load_report(report_file)
            table_name = data.get("table_name", "")
            pk_start = data.get("pk_range_start", "")
            pk_end = data.get("pk_range_end", "")
            # Fix: read pk_column from report's pk_columns list
            pk_cols = data.get("pk_columns", [])
            pk_column = pk_cols[0] if pk_cols else ""
            if table_name and pk_start and pk_end and pk_column:
                plan.add_target(CleanupTarget(
                    table_name=table_name,
                    pk_column=pk_column,
                    pk_range_start=pk_start,
                    pk_range_end=pk_end,
                    campaign_id=campaign_id,
                ))
                report_data_list.append(data)

        if not plan.targets:
            QMessageBox.warning(self, t("common.warning"), t("hist.no_targets"))
            return

        # Get connection from session
        mw = self.window()
        conn_config: ConnectionConfig | None = getattr(mw, "conn_config", None)
        if conn_config is None:
            QMessageBox.warning(self, t("common.warning"), t("hist.no_conn"))
            return

        # Build per-table info list (query DB for estimates + samples)
        db_name = conn_config.database
        if report_data_list:
            db_name = report_data_list[0].get("db_name", db_name) or db_name

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
                        where = target.build_where_clause()
                        count_rows = _db.query(
                            f"SELECT COUNT(*) FROM `{target.table_name}` WHERE {where}"
                        )
                        ti["estimated_rows"] = int(count_rows[0][0]) if count_rows else 0
                        ti["sample_rows"] = _db.query_dicts(
                            f"SELECT * FROM `{target.table_name}` WHERE {where} LIMIT 5"
                        )
                    except Exception:
                        pass
                table_infos.append(ti)
        finally:
            if db_connected:
                _db.disconnect()

        # For non-dry-run: show high-safety confirmation dialog with ALL tables
        if not dry_run:
            dlg = CleanupConfirmDialog(
                self,
                db_name=db_name,
                campaign_id=campaign_id,
                table_infos=table_infos,
            )
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

        self.cleanup_thread = QThread()
        self.cleanup_worker = CleanupWorker(conn_config, plan, dry_run)
        self.cleanup_worker.moveToThread(self.cleanup_thread)
        self.cleanup_thread.started.connect(self.cleanup_worker.run)
        self.cleanup_worker.finished.connect(self._on_cleanup_finished)
        self.cleanup_worker.error.connect(self._on_cleanup_error)
        self.cleanup_worker.finished.connect(self.cleanup_thread.quit)
        self.cleanup_worker.error.connect(self.cleanup_thread.quit)
        self.cleanup_thread.start()

    def _on_cleanup_finished(self, report: CleanupReport):
        report.save(self.paths.reports_dir)
        self.detail_text.setPlainText(report.to_json())
        mode = "DRY-RUN" if report.dry_run else "EXECUTED"
        # Build per-table breakdown for result message
        lines = [f"[{mode}] Campaign: {report.campaign_id}\n"]
        for d in report.details:
            tname = d.get("table_name", "?")
            rows = d.get("rows_affected", 0)
            ok = d.get("success", True)
            status = "OK" if ok else f"ERROR: {d.get('error', '')}"
            lines.append(f"  {tname}: {rows:,} rows  [{status}]")
        lines.append(f"\nTotal deleted: {report.total_rows_deleted:,} rows")
        QMessageBox.information(
            self, t("common.info"), "\n".join(lines)
        )
        self.refresh()

    def _on_cleanup_error(self, error_msg: str):
        QMessageBox.critical(self, t("common.error"), error_msg)




