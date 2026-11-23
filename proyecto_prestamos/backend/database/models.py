import logging
import sqlite3
import bcrypt
from datetime import datetime
from backend.database.db_manager import DatabaseManager

logger = logging.getLogger("prestamos.models")

SCHEMA_SQL = """
-- Tabla de Usuarios del Sistema (PR-01, PR-02)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('Administrador', 'Cajero')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Tabla de Clientes (PR-03 a PR-06)
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type TEXT NOT NULL,
    doc_number TEXT UNIQUE NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    birth_date TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    address TEXT NOT NULL,
    occupation TEXT NOT NULL,
    monthly_income TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Tabla de Préstamos (PR-07 a PR-12)
CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    principal TEXT NOT NULL,
    annual_interest_rate TEXT NOT NULL,
    installments_count INTEGER NOT NULL,
    periodicity TEXT NOT NULL CHECK (periodicity IN ('semanal', 'quincenal', 'mensual')),
    disbursement_date TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('frances', 'aleman')),
    commission_type TEXT CHECK (commission_type IN ('porcentaje', 'fijo', 'ninguna')),
    commission_value TEXT NOT NULL DEFAULT '0.00',
    total_amount TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'activo' CHECK (status IN ('simulado', 'activo', 'en_mora', 'cancelado', 'castigado')),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE RESTRICT
);

-- Tabla de Cuotas / Calendario de Amortización (PR-13 a PR-16)
CREATE TABLE IF NOT EXISTS installments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id INTEGER NOT NULL,
    number INTEGER NOT NULL,
    due_date TEXT NOT NULL,
    capital_expected TEXT NOT NULL,
    interest_expected TEXT NOT NULL,
    total_expected TEXT NOT NULL,
    remaining_principal TEXT NOT NULL,
    capital_paid TEXT NOT NULL DEFAULT '0.00',
    interest_paid TEXT NOT NULL DEFAULT '0.00',
    late_fee_paid TEXT NOT NULL DEFAULT '0.00',
    status TEXT NOT NULL DEFAULT 'pendiente' CHECK (status IN ('pendiente', 'pagada', 'parcial', 'vencida')),
    paid_date TEXT,
    FOREIGN KEY (loan_id) REFERENCES loans (id) ON DELETE CASCADE
);

-- Tabla de Pagos Realizados (PR-17 a PR-20)
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id INTEGER NOT NULL,
    installment_id INTEGER,
    amount TEXT NOT NULL,
    payment_date TEXT NOT NULL,
    payment_method TEXT NOT NULL CHECK (payment_method IN ('efectivo', 'transferencia', 'tarjeta', 'cheque')),
    late_fee_allocated TEXT NOT NULL DEFAULT '0.00',
    interest_allocated TEXT NOT NULL DEFAULT '0.00',
    capital_allocated TEXT NOT NULL DEFAULT '0.00',
    notes TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (loan_id) REFERENCES loans (id) ON DELETE RESTRICT,
    FOREIGN KEY (installment_id) REFERENCES installments (id) ON DELETE SET NULL
);

-- Tabla de Registro de Auditoría
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    username TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT
);

-- Índices para optimización de consultas
CREATE INDEX IF NOT EXISTS idx_clients_doc ON clients(doc_number);
CREATE INDEX IF NOT EXISTS idx_loans_client ON loans(client_id);
CREATE INDEX IF NOT EXISTS idx_loans_status ON loans(status);
CREATE INDEX IF NOT EXISTS idx_installments_loan ON installments(loan_id);
CREATE INDEX IF NOT EXISTS idx_installments_due ON installments(due_date);
CREATE INDEX IF NOT EXISTS idx_installments_status ON installments(status);
CREATE INDEX IF NOT EXISTS idx_payments_loan ON payments(loan_id);
"""

def initialize_database(db_manager: DatabaseManager):
    """
    Crea las tablas, índices y usuario inicial por defecto si no existen.
    Usuario default:
      Username: admin
      Password: admin1234 (hasheado con bcrypt)
      Rol: Administrador
    """
    logger.info("Inicializando esquema de base de datos...")
    with db_manager.connection(exclusive_lock=True) as conn:
        cursor = conn.cursor()
        cursor.executescript(SCHEMA_SQL)

        # Sembrar usuario administrador inicial si la tabla está vacía
        cursor.execute("SELECT COUNT(*) as cnt FROM users;")
        if cursor.fetchone()["cnt"] == 0:
            salt = bcrypt.gensalt(rounds=12)
            hashed_pwd = bcrypt.hashpw(b"admin1234", salt).decode("utf-8")
            cursor.execute(
                """
                INSERT INTO users (username, password_hash, full_name, role, is_active)
                VALUES (?, ?, ?, ?, 1)
                """,
                ("admin", hashed_pwd, "Administrador del Sistema", "Administrador")
            )
            logger.info("Usuario administrador por defecto creado ('admin' / 'admin1234').")

        # Sembrar usuario cajero de prueba si solo hay 1 usuario
        cursor.execute("SELECT COUNT(*) as cnt FROM users;")
        if cursor.fetchone()["cnt"] == 1:
            salt = bcrypt.gensalt(rounds=12)
            cajero_pwd = bcrypt.hashpw(b"cajero1234", salt).decode("utf-8")
            cursor.execute(
                """
                INSERT INTO users (username, password_hash, full_name, role, is_active)
                VALUES (?, ?, ?, ?, 1)
                """,
                ("cajero", cajero_pwd, "Cajero Principal", "Cajero")
            )
            logger.info("Usuario cajero por defecto creado ('cajero' / 'cajero1234').")
    
    logger.info("Esquema de base de datos verificado y listo.")


