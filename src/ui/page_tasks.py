"""
Page 3: Multi-Table Task Configuration — i18n + template save/load.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QSpinBox, QComboBox, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QStackedWidget, QMessageBox, QSplitter,
    QInputDialog,
)

from src.config.app_config import ConnectionConfig
from src.metadata.models import DatabaseScanResult, TableMetadata
from src.plan.models import CampaignPlan, TaskItem
from src.strategy.pk_planner import PKRangeConfig
from src.ui.i18n import t

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _PROJECT_ROOT / "task_templates"


class TaskConfigWidget(QWidget):
    """Per-table configuration widget."""

    def __init__(self, table_meta: TableMetadata, parent=None):
        super().__init__(parent)
        self.table_meta = table_meta
        self._init_ui()

    def _init_ui(self):
        layout = QFormLayout(self)
        info = (f"Table: {self.table_meta.table_name}  |  "
                f"Rows: {self.table_meta.row_count}  |  "
                f"PK: {self.table_meta.pk_display}")
        lbl_info = QLabel(info)
        lbl_info.setStyleSheet("font-weight: bold; color: #333;")
        layout.addRow(lbl_info)

        self.sample_method = QComboBox()
        self.sample_method.addItems(["first_row", "pk_lookup", "where_clause"])
        self.lbl_sample_method = QLabel()
        layout.addRow(self.lbl_sample_method, self.sample_method)

        self.sample_pk_value = QLineEdit()
        self.lbl_sample_pk = QLabel()
        layout.addRow(self.lbl_sample_pk, self.sample_pk_value)

        self.sample_where = QLineEdit()
        self.lbl_sample_where = QLabel()
        layout.addRow(self.lbl_sample_where, self.sample_where)

        self.pk_mode = QComboBox()
        self.pk_mode.addItems(["auto_increment_from_max", "fixed_start", "explicit_range"])
        self.lbl_pk_mode = QLabel()
        layout.addRow(self.lbl_pk_mode, self.pk_mode)

        self.pk_start = QLineEdit()
        self.lbl_pk_start = QLabel()
        layout.addRow(self.lbl_pk_start, self.pk_start)

        self.pk_end = QLineEdit()
        self.lbl_pk_end = QLabel()
        layout.addRow(self.lbl_pk_end, self.pk_end)

        self.pk_prefix = QLineEdit()
        self.lbl_pk_prefix = QLabel()
        layout.addRow(self.lbl_pk_prefix, self.pk_prefix)

        self.pk_pad_width = QSpinBox(); self.pk_pad_width.setRange(0, 20)
        self.lbl_zero_pad = QLabel()
        layout.addRow(self.lbl_zero_pad, self.pk_pad_width)

        self.row_count = QSpinBox(); self.row_count.setRange(1, 10_000_000); self.row_count.setValue(1000)
        self.lbl_row_count = QLabel()
        layout.addRow(self.lbl_row_count, self.row_count)

        self.batch_size = QSpinBox(); self.batch_size.setRange(100, 10000); self.batch_size.setValue(1000)
        self.lbl_batch_size = QLabel()
        layout.addRow(self.lbl_batch_size, self.batch_size)

        self.mode = QComboBox()
        self.mode.addItems(["insert", "dry-run", "export"])
        self.lbl_mode = QLabel()
        layout.addRow(self.lbl_mode, self.mode)

        self.marker_column = QComboBox()
        self.marker_column.addItem(t("common.none"))
        for col in self.table_meta.marker_columns:
            self.marker_column.addItem(col)
        self.lbl_marker_col = QLabel()
        layout.addRow(self.lbl_marker_col, self.marker_column)

        self.marker_value = QLineEdit()
        self.lbl_marker_val = QLabel()
        layout.addRow(self.lbl_marker_val, self.marker_value)

        self.retranslate()

    def retranslate(self):
        self.lbl_sample_method.setText(t("tasks.sample_method"))
        self.lbl_sample_pk.setText(t("tasks.sample_pk"))
        self.lbl_sample_where.setText(t("tasks.sample_where"))
        self.lbl_pk_mode.setText(t("tasks.pk_mode"))
        self.lbl_pk_start.setText(t("tasks.pk_start"))
        self.lbl_pk_end.setText(t("tasks.pk_end"))
        self.lbl_pk_prefix.setText(t("tasks.pk_prefix"))
        self.lbl_zero_pad.setText(t("tasks.zero_pad"))
        self.lbl_row_count.setText(t("tasks.row_count"))
        self.lbl_batch_size.setText(t("tasks.batch_size"))
        self.lbl_mode.setText(t("tasks.mode"))
        self.lbl_marker_col.setText(t("tasks.marker_col"))
        self.lbl_marker_val.setText(t("tasks.marker_val"))

    def to_task_item(self) -> TaskItem:
        pk_start = pk_end = None
        try:
            if self.pk_start.text().strip(): pk_start = int(self.pk_start.text().strip())
        except ValueError: pass
        try:
            if self.pk_end.text().strip(): pk_end = int(self.pk_end.text().strip())
        except ValueError: pass
        marker_col = self.marker_column.currentText()
        if marker_col == t("common.none"):
            marker_col = ""
        return TaskItem(
            table_name=self.table_meta.table_name,
            row_count=self.row_count.value(), batch_size=self.batch_size.value(),
            mode=self.mode.currentText(),
            sample_pk_value=self.sample_pk_value.text().strip(),
            sample_where=self.sample_where.text().strip(),
            sample_method=self.sample_method.currentText(),
            pk_config=PKRangeConfig(mode=self.pk_mode.currentText(), start_value=pk_start,
                                     end_value=pk_end, prefix=self.pk_prefix.text().strip(),
                                     zero_pad_width=self.pk_pad_width.value()),
            marker_column=marker_col, marker_value=self.marker_value.text().strip(),
        )

    def to_template_dict(self) -> dict:
        """Serialize current widget values into a JSON-friendly dict."""
        return {
            "table_name": self.table_meta.table_name,
            "sample_method": self.sample_method.currentText(),
            "sample_pk_value": self.sample_pk_value.text().strip(),
            "sample_where": self.sample_where.text().strip(),
            "pk_mode": self.pk_mode.currentText(),
            "pk_start": self.pk_start.text().strip(),
            "pk_end": self.pk_end.text().strip(),
            "pk_prefix": self.pk_prefix.text().strip(),
            "pk_pad_width": self.pk_pad_width.value(),
            "row_count": self.row_count.value(),
            "batch_size": self.batch_size.value(),
            "mode": self.mode.currentText(),
            "marker_column": self.marker_column.currentText(),
            "marker_value": self.marker_value.text().strip(),
        }

    def load_from_template(self, data: dict) -> None:
        """Restore widget values from a template dict."""
        def _set_combo(combo: QComboBox, value: str):
            idx = combo.findText(value)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        _set_combo(self.sample_method, data.get("sample_method", "first_row"))
        self.sample_pk_value.setText(data.get("sample_pk_value", ""))
        self.sample_where.setText(data.get("sample_where", ""))
        _set_combo(self.pk_mode, data.get("pk_mode", "auto_increment_from_max"))
        self.pk_start.setText(data.get("pk_start", ""))
        self.pk_end.setText(data.get("pk_end", ""))
        self.pk_prefix.setText(data.get("pk_prefix", ""))
        self.pk_pad_width.setValue(data.get("pk_pad_width", 0))
        self.row_count.setValue(data.get("row_count", 1000))
        self.batch_size.setValue(data.get("batch_size", 1000))
        _set_combo(self.mode, data.get("mode", "insert"))
        _set_combo(self.marker_column, data.get("marker_column", t("common.none")))
        self.marker_value.setText(data.get("marker_value", ""))


class TasksPage(QWidget):
    tasks_confirmed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scan_result: DatabaseScanResult | None = None
        self.conn_config: ConnectionConfig | None = None
        self.task_widgets: dict[str, TaskConfigWidget] = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        self.top_group = QGroupBox()
        top = QHBoxLayout()
        self.table_combo = QComboBox(); self.table_combo.setMinimumWidth(250)
        self.lbl_table = QLabel()
        self.btn_add = QPushButton()
        self.btn_add.clicked.connect(self._add_table)
        self.btn_remove = QPushButton()
        self.btn_remove.clicked.connect(self._remove_table)
        top.addWidget(self.lbl_table); top.addWidget(self.table_combo)
        top.addWidget(self.btn_add); top.addWidget(self.btn_remove); top.addStretch()
        self.top_group.setLayout(top)
        layout.addWidget(self.top_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.task_list = QListWidget()
        self.task_list.currentRowChanged.connect(self._on_task_selected)
        splitter.addWidget(self.task_list)

        self.config_stack = QStackedWidget()
        self.empty_widget = QLabel()
        self.empty_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.config_stack.addWidget(self.empty_widget)
        splitter.addWidget(self.config_stack)
        splitter.setSizes([250, 700])
        layout.addWidget(splitter)

        # Template section
        self.tpl_group = QGroupBox()
        tpl_layout = QHBoxLayout()
        self.lbl_tpl = QLabel()
        self.tpl_combo = QComboBox(); self.tpl_combo.setMinimumWidth(200)
        self.btn_save_tpl = QPushButton()
        self.btn_save_tpl.clicked.connect(self._save_template)
        self.btn_load_tpl = QPushButton()
        self.btn_load_tpl.clicked.connect(self._load_template)
        self.btn_delete_tpl = QPushButton()
        self.btn_delete_tpl.clicked.connect(self._delete_template)
        tpl_layout.addWidget(self.lbl_tpl); tpl_layout.addWidget(self.tpl_combo)
        tpl_layout.addWidget(self.btn_save_tpl); tpl_layout.addWidget(self.btn_load_tpl)
        tpl_layout.addWidget(self.btn_delete_tpl); tpl_layout.addStretch()
        self.tpl_group.setLayout(tpl_layout)
        layout.addWidget(self.tpl_group)
        self._refresh_template_list()

        btn_layout = QHBoxLayout()
        self.btn_confirm = QPushButton()
        self.btn_confirm.clicked.connect(self._confirm_tasks)
        self.btn_confirm.setStyleSheet("font-weight: bold;")
        self.lbl_summary = QLabel("")
        btn_layout.addWidget(self.btn_confirm); btn_layout.addWidget(self.lbl_summary); btn_layout.addStretch()
        layout.addLayout(btn_layout)
        self.retranslate()

    def retranslate(self):
        self.top_group.setTitle(t("tasks.add_tables"))
        self.lbl_table.setText(t("tasks.table_label"))
        self.btn_add.setText(t("tasks.btn_add"))
        self.btn_remove.setText(t("tasks.btn_remove"))
        self.empty_widget.setText(t("tasks.select_hint"))
        self.btn_confirm.setText(t("tasks.confirm"))
        self.tpl_group.setTitle(t("tasks.tpl_group"))
        self.lbl_tpl.setText(t("tasks.tpl_label"))
        self.btn_save_tpl.setText(t("tasks.btn_save_tpl"))
        self.btn_load_tpl.setText(t("tasks.btn_load_tpl"))
        self.btn_delete_tpl.setText(t("tasks.btn_delete_tpl"))
        for w in self.task_widgets.values():
            w.retranslate()

    def set_scan_result(self, scan_result, conn_config):
        self.scan_result = scan_result
        self.conn_config = conn_config
        self.table_combo.clear()
        for n in scan_result.table_names:
            self.table_combo.addItem(n)

    def _add_table(self):
        name = self.table_combo.currentText()
        if not name or not self.scan_result: return
        if name in self.task_widgets:
            QMessageBox.information(self, t("common.info"), t("tasks.already_added", name=name)); return
        meta = self.scan_result.tables.get(name)
        if not meta: return
        widget = TaskConfigWidget(meta)
        self.task_widgets[name] = widget
        self.config_stack.addWidget(widget)
        item = QListWidgetItem(name)
        self.task_list.addItem(item); self.task_list.setCurrentItem(item)
        self._update_summary()

    def _remove_table(self):
        cur = self.task_list.currentItem()
        if not cur: return
        name = cur.text()
        if name in self.task_widgets:
            w = self.task_widgets.pop(name); self.config_stack.removeWidget(w); w.deleteLater()
        self.task_list.takeItem(self.task_list.row(cur))
        self._update_summary()

    def _on_task_selected(self, row):
        if row < 0: self.config_stack.setCurrentWidget(self.empty_widget); return
        item = self.task_list.item(row)
        if item and item.text() in self.task_widgets:
            self.config_stack.setCurrentWidget(self.task_widgets[item.text()])

    def _update_summary(self):
        n = len(self.task_widgets)
        rows = sum(w.row_count.value() for w in self.task_widgets.values())
        self.lbl_summary.setText(t("tasks.summary", n=n, rows=f"{rows:,}"))

    def _confirm_tasks(self):
        if not self.task_widgets:
            QMessageBox.warning(self, t("common.warning"), t("tasks.no_tasks")); return
        plan = CampaignPlan(database_name=self.conn_config.database if self.conn_config else "")
        for w in self.task_widgets.values():
            plan.add_task(w.to_task_item())
        self.tasks_confirmed.emit(plan)

    # ── Template management ──

    def _refresh_template_list(self):
        self.tpl_combo.clear()
        _TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        for f in sorted(_TEMPLATE_DIR.glob("*.json")):
            self.tpl_combo.addItem(f.stem, str(f))

    def _save_template(self):
        if not self.task_widgets:
            QMessageBox.information(self, t("common.info"), t("tasks.tpl_no_tasks"))
            return
        name, ok = QInputDialog.getText(self, t("tasks.tpl_save_title"), t("tasks.tpl_save_prompt"))
        if not ok or not name.strip():
            return
        name = name.strip()
        template = {
            "name": name,
            "database_name": self.conn_config.database if self.conn_config else "",
            "tasks": [w.to_template_dict() for w in self.task_widgets.values()],
        }
        _TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        path = _TEMPLATE_DIR / f"{name}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        self._refresh_template_list()
        idx = self.tpl_combo.findText(name)
        if idx >= 0:
            self.tpl_combo.setCurrentIndex(idx)
        QMessageBox.information(self, t("common.info"), t("tasks.tpl_saved", name=name))

    def _load_template(self):
        if self.tpl_combo.currentIndex() < 0:
            QMessageBox.information(self, t("common.info"), t("tasks.tpl_no_select"))
            return
        path = Path(self.tpl_combo.currentData())
        try:
            with path.open("r", encoding="utf-8") as f:
                template = json.load(f)
        except Exception as exc:
            QMessageBox.warning(self, t("common.error"), t("tasks.tpl_load_err", err=str(exc)))
            return

        # Clear current tasks
        for name in list(self.task_widgets.keys()):
            w = self.task_widgets.pop(name)
            self.config_stack.removeWidget(w)
            w.deleteLater()
        self.task_list.clear()

        skipped = []
        for task_data in template.get("tasks", []):
            tbl_name = task_data.get("table_name", "")
            if not tbl_name:
                continue
            # Check if table exists in scan result
            if self.scan_result and tbl_name not in self.scan_result.tables:
                skipped.append(tbl_name)
                continue
            meta = self.scan_result.tables.get(tbl_name) if self.scan_result else None
            if meta is None:
                skipped.append(tbl_name)
                continue
            widget = TaskConfigWidget(meta)
            widget.load_from_template(task_data)
            self.task_widgets[tbl_name] = widget
            self.config_stack.addWidget(widget)
            item = QListWidgetItem(tbl_name)
            self.task_list.addItem(item)

        if self.task_list.count() > 0:
            self.task_list.setCurrentRow(0)
        self._update_summary()

        msg = t("tasks.tpl_loaded", name=template.get("name", path.stem), n=len(self.task_widgets))
        if skipped:
            msg += "\n" + t("tasks.tpl_table_skip", name=", ".join(skipped))
        QMessageBox.information(self, t("common.info"), msg)

    def _delete_template(self):
        if self.tpl_combo.currentIndex() < 0:
            QMessageBox.information(self, t("common.info"), t("tasks.tpl_no_select"))
            return
        name = self.tpl_combo.currentText()
        path = Path(self.tpl_combo.currentData())
        reply = QMessageBox.question(
            self, t("common.warning"), t("tasks.tpl_confirm_del", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            path.unlink(missing_ok=True)
            self._refresh_template_list()
            QMessageBox.information(self, t("common.info"), t("tasks.tpl_deleted", name=name))
