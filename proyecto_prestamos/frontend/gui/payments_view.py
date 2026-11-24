import os
from decimal import Decimal
from datetime import datetime, date
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QComboBox, QDoubleSpinBox, QDateEdit,
    QGroupBox, QFormLayout, QFileDialog, QSplitter, QDialog,
    QRadioButton, QButtonGroup, QFrame, QTextEdit
)
from PySide6.QtCore import Qt, QDate, QTime, QTimer
from PySide6.QtGui import QColor, QFont

from backend.business.payment_service import PaymentService
from backend.business.loan_calculator import LoanCalculator
from backend.business.pdf_generator import PdfReportGenerator


class PaymentModalDialog(QDialog):
    """
    Diálogo didáctico e intuitivo para registrar pagos o abonos.
    - Muestra fecha y hora real automáticamente en tiempo real.
    - Permite elegir si es Abono a Capital, Abono a Interés o Cuota completa.
    - Bloquea pagos si el crédito ya está saldado y muestra un aviso visual claro.
    """
    def __init__(self, loan_data: dict, payment_service: PaymentService, current_user: dict, parent=None):
        super(PaymentModalDialog, self).__init__(parent)
        self.loan_data = loan_data
        self.payment_service = payment_service
        self.current_user = current_user

        self.setWindowTitle(f"Registrar Pago / Abono - Crédito {loan_data['pagare_number']}")
        self.resize(540, 560)
        self.setModal(True)

        self._build_ui()
        self._start_clock()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 1. Encabezado didáctico con datos del cliente y crédito
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            background-color: #1E293B;
            border-radius: 8px;
            padding: 12px;
        """)
        h_layout = QVBoxLayout(header_frame)
        h_layout.setContentsMargins(10, 8, 10, 8)
        h_layout.setSpacing(4)

        lbl_title = QLabel(f"💳 <b>Crédito: {self.loan_data['pagare_number']}</b>")
        lbl_title.setStyleSheet("font-size: 15px; color: #38BDF8;")
        h_layout.addWidget(lbl_title)

        lbl_client = QLabel(f"👤 <b>Cliente:</b> {self.loan_data['nombre']} | <b>Doc:</b> {self.loan_data['documento']}")
        lbl_client.setStyleSheet("font-size: 12px; color: #CBD5E1;")
        h_layout.addWidget(lbl_client)

        saldo_val = self.loan_data['saldo']
        lbl_saldo = QLabel(f"💰 <b>Saldo Total Pendiente:</b> ${saldo_val:,.2f}")
        lbl_saldo.setStyleSheet("font-size: 13px; color: #F59E0B; font-weight: bold;")
        h_layout.addWidget(lbl_saldo)

        layout.addWidget(header_frame)

        # 2. Verificación: Si ya está saldado, mostrar aviso y no dejar agregar más pagos
        self.is_already_settled = (self.loan_data["status"] == "cancelado") or (saldo_val <= Decimal("0.00"))
        if self.is_already_settled:
            settled_box = QFrame()
            settled_box.setStyleSheet("""
                background-color: #ECFDF5;
                border: 2px solid #10B981;
                border-radius: 8px;
                padding: 15px;
            """)
            s_layout = QVBoxLayout(settled_box)
            lbl_congrats = QLabel("🎉 <b>¡ESTE PRÉSTAMO YA ESTÁ COMPLETAMENTE SALDADO!</b>")
            lbl_congrats.setStyleSheet("color: #065F46; font-size: 14px; text-align: center;")
            lbl_congrats.setAlignment(Qt.AlignCenter)
            s_layout.addWidget(lbl_congrats)

            lbl_sub = QLabel("No existen deudas ni cuotas pendientes por pagar para este crédito.")
            lbl_sub.setStyleSheet("color: #047857; font-size: 12px;")
            lbl_sub.setAlignment(Qt.AlignCenter)
            s_layout.addWidget(lbl_sub)

            layout.addWidget(settled_box)

            # Botón de solo cerrar
            btn_close = QPushButton("Entendido (Cerrar)")
            btn_close.setStyleSheet("background-color: #64748B; color: white; padding: 10px; border-radius: 6px; font-weight: bold;")
            btn_close.clicked.connect(self.reject)
            layout.addWidget(btn_close)
            return

        # 3. Fecha y Hora Real Automática
        clock_group = QGroupBox("⏰ Registro Automático de Fecha y Hora Real")
        clock_layout = QHBoxLayout(clock_group)
        self.lbl_clock = QLabel()
        self.lbl_clock.setStyleSheet("font-size: 14px; font-weight: bold; color: #10B981; padding: 4px;")
        clock_layout.addWidget(self.lbl_clock)
        layout.addWidget(clock_group)

        # 4. Tipo de Abono (Didáctico para que cualquier persona lo entienda)
        type_group = QGroupBox("🎯 ¿Qué tipo de abono desea realizar?")
        type_layout = QVBoxLayout(type_group)
        type_layout.setSpacing(8)

        self.btn_group_type = QButtonGroup(self)

        self.rb_cuota = QRadioButton("🟡 Pago de Cuota Regular (Cubre Mora, Interés y Capital en orden legal)")
        self.rb_cuota.setChecked(True)
        self.rb_cuota.setStyleSheet("font-size: 12px; font-weight: 500;")
        self.btn_group_type.addButton(self.rb_cuota)
        type_layout.addWidget(self.rb_cuota)

        self.rb_capital = QRadioButton("🟢 Abono Directo a Capital (Reduce directamente la deuda del préstamo)")
        self.rb_capital.setStyleSheet("font-size: 12px; font-weight: 500; color: #059669;")
        self.btn_group_type.addButton(self.rb_capital)
        type_layout.addWidget(self.rb_capital)

        self.rb_interes = QRadioButton("🔵 Abono a Intereses (Paga los intereses causados sin tocar el capital)")
        self.rb_interes.setStyleSheet("font-size: 12px; font-weight: 500; color: #2563EB;")
        self.btn_group_type.addButton(self.rb_interes)
        type_layout.addWidget(self.rb_interes)

        layout.addWidget(type_group)

        # 5. Formulario de Monto y Método
        form_group = QGroupBox("💵 Datos del Abono")
        form = QFormLayout(form_group)
        form.setSpacing(10)

        # Botones de sugerencia rápida didáctica
        quick_btn_layout = QHBoxLayout()
        btn_quick_quota = QPushButton("💵 Valor de 1 Cuota")
        btn_quick_quota.setStyleSheet("background-color: #E2E8F0; color: #1E293B; font-weight: bold; padding: 6px; border-radius: 4px;")
        btn_quick_quota.clicked.connect(self._set_quick_quota)
        quick_btn_layout.addWidget(btn_quick_quota)

        btn_quick_all = QPushButton("💰 Pagar Todo (Liquidar)")
        btn_quick_all.setStyleSheet("background-color: #FEF3C7; color: #92400E; font-weight: bold; padding: 6px; border-radius: 4px;")
        btn_quick_all.clicked.connect(self._set_quick_all)
        quick_btn_layout.addWidget(btn_quick_all)

        form.addRow("Sugerencias:", quick_btn_layout)

        self.sp_amount = QDoubleSpinBox()
        self.sp_amount.setRange(100.0, float(saldo_val * 2 if saldo_val > 0 else 100000000))
        self.sp_amount.setPrefix("$ ")
        self.sp_amount.setDecimals(2)
        self.sp_amount.setValue(min(float(saldo_val), 100000.0))
        self.sp_amount.setStyleSheet("font-size: 14px; font-weight: bold; padding: 6px;")
        form.addRow("Monto a Abonar:", self.sp_amount)

        self.cb_method = QComboBox()
        self.cb_method.addItems(["efectivo", "transferencia", "tarjeta", "cheque"])
        self.cb_method.setStyleSheet("padding: 6px;")
        form.addRow("Método de Pago:", self.cb_method)

        self.txt_notes = QLineEdit()
        self.txt_notes.setPlaceholderText("Comprobante o nota opcional")
        self.txt_notes.setStyleSheet("padding: 6px;")
        form.addRow("Observación / Ref:", self.txt_notes)

        layout.addWidget(form_group)

        # 6. Botones de Acción
        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet("background-color: #94A3B8; color: white; padding: 10px 16px; border-radius: 6px;")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        self.btn_confirm = QPushButton("✅ Confirmar y Aplicar Abono")
        self.btn_confirm.setStyleSheet("background-color: #059669; color: white; font-weight: bold; font-size: 13px; padding: 10px 20px; border-radius: 6px;")
        self.btn_confirm.clicked.connect(self._submit_payment)
        btn_box.addWidget(self.btn_confirm)

        layout.addLayout(btn_box)

    def _start_clock(self):
        if hasattr(self, "lbl_clock"):
            self._update_clock()
            self.clock_timer = QTimer(self)
            self.clock_timer.timeout.connect(self._update_clock)
            self.clock_timer.start(1000)

    def _update_clock(self):
        now = datetime.now()
        self.current_date_str = now.strftime("%Y-%m-%d")
        self.current_time_str = now.strftime("%H:%M:%S")
        self.lbl_clock.setText(f"📅 Fecha: {now.strftime('%d/%m/%Y')}   |   🕒 Hora: {self.current_time_str}")

    def _set_quick_quota(self):
        try:
            breakdown = self.payment_service.get_pending_debt_breakdown(self.loan_data["loan_id"])
            if breakdown["cuotas"]:
                quota_val = float(breakdown["cuotas"][0]["total_pending"])
                self.sp_amount.setValue(quota_val)
        except Exception:
            pass

    def _set_quick_all(self):
        self.sp_amount.setValue(float(self.loan_data["saldo"]))

    def _submit_payment(self):
        amount = Decimal(str(self.sp_amount.value()))
        if amount <= Decimal("0.00"):
            QMessageBox.warning(self, "Monto Inválido", "Por favor ingrese un monto mayor a cero.")
            return

        if self.rb_capital.isChecked():
            p_type = "capital"
        elif self.rb_interes.isChecked():
            p_type = "interes"
        else:
            p_type = "cuota"

        method = self.cb_method.currentText()
        notes = self.txt_notes.text().strip()

        try:
            res = self.payment_service.register_payment(
                loan_id=self.loan_data["loan_id"],
                amount=amount,
                payment_method=method,
                payment_date=self.current_date_str,
                payment_time=self.current_time_str,
                payment_type=p_type,
                notes=notes,
                actor_username=self.current_user["username"]
            )

            # Notificación didáctica de éxito
            if res.get("is_settled"):
                QMessageBox.information(
                    self,
                    "🎉 ¡CRÉDITO SALDADO!",
                    f"<b>¡FELICITACIONES!</b><br/><br/>"
                    f"El pago por <b>${res['amount_paid']:,.2f}</b> ha liquidado la deuda por completo.<br/>"
                    f"El crédito <b>{res['pagare_number']}</b> ha quedado <b>TOTALMENTE SALDADO</b>."
                )
            else:
                QMessageBox.information(
                    self,
                    "Abono Aplicado",
                    f"Abono registrado con éxito por <b>${res['amount_paid']:,.2f}</b> ({p_type.upper()}).<br/>"
                    f"Fecha y Hora: {res['payment_time']}"
                )

            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error al Aplicar Pago", str(e))


class InstallmentsHistoryDialog(QDialog):
    """
    Diálogo para ver las cuotas y pagos realizados hasta la fecha.
    Permite:
    - Ver historial detallado con fecha y hora real.
    - Editar un pago registrado erróneamente.
    - Eliminar un pago y revertir automáticamente el saldo.
    """
    def __init__(self, loan_data: dict, payment_service: PaymentService, current_user: dict, parent=None):
        super(InstallmentsHistoryDialog, self).__init__(parent)
        self.loan_data = loan_data
        self.payment_service = payment_service
        self.current_user = current_user

        self.setWindowTitle(f"Historial de Cuotas y Abonos - {loan_data['pagare_number']}")
        self.resize(880, 520)
        self.setModal(True)

        self._build_ui()
        self.load_history()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # Header info
        header = QLabel(
            f"<b>Crédito:</b> {self.loan_data['pagare_number']}  |  "
            f"<b>Cliente:</b> {self.loan_data['nombre']} ({self.loan_data['documento']})  |  "
            f"<b>Monto Inicial:</b> ${self.loan_data['monto']:,.2f}"
        )
        header.setStyleSheet("font-size: 13px; color: #38BDF8; padding: 6px; background-color: #1E293B; border-radius: 6px;")
        layout.addWidget(header)

        # Tabla de pagos
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Pago #", "Fecha y Hora Real", "Tipo Abono", "Monto Pagado",
            "Abono Capital", "Abono Interés", "Método", "Notas", "Acciones"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        # Botón cerrar
        btn_box = QHBoxLayout()
        btn_close = QPushButton("Cerrar")
        btn_close.setStyleSheet("background-color: #64748B; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        btn_close.clicked.connect(self.accept)
        btn_box.addStretch()
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

    def load_history(self):
        payments = self.payment_service.list_payments(self.loan_data["loan_id"])
        self.table.setRowCount(len(payments))

        for row, p in enumerate(payments):
            self.table.setItem(row, 0, QTableWidgetItem(f"#{p['id']}"))

            time_str = p.get("full_timestamp") or f"{p['payment_date']} {p.get('payment_time', '')}"
            self.table.setItem(row, 1, QTableWidgetItem(time_str))

            p_type = p.get("payment_type", "cuota").upper()
            item_type = QTableWidgetItem(p_type)
            if p_type == "CAPITAL":
                item_type.setForeground(QColor("#10B981"))
            elif p_type == "INTERES":
                item_type.setForeground(QColor("#3B82F6"))
            self.table.setItem(row, 2, item_type)

            monto = Decimal(p["amount"])
            self.table.setItem(row, 3, QTableWidgetItem(f"${monto:,.2f}"))

            cap = Decimal(p.get("capital_allocated", "0.00"))
            self.table.setItem(row, 4, QTableWidgetItem(f"${cap:,.2f}"))

            interes = Decimal(p.get("interest_allocated", "0.00"))
            self.table.setItem(row, 5, QTableWidgetItem(f"${interes:,.2f}"))

            self.table.setItem(row, 6, QTableWidgetItem(p["payment_method"].capitalize()))
            self.table.setItem(row, 7, QTableWidgetItem(p.get("notes") or "-"))

            # Acciones (Editar y Eliminar)
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 2, 4, 2)
            action_layout.setSpacing(6)

            btn_edit = QPushButton("✏️ Editar")
            btn_edit.setStyleSheet("background-color: #3B82F6; color: white; font-size: 11px; padding: 4px 8px; border-radius: 4px;")
            btn_edit.clicked.connect(lambda _, pid=p["id"], curr=p: self._edit_payment(pid, curr))
            action_layout.addWidget(btn_edit)

            btn_del = QPushButton("🗑️ Eliminar")
            btn_del.setStyleSheet("background-color: #EF4444; color: white; font-size: 11px; padding: 4px 8px; border-radius: 4px;")
            btn_del.clicked.connect(lambda _, pid=p["id"]: self._delete_payment(pid))
            action_layout.addWidget(btn_del)

            self.table.setCellWidget(row, 8, action_widget)

    def _edit_payment(self, payment_id: int, current_payment: dict):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Editar Pago #{payment_id}")
        dialog.resize(380, 300)
        form = QFormLayout(dialog)

        sp_amount = QDoubleSpinBox()
        sp_amount.setRange(100.0, 1000000000.0)
        sp_amount.setPrefix("$ ")
        sp_amount.setValue(float(current_payment["amount"]))
        form.addRow("Monto Pagado:", sp_amount)

        cb_type = QComboBox()
        cb_type.addItems(["cuota", "capital", "interes"])
        cb_type.setCurrentText(current_payment.get("payment_type", "cuota"))
        form.addRow("Tipo de Abono:", cb_type)

        cb_method = QComboBox()
        cb_method.addItems(["efectivo", "transferencia", "tarjeta", "cheque"])
        cb_method.setCurrentText(current_payment.get("payment_method", "efectivo"))
        form.addRow("Método de Pago:", cb_method)

        txt_notes = QLineEdit(current_payment.get("notes") or "")
        form.addRow("Observaciones:", txt_notes)

        btn_save = QPushButton("Guardar Cambios")
        btn_save.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 8px;")
        
        def save():
            try:
                self.payment_service.edit_payment(
                    payment_id=payment_id,
                    new_amount=Decimal(str(sp_amount.value())),
                    new_payment_type=cb_type.currentText(),
                    new_payment_method=cb_method.currentText(),
                    new_notes=txt_notes.text().strip(),
                    actor_username=self.current_user["username"]
                )
                QMessageBox.information(dialog, "Éxito", "Pago actualizado y saldos recalculados correctamente.")
                dialog.accept()
                self.load_history()
            except Exception as e:
                QMessageBox.critical(dialog, "Error", str(e))

        btn_save.clicked.connect(save)
        form.addRow(btn_save)
        dialog.exec()

    def _delete_payment(self, payment_id: int):
        reply = QMessageBox.question(
            self,
            "Confirmar Eliminación",
            f"¿Está seguro de eliminar el pago #{payment_id}?\n\n"
            "El saldo y las cuotas del crédito se recalcularán automáticamente.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                self.payment_service.delete_payment(payment_id, actor_username=self.current_user["username"])
                QMessageBox.information(self, "Eliminado", "Pago eliminado y saldos restaurados con éxito.")
                self.load_history()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))


class PaymentsView(QWidget):
    """
    Vista Didáctica y Minimalista de Pagos y Cobranzas (Diseño FOTO 2 de la Pizarra).
    - Búsqueda unificada por Documento, Nombre o Número de Crédito / Pagaré.
    - Muestra todos los préstamos asociados al cliente.
    - Columnas exactas de la pizarra:
      Documento | Nombre | Monto | Fecha | # Cuota / Plazo | Capital | Interés | Saldo | Estado | Acciones
    - Abonos flexibles: a Capital, a Intereses o Cuota Normal.
    - Aviso claro cuando la deuda está totalmente saldada.
    """
    def __init__(self, payment_service: PaymentService, loan_calculator: LoanCalculator, current_user: dict, parent=None):
        super(PaymentsView, self).__init__(parent)
        self.payment_service = payment_service
        self.calculator = loan_calculator
        self.pdf_gen = PdfReportGenerator(self.calculator.db)
        self.current_user = current_user

        self._build_ui()
        self.search_loans()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        # 1. Header con Búsqueda Didáctica y Multicriterio
        search_card = QFrame()
        search_card.setStyleSheet("""
            background-color: #1E293B;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 12px;
        """)
        s_layout = QVBoxLayout(search_card)
        s_layout.setSpacing(8)

        lbl_header = QLabel("🔍 <b>Búsqueda Rápida de Clientes y Créditos</b>")
        lbl_header.setStyleSheet("font-size: 15px; color: #F8FAFC;")
        s_layout.addWidget(lbl_header)

        # Input de búsqueda
        search_row = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Escriba Cédula, Nombre del Cliente, Nº de Crédito o Pagaré (ej: Carlos, 100200300, PAG-0001)...")
        self.txt_search.setStyleSheet("""
            background-color: #0F172A;
            color: #F8FAFC;
            border: 1.5px solid #3B82F6;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 13px;
        """)
        self.txt_search.textChanged.connect(self.search_loans)
        search_row.addWidget(self.txt_search)

        btn_search = QPushButton("Buscar")
        btn_search.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 8px 16px; border-radius: 6px;")
        btn_search.clicked.connect(self.search_loans)
        search_row.addWidget(btn_search)

        btn_clear = QPushButton("Ver Todos")
        btn_clear.setStyleSheet("background-color: #475569; color: white; padding: 8px 14px; border-radius: 6px;")
        btn_clear.clicked.connect(self._clear_search)
        search_row.addWidget(btn_clear)

        s_layout.addLayout(search_row)
        main_layout.addWidget(search_card)

        # 2. Resumen didáctico
        self.lbl_summary = QLabel("Mostrando créditos disponibles.")
        self.lbl_summary.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 500;")
        main_layout.addWidget(self.lbl_summary)

        # 3. Tabla Principal con los campos EXACTOS de la pizarra (FOTO 2)
        # Campos: Documento | Nombre | Monto | Fecha | # Cuota Plazo | Capital | Interés | Saldo | Acciones
        self.table_loans = QTableWidget()
        self.table_loans.setColumnCount(11)
        self.table_loans.setHorizontalHeaderLabels([
            "Pagaré / Crédito", "Documento", "Nombre", "Monto",
            "Fecha", "# Cuota / Plazo", "Capital", "Interés", "Saldo", "Estado", "Acciones"
        ])
        self.table_loans.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_loans.horizontalHeader().setSectionResizeMode(10, QHeaderView.ResizeToContents)
        self.table_loans.setAlternatingRowColors(True)
        main_layout.addWidget(self.table_loans)

    def _clear_search(self):
        self.txt_search.clear()
        self.search_loans()

    def search_loans(self):
        query = self.txt_search.text().strip()
        results = self.payment_service.search_loans_and_clients(query)

        self.table_loans.setRowCount(len(results))
        total_saldo_acumulado = Decimal("0.00")

        for row, item in enumerate(results):
            # 0. Pagaré / Crédito
            self.table_loans.setItem(row, 0, QTableWidgetItem(item["pagare_number"]))

            # 1. Documento
            self.table_loans.setItem(row, 1, QTableWidgetItem(item["documento"]))

            # 2. Nombre
            self.table_loans.setItem(row, 2, QTableWidgetItem(item["nombre"]))

            # 3. Monto
            self.table_loans.setItem(row, 3, QTableWidgetItem(f"${item['monto']:,.2f}"))

            # 4. Fecha
            self.table_loans.setItem(row, 4, QTableWidgetItem(item["fecha"]))

            # 5. # Cuota / Plazo
            self.table_loans.setItem(row, 5, QTableWidgetItem(item["cuota_plazo"]))

            # 6. Capital
            self.table_loans.setItem(row, 6, QTableWidgetItem(f"${item['capital']:,.2f}"))

            # 7. Interés
            self.table_loans.setItem(row, 7, QTableWidgetItem(f"${item['interes']:,.2f}"))

            # 8. Saldo
            saldo = item["saldo"]
            total_saldo_acumulado += saldo
            item_saldo = QTableWidgetItem(f"${saldo:,.2f}")
            item_saldo.setFont(QFont("Arial", 9, QFont.Bold))
            if saldo <= Decimal("0.00"):
                item_saldo.setForeground(QColor("#10B981"))
            else:
                item_saldo.setForeground(QColor("#F59E0B"))
            self.table_loans.setItem(row, 8, item_saldo)

            # 9. Estado
            status_text = item["status"].upper()
            if status_text == "CANCELADO":
                status_text = "SALDADO"
            item_status = QTableWidgetItem(status_text)
            if status_text == "SALDADO":
                item_status.setForeground(QColor("#10B981"))
            elif status_text == "EN_MORA":
                item_status.setForeground(QColor("#EF4444"))
            else:
                item_status.setForeground(QColor("#3B82F6"))
            self.table_loans.setItem(row, 9, item_status)

            # 10. Acciones (Abonar, Ver Cuotas, Reporte)
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 2, 4, 2)
            action_layout.setSpacing(6)

            # Botón Abonar / Pagar
            btn_pay = QPushButton("💳 Abonar")
            if item["status"] == "cancelado" or saldo <= Decimal("0.00"):
                btn_pay.setStyleSheet("background-color: #64748B; color: #E2E8F0; font-size: 11px; padding: 4px 8px; border-radius: 4px;")
                btn_pay.setToolTip("Este crédito ya está saldado.")
            else:
                btn_pay.setStyleSheet("background-color: #059669; color: white; font-weight: bold; font-size: 11px; padding: 4px 8px; border-radius: 4px;")
            btn_pay.clicked.connect(lambda _, it=item: self._open_payment_modal(it))
            action_layout.addWidget(btn_pay)

            # Botón Ver Cuotas (Historial con Editar y Eliminar)
            btn_history = QPushButton("📋 Cuotas")
            btn_history.setStyleSheet("background-color: #2563EB; color: white; font-size: 11px; padding: 4px 8px; border-radius: 4px;")
            btn_history.clicked.connect(lambda _, it=item: self._open_installments_history(it))
            action_layout.addWidget(btn_history)

            # Botón Reporte PDF
            btn_report = QPushButton("📄 PDF")
            btn_report.setStyleSheet("background-color: #475569; color: white; font-size: 11px; padding: 4px 8px; border-radius: 4px;")
            btn_report.clicked.connect(lambda _, it=item: self._generate_loan_pdf(it))
            action_layout.addWidget(btn_report)

            self.table_loans.setCellWidget(row, 10, action_widget)

        count = len(results)
        self.lbl_summary.setText(
            f"Se encontraron <b>{count}</b> crédito(s). Saldo total pendiente de cobro: "
            f"<b style='color: #F59E0B;'>${total_saldo_acumulado:,.2f}</b>"
        )

    def _open_payment_modal(self, loan_item: dict):
        dialog = PaymentModalDialog(loan_item, self.payment_service, self.current_user, self)
        if dialog.exec() == QDialog.Accepted:
            self.search_loans()

    def _open_installments_history(self, loan_item: dict):
        dialog = InstallmentsHistoryDialog(loan_item, self.payment_service, self.current_user, self)
        dialog.exec()
        self.search_loans()

    def _generate_loan_pdf(self, loan_item: dict):
        try:
            pdf_path = self.pdf_gen.generate_amortization_schedule_pdf(loan_item["loan_id"])
            QMessageBox.information(
                self,
                "Reporte Generado",
                f"Estado de cuenta generado con éxito en:\n{pdf_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error al Generar PDF", str(e))
