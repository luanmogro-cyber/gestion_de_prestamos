from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from backend.business.auth_service import AuthService

class LoginDialog(QDialog):
    """
    Diálogo de autenticación de usuarios (PR-01, PR-02).
    Garantiza contraste óptimo y texto 100% visible al escribir.
    """
    def __init__(self, auth_service: AuthService, parent=None):
        super(LoginDialog, self).__init__(parent)
        self.auth_service = auth_service
        self.user_data = None

        self.setWindowTitle("Iniciar Sesión - Sistema de Préstamos")
        self.setFixedSize(420, 340)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.setStyleSheet("""
            QDialog {
                background-color: #F8FAFC;
            }
            QLabel {
                color: #0F172A;
                font-size: 13px;
                font-weight: 500;
            }
            QLineEdit {
                border: 1.5px solid #94A3B8;
                border-radius: 6px;
                padding: 8px 12px;
                background-color: #FFFFFF !important;
                color: #0F172A !important;
                font-size: 14px;
                selection-background-color: #2563EB;
                selection-color: #FFFFFF;
            }
            QLineEdit:focus {
                border: 2px solid #2563EB !important;
                background-color: #FFFFFF !important;
                color: #0F172A !important;
            }
            QPushButton#btnLogin {
                background-color: #2563EB;
                color: #FFFFFF;
                font-weight: bold;
                border-radius: 6px;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton#btnLogin:hover {
                background-color: #1D4ED8;
            }
            QPushButton#btnCancel {
                background-color: #E2E8F0;
                color: #334155;
                font-weight: 500;
                border-radius: 6px;
                padding: 9px;
            }
            QPushButton#btnCancel:hover {
                background-color: #CBD5E1;
            }
        """)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        # Encabezado
        title = QLabel("Gestión de Préstamos")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #1E3A8A; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel("Acceso seguro con control de roles (Linux / Windows)")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #64748B; font-size: 11px;")
        layout.addWidget(subtitle)

        layout.addSpacing(6)

        # Campos
        lbl_u = QLabel("Usuario:")
        layout.addWidget(lbl_u)
        self.txt_username = QLineEdit()
        self.txt_username.setPlaceholderText("Ej: admin o cajero")
        self.txt_username.setText("admin")  # Default inicial
        layout.addWidget(self.txt_username)

        lbl_p = QLabel("Contraseña:")
        layout.addWidget(lbl_p)
        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_password.setPlaceholderText("••••••••")
        self.txt_password.setText("admin1234")  # Default inicial
        self.txt_password.returnPressed.connect(self._do_login)
        layout.addWidget(self.txt_password)

        layout.addSpacing(8)

        # Botones
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        self.btn_cancel = QPushButton("Salir")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_login = QPushButton("Ingresar al Sistema")
        self.btn_login.setObjectName("btnLogin")
        self.btn_login.clicked.connect(self._do_login)
        btn_layout.addWidget(self.btn_login)

        layout.addLayout(btn_layout)

    def _do_login(self):
        username = self.txt_username.text().strip()
        password = self.txt_password.text()

        if not username or not password:
            QMessageBox.warning(self, "Campos Requeridos", "Por favor ingrese usuario y contraseña.")
            return

        user = self.auth_service.authenticate(username, password)
        if user:
            self.user_data = user
            self.accept()
        else:
            QMessageBox.critical(self, "Error de Autenticación", "Usuario o contraseña incorrectos.")
            self.txt_password.clear()
            self.txt_password.setFocus()

