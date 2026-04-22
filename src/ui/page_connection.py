"""
Page 1: Database Connection — with persistent session and i18n.
V3.0: tkinter version.

Supports four dialects (see src.config.app_config.DIALECT_INFO):
  - mysql        — MySQL, MariaDB, Aurora MySQL, Percona
  - postgresql   — PostgreSQL, Aurora PG, TimescaleDB
  - oracle       — Oracle 12c+ (thin-mode oracledb, no Instant Client)
  - sqlite       — single-file / :memory:

The dropdown shows a human-readable label (from DIALECT_INFO) and an
info panel below it spells out which real engines that label covers,
which driver is loaded, and whether a bulk-load fast path exists.

This is so coworkers who never read the code know what each option
means without asking.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from src.config.app_config import (
    ConnectionConfig, SUPPORTED_DIALECTS, DIALECT_INFO,
    get_dialect_label, resolve_dialect_from_label,
    load_connection_profiles, save_connection_profiles, load_dotenv_file,
)
from src.ui.i18n import t


# Port values we treat as "auto-filled" defaults. If the user's port field
# currently holds one of these, switching dialect overwrites it with the new
# dialect's default. Any other port is assumed to be user-customized (e.g.
# 3307 for a Docker-mapped MySQL) and is left alone.
_KNOWN_DEFAULT_PORTS = {0, 3306, 5432, 1521}


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

        self._vars: dict[str, tk.StringVar] = {}
        self._form_labels: dict[str, ttk.Label] = {}
        self._form_entries: dict[str, ttk.Entry] = {}

        # ── Dialect dropdown ──
        # The combobox displays human-readable labels like
        # "MySQL / MariaDB / Aurora MySQL"; we translate back to the
        # internal dialect id (mysql/postgresql/oracle/sqlite) with
        # resolve_dialect_from_label() whenever we need it.
        self._lbl_dialect = ttk.Label(form_frame, text=t("conn.dialect"), width=14, anchor=tk.E)
        self._lbl_dialect.grid(row=0, column=0, padx=5, pady=3, sticky=tk.E)
        self._form_labels["dialect"] = self._lbl_dialect

        default_label = get_dialect_label("mysql")
        self._vars["dialect"] = tk.StringVar(value=default_label)
        dialect_values = [get_dialect_label(d) for d in SUPPORTED_DIALECTS]
        self._dialect_combo = ttk.Combobox(
            form_frame, textvariable=self._vars["dialect"],
            values=dialect_values, width=42, state="readonly",
        )
        self._dialect_combo.grid(row=0, column=1, columnspan=2, padx=5, pady=3, sticky=tk.W)
        self._dialect_combo.bind("<<ComboboxSelected>>", self._on_dialect_change)

        # ── "Supported engines" info panel ──
        # Placed between the dialect dropdown and the form fields so the
        # user picks the DB type → immediately sees what real engines
        # that option actually covers, and whether a bulk-load fast path
        # exists.
        info_frame = ttk.LabelFrame(form_frame, text=t("conn.engines_group"))
        info_frame.grid(row=1, column=0, columnspan=3, padx=5, pady=(4, 8), sticky=tk.EW)
        form_frame.columnconfigure(1, weight=1)
        self._info_frame = info_frame

        # Three rows inside the info panel, each a "label: value" pair.
        # Wraplength keeps the engines list readable in narrow windows.
        self._lbl_info_driver = ttk.Label(info_frame, text="", foreground="gray20",
                                          justify=tk.LEFT, wraplength=560)
        self._lbl_info_driver.grid(row=0, column=0, padx=8, pady=(4, 2), sticky=tk.W)

        self._lbl_info_engines = ttk.Label(info_frame, text="", foreground="gray20",
                                           justify=tk.LEFT, wraplength=560)
        self._lbl_info_engines.grid(row=1, column=0, padx=8, pady=2, sticky=tk.W)

        self._lbl_info_fastpath = ttk.Label(info_frame, text="", foreground="gray40",
                                            justify=tk.LEFT, wraplength=560)
        self._lbl_info_fastpath.grid(row=2, column=0, padx=8, pady=(2, 6), sticky=tk.W)

        # ── Data-entry fields ──
        # These are declared once but their enable/disable state and in a
        # couple of cases their labels are swapped on dialect change by
        # _on_dialect_change(). Keep the original row offsets here so the
        # existing grid layout stays aligned.
        fields = [
            ("host", t("conn.host"), "localhost"),
            ("port", t("conn.port"), "3306"),
            ("user", t("conn.user"), ""),
            ("password", t("conn.password"), ""),
            ("database", t("conn.database"), ""),
            ("charset", t("conn.charset"), "utf8mb4"),
        ]
        first_field_row = 2  # rows 0/1 are dialect dropdown + info panel
        for i, (key, label, default) in enumerate(fields):
            r = first_field_row + i
            lbl = ttk.Label(form_frame, text=label, width=14, anchor=tk.E)
            lbl.grid(row=r, column=0, padx=5, pady=3, sticky=tk.E)
            self._form_labels[key] = lbl

            var = tk.StringVar(value=default)
            self._vars[key] = var
            if key == "password":
                entry = ttk.Entry(form_frame, textvariable=var, show="*", width=40)
            else:
                entry = ttk.Entry(form_frame, textvariable=var, width=40)
            entry.grid(row=r, column=1, padx=5, pady=3, sticky=tk.W)
            self._form_entries[key] = entry

        # Browse button next to database — only useful for SQLite, hidden otherwise.
        database_row = first_field_row + 4  # host, port, user, password, database
        self._btn_browse = ttk.Button(
            form_frame, text=t("conn.browse"), command=self._browse_sqlite_file,
        )
        self._btn_browse.grid(row=database_row, column=2, padx=3, pady=3, sticky=tk.W)
        self._btn_browse.grid_remove()

        # Per-dialect hint line at the bottom of the form. Populated on
        # dialect change via DIALECT_INFO[*]["i18n_hint_key"].
        hint_row = first_field_row + 6
        self._lbl_hint = ttk.Label(form_frame, text="", foreground="#0b5394",
                                    justify=tk.LEFT, wraplength=560)
        self._lbl_hint.grid(row=hint_row, column=0, columnspan=3, padx=8, pady=(4, 4), sticky=tk.W)

        # Apply initial dialect-driven state (info panel, enable/disable, hint).
        self._refresh_for_dialect()

        # ── Action buttons ──
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

    # ── i18n ──

    def retranslate(self):
        self._profile_frame.config(text=t("conn.profile_group"))
        self._lbl_profile.config(text=t("conn.profile_label"))
        self._btn_save_profile.config(text=t("conn.save_profile"))
        self._btn_delete_profile.config(text=t("conn.delete_profile"))
        self._btn_load_env.config(text=t("conn.load_env"))
        self._form_frame.config(text=t("conn.settings_group"))
        self._info_frame.config(text=t("conn.engines_group"))
        # Plain per-field labels. The "database" label is dialect-dependent
        # and is re-set inside _refresh_for_dialect() below.
        static_label_keys = {
            "dialect":  "conn.dialect",
            "host":     "conn.host",
            "port":     "conn.port",
            "user":     "conn.user",
            "password": "conn.password",
            "charset":  "conn.charset",
        }
        for key, i18n_key in static_label_keys.items():
            self._form_labels[key].config(text=t(i18n_key))
        self._btn_browse.config(text=t("conn.browse"))
        self._btn_test.config(text=t("conn.test"))
        self._btn_connect.config(text=t("conn.connect"))
        self._btn_disconnect.config(text=t("conn.disconnect"))
        self._btn_reconnect.config(text=t("conn.reconnect"))
        # Refresh info panel + dialect-dependent label/hint for the
        # currently-selected dialect.
        self._refresh_for_dialect()

    # ── Dialect helpers ──

    def _current_dialect_id(self) -> str:
        """Resolve the combobox's displayed label back to a dialect id."""
        return resolve_dialect_from_label(self._vars["dialect"].get())

    def _set_dialect_id(self, dialect_id: str) -> None:
        """Set the dropdown to the label for a given dialect id."""
        self._vars["dialect"].set(get_dialect_label(dialect_id))

    def _refresh_for_dialect(self, previous_dialect: str | None = None) -> None:
        """
        Rebuild every dialect-dependent piece of the UI.

        Called on init, on combobox change, on profile load, and on language
        retranslate. `previous_dialect` is used to decide whether to auto-fill
        the port (we only overwrite a port that looks like it was itself
        auto-filled, so a user-customised port is preserved).
        """
        dialect = self._current_dialect_id()
        info = DIALECT_INFO.get(dialect, {})

        # ── Info panel ──
        driver_txt = f'{t("conn.engines_driver")} {info.get("driver", "-")}'
        engines = info.get("engines") or []
        engines_txt = t("conn.engines_supports") + "\n" + "\n".join(
            f"    • {e}" for e in engines
        )
        fast_txt = f'{t("conn.engines_fastpath")} {info.get("fast_path", "-")}'
        self._lbl_info_driver.config(text=driver_txt)
        self._lbl_info_engines.config(text=engines_txt)
        self._lbl_info_fastpath.config(text=fast_txt)

        # ── Field enable/disable based on needs_network ──
        needs_net = bool(info.get("needs_network", True))
        net_fields = ("host", "port", "user", "password")
        net_state = tk.NORMAL if needs_net else tk.DISABLED
        for key in net_fields:
            entry = self._form_entries.get(key)
            if entry is not None:
                entry.config(state=net_state)

        # Charset is MySQL-specific. Disable it for everything else so users
        # don't think they need to fill it in.
        charset_entry = self._form_entries.get("charset")
        if charset_entry is not None:
            charset_entry.config(state=tk.NORMAL if dialect == "mysql" else tk.DISABLED)

        # ── "Database" field: label text depends on dialect ──
        database_label = self._form_labels.get("database")
        if database_label is not None:
            if dialect == "oracle":
                database_label.config(text=t("conn.database_service"))
            elif dialect == "sqlite":
                database_label.config(text=t("conn.database_file"))
            else:
                database_label.config(text=t("conn.database"))

        # ── Browse button: only for SQLite ──
        if dialect == "sqlite":
            self._btn_browse.grid()
        else:
            self._btn_browse.grid_remove()

        # ── Hint line ──
        hint_key = info.get("i18n_hint_key") or ""
        hint_text = t(hint_key) if hint_key else ""
        if hint_text:
            self._lbl_hint.config(text=hint_text)
            self._lbl_hint.grid()
        else:
            self._lbl_hint.config(text="")
            self._lbl_hint.grid_remove()

        # ── Port auto-fill ──
        # Only overwrite the port if the current value looks like a default
        # from some dialect (3306/5432/1521/0/empty). Anything else is
        # treated as intentional user input and left alone.
        port_var = self._vars.get("port")
        new_port = int(info.get("default_port") or 0)
        if port_var is not None:
            raw = port_var.get().strip()
            current_int: int | None
            if raw == "":
                current_int = 0
            else:
                try:
                    current_int = int(raw)
                except ValueError:
                    current_int = None
            should_replace = current_int in _KNOWN_DEFAULT_PORTS
            if should_replace:
                port_var.set(str(new_port) if new_port else "")

    def _on_dialect_change(self, event=None):
        """Called when the user picks a new dialect from the dropdown."""
        self._refresh_for_dialect()

    # ── Config <-> UI ──

    def _get_config(self) -> ConnectionConfig:
        dialect = self._current_dialect_id()
        if dialect == "sqlite":
            # For SQLite we don't care about host/port/user/password/charset;
            # pass empty values so they don't confuse display_safe().
            return ConnectionConfig(
                dialect="sqlite",
                host="", port=0, user="", password="",
                database=self._vars["database"].get().strip(),
                charset="",
            )

        # Network dialects (mysql/postgresql/oracle) share the same form.
        # We zero-out charset for non-mysql because it's MySQL-specific and
        # the field is disabled for those dialects anyway.
        info = DIALECT_INFO.get(dialect, {})
        default_port = int(info.get("default_port") or 0)
        try:
            port_int = int(self._vars["port"].get() or default_port or 0)
        except ValueError:
            port_int = default_port
        charset = ""
        if dialect == "mysql":
            charset = self._vars["charset"].get().strip() or "utf8mb4"
        return ConnectionConfig(
            dialect=dialect,
            host=self._vars["host"].get().strip(),
            port=port_int,
            user=self._vars["user"].get().strip(),
            password=self._vars["password"].get(),
            database=self._vars["database"].get().strip(),
            charset=charset,
        )

    def _set_config(self, config: ConnectionConfig):
        self._set_dialect_id((config.dialect or "mysql").lower())
        self._vars["host"].set(config.host)
        self._vars["port"].set(str(config.port))
        self._vars["user"].set(config.user)
        self._vars["password"].set(config.password)
        self._vars["database"].set(config.database)
        self._vars["charset"].set(config.charset)
        # Apply field enable/disable, label swaps, info panel, and hint
        # for the newly-loaded dialect. Don't let port auto-fill overwrite
        # the value we just set: _KNOWN_DEFAULT_PORTS logic protects it
        # unless it happened to land on one of those exact values.
        self._refresh_for_dialect()

    # ── SQLite-specific ──

    def _browse_sqlite_file(self):
        """Pick an existing SQLite file, or let the user type a new path."""
        path = filedialog.askopenfilename(
            title=t("conn.dialect"),
            filetypes=[("SQLite database", "*.db *.sqlite *.sqlite3"), ("All files", "*.*")],
        )
        if path:
            self._vars["database"].set(path)

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
