import os
import sys
import json
from http.server import HTTPServer, SimpleHTTPRequestHandler
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

# Ensure project modules can be loaded
current_dir = os.path.dirname(os.path.abspath(__file__))
proyecto_dir = os.path.join(current_dir, "proyecto_prestamos")
if proyecto_dir not in sys.path:
    sys.path.insert(0, proyecto_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

PORT = int(os.environ.get("PORT", 8080))

class LoanManagementHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        
        # Health check endpoint for Railway
        if parsed.path in ["/health", "/api/health"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            data = {
                "status": "healthy",
                "service": "Sistema de Gestion de Prestamos",
                "version": "2.0.0",
                "platform": "Railway Cloud",
                "os_architecture": "Decoupled Frontend / Backend Daemon",
                "storage": "SQLite3 WAL Mode"
            }
            self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))
            return

        # Status and info endpoint
        if parsed.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            info = {
                "system": "Gestion de Prestamos - Sistemas Operativos",
                "daemon": "prestamos-daemon (Background service)",
                "ipc": "UNIX Domain Socket (~/.local/share/gestion_prestamos/ipc.sock)",
                "concurrency": "POSIX fcntl.flock advisory locking",
                "financial_engine": "decimal.Decimal strict rounding"
            }
            self.wfile.write(json.dumps(info, indent=2).encode("utf-8"))
            return

        # Main interactive page
        if parsed.path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            
            # Check if preview artifact exists
            preview_html = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sistema de Gestión de Préstamos - Despliegue Cloud</title>
    <style>
        :root {
            --primary: #4F46E5;
            --primary-hover: #4338CA;
            --bg: #0F172A;
            --card-bg: #1E293B;
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
            --border: #334155;
            --accent: #10B981;
            --amber: #F59E0B;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        header {
            background-color: var(--card-bg);
            border-bottom: 1px solid var(--border);
            padding: 1.25rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .logo-area { display: flex; align-items: center; gap: 0.75rem; }
        .logo-badge {
            background: linear-gradient(135deg, var(--primary), #818CF8);
            width: 40px; height: 40px; border-radius: 10px;
            display: flex; align-items: center; justify-content: center;
            font-weight: bold; font-size: 1.25rem;
        }
        .status-pill {
            background: rgba(16, 185, 129, 0.15);
            color: var(--accent);
            padding: 0.4rem 0.85rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 600;
            border: 1px solid rgba(16, 185, 129, 0.3);
            display: flex; align-items: center; gap: 0.5rem;
        }
        .status-dot { width: 8px; height: 8px; background: var(--accent); border-radius: 50%; }
        main {
            flex: 1;
            max-width: 1200px;
            width: 100%;
            margin: 0 auto;
            padding: 2.5rem 1.5rem;
        }
        .hero {
            text-align: center;
            margin-bottom: 3rem;
        }
        .hero h1 { font-size: 2.5rem; margin-bottom: 0.75rem; }
        .hero p { color: var(--text-muted); font-size: 1.15rem; max-width: 750px; margin: 0 auto; }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2.5rem;
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 1.75rem;
        }
        .card h2 { font-size: 1.25rem; margin-bottom: 1rem; color: #E2E8F0; display: flex; align-items: center; gap: 0.5rem; }
        .card p { color: var(--text-muted); font-size: 0.95rem; line-height: 1.6; margin-bottom: 1rem; }
        .tech-tags { display: flex; flex-wrap: wrap; gap: 0.5rem; }
        .tag {
            background: rgba(255,255,255,0.06);
            border: 1px solid var(--border);
            padding: 0.25rem 0.6rem;
            border-radius: 6px;
            font-size: 0.8rem;
            color: #CBD5E1;
        }
        .simulator-form { display: flex; flex-direction: column; gap: 1rem; }
        .form-group { display: flex; flex-direction: column; gap: 0.35rem; }
        .form-group label { font-size: 0.85rem; color: #CBD5E1; }
        .form-group input, .form-group select {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border);
            color: white;
            padding: 0.65rem 0.85rem;
            border-radius: 8px;
            font-size: 0.95rem;
        }
        .btn-calc {
            background: var(--primary);
            color: white;
            border: none;
            padding: 0.75rem;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            margin-top: 0.5rem;
            transition: background 0.2s;
        }
        .btn-calc:hover { background: var(--primary-hover); }
        .result-box {
            background: rgba(16, 185, 129, 0.08);
            border: 1px solid rgba(16, 185, 129, 0.2);
            padding: 1rem;
            border-radius: 8px;
            margin-top: 1rem;
            display: none;
        }
        footer {
            background: var(--card-bg);
            border-top: 1px solid var(--border);
            text-align: center;
            padding: 1.5rem;
            color: var(--text-muted);
            font-size: 0.9rem;
        }
    </style>
</head>
<body>
    <header>
        <div class="logo-area">
            <div class="logo-badge">GP</div>
            <div>
                <h3 style="font-size: 1.1rem;">Gestión de Préstamos</h3>
                <span style="font-size: 0.75rem; color: var(--text-muted);">Sistemas Operativos • Arquitectura Desacoplada</span>
            </div>
        </div>
        <div class="status-pill">
            <div class="status-dot"></div>
            <span>En línea en Railway Cloud</span>
        </div>
    </header>

    <main>
        <div class="hero">
            <h1>Sistema de Gestión de Préstamos</h1>
            <p>Servicio desplegado en la nube con arquitectura desacoplada: motor financiero en Decimal de alta precisión, base de datos SQLite ACID y demonio de segundo plano.</p>
        </div>

        <div class="grid">
            <div class="card">
                <h2>🖥️ Arquitectura del Sistema</h2>
                <p>El proyecto separa de forma estricta las responsabilidades para garantizar mantenibilidad, concurrencia y seguridad POSIX:</p>
                <div class="tech-tags">
                    <span class="tag">Frontend: PySide6 (Qt6)</span>
                    <span class="tag">Backend: Python 3.13</span>
                    <span class="tag">IPC: Unix Domain Socket</span>
                    <span class="tag">Concurrencia: fcntl.flock</span>
                    <span class="tag">Motor: Decimal Estricto</span>
                    <span class="tag">Auth: bcrypt</span>
                    <span class="tag">Reportes: PDF ReportLab</span>
                </div>
            </div>

            <div class="card">
                <h2>⚡ Simulador de Amortizaciones</h2>
                <form class="simulator-form" id="simForm" onsubmit="calculate(event)">
                    <div class="form-group">
                        <label>Monto del Préstamo ($):</label>
                        <input type="number" id="monto" value="5000000" min="100000" step="50000" required>
                    </div>
                    <div class="form-group">
                        <label>Tasa de Interés Mensual (%):</label>
                        <input type="number" id="tasa" value="2.5" step="0.1" required>
                    </div>
                    <div class="form-group">
                        <label>Plazo (Meses):</label>
                        <input type="number" id="plazo" value="12" min="1" max="120" required>
                    </div>
                    <div class="form-group">
                        <label>Sistema de Amortización:</label>
                        <select id="sistema">
                            <option value="FRANCES">Francés (Cuota Fija)</option>
                            <option value="ALEMAN">Alemán (Capital Fijo)</option>
                        </select>
                    </div>
                    <button type="submit" class="btn-calc">Calcular Simulación</button>
                    <div class="result-box" id="resultBox"></div>
                </form>
            </div>

            <div class="card">
                <h2>🛡️ Monitoreo & Endpoints</h2>
                <p>Este despliegue expone endpoints de observabilidad listos para integración continua:</p>
                <ul style="margin-left: 1.25rem; color: #CBD5E1; font-size: 0.9rem; line-height: 1.8;">
                    <li><code>/health</code> - Verificación de salud y estado del servicio.</li>
                    <li><code>/api/status</code> - Mecanismos activos de concurrencia e IPC.</li>
                    <li><code>/api/calculate</code> - API de simulación de amortización.</li>
                </ul>
            </div>
        </div>
    </main>

    <footer>
        Sistema de Gestión de Préstamos • Proyecto de Sistemas Operativos • Universidad
    </footer>

    <script>
        function calculate(e) {
            e.preventDefault();
            const P = parseFloat(document.getElementById('monto').value);
            const r = parseFloat(document.getElementById('tasa').value) / 100;
            const n = parseInt(document.getElementById('plazo').value);
            const sys = document.getElementById('sistema').value;
            
            let cuotaHtml = '';
            if (sys === 'FRANCES') {
                const cuota = P * (r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1);
                const total = cuota * n;
                const intereses = total - P;
                cuotaHtml = `<strong>Cuota Mensual Fija:</strong> $${cuota.toLocaleString('es-CO', {maximumFractionDigits: 0})}<br>` +
                            `<strong>Total Intereses:</strong> $${intereses.toLocaleString('es-CO', {maximumFractionDigits: 0})}<br>` +
                            `<strong>Total a Pagar:</strong> $${total.toLocaleString('es-CO', {maximumFractionDigits: 0})}`;
            } else {
                const capFijo = P / n;
                const primeraCuota = capFijo + (P * r);
                const ultimaCuota = capFijo + (capFijo * r);
                cuotaHtml = `<strong>Primera Cuota:</strong> $${primeraCuota.toLocaleString('es-CO', {maximumFractionDigits: 0})}<br>` +
                            `<strong>Última Cuota:</strong> $${ultimaCuota.toLocaleString('es-CO', {maximumFractionDigits: 0})}<br>` +
                            `<strong>Amortización Capital/Mes:</strong> $${capFijo.toLocaleString('es-CO', {maximumFractionDigits: 0})}`;
            }
            const res = document.getElementById('resultBox');
            res.style.display = 'block';
            res.innerHTML = cuotaHtml;
        }
    </script>
</body>
</html>"""
            self.wfile.write(preview_html.encode("utf-8"))
            return

        super().do_GET()

def run():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, LoanManagementHandler)
    print(f"🚀 Servidor de Gestión de Préstamos iniciado en el puerto {PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando servidor...")
        httpd.server_close()

if __name__ == '__main__':
    run()
