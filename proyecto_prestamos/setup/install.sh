#!/usr/bin/env bash
# ==============================================================================
# Script de Instalación - Sistema de Gestión de Préstamos
# Compatible con Ubuntu 22.04/24.04 LTS y Debian 12
# ==============================================================================
set -e

echo "=== Instalador del Sistema de Gestión de Préstamos ==="

# 1. Comprobación de dependencias del sistema Linux
command -v python3 >/dev/null 2>&1 || { echo "[ERROR] Python 3 no está instalado. Ejecute: sudo apt install python3"; exit 1; }
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[INFO] Python detectado: $PYTHON_VERSION"

# Verificar paquetes recomendados en Debian/Ubuntu
PACKAGES_TO_INSTALL=()
dpkg -s python3-venv >/dev/null 2>&1 || PACKAGES_TO_INSTALL+=("python3-venv")
dpkg -s python3-pip >/dev/null 2>&1 || PACKAGES_TO_INSTALL+=("python3-pip")
dpkg -s libnotify-bin >/dev/null 2>&1 || PACKAGES_TO_INSTALL+=("libnotify-bin")

if [ ${#PACKAGES_TO_INSTALL[@]} -ne 0 ]; then
    echo "[AVISO] Se requieren paquetes del sistema: ${PACKAGES_TO_INSTALL[*]}"
    echo "Instalando paquetes (puede requerir sudo)..."
    sudo apt-get update -qq && sudo apt-get install -y "${PACKAGES_TO_INSTALL[@]}"
fi

# 2. Rutas estándar XDG
XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_CONFIG_DIR="$XDG_CONFIG_HOME/gestion_prestamos"
APP_DATA_DIR="$XDG_DATA_HOME/gestion_prestamos"
APP_BIN_DIR="$HOME/.local/bin"
SYSTEMD_USER_DIR="$XDG_CONFIG_HOME/systemd/user"
DESKTOP_APPS_DIR="$XDG_DATA_HOME/applications"
ICONS_DIR="$XDG_DATA_HOME/icons/hicolor/scalable/apps"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 3. Creación de directorios con permisos estrictos (SO-05: 700 para directorios)
echo "[INFO] Configurando directorios según estándar XDG..."
mkdir -p "$APP_CONFIG_DIR" "$APP_DATA_DIR/backups" "$APP_DATA_DIR/logs" "$APP_BIN_DIR" "$SYSTEMD_USER_DIR" "$DESKTOP_APPS_DIR" "$ICONS_DIR"
chmod 700 "$APP_CONFIG_DIR"
chmod 700 "$APP_DATA_DIR"
chmod 700 "$APP_DATA_DIR/backups"
chmod 700 "$APP_DATA_DIR/logs"

# 4. Configurar Entorno Virtual (VENV)
VENV_DIR="$APP_DATA_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[INFO] Creando entorno virtual en $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

echo "[INFO] Instalando dependencias de Python..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# 5. Instalar archivos ejecutables en ~/.local/bin
echo "[INFO] Creando lanzadores en $APP_BIN_DIR..."

cat <<EOF > "$APP_BIN_DIR/prestamos-gui"
#!/bin/bash
export PYTHONPATH="$SCRIPT_DIR:\$PYTHONPATH"
exec "$VENV_DIR/bin/python3" "$SCRIPT_DIR/prestamos_gui_app.py" "\$@"
EOF
chmod 755 "$APP_BIN_DIR/prestamos-gui"

cat <<EOF > "$APP_BIN_DIR/prestamos-daemon"
#!/bin/bash
export PYTHONPATH="$SCRIPT_DIR:\$PYTHONPATH"
exec "$VENV_DIR/bin/python3" "$SCRIPT_DIR/prestamos_daemon_app.py" "\$@"
EOF
chmod 755 "$APP_BIN_DIR/prestamos-daemon"

# 6. Copiar lanzador .desktop e icono
echo "[INFO] Instalando archivo .desktop..."
sed -e "s|@BIN_PATH@|$APP_BIN_DIR/prestamos-gui|g" \
    "$SCRIPT_DIR/setup/gestion-prestamos.desktop" > "$DESKTOP_APPS_DIR/gestion-prestamos.desktop"
chmod 644 "$DESKTOP_APPS_DIR/gestion-prestamos.desktop"

# Actualizar base de datos de escritorio si existe
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_APPS_DIR" || true
fi

# 7. Configurar servicio systemd --user
echo "[INFO] Configurando servicio systemd --user..."
sed -e "s|@DAEMON_PATH@|$APP_BIN_DIR/prestamos-daemon|g" \
    "$SCRIPT_DIR/setup/prestamos-daemon.service" > "$SYSTEMD_USER_DIR/prestamos-daemon.service"
chmod 644 "$SYSTEMD_USER_DIR/prestamos-daemon.service"

systemctl --user daemon-reload
systemctl --user enable prestamos-daemon.service
systemctl --user restart prestamos-daemon.service

echo ""
echo "=========================================================="
echo "¡Instalación completada con éxito!"
echo "Puede iniciar la interfaz gráfica ejecutando:"
echo "  $APP_BIN_DIR/prestamos-gui  (o desde el menú de aplicaciones)"
echo "Estado del demonio systemd:"
systemctl --user status prestamos-daemon.service --no-pager || true
echo "=========================================================="

