from decimal import Decimal
from datetime import datetime, date
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QComboBox, QDateEdit,
    QFrame
)
from PySide6.QtCore import Qt, QDate
from backend.business.client_service import ClientService

class ClientFormDialog(QDialog):
    """
    Formulario emergente con validación previa interactiva.
    Mantiene los datos intactos si hay algún error de validación y garantiza
    visibilidad absoluta del texto ingresado.
    """
    def __init__(self, client_service: ClientService, client_data=None, parent=None):
        super(ClientFormDialog, self).__init__(parent)
        self.client_service = client_service
        self.client_data = client_data or {}
        self.clean_data = None

        self.setWindowTitle("Editar Cliente" if client_data else "Registrar Nuevo Cliente")
        self.setFixedSize(480, 560)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Banner de Error (oculto por defecto)
        self.lbl_error = QLabel()
        self.lbl_error.setStyleSheet("""
            background-color: #FEE2E2;
            color: #991B1B;
            border: 1px solid #F87171;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 12px;
            font-weight: bold;
        """)
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setVisible(False)
        layout.addWidget(self.lbl_error)

        form = QFormLayout()
        form.setSpacing(10)

        self.cb_doc_type = QComboBox()
        self.cb_doc_type.addItems(["CC - Cédula de Ciudadanía", "CE - Cédula de Extranjería", "TI - Tarjeta de Identidad", "NIT", "PASAPORTE"])
        if "doc_type" in self.client_data:
            for i in range(self.cb_doc_type.count()):
                if self.client_data["doc_type"] in self.cb_doc_type.itemText(i):
                    self.cb_doc_type.setCurrentIndex(i)
                    break
        form.addRow("Tipo de Documento:", self.cb_doc_type)

        self.txt_doc_number = QLineEdit(self.client_data.get("doc_number", ""))
        self.txt_doc_number.setPlaceholderText("Ej: 1002345678 (sin puntos)")
        form.addRow("N° de Documento:", self.txt_doc_number)

        self.txt_first_name = QLineEdit(self.client_data.get("first_name", ""))
        self.txt_first_name.setPlaceholderText("Ej: Juan")
        form.addRow("Nombres:", self.txt_first_name)

        self.txt_last_name = QLineEdit(self.client_data.get("last_name", ""))
        self.txt_last_name.setPlaceholderText("Ej: Pérez Gómez")
        form.addRow("Apellidos:", self.txt_last_name)

        # Fecha de Nacimiento con selector de calendario (garantiza edad >= 18)
        self.dt_birth = QDateEdit()
        self.dt_birth.setCalendarPopup(True)
        self.dt_birth.setDisplayFormat("yyyy-MM-dd")
        if "birth_date" in self.client_data:
            try:
                b = datetime.strptime(self.client_data["birth_date"], "%Y-%m-%d").date()
                self.dt_birth.setDate(QDate(b.year, b.month, b.day))
            except Exception:
                self.dt_birth.setDate(QDate(1995, 1, 1))
        else:
            self.dt_birth.setDate(QDate(1995, 1, 1))
        form.addRow("Fecha de Nacimiento:", self.dt_birth)

        self.txt_phone = QLineEdit(self.client_data.get("phone", ""))
        self.txt_phone.setPlaceholderText("Ej: 3001234567 (10 dígitos)")
        form.addRow("Teléfono Móvil:", self.txt_phone)

        self.txt_email = QLineEdit(self.client_data.get("email", ""))
        self.txt_email.setPlaceholderText("Ej: juan.perez@correo.com")
        form.addRow("Correo Electrónico:", self.txt_email)

        self.txt_address = QLineEdit(self.client_data.get("address", ""))
        self.txt_address.setPlaceholderText("Ej: Calle 45 # 12-34")
        form.addRow("Dirección de Residencia:", self.txt_address)

        self.txt_occupation = QLineEdit(self.client_data.get("occupation", "Empleado"))
        self.txt_occupation.setPlaceholderText("Ej: Empleado, Comerciante, Independiente, Docente...")
        self.txt_occupation.setToolTip("Actividad laboral a la que se dedica el cliente en la vida real. Sirve para evaluar su perfil de ingresos y capacidad crediticia.")
        form.addRow("Ocupación del Cliente:", self.txt_occupation)

        self.txt_income = QLineEdit(str(self.client_data.get("monthly_income", "2500000")))
        self.txt_income.setPlaceholderText("Ej: 2500000")
        form.addRow("Ingresos Mensuales ($):", self.txt_income)

        layout.addLayout(form)

        # Botones de Acción
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet("background-color: #64748B; color: white; padding: 8px 16px;")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("💾 Guardar Cliente")
        btn_save.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 8px 20px;")
        btn_save.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def _validate_and_accept(self):
        """Valida ANTES de cerrar la ventana; si falla, no cierra el diálogo ni pierde datos."""
        # Extraer tipo de documento limpio (primeros 2 a 10 caracteres antes del guión)
        raw_type = self.cb_doc_type.currentText().split("-")[0].strip()

        raw_data = {
            "doc_type": raw_type,
            "doc_number": self.txt_doc_number.text(),
            "first_name": self.txt_first_name.text(),
            "last_name": self.txt_last_name.text(),
            "birth_date": self.dt_birth.date().toString("yyyy-MM-dd"),
            "phone": self.txt_phone.text(),
            "email": self.txt_email.text(),
            "address": self.txt_address.text(),
            "occupation": self.txt_occupation.text(),
            "monthly_income": self.txt_income.text(),
        }

        try:
            self.clean_data = self.client_service.validate_and_sanitize_client_data(raw_data)
            self.lbl_error.setVisible(False)
            self.accept()
        except Exception as e:
            self.lbl_error.setText(f"⚠️ {str(e)}")
            self.lbl_error.setVisible(True)


