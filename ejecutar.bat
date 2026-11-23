@echo off
title Sistema de Gestion de Prestamos
cd /d "%~dp0proyecto_prestamos"

echo ========================================================
echo       INICIANDO SISTEMA DE GESTION DE PRESTAMOS
echo ========================================================
echo.

if exist "C:\laragon\bin\python\python-3.13\python.exe" (
    echo [OK] Utilizando entorno Python de Laragon (Python 3.13)
    "C:\laragon\bin\python\python-3.13\python.exe" prestamos_gui_app.py
) else (
    echo [INFO] Utilizando Python del sistema
    python prestamos_gui_app.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Hubo un problema al iniciar la aplicacion.
    pause
)

