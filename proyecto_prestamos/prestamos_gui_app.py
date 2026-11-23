#!/usr/bin/env python3
"""
Punto de Entrada del Frontend de Escritorio (prestamos-gui)
Ejecutable PySide6 con login, control de roles y manejo de señales POSIX.
Estructura desacoplada: Frontend (PySide6) + Backend (Lógica de Negocio y Persistencia).
"""
import sys
import os
from pathlib import Path

# Agregar directorio raíz al PYTHONPATH
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from backend.common.config import ConfigManager
from backend.common.logger import setup_logger
from backend.common.signals import signal_manager
from backend.database.db_manager import DatabaseManager
from backend.database.models import initialize_database
from backend.business.auth_service import AuthService
from frontend.gui.login_dialog import LoginDialog
from frontend.gui.main_window import MainWindow

logger = setup_logger("prestamos.gui", "gui.log")


def run_app():
    app = QApplication(sys.argv)
    app.setApplicationName("Sistema de Gestión de Préstamos")
    app.setOrganizationName("SistemasOperativosLinux")

    config = ConfigManager()
    db = DatabaseManager(config.db_path)
    initialize_database(db)

    # Registrar señales POSIX para cierre ordenado (SO-04)
    signal_manager.register_shutdown_hook(lambda: app.quit())
    signal_manager.register_reload_hook(config.reload)
    signal_manager.setup()

    auth_service = AuthService(db)

    def show_flow():
        login_dlg = LoginDialog(auth_service)
        if login_dlg.exec():
            user = login_dlg.user_data
            main_win = MainWindow(current_user=user, on_logout_callback=show_flow)
            main_win.show()
            # Guardar referencia para que no sea recolectado por el GC
            app._main_window = main_win
        else:
            sys.exit(0)

    show_flow()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