class ClientsView(QWidget):
    """
    Vista de Gestión de Clientes (PR-03 a PR-06).
    """
    def __init__(self, client_service: ClientService, current_user: dict, parent=None):
        super(ClientsView, self).__init__(parent)
        self.client_service = client_service
        self.current_user = current_user
        self.current_page = 1
        self.page_size = 10
        self.total_records = 0

        self._build_ui()
        self.load_clients()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Encabezado y barra de búsqueda
        top_bar = QHBoxLayout()
        title = QLabel("Gestión de Clientes")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1E3A8A;")
        top_bar.addWidget(title)

        top_bar.addStretch()

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Buscar por nombre o documento...")
        self.txt_search.setFixedWidth(280)
        self.txt_search.textChanged.connect(self._on_search_changed)
        top_bar.addWidget(self.txt_search)

        btn_new = QPushButton("➕ Nuevo Cliente")
        btn_new.setStyleSheet("background-color: #10B981; color: white; font-weight: bold; padding: 8px 16px; border-radius: 6px;")
        btn_new.clicked.connect(self._create_client)
        top_bar.addWidget(btn_new)

        layout.addLayout(top_bar)

        # Tabla de clientes
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Documento", "Nombre Completo", "Teléfono", "Correo", "Ingresos", "Ocupación", "Acciones"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        # Paginación
        pag_bar = QHBoxLayout()
        self.lbl_pag_info = QLabel("Mostrando 0 de 0 clientes")
        pag_bar.addWidget(self.lbl_pag_info)

        pag_bar.addStretch()

        self.btn_prev = QPushButton("◀ Anterior")
        self.btn_prev.clicked.connect(self._prev_page)
        pag_bar.addWidget(self.btn_prev)

        self.lbl_page = QLabel("Página 1")
        pag_bar.addWidget(self.lbl_page)

        self.btn_next = QPushButton("Siguiente ▶")
        self.btn_next.clicked.connect(self._next_page)
        pag_bar.addWidget(self.btn_next)

        layout.addLayout(pag_bar)

    def load_clients(self):
        query = self.txt_search.text().strip()
        try:
            records, total = self.client_service.list_clients(
                page=self.current_page,
                page_size=self.page_size,
                search_query=query
            )
            self.total_records = total
            self.table.setRowCount(len(records))

            for row_idx, c in enumerate(records):
                self.table.setItem(row_idx, 0, QTableWidgetItem(str(c["id"])))
                self.table.setItem(row_idx, 1, QTableWidgetItem(f"{c['doc_type']} {c['doc_number']}"))
                self.table.setItem(row_idx, 2, QTableWidgetItem(f"{c['first_name']} {c['last_name']}"))
                self.table.setItem(row_idx, 3, QTableWidgetItem(c["phone"]))
                self.table.setItem(row_idx, 4, QTableWidgetItem(c["email"]))
                self.table.setItem(row_idx, 5, QTableWidgetItem(f"${Decimal(c['monthly_income']):,.2f}"))
                self.table.setItem(row_idx, 6, QTableWidgetItem(c["occupation"]))

                # Botones de acción
                action_widget = QWidget()
                act_layout = QHBoxLayout(action_widget)
                act_layout.setContentsMargins(2, 2, 2, 2)
                act_layout.setSpacing(4)

                btn_edit = QPushButton("Editar")
                btn_edit.setStyleSheet("background-color: #3B82F6; color: white; padding: 3px 8px; font-size: 11px;")
                btn_edit.clicked.connect(lambda _, client_data=c: self._edit_client(client_data))
                act_layout.addWidget(btn_edit)

                btn_del = QPushButton("Desactivar")
                btn_del.setStyleSheet("background-color: #EF4444; color: white; padding: 3px 8px; font-size: 11px;")
                btn_del.clicked.connect(lambda _, cid=c["id"], name=c["first_name"]: self._delete_client(cid, name))
                act_layout.addWidget(btn_del)

                self.table.setCellWidget(row_idx, 7, action_widget)

            # Actualizar barra de paginación
            start = (self.current_page - 1) * self.page_size + 1 if total > 0 else 0
            end = min(self.current_page * self.page_size, total)
            self.lbl_pag_info.setText(f"Mostrando {start} a {end} de {total} clientes")
            self.lbl_page.setText(f"Página {self.current_page}")

            self.btn_prev.setEnabled(self.current_page > 1)
            self.btn_next.setEnabled(end < total)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error cargando clientes: {e}")

    def _on_search_changed(self):
        self.current_page = 1
        self.load_clients()

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_clients()

    def _next_page(self):
        self.current_page += 1
        self.load_clients()

    def _create_client(self):
        dlg = ClientFormDialog(client_service=self.client_service, parent=self)
        if dlg.exec():
            try:
                cid = self.client_service.create_client(dlg.clean_data, self.current_user["username"])
                QMessageBox.information(self, "¡Cliente Registrado!", f"Cliente ID #{cid} ({dlg.clean_data['first_name']} {dlg.clean_data['last_name']}) registrado exitosamente.")
                self.current_page = 1
                self.load_clients()
            except Exception as e:
                QMessageBox.warning(self, "Error al Guardar", str(e))

    def _edit_client(self, client_data: dict):
        dlg = ClientFormDialog(client_service=self.client_service, client_data=client_data, parent=self)
        if dlg.exec():
            try:
                self.client_service.update_client(client_data["id"], dlg.clean_data, self.current_user["username"])
                QMessageBox.information(self, "Cliente Actualizado", "Datos del cliente actualizados exitosamente.")
                self.load_clients()
            except Exception as e:
                QMessageBox.warning(self, "Error al Actualizar", str(e))

    def _delete_client(self, client_id: int, client_name: str):
        reply = QMessageBox.question(
            self,
            "Confirmar Desactivación",
            f"¿Está seguro de desactivar lógicamente al cliente {client_name}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                self.client_service.delete_client(client_id, self.current_user["username"])
                QMessageBox.information(self, "Desactivado", "Cliente desactivado exitosamente.")
                self.load_clients()
            except Exception as e:
                QMessageBox.warning(self, "Operación no permitida", str(e))

