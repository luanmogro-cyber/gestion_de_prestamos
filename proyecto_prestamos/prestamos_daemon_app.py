#!/usr/bin/env python3
"""
Punto de Entrada del Backend Demonio en Segundo Plano (prestamos-daemon)
Gestionado por systemd --user con servidor Socket Unix, alertas libnotify y respaldos.
"""
import sys
from pathlib import Path

# Agregar directorio raíz al PYTHONPATH
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.daemon.daemon_main import main

if __name__ == "__main__":
    main()
