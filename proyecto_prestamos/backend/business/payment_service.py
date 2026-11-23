import logging
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, List

from backend.database.db_manager import DatabaseManager
from backend.business.loan_calculator import LoanCalculator, ROUND_CENTS

logger = logging.getLogger("prestamos.payments")

class PaymentService:
    """
    Gestión de Pagos y Liquidación de Cuotas (PR-17 a PR-20).
    Prelación de pagos estricta:
      1° Mora (Interés Moratorio)
      2° Interés Corriente
      3° Capital
    Soporte para pagos parciales, completos y abonos adelantados con recálculo.
    """
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()
        self.calculator = LoanCalculator(self.db)

    def get_pending_debt_breakdown(self, loan_id: int, as_of_date_str: Optional[str] = None) -> Dict[str, Any]:
        """Calcula el desglose exigible de deuda a la fecha actual."""
        as_of_date = as_of_date_str or date.today().strftime("%Y-%m-%d")

        with self.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM installments
                WHERE loan_id = ? AND status IN ('pendiente', 'parcial', 'vencida')
                ORDER BY number ASC;
                """,
                (loan_id,)
            )
            rows = cursor.fetchall()

            total_mora = Decimal("0.00")
            total_interes_pendiente = Decimal("0.00")
            total_capital_pendiente = Decimal("0.00")

            installments_detail = []

            for r in rows:
                cap_exp = Decimal(r["capital_expected"])
                cap_paid = Decimal(r["capital_paid"])
                cap_pending = cap_exp - cap_paid

                int_exp = Decimal(r["interest_expected"])
                int_paid = Decimal(r["interest_paid"])
                int_pending = int_exp - int_paid

                # Calcular mora si está vencida
                mora = self.calculator.calculate_installment_late_fee(cap_pending, r["due_date"], as_of_date)
                mora_paid = Decimal(r["late_fee_paid"])
                mora_pending = max(Decimal("0.00"), mora - mora_paid)

                total_mora += mora_pending
                total_interes_pendiente += int_pending
                total_capital_pendiente += cap_pending

                installments_detail.append({
                    "id": r["id"],
                    "numero": r["number"],
                    "due_date": r["due_date"],
                    "cap_pending": cap_pending,
                    "int_pending": int_pending,
                    "mora_pending": mora_pending,
                    "total_pending": cap_pending + int_pending + mora_pending
                })

            total_exigible = total_mora + total_interes_pendiente + total_capital_pendiente

            return {
                "loan_id": loan_id,
                "as_of_date": as_of_date,
                "total_mora": total_mora,
                "total_interes": total_interes_pendiente,
                "total_capital": total_capital_pendiente,
                "total_exigible": total_exigible,
                "cuotas": installments_detail
            }

    def register_payment(
        self,
        loan_id: int,
        amount: Decimal,
        payment_method: str,
        payment_date: Optional[str] = None,
        notes: str = "",
        actor_username: str = "sistema"
    ) -> Dict[str, Any]:
        """
        Ejecuta el pago respetando la prelación (1° Mora -> 2° Interés -> 3° Capital).
        Transacción ACID con bloqueo exclusivo flock.
        """
        if amount <= Decimal("0.00"):
            raise ValueError("El monto del pago debe ser mayor a cero.")

        pay_date_str = payment_date or date.today().strftime("%Y-%m-%d")
        amount_remaining = amount.quantize(ROUND_CENTS, rounding=ROUND_HALF_UP)

        with self.db.connection(exclusive_lock=True) as conn:
            cursor = conn.cursor()

            # Verificar estado del préstamo
            cursor.execute("SELECT id, client_id, status FROM loans WHERE id = ?;", (loan_id,))
            loan = cursor.fetchone()
            if not loan:
                raise ValueError(f"Préstamo #{loan_id} no encontrado.")
            if loan["status"] == "cancelado":
                raise ValueError(f"El préstamo #{loan_id} ya se encuentra totalmente cancelado.")

            # Obtener cuotas pendientes ordenadas cronológicamente
            cursor.execute(
                """
                SELECT * FROM installments
                WHERE loan_id = ? AND status IN ('pendiente', 'parcial', 'vencida')
                ORDER BY number ASC;
                """,
                (loan_id,)
            )
            installments = cursor.fetchall()
            if not installments:
                raise ValueError("No hay cuotas pendientes para aplicar el pago.")

            total_mora_applied = Decimal("0.00")
            total_interest_applied = Decimal("0.00")
            total_capital_applied = Decimal("0.00")

            affected_installments = []

            for inst in installments:
                if amount_remaining <= Decimal("0.00"):
                    break

                inst_id = inst["id"]
                cap_exp = Decimal(inst["capital_expected"])
                cap_paid = Decimal(inst["capital_paid"])
                cap_due = cap_exp - cap_paid

                int_exp = Decimal(inst["interest_expected"])
                int_paid = Decimal(inst["interest_paid"])
                int_due = int_exp - int_paid

                # 1. Calcular y cobrar Mora
                mora_total = self.calculator.calculate_installment_late_fee(cap_due, inst["due_date"], pay_date_str)
                mora_paid_prev = Decimal(inst["late_fee_paid"])
                mora_due = max(Decimal("0.00"), mora_total - mora_paid_prev)

                mora_to_pay = Decimal("0.00")
                if mora_due > Decimal("0.00"):
                    mora_to_pay = min(amount_remaining, mora_due)
                    amount_remaining -= mora_to_pay
                    total_mora_applied += mora_to_pay

                # 2. Cobrar Interés Corriente
                interest_to_pay = Decimal("0.00")
                if amount_remaining > Decimal("0.00") and int_due > Decimal("0.00"):
                    interest_to_pay = min(amount_remaining, int_due)
                    amount_remaining -= interest_to_pay
                    total_interest_applied += interest_to_pay

                # 3. Cobrar Capital
                capital_to_pay = Decimal("0.00")
                if amount_remaining > Decimal("0.00") and cap_due > Decimal("0.00"):
                    capital_to_pay = min(amount_remaining, cap_due)
                    amount_remaining -= capital_to_pay
                    total_capital_applied += capital_to_pay

                # Actualizar cuota
                new_cap_paid = cap_paid + capital_to_pay
                new_int_paid = int_paid + interest_to_pay
                new_mora_paid = mora_paid_prev + mora_to_pay

                is_fully_paid = (new_cap_paid >= cap_exp) and (new_int_paid >= int_exp)
                new_status = "pagada" if is_fully_paid else "parcial"
                paid_date_val = pay_date_str if is_fully_paid else None

                cursor.execute(
                    """
                    UPDATE installments SET
                        capital_paid = ?,
                        interest_paid = ?,
                        late_fee_paid = ?,
                        status = ?,
                        paid_date = COALESCE(paid_date, ?)
                    WHERE id = ?;
                    """,
                    (
                        str(new_cap_paid),
                        str(new_int_paid),
                        str(new_mora_paid),
                        new_status,
                        paid_date_val,
                        inst_id
                    )
                )

                affected_installments.append({
                    "installment_id": inst_id,
                    "number": inst["number"],
                    "mora_allocated": mora_to_pay,
                    "interest_allocated": interest_to_pay,
                    "capital_allocated": capital_to_pay,
                    "status": new_status
                })

            # Si sobra dinero tras cubrir todas las cuotas pendientes, abonar directo a capital (prepago)
            # o advertir si ya no queda saldo
            extra_credit = amount_remaining

            # Registrar el pago en la tabla payments
            cursor.execute(
                """
                INSERT INTO payments (
                    loan_id, installment_id, amount, payment_date, payment_method,
                    late_fee_allocated, interest_allocated, capital_allocated, notes, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    loan_id,
                    affected_installments[0]["installment_id"] if affected_installments else None,
                    str(amount - extra_credit),
                    pay_date_str,
                    payment_method,
                    str(total_mora_applied),
                    str(total_interest_applied),
                    str(total_capital_applied),
                    notes,
                    actor_username
                )
            )
            payment_id = cursor.lastrowid

            # Actualizar estado general del préstamo
            cursor.execute(
                """
                SELECT COUNT(*) as pending_cnt
                FROM installments
                WHERE loan_id = ? AND status != 'pagada';
                """,
                (loan_id,)
            )
            has_pending = cursor.fetchone()["pending_cnt"] > 0

            if not has_pending:
                new_loan_status = "cancelado"
            else:
                # Comprobar si tiene alguna cuota vencida
                cursor.execute(
                    """
                    SELECT COUNT(*) as overdue_cnt
                    FROM installments
                    WHERE loan_id = ? AND status IN ('pendiente', 'parcial', 'vencida') AND due_date < ?;
                    """,
                    (loan_id, pay_date_str)
                )
                if cursor.fetchone()["overdue_cnt"] > 0:
                    new_loan_status = "en_mora"
                else:
                    new_loan_status = "activo"

            cursor.execute("UPDATE loans SET status = ? WHERE id = ?;", (new_loan_status, loan_id))

            # Registro de auditoría
            conn.execute(
                "INSERT INTO audit_logs (username, action, details) VALUES (?, ?, ?);",
                (
                    actor_username,
                    "REGISTRAR_PAGO",
                    f"Pago #{payment_id} registrado en préstamo #{loan_id} por {amount}. "
                    f"Mora: {total_mora_applied}, Interés: {total_interest_applied}, Capital: {total_capital_applied}."
                )
            )

            logger.info(f"Pago #{payment_id} procesado con éxito para préstamo #{loan_id}.")

            return {
                "payment_id": payment_id,
                "loan_id": loan_id,
                "amount_paid": amount - extra_credit,
                "excess_unapplied": extra_credit,
                "mora_applied": total_mora_applied,
                "interest_applied": total_interest_applied,
                "capital_applied": total_capital_applied,
                "new_loan_status": new_loan_status,
                "affected_installments": affected_installments
            }

    def list_payments(self, loan_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM payments WHERE 1=1"
            params = []
            if loan_id:
                query += " AND loan_id = ?"
                params.append(loan_id)
            query += " ORDER BY id DESC;"
            cursor.execute(query, tuple(params))
            return [dict(r) for r in cursor.fetchall()]


