import logging
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, Any, List, Optional, Tuple

from backend.common.config import ConfigManager
from backend.database.db_manager import DatabaseManager

logger = logging.getLogger("prestamos.loans")

ROUND_CENTS = Decimal("0.01")
ROUND_RATE = Decimal("0.00000001")

class LoanCalculator:
    """
    Motor de cálculo financiero de alta precisión (PR-07 a PR-16).
    Uso estricto de decimal.Decimal (prohibido float para dinero).
    Amortización:
    - Sistema Francés (cuota fija)
    - Sistema Alemán (abono constante a capital)
    Ajuste automático de feriados y fines de semana.
    """
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.config = ConfigManager()
        self.db = db_manager or DatabaseManager()

    def get_periods_per_year(self, periodicity: str) -> int:
        periodicities = {
            "semanal": 52,
            "quincenal": 24,
            "mensual": 12
        }
        p = periodicity.lower().strip()
        if p not in periodicities:
            raise ValueError(f"Periodicidad inválida: {periodicity}. Debe ser 'semanal', 'quincenal' o 'mensual'.")
        return periodicities[p]

    def adjust_for_weekends_and_holidays(self, target_date: date) -> date:
        """
        Ajusta la fecha de vencimiento si cae en sábado, domingo o día feriado configurable (PR-14).
        Avanza al siguiente día hábil.
        """
        holidays_str = set(self.config.holidays)
        curr = target_date

        while True:
            # 5 = Sábado, 6 = Domingo
            is_weekend = curr.weekday() in (5, 6)
            is_holiday = curr.strftime("%Y-%m-%d") in holidays_str

            if not is_weekend and not is_holiday:
                break
            curr += timedelta(days=1)

        return curr

    def calculate_next_date(self, base_date: date, periodicity: str, step: int) -> date:
        """Calcula la fecha tentativa de vencimiento para la cuota N."""
        p = periodicity.lower().strip()
        if p == "semanal":
            tentative = base_date + timedelta(weeks=step)
        elif p == "quincenal":
            tentative = base_date + timedelta(days=15 * step)
        elif p == "mensual":
            # Avanzar meses respetando el día
            year = base_date.year + (base_date.month + step - 1) // 12
            month = (base_date.month + step - 1) % 12 + 1
            day = base_date.day
            # Ajustar si el mes no tiene 31 o 30 días
            while day > 28:
                try:
                    tentative = date(year, month, day)
                    break
                except ValueError:
                    day -= 1
            else:
                tentative = date(year, month, day)
        else:
            tentative = base_date + timedelta(days=30 * step)

        return self.adjust_for_weekends_and_holidays(tentative)

    def calculate_commission(self, principal: Decimal, commission_type: str, commission_val: Decimal) -> Decimal:
        c_type = (commission_type or "ninguna").lower().strip()
        if c_type == "porcentaje":
            return (principal * (commission_val / Decimal("100"))).quantize(ROUND_CENTS, rounding=ROUND_HALF_UP)
        elif c_type == "fijo":
            return commission_val.quantize(ROUND_CENTS, rounding=ROUND_HALF_UP)
        return Decimal("0.00")

    def simulate_loan(
        self,
        principal: Decimal,
        annual_interest_rate: Decimal,
        installments_count: int,
        periodicity: str,
        method: str,
        commission_type: str = "ninguna",
        commission_value: Decimal = Decimal("0.00"),
        disbursement_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Simulador de préstamos con cálculo exacto en Decimal (PR-09).
        Genera el calendario y resumen sin guardar en base de datos.
        """
        if principal <= Decimal("0.00"):
            raise ValueError("El monto principal del préstamo debe ser mayor a cero.")
        if installments_count <= 0:
            raise ValueError("El número de cuotas debe ser mayor a cero.")

        max_rate = self.config.max_annual_rate_decimal
        if annual_interest_rate < Decimal("0.00") or annual_interest_rate > max_rate:
            raise ValueError(f"La tasa anual debe estar entre 0% y el límite máximo configurado ({max_rate}%).")

        method = method.lower().strip()
        if method not in ("frances", "aleman"):
            raise ValueError("El método de amortización debe ser 'frances' o 'aleman'.")

        start_date = disbursement_date or date.today()
        periods_year = self.get_periods_per_year(periodicity)
        
        # Tasa periódica r = (Tasa Anual / 100) / Periodos
        periodic_rate = ((annual_interest_rate / Decimal("100")) / Decimal(str(periods_year)))

        commission = self.calculate_commission(principal, commission_type, commission_value)

        schedule: List[Dict[str, Any]] = []
        saldo = principal
        total_interes = Decimal("0.00")

        if method == "frances":
            # Cuota fija francesa: R = P * [ r / (1 - (1+r)^-n) ]
            if periodic_rate > Decimal("0.00"):
                factor = (Decimal("1.0") + periodic_rate) ** installments_count
                cuota_fija = (principal * (periodic_rate * factor) / (factor - Decimal("1.0"))).quantize(
                    ROUND_CENTS, rounding=ROUND_HALF_UP
                )
            else:
                cuota_fija = (principal / Decimal(str(installments_count))).quantize(ROUND_CENTS, rounding=ROUND_HALF_UP)

            for i in range(1, installments_count + 1):
                due_date = self.calculate_next_date(start_date, periodicity, i)
                interes = (saldo * periodic_rate).quantize(ROUND_CENTS, rounding=ROUND_HALF_UP)
                
                if i == installments_count:
                    # En la última cuota, se liquida el saldo remanente exacto
                    capital = saldo
                    cuota_total = capital + interes
                    saldo_final = Decimal("0.00")
                else:
                    capital = cuota_fija - interes
                    if capital > saldo:
                        capital = saldo
                    cuota_total = capital + interes
                    saldo_final = saldo - capital

                total_interes += interes
                saldo = saldo_final

                schedule.append({
                    "numero": i,
                    "fecha_vencimiento": due_date.strftime("%Y-%m-%d"),
                    "capital": capital,
                    "interes": interes,
                    "cuota_total": cuota_total,
                    "saldo_remanente": saldo_final
                })

        elif method == "aleman":
            # Abono constante a capital: C = P / n
            abono_capital_base = (principal / Decimal(str(installments_count))).quantize(ROUND_CENTS, rounding=ROUND_HALF_UP)

            for i in range(1, installments_count + 1):
                due_date = self.calculate_next_date(start_date, periodicity, i)
                interes = (saldo * periodic_rate).quantize(ROUND_CENTS, rounding=ROUND_HALF_UP)

                if i == installments_count:
                    capital = saldo
                    saldo_final = Decimal("0.00")
                else:
                    capital = abono_capital_base
                    saldo_final = saldo - capital

                cuota_total = capital + interes
                total_interes += interes
                saldo = saldo_final

                schedule.append({
                    "numero": i,
                    "fecha_vencimiento": due_date.strftime("%Y-%m-%d"),
                    "capital": capital,
                    "interes": interes,
                    "cuota_total": cuota_total,
                    "saldo_remanente": saldo_final
                })

        total_a_pagar = principal + total_interes + commission

        return {
            "resumen": {
                "principal": principal,
                "tasa_anual": annual_interest_rate,
                "tasa_periodica": (periodic_rate * Decimal("100")).quantize(Decimal("0.0001")),
                "numero_cuotas": installments_count,
                "periodicidad": periodicity,
                "metodo": method,
                "comision": commission,
                "total_intereses": total_interes,
                "total_a_pagar": total_a_pagar,
                "fecha_desembolso": start_date.strftime("%Y-%m-%d")
            },
            "cronograma": schedule
        }

    def check_client_delinquency(self, client_id: int):
        """
        Bloquea nuevos préstamos si el cliente supera el umbral configurable de días en mora (PR-11).
        """
        threshold_days = int(self.config.get("financiero", "dias_umbral_mora_bloqueo", default=30))
        today = date.today().strftime("%Y-%m-%d")

        with self.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT l.id as loan_id, i.number, i.due_date,
                       julianday(?) - julianday(i.due_date) as dias_retraso
                FROM installments i
                JOIN loans l ON i.loan_id = l.id
                WHERE l.client_id = ?
                  AND l.status IN ('activo', 'en_mora')
                  AND i.status IN ('pendiente', 'parcial', 'vencida')
                  AND i.due_date < ?
                ORDER BY dias_retraso DESC
                LIMIT 1;
                """,
                (today, client_id, today)
            )
            row = cursor.fetchone()
            if row:
                dias_retraso = int(row["dias_retraso"])
                if dias_retraso > threshold_days:
                    raise ValueError(
                        f"El cliente tiene cuotas en mora con {dias_retraso} días de retraso en el préstamo #{row['loan_id']}. "
                        f"El umbral máximo permitido es de {threshold_days} días. No se pueden otorgar nuevos préstamos."
                    )

    def calculate_installment_late_fee(self, capital_pending: Decimal, due_date_str: str, as_of_date_str: Optional[str] = None) -> Decimal:
        """
        Calcula el interés moratorio diario según la tasa diaria configurable (PR-20).
        Fórmula: Capital Pendiente * Tasa Diaria * Días en Mora
        """
        if capital_pending <= Decimal("0.00"):
            return Decimal("0.00")

        due_d = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        as_of_d = datetime.strptime(as_of_date_str, "%Y-%m-%d").date() if as_of_date_str else date.today()

        days_overdue = (as_of_d - due_d).days
        if days_overdue <= 0:
            return Decimal("0.00")

        daily_rate = self.config.daily_late_rate_decimal
        late_fee = (capital_pending * daily_rate * Decimal(str(days_overdue))).quantize(ROUND_CENTS, rounding=ROUND_HALF_UP)
        return late_fee

    def create_loan(
        self,
        client_id: int,
        principal: Decimal,
        annual_interest_rate: Decimal,
        installments_count: int,
        periodicity: str,
        method: str,
        commission_type: str,
        commission_value: Decimal,
        disbursement_date: str,
        actor_username: str
    ) -> int:
        """
        Registra el préstamo y sus cuotas en la base de datos de manera atómica (ACID).
        """
        # Verificar bloqueo por mora
        self.check_client_delinquency(client_id)

        d_date = datetime.strptime(disbursement_date, "%Y-%m-%d").date()
        simulation = self.simulate_loan(
            principal=principal,
            annual_interest_rate=annual_interest_rate,
            installments_count=installments_count,
            periodicity=periodicity,
            method=method,
            commission_type=commission_type,
            commission_value=commission_value,
            disbursement_date=d_date
        )

        resumen = simulation["resumen"]
        cronograma = simulation["cronograma"]

        with self.db.connection(exclusive_lock=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO loans (
                    client_id, principal, annual_interest_rate, installments_count,
                    periodicity, disbursement_date, method, commission_type,
                    commission_value, total_amount, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'activo');
                """,
                (
                    client_id,
                    str(principal),
                    str(annual_interest_rate),
                    installments_count,
                    periodicity,
                    disbursement_date,
                    method,
                    commission_type,
                    str(commission_value),
                    str(resumen["total_a_pagar"])
                )
            )
            loan_id = cursor.lastrowid
            pagare_num = f"PAG-{loan_id:04d}"
            cursor.execute("UPDATE loans SET pagare_number = ? WHERE id = ?;", (pagare_num, loan_id))

            # Insertar cuotas
            for item in cronograma:
                cursor.execute(
                    """
                    INSERT INTO installments (
                        loan_id, number, due_date, capital_expected, interest_expected,
                        total_expected, remaining_principal, capital_paid, interest_paid,
                        late_fee_paid, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, '0.00', '0.00', '0.00', 'pendiente');
                    """,
                    (
                        loan_id,
                        item["numero"],
                        item["fecha_vencimiento"],
                        str(item["capital"]),
                        str(item["interes"]),
                        str(item["cuota_total"]),
                        str(item["saldo_remanente"])
                    )
                )

            conn.execute(
                "INSERT INTO audit_logs (username, action, details) VALUES (?, ?, ?);",
                (actor_username, "CREAR_PRESTAMO", f"Préstamo #{loan_id} por {principal} creado para cliente ID {client_id}.")
            )
            logger.info(f"Préstamo #{loan_id} creado exitosamente por {actor_username}.")
            return loan_id

    def get_loan(self, loan_id: int) -> Optional[Dict[str, Any]]:
        with self.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT l.*, c.first_name, c.last_name, c.doc_number, c.doc_type, c.phone, c.email
                FROM loans l
                JOIN clients c ON l.client_id = c.id
                WHERE l.id = ?;
                """,
                (loan_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)

            # Obtener cuotas
            cursor.execute("SELECT * FROM installments WHERE loan_id = ? ORDER BY number ASC;", (loan_id,))
            res["installments"] = [dict(r) for r in cursor.fetchall()]
            return res

    def list_loans(self, client_id: Optional[int] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()
            query = """
                SELECT l.*, c.first_name, c.last_name, c.doc_number
                FROM loans l
                JOIN clients c ON l.client_id = c.id
                WHERE 1=1
            """
            params = []
            if client_id:
                query += " AND l.client_id = ?"
                params.append(client_id)
            if status:
                query += " AND l.status = ?"
                params.append(status)

            query += " ORDER BY l.id DESC;"
            cursor.execute(query, tuple(params))
            return [dict(r) for r in cursor.fetchall()]


