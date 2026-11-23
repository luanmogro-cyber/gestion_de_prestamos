import os
import sys
import errno
import sqlite3
import logging
import shutil
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import Generator, Optional

from backend.common.config import ConfigManager

logger = logging.getLogger("prestamos.database")

# Detección de fcntl para POSIX Linux
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False


class FileSystemError(Exception):
    """Excepción base para errores de sistema de archivos (SO-10)."""
    pass

class DiskFullError(FileSystemError):
    """ENOSPC: Disco lleno."""
    pass

class PermissionDeniedError(FileSystemError):
    """EACCES / EPERM: Permisos denegados."""
    pass

class FileNotFoundError(FileSystemError):
    """ENOENT: Archivo no encontrado."""
    pass


class DatabaseManager:
    """
    Gestor de base de datos SQLite con transacciones ACID,
    control de concurrencia mediante fcntl.flock (SO-05, SO-10)
    y captura rigurosa de errores de sistema de archivos.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: Optional[Path] = None):
        if getattr(self, "_initialized", False):
            return

        self.config = ConfigManager()
        self.db_path = db_path or self.config.db_path
        self.lock_file_path = self.db_path.with_suffix(".lock")
        self._ensure_paths()
        self._initialized = True

    def _ensure_paths(self):
        """Garantiza la creación de carpetas con permisos 700 y archivo con 600."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(self.db_path.parent, 0o700)
            except (OSError, NotImplementedError):
                pass
        except OSError as e:
            self._handle_fs_error(e, f"Creando directorio base para BD: {self.db_path.parent}")

    def _handle_fs_error(self, e: OSError, action_desc: str):
        """Mapea excepciones de sistema de archivos POSIX (SO-10)."""
        logger.error(f"Error de sistema de archivos durante '{action_desc}': {e} (errno: {getattr(e, 'errno', 'N/A')})")
        if getattr(e, "errno", None) == errno.ENOSPC:
            raise DiskFullError(f"No hay espacio suficiente en el disco para completar la operación: {action_desc}") from e
        elif getattr(e, "errno", None) in (errno.EACCES, errno.EPERM):
            raise PermissionDeniedError(f"Permiso denegado por el sistema operativo durante: {action_desc}") from e
        elif getattr(e, "errno", None) == errno.ENOENT:
            raise FileNotFoundError(f"Archivo o ruta inexistente durante: {action_desc}") from e
        else:
            raise FileSystemError(f"Error de E/S en sistema de archivos ({e})") from e

    @contextmanager
    def _file_lock(self, exclusive: bool = True) -> Generator[None, None, None]:
        """
        Aplica bloqueo fcntl.flock sobre el archivo de lock para garantizar
        que múltiples procesos (GUI y Demonio) operen de forma segura.
        """
        lock_fd = None
        if HAS_FCNTL:
            try:
                lock_mode = os.O_RDWR | os.O_CREAT
                lock_fd = os.open(str(self.lock_file_path), lock_mode, 0o600)
                try:
                    os.chmod(self.lock_file_path, 0o600)
                except (OSError, NotImplementedError):
                    pass

                operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                fcntl.flock(lock_fd, operation)
            except OSError as e:
                if lock_fd is not None:
                    try:
                        os.close(lock_fd)
                    except OSError:
                        pass
                self._handle_fs_error(e, f"Adquiriendo bloqueo flock en {self.lock_file_path}")

        try:
            yield
        finally:
            if HAS_FCNTL and lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    os.close(lock_fd)
                except OSError as e:
                    logger.warning(f"Error liberando bloqueo flock: {e}")

    @contextmanager
    def connection(self, exclusive_lock: bool = False) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager para conexión SQLite con transacciones ACID y flock.
        """
        with self._file_lock(exclusive=exclusive_lock):
            conn = None
            try:
                # Activar pragmas de rendimiento y seguridad transaccional
                conn = sqlite3.connect(
                    str(self.db_path),
                    timeout=30.0,
                    detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
                )
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON;")
                conn.execute("PRAGMA journal_mode = WAL;")  # Write-Ahead Logging para concurrencia
                conn.execute("PRAGMA synchronous = NORMAL;")

                # Asegurar permisos 600 en el archivo de base de datos
                if self.db_path.exists():
                    try:
                        os.chmod(self.db_path, 0o600)
                    except (OSError, NotImplementedError):
                        pass

                yield conn

                if exclusive_lock:
                    conn.commit()
            except sqlite3.OperationalError as e:
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                err_msg = str(e).lower()
                if "disk" in err_msg or "full" in err_msg:
                    raise DiskFullError("Disco lleno detectado por SQLite al escribir datos.") from e
                elif "readonly" in err_msg or "permission" in err_msg:
                    raise PermissionDeniedError("Base de datos en modo solo lectura o sin permisos de escritura.") from e
                logger.error(f"Error operacional de SQLite: {e}")
                raise
            except OSError as e:
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                self._handle_fs_error(e, "Operación sobre base de datos SQLite")
            except Exception as e:
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                logger.error(f"Error durante transacción de base de datos: {e}")
                raise
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def create_backup(self, custom_dest_dir: Optional[Path] = None) -> Path:
        """
        Genera un respaldo íntegro y consistente de la base de datos (SO-05: permisos 600).
        """
        backup_dir = custom_dest_dir or self.config.backup_dir
        backup_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(backup_dir, 0o700)
        except (OSError, NotImplementedError):
            pass

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"prestamos_backup_{timestamp}.db"
        dest_path = backup_dir / backup_filename

        with self.connection(exclusive_lock=True) as src_conn:
            try:
                dest_conn = sqlite3.connect(str(dest_path))
                with dest_conn:
                    src_conn.backup(dest_conn, pages=100)
                dest_conn.close()

                try:
                    os.chmod(dest_path, 0o600)
                except (OSError, NotImplementedError):
                    pass

                logger.info(f"Respaldo de base de datos generado con éxito: {dest_path}")
                self._rotate_backups(backup_dir)
                return dest_path
            except OSError as e:
                if dest_path.exists():
                    dest_path.unlink(missing_ok=True)
                self._handle_fs_error(e, f"Creando respaldo en {dest_path}")
            except Exception as e:
                if dest_path.exists():
                    dest_path.unlink(missing_ok=True)
                logger.error(f"Error inesperado al crear respaldo: {e}")
                raise

    def _rotate_backups(self, backup_dir: Path):
        """Mantiene únicamente los últimos N respaldos configurados."""
        try:
            max_backups = int(self.config.get("demonio", "max_respaldos_guardados", default=15))
            backups = sorted(backup_dir.glob("prestamos_backup_*.db"), key=os.path.getmtime, reverse=True)
            if len(backups) > max_backups:
                for b in backups[max_backups:]:
                    try:
                        b.unlink(missing_ok=True)
                        logger.info(f"Respaldo antiguo eliminado por rotación: {b.name}")
                    except OSError as e:
                        logger.warning(f"No se pudo eliminar respaldo antiguo {b}: {e}")
        except Exception as e:
            logger.error(f"Error en rotación de respaldos: {e}")

    def restore_backup(self, backup_file_path: Path):
        """Restaura la base de datos a partir de un archivo de respaldo."""
        if not backup_file_path.exists():
            raise FileNotFoundError(f"El archivo de respaldo no existe: {backup_file_path}")

        with self._file_lock(exclusive=True):
            try:
                # Crear copia de seguridad preventiva antes de sobreescribir
                temp_pre_restore = self.db_path.with_suffix(".pre_restore.bak")
                if self.db_path.exists():
                    shutil.copy2(self.db_path, temp_pre_restore)

                src_conn = sqlite3.connect(str(backup_file_path))
                dest_conn = sqlite3.connect(str(self.db_path))
                with dest_conn:
                    src_conn.backup(dest_conn)
                src_conn.close()
                dest_conn.close()

                if temp_pre_restore.exists():
                    temp_pre_restore.unlink(missing_ok=True)

                try:
                    os.chmod(self.db_path, 0o600)
                except (OSError, NotImplementedError):
                    pass
                logger.info(f"Base de datos restaurada exitosamente desde {backup_file_path}")
            except OSError as e:
                self._handle_fs_error(e, f"Restaurando base de datos desde {backup_file_path}")
            except Exception as e:
                logger.error(f"Fallo al restaurar respaldo: {e}")
                raise


