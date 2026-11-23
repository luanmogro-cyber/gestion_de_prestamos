# GUÍA TÉCNICA Y PEDAGÓGICA DEL PROYECTO
## Sistema de Gestión de Préstamos - Asignatura: Sistemas Operativos
**Documento de Sustentación para el Docente y Equipo de Desarrollo**

---

## 🎯 1. Resumen Ejecutivo del Proyecto
El **Sistema de Gestión de Préstamos** es una aplicación de escritorio corporativa desarrollada de forma **nativa para Linux (Ubuntu 22.04/24.04 LTS y Debian 12)** y compatible con **Windows**, diseñada bajo estándares rigurosos de la ingeniería de sistemas operativos. 

Su propósito es administrar clientes, amortizaciones financieras (Sistemas Francés y Alemán), cobranzas con prelación legal y generación de reportes oficiales en PDF/CSV, todo operando bajo un esquema desacoplado de dos procesos:
1. **Frontend de Interfaz Gráfica (`prestamos-gui`):** Construido en PySide6 (Qt 6) con arquitectura multihilo para garantizar fluidez visual.
2. **Backend Demonio en Segundo Plano (`prestamos-daemon`):** Proceso desatendido administrado por `systemd --user` que realiza monitoreo de mora, emisión de alertas con `libnotify` y copias de seguridad automáticas de SQLite.

---

## ⚙️ 2. ¿Cómo funciona el proyecto por dentro? (Mecanismos de Sistemas Operativos)

Para explicarle al profesor cómo funciona el sistema, estos son los pilares fundamentales de sistemas operativos implementados:

```text
                               +----------------------------------------+
                               |        FRONTEND: prestamos-gui         |
                               |  - PySide6 (Qt 6)                      |
                               |  - Hilos QThread (Reportes pesados)   |
                               |  - Modo Día / Modo Noche dinámico      |
                               +-------------------+--------------------+
                                                   |
                   Comunicación IPC: Socket Unix (~/.local/share/gestion_prestamos/ipc.sock)
                   Protocolo: Mensajes estructurados JSON (FORZAR_RESPALDO, VERIFICAR_ALERTAS)
                                                   |
                               +-------------------v--------------------+
                               |       BACKEND: prestamos-daemon        |
                               |  - Proceso hijo gestionado por systemd |
                               |  - Alertas libnotify (notify-send)     |
                               |  - Planificador de respaldos periódicos|
                               +-------------------+--------------------+
                                                   |
                      Transacciones ACID + Concurrencia fcntl.flock
                                                   |
                               +-------------------v--------------------+
                               |          BASE DE DATOS: SQLite3        |
                               |  ~/.local/share/gestion_prestamos/db   |
                               |  Modo WAL (Write-Ahead Logging)        |
                               |  Permisos POSIX estrictos: 600         |
                               +----------------------------------------+
```

### A. Comunicación Entre Procesos (IPC - Inter-Process Communication)
* **Mecanismo:** Socket de Dominio Unix (`AF_UNIX`, `SOCK_STREAM`), ubicado en `~/.local/share/gestion_prestamos/ipc.sock` con permisos `600`.
* **Cómo funciona:** La interfaz gráfica no ejecuta respaldos de base de datos ni lanza notificaciones directamente; se comunica mediante un protocolo bidireccional en formato JSON con el demonio en segundo plano enviando comandos como:
  * `FORZAR_RESPALDO`: Ordena al demonio generar una copia consistente de SQLite.
  * `VERIFICAR_ALERTAS`: Solicita al demonio inspeccionar cuotas vencidas y disparar alertas de escritorio.
  * `ESTADO_DEMONIO`: Retorna en tiempo real el tiempo de actividad (*uptime*) y estado del servicio.

### B. Concurrencia y Bloqueo de Archivos (`fcntl.flock`)
* **Problema de SO:** Si la interfaz gráfica y el demonio intentan escribir al mismo tiempo en el archivo SQLite, ocurriría corrupción de datos o condiciones de carrera (*race conditions*).
* **Solución:** Implementación de bloqueo de archivos a nivel de kernel mediante `fcntl.flock`:
  * **Bloqueo Compartido (`LOCK_SH`):** Para lecturas y consultas.
  * **Bloqueo Exclusivo (`LOCK_EX`):** Para inserción de pagos, nuevos créditos y transacciones ACID.
  * **Modo WAL (`Write-Ahead Logging`):** Permite que múltiples lectores operen simultáneamente mientras se escribe.

