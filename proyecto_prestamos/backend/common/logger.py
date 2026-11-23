import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logger(name: str = "prestamos", log_file_name: str = "prestamos.log") -> logging.Logger:
    """
    Configura y retorna un logger con RotatingFileHandler (SO-06).
    Niveles: INFO, WARNING y ERROR.
    Permisos de archivos de logs: 600, directorio 700.
    """
    xdg_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    logs_dir = xdg_data / "gestion_prestamos" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(logs_dir, 0o700)
    except (OSError, NotImplementedError):
        pass

    log_path = logs_dir / log_file_name

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        # Formato detallado de log POSIX
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(process)d] [%(levelname)s] [%(name)s:%(filename)s:%(lineno)d]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # RotatingFileHandler: 5 MB por archivo, rota hasta 5 respaldos
        file_handler = RotatingFileHandler(
            filename=str(log_path),
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Asegurar permisos 600 en el archivo de log si existe
        if log_path.exists():
            try:
                os.chmod(log_path, 0o600)
            except (OSError, NotImplementedError):
                pass

        # StreamHandler para consola (útil durante ejecución directa / depuración)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger

app_logger = setup_logger("prestamos.app")


