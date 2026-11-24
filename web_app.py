import os
import sys
import json
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from decimal import Decimal
from datetime import datetime, date
from urllib.parse import parse_qs, urlparse

# Ensure project modules can be loaded
current_dir = os.path.dirname(os.path.abspath(__file__))
proyecto_dir = os.path.join(current_dir, "proyecto_prestamos")
if proyecto_dir not in sys.path:
    sys.path.insert(0, proyecto_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from backend.database.db_manager import DatabaseManager
from backend.database.models import initialize_database
from backend.business.client_service import ClientService
from backend.business.loan_calculator import LoanCalculator
from backend.business.payment_service import PaymentService

PORT = int(os.environ.get("PORT", 8080))
DB_PATH = Path(os.environ.get("SQLITE_DB_PATH", os.path.join(current_dir, "prestamos_cloud.db")))

# Inicializar Base de Datos SQLite en la nube
db_manager = DatabaseManager(DB_PATH)
initialize_database(db_manager)
client_service = ClientService(db_manager)
loan_calculator = LoanCalculator(db_manager)
payment_service = PaymentService(db_manager)

# Sembrar datos de demostración si la base de datos está vacía
def seed_demo_data():
    try:
        clients = client_service.list_clients()
        if not clients:
            print("🌱 Sembrando datos demostrativos en la base de datos SQLite...")
            # Cliente 1
            cid1 = client_service.create_client({
                "doc_type": "CC", "doc_number": "100200300",
                "first_name": "Carlos", "last_name": "Mendoza",
                "birth_date": "1992-05-10", "phone": "3001234567",
                "email": "carlos.mendoza@correo.com", "address": "Calle 45 # 12-34",
                "occupation": "Empleado de Empresa", "monthly_income": "3500000"
            }, "admin")

            # Préstamo 1
            lid1 = loan_calculator.create_loan(
                client_id=cid1, principal=Decimal("5000000.00"),
                annual_interest_rate=Decimal("15.00"), installments_count=12,
                periodicity="mensual", method="frances",
                commission_type="ninguna", commission_value=Decimal("0.00"),
                disbursement_date="2026-06-01", actor_username="admin"
            )
            # Abono a capital en préstamo 1
            payment_service.register_payment(
                loan_id=lid1, amount=Decimal("450000.00"), payment_type="cuota",
                payment_method="transferencia", actor_username="cajero"
            )

            # Cliente 2
            cid2 = client_service.create_client({
                "doc_type": "CC", "doc_number": "555666777",
                "first_name": "Ana", "last_name": "Gómez Pérez",
                "birth_date": "1988-10-15", "phone": "3109876543",
                "email": "ana.gomez@comercio.com", "address": "Carrera 70 # 33-10",
                "occupation": "Comerciante Independiente", "monthly_income": "5200000"
            }, "admin")

            # Préstamo 2
            loan_calculator.create_loan(
                client_id=cid2, principal=Decimal("10000000.00"),
                annual_interest_rate=Decimal("18.00"), installments_count=24,
                periodicity="mensual", method="aleman",
                commission_type="ninguna", commission_value=Decimal("0.00"),
                disbursement_date="2026-07-15", actor_username="admin"
            )

            # Cliente 3 (Con crédito saldado para verificar aviso)
            cid3 = client_service.create_client({
                "doc_type": "CC", "doc_number": "777888999",
                "first_name": "Mario", "last_name": "Restrepo",
                "birth_date": "1995-02-20", "phone": "3124445566",
                "email": "mario.restrepo@empresa.com", "address": "Diagonal 20 # 5-60",
                "occupation": "Ingeniero de Sistemas", "monthly_income": "6000000"
            }, "admin")

            lid3 = loan_calculator.create_loan(
                client_id=cid3, principal=Decimal("1000000.00"),
                annual_interest_rate=Decimal("10.00"), installments_count=2,
                periodicity="mensual", method="frances",
                commission_type="ninguna", commission_value=Decimal("0.00"),
                disbursement_date="2026-01-01", actor_username="admin"
            )
            # Liquidar préstamo 3 por completo
            payment_service.register_payment(
                loan_id=lid3, amount=Decimal("1200000.00"), payment_type="cuota",
                payment_method="efectivo", actor_username="cajero"
            )
            print("✅ Datos iniciales sembrados con éxito.")
    except Exception as e:
        print(f"Nota de siembra de datos: {e}")

seed_demo_data()

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

class CloudLoanManagementHandler(SimpleHTTPRequestHandler):
    def _send_json(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, cls=DecimalEncoder, indent=2).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # 1. Health check para Railway
        if parsed.path in ["/health", "/api/health"]:
            self._send_json({
                "status": "healthy",
                "service": "Sistema de Gestion de Prestamos",
                "version": "2.1.0",
                "database": "SQLite3 WAL Activa",
                "platform": "Railway Cloud"
            })
            return

        # 2. Búsqueda multicriterio (Foto 2 de la Pizarra)
        if parsed.path == "/api/loans/search":
            q = params.get("q", [""])[0]
            results = payment_service.search_loans_and_clients(q)
            self._send_json({"count": len(results), "loans": results})
            return

        # 3. Listar clientes
        if parsed.path == "/api/clients":
            clients = client_service.list_clients()
            self._send_json({"clients": clients})
            return

        # 4. Historial de cuotas y pagos de un préstamo
        if parsed.path == "/api/payments":
            loan_id = params.get("loan_id", [None])[0]
            lid = int(loan_id) if loan_id else None
            payments = payment_service.list_payments(lid)
            self._send_json({"payments": payments})
            return

        # 5. Desglose exigible de un crédito
        if parsed.path == "/api/loans/debt":
            loan_id = int(params.get("loan_id", [0])[0])
            breakdown = payment_service.get_pending_debt_breakdown(loan_id)
            self._send_json(breakdown)
            return

        # 6. Estadísticas de Base de Datos para el profesor
        if parsed.path == "/api/db/stats":
            with db_manager.connection(exclusive_lock=False) as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) as c FROM clients;")
                clients_cnt = cur.fetchone()["c"]
                cur.execute("SELECT COUNT(*) as c FROM loans;")
                loans_cnt = cur.fetchone()["c"]
                cur.execute("SELECT COUNT(*) as c FROM payments;")
                payments_cnt = cur.fetchone()["c"]
                cur.execute("SELECT COUNT(*) as c FROM audit_logs;")
                logs_cnt = cur.fetchone()["c"]
            self._send_json({
                "database_file": DB_PATH,
                "engine": "SQLite3 con modo WAL (Write-Ahead Logging)",
                "concurrency": "POSIX fcntl.flock advisory locking",
                "clients_count": clients_cnt,
                "loans_count": loans_cnt,
                "payments_count": payments_cnt,
                "audit_logs_count": logs_cnt
            })
            return

        # 7. Interfaz Web Interactiva Completa (HTML/JS/CSS)
        if parsed.path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_APP.encode("utf-8"))
            return

        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        data = json.loads(body) if body else {}

        # 1. Registrar Pago / Abono (Capital, Interés o Cuota)
        if parsed.path == "/api/payments/register":
            try:
                res = payment_service.register_payment(
                    loan_id=int(data["loan_id"]),
                    amount=Decimal(str(data["amount"])),
                    payment_type=data.get("payment_type", "cuota"),
                    payment_method=data.get("payment_method", "efectivo"),
                    notes=data.get("notes", ""),
                    actor_username=data.get("username", "cajero")
                )
                self._send_json({"success": True, "result": res})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status_code=400)
            return

        # 2. Eliminar un pago y revertir saldos
        if parsed.path == "/api/payments/delete":
            try:
                payment_id = int(data["payment_id"])
                payment_service.delete_payment(payment_id, actor_username="cajero")
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status_code=400)
            return

        # 3. Crear nuevo cliente
        if parsed.path == "/api/clients/create":
            try:
                cid = client_service.create_client(data, actor_username="admin")
                self._send_json({"success": True, "client_id": cid})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status_code=400)
            return

        # 4. Crear nuevo préstamo
        if parsed.path == "/api/loans/create":
            try:
                lid = loan_calculator.create_loan(
                    client_id=int(data["client_id"]),
                    principal=Decimal(str(data["principal"])),
                    annual_interest_rate=Decimal(str(data["rate"])),
                    installments_count=int(data["installments_count"]),
                    periodicity=data.get("periodicity", "mensual"),
                    method=data.get("method", "frances"),
                    actor_username="admin"
                )
                self._send_json({"success": True, "loan_id": lid})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status_code=400)
            return

        self._send_json({"error": "Ruta POST no encontrada"}, status_code=404)


