"""
Page 2: Database Scan — uses shared session, JST timestamps, i18n.
"""

from __future__ import annotations

from PySide6.QtCore import Signal, QThread, QObject
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar, QMessageBox,
)

from src.config.app_config import AppPaths
from src.metadata.models import DatabaseScanResult
from src.metadata.scanner import scan_database, save_scan_result, load_scan_result, list_cached_databases
from src.ui.i18n import t
from src.ui.session import SessionManager
from src.utils.timezone import now_jst_str


class ScanWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, session: SessionManager):
        super().__init__()
        self.session = session

    def run(self):
        try:
            if not self.session.ensure_connected():
                self.error.emit("Database connection lost")
                return
            result = scan_database(self.session.db, progress_callback=self._on_progress)
            # Overwrite scan_time with JST
            result.scan_time = now_jst_str()
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))

    def _on_progress(self, current, total, table_name):
        self.progress.emit(current, total, table_name)


class ScanPage(QWidget):
    scan_complete = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session: SessionManager | None = None
        self.scan_result: DatabaseScanResult | None = None
        self._init_ui()

    def set_session(self, session: SessionManager):
        self._session = session
        self.btn_scan.setEnabled(True)

    # kept for backward compat; redirects to set_session via main_window
    def set_connection(self, config):
        pass

    def _init_ui(self):
        layout = QVBoxLayout(self)

        ctrl = QHBoxLayout()
        self.btn_scan = QPushButton()
        self.btn_scan.clicked.connect(self._start_scan)
        self.btn_scan.setEnabled(False)
        self.btn_load_cache = QPushButton()
        self.btn_load_cache.clicked.connect(self._load_cached)
        self.btn_use = QPushButton()
        self.btn_use.clicked.connect(self._use_result)
        self.btn_use.setEnabled(False)
        self.btn_use.setStyleSheet("font-weight: bold;")

        ctrl.addWidget(self.btn_scan)
        ctrl.addWidget(self.btn_load_cache)
        ctrl.addWidget(self.btn_use)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.lbl_progress = QLabel("")
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.lbl_progress)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        self.retranslate()

    def retranslate(self):
        self.btn_scan.setText(t("scan.btn_scan"))
        self.btn_load_cache.setText(t("scan.btn_load_cache"))
        self.btn_use.setText(t("scan.btn_use"))
        headers = [t("scan.col_table"), t("scan.col_rows"), t("scan.col_pk"),
                   t("scan.col_unique"), t("scan.col_json"), t("scan.col_time"), t("scan.col_marker")]
        self.table.setHorizontalHeaderLabels(headers)

    def _start_scan(self):
        if not self._session:
            return
        self.btn_scan.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_progress.setText(t("scan.scanning"))

        self._thread = QThread()
        self._worker = ScanWorker(self._session)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _on_progress(self, c, tot, name):
        self.progress_bar.setMaximum(tot)
        self.progress_bar.setValue(c)
        self.lbl_progress.setText(t("scan.progress", c=c, t=tot, name=name))

    def _on_finished(self, result: DatabaseScanResult):
        self.scan_result = result
        self.btn_scan.setEnabled(True)
        self.btn_use.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_progress.setText(t("scan.complete", n=len(result.tables), time=result.scan_time))
        save_scan_result(result, AppPaths().metadata_cache_dir)
        self._populate_table(result)

    def _on_error(self, msg):
        self.btn_scan.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_progress.setText(f"{t('scan.error')}: {msg}")
        QMessageBox.critical(self, t("scan.error"), msg)

    def _load_cached(self):
        paths = AppPaths()
        db_name = ""
        if self._session and self._session.config:
            db_name = self._session.config.database
        if not db_name:
            cached = list_cached_databases(paths.metadata_cache_dir)
            if not cached:
                QMessageBox.information(self, t("scan.no_cache"), t("scan.no_cache_msg"))
                return
            db_name = cached[0]
        result = load_scan_result(paths.metadata_cache_dir, db_name)
        if result:
            self.scan_result = result
            self.btn_use.setEnabled(True)
            self.lbl_progress.setText(t("scan.loaded_cache", n=len(result.tables), time=result.scan_time))
            self._populate_table(result)
        else:
            QMessageBox.information(self, t("scan.no_cache"), t("scan.no_cache_msg"))

    def _use_result(self):
        if self.scan_result:
            self.scan_complete.emit(self.scan_result)

    def _populate_table(self, result: DatabaseScanResult):
        self.table.setRowCount(0)
        for name in sorted(result.tables.keys()):
            meta = result.tables[name]
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(name))
            self.table.setItem(r, 1, QTableWidgetItem(str(meta.row_count)))
            self.table.setItem(r, 2, QTableWidgetItem(", ".join(meta.primary_key_columns)))
            self.table.setItem(r, 3, QTableWidgetItem(", ".join(meta.unique_key_columns)))
            self.table.setItem(r, 4, QTableWidgetItem(", ".join(meta.json_columns)))
            self.table.setItem(r, 5, QTableWidgetItem(", ".join(meta.time_columns)))
            self.table.setItem(r, 6, QTableWidgetItem(", ".join(meta.marker_columns)))
