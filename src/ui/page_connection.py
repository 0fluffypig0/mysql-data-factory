"""
Page 1: Database Connection — with persistent session and i18n.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QSpinBox, QPushButton, QComboBox, QLabel, QMessageBox,
)

from src.config.app_config import (
    ConnectionConfig, load_connection_profiles, save_connection_profiles,
    load_dotenv_file,
)
from src.ui.i18n import t
from src.ui.session import SessionManager


class ConnectionPage(QWidget):
    connection_ready = Signal(object)  # emits ConnectionConfig

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._load_profiles()

    @property
    def _session(self) -> SessionManager:
        return self.window().session

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # ── Profile selector ──
        self.profile_group = QGroupBox()
        profile_layout = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.currentTextChanged.connect(self._on_profile_selected)
        self.lbl_profile = QLabel()
        profile_layout.addWidget(self.lbl_profile)
        profile_layout.addWidget(self.profile_combo)

        self.btn_save_profile = QPushButton()
        self.btn_save_profile.clicked.connect(self._save_profile)
        self.btn_delete_profile = QPushButton()
        self.btn_delete_profile.clicked.connect(self._delete_profile)
        self.btn_load_env = QPushButton()
        self.btn_load_env.clicked.connect(self._load_from_env)
        profile_layout.addWidget(self.btn_save_profile)
        profile_layout.addWidget(self.btn_delete_profile)
        profile_layout.addWidget(self.btn_load_env)
        profile_layout.addStretch()
        self.profile_group.setLayout(profile_layout)
        layout.addWidget(self.profile_group)

        # ── Connection form ──
        self.form_group = QGroupBox()
        form_layout = QFormLayout()

        self.input_host = QLineEdit("localhost")
        self.input_port = QSpinBox(); self.input_port.setRange(1, 65535); self.input_port.setValue(3306)
        self.input_user = QLineEdit()
        self.input_password = QLineEdit(); self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_database = QLineEdit()
        self.input_charset = QLineEdit("utf8mb4")

        self.form_labels = {}
        for key, widget in [("conn.host", self.input_host), ("conn.port", self.input_port),
                            ("conn.user", self.input_user), ("conn.password", self.input_password),
                            ("conn.database", self.input_database), ("conn.charset", self.input_charset)]:
            lbl = QLabel()
            self.form_labels[key] = lbl
            form_layout.addRow(lbl, widget)

        self.form_group.setLayout(form_layout)
        layout.addWidget(self.form_group)

        # ── Buttons ──
        btn_layout = QHBoxLayout()
        self.btn_test = QPushButton()
        self.btn_test.clicked.connect(self._test_connection)
        self.btn_connect = QPushButton()
        self.btn_connect.clicked.connect(self._connect_and_continue)
        self.btn_connect.setStyleSheet("font-weight: bold;")
        self.btn_disconnect = QPushButton()
        self.btn_disconnect.clicked.connect(self._disconnect)
        self.btn_disconnect.setEnabled(False)
        self.btn_reconnect = QPushButton()
        self.btn_reconnect.clicked.connect(self._reconnect)
        self.btn_reconnect.setEnabled(False)

        self.lbl_status = QLabel()
        btn_layout.addWidget(self.btn_test)
        btn_layout.addWidget(self.btn_connect)
        btn_layout.addWidget(self.btn_disconnect)
        btn_layout.addWidget(self.btn_reconnect)
        btn_layout.addStretch()
        btn_layout.addWidget(self.lbl_status)
        layout.addLayout(btn_layout)
        layout.addStretch()

        self.retranslate()

    def retranslate(self):
        self.profile_group.setTitle(t("conn.profile_group"))
        self.lbl_profile.setText(t("conn.profile_label"))
        self.btn_save_profile.setText(t("conn.save_profile"))
        self.btn_delete_profile.setText(t("conn.delete_profile"))
        self.btn_load_env.setText(t("conn.load_env"))
        self.form_group.setTitle(t("conn.settings_group"))
        for key, lbl in self.form_labels.items():
            lbl.setText(t(key))
        self.btn_test.setText(t("conn.test"))
        self.btn_connect.setText(t("conn.connect"))
        self.btn_disconnect.setText(t("conn.disconnect"))
        self.btn_reconnect.setText(t("conn.reconnect"))

    # ── Helpers ──

    def _get_config(self) -> ConnectionConfig:
        return ConnectionConfig(
            host=self.input_host.text().strip(),
            port=self.input_port.value(),
            user=self.input_user.text().strip(),
            password=self.input_password.text(),
            database=self.input_database.text().strip(),
            charset=self.input_charset.text().strip() or "utf8mb4",
        )

    def _set_config(self, config: ConnectionConfig):
        self.input_host.setText(config.host)
        self.input_port.setValue(config.port)
        self.input_user.setText(config.user)
        self.input_password.setText(config.password)
        self.input_database.setText(config.database)
        self.input_charset.setText(config.charset)

    # ── Actions ──

    def _test_connection(self):
        """Test connection WITHOUT consuming the session — uses a throw-away connection."""
        config = self._get_config()
        from src.db.connection import DatabaseManager
        db = DatabaseManager(config=config)
        if db.connect():
            n = len(db.show_tables())
            db.disconnect()
            self.lbl_status.setText(t("conn.status_ok", n=n))
            self.lbl_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.lbl_status.setText(t("conn.status_fail"))
            self.lbl_status.setStyleSheet("color: red; font-weight: bold;")

    def _connect_and_continue(self):
        """Establish a PERSISTENT session and proceed."""
        config = self._get_config()
        if not config.database:
            QMessageBox.warning(self, t("common.error"), t("conn.db_required"))
            return
        session = self._session
        if session.connect(config):
            self.lbl_status.setText(t("conn.status_active", info=config.display_safe()))
            self.lbl_status.setStyleSheet("color: green; font-weight: bold;")
            self.btn_disconnect.setEnabled(True)
            self.btn_reconnect.setEnabled(True)
            self.connection_ready.emit(config)
        else:
            QMessageBox.critical(self, t("common.error"), t("conn.connect_error"))

    def _disconnect(self):
        self._session.disconnect()
        self.btn_disconnect.setEnabled(False)
        self.lbl_status.setText(t("conn.status_disconnected"))
        self.lbl_status.setStyleSheet("color: gray;")

    def _reconnect(self):
        if self._session.reconnect():
            self.lbl_status.setText(t("conn.status_active", info=self._session.status_text))
            self.lbl_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.lbl_status.setText(t("conn.status_fail"))
            self.lbl_status.setStyleSheet("color: red; font-weight: bold;")

    # ── Profile management ──

    def _load_profiles(self):
        self.profile_combo.clear()
        self.profile_combo.addItem("(new)")
        for name in sorted(load_connection_profiles().keys()):
            self.profile_combo.addItem(name)

    def _on_profile_selected(self, name: str):
        if name == "(new)" or not name:
            return
        profiles = load_connection_profiles()
        if name in profiles:
            self._set_config(profiles[name])

    def _save_profile(self):
        name = self.profile_combo.currentText()
        if name == "(new)":
            name = self.input_database.text().strip() or "default"
        profiles = load_connection_profiles()
        profiles[name] = self._get_config()
        save_connection_profiles(profiles)
        self._load_profiles()
        self.profile_combo.setCurrentText(name)

    def _delete_profile(self):
        name = self.profile_combo.currentText()
        if name == "(new)":
            return
        profiles = load_connection_profiles()
        profiles.pop(name, None)
        save_connection_profiles(profiles)
        self._load_profiles()

    def _load_from_env(self):
        load_dotenv_file()
        self._set_config(ConnectionConfig.from_env())
        self.lbl_status.setText(t("conn.loaded_env"))
        self.lbl_status.setStyleSheet("color: blue;")