### C. Manejo de Señales POSIX (Signals)
* **Captura de `SIGTERM` y `SIGINT` (Ctrl + C):** Ambos procesos interceptan estas señales para realizar un cierre ordenado (*graceful shutdown*): liberan los bloqueos de archivo `flock`, cierran las transacciones activas de SQLite, eliminan el archivo del socket Unix y cierran los archivos de registro.
* **Captura de `SIGHUP`:** Permite la recarga en caliente (*hot-reload*) del archivo `config.json` sin necesidad de reiniciar la aplicación ni interrumpir las operaciones del cajero.

### D. Concurrencia Asíncrona en el Frontend (`QThread`)
* Las operaciones que consumen alto procesamiento (por ejemplo, generar un PDF con ReportLab de más de 500 registros o un consolidado de cartera) no se ejecutan en el hilo principal de la GUI, sino en hilos secundarios `QThread`. Esto evita que la ventana se "congele" o deje de responder ante el usuario.

### E. Precisión Financiera Estricta (`decimal.Decimal`)
* **Regla de oro de ingeniería:** Queda prohibido el uso de números de punto flotante (`float`) para representar dinero, debido a los errores de precisión binaria (IEEE 754). Todos los cálculos de amortización (Francés y Alemán), mora diaria y prelación de pagos se ejecutan con `decimal.Decimal` redondeado a dos cifras (`ROUND_HALF_UP`).

### F. Prelación de Pagos (Orden Legal de Cobranza)
* Al recibir un abono o pago, el sistema aplica los fondos bajo un orden estricto:
  1. **1° Interés Moratorio (Mora):** Se liquida primero la sanción diaria por retraso.
  2. **2° Interés Corriente:** Se amortizan los intereses causados del periodo.
  3. **3° Abono a Capital:** El excedente amortiza la deuda real o adelanta cuotas futuras.

### G. Estándar XDG y Permisos POSIX de Seguridad
* **Configuración:** `~/.config/gestion_prestamos/config.json` con permisos de directorio `700` y archivo `600`.
* **Datos, Logs y Respaldos:** `~/.local/share/gestion_prestamos/` con permisos `700` y archivos `600` (ningún otro usuario del sistema puede leer la base de datos financiera).

### H. Tolerancia a Fallos de Sistema de Archivos (SO-10)
* El código captura explícitamente excepciones de bajo nivel del kernel:
  * `ENOSPC`: Disco lleno.
  * `EACCES` / `EPERM`: Permisos denegados.
  * `ENOENT`: Archivo o ruta inexistente.
  Mostrando advertencias claras en pantalla sin que el software sufra un fallo catastrófico (*crash*).

### I. ¿Qué es y qué significa exactamente "El Demonio" (Daemon) en el Backend?
En Sistemas Operativos tipo Unix/Linux, un **demonio (*daemon*)** es un proceso que se ejecuta en **segundo plano (*background*)** de forma autónoma, continua y desatendida, sin una interfaz gráfica directa y sin depender de una terminal abierta. Tradicionalmente en Linux sus nombres terminan con la letra "d" (ejemplo: `systemd`, `sshd`, `crond`, `syslogd`).

En la arquitectura de nuestro proyecto, el demonio reside en `backend/daemon/daemon_main.py` y se ejecuta como un servicio del sistema operativo mediante `systemd --user` (`prestamos-daemon.service`). Cumple **4 funciones vitales en el backend**:
1. **Monitoreo Continuo de Cartera:** Revisa periódicamente la base de datos SQLite para detectar cuotas que vencen en los próximos N días o clientes que han caído en mora.
2. **Disparo de Alertas Nativas (`libnotify`):** Emite notificaciones emergentes en el escritorio Linux usando el subsistema de notificaciones (`notify-send`) para avisar vencimientos sin obligar al usuario a tener abierta la ventana del programa.
3. **Planificador de Respaldos Autónomos:** Cada intervalo programado (ej. cada 24 horas), ejecuta una copia de seguridad en caliente de la base de datos SQLite hacia `~/.local/share/gestion_prestamos/backups/`, aplicando políticas de rotación para conservar solo las últimas N copias y no saturar el disco.
4. **Servidor de Comunicación IPC:** Mantiene abierto el Socket Unix (`ipc.sock`) a la espera de comandos de la interfaz gráfica. Si el Administrador presiona "Forzar Respaldo" o "Verificar Alertas" desde la GUI, es el demonio quien procesa la tarea en el backend y devuelve una respuesta estructurada en JSON.

