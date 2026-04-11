"""
Page 1: Database Connection — with persistent session and i18n.
V3.0: tkinter version.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from src.config.app_config import (
    ConnectionConfig, load_connection_profiles, save_connection_profiles,
    load_dotenv_file,
)
from src.ui.i18n import t


class ConnectionPage(ttk.Frame):
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.on_connection_ready = None  # callback(config)

        self._init_ui()
        self._load_profiles()

    @property
    def _session(self):
        return self.main_window.session

    def _init_ui(self):
        # ── Profile selector ──
        profile_frame = ttk.LabelFrame(self, text=t("conn.profile_group"))
        profile_frame.pack(fill=tk.X, padx=10, pady=5)
        self._profile_frame = profile_frame

        row = ttk.Frame(profile_frame)
        row.pack(fill=tk.X, padx=5, pady=5)

        self._lbl_profile = ttk.Label(row, text=t("conn.profile_label"))
        self._lbl_profile.pack(side=tk.LEFT)

        self._profile_var = tk.StringVar()
        self._profile_combo = ttk.Combobox(row, textvariable=self._profile_var, width=25, state="readonly")
        self._profile_combo.pack(side=tk.LEFT, padx=5)
        self._profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)

        self._btn_save_profile = ttk.Button(row, text=t("conn.save_profile"), command=self._save_profile)
        self._btn_save_profile.pack(side=tk.LEFT, padx=2)
        self._btn_delete_profile = ttk.Button(row, text=t("conn.delete_profile"), command=self._delete_profile)
        self._btn_delete_profile.pack(side=tk.LEFT, padx=2)
        self._btn_load_env = ttk.Button(row, text=t("conn.load_env"), command=self._load_from_env)
        self._btn_load_env.pack(side=tk.LEFT, padx=2)

        # ── Connection form ──
        form_frame = ttk.LabelFrame(self, text=t("conn.settings_group"))
        form_frame.pack(fill=tk.X, padx=10, pady=5)
        self._form_frame = form_frame

        self._vars = {}
        fields = [
            ("host", t("conn.host"), "localhost"),
            ("port", t("conn.port"), "3306"),
            ("user", t("conn.user"), ""),
            ("password", t("conn.password"), ""),
            ("database", t("conn.database"), ""),
            ("charset", t("conn.charset"), "utf8mb4"),
        ]
        self._form_labels = {}
        for i, (key, label, default) in enumerate(fields):
            lbl = ttk.Label(form_frame, text=label, width=12, anchor=tk.E)
            lbl.grid(row=i, column=0, padx=5, pady=3, sticky=tk.E)
            self._form_labels[key] = lbl

            var = tk.StringVar(value=default)
            self._vars[key] = var
            if key == "password":
                entry = ttk.Entry(form_frame, textvariable=var, show="*", width=40)
            else:
                entry = ttk.Entry(form_frame, textvariable=var, width=40)
            entry.grid(row=i, column=1, padx=5, pady=3, sticky=tk.W)

        # ── Buttons ──
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        self._btn_test = ttk.Button(btn_frame, text=t("conn.test"), command=self._test_connection)
        self._btn_test.pack(side=tk.LEFT, padx=3)
        self._btn_connect = ttk.Button(btn_frame, text=t("conn.connect"), command=self._connect_and_continue)
        self._btn_connect.pack(side=tk.LEFT, padx=3)
        self._btn_disconnect = ttk.Button(btn_frame, text=t("conn.disconnect"), command=self._disconnect, state=tk.DISABLED)
        self._btn_disconnect.pack(side=tk.LEFT, padx=3)
        self._btn_reconnect = ttk.Button(btn_frame, text=t("conn.reconnect"), command=self._reconnect, state=tk.DISABLED)
        self._btn_reconnect.pack(side=tk.LEFT, padx=3)

        self._lbl_status = ttk.Label(btn_frame, text="", foreground="gray")
        self._lbl_status.pack(side=tk.RIGHT, padx=10)

    def retranslate(self):
        self._profile_frame.config(text=t("conn.profile_group"))
        self._lbl_profile.config(text=t("conn.profile_label"))
        self._btn_save_profile.config(text=t("conn.save_profile"))
        self._btn_delete_profile.config(text=t("conn.delete_profile"))
        self._btn_load_env.config(text=t("conn.load_env"))
        self._form_frame.config(text=t("conn.settings_group"))
        label_keys = {"host": "conn.host", "port": "conn.port", "user": "conn.user",
                      "password": "conn.password", "database": "conn.database", "charset": "conn.charset"}
        for key, i18n_key in label_keys.items():
            self._form_labels[key].config(text=t(i18n_key))
        self._btn_test.config(text=t("conn.test"))
        self._btn_connect.config(text=t("conn.connect"))
        self._btn_disconnect.config(text=t("conn.disconnect"))
        self._btn_reconnect.config(text=t("conn.reconnect"))

    # ── Helpers ──

    def _get_config(self) -> ConnectionConfig:
        return ConnectionConfig(
            host=self._vars["host"].get().strip(),
            port=int(self._vars["port"].get() or 3306),
            user=self._vars["user"].get().strip(),
            password=self._vars["password"].get(),
            database=self._vars["database"].get().strip(),
            charset=self._vars["charset"].get().strip() or "utf8mb4",
        )

    def _set_config(self, config: ConnectionConfig):
        self._vars["host"].set(config.host)
        self._vars["port"].set(str(config.port))
        self._vars["user"].set(config.user)
        self._vars["password"].set(config.password)
        self._vars["database"].set(config.database)
        self._vars["charset"].set(config.charset)

    # ── Actions ──

    def _test_connection(self):
        config = self._get_config()
        from src.db.connection import DatabaseManager
        db = DatabaseManager(config=config)
        if db.connect():
            n = len(db.show_tables())
            db.disconnect()
            self._lbl_status.config(text=t("conn.status_ok", n=n), foreground="green")
        else:
            self._lbl_status.config(text=t("conn.status_fail"), foreground="red")

    def _connect_and_continue(self):
        config = self._get_config()
        if not config.database:
            messagebox.showwarning(t("common.error"), t("conn.db_required"))
            return
        session = self._session
        if session.connect(config):
            self._lbl_status.config(text=t("conn.status_active", info=config.display_safe()), foreground="green")
            self._btn_disconnect.config(state=tk.NORMAL)
            self._btn_reconnect.config(state=tk.NORMAL)
            if self.on_connection_ready:
                self.on_connection_ready(config)
        else:
            messagebox.showerror(t("common.error"), t("conn.connect_error"))

    def _disconnect(self):
        self._session.disconnect()
        self._btn_disconnect.config(state=tk.DISABLED)
        self._lbl_status.config(text=t("conn.status_disconnected"), foreground="gray")

    def _reconnect(self):
        if self._session.reconnect():
            self._lbl_status.config(text=t("conn.status_active", info=self._session.status_text), foreground="green")
        else:
            self._lbl_status.config(text=t("conn.status_fail"), foreground="red")

    # ── Profile management ──

    def _load_profiles(self):
        names = ["(new)"] + sorted(load_connection_profiles().keys())
        self._profile_combo["values"] = names
        if names:
            self._profile_combo.current(0)

    def _on_profile_selected(self, event=None):
        name = self._profile_var.get()
        if name == "(new)" or not name:
            return
        profiles = load_connection_profiles()
        if name in profiles:
            self._set_config(profiles[name])

    def _save_profile(self):
        name = self._profile_var.get()
        if name == "(new)":
            name = self._vars["database"].get().strip() or "default"
        profiles = load_connection_profiles()
        profiles[name] = self._get_config()
        save_connection_profiles(profiles)
        self._load_profiles()
        # Select saved profile
        values = list(self._profile_combo["values"])
        if name in values:
            self._profile_combo.current(values.index(name))

    def _delete_profile(self):
        name = self._profile_var.get()
        if name == "(new)":
            return
        profiles = load_connection_profiles()
        profiles.pop(name, None)
        save_connection_profiles(profiles)
        self._load_profiles()

    def _load_from_env(self):
        load_dotenv_file()
        self._set_config(ConnectionConfig.from_env())
        self._lbl_status.config(text=t("conn.loaded_env"), foreground="blue")
