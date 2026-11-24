from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QFileDialog,
    QProgressBar, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal

from backend.business.pdf_generator import PdfReportGenerator
from backend.database.db_manager import DatabaseManager

class ReportWorkerThread(QThread):
    """
    Hilo de trabajo secundario (QThread) para la generación de reportes pesados
    evitando congelar la interfaz de usuario (SO-02, PR-21).
    """
    finished_success = Signal(str)
    finished_error = Signal(str)

    def __init__(self, pdf_gen: PdfReportGenerator, report_type: str, out_path: Path, username: str, parent=None):
        super(ReportWorkerThread, self).__init__(parent)
        self.pdf_gen = pdf_gen
        self.report_type = report_type
        self.out_path = out_path
        self.username = username

    def run(self):
        try:
            self.pdf_gen.generate_managerial_report_pdf(
                report_type=self.report_type,
                output_path=self.out_path,
                actor_username=self.username
            )
            self.finished_success.emit(str(self.out_path))
        except Exception as e:
            self.finished_error.emit(str(e))


class ReportsView(QWidget):
    """
    Vista de Generación de Reportes Gerenciales en PDF y CSV (PR-21 a PR-24).
    """
    def __init__(self, db_manager: DatabaseManager, current_user: dict, parent=None):
        super(ReportsView, self).__init__(parent)
        self.db = db_manager
        self.pdf_gen = PdfReportGenerator(self.db)
        self.current_user = current_user
        self.worker_thread = None

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        title = QLabel("Reportes Gerenciales y Exportación")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #0F2942;")
        layout.addWidget(title)

        box = QGroupBox("Seleccione el Tipo de Reporte a Generar")
        box_layout = QVBoxLayout(box)

        self.cb_report_type = QComboBox()
        self.cb_report_type.addItem("Cartera Vigente (Préstamos activos y consolidados)", "cartera_vigente")
        self.cb_report_type.addItem("Cartera en Mora (Cuotas vencidas y días de retraso)", "cartera_mora")
        self.cb_report_type.addItem("Historial de Recaudo (Detalle de pagos recibidos)", "recaudo")
        box_layout.addWidget(self.cb_report_type)

        layout.addWidget(box)

        # Barra de progreso para hilo de trabajo
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0) # Indeterminado
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Listo para generar reportes.")
        layout.addWidget(self.lbl_status)

        btn_layout = QHBoxLayout()

        self.btn_pdf = QPushButton("📄 Generar Reporte PDF (en segundo plano)")
        self.btn_pdf.setStyleSheet("background-color: #1D4ED8; color: white; font-weight: bold; padding: 10px 18px; border-radius: 6px;")
        self.btn_pdf.clicked.connect(self._start_pdf_generation)
        btn_layout.addWidget(self.btn_pdf)

        self.btn_csv = QPushButton("📊 Exportar Datos a CSV")
        self.btn_csv.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 10px 18px; border-radius: 6px;")
        self.btn_csv.clicked.connect(self._export_csv)
        btn_layout.addWidget(self.btn_csv)

        layout.addLayout(btn_layout)
        layout.addStretch()

    def _start_pdf_generation(self):
        report_key = self.cb_report_type.currentData()
        default_name = f"Reporte_{report_key}.pdf"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Guardar Reporte Gerencial", default_name, "Archivos PDF (*.pdf)"
        )
        if not file_path:
            return

        self.progress_bar.setVisible(True)
        self.btn_pdf.setEnabled(False)
        self.btn_csv.setEnabled(False)
        self.lbl_status.setText("Generando reporte en hilo secundario QThread...")

        self.worker_thread = ReportWorkerThread(
            pdf_gen=self.pdf_gen,
            report_type=report_key,
            out_path=Path(file_path),
            username=self.current_user["username"]
        )
        self.worker_thread.finished_success.connect(self._on_pdf_success)
        self.worker_thread.finished_error.connect(self._on_pdf_error)
        self.worker_thread.start()

    def _on_pdf_success(self, path_str: str):
        self.progress_bar.setVisible(False)
        self.btn_pdf.setEnabled(True)
        self.btn_csv.setEnabled(True)
        self.lbl_status.setText(f"Reporte generado exitosamente.")
        QMessageBox.information(self, "Reporte Finalizado", f"Documento PDF guardado en:\n{path_str}")

    def _on_pdf_error(self, err_msg: str):
        self.progress_bar.setVisible(False)
        self.btn_pdf.setEnabled(True)
        self.btn_csv.setEnabled(True)
        self.lbl_status.setText(f"Error generando reporte.")
        QMessageBox.critical(self, "Error en Generación", f"Fallo al crear reporte: {err_msg}")

    def _export_csv(self):
        report_key = self.cb_report_type.currentData()
        default_name = f"Export_{report_key}.csv"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Datos a CSV", default_name, "Archivos CSV (*.csv)"
        )
        if not file_path:
            return

        try:
            with self.db.connection(exclusive_lock=False) as conn:
                cursor = conn.cursor()
                if report_key == "cartera_vigente":
                    cursor.execute(
                        """
                        SELECT l.id as prestamo_id, c.doc_number, (c.first_name || ' ' || c.last_name) as cliente,
                               l.principal, l.total_amount, l.periodicity, l.status
                        FROM loans l JOIN clients c ON l.client_id = c.id;
                        """
                    )
                    headers = ["prestamo_id", "doc_number", "cliente", "principal", "total_amount", "periodicity", "status"]
                elif report_key == "cartera_mora":
                    cursor.execute(
                        """
                        SELECT l.id as prestamo_id, (c.first_name || ' ' || c.last_name) as cliente, c.phone,
                               i.number as cuota_num, i.due_date,
                               (CAST(i.capital_expected AS REAL) - CAST(i.capital_paid AS REAL)) as capital_mora
                        FROM installments i JOIN loans l ON i.loan_id = l.id JOIN clients c ON l.client_id = c.id
                        WHERE i.status != 'pagada';
                        """
                    )
                    headers = ["prestamo_id", "cliente", "telefono", "cuota_num", "vencimiento", "capital_mora"]
                else:
                    cursor.execute("SELECT * FROM payments;")
                    headers = [d[0] for d in cursor.description]

                rows = [list(r) for r in cursor.fetchall()]

            self.pdf_gen.export_to_csv(headers, rows, Path(file_path))
            QMessageBox.information(self, "CSV Exportado", f"Archivo CSV generado en:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error CSV", str(e))


