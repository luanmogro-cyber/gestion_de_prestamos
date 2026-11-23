"""
Módulo Backend del Sistema de Gestión de Préstamos.
Contiene:
- common: Configuración XDG, logger rotativo, señales POSIX y protocolo IPC.
- database: Gestor SQLite3, control de concurrencia flock y modelos de datos.
- business: Servicios de autenticación, validación de clientes, cálculo financiero con Decimal, prelación de pagos y generación de PDF.
- daemon: Demonio en segundo plano (prestamos-daemon) con libnotify y respaldos automáticos.
"""

