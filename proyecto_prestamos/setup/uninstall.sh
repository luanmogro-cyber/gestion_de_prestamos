#!/usr/bin/env bash
# ==============================================================================
# Script de Desinstalación - Sistema de Gestión de Préstamos
# ==============================================================================
set -e

echo "=== Desinstalador del Sistema de Gestión de Préstamos ==="

XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_CONFIG_DIR="$XDG_CONFIG_HOME/gestion_prestamos"
APP_DATA_DIR="$XDG_DATA_HOME/gestion_prestamos"
APP_BIN_DIR="$HOME/.local/bin"
SYSTEMD_USER_DIR="$XDG_CONFIG_HOME/systemd/user"
DESKTOP_APPS_DIR="$XDG_DATA_HOME/applications"

# 1. Detener y deshabilitar servicio systemd --user
echo "[INFO] Deteniendo y deshabilitando el servicio systemd --user..."
systemctl --user stop prestamos-daemon.service 2>/dev/null || true
systemctl --user disable prestamos-daemon.service 2>/dev/null || true
rm -f "$SYSTEMD_USER_DIR/prestamos-daemon.service"
systemctl --user daemon-reload

# 2. Eliminar lanzadores y archivo .desktop
echo "[INFO] Eliminando lanzadores y entradas de escritorio..."
rm -f "$APP_BIN_DIR/prestamos-gui"
rm -f "$APP_BIN_DIR/prestamos-daemon"
rm -f "$DESKTOP_APPS_DIR/gestion-prestamos.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_APPS_DIR" || true
fi

# 3. Preguntar por la eliminación de datos
read -p "¿Desea eliminar la base de datos, respaldos y configuración (~/.config y ~/.local/share)? (s/N): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Ss]$ ]]; then
    echo "[INFO] Eliminando datos y configuración..."
    rm -rf "$APP_CONFIG_DIR"
    rm -rf "$APP_DATA_DIR"
else
    echo "[INFO] Se mantuvieron los datos en $APP_DATA_DIR y $APP_CONFIG_DIR."
    echo "[INFO] Eliminando únicamente el entorno virtual..."
    rm -rf "$APP_DATA_DIR/venv"
fi

echo "Desinstalación finalizada correctamente."

