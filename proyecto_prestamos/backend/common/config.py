import os
import json
import logging
from pathlib import Path
from decimal import Decimal
from typing import Any, Dict, List

logger = logging.getLogger("prestamos.config")

# Valores por defecto para el sistema
DEFAULT_CONFIG = {
    "empresa": {
        "nombre": "Préstamos & Soluciones Financieras Linux S.A.S.",
        "nit": "900.876.543-1",
        "telefono": "+57 (601) 789-0123",
        "email": "contacto@prestamoslinux.local",
        "direccion": "Calle 100 # 15-20, Bogotá, Colombia"
    },
    "financiero": {
        "moneda_simbolo": "$",
        "moneda_codigo": "COP",
        "tasa_interes_anual_maxima": "45.00",
        "tasa_mora_diaria_porcentaje": "0.05",  # 0.05% diario = 1.5% mensual aprox
        "dias_umbral_mora_bloqueo": 30,          # Máximo días en mora antes de bloquear nuevos créditos
        "dias_gracia": 0
    },
    "feriados": [
        "2026-01-01", "2026-01-12", "2026-03-23", "2026-04-02", "2026-04-03",
        "2026-05-01", "2026-05-18", "2026-06-08", "2026-06-15", "2026-06-29",
        "2026-07-20", "2026-08-07", "2026-08-17", "2026-10-12", "2026-11-02",
        "2026-11-16", "2026-12-08", "2026-12-25"
    ],
    "demonio": {
        "dias_anticipacion_alerta": 3,           # Notificar cuotas que vencen en los próximos N días
        "intervalo_chequeo_segundos": 3600,      # Cada hora verificar vencimientos
        "intervalo_respaldo_horas": 24,          # Respaldo diario automático
        "max_respaldos_guardados": 15
    }
}

class ConfigManager:
    """
    Gestión de configuración respetando el estándar XDG (SO-05).
    Configuración en ~/.config/gestion_prestamos/config.json con permisos 600 y directorio 700.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.xdg_config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        self.xdg_data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

        self.config_dir = self.xdg_config_home / "gestion_prestamos"
        self.data_dir = self.xdg_data_home / "gestion_prestamos"
        self.backup_dir = self.data_dir / "backups"
        self.logs_dir = self.data_dir / "logs"

        self.config_file = self.config_dir / "config.json"
        self.db_path = self.data_dir / "prestamos.db"
        self.ipc_socket_path = self.data_dir / "ipc.sock"

        self._config_data: Dict[str, Any] = {}
        self._ensure_directories()
        self.load()
        self._initialized = True

    def _ensure_directories(self):
        """Crea los directorios con permisos 700 (SO-05)."""
        for d in [self.config_dir, self.data_dir, self.backup_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(d, 0o700)
            except (OSError, NotImplementedError):
                pass

    def load(self):
        """Carga el archivo config.json o crea uno con valores por defecto."""
        self._ensure_directories()
        if not self.config_file.exists():
            self._config_data = json.loads(json.dumps(DEFAULT_CONFIG))
            self.save()
        else:
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # Fusionar con defaults para claves faltantes
                    self._config_data = json.loads(json.dumps(DEFAULT_CONFIG))
                    self._deep_update(self._config_data, loaded)
            except Exception as e:
                logger.error(f"Error al leer config.json: {e}. Usando configuración por defecto.")
                self._config_data = json.loads(json.dumps(DEFAULT_CONFIG))

    def _deep_update(self, base: dict, override: dict):
        for k, v in override.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                self._deep_update(base[k], v)
            else:
                base[k] = v

    def save(self):
        """Guarda la configuración actual en config.json con permisos 600 (SO-05)."""
        self._ensure_directories()
        temp_file = self.config_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._config_data, f, indent=4, ensure_ascii=False)
            
            # Establecer permisos estrictos 600 antes de reemplazar
            try:
                os.chmod(temp_file, 0o600)
            except (OSError, NotImplementedError):
                pass

            temp_file.replace(self.config_file)
            try:
                os.chmod(self.config_file, 0o600)
            except (OSError, NotImplementedError):
                pass
            logger.info("Configuración guardada exitosamente con permisos 600.")
        except Exception as e:
            logger.error(f"Error al guardar config.json: {e}")
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
            raise

    def reload(self):
        """Recarga dinámica activada típicamente por señal SIGHUP (SO-04)."""
        logger.info("Recargando dinámicamente archivo de configuración por señal SIGHUP...")
        self.load()
        logger.info("Configuración recargada con éxito.")

    def get(self, *keys, default=None) -> Any:
        curr = self._config_data
        for k in keys:
            if isinstance(curr, dict) and k in curr:
                curr = curr[k]
            else:
                return default
        return curr

    def set(self, *keys_and_value):
        if len(keys_and_value) < 2:
            raise ValueError("Se requiere al menos una clave y un valor.")
        keys = keys_and_value[:-1]
        value = keys_and_value[-1]

        curr = self._config_data
        for k in keys[:-1]:
            if k not in curr or not isinstance(curr[k], dict):
                curr[k] = {}
            curr = curr[k]
        curr[keys[-1]] = value
        self.save()

    @property
    def holidays(self) -> List[str]:
        return self._config_data.get("feriados", [])

    @property
    def daily_late_rate_decimal(self) -> Decimal:
        raw = self.get("financiero", "tasa_mora_diaria_porcentaje", default="0.05")
        return (Decimal(str(raw)) / Decimal("100")).quantize(Decimal("0.000001"))

    @property
    def max_annual_rate_decimal(self) -> Decimal:
        raw = self.get("financiero", "tasa_interes_anual_maxima", default="45.00")
        return Decimal(str(raw))


