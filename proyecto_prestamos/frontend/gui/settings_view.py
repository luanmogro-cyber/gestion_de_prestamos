from pathlib import Path
from decimal import Decimal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QFormLayout, QDoubleSpinBox,
    QSpinBox, QMessageBox, QFileDialog, QTextEdit
)
from PySide6.QtCore import Qt

from backend.common.config import ConfigManager
from backend.common.ipc_protocol import UnixSocketClient
from backend.database.db_manager import DatabaseManager

class SettingsView(QWidget):
    """
    Vista de Configuración, Respaldos y Monitoreo del Demonio (PR-25, PR-26, SO-04, SO-05).
    Acceso restringido: Solo rol 'Administrador'.
    """
    def __init__(self, config_manager: ConfigManager, db_manager: DatabaseManager, current_user: dict, parent=None):
        super(SettingsView, self).__init__(parent)
        self.config = config_manager
        self.db = db_manager
        self.current_user = current_user
        self.ipc_client = UnixSocketClient(self.config.ipc_socket_path)

        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Configuración del Sistema y Respaldos (SO-05)")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #0F2942;")
        layout.addWidget(title)

        is_admin = self.current_user.get("role") == "Administrador"

        # 1. Parámetros de la Entidad
        grp_company = QGroupBox("Datos de la Entidad Financiera")
        form_company = QFormLayout(grp_company)
        self.txt_company_name = QLineEdit()
        form_company.addRow("Razón Social:", self.txt_company_name)
        self.txt_company_nit = QLineEdit()
        form_company.addRow("NIT / Identificación:", self.txt_company_nit)
        self.txt_company_phone = QLineEdit()
        form_company.addRow("Teléfono de Contacto:", self.txt_company_phone)
        layout.addWidget(grp_company)

        # 2. Políticas Financieras
        grp_fin = QGroupBox("Políticas Financieras y Umbrales")
        form_fin = QFormLayout(grp_fin)

        self.sp_max_rate = QDoubleSpinBox()
        self.sp_max_rate.setRange(0.0, 100.0)
        self.sp_max_rate.setSuffix(" % Anual")
        form_fin.addRow("Tasa de Interés Máxima:", self.sp_max_rate)

        self.sp_late_rate = QDoubleSpinBox()
        self.sp_late_rate.setRange(0.001, 10.0)
        self.sp_late_rate.setDecimals(3)
        self.sp_late_rate.setSuffix(" % Diario")
        form_fin.addRow("Tasa de Mora Diaria:", self.sp_late_rate)

        self.sp_threshold = QSpinBox()
        self.sp_threshold.setRange(1, 365)
        self.sp_threshold.setSuffix(" Días")
        form_fin.addRow("Umbral Días en Mora para Bloqueo:", self.sp_threshold)
        layout.addWidget(grp_fin)

        # Botón Guardar Configuración
        btn_save_cfg = QPushButton("💾 Guardar Configuración (permisos 600)")
        btn_save_cfg.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 8px;")
        btn_save_cfg.clicked.connect(self._save_configuration)
        btn_save_cfg.setEnabled(is_admin)
        layout.addWidget(btn_save_cfg)

        # 3. Respaldos y Restauración SQLite (PR-26)
        grp_backup = QGroupBox("Gestión de Respaldos de Base de Datos (SQLite)")
        h_backup = QHBoxLayout(grp_backup)

        btn_manual_backup = QPushButton("📦 Crear Respaldo Ahora")
        btn_manual_backup.clicked.connect(self._create_manual_backup)
        btn_manual_backup.setEnabled(is_admin)
        h_backup.addWidget(btn_manual_backup)

        btn_restore = QPushButton("🔄 Restaurar desde Respaldo...")
        btn_restore.setStyleSheet("background-color: #DC2626; color: white;")
        btn_restore.clicked.connect(self._restore_backup)
        btn_restore.setEnabled(is_admin)
        h_backup.addWidget(btn_restore)
        layout.addWidget(grp_backup)

        # 4. Demonio en Segundo Plano y Comunicación IPC
        grp_daemon = QGroupBox("Demonio en Segundo Plano (prestamos-daemon) - IPC Unix Socket")
        v_daemon = QVBoxLayout(grp_daemon)

        h_daemon_btns = QHBoxLayout()
        btn_status = QPushButton("🔍 Consultar Estado Demonio")
        btn_status.clicked.connect(self._check_daemon_status)
        h_daemon_btns.addWidget(btn_status)

        btn_force_b = QPushButton("⚡ Forzar Respaldo vía Demonio")
        btn_force_b.clicked.connect(self._force_daemon_backup)
        btn_force_b.setEnabled(is_admin)
        h_daemon_btns.addWidget(btn_force_b)

        btn_force_a = QPushButton("🔔 Disparar Alertas Libnotify")
        btn_force_a.clicked.connect(self._force_daemon_alerts)
        h_daemon_btns.addWidget(btn_force_a)
        v_daemon.addLayout(h_daemon_btns)

        self.txt_daemon_output = QTextEdit()
        self.txt_daemon_output.setReadOnly(True)
        self.txt_daemon_output.setFixedHeight(80)
        self.txt_daemon_output.setPlaceholderText("Resultado de las consultas IPC con el demonio...")
        v_daemon.addWidget(self.txt_daemon_output)

        layout.addWidget(grp_daemon)

        if not is_admin:
            lbl_notice = QLabel("⚠️ Modo Cajero: Opciones de configuración y respaldos restringidas a Administrador.")
            lbl_notice.setStyleSheet("color: #DC2626; font-weight: bold;")
            layout.addWidget(lbl_notice)

    def _load_values(self):
        empresa = self.config.get("empresa", default={})
        self.txt_company_name.setText(empresa.get("nombre", ""))
        self.txt_company_nit.setText(empresa.get("nit", ""))
        self.txt_company_phone.setText(empresa.get("telefono", ""))

        fin = self.config.get("financiero", default={})
        self.sp_max_rate.setValue(float(fin.get("tasa_interes_anual_maxima", 45.0)))
        self.sp_late_rate.setValue(float(fin.get("tasa_mora_diaria_porcentaje", 0.05)))
        self.sp_threshold.setValue(int(fin.get("dias_umbral_mora_bloqueo", 30)))

    def _save_configuration(self):
        try:
            self.config.set("empresa", "nombre", self.txt_company_name.text().strip())
            self.config.set("empresa", "nit", self.txt_company_nit.text().strip())
            self.config.set("empresa", "telefono", self.txt_company_phone.text().strip())

            self.config.set("financiero", "tasa_interes_anual_maxima", str(self.sp_max_rate.value()))
            self.config.set("financiero", "tasa_mora_diaria_porcentaje", str(self.sp_late_rate.value()))
            self.config.set("financiero", "dias_umbral_mora_bloqueo", int(self.sp_threshold.value()))

            QMessageBox.information(self, "Configuración Guardada", "Parámetros actualizados con éxito en config.json.")
        except Exception as e:
            QMessageBox.critical(self, "Error al Guardar", str(e))

    def _create_manual_backup(self):
        try:
            path = self.db.create_backup()
            QMessageBox.information(self, "Respaldo Creado", f"Copia de seguridad SQLite creada en:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error Respaldo", str(e))

    def _restore_backup(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Archivo de Respaldo", str(self.config.backup_dir), "Bases de Datos (*.db)"
        )
        if not path:
            return

        reply = QMessageBox.warning(
            self, "Confirmar Restauración",
            "ATENCIÓN: Restaurar reemplazará los datos actuales por los del respaldo. ¿Desea continuar?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                self.db.restore_backup(Path(path))
                QMessageBox.information(self, "Restauración Exitosa", "La base de datos fue restaurada correctamente.")
            except Exception as e:
                QMessageBox.critical(self, "Error al Restaurar", str(e))

    def _check_daemon_status(self):
        res = self.ipc_client.send_command("ESTADO_DEMONIO")
        self.txt_daemon_output.setPlainText(str(res))

    def _force_daemon_backup(self):
        res = self.ipc_client.send_command("FORZAR_RESPALDO")
        self.txt_daemon_output.setPlainText(str(res))

    def _force_daemon_alerts(self):
        res = self.ipc_client.send_command("VERIFICAR_ALERTAS")
        self.txt_daemon_output.setPlainText(str(res))


