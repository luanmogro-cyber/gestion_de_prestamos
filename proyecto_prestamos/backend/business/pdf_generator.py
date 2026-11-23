import os
import csv
import logging
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, List, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from backend.common.config import ConfigManager
from backend.database.db_manager import DatabaseManager

logger = logging.getLogger("prestamos.pdf")


class NumberedCanvas(canvas.Canvas):
    """
    Canvas de dos pasadas para calcular e imprimir dinámicamente:
    'Página X de Y' junto con el pie de página institucional.
    """
    def __init__(self, *args, **kwargs):
        super(NumberedCanvas, self).__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#555555"))

        # Línea divisoria del pie
        self.setStrokeColor(colors.HexColor("#D1D5DB"))
        self.setLineWidth(0.5)
        self.line(40, 40, letter[0] - 40, 40)

        page_str = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(letter[0] - 40, 28, page_str)
        self.drawString(40, 28, "Sistema de Gestión de Préstamos - Entorno Linux Nativo")
        self.restoreState()


class PdfReportGenerator:
    """
    Generador de Reportes PDF y CSV profesionales (PR-21 a PR-24).
    Diseñado para ejecución eficiente en hilos secundarios (QThread).
    """
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.config = ConfigManager()
        self.db = db_manager or DatabaseManager()
        self.styles = getSampleStyleSheet()
        self._custom_styles()

    def _custom_styles(self):
        self.styles.add(ParagraphStyle(
            name="ReportTitle",
            parent=self.styles["Heading1"],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#1E3A8A"),
            alignment=1, # Centro
            spaceAfter=6
        ))
        self.styles.add(ParagraphStyle(
            name="ReportSubtitle",
            parent=self.styles["Normal"],
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#4B5563"),
            alignment=1,
            spaceAfter=12
        ))
        self.styles.add(ParagraphStyle(
            name="SectionHeading",
            parent=self.styles["Heading2"],
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#1F2937"),
            spaceBefore=10,
            spaceAfter=6
        ))
        self.styles.add(ParagraphStyle(
            name="TableHeader",
            parent=self.styles["Normal"],
            fontSize=8,
            leading=10,
            fontName="Helvetica-Bold",
            textColor=colors.white,
            alignment=1
        ))
        self.styles.add(ParagraphStyle(
            name="TableCell",
            parent=self.styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#1F2937")
        ))
        self.styles.add(ParagraphStyle(
            name="TableCellRight",
            parent=self.styles["TableCell"],
            alignment=2 # Derecha
        ))

    def _build_header_flowables(self, report_name: str, actor_username: str) -> List[Any]:
        company = self.config.get("empresa", default={})
        elements = []

        header_text = f"""
        <b>{company.get('nombre', 'Sistema de Préstamos')}</b><br/>
        NIT: {company.get('nit', 'N/A')} | Tel: {company.get('telefono', 'N/A')}<br/>
        {company.get('direccion', '')}
        """
        meta_text = f"""
        <b>Fecha de Emisión:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br/>
        <b>Generado por:</b> {actor_username}<br/>
        <b>Estado:</b> Documento Oficial
        """

        header_data = [
            [Paragraph(header_text, self.styles["Normal"]), Paragraph(meta_text, self.styles["TableCellRight"])]
        ]
        header_table = Table(header_data, colWidths=[3.5 * inch, 3.5 * inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(header_table)
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1E3A8A"), spaceBefore=4, spaceAfter=8))
        elements.append(Paragraph(report_name, self.styles["ReportTitle"]))
        return elements

    def generate_payment_receipt(self, payment_id: int, output_path: Path, actor_username: str) -> Path:
        """Comprobante de pago individual."""
        with self.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT p.*, l.principal, l.method, c.first_name, c.last_name, c.doc_number, c.doc_type
                FROM payments p
                JOIN loans l ON p.loan_id = l.id
                JOIN clients c ON l.client_id = c.id
                WHERE p.id = ?;
                """,
                (payment_id,)
            )
            pay = cursor.fetchone()
            if not pay:
                raise ValueError(f"Pago #{payment_id} no encontrado.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=50
        )
        elements = self._build_header_flowables(f"COMPROBANTE DE PAGO #{payment_id}", actor_username)

        # Detalles del pago
        info_data = [
            ["N° de Préstamo:", f"#{pay['loan_id']}", "Fecha de Pago:", pay["payment_date"]],
            ["Cliente:", f"{pay['first_name']} {pay['last_name']}", "Documento:", f"{pay['doc_type']} {pay['doc_number']}"],
            ["Método de Pago:", pay["payment_method"].upper(), "Registrado por:", pay["created_by"]],
        ]
        info_table = Table(info_data, colWidths=[1.7 * inch, 2.0 * inch, 1.7 * inch, 2.0 * inch])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F3F4F6")),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 15))

        elements.append(Paragraph("Desglose de Aplicación de Fondos (Prelación de Pago)", self.styles["SectionHeading"]))
        sym = self.config.get("financiero", "moneda_simbolo", default="$")

        breakdown_data = [
            [Paragraph("Concepto", self.styles["TableHeader"]), Paragraph("Monto Aplicado", self.styles["TableHeader"])],
            [Paragraph("1° Intereses de Mora", self.styles["TableCell"]), Paragraph(f"{sym} {Decimal(pay['late_fee_allocated']):,.2f}", self.styles["TableCellRight"])],
            [Paragraph("2° Interés Corriente", self.styles["TableCell"]), Paragraph(f"{sym} {Decimal(pay['interest_allocated']):,.2f}", self.styles["TableCellRight"])],
            [Paragraph("3° Abono a Capital", self.styles["TableCell"]), Paragraph(f"{sym} {Decimal(pay['capital_allocated']):,.2f}", self.styles["TableCellRight"])],
            [Paragraph("<b>TOTAL PAGADO</b>", self.styles["TableCell"]), Paragraph(f"<b>{sym} {Decimal(pay['amount']):,.2f}</b>", self.styles["TableCellRight"])]
        ]
        breakdown_table = Table(breakdown_data, colWidths=[4.5 * inch, 2.5 * inch])
        breakdown_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#E5E7EB")),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(breakdown_table)

        if pay["notes"]:
            elements.append(Spacer(1, 10))
            elements.append(Paragraph(f"<b>Observaciones:</b> {pay['notes']}", self.styles["Normal"]))

        doc.build(elements, canvasmaker=NumberedCanvas)
        logger.info(f"Comprobante PDF generado: {output_path}")
        return output_path

    def generate_amortization_table_pdf(self, loan_id: int, output_path: Path, actor_username: str) -> Path:
        """Contrato / Tabla de Amortización completa de un préstamo."""
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
            loan = cursor.fetchone()
            if not loan:
                raise ValueError(f"Préstamo #{loan_id} no encontrado.")

            cursor.execute("SELECT * FROM installments WHERE loan_id = ? ORDER BY number ASC;", (loan_id,))
            installments = cursor.fetchall()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            leftMargin=35, rightMargin=35, topMargin=40, bottomMargin=50
        )
        elements = self._build_header_flowables(f"PLAN DE AMORTIZACIÓN - PRÉSTAMO #{loan_id}", actor_username)

        sym = self.config.get("financiero", "moneda_simbolo", default="$")
        summary_data = [
            ["Cliente:", f"{loan['first_name']} {loan['last_name']}", "Monto Principal:", f"{sym} {Decimal(loan['principal']):,.2f}"],
            ["Identificación:", f"{loan['doc_type']} {loan['doc_number']}", "Tasa Interés Anual:", f"{Decimal(loan['annual_interest_rate']):,.2f}%"],
            ["Método:", loan["method"].capitalize(), "Periodicidad / Cuotas:", f"{loan['periodicity'].capitalize()} ({loan['installments_count']} cuotas)"],
            ["Desembolso:", loan["disbursement_date"], "Total Financiado:", f"{sym} {Decimal(loan['total_amount']):,.2f}"]
        ]
        sum_table = Table(summary_data, colWidths=[1.6 * inch, 2.2 * inch, 1.6 * inch, 2.0 * inch])
        sum_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(sum_table)
        elements.append(Spacer(1, 10))

        # Tabla de Cuotas
        elements.append(Paragraph("Calendario Detallado de Cuotas", self.styles["SectionHeading"]))
        table_rows = [
            [
                Paragraph("N°", self.styles["TableHeader"]),
                Paragraph("Vencimiento", self.styles["TableHeader"]),
                Paragraph("Capital", self.styles["TableHeader"]),
                Paragraph("Interés", self.styles["TableHeader"]),
                Paragraph("Cuota Total", self.styles["TableHeader"]),
                Paragraph("Saldo", self.styles["TableHeader"]),
                Paragraph("Estado", self.styles["TableHeader"]),
            ]
        ]

        for inst in installments:
            table_rows.append([
                Paragraph(str(inst["number"]), self.styles["TableCell"]),
                Paragraph(inst["due_date"], self.styles["TableCell"]),
                Paragraph(f"{sym} {Decimal(inst['capital_expected']):,.2f}", self.styles["TableCellRight"]),
                Paragraph(f"{sym} {Decimal(inst['interest_expected']):,.2f}", self.styles["TableCellRight"]),
                Paragraph(f"{sym} {Decimal(inst['total_expected']):,.2f}", self.styles["TableCellRight"]),
                Paragraph(f"{sym} {Decimal(inst['remaining_principal']):,.2f}", self.styles["TableCellRight"]),
                Paragraph(inst["status"].upper(), self.styles["TableCell"]),
            ])

        col_w = [0.4 * inch, 1.0 * inch, 1.2 * inch, 1.1 * inch, 1.2 * inch, 1.3 * inch, 1.0 * inch]
        amort_table = Table(table_rows, colWidths=col_w, repeatRows=1)
        amort_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 3),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
        ]))
        elements.append(amort_table)

        doc.build(elements, canvasmaker=NumberedCanvas)
        logger.info(f"Plan de amortización PDF generado: {output_path}")
        return output_path

    def generate_managerial_report_pdf(
        self,
        report_type: str,
        output_path: Path,
        actor_username: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Path:
        """Genera reportes gerenciales (PR-23)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            leftMargin=35, rightMargin=35, topMargin=40, bottomMargin=50
        )
        sym = self.config.get("financiero", "moneda_simbolo", default="$")

        with self.db.connection(exclusive_lock=False) as conn:
            cursor = conn.cursor()

            if report_type == "cartera_vigente":
                title = "REPORTE GERENCIAL: CARTERA VIGENTE"
                cursor.execute(
                    """
                    SELECT l.id, c.doc_number, (c.first_name || ' ' || c.last_name) as cliente,
                           l.principal, l.total_amount, l.periodicity, l.status
                    FROM loans l
                    JOIN clients c ON l.client_id = c.id
                    WHERE l.status IN ('activo', 'en_mora')
                    ORDER BY l.id ASC;
                    """
                )
                rows = cursor.fetchall()

                elements = self._build_header_flowables(title, actor_username)
                data = [
                    [Paragraph("Préstamo", self.styles["TableHeader"]), Paragraph("Documento", self.styles["TableHeader"]),
                     Paragraph("Cliente", self.styles["TableHeader"]), Paragraph("Principal", self.styles["TableHeader"]),
                     Paragraph("Total Financiado", self.styles["TableHeader"]), Paragraph("Estado", self.styles["TableHeader"])]
                ]
                tot_p = Decimal("0.00")
                tot_f = Decimal("0.00")
                for r in rows:
                    p = Decimal(r["principal"])
                    f = Decimal(r["total_amount"])
                    tot_p += p
                    tot_f += f
                    data.append([
                        Paragraph(f"#{r['id']}", self.styles["TableCell"]),
                        Paragraph(r["doc_number"], self.styles["TableCell"]),
                        Paragraph(r["cliente"], self.styles["TableCell"]),
                        Paragraph(f"{sym} {p:,.2f}", self.styles["TableCellRight"]),
                        Paragraph(f"{sym} {f:,.2f}", self.styles["TableCellRight"]),
                        Paragraph(r["status"].upper(), self.styles["TableCell"]),
                    ])
                data.append([
                    Paragraph("<b>TOTALES</b>", self.styles["TableCell"]),
                    Paragraph("", self.styles["TableCell"]),
                    Paragraph("", self.styles["TableCell"]),
                    Paragraph(f"<b>{sym} {tot_p:,.2f}</b>", self.styles["TableCellRight"]),
                    Paragraph(f"<b>{sym} {tot_f:,.2f}</b>", self.styles["TableCellRight"]),
                    Paragraph("", self.styles["TableCell"]),
                ])
                t = Table(data, colWidths=[1.0 * inch, 1.2 * inch, 2.2 * inch, 1.3 * inch, 1.3 * inch, 1.0 * inch], repeatRows=1)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                    ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#E5E7EB")),
                    ('PADDING', (0, 0), (-1, -1), 4),
                ]))
                elements.append(t)

            elif report_type == "cartera_mora":
                title = "REPORTE GERENCIAL: CARTERA EN MORA"
                today = date.today().strftime("%Y-%m-%d")
                cursor.execute(
                    """
                    SELECT l.id as loan_id, (c.first_name || ' ' || c.last_name) as cliente, c.phone,
                           i.number as cuota_num, i.due_date,
                           (CAST(i.capital_expected AS REAL) - CAST(i.capital_paid AS REAL)) as cap_pendiente,
                           CAST((julianday(?) - julianday(i.due_date)) AS INTEGER) as dias_mora
                    FROM installments i
                    JOIN loans l ON i.loan_id = l.id
                    JOIN clients c ON l.client_id = c.id
                    WHERE i.status IN ('pendiente', 'parcial', 'vencida')
                      AND i.due_date < ?
                    ORDER BY dias_mora DESC;
                    """,
                    (today, today)
                )
                rows = cursor.fetchall()
                elements = self._build_header_flowables(title, actor_username)
                data = [
                    [Paragraph("Préstamo", self.styles["TableHeader"]), Paragraph("Cliente", self.styles["TableHeader"]),
                     Paragraph("Teléfono", self.styles["TableHeader"]), Paragraph("Cuota", self.styles["TableHeader"]),
                     Paragraph("Vencimiento", self.styles["TableHeader"]), Paragraph("Días Mora", self.styles["TableHeader"]),
                     Paragraph("Capital Vencido", self.styles["TableHeader"])]
                ]
                tot_vencido = Decimal("0.00")
                for r in rows:
                    cap = Decimal(str(r["cap_pendiente"])).quantize(Decimal("0.01"))
                    tot_vencido += cap
                    data.append([
                        Paragraph(f"#{r['loan_id']}", self.styles["TableCell"]),
                        Paragraph(r["cliente"], self.styles["TableCell"]),
                        Paragraph(r["phone"], self.styles["TableCell"]),
                        Paragraph(str(r["cuota_num"]), self.styles["TableCell"]),
                        Paragraph(r["due_date"], self.styles["TableCell"]),
                        Paragraph(str(r["dias_mora"]), self.styles["TableCellRight"]),
                        Paragraph(f"{sym} {cap:,.2f}", self.styles["TableCellRight"]),
                    ])
                data.append([
                    Paragraph("<b>TOTAL EN MORA</b>", self.styles["TableCell"]),
                    Paragraph("", self.styles["TableCell"]),
                    Paragraph("", self.styles["TableCell"]),
                    Paragraph("", self.styles["TableCell"]),
                    Paragraph("", self.styles["TableCell"]),
                    Paragraph("", self.styles["TableCell"]),
                    Paragraph(f"<b>{sym} {tot_vencido:,.2f}</b>", self.styles["TableCellRight"]),
                ])
                t = Table(data, colWidths=[0.8 * inch, 1.8 * inch, 1.1 * inch, 0.6 * inch, 1.0 * inch, 0.9 * inch, 1.4 * inch], repeatRows=1)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B91C1C")), # Rojo para mora
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                    ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#FEE2E2")),
                    ('PADDING', (0, 0), (-1, -1), 4),
                ]))
                elements.append(t)

            else:
                # Recaudo por fechas
                title = "REPORTE GERENCIAL: HISTORIAL DE RECAUDO"
                cursor.execute(
                    """
                    SELECT p.*, (c.first_name || ' ' || c.last_name) as cliente
                    FROM payments p
                    JOIN loans l ON p.loan_id = l.id
                    JOIN clients c ON l.client_id = c.id
                    ORDER BY p.id DESC LIMIT 100;
                    """
                )
                rows = cursor.fetchall()
                elements = self._build_header_flowables(title, actor_username)
                data = [
                    [Paragraph("Pago #", self.styles["TableHeader"]), Paragraph("Fecha", self.styles["TableHeader"]),
                     Paragraph("Cliente", self.styles["TableHeader"]), Paragraph("Método", self.styles["TableHeader"]),
                     Paragraph("Mora", self.styles["TableHeader"]), Paragraph("Interés", self.styles["TableHeader"]),
                     Paragraph("Capital", self.styles["TableHeader"]), Paragraph("Total", self.styles["TableHeader"])]
                ]
                for r in rows:
                    data.append([
                        Paragraph(f"#{r['id']}", self.styles["TableCell"]),
                        Paragraph(r["payment_date"], self.styles["TableCell"]),
                        Paragraph(r["cliente"], self.styles["TableCell"]),
                        Paragraph(r["payment_method"].upper(), self.styles["TableCell"]),
                        Paragraph(f"{sym} {Decimal(r['late_fee_allocated']):,.2f}", self.styles["TableCellRight"]),
                        Paragraph(f"{sym} {Decimal(r['interest_allocated']):,.2f}", self.styles["TableCellRight"]),
                        Paragraph(f"{sym} {Decimal(r['capital_allocated']):,.2f}", self.styles["TableCellRight"]),
                        Paragraph(f"{sym} {Decimal(r['amount']):,.2f}", self.styles["TableCellRight"]),
                    ])
                t = Table(data, colWidths=[0.6 * inch, 0.9 * inch, 1.8 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch, 1.0 * inch, 1.0 * inch], repeatRows=1)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#047857")), # Verde para recaudo
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                    ('PADDING', (0, 0), (-1, -1), 3),
                ]))
                elements.append(t)

        doc.build(elements, canvasmaker=NumberedCanvas)
        logger.info(f"Reporte gerencial generado: {output_path}")
        return output_path

    @staticmethod
    def export_to_csv(headers: List[str], rows: List[List[Any]], output_path: Path) -> Path:
        """Exporta cualquier conjunto de datos tabulares a archivo CSV (PR-24)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        logger.info(f"Archivo CSV exportado exitosamente: {output_path}")
        return output_path


