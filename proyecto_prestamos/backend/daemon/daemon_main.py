import os
import sys
import time
import shutil
import logging
import subprocess
from datetime import datetime, date, timedelta
from pathlib import Path
from decimal import Decimal

from backend.common.config import ConfigManager
from backend.common.logger import setup_logger
from backend.common.signals import signal_manager
from backend.common.ipc_protocol import UnixSocketServer
from backend.database.db_manager import DatabaseManager

logger = setup_logger("prestamos.daemon", "daemon.log")


class PrestamosDaemon:
    """
    Demonio en Segundo Plano (prestamos-daemon) gestionado por systemd --user.
    Funcionalidades:
    1. Servidor Socket Unix para recibir comandos desde la GUI en tiempo real.
    2. Monitoreo de cuotas por vencer o en mora y emisión de alertas de escritorio con libnotify.
    3. Planificación y ejecución de respaldos periódicos automáticos de SQLite.
    4. Cierre ordenado capturando SIGTERM/SIGINT y recarga con SIGHUP.
    """
    def __init__(self):
        self.config = ConfigManager()
        self.db = DatabaseManager()
        self.ipc_server = UnixSocketServer(self.config.ipc_socket_path)
        self.start_time = datetime.now()
        self.last_backup_time: Optional[datetime] = None
        self.last_backup_path: Optional[Path] = None
        self.running = False

    def notify_desktop(self, title: str, message: str, urgency: str = "normal"):
        """
        Envía notificaciones nativas de escritorio Linux usando libnotify (notify-send).
        """
        logger.info(f"[LIBNOTIFY] {title}: {message}")
        if shutil.which("notify-send"):
            try:
                subprocess.run(
                    ["notify-send", "-a", "Gestión de Préstamos", "-u", urgency, title, message],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception as e:
                logger.warning(f"Error invocando notify-send: {e}")

    def check_alerts(self) -> int:
        """
        Verifica cuotas con vencimiento próximo en los siguientes N días o vencidas.
        Emite alertas de escritorio vía libnotify.
        """
        days_ahead = int(self.config.get("demonio", "dias_anticipacion_alerta", default=3))
        today = date.today()
        target_date = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        today_str = today.strftime("%Y-%m-%d")

        alerts_count = 0

        try:
            with self.db.connection(exclusive_lock=False) as conn:
                cursor = conn.cursor()
                # 1. Cuotas próximas a vencer
                cursor.execute(
                    """
                    SELECT i.id, i.loan_id, i.number, i.due_date, i.total_expected,
                           c.first_name, c.last_name
                    FROM installments i
                    JOIN loans l ON i.loan_id = l.id
                    JOIN clients c ON l.client_id = c.id
                    WHERE i.status IN ('pendiente', 'parcial')
                      AND i.due_date BETWEEN ? AND ?
                    ORDER BY i.due_date ASC;
                    """,
                    (today_str, target_date)
                )
                upcoming = cursor.fetchall()

                for r in upcoming:
                    alerts_count += 1
                    sym = self.config.get("financiero", "moneda_simbolo", default="$")
                    self.notify_desktop(
                        title=f"Alerta: Cuota #{r['number']} próxima a vencer",
                        message=f"Cliente: {r['first_name']} {r['last_name']}\n"
                                f"Préstamo #{r['loan_id']} vence el {r['due_date']}\n"
                                f"Monto: {sym} {Decimal(r['total_expected']):,.2f}",
                        urgency="normal"
                    )

                # 2. Cuotas en mora
                cursor.execute(
                    """
                    SELECT COUNT(*) as mora_count, SUM(CAST(capital_expected AS REAL) - CAST(capital_paid AS REAL)) as total_mora
                    FROM installments
                    WHERE status IN ('pendiente', 'parcial', 'vencida') AND due_date < ?;
                    """,
                    (today_str,)
                )
                mora_row = cursor.fetchone()
                if mora_row and mora_row["mora_count"] > 0:
                    cnt = mora_row["mora_count"]
                    tot = Decimal(str(mora_row["total_mora"] or "0.00")).quantize(Decimal("0.01"))
                    sym = self.config.get("financiero", "moneda_simbolo", default="$")
                    self.notify_desktop(
                        title=f"Atención: {cnt} Cuotas en Mora",
                        message=f"Capital total en mora: {sym} {tot:,.2f}. Revise el panel de cobranza.",
                        urgency="critical"
                    )

        except Exception as e:
            logger.error(f"Error verificando alertas: {e}")

        return alerts_count

    def perform_backup(self) -> Path:
        """Ejecuta un respaldo consistente de la base de datos."""
        logger.info("Iniciando respaldo de base de datos desde el demonio...")
        path = self.db.create_backup()
        self.last_backup_time = datetime.now()
        self.last_backup_path = path
        logger.info(f"Respaldo generado con éxito en: {path}")
        return path

    def handle_ipc_command(self, cmd: str, params: dict) -> dict:
        """Despachador de comandos recibidos vía Socket Unix."""
        logger.info(f"Comando IPC recibido: {cmd}")
        if cmd == "PING":
            return {"status": "ok", "message": "pong"}

        elif cmd == "ESTADO_DEMONIO":
            uptime_seconds = int((datetime.now() - self.start_time).total_seconds())
            return {
                "status": "ok",
                "uptime_seconds": uptime_seconds,
                "start_time": self.start_time.isoformat(),
                "last_backup": self.last_backup_path.name if self.last_backup_path else "Ninguno",
                "last_backup_time": self.last_backup_time.isoformat() if self.last_backup_time else None
            }

        elif cmd == "FORZAR_RESPALDO":
            try:
                b_path = self.perform_backup()
                return {"status": "ok", "message": "Respaldo completado", "backup_path": str(b_path)}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        elif cmd == "VERIFICAR_ALERTAS":
            try:
                count = self.check_alerts()
                return {"status": "ok", "message": "Alertas verificadas", "alerts_count": count}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        return {"status": "error", "message": f"Comando no reconocido: {cmd}"}

    def start(self):
        """Inicia el ciclo de vida del demonio."""
        logger.info("Iniciando Demonio prestamos-daemon (PID: %d)...", os.getpid())
        self.running = True

        # Configurar servidor IPC
        self.ipc_server.register_handler("PING", lambda p: self.handle_ipc_command("PING", p))
        self.ipc_server.register_handler("ESTADO_DEMONIO", lambda p: self.handle_ipc_command("ESTADO_DEMONIO", p))
        self.ipc_server.register_handler("FORZAR_RESPALDO", lambda p: self.handle_ipc_command("FORZAR_RESPALDO", p))
        self.ipc_server.register_handler("VERIFICAR_ALERTAS", lambda p: self.handle_ipc_command("VERIFICAR_ALERTAS", p))
        self.ipc_server.start()

        # Registrar hooks de señales POSIX (SO-04)
        signal_manager.register_shutdown_hook(self.stop)
        signal_manager.register_reload_hook(self.config.reload)
        signal_manager.setup()

        # Realizar chequeo inicial de alertas al encender
        self.check_alerts()

        # Bucle principal de planificación
        check_interval = int(self.config.get("demonio", "intervalo_chequeo_segundos", default=3600))
        backup_hours = int(self.config.get("demonio", "intervalo_respaldo_horas", default=24))

        last_check = time.time()
        last_auto_backup = time.time()

        while self.running:
            try:
                time.sleep(5)
                now = time.time()

                # Chequeo periódico de alertas
                if now - last_check >= check_interval:
                    self.check_alerts()
                    last_check = now

                # Chequeo periódico de respaldos
                if now - last_auto_backup >= (backup_hours * 3600):
                    self.perform_backup()
                    last_auto_backup = now

            except (KeyboardInterrupt, SystemExit):
                break
            except Exception as e:
                logger.error(f"Error inesperado en ciclo del demonio: {e}")

        self.stop()

    def stop(self):
        """Parada limpia del demonio."""
        if not self.running:
            return
        logger.info("Deteniendo prestamos-daemon...")
        self.running = False
        self.ipc_server.stop()
        logger.info("prestamos-daemon detenido correctamente.")


def main():
    daemon = PrestamosDaemon()
    daemon.start()


if __name__ == "__main__":
    main()


