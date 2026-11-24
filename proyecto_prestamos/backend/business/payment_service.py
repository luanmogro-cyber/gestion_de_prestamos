import logging
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, List

from backend.database.db_manager import DatabaseManager
from backend.business.loan_calculator import LoanCalculator, ROUND_CENTS

logger = logging.getLogger("prestamos.payments")

class PaymentService:
    """
    Gestión de Pagos, Abonos a Capital, Abonos a Interés y Liquidación de Cuotas.
    Manejo didáctico, flexible y con validación de deudas saldadas.
    """
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()
        self.calculator = LoanCalculator(self.db)

    def get_pending_debt_breakdown(self, loan_id: int, as_of_date_str: Optional[str] = None) -> Dict[str, Any]:
        """Calcula el desglose exigible de deuda al día."""
        as_of_date = as_of_date_str or date.today().strftime("%Y-%m-%d")

        with self.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()

            # Obtener datos del préstamo
            cursor.execute("SELECT * FROM loans WHERE id = ?;", (loan_id,))
            loan = cursor.fetchone()
            if not loan:
                raise ValueError(f"Préstamo #{loan_id} no encontrado.")

            cursor.execute(
                """
                SELECT * FROM installments
                WHERE loan_id = ?
                ORDER BY number ASC;
                """,
                (loan_id,)
            )
            all_rows = cursor.fetchall()

            total_mora = Decimal("0.00")
            total_interes_pendiente = Decimal("0.00")
            total_capital_pendiente = Decimal("0.00")

            paid_cnt = 0
            installments_detail = []

            for r in all_rows:
                cap_exp = Decimal(r["capital_expected"])
                cap_paid = Decimal(r["capital_paid"])
                cap_pending = max(Decimal("0.00"), cap_exp - cap_paid)

                int_exp = Decimal(r["interest_expected"])
                int_paid = Decimal(r["interest_paid"])
                int_pending = max(Decimal("0.00"), int_exp - int_paid)

                if r["status"] == "pagada":
                    paid_cnt += 1
                    mora_pending = Decimal("0.00")
                else:
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
                    "total_pending": cap_pending + int_pending + mora_pending,
                    "status": r["status"]
                })

            total_exigible = total_mora + total_interes_pendiente + total_capital_pendiente
            is_settled = (loan["status"] == "cancelado") or (total_exigible <= Decimal("0.00"))

            return {
                "loan_id": loan_id,
                "pagare_number": loan["pagare_number"] or f"PAG-{loan_id:04d}",
                "as_of_date": as_of_date,
                "status": loan["status"],
                "total_mora": total_mora,
                "total_interes": total_interes_pendiente,
                "total_capital": total_capital_pendiente,
                "total_exigible": total_exigible,
                "is_settled": is_settled,
                "paid_installments_count": paid_cnt,
                "total_installments_count": len(all_rows),
                "cuotas": installments_detail
            }

    def register_payment(
        self,
        loan_id: int,
        amount: Decimal,
        payment_method: str = "efectivo",
        payment_date: Optional[str] = None,
        payment_time: Optional[str] = None,
        payment_type: str = "cuota",
        notes: str = "",
        actor_username: str = "sistema"
    ) -> Dict[str, Any]:
        """
        Registra un abono/pago de cuota con soporte didáctico y flexible:
        - payment_type == 'capital': abono directo a reducción de capital.
        - payment_type == 'interes': abono directo a intereses.
        - payment_type == 'cuota': prelación estándar (Mora -> Interés -> Capital).
        - Validación estricta: si el crédito ya está saldado, no admite más pagos.
        """
        if amount <= Decimal("0.00"):
            raise ValueError("El monto a pagar debe ser mayor a cero.")

        now_dt = datetime.now()
        pay_date_str = payment_date or now_dt.strftime("%Y-%m-%d")
        pay_time_str = payment_time or now_dt.strftime("%H:%M:%S")

        amount_to_apply = amount.quantize(ROUND_CENTS, rounding=ROUND_HALF_UP)
        amount_remaining = amount_to_apply

        with self.db.connection(exclusive_lock=True) as conn:
            cursor = conn.cursor()

            # 1. Validar existencia y estado del préstamo
            cursor.execute("SELECT id, client_id, status, pagare_number FROM loans WHERE id = ?;", (loan_id,))
            loan = cursor.fetchone()
            if not loan:
                raise ValueError(f"Préstamo #{loan_id} no encontrado.")

            pagare_display = loan["pagare_number"] or f"PAG-{loan_id:04d}"

            if loan["status"] == "cancelado":
                raise ValueError(f"¡El crédito #{loan_id} ({pagare_display}) ya se encuentra totalmente SALDADO! No se admiten más pagos.")

            # 2. Consultar cuotas pendientes
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
                cursor.execute("UPDATE loans SET status = 'cancelado' WHERE id = ?;", (loan_id,))
                raise ValueError(f"¡El crédito #{loan_id} ({pagare_display}) no tiene cuotas pendientes y se encuentra SALDADO.")

            total_mora_applied = Decimal("0.00")
            total_interest_applied = Decimal("0.00")
            total_capital_applied = Decimal("0.00")
            affected_installments = []

            # 3. Aplicar pago según el tipo de abono elegido
            p_type = (payment_type or "cuota").lower().strip()

            if p_type == "capital":
                # ABONO DIRECTO A CAPITAL
                for inst in installments:
                    if amount_remaining <= Decimal("0.00"):
                        break
                    inst_id = inst["id"]
                    cap_exp = Decimal(inst["capital_expected"])
                    cap_paid = Decimal(inst["capital_paid"])
                    cap_due = max(Decimal("0.00"), cap_exp - cap_paid)

                    if cap_due > Decimal("0.00"):
                        cap_to_pay = min(amount_remaining, cap_due)
                        amount_remaining -= cap_to_pay
                        total_capital_applied += cap_to_pay

                        new_cap_paid = cap_paid + cap_to_pay
                        int_exp = Decimal(inst["interest_expected"])
                        int_paid = Decimal(inst["interest_paid"])
                        is_fully_paid = (new_cap_paid >= cap_exp) and (int_paid >= int_exp)
                        new_status = "pagada" if is_fully_paid else "parcial"

                        cursor.execute(
                            """
                            UPDATE installments SET
                                capital_paid = ?,
                                status = ?,
                                paid_date = CASE WHEN ? = 'pagada' THEN COALESCE(paid_date, ?) ELSE paid_date END
                            WHERE id = ?;
                            """,
                            (str(new_cap_paid), new_status, new_status, pay_date_str, inst_id)
                        )
                        affected_installments.append({"installment_id": inst_id, "number": inst["number"], "status": new_status})

            elif p_type == "interes":
                # ABONO DIRECTO A INTERÉS
                for inst in installments:
                    if amount_remaining <= Decimal("0.00"):
                        break
                    inst_id = inst["id"]
                    int_exp = Decimal(inst["interest_expected"])
                    int_paid = Decimal(inst["interest_paid"])
                    int_due = max(Decimal("0.00"), int_exp - int_paid)

                    if int_due > Decimal("0.00"):
                        int_to_pay = min(amount_remaining, int_due)
                        amount_remaining -= int_to_pay
                        total_interest_applied += int_to_pay

                        new_int_paid = int_paid + int_to_pay
                        cap_exp = Decimal(inst["capital_expected"])
                        cap_paid = Decimal(inst["capital_paid"])
                        is_fully_paid = (cap_paid >= cap_exp) and (new_int_paid >= int_exp)
                        new_status = "pagada" if is_fully_paid else "parcial"

                        cursor.execute(
                            """
                            UPDATE installments SET
                                interest_paid = ?,
                                status = ?,
                                paid_date = CASE WHEN ? = 'pagada' THEN COALESCE(paid_date, ?) ELSE paid_date END
                            WHERE id = ?;
                            """,
                            (str(new_int_paid), new_status, new_status, pay_date_str, inst_id)
                        )
                        affected_installments.append({"installment_id": inst_id, "number": inst["number"], "status": new_status})

            else:
                # PAGO REGULAR DE CUOTA (Prelación: 1° Mora -> 2° Interés -> 3° Capital)
                for inst in installments:
                    if amount_remaining <= Decimal("0.00"):
                        break

                    inst_id = inst["id"]
                    cap_exp = Decimal(inst["capital_expected"])
                    cap_paid = Decimal(inst["capital_paid"])
                    cap_due = max(Decimal("0.00"), cap_exp - cap_paid)

                    int_exp = Decimal(inst["interest_expected"])
                    int_paid = Decimal(inst["interest_paid"])
                    int_due = max(Decimal("0.00"), int_exp - int_paid)

                    # Mora
                    mora_total = self.calculator.calculate_installment_late_fee(cap_due, inst["due_date"], pay_date_str)
                    mora_paid_prev = Decimal(inst["late_fee_paid"])
                    mora_due = max(Decimal("0.00"), mora_total - mora_paid_prev)

                    mora_to_pay = Decimal("0.00")
                    if mora_due > Decimal("0.00"):
                        mora_to_pay = min(amount_remaining, mora_due)
                        amount_remaining -= mora_to_pay
                        total_mora_applied += mora_to_pay

                    # Interés
                    int_to_pay = Decimal("0.00")
                    if amount_remaining > Decimal("0.00") and int_due > Decimal("0.00"):
                        int_to_pay = min(amount_remaining, int_due)
                        amount_remaining -= int_to_pay
                        total_interest_applied += int_to_pay

                    # Capital
                    cap_to_pay = Decimal("0.00")
                    if amount_remaining > Decimal("0.00") and cap_due > Decimal("0.00"):
                        cap_to_pay = min(amount_remaining, cap_due)
                        amount_remaining -= cap_to_pay
                        total_capital_applied += cap_to_pay

                    new_cap_paid = cap_paid + cap_to_pay
                    new_int_paid = int_paid + int_to_pay
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
                        (str(new_cap_paid), str(new_int_paid), str(new_mora_paid), new_status, paid_date_val, inst_id)
                    )
                    affected_installments.append({"installment_id": inst_id, "number": inst["number"], "status": new_status})

            actual_paid = amount_to_apply - amount_remaining

            # 4. Insertar en payments
            cursor.execute(
                """
                INSERT INTO payments (
                    loan_id, installment_id, amount, payment_date, payment_method,
                    payment_type, payment_time, late_fee_allocated, interest_allocated,
                    capital_allocated, notes, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    loan_id,
                    affected_installments[0]["installment_id"] if affected_installments else None,
                    str(actual_paid),
                    pay_date_str,
                    payment_method,
                    p_type,
                    pay_time_str,
                    str(total_mora_applied),
                    str(total_interest_applied),
                    str(total_capital_applied),
                    notes,
                    actor_username
                )
            )
            payment_id = cursor.lastrowid

            # 5. Comprobar si se canceló totalmente la deuda
            cursor.execute(
                """
                SELECT COUNT(*) as pending_cnt
                FROM installments
                WHERE loan_id = ? AND status != 'pagada';
                """,
                (loan_id,)
            )
            has_pending = cursor.fetchone()["pending_cnt"] > 0

            cursor.execute(
                """
                SELECT 
                    SUM(CAST(capital_expected AS REAL) - CAST(capital_paid AS REAL)) as rem_cap,
                    SUM(CAST(interest_expected AS REAL) - CAST(interest_paid AS REAL)) as rem_int
                FROM installments WHERE loan_id = ?;
                """,
                (loan_id,)
            )
            rem_row = cursor.fetchone()
            rem_cap = Decimal(str(rem_row["rem_cap"] or 0))
            rem_int = Decimal(str(rem_row["rem_int"] or 0))

            is_settled = False
            if (not has_pending) or (rem_cap <= Decimal("0.00") and rem_int <= Decimal("0.00")):
                new_loan_status = "cancelado"
                is_settled = True
                cursor.execute("UPDATE installments SET status = 'pagada' WHERE loan_id = ?;", (loan_id,))
            else:
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

            conn.execute(
                "INSERT INTO audit_logs (username, action, details) VALUES (?, ?, ?);",
                (
                    actor_username,
                    "REGISTRAR_PAGO",
                    f"Pago #{payment_id} ({p_type.upper()}) registrado en préstamo #{loan_id} por ${actual_paid:,.2f}. "
                    f"Capital: ${total_capital_applied:,.2f}, Interés: ${total_interest_applied:,.2f}, Mora: ${total_mora_applied:,.2f}. "
                    f"Estado resultante: {new_loan_status.upper()}."
                )
            )

            logger.info(f"Pago #{payment_id} procesado con éxito para préstamo #{loan_id}. Estado: {new_loan_status}.")

            return {
                "payment_id": payment_id,
                "loan_id": loan_id,
                "pagare_number": pagare_display,
                "amount_paid": actual_paid,
                "excess_unapplied": amount_remaining,
                "payment_type": p_type,
                "payment_time": f"{pay_date_str} {pay_time_str}",
                "mora_applied": total_mora_applied,
                "interest_applied": total_interest_applied,
                "capital_applied": total_capital_applied,
                "new_loan_status": new_loan_status,
                "is_settled": is_settled,
                "affected_installments": affected_installments
            }

    def edit_payment(
        self,
        payment_id: int,
        new_amount: Decimal,
        new_payment_type: str,
        new_payment_method: str,
        new_notes: str,
        actor_username: str = "sistema"
    ) -> Dict[str, Any]:
        """Permite editar una cuota o pago que haya tenido un error de digitación."""
        with self.db.connection(exclusive_lock=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM payments WHERE id = ?;", (payment_id,))
            p = cursor.fetchone()
            if not p:
                raise ValueError(f"Pago #{payment_id} no encontrado.")

            loan_id = p["loan_id"]

        self.delete_payment(payment_id, actor_username=actor_username)
        return self.register_payment(
            loan_id=loan_id,
            amount=new_amount,
            payment_method=new_payment_method,
            payment_type=new_payment_type,
            notes=new_notes,
            actor_username=actor_username
        )

    def delete_payment(self, payment_id: int, actor_username: str = "sistema") -> bool:
        """Elimina un pago erróneo y revierte la amortización de cuotas y estado del crédito."""
        with self.db.connection(exclusive_lock=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM payments WHERE id = ?;", (payment_id,))
            p = cursor.fetchone()
            if not p:
                raise ValueError(f"Pago #{payment_id} no encontrado.")

            loan_id = p["loan_id"]
            cap_rev = Decimal(p["capital_allocated"])
            int_rev = Decimal(p["interest_allocated"])
            mora_rev = Decimal(p["late_fee_allocated"])

            cursor.execute(
                """
                SELECT * FROM installments
                WHERE loan_id = ? AND (CAST(capital_paid AS REAL) > 0 OR CAST(interest_paid AS REAL) > 0 OR CAST(late_fee_paid AS REAL) > 0)
                ORDER BY number DESC;
                """,
                (loan_id,)
            )
            rows = cursor.fetchall()

            for r in rows:
                if cap_rev <= Decimal("0.00") and int_rev <= Decimal("0.00") and mora_rev <= Decimal("0.00"):
                    break

                inst_id = r["id"]
                cap_paid = Decimal(r["capital_paid"])
                int_paid = Decimal(r["interest_paid"])
                mora_paid = Decimal(r["late_fee_paid"])

                take_mora = min(mora_rev, mora_paid)
                mora_rev -= take_mora
                new_mora = mora_paid - take_mora

                take_int = min(int_rev, int_paid)
                int_rev -= take_int
                new_int = int_paid - take_int

                take_cap = min(cap_rev, cap_paid)
                cap_rev -= take_cap
                new_cap = cap_paid - take_cap

                cap_exp = Decimal(r["capital_expected"])
                int_exp = Decimal(r["interest_expected"])

                if (new_cap >= cap_exp) and (new_int >= int_exp):
                    new_st = "pagada"
                elif (new_cap > 0) or (new_int > 0) or (new_mora > 0):
                    new_st = "parcial"
                else:
                    new_st = "pendiente"

                cursor.execute(
                    """
                    UPDATE installments SET
                        capital_paid = ?, interest_paid = ?, late_fee_paid = ?,
                        status = ?, paid_date = CASE WHEN ? = 'pagada' THEN paid_date ELSE NULL END
                    WHERE id = ?;
                    """,
                    (str(new_cap), str(new_int), str(new_mora), new_st, new_st, inst_id)
                )

            cursor.execute("DELETE FROM payments WHERE id = ?;", (payment_id,))

            today_str = date.today().strftime("%Y-%m-%d")
            cursor.execute(
                """
                SELECT COUNT(*) as overdue_cnt FROM installments
                WHERE loan_id = ? AND status != 'pagada' AND due_date < ?;
                """,
                (loan_id, today_str)
            )
            if cursor.fetchone()["overdue_cnt"] > 0:
                restored_st = "en_mora"
            else:
                restored_st = "activo"

            cursor.execute("UPDATE loans SET status = ? WHERE id = ?;", (restored_st, loan_id))

            conn.execute(
                "INSERT INTO audit_logs (username, action, details) VALUES (?, ?, ?);",
                (actor_username, "ELIMINAR_PAGO", f"Pago #{payment_id} eliminado de préstamo #{loan_id}. Estado restaurado a {restored_st}.")
            )
            logger.info(f"Pago #{payment_id} eliminado y saldos revertidos con éxito.")
            return True

    def search_loans_and_clients(self, query: str = "") -> List[Dict[str, Any]]:
        """
        Búsqueda multicriterio didáctica:
        Busca por Cédula / Documento, Nombre o Apellido, Nº de Crédito o Pagaré.
        Genera los datos exactos requeridos en la FOTO 2 de la pizarra:
        - Documento
        - Nombre
        - Monto
        - Fecha
        - # Cuota / Plazo
        - Capital
        - Interés
        - Saldo
        """
        q = f"%{query.strip()}%" if query.strip() else "%"

        with self.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()
            sql = """
                SELECT 
                    l.id as loan_id,
                    COALESCE(l.pagare_number, 'PAG-' || printf('%04d', l.id)) as pagare_number,
                    l.principal,
                    l.disbursement_date,
                    l.installments_count,
                    l.status as loan_status,
                    c.id as client_id,
                    printf('CLI-%04d', c.id) as client_code,
                    c.doc_type,
                    c.doc_number,
                    c.first_name,
                    c.last_name,
                    (c.first_name || ' ' || c.last_name) as client_full_name,
                    c.phone
                FROM loans l
                JOIN clients c ON l.client_id = c.id
                WHERE (
                    c.doc_number LIKE ?
                    OR c.first_name LIKE ?
                    OR c.last_name LIKE ?
                    OR (c.first_name || ' ' || c.last_name) LIKE ?
                    OR l.pagare_number LIKE ?
                    OR ('CRE-' || printf('%04d', l.id)) LIKE ?
                    OR ('PAG-' || printf('%04d', l.id)) LIKE ?
                    OR ('CLI-' || printf('%04d', c.id)) LIKE ?
                    OR CAST(l.id AS TEXT) = ?
                )
                ORDER BY l.id DESC;
            """
            clean_term = query.strip()
            cursor.execute(sql, (q, q, q, q, q, q, q, q, clean_term))
            rows = cursor.fetchall()

            today_str = date.today().strftime("%Y-%m-%d")
            results = []

            for r in rows:
                loan_id = r["loan_id"]

                cursor.execute(
                    """
                    SELECT 
                        COUNT(*) as total_cuotas,
                        SUM(CASE WHEN status = 'pagada' THEN 1 ELSE 0 END) as pagadas,
                        SUM(CAST(capital_expected AS REAL) - CAST(capital_paid AS REAL)) as rem_cap,
                        SUM(CAST(interest_expected AS REAL) - CAST(interest_paid AS REAL)) as rem_int
                    FROM installments
                    WHERE loan_id = ?;
                    """,
                    (loan_id,)
                )
                stats = cursor.fetchone()

                total_cuotas = stats["total_cuotas"] or r["installments_count"]
                pagadas = stats["pagadas"] or 0
                rem_cap = max(Decimal("0.00"), Decimal(str(stats["rem_cap"] or 0)).quantize(ROUND_CENTS))
                rem_int = max(Decimal("0.00"), Decimal(str(stats["rem_int"] or 0)).quantize(ROUND_CENTS))

                breakdown = self.get_pending_debt_breakdown(loan_id, as_of_date_str=today_str)
                mora = breakdown["total_mora"]
                saldo_total = rem_cap + rem_int + mora

                cuota_plazo_str = f"{pagadas} / {total_cuotas} pagadas"

                results.append({
                    "loan_id": loan_id,
                    "pagare_number": r["pagare_number"],
                    "documento": f"{r['doc_type']}-{r['doc_number']}",
                    "doc_number_plain": r["doc_number"],
                    "nombre": r["client_full_name"],
                    "client_code": r["client_code"],
                    "monto": Decimal(r["principal"]).quantize(ROUND_CENTS),
                    "fecha": r["disbursement_date"],
                    "cuota_plazo": cuota_plazo_str,
                    "cuotas_pagadas": pagadas,
                    "cuotas_totales": total_cuotas,
                    "capital": rem_cap,
                    "interes": rem_int,
                    "mora": mora,
                    "saldo": saldo_total,
                    "status": r["loan_status"],
                    "phone": r["phone"]
                })

            return results

    def list_payments(self, loan_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Devuelve el historial detallado de pagos con fecha y hora real."""
        with self.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()
            query = """
                SELECT 
                    p.*,
                    COALESCE(p.payment_type, 'cuota') as payment_type,
                    COALESCE(p.payment_time, p.payment_date) as full_timestamp,
                    COALESCE(l.pagare_number, 'PAG-' || printf('%04d', l.id)) as pagare_number,
                    c.first_name || ' ' || c.last_name as client_name,
                    c.doc_number
                FROM payments p
                JOIN loans l ON p.loan_id = l.id
                JOIN clients c ON l.client_id = c.id
                WHERE 1=1
            """
            params = []
            if loan_id:
                query += " AND p.loan_id = ?"
                params.append(loan_id)
            query += " ORDER BY p.id DESC;"
            cursor.execute(query, tuple(params))
            return [dict(r) for r in cursor.fetchall()]