> **Analogía pedagógica para el profesor:**  
> *"La Interfaz Gráfica (Frontend) es como el cajero visible en la ventanilla que atiende al público; mientras que el Demonio (Backend) es el sistema automático de seguridad y auditoría que trabaja silenciosamente las 24 horas en el fondo, cuidando los respaldos y enviando alertas de cobro."*

---

## 💡 3. ¿Qué función cumple LARAGON en el proyecto? (Explicación para el Profesor)

Esta es una pregunta habitual del profesor: *"¿Por qué está este proyecto dentro de la carpeta `C:\laragon\www\`?"*

### La Respuesta Exacta para el Profesor:

> **"Profesor, Laragon en este proyecto cumple ÚNICAMENTE el papel de estación de trabajo / entorno de desarrollo local portátil en Windows. NO estamos utilizando el servidor Apache, ni Nginx, ni PHP, ni MySQL de Laragon."**

### Desglose Detallado de lo que hace y NO hace Laragon:

| Componente | ¿Se usa en el proyecto? | Explicación Técnica |
|---|---|---|
| **Python 3.13 de Laragon** | **SÍ** | Se utilizó el intérprete de Python que Laragon incluye en `C:\laragon\bin\python\python-3.13`. |
| **Gestor `pip` de Laragon** | **SÍ** | Se usó para instalar las dependencias aisladas (`PySide6`, `reportlab`, `bcrypt`, `pytest`). |
| **Terminal de Laragon (Cmder)** | **SÍ** | Se usó porque ya tiene configuradas las variables de entorno (`PATH`) listas para ejecutar `python` y `pip` sin alterar el sistema operativo Windows anfitrión. |
| **Carpeta `www/` de Laragon** | **SÍ** | Solo como directorio de almacenamiento del código fuente en la máquina física. |
| **Servidor Web Apache / Nginx** | **NO** | La aplicación es de escritorio nativa (PySide6 / Qt), no un sitio web PHP. |
| **Base de Datos MySQL de Laragon** | **NO** | Por requerimiento de SO, la persistencia es mediante un motor embebido **SQLite3** con transacciones ACID y control concurrente por bloqueos `fcntl.flock`. |
| **Intérprete PHP** | **NO** | El 100% del software está escrito en **Python 3**. |

> **Conclusión para la sustentación:** Laragon sirvió como entorno cómodo de programación en Windows. El proyecto final está empaquetado para desplegarse de manera 100% nativa en Linux mediante los scripts `setup/install.sh` y el servicio `prestamos-daemon.service` de `systemd --user`.

---

## 📁 4. Función y Propósito de cada Carpeta del Proyecto

El código está organizado bajo una arquitectura desacoplada que separa la presentación (`frontend/`) de la lógica de negocio y persistencia (`backend/`):

