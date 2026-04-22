"""
Page 3: Multi-Table Task Configuration — i18n + template save/load.
V3.0: tkinter version.
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path

from src.config.app_config import ConnectionConfig
from src.metadata.models import DatabaseScanResult, TableMetadata
from src.plan.models import CampaignPlan, TaskItem
from src.strategy.pk_planner import PKRangeConfig
from src.ui.i18n import t
from src.utils.runtime_paths import get_app_root

_PROJECT_ROOT = get_app_root()
_TEMPLATE_DIR = _PROJECT_ROOT / "task_templates"


class TaskConfigFrame(ttk.Frame):
    """Per-table configuration frame."""

    def __init__(self, parent, table_meta: TableMetadata):
        super().__init__(parent)
        self.table_meta = table_meta
        self._vars: dict[str, tk.Variable] = {}
        self._labels: dict[str, ttk.Label] = {}
        self._init_ui()

    def _init_ui(self):
        info = (f"Table: {self.table_meta.table_name}  |  "
                f"Rows: {self.table_meta.row_count}  |  "
                f"PK: {self.table_meta.pk_display}")
        lbl_info = ttk.Label(self, text=info, font=("", 10, "bold"))
        lbl_info.grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)

        fields = [
            ("sample_method", t("tasks.sample_method"), "combo", ["first_row", "pk_lookup", "where_clause"]),
            ("sample_pk_value", t("tasks.sample_pk"), "entry", ""),
            ("sample_where", t("tasks.sample_where"), "entry", ""),
            ("pk_mode", t("tasks.pk_mode"), "combo", ["auto_increment_from_max", "fixed_start", "explicit_range"]),
            ("pk_start", t("tasks.pk_start"), "entry", ""),
            ("pk_end", t("tasks.pk_end"), "entry", ""),
            ("pk_prefix", t("tasks.pk_prefix"), "entry", ""),
            ("zero_pad", t("tasks.zero_pad"), "spin", (0, 20, 0)),
            ("row_count", t("tasks.row_count"), "spin", (1, 10_000_000, 1000)),
            ("batch_size", t("tasks.batch_size"), "spin", (100, 10000, 1000)),
            ("mode", t("tasks.mode"), "combo", ["insert", "dry-run", "export"]),
            ("marker_column", t("tasks.marker_col"), "combo",
             [t("common.none")] + list(self.table_meta.marker_columns)),
            ("marker_value", t("tasks.marker_val"), "entry", ""),
        ]

        for i, (key, label, wtype, default) in enumerate(fields, start=1):
            lbl = ttk.Label(self, text=label, anchor=tk.E)
            lbl.grid(row=i, column=0, padx=5, pady=2, sticky=tk.E)
            self._labels[key] = lbl

            if wtype == "combo":
                var = tk.StringVar(value=default[0] if default else "")
                combo = ttk.Combobox(self, textvariable=var, values=default, state="readonly", width=30)
                combo.grid(row=i, column=1, padx=5, pady=2, sticky=tk.W)
                self._vars[key] = var
            elif wtype == "spin":
                lo, hi, init = default
                var = tk.IntVar(value=init)
                spin = ttk.Spinbox(self, from_=lo, to=hi, textvariable=var, width=15)
                spin.grid(row=i, column=1, padx=5, pady=2, sticky=tk.W)
                self._vars[key] = var
            else:  # entry
                var = tk.StringVar(value=default)
                entry = ttk.Entry(self, textvariable=var, width=35)
                entry.grid(row=i, column=1, padx=5, pady=2, sticky=tk.W)
                self._vars[key] = var

    def retranslate(self):
        keys_map = {
            "sample_method": "tasks.sample_method", "sample_pk_value": "tasks.sample_pk",
            "sample_where": "tasks.sample_where", "pk_mode": "tasks.pk_mode",
            "pk_start": "tasks.pk_start", "pk_end": "tasks.pk_end",
            "pk_prefix": "tasks.pk_prefix", "zero_pad": "tasks.zero_pad",
            "row_count": "tasks.row_count", "batch_size": "tasks.batch_size",
            "mode": "tasks.mode", "marker_column": "tasks.marker_col",
            "marker_value": "tasks.marker_val",
        }
        for key, i18n_key in keys_map.items():
            if key in self._labels:
                self._labels[key].config(text=t(i18n_key))

    def to_task_item(self) -> TaskItem:
        pk_start = pk_end = None
        try:
            v = self._vars["pk_start"].get()
            if v:
                pk_start = int(v)
        except (ValueError, tk.TclError):
            pass
        try:
            v = self._vars["pk_end"].get()
            if v:
                pk_end = int(v)
        except (ValueError, tk.TclError):
            pass
        marker_col = self._vars["marker_column"].get()
        if marker_col == t("common.none"):
            marker_col = ""
        return TaskItem(
            table_name=self.table_meta.table_name,
            row_count=self._vars["row_count"].get(),
            batch_size=self._vars["batch_size"].get(),
            mode=self._vars["mode"].get(),
            sample_pk_value=self._vars["sample_pk_value"].get().strip(),
            sample_where=self._vars["sample_where"].get().strip(),
            sample_method=self._vars["sample_method"].get(),
            pk_config=PKRangeConfig(
                mode=self._vars["pk_mode"].get(),
                start_value=pk_start, end_value=pk_end,
                prefix=self._vars["pk_prefix"].get().strip(),
                zero_pad_width=self._vars["zero_pad"].get(),
            ),
            marker_column=marker_col,
            marker_value=self._vars["marker_value"].get().strip(),
        )

    def to_template_dict(self) -> dict:
        return {
            "table_name": self.table_meta.table_name,
            "sample_method": self._vars["sample_method"].get(),
            "sample_pk_value": self._vars["sample_pk_value"].get().strip(),
            "sample_where": self._vars["sample_where"].get().strip(),
            "pk_mode": self._vars["pk_mode"].get(),
            "pk_start": self._vars["pk_start"].get().strip() if isinstance(self._vars["pk_start"], tk.StringVar) else "",
            "pk_end": self._vars["pk_end"].get().strip() if isinstance(self._vars["pk_end"], tk.StringVar) else "",
            "pk_prefix": self._vars["pk_prefix"].get().strip(),
            "pk_pad_width": self._vars["zero_pad"].get(),
            "row_count": self._vars["row_count"].get(),
            "batch_size": self._vars["batch_size"].get(),
            "mode": self._vars["mode"].get(),
            "marker_column": self._vars["marker_column"].get(),
            "marker_value": self._vars["marker_value"].get().strip(),
        }

    def load_from_template(self, data: dict) -> None:
        def _set_var(key, value):
            if key in self._vars:
                try:
                    self._vars[key].set(value)
                except (tk.TclError, ValueError):
                    pass

        _set_var("sample_method", data.get("sample_method", "first_row"))
        _set_var("sample_pk_value", data.get("sample_pk_value", ""))
        _set_var("sample_where", data.get("sample_where", ""))
        _set_var("pk_mode", data.get("pk_mode", "auto_increment_from_max"))
        _set_var("pk_start", data.get("pk_start", ""))
        _set_var("pk_end", data.get("pk_end", ""))
        _set_var("pk_prefix", data.get("pk_prefix", ""))
        _set_var("zero_pad", data.get("pk_pad_width", 0))
        _set_var("row_count", data.get("row_count", 1000))
        _set_var("batch_size", data.get("batch_size", 1000))
        _set_var("mode", data.get("mode", "insert"))
        _set_var("marker_column", data.get("marker_column", t("common.none")))
        _set_var("marker_value", data.get("marker_value", ""))


class TasksPage(ttk.Frame):
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.scan_result: DatabaseScanResult | None = None
        self.conn_config: ConnectionConfig | None = None
        self.task_widgets: dict[str, TaskConfigFrame] = {}
        self.on_tasks_confirmed = None  # callback(plan)
        self._init_ui()

    def _init_ui(self):
        # ── Top: table selector ──
        self._top_group = ttk.LabelFrame(self, text=t("tasks.add_tables"))
        self._top_group.pack(fill=tk.X, padx=10, pady=5)

        row = ttk.Frame(self._top_group)
        row.pack(fill=tk.X, padx=5, pady=5)
        self._lbl_table = ttk.Label(row, text=t("tasks.table_label"))
        self._lbl_table.pack(side=tk.LEFT)
        self._table_var = tk.StringVar()
        self._table_combo = ttk.Combobox(row, textvariable=self._table_var, width=35, state="readonly")
        self._table_combo.pack(side=tk.LEFT, padx=5)
        self._btn_add = ttk.Button(row, text=t("tasks.btn_add"), command=self._add_table)
        self._btn_add.pack(side=tk.LEFT, padx=3)
        self._btn_remove = ttk.Button(row, text=t("tasks.btn_remove"), command=self._remove_table)
        self._btn_remove.pack(side=tk.LEFT, padx=3)

        # ── Middle: task list + config panel ──
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Left: task listbox
        list_frame = ttk.Frame(paned)
        # Keep the selected task highlighted while focus moves into the
        # configuration widgets on the right side.
        self._task_listbox = tk.Listbox(list_frame, width=30, exportselection=False)
        self._task_listbox.pack(fill=tk.BOTH, expand=True)
        self._task_listbox.bind("<<ListboxSelect>>", self._on_task_selected)
        paned.add(list_frame, weight=1)

        # Right: config area (scrollable)
        self._config_container = ttk.Frame(paned)
        self._current_config: TaskConfigFrame | None = None
        self._empty_label = ttk.Label(self._config_container, text=t("tasks.select_hint"), anchor=tk.CENTER)
        self._empty_label.pack(fill=tk.BOTH, expand=True)
        paned.add(self._config_container, weight=3)

        # ── Template section ──
        self._tpl_group = ttk.LabelFrame(self, text=t("tasks.tpl_group"))
        self._tpl_group.pack(fill=tk.X, padx=10, pady=5)
        tpl_row = ttk.Frame(self._tpl_group)
        tpl_row.pack(fill=tk.X, padx=5, pady=5)
        self._lbl_tpl = ttk.Label(tpl_row, text=t("tasks.tpl_label"))
        self._lbl_tpl.pack(side=tk.LEFT)
        self._tpl_var = tk.StringVar()
        self._tpl_combo = ttk.Combobox(tpl_row, textvariable=self._tpl_var, width=25, state="readonly")
        self._tpl_combo.pack(side=tk.LEFT, padx=5)
        self._btn_save_tpl = ttk.Button(tpl_row, text=t("tasks.btn_save_tpl"), command=self._save_template)
        self._btn_save_tpl.pack(side=tk.LEFT, padx=2)
        self._btn_load_tpl = ttk.Button(tpl_row, text=t("tasks.btn_load_tpl"), command=self._load_template)
        self._btn_load_tpl.pack(side=tk.LEFT, padx=2)
        self._btn_delete_tpl = ttk.Button(tpl_row, text=t("tasks.btn_delete_tpl"), command=self._delete_template)
        self._btn_delete_tpl.pack(side=tk.LEFT, padx=2)
        self._refresh_template_list()

        # ── Bottom: confirm ──
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=10, pady=5)
        self._btn_confirm = ttk.Button(bottom, text=t("tasks.confirm"), command=self._confirm_tasks)
        self._btn_confirm.pack(side=tk.LEFT, padx=3)
        self._lbl_summary = ttk.Label(bottom, text="")
        self._lbl_summary.pack(side=tk.LEFT, padx=10)

    def retranslate(self):
        self._top_group.config(text=t("tasks.add_tables"))
        self._lbl_table.config(text=t("tasks.table_label"))
        self._btn_add.config(text=t("tasks.btn_add"))
        self._btn_remove.config(text=t("tasks.btn_remove"))
        self._empty_label.config(text=t("tasks.select_hint"))
        self._btn_confirm.config(text=t("tasks.confirm"))
        self._tpl_group.config(text=t("tasks.tpl_group"))
        self._lbl_tpl.config(text=t("tasks.tpl_label"))
        self._btn_save_tpl.config(text=t("tasks.btn_save_tpl"))
        self._btn_load_tpl.config(text=t("tasks.btn_load_tpl"))
        self._btn_delete_tpl.config(text=t("tasks.btn_delete_tpl"))
        for w in self.task_widgets.values():
            w.retranslate()

    def set_scan_result(self, scan_result, conn_config):
        self.scan_result = scan_result
        self.conn_config = conn_config
        self._table_combo["values"] = list(scan_result.table_names)

    def _add_table(self):
        name = self._table_var.get()
        if not name or not self.scan_result:
            return
        if name in self.task_widgets:
            messagebox.showinfo(t("common.info"), t("tasks.already_added", name=name))
            return
        meta = self.scan_result.tables.get(name)
        if not meta:
            return
        widget = TaskConfigFrame(self._config_container, meta)
        self.task_widgets[name] = widget
        self._task_listbox.insert(tk.END, name)
        self._task_listbox.selection_clear(0, tk.END)
        self._task_listbox.selection_set(tk.END)
        self._show_config(name)
        self._update_summary()

    def _remove_table(self):
        sel = self._task_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        name = self._task_listbox.get(idx)
        if name in self.task_widgets:
            w = self.task_widgets.pop(name)
            w.destroy()
        self._task_listbox.delete(idx)
        self._show_empty()
        self._update_summary()

    def _on_task_selected(self, event=None):
        sel = self._task_listbox.curselection()
        if not sel:
            self._show_empty()
            return
        name = self._task_listbox.get(sel[0])
        self._show_config(name)

    def _show_config(self, name: str):
        if self._current_config:
            self._current_config.pack_forget()
        self._empty_label.pack_forget()
        if name in self.task_widgets:
            self._current_config = self.task_widgets[name]
            self._current_config.pack(fill=tk.BOTH, expand=True)

    def _show_empty(self):
        if self._current_config:
            self._current_config.pack_forget()
            self._current_config = None
        self._empty_label.pack(fill=tk.BOTH, expand=True)

    def _update_summary(self):
        n = len(self.task_widgets)
        rows = sum(w._vars["row_count"].get() for w in self.task_widgets.values())
        self._lbl_summary.config(text=t("tasks.summary", n=n, rows=f"{rows:,}"))

    def _confirm_tasks(self):
        if not self.task_widgets:
            messagebox.showwarning(t("common.warning"), t("tasks.no_tasks"))
            return
        plan = CampaignPlan(database_name=self.conn_config.database if self.conn_config else "")
        for w in self.task_widgets.values():
            plan.add_task(w.to_task_item())
        if self.on_tasks_confirmed:
            self.on_tasks_confirmed(plan)

    # ── Template management ──

    def _refresh_template_list(self):
        _TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        names = [f.stem for f in sorted(_TEMPLATE_DIR.glob("*.json"))]
        self._tpl_combo["values"] = names

    def _save_template(self):
        if not self.task_widgets:
            messagebox.showinfo(t("common.info"), t("tasks.tpl_no_tasks"))
            return
        name = simpledialog.askstring(t("tasks.tpl_save_title"), t("tasks.tpl_save_prompt"),
                                      parent=self)
        if not name or not name.strip():
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
        messagebox.showinfo(t("common.info"), t("tasks.tpl_saved", name=name))

    def _load_template(self):
        name = self._tpl_var.get()
        if not name:
            messagebox.showinfo(t("common.info"), t("tasks.tpl_no_select"))
            return
        path = _TEMPLATE_DIR / f"{name}.json"
        try:
            with path.open("r", encoding="utf-8") as f:
                template = json.load(f)
        except Exception as exc:
            messagebox.showwarning(t("common.error"), t("tasks.tpl_load_err", err=str(exc)))
            return

        # Clear current tasks
        for tbl_name in list(self.task_widgets.keys()):
            w = self.task_widgets.pop(tbl_name)
            w.destroy()
        self._task_listbox.delete(0, tk.END)

        skipped = []
        for task_data in template.get("tasks", []):
            tbl_name = task_data.get("table_name", "")
            if not tbl_name:
                continue
            if self.scan_result and tbl_name not in self.scan_result.tables:
                skipped.append(tbl_name)
                continue
            meta = self.scan_result.tables.get(tbl_name) if self.scan_result else None
            if meta is None:
                skipped.append(tbl_name)
                continue
            widget = TaskConfigFrame(self._config_container, meta)
            widget.load_from_template(task_data)
            self.task_widgets[tbl_name] = widget
            self._task_listbox.insert(tk.END, tbl_name)

        if self._task_listbox.size() > 0:
            self._task_listbox.selection_set(0)
            self._show_config(self._task_listbox.get(0))
        self._update_summary()

        msg = t("tasks.tpl_loaded", name=template.get("name", name), n=len(self.task_widgets))
        if skipped:
            msg += "\n" + t("tasks.tpl_table_skip", name=", ".join(skipped))
        messagebox.showinfo(t("common.info"), msg)

    def _delete_template(self):
        name = self._tpl_var.get()
        if not name:
            messagebox.showinfo(t("common.info"), t("tasks.tpl_no_select"))
            return
        if not messagebox.askyesno(t("common.warning"), t("tasks.tpl_confirm_del", name=name)):
            return
        path = _TEMPLATE_DIR / f"{name}.json"
        path.unlink(missing_ok=True)
        self._refresh_template_list()
        messagebox.showinfo(t("common.info"), t("tasks.tpl_deleted", name=name))

