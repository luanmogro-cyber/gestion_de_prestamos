from decimal import Decimal
from datetime import date
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QComboBox, QDoubleSpinBox, QDateEdit,
    QGroupBox, QFormLayout, QFileDialog, QSplitter
)
from PySide6.QtCore import Qt, QDate

from backend.business.payment_service import PaymentService
from backend.business.loan_calculator import LoanCalculator
from backend.business.pdf_generator import PdfReportGenerator

class PaymentsView(QWidget):
    """
    Vista de Pagos y Cobranzas (PR-17 a PR-20).
    Aplica rigurosamente la prelación: 1° Mora -> 2° Interés -> 3° Capital.
    Genera comprobantes de pago PDF de inmediato.
    """
    def __init__(self, payment_service: PaymentService, loan_calculator: LoanCalculator, current_user: dict, parent=None):
        super(PaymentsView, self).__init__(parent)
        self.payment_service = payment_service
        self.calculator = loan_calculator
        self.pdf_gen = PdfReportGenerator(self.calculator.db)
        self.current_user = current_user

        self._build_ui()
        self.refresh_loans_combo()
        self.load_payments_history()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        splitter = QSplitter(Qt.Horizontal)

        # Panel izquierdo: Formulario de Registro de Pago
        left_widget = QGroupBox("Registrar Pago de Cuota / Abono")
        left_widget.setFixedWidth(400)
        form = QFormLayout(left_widget)

        self.cb_loans = QComboBox()
        self.cb_loans.currentIndexChanged.connect(self._on_loan_selection_changed)
        form.addRow("Préstamo Activo:", self.cb_loans)

        # Desglose exigible con contraste de texto alto y visible
        self.lbl_debt_info = QLabel("Seleccione un préstamo para ver la deuda exigible.")
        self.lbl_debt_info.setStyleSheet("""
            background-color: #FEF3C7;
            color: #78350F !important;
            border: 1.5px solid #F59E0B;
            border-radius: 6px;
            padding: 10px 12px;
            font-size: 12px;
            font-weight: 500;
        """)
        self.lbl_debt_info.setWordWrap(True)
        form.addRow(self.lbl_debt_info)

        self.sp_amount = QDoubleSpinBox()
        self.sp_amount.setRange(1.0, 1000000000.0)
        self.sp_amount.setPrefix("$ ")
        self.sp_amount.setDecimals(2)
        form.addRow("Monto a Pagar:", self.sp_amount)

        self.cb_method = QComboBox()
        self.cb_method.addItems(["efectivo", "transferencia", "tarjeta", "cheque"])
        form.addRow("Método de Pago:", self.cb_method)

        self.dt_pay_date = QDateEdit()
        self.dt_pay_date.setDate(QDate.currentDate())
        self.dt_pay_date.setCalendarPopup(True)
        form.addRow("Fecha de Pago:", self.dt_pay_date)

        self.txt_notes = QLineEdit()
        self.txt_notes.setPlaceholderText("Comprobante o nota opcional")
        form.addRow("Observaciones:", self.txt_notes)

        btn_pay = QPushButton("Registrar y Aplicar Pago")
        btn_pay.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 10px; border-radius: 4px;")
        btn_pay.clicked.connect(self._do_payment)
        form.addRow(btn_pay)

        splitter.addWidget(left_widget)

        # Panel derecho: Historial de Pagos
        right_widget = QGroupBox("Historial de Recaudo y Comprobantes")
        right_layout = QVBoxLayout(right_widget)

        self.table_history = QTableWidget()
        self.table_history.setColumnCount(8)
        self.table_history.setHorizontalHeaderLabels([
            "Pago #", "Préstamo", "Fecha", "Método", "Mora", "Interés", "Capital", "Acción"
        ])
        self.table_history.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right_layout.addWidget(self.table_history)

        splitter.addWidget(right_widget)
        layout.addWidget(splitter)

    def refresh_loans_combo(self):
        self.cb_loans.clear()
        loans = self.calculator.list_loans()
        active_loans = [l for l in loans if l["status"] in ("activo", "en_mora")]
        for l in active_loans:
            self.cb_loans.addItem(f"Préstamo #{l['id']} - {l['first_name']} {l['last_name']} ({l['status'].upper()})", l["id"])

    def _on_loan_selection_changed(self):
        if self.cb_loans.currentIndex() < 0:
            self.lbl_debt_info.setText("Seleccione un préstamo.")
            return

        loan_id = self.cb_loans.currentData()
        breakdown = self.payment_service.get_pending_debt_breakdown(loan_id)
        sym = "$"

        self.lbl_debt_info.setText(
            f"<div style='color: #78350F; font-size: 12px; line-height: 1.4;'>"
            f"<b style='font-size: 13px; color: #92400E;'>📋 Desglose Exigible al día:</b><br/>"
            f"<span style='color: #78350F;'>• <b>Intereses de Mora:</b> {sym}{breakdown['total_mora']:,.2f}</span><br/>"
            f"<span style='color: #78350F;'>• <b>Interés Corriente:</b> {sym}{breakdown['total_interes']:,.2f}</span><br/>"
            f"<span style='color: #78350F;'>• <b>Capital Pendiente:</b> {sym}{breakdown['total_capital']:,.2f}</span><br/>"
            f"<span style='font-size: 13px; color: #9A3412;'><b>💰 Total Deuda Exigible: {sym}{breakdown['total_exigible']:,.2f}</b></span>"
            f"</div>"
        )
        if breakdown["total_exigible"] > 0:
            self.sp_amount.setValue(float(breakdown["cuotas"][0]["total_pending"] if breakdown["cuotas"] else breakdown["total_exigible"]))

    def _do_payment(self):
        if self.cb_loans.currentIndex() < 0:
            QMessageBox.warning(self, "Atención", "Debe seleccionar un préstamo activo.")
            return

        loan_id = self.cb_loans.currentData()
        amount = Decimal(str(self.sp_amount.value()))
        method = self.cb_method.currentText()
        pay_date = self.dt_pay_date.date().toString("yyyy-MM-dd")
        notes = self.txt_notes.text().strip()

        try:
            res = self.payment_service.register_payment(
                loan_id=loan_id,
                amount=amount,
                payment_method=method,
                payment_date=pay_date,
                notes=notes,
                actor_username=self.current_user["username"]
            )
            pid = res["payment_id"]

            QMessageBox.information(
                self, "Pago Registrado",
                f"Pago #{pid} procesado exitosamente.\n"
                f"Aplicado a Mora: ${res['mora_applied']:,.2f}\n"
                f"Aplicado a Interés: ${res['interest_applied']:,.2f}\n"
                f"Aplicado a Capital: ${res['capital_applied']:,.2f}\n"
                f"Nuevo estado del préstamo: {res['new_loan_status'].upper()}"
            )

            # Ofrecer descargar comprobante PDF de inmediato
            ask_pdf = QMessageBox.question(
                self, "Comprobante de Pago",
                "¿Desea generar y descargar el Comprobante de Pago en PDF ahora?",
                QMessageBox.Yes | QMessageBox.No
            )
            if ask_pdf == QMessageBox.Yes:
                self._export_payment_pdf(pid)

            self.refresh_loans_combo()
            self.load_payments_history()

        except Exception as e:
            QMessageBox.critical(self, "Error al Procesar Pago", str(e))

    def load_payments_history(self):
        try:
            payments = self.payment_service.list_payments()
            self.table_history.setRowCount(len(payments))
            for idx, p in enumerate(payments):
                self.table_history.setItem(idx, 0, QTableWidgetItem(f"#{p['id']}"))
                self.table_history.setItem(idx, 1, QTableWidgetItem(f"#{p['loan_id']}"))
                self.table_history.setItem(idx, 2, QTableWidgetItem(p["payment_date"]))
                self.table_history.setItem(idx, 3, QTableWidgetItem(p["payment_method"].upper()))
                self.table_history.setItem(idx, 4, QTableWidgetItem(f"${Decimal(p['late_fee_allocated']):,.2f}"))
                self.table_history.setItem(idx, 5, QTableWidgetItem(f"${Decimal(p['interest_allocated']):,.2f}"))
                self.table_history.setItem(idx, 6, QTableWidgetItem(f"${Decimal(p['capital_allocated']):,.2f}"))

                btn_receipt = QPushButton("PDF Recibo")
                btn_receipt.setStyleSheet("background-color: #3B82F6; color: white; padding: 2px 6px;")
                btn_receipt.clicked.connect(lambda _, pid=p["id"]: self._export_payment_pdf(pid))
                self.table_history.setCellWidget(idx, 7, btn_receipt)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error cargando pagos: {e}")

    def _export_payment_pdf(self, payment_id: int):
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar Comprobante de Pago en PDF",
            f"Comprobante_Pago_{payment_id}.pdf",
            "Archivos PDF (*.pdf)"
        )
        if path:
            try:
                self.pdf_gen.generate_payment_receipt(payment_id, Path(path), self.current_user["username"])
                QMessageBox.information(self, "Comprobante Creado", f"Comprobante PDF guardado en:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error PDF", str(e))


