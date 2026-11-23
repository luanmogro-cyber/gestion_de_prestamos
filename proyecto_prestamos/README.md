# Sistema de Gestión de Préstamos (Linux Nativo)
**Proyecto de Sistemas Operativos - Entorno Nativo para Ubuntu 22.04/24.04 LTS y Debian 12**

Este proyecto es una solución integral y robusta para la administración de clientes, préstamos, amortizaciones y cobranzas, construida en **Python 3.11+** y **PySide6 (Qt 6)** bajo una **arquitectura desacoplada y modular** separada en **Frontend** y **Backend**.

---

## 🏛 Arquitectura Separada en Frontend y Backend

```text
proyecto_prestamos/
├── frontend/                     # Capa de Presentación (Interfaz Gráfica)
│   ├── __init__.py
│   └── gui/
│       ├── main_window.py        # Ventana principal, roles y monitoreo de estado IPC
│       ├── login_dialog.py       # Pantalla de autenticación segura
│       ├── clients_view.py       # CRUD y paginación de clientes
│       ├── loans_view.py         # Simulador Francés/Alemán y calendario de cuotas
│       ├── payments_view.py      # Cobranzas con prelación estricta y recibos
│       ├── reports_view.py       # Generación de reportes PDF en segundo plano (QThread)
│       ├── settings_view.py      # Configuración del sistema y respaldos
│       └── theme_manager.py      # Gestor dinámico de Modo Día / Modo Noche
├── backend/                      # Capa de Lógica de Negocio, Demonio y Persistencia
│   ├── __init__.py
│   ├── business/                 # Lógica Financiera y Validaciones
│   │   ├── auth_service.py       # Login y hashing bcrypt
│   │   ├── client_service.py     # Sanitización y validaciones de clientes
│   │   ├── loan_calculator.py    # Cálculos en Decimal (Francés, Alemán, Feriados)
│   │   ├── payment_service.py    # Prelación (1° Mora -> 2° Interés -> 3° Capital)
│   │   └── pdf_generator.py      # Generador de reportes PDF (ReportLab) y CSV
│   ├── database/                 # Capa de Datos
│   │   ├── db_manager.py         # SQLite3, flock concurrente, errores FS (SO-10)
│   │   └── models.py             # DDL, índices y usuarios semilla (admin y cajero)
│   ├── daemon/                   # Demonio en Segundo Plano (systemd --user)
│   │   └── daemon_main.py        # Servidor Socket Unix, libnotify y respaldos
│   └── common/                   # Servicios Transversales de SO
│       ├── config.py             # Estándar XDG (~/.config, permisos 600/700)
│       ├── logger.py             # RotatingFileHandler (SO-06)
│       ├── signals.py            # Señales POSIX (SIGINT, SIGTERM, SIGHUP)
│       └── ipc_protocol.py       # Protocolo IPC Socket Unix (~/.../ipc.sock)
├── setup/                        # Empaquetado y Despliegue en SO Linux
│   ├── install.sh                # Instalador automatizado con venv y systemd --user
│   ├── uninstall.sh              # Desinstalador limpio
│   ├── gestion-prestamos.desktop # Lanzador de escritorio .desktop
│   └── prestamos-daemon.service  # Unidad de servicio systemd --user
├── tests/
│   └── test_business_logic.py    # 13 pruebas unitarias exhaustivas con pytest
├── prestamos_gui_app.py          # Lanzador de la aplicación de escritorio
├── prestamos_daemon_app.py       # Lanzador del demonio en segundo plano
└── lanzar_dual.py                # Lanzador dual (Admin + Cajero lado a lado)
```

---

## 🔒 Cumplimiento de Requerimientos de Sistemas Operativos

| Requerimiento | Especificación | Implementación |
|---|---|---|
| **SO-01** | Nativo Linux | Ejecución directa en Ubuntu/Debian sin Wine, VMs ni Cloud. |
| **SO-02** | Concurrencia e Hilos | `QThread` en `frontend/gui/reports_view.py` para reportes pesados. |
| **SO-04** | Señales POSIX | `SIGINT`/`SIGTERM` liberan locks y sockets; `SIGHUP` recarga config. |
| **SO-05** | Estándar XDG y Permisos | Directorios `700`, Base de Datos y Configuración `600`. |
| **SO-06** | Logs y Rotación | `RotatingFileHandler` con límites de 5MB y 5 copias históricas. |
| **SO-07** | Concurrencia BD | Bloqueo por archivos con `fcntl.flock` (exclusivo para escrituras). |
| **SO-10** | Tolerancia a Fallos FS | Captura explícita de `ENOSPC` (disco lleno) y `EACCES` (permisos). |

---

## 🚀 Instalación y Despliegue en Linux

### Requisitos del Sistema:
- Ubuntu 22.04 LTS / 24.04 LTS o Debian 12
- Python 3.11 o superior
- Paquetes recomendados: `python3-venv`, `python3-pip`, `libnotify-bin`

### 1. Ejecutar el Script de Instalación Automatizado
```bash
chmod +x setup/install.sh setup/uninstall.sh
./setup/install.sh
```

### 2. Iniciar la Aplicación
Puede iniciarse desde el menú de aplicaciones del entorno de escritorio buscando **"Gestión de Préstamos"** o desde la terminal:
```bash
prestamos-gui
```

### 3. Credenciales de Acceso por Defecto:
- **Administrador:**
  - Usuario: `admin` | Contraseña: `admin1234`
- **Cajero:**
  - Usuario: `cajero` | Contraseña: `cajero1234`

---

## 💻 Ejecución en Windows (Terminal de Laragon)

```bash
cd c:/laragon/www/gestion_de_prestamos/proyecto_prestamos
pip install -r requirements.txt

# Para abrir la aplicación normal:
python prestamos_gui_app.py

# Para abrir el modo dual (Admin y Cajero al 50% de la pantalla):
python lanzar_dual.py
```

---

## 🧪 Pruebas Unitarias (`pytest`)

```bash
pytest -v tests/test_business_logic.py
```