HTML_APP = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sistema de Gestión de Préstamos - Base de Datos en Vivo</title>
    <style>
        :root {
            --navy-dark: #0F2942;
            --navy-primary: #1E3A8A;
            --blue-accent: #1D4ED8;
            --emerald: #059669;
            --emerald-light: #10B981;
            --amber: #D97706;
            --amber-light: #F59E0B;
            --red: #DC2626;
            --bg: #0B1120;
            --card-bg: #111827;
            --card-surface: #1F2937;
            --border: #374151;
            --text-main: #F9FAFB;
            --text-muted: #9CA3AF;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: "Segoe UI", "Inter", -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        header {
            background-color: var(--navy-dark);
            border-bottom: 2px solid var(--navy-primary);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1rem;
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 0.85rem;
        }
        .brand-badge {
            background: linear-gradient(135deg, var(--blue-accent), #38BDF8);
            width: 44px; height: 44px; border-radius: 10px;
            display: flex; align-items: center; justify-content: center;
            font-size: 1.4rem; font-weight: bold;
        }
        .pills { display: flex; gap: 0.75rem; align-items: center; }
        .pill {
            padding: 0.35rem 0.85rem;
            border-radius: 9999px;
            font-size: 0.8rem;
            font-weight: 600;
            display: flex; align-items: center; gap: 0.4rem;
        }
        .pill-live {
            background: rgba(16, 185, 129, 0.15);
            color: var(--emerald-light);
            border: 1px solid rgba(16, 185, 129, 0.4);
        }
        .pill-db {
            background: rgba(56, 189, 248, 0.15);
            color: #38BDF8;
            border: 1px solid rgba(56, 189, 248, 0.4);
        }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }

        /* Tabs de Navegación */
        .tabs-nav {
            background-color: var(--card-bg);
            border-bottom: 1px solid var(--border);
            display: flex;
            padding: 0 2rem;
            gap: 1rem;
            overflow-x: auto;
        }
        .tab-btn {
            background: transparent;
            color: var(--text-muted);
            border: none;
            padding: 1rem 1.25rem;
            font-size: 0.95rem;
            font-weight: 600;
            cursor: pointer;
            border-bottom: 3px solid transparent;
            transition: all 0.2s;
            display: flex; align-items: center; gap: 0.5rem;
        }
        .tab-btn:hover { color: var(--text-main); }
        .tab-btn.active {
            color: #38BDF8;
            border-bottom-color: var(--blue-accent);
        }

        main {
            flex: 1;
            max-width: 1400px;
            width: 100%;
            margin: 0 auto;
            padding: 2rem 1.5rem;
        }
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        /* Búsqueda Didáctica y Minimalista */
        .search-card {
            background-color: var(--card-bg);
            border: 1.5px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }
        .search-card h3 { font-size: 1.2rem; margin-bottom: 0.75rem; color: #E2E8F0; }
        .search-bar { display: flex; gap: 0.75rem; flex-wrap: wrap; }
        .search-input {
            flex: 1; min-width: 280px;
            background-color: var(--bg);
            border: 1.5px solid var(--border);
            color: white;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            font-size: 1rem;
        }
        .search-input:focus { border-color: var(--blue-accent); outline: none; }
        .btn {
            padding: 0.75rem 1.25rem;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.95rem;
            border: none;
            cursor: pointer;
            display: inline-flex; align-items: center; gap: 0.5rem;
            transition: opacity 0.2s;
        }
        .btn:hover { opacity: 0.9; }
        .btn-primary { background-color: var(--blue-accent); color: white; }
        .btn-success { background-color: var(--emerald); color: white; }
        .btn-danger { background-color: var(--red); color: white; }
        .btn-secondary { background-color: #4B5563; color: white; }

        /* Tabla Financiera de Préstamos (Foto 2) */
        .table-responsive {
            background-color: var(--card-bg);
            border: 1.5px solid var(--border);
            border-radius: 12px;
            overflow-x: auto;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.92rem;
        }
        thead {
            background-color: var(--navy-dark);
            border-bottom: 2px solid var(--navy-primary);
        }
        th {
            padding: 0.9rem 1rem;
            color: #F8FAFC;
            font-weight: 700;
            white-space: nowrap;
        }
        td {
            padding: 0.85rem 1rem;
            border-bottom: 1px solid var(--border);
            color: #E2E8F0;
            white-space: nowrap;
        }
        tbody tr:hover { background-color: rgba(255,255,255,0.03); }
        .badge {
            padding: 0.25rem 0.6rem;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
        }
        .badge-saldado { background: rgba(16, 185, 129, 0.2); color: #34D399; border: 1px solid #10B981; }
        .badge-activo { background: rgba(59, 130, 246, 0.2); color: #60A5FA; border: 1px solid #3B82F6; }
        .badge-mora { background: rgba(239, 68, 68, 0.2); color: #F87171; border: 1px solid #EF4444; }

        /* Modales */
        .modal-overlay {
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.75);
            display: none; align-items: center; justify-content: center;
            z-index: 1000; padding: 1rem;
        }
        .modal {
            background: var(--card-bg);
            border: 1.5px solid var(--border);
            border-radius: 14px;
            max-width: 600px; width: 100%;
            padding: 2rem;
            max-height: 90vh;
            overflow-y: auto;
        }
        .modal h2 { font-size: 1.35rem; margin-bottom: 1rem; color: #E2E8F0; }
        .form-group { margin-bottom: 1rem; display: flex; flex-direction: column; gap: 0.35rem; }
        .form-group label { font-size: 0.85rem; color: #CBD5E1; font-weight: 600; }
        .form-group input, .form-group select, .form-group textarea {
            background: var(--bg);
            border: 1.5px solid var(--border);
            color: white;
            padding: 0.7rem;
            border-radius: 8px;
            font-size: 0.95rem;
        }
        .radio-box {
            background: var(--card-surface);
            border: 1.5px solid var(--border);
            border-radius: 8px;
            padding: 0.75rem 1rem;
            margin-bottom: 0.5rem;
            display: flex; align-items: center; gap: 0.75rem;
            cursor: pointer;
        }
        .banner-saldado {
            background: rgba(16, 185, 129, 0.15);
            border: 2px solid #10B981;
            padding: 1.25rem; border-radius: 10px;
            text-align: center; margin-bottom: 1rem;
            color: #34D399; font-weight: bold;
        }
        .clock-live {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid var(--emerald);
            padding: 0.5rem 0.75rem;
            border-radius: 6px;
            color: #34D399;
            font-weight: bold;
            font-size: 0.9rem;
            margin-bottom: 1rem;
            text-align: center;
        }
        footer {
            background: var(--navy-dark);
            border-top: 1px solid var(--navy-primary);
            text-align: center;
            padding: 1.25rem;
            color: var(--text-muted);
            font-size: 0.85rem;
        }
    </style>
</head>
<body>
    <header>
        <div class="brand">
            <div class="brand-badge">🏦</div>
            <div>
                <h2 style="font-size: 1.2rem; font-weight: 700;">Sistema de Gestión de Préstamos</h2>
                <span style="font-size: 0.8rem; color: #94A3B8;">Base de Datos SQLite en la Nube • Sistemas Operativos</span>
            </div>
        </div>
        <div class="pills">
            <div class="pill pill-live"><div class="dot"></div> En línea en Railway</div>
            <div class="pill pill-db">🗄️ SQLite WAL Activa</div>
        </div>
    </header>

    <div class="tabs-nav">
        <button class="tab-btn active" onclick="switchTab('cobranzas')">💳 Cobranzas & Préstamos (Foto 2)</button>
        <button class="tab-btn" onclick="switchTab('clientes')">👥 Directorio de Clientes</button>
        <button class="tab-btn" onclick="switchTab('nuevo_prestamo')">➕ Nuevo Crédito / Simulador</button>
        <button class="tab-btn" onclick="switchTab('basedatos')">🗄️ Base de Datos & Auditoría</button>
    </div>

    <main>
        <!-- TAB 1: COBRANZAS Y PRÉSTAMOS (FOTO 2) -->
        <div id="tab-cobranzas" class="tab-content active">
            <div class="search-card">
                <h3>🔍 Búsqueda Multicriterio de Clientes y Créditos</h3>
                <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 0.75rem;">
                    Escriba el número de documento (cédula), nombre del cliente o número de crédito/pagaré (ej: <code>100200300</code>, <code>Carlos</code>, <code>PAG-0001</code>):
                </p>
                <div class="search-bar">
                    <input type="text" id="searchInput" class="search-input" placeholder="Buscar por Cédula, Nombre o Pagaré..." oninput="loadLoans()">
                    <button class="btn btn-primary" onclick="loadLoans()">Buscar</button>
                    <button class="btn btn-secondary" onclick="clearSearch()">Ver Todos</button>
                </div>
            </div>

            <div style="margin-bottom: 0.75rem; display: flex; justify-content: space-between; align-items: center;">
                <span id="loansCount" style="color: #94A3B8; font-size: 0.9rem; font-weight: 600;">Cargando créditos...</span>
            </div>

            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th>PAGARÉ / CRÉDITO</th>
                            <th>DOCUMENTO</th>
                            <th>NOMBRE</th>
                            <th>MONTO</th>
                            <th>FECHA</th>
                            <th># CUOTA / PLAZO</th>
                            <th>CAPITAL</th>
                            <th>INTERÉS</th>
                            <th>SALDO</th>
                            <th>ESTADO</th>
                            <th>ACCIONES</th>
                        </tr>
                    </thead>
                    <tbody id="loansTableBody">
                        <tr><td colspan="11" style="text-align: center; padding: 2rem;">Cargando base de datos...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- TAB 2: CLIENTES -->
        <div id="tab-clientes" class="tab-content">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem;">
                <h3>👥 Clientes Registrados en la Base de Datos</h3>
                <button class="btn btn-success" onclick="openNewClientModal()">➕ Registrar Nuevo Cliente</button>
            </div>
            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th>ID CLIENTE</th>
                            <th>DOCUMENTO</th>
                            <th>NOMBRE COMPLETO</th>
                            <th>TELÉFONO</th>
                            <th>CORREO ELECTRÓNICO</th>
                            <th>OCUPACIÓN</th>
                            <th>INGRESOS</th>
                        </tr>
                    </thead>
                    <tbody id="clientsTableBody">
                        <tr><td colspan="7" style="text-align: center; padding: 2rem;">Cargando clientes...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- TAB 3: NUEVO CRÉDITO -->
        <div id="tab-nuevo_prestamo" class="tab-content">
            <div class="search-card" style="max-width: 650px; margin: 0 auto;">
                <h3>➕ Simulación y Desembolso de Nuevo Crédito</h3>
                <form id="newLoanForm" onsubmit="submitNewLoan(event)">
                    <div class="form-group">
                        <label>Cliente Solicitante:</label>
                        <select id="loanClientSelect" required></select>
                    </div>
                    <div class="form-group">
                        <label>Monto a Prestar ($):</label>
                        <input type="number" id="loanPrincipal" value="5000000" min="100000" step="50000" required>
                    </div>
                    <div class="form-group">
                        <label>Tasa de Interés Anual (%):</label>
                        <input type="number" id="loanRate" value="18.0" step="0.1" required>
                    </div>
                    <div class="form-group">
                        <label>Plazo (Número de Cuotas):</label>
                        <input type="number" id="loanInstallments" value="12" min="1" max="120" required>
                    </div>
                    <div class="form-group">
                        <label>Sistema de Amortización:</label>
                        <select id="loanMethod">
                            <option value="frances">Sistema Francés (Cuota Fija)</option>
                            <option value="aleman">Sistema Alemán (Capital Constante)</option>
                        </select>
                    </div>
                    <button type="submit" class="btn btn-success" style="width: 100%; margin-top: 1rem;">Desembolsar Crédito y Crear Pagaré</button>
                </form>
            </div>
        </div>

        <!-- TAB 4: BASE DE DATOS Y AUDITORÍA -->
        <div id="tab-basedatos" class="tab-content">
            <div class="search-card">
                <h3>🗄️ Estado en Vivo de la Base de Datos SQLite (Sistemas Operativos)</h3>
                <p style="color: var(--text-muted); font-size: 0.9rem; line-height: 1.6; margin-bottom: 1rem;">
                    Esta plataforma ejecuta SQLite3 en la nube con transacciones ACID, registro WAL y control de concurrencia POSIX:
                </p>
                <div id="dbStatsContainer" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem;">
                    <div style="background: var(--card-surface); padding: 1rem; border-radius: 8px;">Cargando métricas...</div>
                </div>
            </div>
        </div>
    </main>

    <!-- MODAL DE ABONO / PAGO -->
    <div id="paymentModal" class="modal-overlay">
        <div class="modal">
            <h2 id="payModalTitle">💳 Registrar Abono / Pago</h2>
            <div id="payModalSaldadoBanner" class="banner-saldado" style="display: none;">
                🎉 ¡ESTE PRÉSTAMO YA ESTÁ COMPLETAMENTE SALDADO!<br>
                <span style="font-size: 0.85rem; font-weight: normal;">No registra cuotas ni deudas pendientes.</span>
            </div>

            <div class="clock-live" id="liveClock">Cargando hora...</div>

            <form id="paymentForm" onsubmit="submitPayment(event)">
                <input type="hidden" id="payLoanId">

                <div id="payOptionsContainer">
                    <div class="form-group">
                        <label>Seleccione el Tipo de Abono:</label>
                        <label class="radio-box">
                            <input type="radio" name="payType" value="cuota" checked>
                            <div>
                                <strong>🟡 Cuota Normal</strong><br>
                                <small style="color: var(--text-muted);">Aplica orden legal: Mora ➔ Interés ➔ Capital</small>
                            </div>
                        </label>
                        <label class="radio-box">
                            <input type="radio" name="payType" value="capital">
                            <div>
                                <strong style="color: #34D399;">🟢 Abono Directo a Capital</strong><br>
                                <small style="color: var(--text-muted);">Reduce directamente la deuda del préstamo</small>
                            </div>
                        </label>
                        <label class="radio-box">
                            <input type="radio" name="payType" value="interes">
                            <div>
                                <strong style="color: #60A5FA;">🔵 Abono a Intereses</strong><br>
                                <small style="color: var(--text-muted);">Cubre intereses causados sin tocar el capital</small>
                            </div>
                        </label>
                    </div>

                    <div class="form-group">
                        <label>Monto a Pagar ($):</label>
                        <input type="number" id="payAmount" min="100" step="100" required>
                    </div>

                    <div class="form-group">
                        <label>Método de Pago:</label>
                        <select id="payMethod">
                            <option value="efectivo">Efectivo 💵</option>
                            <option value="transferencia">Transferencia Bancaria 📲</option>
                            <option value="tarjeta">Tarjeta 💳</option>
                            <option value="cheque">Cheque 📝</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label>Observaciones / Comprobante:</label>
                        <input type="text" id="payNotes" placeholder="Opcional">
                    </div>
                </div>

                <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem;">
                    <button type="button" class="btn btn-secondary" onclick="closeModal('paymentModal')">Cerrar</button>
                    <button type="submit" id="btnSubmitPay" class="btn btn-success">✅ Confirmar Abono</button>
                </div>
            </form>
        </div>
    </div>

    <!-- MODAL DE HISTORIAL DE CUOTAS / PAGOS -->
    <div id="historyModal" class="modal-overlay">
        <div class="modal" style="max-width: 850px;">
            <h2 id="histModalTitle">📋 Cuotas y Pagos Realizados</h2>
            <div class="table-responsive" style="max-height: 400px; margin-bottom: 1.25rem;">
                <table>
                    <thead>
                        <tr>
                            <th># PAGO</th>
                            <th>FECHA Y HORA REAL</th>
                            <th>TIPO ABONO</th>
                            <th>MONTO PAGADO</th>
                            <th>CAPITAL</th>
                            <th>INTERÉS</th>
                            <th>MÉTODO</th>
                            <th>ACCIÓN</th>
                        </tr>
                    </thead>
                    <tbody id="historyTableBody"></tbody>
                </table>
            </div>
            <div style="display: flex; justify-content: flex-end;">
                <button type="button" class="btn btn-secondary" onclick="closeModal('historyModal')">Cerrar</button>
            </div>
        </div>
    </div>

    <!-- MODAL NUEVO CLIENTE -->
    <div id="clientModal" class="modal-overlay">
        <div class="modal">
            <h2>➕ Registrar Nuevo Cliente</h2>
            <form id="newClientForm" onsubmit="submitNewClient(event)">
                <div class="form-group">
                    <label>Tipo de Documento:</label>
                    <select id="cliDocType">
                        <option value="CC">Cédula de Ciudadanía (CC)</option>
                        <option value="CE">Cédula de Extranjería (CE)</option>
                        <option value="TI">Tarjeta de Identidad (TI)</option>
                        <option value="NIT">NIT</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Número de Documento:</label>
                    <input type="text" id="cliDocNum" required placeholder="Ej: 100200300">
                </div>
                <div class="form-group">
                    <label>Nombres:</label>
                    <input type="text" id="cliFirstName" required placeholder="Ej: Carlos">
                </div>
                <div class="form-group">
                    <label>Apellidos:</label>
                    <input type="text" id="cliLastName" required placeholder="Ej: Mendoza">
                </div>
                <div class="form-group">
                    <label>Teléfono Móvil:</label>
                    <input type="text" id="cliPhone" required placeholder="Ej: 3001234567">
                </div>
                <div class="form-group">
                    <label>Correo Electrónico:</label>
                    <input type="email" id="cliEmail" required placeholder="Ej: correo@test.com">
                </div>
                <div class="form-group">
                    <label>Ocupación del Cliente (Actividad económica):</label>
                    <input type="text" id="cliOccupation" value="Empleado" required placeholder="Ej: Empleado, Comerciante, Independiente...">
                </div>
                <div class="form-group">
                    <label>Ingresos Mensuales ($):</label>
                    <input type="number" id="cliIncome" value="3000000" step="50000" required>
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.25rem;">
                    <button type="button" class="btn btn-secondary" onclick="closeModal('clientModal')">Cancelar</button>
                    <button type="submit" class="btn btn-success">Guardar Cliente</button>
                </div>
            </form>
        </div>
    </div>

    <footer>
        Sistema de Gestión de Préstamos • Proyecto de Sistemas Operativos • Universidad • Desplegado en Railway Cloud
    </footer>

    <script>
        let currentLoans = [];

        // Cambiar pestañas
        function switchTab(tabId) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('tab-' + tabId).classList.add('active');

            if (tabId === 'cobranzas') loadLoans();
            if (tabId === 'clientes') loadClients();
            if (tabId === 'nuevo_prestamo') loadClientSelect();
            if (tabId === 'basedatos') loadDbStats();
        }

        // Reloj en vivo
        setInterval(() => {
            const now = new Date();
            const clockEl = document.getElementById('liveClock');
            if (clockEl) {
                clockEl.innerText = '⏰ Registro en Tiempo Real: ' + now.toLocaleDateString() + ' ' + now.toLocaleTimeString();
            }
        }, 1000);

        // Cargar Préstamos (FOTO 2)
        async function loadLoans() {
            const q = document.getElementById('searchInput').value;
            try {
                const res = await fetch('/api/loans/search?q=' + encodeURIComponent(q));
                const data = await res.json();
                currentLoans = data.loans || [];

                document.getElementById('loansCount').innerText = `Mostrando ${currentLoans.length} crédito(s) en la base de datos.`;

                const tbody = document.getElementById('loansTableBody');
                if (currentLoans.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="11" style="text-align: center; padding: 2rem;">No se encontraron créditos con ese criterio de búsqueda.</td></tr>';
                    return;
                }

                tbody.innerHTML = currentLoans.map(l => {
                    const isSaldado = l.status === 'cancelado' || l.saldo <= 0;
                    const badgeClass = isSaldado ? 'badge-saldado' : (l.status === 'en_mora' ? 'badge-mora' : 'badge-activo');
                    const badgeText = isSaldado ? 'SALDADO' : l.status.toUpperCase();

                    return `
                        <tr>
                            <td><strong style="color: #38BDF8;">${l.pagare_number}</strong></td>
                            <td>${l.documento}</td>
                            <td>${l.nombre}</td>
                            <td>$${Number(l.monto).toLocaleString('es-CO')}</td>
                            <td>${l.fecha}</td>
                            <td>${l.cuota_plazo}</td>
                            <td>$${Number(l.capital).toLocaleString('es-CO')}</td>
                            <td>$${Number(l.interes).toLocaleString('es-CO')}</td>
                            <td><strong style="color: ${isSaldado ? '#34D399' : '#F59E0B'}">$${Number(l.saldo).toLocaleString('es-CO')}</strong></td>
                            <td><span class="badge ${badgeClass}">${badgeText}</span></td>
                            <td>
                                <button class="btn btn-success" style="padding: 0.35rem 0.65rem; font-size: 0.8rem;" onclick='openPaymentModal(${JSON.stringify(l)})'>💳 Abonar</button>
                                <button class="btn btn-primary" style="padding: 0.35rem 0.65rem; font-size: 0.8rem;" onclick='openHistoryModal(${l.loan_id}, "${l.pagare_number}")'>📋 Cuotas</button>
                            </td>
                        </tr>
                    `;
                }).join('');
            } catch (err) {
                console.error(err);
            }
        }

        function clearSearch() {
            document.getElementById('searchInput').value = '';
            loadLoans();
        }

        // Modal de Pago / Abono
        function openPaymentModal(loan) {
            document.getElementById('payLoanId').value = loan.loan_id;
            document.getElementById('payModalTitle').innerText = `💳 Abonar al Crédito: ${loan.pagare_number} (${loan.nombre})`;
            
            const isSaldado = loan.status === 'cancelado' || loan.saldo <= 0;
            const saldadoBanner = document.getElementById('payModalSaldadoBanner');
            const optionsContainer = document.getElementById('payOptionsContainer');
            const btnSubmit = document.getElementById('btnSubmitPay');

            if (isSaldado) {
                saldadoBanner.style.display = 'block';
                optionsContainer.style.display = 'none';
                btnSubmit.style.display = 'none';
            } else {
                saldadoBanner.style.display = 'none';
                optionsContainer.style.display = 'block';
                btnSubmit.style.display = 'inline-block';
                document.getElementById('payAmount').value = Math.min(loan.saldo, 250000);
            }

            document.getElementById('paymentModal').style.display = 'flex';
        }

        async function submitPayment(e) {
            e.preventDefault();
            const loanId = document.getElementById('payLoanId').value;
            const amount = document.getElementById('payAmount').value;
            const payType = document.querySelector('input[name="payType"]:checked').value;
            const payMethod = document.getElementById('payMethod').value;
            const notes = document.getElementById('payNotes').value;

            try {
                const res = await fetch('/api/payments/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        loan_id: loanId,
                        amount: amount,
                        payment_type: payType,
                        payment_method: payMethod,
                        notes: notes
                    })
                });
                const data = await res.json();
                if (data.success) {
                    if (data.result.is_settled) {
                        alert(`🎉 ¡FELICITACIONES! El pago ha cancelado la totalidad de la deuda.\nEl crédito ${data.result.pagare_number} ha quedado SALDADO.`);
                    } else {
                        alert(`✅ Abono registrado con éxito por $${Number(data.result.amount_paid).toLocaleString('es-CO')} (${payType.toUpperCase()}).`);
                    }
                    closeModal('paymentModal');
                    loadLoans();
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (err) {
                alert('Error al procesar el pago.');
            }
        }

        // Historial de Cuotas / Pagos
        async function openHistoryModal(loanId, pagareNum) {
            document.getElementById('histModalTitle').innerText = `📋 Cuotas y Pagos Registrados - ${pagareNum}`;
            const tbody = document.getElementById('historyTableBody');
            tbody.innerHTML = '<tr><td colspan="8" style="text-align: center;">Cargando pagos...</td></tr>';
            document.getElementById('historyModal').style.display = 'flex';

            try {
                const res = await fetch('/api/payments?loan_id=' + loanId);
                const data = await res.json();
                const payments = data.payments || [];

                if (payments.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 1.5rem;">No se registran pagos en este crédito aún.</td></tr>';
                    return;
                }

                tbody.innerHTML = payments.map(p => `
                    <tr>
                        <td><strong>#${p.id}</strong></td>
                        <td>${p.full_timestamp || p.payment_date}</td>
                        <td><span style="color: ${p.payment_type === 'capital' ? '#34D399' : (p.payment_type === 'interes' ? '#60A5FA' : '#FBBF24')}">${(p.payment_type || 'cuota').toUpperCase()}</span></td>
                        <td><strong>$${Number(p.amount).toLocaleString('es-CO')}</strong></td>
                        <td>$${Number(p.capital_allocated).toLocaleString('es-CO')}</td>
                        <td>$${Number(p.interest_allocated).toLocaleString('es-CO')}</td>
                        <td>${p.payment_method}</td>
                        <td>
                            <button class="btn btn-danger" style="padding: 0.25rem 0.5rem; font-size: 0.75rem;" onclick="deletePayment(${p.id})">🗑️ Anular</button>
                        </td>
                    </tr>
                `).join('');
            } catch (err) {
                console.error(err);
            }
        }

        async function deletePayment(paymentId) {
            if (!confirm(`¿Está seguro de anular el pago #${paymentId}? El saldo del crédito se restaurará automáticamente.`)) return;

            try {
                const res = await fetch('/api/payments/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ payment_id: paymentId })
                });
                const data = await res.json();
                if (data.success) {
                    alert('Pago anulado y saldo del crédito restaurado.');
                    closeModal('historyModal');
                    loadLoans();
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (err) {
                alert('Error al anular pago.');
            }
        }

        // Clientes
        async function loadClients() {
            try {
                const res = await fetch('/api/clients');
                const data = await res.json();
                const clients = data.clients || [];

                const tbody = document.getElementById('clientsTableBody');
                tbody.innerHTML = clients.map(c => `
                    <tr>
                        <td><strong style="color: #38BDF8;">CLI-${String(c.id).padStart(4, '0')}</strong></td>
                        <td>${c.doc_type}-${c.doc_number}</td>
                        <td><strong>${c.first_name} ${c.last_name}</strong></td>
                        <td>${c.phone}</td>
                        <td>${c.email}</td>
                        <td>${c.occupation}</td>
                        <td>$${Number(c.monthly_income).toLocaleString('es-CO')}</td>
                    </tr>
                `).join('');
            } catch (err) {
                console.error(err);
            }
        }

        function openNewClientModal() {
            document.getElementById('clientModal').style.display = 'flex';
        }

        async function submitNewClient(e) {
            e.preventDefault();
            const clientData = {
                doc_type: document.getElementById('cliDocType').value,
                doc_number: document.getElementById('cliDocNum').value,
                first_name: document.getElementById('cliFirstName').value,
                last_name: document.getElementById('cliLastName').value,
                phone: document.getElementById('cliPhone').value,
                email: document.getElementById('cliEmail').value,
                occupation: document.getElementById('cliOccupation').value,
                monthly_income: document.getElementById('cliIncome').value,
                birth_date: '1995-01-01',
                address: 'Dirección Principal'
            };

            try {
                const res = await fetch('/api/clients/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(clientData)
                });
                const data = await res.json();
                if (data.success) {
                    alert('✅ Cliente registrado con éxito.');
                    closeModal('clientModal');
                    loadClients();
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (err) {
                alert('Error al registrar cliente.');
            }
        }

        async function loadClientSelect() {
            const select = document.getElementById('loanClientSelect');
            try {
                const res = await fetch('/api/clients');
                const data = await res.json();
                const clients = data.clients || [];
                select.innerHTML = clients.map(c => `<option value="${c.id}">${c.first_name} ${c.last_name} (${c.doc_number}) - ${c.occupation}</option>`).join('');
            } catch (err) {
                console.error(err);
            }
        }

        async function submitNewLoan(e) {
            e.preventDefault();
            const loanData = {
                client_id: document.getElementById('loanClientSelect').value,
                principal: document.getElementById('loanPrincipal').value,
                rate: document.getElementById('loanRate').value,
                installments_count: document.getElementById('loanInstallments').value,
                method: document.getElementById('loanMethod').value,
                periodicity: 'mensual'
            };

            try {
                const res = await fetch('/api/loans/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(loanData)
                });
                const data = await res.json();
                if (data.success) {
                    alert('✅ Crédito desembolsado y Pagaré creado exitosamente.');
                    switchTab('cobranzas');
                    loadLoans();
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (err) {
                alert('Error al crear crédito.');
            }
        }

        // Métricas de base de datos para el profesor
        async function loadDbStats() {
            try {
                const res = await fetch('/api/db/stats');
                const stats = await res.json();
                const container = document.getElementById('dbStatsContainer');
                container.innerHTML = `
                    <div style="background: var(--card-surface); padding: 1rem; border-radius: 8px;">
                        <span style="color: #94A3B8; font-size: 0.8rem;">MOTOR DE BASE DE DATOS</span>
                        <h4 style="color: #38BDF8; margin-top: 0.25rem;">${stats.engine}</h4>
                    </div>
                    <div style="background: var(--card-surface); padding: 1rem; border-radius: 8px;">
                        <span style="color: #94A3B8; font-size: 0.8rem;">TOTAL CLIENTES</span>
                        <h4 style="color: #34D399; margin-top: 0.25rem;">${stats.clients_count} registrados</h4>
                    </div>
                    <div style="background: var(--card-surface); padding: 1rem; border-radius: 8px;">
                        <span style="color: #94A3B8; font-size: 0.8rem;">CRÉDITOS Y PAGARÉS</span>
                        <h4 style="color: #F59E0B; margin-top: 0.25rem;">${stats.loans_count} créditos</h4>
                    </div>
                    <div style="background: var(--card-surface); padding: 1rem; border-radius: 8px;">
                        <span style="color: #94A3B8; font-size: 0.8rem;">PAGOS Y ABONOS</span>
                        <h4 style="color: #60A5FA; margin-top: 0.25rem;">${stats.payments_count} registrados</h4>
                    </div>
                `;
            } catch (err) {
                console.error(err);
            }
        }

        function closeModal(modalId) {
            document.getElementById(modalId).style.display = 'none';
        }

        // Cargar datos al inicio
        loadLoans();
    </script>
</body>
</html>"""

def run():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, CloudLoanManagementHandler)
    print(f"🚀 Servidor Cloud de Gestión de Préstamos iniciado en el puerto {PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando servidor cloud...")
        httpd.server_close()

if __name__ == '__main__':
    run()
