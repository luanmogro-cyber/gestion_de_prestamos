from decimal import Decimal
from datetime import datetime, date
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit,
    QTabWidget, QGroupBox, QFormLayout, QCalendarWidget, QSplitter,
    QFileDialog
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QTextCharFormat, QColor, QBrush

from backend.business.loan_calculator import LoanCalculator
from backend.business.client_service import ClientService
from backend.business.pdf_generator import PdfReportGenerator
from pathlib import Path

class LoansView(QWidget):
    """
    Vista Integral de Préstamos y Simulador (PR-07 a PR-16).
    Incluye:
    1. Simulador y Desembolso de Préstamos (Francés y Alemán con Decimal).
    2. Visualizador de Tabla de Amortización.
    3. Calendario Visual con colores por estado (QCalendarWidget).
    """
    def __init__(self, loan_calculator: LoanCalculator, client_service: ClientService, current_user: dict, parent=None):
        super(LoansView, self).__init__(parent)
        self.calculator = loan_calculator
        self.client_service = client_service
        self.pdf_gen = PdfReportGenerator(self.calculator.db)
        self.current_user = current_user
        self.current_simulation = None

        self._build_ui()
        self.refresh_clients_combo()
        self.load_loans_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Simulador y Nuevo Préstamo
        tab_sim = QWidget()
        self._build_simulator_tab(tab_sim)
        self.tabs.addTab(tab_sim, "Simulador & Nuevo Préstamo")

        # Tab 2: Préstamos Activos y Amortización
        tab_loans = QWidget()
        self._build_loans_tab(tab_loans)
        self.tabs.addTab(tab_loans, "Préstamos Activos & Cronogramas")

        # Tab 3: Calendario de Vencimientos (PR-15, PR-16)
        tab_cal = QWidget()
        self._build_calendar_tab(tab_cal)
        self.tabs.addTab(tab_cal, "Calendario de Cobranzas")

    def _build_simulator_tab(self, tab):
        main_layout = QHBoxLayout(tab)

        # Panel izquierdo: Parámetros del préstamo
        left_group = QGroupBox("Parámetros del Crédito")
        left_group.setFixedWidth(360)
        form = QFormLayout(left_group)

        self.cb_clients = QComboBox()
        form.addRow("Cliente:", self.cb_clients)

        self.sp_principal = QDoubleSpinBox()
        self.sp_principal.setRange(100000.0, 1000000000.0)
        self.sp_principal.setValue(10000000.0)  # Caso de aceptación inicial: 10 millones
        self.sp_principal.setPrefix("$ ")
        self.sp_principal.setDecimals(2)
        form.addRow("Monto Principal:", self.sp_principal)

        self.sp_rate = QDoubleSpinBox()
        self.sp_rate.setRange(0.0, 100.0)
        self.sp_rate.setValue(18.0)  # 18% anual
        self.sp_rate.setSuffix(" % Anual")
        self.sp_rate.setDecimals(2)
        form.addRow("Tasa de Interés:", self.sp_rate)

        self.sp_installments = QSpinBox()
        self.sp_installments.setRange(1, 120)
        self.sp_installments.setValue(12)  # 12 cuotas
        form.addRow("N° de Cuotas:", self.sp_installments)

        self.cb_periodicity = QComboBox()
        self.cb_periodicity.addItems(["mensual", "quincenal", "semanal"])
        form.addRow("Periodicidad:", self.cb_periodicity)

        self.cb_method = QComboBox()
        self.cb_method.addItem("Sistema Francés (Cuota Fija)", "frances")
        self.cb_method.addItem("Sistema Alemán (Abono Constante Capital)", "aleman")
        form.addRow("Método Amortización:", self.cb_method)

        self.cb_commission_type = QComboBox()
        self.cb_commission_type.addItem("Ninguna", "ninguna")
        self.cb_commission_type.addItem("Porcentaje (%)", "porcentaje")
        self.cb_commission_type.addItem("Valor Fijo ($)", "fijo")
        form.addRow("Tipo de Comisión/Seguro:", self.cb_commission_type)

        self.sp_commission_val = QDoubleSpinBox()
        self.sp_commission_val.setRange(0.0, 1000000.0)
        self.sp_commission_val.setValue(0.0)
        form.addRow("Valor Comisión/Seguro:", self.sp_commission_val)

        self.dt_disbursement = QDateEdit()
        self.dt_disbursement.setDate(QDate.currentDate())
        self.dt_disbursement.setCalendarPopup(True)
        form.addRow("Fecha Desembolso:", self.dt_disbursement)

        # Botones
        btn_simulate = QPushButton("1. Simular Préstamo")
        btn_simulate.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 8px;")
        btn_simulate.clicked.connect(self._do_simulation)
        form.addRow(btn_simulate)

        btn_create = QPushButton("2. Crear y Desembolsar Préstamo")
        btn_create.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 8px;")
        btn_create.clicked.connect(self._do_create_loan)
        form.addRow(btn_create)

        main_layout.addWidget(left_group)

        # Panel derecho: Resumen y tabla del simulador
        right_panel = QVBoxLayout()

        self.lbl_sim_summary = QLabel("Ingrese los parámetros y haga clic en 'Simular Préstamo' para ver la proyección.")
        self.lbl_sim_summary.setStyleSheet("""
            background-color: #EFF6FF;
            color: #1E3A8A !important;
            border: 1.5px solid #93C5FD;
            border-radius: 6px;
            padding: 10px 14px;
            font-size: 12px;
            font-weight: bold;
        """)
        self.lbl_sim_summary.setWordWrap(True)
        right_panel.addWidget(self.lbl_sim_summary)

        self.table_sim = QTableWidget()
        self.table_sim.setColumnCount(6)
        self.table_sim.setHorizontalHeaderLabels(["N° Cuota", "Vencimiento", "Capital", "Interés", "Cuota Total", "Saldo Remanente"])
        self.table_sim.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right_panel.addWidget(self.table_sim)

        main_layout.addLayout(right_panel)

    def _build_loans_tab(self, tab):
        layout = QVBoxLayout(tab)

        splitter = QSplitter(Qt.Vertical)

        # Arriba: Lista de préstamos
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("<b>Préstamos Registrados:</b>"))
        btn_refresh = QPushButton("Actualizar Lista")
        btn_refresh.clicked.connect(self.load_loans_list)
        top_bar.addWidget(btn_refresh)
        top_bar.addStretch()
        top_layout.addLayout(top_bar)

        self.table_loans = QTableWidget()
        self.table_loans.setColumnCount(8)
        self.table_loans.setHorizontalHeaderLabels([
            "ID", "Documento", "Cliente", "Principal", "Tasa Anual", "Cuotas", "Estado", "Acciones"
        ])
        self.table_loans.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_loans.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_loans.itemSelectionChanged.connect(self._on_loan_selected)
        top_layout.addWidget(self.table_loans)

        splitter.addWidget(top_widget)

        # Abajo: Cronograma del préstamo seleccionado
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bot_bar = QHBoxLayout()
        self.lbl_detail_title = QLabel("<b>Detalle de Cuotas del Préstamo Seleccionado</b>")
        bot_bar.addWidget(self.lbl_detail_title)
        bot_bar.addStretch()

        self.btn_export_pdf = QPushButton("Descargar Tabla PDF")
        self.btn_export_pdf.setStyleSheet("background-color: #DC2626; color: white; font-weight: bold; padding: 4px 10px;")
        self.btn_export_pdf.clicked.connect(self._export_selected_loan_pdf)
        self.btn_export_pdf.setEnabled(False)
        bot_bar.addWidget(self.btn_export_pdf)
        bottom_layout.addLayout(bot_bar)

        self.table_installments = QTableWidget()
        self.table_installments.setColumnCount(8)
        self.table_installments.setHorizontalHeaderLabels([
            "N°", "Vencimiento", "Capital", "Interés", "Total Cuota", "Capital Pagado", "Interés Pagado", "Estado"
        ])
        self.table_installments.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        bottom_layout.addWidget(self.table_installments)

        splitter.addWidget(bottom_widget)
        layout.addWidget(splitter)

    def _build_calendar_tab(self, tab):
        layout = QHBoxLayout(tab)

        # Calendario visual
        cal_group = QGroupBox("Calendario de Cobranzas y Vencimientos")
        cal_layout = QVBoxLayout(cal_group)

        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.clicked.connect(self._on_calendar_date_clicked)
        cal_layout.addWidget(self.calendar)

        legend = QLabel(
            "<b>Leyenda de Colores:</b> "
            "<span style='color:#10B981;'>■ Pagada</span> | "
            "<span style='color:#F59E0B;'>■ Pendiente / Próxima</span> | "
            "<span style='color:#EF4444;'>■ Vencida (Mora)</span>"
        )
        legend.setAlignment(Qt.AlignCenter)
        cal_layout.addWidget(legend)
        layout.addWidget(cal_group)

        # Panel lateral con cuotas del día seleccionado
        side_group = QGroupBox("Cuotas con Vencimiento en la Fecha Seleccionada")
        side_layout = QVBoxLayout(side_group)
        self.lbl_cal_date = QLabel("Seleccione un día en el calendario...")
        self.lbl_cal_date.setStyleSheet("font-weight: bold; color: #1E3A8A;")
        side_layout.addWidget(self.lbl_cal_date)

        self.table_cal_details = QTableWidget()
        self.table_cal_details.setColumnCount(5)
        self.table_cal_details.setHorizontalHeaderLabels(["Préstamo", "Cliente", "N° Cuota", "Total Exigible", "Estado"])
        self.table_cal_details.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        side_layout.addWidget(self.table_cal_details)
        layout.addWidget(side_group)

    def refresh_clients_combo(self):
        self.cb_clients.clear()
        clients, _ = self.client_service.list_clients(page=1, page_size=500)
        for c in clients:
            self.cb_clients.addItem(f"{c['first_name']} {c['last_name']} ({c['doc_number']})", c["id"])

    def _do_simulation(self):
        try:
            principal = Decimal(str(self.sp_principal.value()))
            rate = Decimal(str(self.sp_rate.value()))
            count = self.sp_installments.value()
            periodicity = self.cb_periodicity.currentText()
            method = self.cb_method.currentData()
            comm_type = self.cb_commission_type.currentData()
            comm_val = Decimal(str(self.sp_commission_val.value()))
            q_date = self.dt_disbursement.date()
            disb_date = date(q_date.year(), q_date.month(), q_date.day())

            res = self.calculator.simulate_loan(
                principal=principal,
                annual_interest_rate=rate,
                installments_count=count,
                periodicity=periodicity,
                method=method,
                commission_type=comm_type,
                commission_value=comm_val,
                disbursement_date=disb_date
            )
            self.current_simulation = res
            r = res["resumen"]
            sym = "$"

            self.lbl_sim_summary.setText(
                f"<div style='color: #1E3A8A; font-size: 12px; line-height: 1.4;'>"
                f"<b>Resumen de Simulación:</b> Monto: {sym}{r['principal']:,.2f} | "
                f"Intereses Totales: {sym}{r['total_intereses']:,.2f} | "
                f"Comisión: {sym}{r['comision']:,.2f} | "
                f"<span style='color: #1E40AF; font-size: 13px;'><b>Total a Pagar: {sym}{r['total_a_pagar']:,.2f}</b></span>"
                f"</div>"
            )

            schedule = res["cronograma"]
            self.table_sim.setRowCount(len(schedule))
            for idx, item in enumerate(schedule):
                self.table_sim.setItem(idx, 0, QTableWidgetItem(str(item["numero"])))
                self.table_sim.setItem(idx, 1, QTableWidgetItem(item["fecha_vencimiento"]))
                self.table_sim.setItem(idx, 2, QTableWidgetItem(f"{sym} {item['capital']:,.2f}"))
                self.table_sim.setItem(idx, 3, QTableWidgetItem(f"{sym} {item['interes']:,.2f}"))
                self.table_sim.setItem(idx, 4, QTableWidgetItem(f"{sym} {item['cuota_total']:,.2f}"))
                self.table_sim.setItem(idx, 5, QTableWidgetItem(f"{sym} {item['saldo_remanente']:,.2f}"))

        except Exception as e:
            QMessageBox.critical(self, "Error en Simulación", str(e))

    def _do_create_loan(self):
        if self.cb_clients.currentIndex() < 0:
            QMessageBox.warning(self, "Atención", "Debe seleccionar un cliente.")
            return

        client_id = self.cb_clients.currentData()
        principal = Decimal(str(self.sp_principal.value()))
        rate = Decimal(str(self.sp_rate.value()))
        count = self.sp_installments.value()
        periodicity = self.cb_periodicity.currentText()
        method = self.cb_method.currentData()
        comm_type = self.cb_commission_type.currentData()
        comm_val = Decimal(str(self.sp_commission_val.value()))
        disb_date_str = self.dt_disbursement.date().toString("yyyy-MM-dd")

        reply = QMessageBox.question(
            self,
            "Confirmar Desembolso",
            f"¿Desea crear y desembolsar el préstamo por ${principal:,.2f} para este cliente?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                loan_id = self.calculator.create_loan(
                    client_id=client_id,
                    principal=principal,
                    annual_interest_rate=rate,
                    installments_count=count,
                    periodicity=periodicity,
                    method=method,
                    commission_type=comm_type,
                    commission_value=comm_val,
                    disbursement_date=disb_date_str,
                    actor_username=self.current_user["username"]
                )
                QMessageBox.information(self, "Éxito", f"Préstamo #{loan_id} creado y desembolsado exitosamente.")
                self.load_loans_list()
                self.tabs.setCurrentIndex(1)
            except Exception as e:
                QMessageBox.critical(self, "Error al Crear Préstamo", str(e))

    def load_loans_list(self):
        try:
            loans = self.calculator.list_loans()
            self.table_loans.setRowCount(len(loans))
            for idx, l in enumerate(loans):
                self.table_loans.setItem(idx, 0, QTableWidgetItem(str(l["id"])))
                self.table_loans.setItem(idx, 1, QTableWidgetItem(l["doc_number"]))
                self.table_loans.setItem(idx, 2, QTableWidgetItem(f"{l['first_name']} {l['last_name']}"))
                self.table_loans.setItem(idx, 3, QTableWidgetItem(f"${Decimal(l['principal']):,.2f}"))
                self.table_loans.setItem(idx, 4, QTableWidgetItem(f"{Decimal(l['annual_interest_rate']):,.2f}%"))
                self.table_loans.setItem(idx, 5, QTableWidgetItem(str(l["installments_count"])))
                self.table_loans.setItem(idx, 6, QTableWidgetItem(l["status"].upper()))

                btn_view = QPushButton("Ver Plan")
                btn_view.clicked.connect(lambda _, lid=l["id"]: self._load_loan_detail(lid))
                self.table_loans.setCellWidget(idx, 7, btn_view)

            self._update_calendar_highlights()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error cargando préstamos: {e}")

    def _on_loan_selected(self):
        selected_rows = self.table_loans.selectedItems()
        if selected_rows:
            row = selected_rows[0].row()
            loan_id_item = self.table_loans.item(row, 0)
            if loan_id_item:
                self._load_loan_detail(int(loan_id_item.text()))

    def _load_loan_detail(self, loan_id: int):
        loan = self.calculator.get_loan(loan_id)
        if not loan:
            return
        self.selected_loan_id = loan_id
        self.btn_export_pdf.setEnabled(True)
        self.lbl_detail_title.setText(
            f"<b>Plan de Amortización: Préstamo #{loan_id} - Cliente: {loan['first_name']} {loan['last_name']}</b>"
        )

        insts = loan.get("installments", [])
        self.table_installments.setRowCount(len(insts))
        for idx, item in enumerate(insts):
            self.table_installments.setItem(idx, 0, QTableWidgetItem(str(item["number"])))
            self.table_installments.setItem(idx, 1, QTableWidgetItem(item["due_date"]))
            self.table_installments.setItem(idx, 2, QTableWidgetItem(f"${Decimal(item['capital_expected']):,.2f}"))
            self.table_installments.setItem(idx, 3, QTableWidgetItem(f"${Decimal(item['interest_expected']):,.2f}"))
            self.table_installments.setItem(idx, 4, QTableWidgetItem(f"${Decimal(item['total_expected']):,.2f}"))
            self.table_installments.setItem(idx, 5, QTableWidgetItem(f"${Decimal(item['capital_paid']):,.2f}"))
            self.table_installments.setItem(idx, 6, QTableWidgetItem(f"${Decimal(item['interest_paid']):,.2f}"))
            self.table_installments.setItem(idx, 7, QTableWidgetItem(item["status"].upper()))

    def _export_selected_loan_pdf(self):
        if not getattr(self, "selected_loan_id", None):
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar Tabla de Amortización en PDF",
            f"Plan_Amortizacion_Prestamo_{self.selected_loan_id}.pdf",
            "Archivos PDF (*.pdf)"
        )
        if path:
            try:
                self.pdf_gen.generate_amortization_table_pdf(self.selected_loan_id, Path(path), self.current_user["username"])
                QMessageBox.information(self, "PDF Generado", f"Archivo PDF guardado exitosamente en:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error PDF", str(e))

    def _update_calendar_highlights(self):
        """Pinta los días del calendario con colores según el estado de las cuotas."""
        with self.calculator.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT due_date, status FROM installments;")
            rows = cursor.fetchall()

            fmt_paid = QTextCharFormat()
            fmt_paid.setBackground(QBrush(QColor("#D1FAE5"))) # Verde claro
            fmt_paid.setForeground(QBrush(QColor("#065F46")))

            fmt_pending = QTextCharFormat()
            fmt_pending.setBackground(QBrush(QColor("#FEF3C7"))) # Amarillo claro
            fmt_pending.setForeground(QBrush(QColor("#92400E")))

            fmt_overdue = QTextCharFormat()
            fmt_overdue.setBackground(QBrush(QColor("#FEE2E2"))) # Rojo claro
            fmt_overdue.setForeground(QBrush(QColor("#991B1B")))

            today_str = date.today().strftime("%Y-%m-%d")

            for r in rows:
                due_d = datetime.strptime(r["due_date"], "%Y-%m-%d").date()
                q_d = QDate(due_d.year, due_d.month, due_d.day)
                st = r["status"]

                if st == "pagada":
                    self.calendar.setDateTextFormat(q_d, fmt_paid)
                elif st in ("pendiente", "parcial"):
                    if r["due_date"] < today_str:
                        self.calendar.setDateTextFormat(q_d, fmt_overdue)
                    else:
                        self.calendar.setDateTextFormat(q_d, fmt_pending)

    def _on_calendar_date_clicked(self, q_date: QDate):
        date_str = q_date.toString("yyyy-MM-dd")
        self.lbl_cal_date.setText(f"Cuotas con Vencimiento el {date_str}:")

        with self.calculator.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT i.loan_id, i.number, i.total_expected, i.status,
                       (c.first_name || ' ' || c.last_name) as cliente
                FROM installments i
                JOIN loans l ON i.loan_id = l.id
                JOIN clients c ON l.client_id = c.id
                WHERE i.due_date = ?;
                """,
                (date_str,)
            )
            rows = cursor.fetchall()
            self.table_cal_details.setRowCount(len(rows))
            for idx, r in enumerate(rows):
                self.table_cal_details.setItem(idx, 0, QTableWidgetItem(f"#{r['loan_id']}"))
                self.table_cal_details.setItem(idx, 1, QTableWidgetItem(r["cliente"]))
                self.table_cal_details.setItem(idx, 2, QTableWidgetItem(str(r["number"])))
                self.table_cal_details.setItem(idx, 3, QTableWidgetItem(f"${Decimal(r['total_expected']):,.2f}"))
                self.table_cal_details.setItem(idx, 4, QTableWidgetItem(r["status"].upper()))