```text
proyecto_prestamos/
├── frontend/
│   ├── __init__.py
│   └── gui/
│       ├── main_window.py        # Ventana principal: navegación lateral, roles, estado IPC y barra de estado.
│       ├── login_dialog.py       # Diálogo de inicio de sesión con contraste de texto optimizado.
│       ├── clients_view.py       # Interfaz CRUD de clientes con validación interactiva y paginación.
│       ├── loans_view.py         # Simulador de préstamos (Francés/Alemán) y calendario de cuotas.
│       ├── payments_view.py      # Panel de cobranzas, prelación de pagos y generación de recibos.
│       ├── reports_view.py       # Generador de reportes en segundo plano usando QThread.
│       ├── settings_view.py      # Panel de configuración, respaldos SQLite y control del demonio.
│       └── theme_manager.py      # Gestor dinámico de estilos para Modo Día y Modo Noche.
│
├── backend/
│   ├── __init__.py
│   ├── business/
│   │   ├── auth_service.py       # Autenticación, control de roles (Admin/Cajero) y hashing bcrypt.
│   │   ├── client_service.py     # Lógica de validación (regex), sanitización de ingresos y desactivación lógica.
│   │   ├── loan_calculator.py    # Motor financiero en Decimal: cuotas, intereses, mora y ajuste de feriados.
│   │   ├── payment_service.py    # Transacciones ACID de pago: distribución Mora -> Interés -> Capital.
│   │   └── pdf_generator.py      # Motor de reportes oficiales con ReportLab (comprobantes, amortizaciones) y CSV.
│   ├── database/
│   │   ├── db_manager.py         # Conexión SQLite3, control de concurrencia flock, copias de seguridad y restore.
│   │   └── models.py             # DDL: creación de tablas, índices de rendimiento y usuario admin inicial.
│   ├── daemon/
│   │   └── daemon_main.py        # Demonio en segundo plano: servidor Socket Unix, alertas libnotify y temporizador.
│   └── common/
│       ├── config.py             # Lógica XDG (~/.config, permisos 600/700) y recarga por SIGHUP.
│       ├── logger.py             # Logging con rotación de archivos (RotatingFileHandler de 5MB x 5 backups).
│       ├── signals.py            # Manejo de señales del kernel Linux: SIGTERM, SIGINT y SIGHUP.
│       └── ipc_protocol.py       # Servidor y cliente de IPC mediante Socket Unix con protocolo JSON.
│
├── setup/                        # Empaquetado y Despliegue en Linux
│   ├── install.sh                # Script Bash que crea el venv, instala dependencias y habilita systemd.
│   ├── uninstall.sh              # Script Bash para remover el servicio y limpiar archivos.
│   ├── gestion-prestamos.desktop # Lanzador oficial para el menú de aplicaciones de Linux (GNOME/KDE/XFCE).
│   └── prestamos-daemon.service  # Unidad de servicio systemd --user para autoinicio del demonio.
│
├── tests/
│   ├── __init__.py
│   └── test_business_logic.py    # Suite de 13 pruebas unitarias con pytest (caso aceptación 10M al 18%, etc.).
│
├── src/                          # Capa de compatibilidad (proxies que redirigen hacia backend y frontend).
├── prestamos_gui_app.py          # Punto de entrada ejecutable del Frontend de escritorio.
├── prestamos_daemon_app.py       # Punto de entrada ejecutable del Demonio en segundo plano.
├── lanzar_dual.py                # Lanzador de demostración en Pantalla Dividida (Admin + Cajero lado a lado).
├── requirements.txt              # Lista de dependencias de Python: PySide6, reportlab, bcrypt, pytest.
└── README.md                     # Documentación técnica general de instalación y comandos SO.
```

---

## 📈 5. Registro Evolutivo de Cambios Realizados al Proyecto

Este apartado recopila todos los cambios y mejoras incorporadas cronológicamente para mantener el concepto actualizado:

