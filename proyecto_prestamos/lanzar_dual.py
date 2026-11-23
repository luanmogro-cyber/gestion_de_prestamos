#!/usr/bin/env python3
"""
Lanzador de Demostración Dual (Administrador y Cajero en Pantalla Dividida).
Abre dos ventanas simultáneas de PySide6 posicionadas lado a lado para
evaluar y comparar en tiempo real el control de roles (PR-01, PR-02).
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PySide6.QtWidgets import QApplication
from backend.common.config import ConfigManager
from backend.database.db_manager import DatabaseManager
from backend.database.models import initialize_database
from frontend.gui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Gestión de Préstamos - Modo Dual")

    config = ConfigManager()
    db = DatabaseManager(config.db_path)
    initialize_database(db)

    # Usuarios predefinidos
    user_admin = {
        "id": 1,
        "username": "admin",
        "full_name": "Administrador del Sistema",
        "role": "Administrador"
    }

    user_cajero = {
        "id": 2,
        "username": "cajero",
        "full_name": "Cajero Principal",
        "role": "Cajero"
    }

    # Instanciar ambas ventanas
    win_admin = MainWindow(current_user=user_admin)
    win_cajero = MainWindow(current_user=user_cajero)

    # Posicionamiento automático lado a lado (pantalla dividida 50% / 50%)
    screen = app.primaryScreen()
    if screen:
        geo = screen.availableGeometry()
        half_width = geo.width() // 2
        height = geo.height() - 35

        win_admin.setGeometry(geo.x(), geo.y(), half_width, height)
        win_cajero.setGeometry(geo.x() + half_width, geo.y(), half_width, height)

    win_admin.show()
    win_cajero.show()

    # Mantener referencias vivas
    app._win_admin = win_admin
    app._win_cajero = win_cajero

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
