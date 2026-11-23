import logging
from typing import Optional, Dict, Any, List
import bcrypt
from backend.database.db_manager import DatabaseManager

logger = logging.getLogger("prestamos.auth")

class AuthService:
    """
    Servicio de autenticación, gestión de usuarios y control de acceso (PR-01, PR-02).
    Roles soportados: 'Administrador' y 'Cajero'.
    """
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Verifica credenciales contra el hash bcrypt."""
        username = username.strip()
        with self.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username, password_hash, full_name, role, is_active FROM users WHERE username = ?;",
                (username,)
            )
            user = cursor.fetchone()

            if not user:
                logger.warning(f"Intento fallido de login: usuario '{username}' no existe.")
                return None

            if not user["is_active"]:
                logger.warning(f"Intento de login con usuario inactivo: '{username}'.")
                return None

            # Validación de hash bcrypt
            pwd_bytes = password.encode("utf-8")
            hash_bytes = user["password_hash"].encode("utf-8")
            
            if bcrypt.checkpw(pwd_bytes, hash_bytes):
                logger.info(f"Autenticación exitosa para el usuario: '{username}' (Rol: {user['role']}).")
                self._log_audit(user["username"], "LOGIN", "Inicio de sesión exitoso.")
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "full_name": user["full_name"],
                    "role": user["role"]
                }
            else:
                logger.warning(f"Contraseña incorrecta para el usuario: '{username}'.")
                return None

    def create_user(self, username: str, password: str, full_name: str, role: str, actor_username: str) -> int:
        """Crea un nuevo usuario en la base de datos."""
        username = username.strip()
        if role not in ("Administrador", "Cajero"):
            raise ValueError("El rol debe ser 'Administrador' o 'Cajero'.")
        if len(password) < 6:
            raise ValueError("La contraseña debe tener al menos 6 caracteres.")

        salt = bcrypt.gensalt(rounds=12)
        pwd_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

        with self.db.connection(exclusive_lock=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (username, password_hash, full_name, role, is_active)
                VALUES (?, ?, ?, ?, 1);
                """,
                (username, pwd_hash, full_name.strip(), role)
            )
            new_id = cursor.lastrowid
            self._log_audit(actor_username, "CREAR_USUARIO", f"Usuario {username} creado con rol {role}.")
            logger.info(f"Usuario '{username}' creado exitosamente por '{actor_username}'.")
            return new_id

    def change_password(self, username: str, new_password: str, actor_username: str):
        if len(new_password) < 6:
            raise ValueError("La nueva contraseña debe tener al menos 6 caracteres.")

        salt = bcrypt.gensalt(rounds=12)
        pwd_hash = bcrypt.hashpw(new_password.encode("utf-8"), salt).decode("utf-8")

        with self.db.connection(exclusive_lock=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?;",
                (pwd_hash, username)
            )
            self._log_audit(actor_username, "CAMBIO_PASSWORD", f"Contraseña actualizada para {username}.")
            logger.info(f"Contraseña modificada para '{username}' por '{actor_username}'.")

    def list_users(self) -> List[Dict[str, Any]]:
        with self.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, full_name, role, is_active, created_at FROM users ORDER BY id ASC;")
            return [dict(r) for r in cursor.fetchall()]

    def _log_audit(self, username: str, action: str, details: str):
        try:
            with self.db.connection(exclusive_lock=True) as conn:
                conn.execute(
                    "INSERT INTO audit_logs (username, action, details) VALUES (?, ?, ?);",
                    (username, action, details)
                )
        except Exception as e:
            logger.warning(f"No se pudo registrar log de auditoría: {e}")