| Registro | Fecha | Petición / Cambio | Concepto Técnico Aplicado |
|---|---|---|---|
| **01** | 2026-11-20 | Creación inicial del proyecto según especificación de Sistemas Operativos. | Arquitectura modular de dos componentes (Frontend PySide6 + Demonio systemd), SQLite con `fcntl.flock`, `decimal.Decimal`, `libnotify`, XDG 600/700 y 13 pruebas `pytest`. |
| **02** | 2026-11-20 | Consulta sobre dónde y cómo ver el sistema funcionando. | Creación de la **Vista Previa Interactiva HTML** (`vista_previa_sistema.html`) con simulador en tiempo real y documentación de ejecución en Windows y Linux. |
| **03** | 2026-11-20 | Solución al error `'pip' no se reconoce como un comando en PowerShell`. | Diagnóstico de variables de entorno `PATH` y recomendación de utilizar la Terminal integrada de Laragon. |
| **04** | 2026-11-20 | Confirmación de uso de la Terminal de Laragon. | Instrucciones de ejecución directa usando el entorno Python 3.13 preconfigurado de Laragon. |
| **05** | 2026-11-20 | 1) Corrección del color de letras (visibilidad al escribir).<br>2) Selector de Modo Día / Noche.<br>3) Corrección al agregar nuevos clientes. | • Se forzó el color de texto con `!important` en todas las entradas (`QLineEdit`, `QSpinBox`).<br>• Se creó `theme_manager.py` con botón conmutador ☀️/🌙 en la barra lateral.<br>• En `clients_view.py`, se integró validación previa con preservación de datos, selector `QDateEdit` con calendario y sanitización inteligente de ingresos con separadores de miles (`2.500.000`). |
| **06** | 2026-11-20 | Instrucciones de actualización (por qué no se veían los cambios). | Explicación del ciclo de vida de procesos Python de escritorio (requiere reiniciar el script) y purga de la caché `__pycache__`. |
| **07** | 2026-11-20 | Visualización simultánea de dos ventanas (Admin y Cajero al mismo tiempo). | Creación del script ejecutable `lanzar_dual.py` que abre y posiciona automáticamente ambas sesiones al 50% de la pantalla (lado a lado), más el modo dual en la vista previa web. |
| **08** | 2026-11-23 | Reorganización y separación arquitectónica en Backend y Frontend. | Desacoplamiento total del código en los paquetes `frontend/` (PySide6) y `backend/` (negocio, datos, demonio y SO), con capas puente en `src/`. |
| **09** | 2026-11-23 | Elaboración de la Guía Técnica y Pedagógica para el Profesor. | Redacción del presente documento (`GUIA_EXPLICACION_PROYECTO.md`) explicando los mecanismos de SO, el papel de Laragon y la función de cada carpeta. |
| **10** | 2026-11-23 | Definición y alcance del concepto de Demonio (Daemon) en el Backend. | Incorporación de la sección técnica y pedagógica sobre procesos de fondo, `systemd --user`, alertas con `libnotify` y servidor IPC Socket Unix. |
| **11** | 2026-11-23 | Corrección de contraste en panel de Pagos y Cobranzas. | Se forzó color de texto `#78350F !important` con borde contrastado en `lbl_debt_info` y formato HTML legible en el desglose de deuda (mora, interés, capital). |
| **12** | 2026-11-23 | Diagnóstico y solución de ejecución en PowerShell (`pip`/`python` no reconocido). | Explicación del entorno aislado de Laragon Python 3.13; verificación de paquetes preinstalados (`PySide6`, `bcrypt`, `reportlab`) y creación de scripts `ejecutar.bat` para arranque automático con un solo clic. |
| **13** | 2026-11-23 | Inicialización de Git y preparación para despliegue en Railway Cloud. | Configuración de `.gitignore`, inicialización del repositorio Git local, creación del servicio web `web_app.py` con monitoreo de salud `/health`, y descriptores `Procfile` / `railway.json` para despliegue en contenedores Railway. |
| **14** | 2026-11-23 | Gestión de autorización y despliegue autónomo en Railway. | Coordinación del flujo de autenticación OAuth de Railway y preparación para aprovisionamiento directo del servicio cloud. |
| **15** | 2026-11-23 | Creación de Proyecto, Servicio y Dominio en Railway y Remote GitHub. | Se creó en Railway el proyecto `gestion_de_prestamos`, el servicio `gestion_de_prestamos` y se asignó el dominio público `https://gestiondeprestamos-production-e552d9f2.up.railway.app`. Se enlazó el repositorio remoto `luanmogro-cyber/gestion_de_prestamos`. |
| **16** | 2026-11-23 | Diagnóstico de autenticación interactiva de Git y conexión Railway. | Identificación de requerimiento de autorización de Git Credential Manager en Windows para el primer push interactivo hacia GitHub. |

---

## 🎤 6. Guión Rápido de 3 Minutos para Defender el Proyecto ante el Profesor

1. **Introducción (30 seg):**
   > *"Profesor, este proyecto es un Sistema de Gestión de Préstamos diseñado con arquitectura desacoplada en dos procesos independientes: una interfaz gráfica en PySide6 y un demonio en segundo plano gestionado por systemd."*
2. **Sistemas Operativos (60 seg):**
   > *"Ambos procesos se comunican mediante un Socket Unix local en `~/.local/share/` intercambiando comandos en formato JSON. Para garantizar la integridad transaccional ACID de SQLite entre la GUI y el demonio, implementamos control de concurrencia a nivel de sistema de archivos con la llamada `fcntl.flock`. Además, manejamos señales POSIX: `SIGTERM` para cierre limpio de sockets y locks, y `SIGHUP` para recarga en caliente de la configuración XDG sin reiniciar la app."*
3. **Lógica de Negocio y Frontend (60 seg):**
   > *"La aplicación utiliza estrictamente `decimal.Decimal` para erradicar errores de precisión binaria en los sistemas Francés y Alemán. Los cobros aplican prelación estricta (1° Mora -> 2° Interés -> 3° Capital). En la interfaz contamos con control de roles por bcrypt (Admin y Cajero), selector de Modo Día/Noche y generación de PDFs en hilos `QThread` para evitar bloquear la interfaz."*
4. **Demostración Práctica (30 seg):**
   > *"Para demostrar la concurrencia y la diferencia de roles, podemos ejecutar `python lanzar_dual.py`, que abre ambas ventanas simultáneas en pantalla dividida."*

