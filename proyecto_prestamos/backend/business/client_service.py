import re
import logging
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, Any, List, Tuple
from backend.database.db_manager import DatabaseManager

logger = logging.getLogger("prestamos.clients")

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")
PHONE_REGEX = re.compile(r"^\+?[\d]{7,15}$")
DOC_REGEX = re.compile(r"^[A-Za-z0-9-]{4,20}$")

def sanitize_money_string(value: Any) -> str:
    """Convierte entradas con formatos como '$ 2.500.000', '2,500,000' o '2500000' a formato Decimal estándar."""
    val_str = str(value).strip().replace("$", "").replace(" ", "")
    if not val_str:
        return "0.00"

    # Si tiene puntos como separadores de miles (ej. 2.500.000 o 2.500.000,00)
    if "." in val_str and "," in val_str:
        val_str = val_str.replace(".", "").replace(",", ".")
    elif val_str.count(".") > 1:
        val_str = val_str.replace(".", "")
    elif "," in val_str:
        val_str = val_str.replace(",", ".")

    return val_str


class ClientService:
    """
    CRUD y validaciones de clientes (PR-03 a PR-06).
    Maneja desactivación lógica, paginación con filtros y sanitización robusta.
    """
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()

    def validate_and_sanitize_client_data(self, data: Dict[str, Any], is_update: bool = False) -> Dict[str, Any]:
        """Valida y sanitiza rigurosamente los campos de cliente antes de persistir."""
        doc_type = data.get("doc_type", "").strip()
        doc_number = data.get("doc_number", "").replace(".", "").replace(" ", "").strip()
        first_name = data.get("first_name", "").strip()
        last_name = data.get("last_name", "").strip()
        birth_date = data.get("birth_date", "").strip()
        phone = data.get("phone", "").replace(" ", "").replace("-", "").strip()
        email = data.get("email", "").strip()
        raw_income = data.get("monthly_income", "0")

        if not doc_type:
            raise ValueError("El tipo de documento es obligatorio.")
        if not doc_number or not DOC_REGEX.match(doc_number):
            raise ValueError("El número de documento debe contener entre 4 y 20 caracteres alfanuméricos válidos.")
        if not first_name or len(first_name) < 2:
            raise ValueError("El nombre debe tener al menos 2 caracteres.")
        if not last_name or len(last_name) < 2:
            raise ValueError("El apellido debe tener al menos 2 caracteres.")
        if not phone or not PHONE_REGEX.match(phone):
            raise ValueError("El teléfono debe contener entre 7 y 15 dígitos numéricos.")
        if email and not EMAIL_REGEX.match(email):
            raise ValueError("El formato del correo electrónico no es válido (ej: usuario@dominio.com).")

        # Validar fecha de nacimiento y mayoría de edad
        try:
            b_date = datetime.strptime(birth_date, "%Y-%m-%d").date()
            today = date.today()
            age = today.year - b_date.year - ((today.month, today.day) < (b_date.month, b_date.day))
            if age < 18:
                raise ValueError(f"El cliente debe ser mayor de edad (tiene {age} años).")
        except ValueError as e:
            if "mayor de edad" in str(e):
                raise
            raise ValueError("La fecha de nacimiento debe tener formato AAAA-MM-DD.")

        # Sanitizar y validar ingresos mensuales con Decimal
        sanitized_income = sanitize_money_string(raw_income)
        try:
            income_dec = Decimal(sanitized_income)
            if income_dec <= Decimal("0.00"):
                raise ValueError("Los ingresos mensuales deben ser mayores a cero ($0.00).")
        except InvalidOperation:
            raise ValueError(f"El valor de ingresos '{raw_income}' no es válido.")

        return {
            "doc_type": doc_type,
            "doc_number": doc_number,
            "first_name": first_name,
            "last_name": last_name,
            "birth_date": birth_date,
            "phone": phone,
            "email": email or "sin_correo@prestamos.local",
            "address": data.get("address", "").strip(),
            "occupation": data.get("occupation", "").strip(),
            "monthly_income": str(income_dec.quantize(Decimal("0.01"))),
        }

    def create_client(self, data: Dict[str, Any], actor_username: str) -> int:
        clean_data = self.validate_and_sanitize_client_data(data)
        doc_number = clean_data["doc_number"]

        with self.db.connection(exclusive_lock=True) as conn:
            cursor = conn.cursor()
            # Verificar si ya existe el número de documento
            cursor.execute("SELECT id, is_active FROM clients WHERE doc_number = ?;", (doc_number,))
            existing = cursor.fetchone()
            if existing:
                if not existing["is_active"]:
                    # Reactivar lógicamente si estaba desactivado
                    cursor.execute(
                        """
                        UPDATE clients SET
                            doc_type = ?, first_name = ?, last_name = ?, birth_date = ?,
                            phone = ?, email = ?, address = ?, occupation = ?,
                            monthly_income = ?, is_active = 1, updated_at = datetime('now', 'localtime')
                        WHERE id = ?;
                        """,
                        (
                            clean_data["doc_type"], clean_data["first_name"], clean_data["last_name"],
                            clean_data["birth_date"], clean_data["phone"], clean_data["email"],
                            clean_data["address"], clean_data["occupation"], clean_data["monthly_income"],
                            existing["id"]
                        )
                    )
                    conn.execute(
                        "INSERT INTO audit_logs (username, action, details) VALUES (?, ?, ?);",
                        (actor_username, "REACTIVAR_CLIENTE", f"Cliente ID {existing['id']} reactivado.")
                    )
                    logger.info(f"Cliente {doc_number} reactivado por {actor_username}.")
                    return existing["id"]

                raise ValueError(f"Ya existe un cliente registrado con el documento {doc_number}.")

            cursor.execute(
                """
                INSERT INTO clients (
                    doc_type, doc_number, first_name, last_name, birth_date,
                    phone, email, address, occupation, monthly_income, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
                """,
                (
                    clean_data["doc_type"],
                    clean_data["doc_number"],
                    clean_data["first_name"],
                    clean_data["last_name"],
                    clean_data["birth_date"],
                    clean_data["phone"],
                    clean_data["email"],
                    clean_data["address"],
                    clean_data["occupation"],
                    clean_data["monthly_income"]
                )
            )
            client_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO audit_logs (username, action, details) VALUES (?, ?, ?);",
                (actor_username, "CREAR_CLIENTE", f"Cliente ID {client_id} ({doc_number}) registrado.")
            )
            logger.info(f"Cliente {doc_number} creado por {actor_username} (ID: {client_id}).")
            return client_id

    def update_client(self, client_id: int, data: Dict[str, Any], actor_username: str):
        clean_data = self.validate_and_sanitize_client_data(data, is_update=True)
        doc_number = clean_data["doc_number"]

        with self.db.connection(exclusive_lock=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM clients WHERE doc_number = ? AND id != ?;", (doc_number, client_id))
            if cursor.fetchone():
                raise ValueError(f"El documento {doc_number} ya pertenece a otro cliente.")

            cursor.execute(
                """
                UPDATE clients SET
                    doc_type = ?, doc_number = ?, first_name = ?, last_name = ?,
                    birth_date = ?, phone = ?, email = ?, address = ?,
                    occupation = ?, monthly_income = ?, updated_at = datetime('now', 'localtime')
                WHERE id = ?;
                """,
                (
                    clean_data["doc_type"],
                    clean_data["doc_number"],
                    clean_data["first_name"],
                    clean_data["last_name"],
                    clean_data["birth_date"],
                    clean_data["phone"],
                    clean_data["email"],
                    clean_data["address"],
                    clean_data["occupation"],
                    clean_data["monthly_income"],
                    client_id
                )
            )
            conn.execute(
                "INSERT INTO audit_logs (username, action, details) VALUES (?, ?, ?);",
                (actor_username, "ACTUALIZAR_CLIENTE", f"Cliente ID {client_id} actualizado.")
            )
            logger.info(f"Cliente {client_id} actualizado por {actor_username}.")

    def delete_client(self, client_id: int, actor_username: str):
        """Desactivación lógica de cliente (PR-04)."""
        with self.db.connection(exclusive_lock=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM loans WHERE client_id = ? AND status IN ('activo', 'en_mora');",
                (client_id,)
            )
            if cursor.fetchone()["cnt"] > 0:
                raise ValueError("No se puede desactivar un cliente con préstamos activos o en mora.")

            cursor.execute("UPDATE clients SET is_active = 0, updated_at = datetime('now', 'localtime') WHERE id = ?;", (client_id,))
            conn.execute(
                "INSERT INTO audit_logs (username, action, details) VALUES (?, ?, ?);",
                (actor_username, "DESACTIVAR_CLIENTE", f"Cliente ID {client_id} desactivado lógicamente.")
            )
            logger.info(f"Cliente ID {client_id} desactivado lógicamente por {actor_username}.")

    def get_client(self, client_id: int) -> Optional[Dict[str, Any]]:
        with self.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clients WHERE id = ?;", (client_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_clients(self, page: int = 1, page_size: int = 10, search_query: str = "") -> Tuple[List[Dict[str, Any]], int]:
        search_query = search_query.strip()
        offset = max(0, (page - 1) * page_size)

        with self.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()
            if search_query:
                param = f"%{search_query}%"
                cursor.execute(
                    """
                    SELECT COUNT(*) as total FROM clients
                    WHERE is_active = 1 AND (doc_number LIKE ? OR first_name LIKE ? OR last_name LIKE ?);
                    """,
                    (param, param, param)
                )
                total = cursor.fetchone()["total"]

                cursor.execute(
                    """
                    SELECT * FROM clients
                    WHERE is_active = 1 AND (doc_number LIKE ? OR first_name LIKE ? OR last_name LIKE ?)
                    ORDER BY id DESC
                    LIMIT ? OFFSET ?;
                    """,
                    (param, param, param, page_size, offset)
                )
            else:
                cursor.execute("SELECT COUNT(*) as total FROM clients WHERE is_active = 1;")
                total = cursor.fetchone()["total"]

                cursor.execute(
                    "SELECT * FROM clients WHERE is_active = 1 ORDER BY id DESC LIMIT ? OFFSET ?;",
                    (page_size, offset)
                )

            return [dict(r) for r in cursor.fetchall()], total

