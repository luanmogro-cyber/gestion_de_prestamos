import signal
import sys
import logging
from typing import Callable, List

logger = logging.getLogger("prestamos.signals")

class PosixSignalManager:
    """
    Manejo de Señales POSIX (SO-04):
    - SIGTERM y SIGINT: Terminan ordenadamente liberando locks SQLite, cerrando sockets Unix y transacciones.
    - SIGHUP: Recarga dinámica de configuración sin reiniciar.
    """
    def __init__(self):
        self._shutdown_callbacks: List[Callable[[], None]] = []
        self._reload_callbacks: List[Callable[[], None]] = []
        self._signals_registered = False

    def register_shutdown_hook(self, callback: Callable[[], None]):
        """Registra funciones que deben ejecutarse ante SIGTERM o SIGINT."""
        self._shutdown_callbacks.append(callback)

    def register_reload_hook(self, callback: Callable[[], None]):
        """Registra funciones que deben ejecutarse ante SIGHUP."""
        self._reload_callbacks.append(callback)

    def setup(self):
        if self._signals_registered:
            return

        # Solo registrar si estamos en el hilo principal
        try:
            signal.signal(signal.SIGINT, self._handle_termination)
            signal.signal(signal.SIGTERM, self._handle_termination)

            # SIGHUP solo existe en sistemas Unix / POSIX
            if hasattr(signal, "SIGHUP"):
                signal.signal(signal.SIGHUP, self._handle_reload)
            
            self._signals_registered = True
            logger.info("Manejadores de señales POSIX (SIGTERM, SIGINT, SIGHUP) registrados correctamente.")
        except ValueError as e:
            logger.warning(f"No se pudieron registrar manejadores de señales (no es hilo principal): {e}")

    def _handle_termination(self, signum, frame):
        sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
        logger.warning(f"Señal de terminación recibida ({sig_name}). Iniciando apagado ordenado...")
        for callback in self._shutdown_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error ejecutando hook de apagado: {e}")
        logger.info("Cierre ordenado completado. Saliendo con código 0.")
        sys.exit(0)

    def _handle_reload(self, signum, frame):
        logger.info("Señal SIGHUP recibida. Ejecutando recarga dinámica de componentes...")
        for callback in self._reload_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error ejecutando hook de recarga (SIGHUP): {e}")

signal_manager = PosixSignalManager()


