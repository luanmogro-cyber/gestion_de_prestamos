import os
import sys
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QPushButton, QLabel, QStatusBar,
    QFrame, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from backend.common.config import ConfigManager
from backend.common.signals import signal_manager
from backend.common.ipc_protocol import UnixSocketClient
from backend.database.db_manager import DatabaseManager
from backend.business.auth_service import AuthService
from backend.business.client_service import ClientService
from backend.business.loan_calculator import LoanCalculator
from backend.business.payment_service import PaymentService
from frontend.gui.clients_view import ClientsView
from frontend.gui.loans_view import LoansView
from frontend.gui.payments_view import PaymentsView
from frontend.gui.reports_view import ReportsView
from frontend.gui.settings_view import SettingsView
from frontend.gui.theme_manager import get_theme_stylesheet

class MainWindow(QMainWindow):
    """
    Ventana Principal del Sistema de Gestión de Préstamos (prestamos-gui).
    Incluye:
    - Selector dinámico de Modo Día / Modo Noche con contraste perfecto de tipografía.
    - Barra lateral con navegación desacoplada.
    - Control de roles y monitoreo en tiempo real del Demonio IPC.
    """
    def __init__(self, current_user: dict, on_logout_callback=None):
        super(MainWindow, self).__init__()
        self.current_user = current_user
        self.on_logout_callback = on_logout_callback

        self.config = ConfigManager()
        self.db = DatabaseManager()
        self.auth_service = AuthService(self.db)
        self.client_service = ClientService(self.db)
        self.loan_calculator = LoanCalculator(self.db)
        self.payment_service = PaymentService(self.db)
        self.ipc_client = UnixSocketClient(self.config.ipc_socket_path)

        # Cargar preferencia de tema (default: claro)
        self.current_theme = self.config.get("interfaz", "tema", default="claro")

        self.setWindowTitle(f"Sistema de Gestión de Préstamos - [{self.current_user['role']}: {self.current_user['full_name']}]")
        self.resize(1200, 780)
        self.setMinimumSize(980, 660)

        self._build_ui()
        self._apply_theme(self.current_theme)

        # Timer para consultar estado del demonio cada 10 segundos
        self.timer_daemon = QTimer(self)
        self.timer_daemon.timeout.connect(self._check_daemon_status)
        self.timer_daemon.start(10000)
        self._check_daemon_status()

    def _apply_theme(self, theme_name: str):
        self.current_theme = theme_name
        stylesheet = get_theme_stylesheet(theme_name)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet)
        else:
            self.setStyleSheet(stylesheet)

        # Actualizar texto del botón de tema
        if theme_name == "oscuro":
            self.btn_theme_toggle.setText("☀️ Cambiar a Modo Día")
            self.btn_theme_toggle.setStyleSheet("background-color: #334155; color: #F8FAFC; border: 1px solid #475569; text-align: center;")
        else:
            self.btn_theme_toggle.setText("🌙 Cambiar a Modo Noche")
            self.btn_theme_toggle.setStyleSheet("background-color: #1E293B; color: #F8FAFC; border: 1px solid #334155; text-align: center;")

    def _toggle_theme(self):
        new_theme = "oscuro" if self.current_theme == "claro" else "claro"
        self._apply_theme(new_theme)
        try:
            self.config.set("interfaz", "tema", new_theme)
        except Exception:
            pass

    def _build_ui(self):
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Barra lateral (Sidebar)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 15, 0, 15)
        side_layout.setSpacing(6)

        # Logo / Título institucional
        lbl_app = QLabel("Créditos Linux")
        lbl_app.setStyleSheet("color: #FFFFFF; font-size: 19px; font-weight: bold; padding: 10px 16px 2px 16px;")
        side_layout.addWidget(lbl_app)

        lbl_role = QLabel(f"● {self.current_user['role']}\n{self.current_user['full_name']}")
        lbl_role.setStyleSheet("color: #94A3B8; font-size: 11px; padding: 0 16px 12px 16px;")
        side_layout.addWidget(lbl_role)

        # Botón para alternar Modo Día / Noche
        self.btn_theme_toggle = QPushButton("🌙 Modo Noche")
        self.btn_theme_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_theme_toggle.clicked.connect(self._toggle_theme)
        side_layout.addWidget(self.btn_theme_toggle)

        side_layout.addSpacing(6)

        self.nav_buttons = []

        btn_clients = self._create_nav_btn("👥 Clientes", 0)
        side_layout.addWidget(btn_clients)

        btn_loans = self._create_nav_btn("💰 Préstamos & Simulador", 1)
        side_layout.addWidget(btn_loans)

        btn_payments = self._create_nav_btn("💳 Pagos & Cobranza", 2)
        side_layout.addWidget(btn_payments)

        btn_reports = self._create_nav_btn("📈 Reportes & Exportar", 3)
        side_layout.addWidget(btn_reports)

        btn_settings = self._create_nav_btn("⚙ Configuración & Demonio", 4)
        side_layout.addWidget(btn_settings)

        side_layout.addStretch()

        # Botón cerrar sesión
        btn_logout = QPushButton("🚪 Cerrar Sesión")
        btn_logout.setStyleSheet("color: #F87171; background: transparent; text-align: left; padding: 10px 16px; margin: 8px; font-weight: 500;")
        btn_logout.setCursor(Qt.PointingHandCursor)
        btn_logout.clicked.connect(self._do_logout)
        side_layout.addWidget(btn_logout)

        main_layout.addWidget(sidebar)

        # 2. Contenedor de Vistas apiladas (Stacked Widget)
        self.stack = QStackedWidget()

        self.view_clients = ClientsView(self.client_service, self.current_user)
        self.stack.addWidget(self.view_clients)

        self.view_loans = LoansView(self.loan_calculator, self.client_service, self.current_user)
        self.stack.addWidget(self.view_loans)

        self.view_payments = PaymentsView(self.payment_service, self.loan_calculator, self.current_user)
        self.stack.addWidget(self.view_payments)

        self.view_reports = ReportsView(self.db, self.current_user)
        self.stack.addWidget(self.view_reports)

        self.view_settings = SettingsView(self.config, self.db, self.current_user)
        self.stack.addWidget(self.view_settings)

        main_layout.addWidget(self.stack)

        self.setCentralWidget(main_widget)

        # 3. Barra de Estado
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.lbl_user_status = QLabel(f"Usuario activo: {self.current_user['username']} ({self.current_user['role']})")
        self.lbl_db_status = QLabel("Base de Datos: SQLite3 (ACID - flock activo)")
        self.lbl_daemon_status = QLabel("Demonio IPC: Verificando...")

        self.status_bar.addWidget(self.lbl_user_status)
        self.status_bar.addPermanentWidget(self.lbl_db_status)
        self.status_bar.addPermanentWidget(self.lbl_daemon_status)

        # Activar primera pestaña por defecto
        self.nav_buttons[0].setChecked(True)

    def _create_nav_btn(self, text: str, index: int) -> QPushButton:
        btn = QPushButton(text)
        btn.setProperty("class", "nav-btn")
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda: self._switch_tab(index))
        self.nav_buttons.append(btn)
        return btn

    def _switch_tab(self, index: int):
        for idx, btn in enumerate(self.nav_buttons):
            btn.setChecked(idx == index)
        self.stack.setCurrentIndex(index)

        # Refrescar listas al cambiar de pestaña
        if index == 0:
            self.view_clients.load_clients()
        elif index == 1:
            self.view_loans.refresh_clients_combo()
            self.view_loans.load_loans_list()
        elif index == 2:
            self.view_payments.refresh_loans_combo()
            self.view_payments.load_payments_history()

    def _check_daemon_status(self):
        active = self.ipc_client.is_daemon_active()
        if active:
            self.lbl_daemon_status.setText("🟢 Demonio IPC: Conectado (Socket Unix)")
            self.lbl_daemon_status.setStyleSheet("color: #059669; font-weight: bold; padding-right: 10px;")
        else:
            self.lbl_daemon_status.setText("🔴 Demonio IPC: Desconectado")
            self.lbl_daemon_status.setStyleSheet("color: #DC2626; font-weight: bold; padding-right: 10px;")

    def _do_logout(self):
        reply = QMessageBox.question(
            self, "Cerrar Sesión", "¿Está seguro de que desea cerrar la sesión actual?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.close()
            if self.on_logout_callback:
                self.on_logout_callback()

    def closeEvent(self, event):
        self.timer_daemon.stop()
        event.accept()

