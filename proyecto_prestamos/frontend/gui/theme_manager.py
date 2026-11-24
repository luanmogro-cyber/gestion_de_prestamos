"""
Gestor de Temas y Paleta de Colores de Entidades Financieras para PySide6.
Diseñado bajo estándares corporativos y fintech:
- Paleta Institucional: Azul Marino Profundo (Confianza), Verde Esmeralda (Liquidez / Pagos), Ámbar Oro (Intereses / Pendientes) y Rojo Carmesí (Riesgo / Mora).
- Tipografía Ejecutiva: Familia Sans-Serif clara, legible y con alta legibilidad en números y montos monetarios.
- Soporte para Modo Día y Modo Noche dinámico con contraste óptimo en ambos esquemas.
"""

def get_theme_stylesheet(theme: str = "claro") -> str:
    is_dark = (theme.lower() == "oscuro")

    if is_dark:
        # ==========================================
        # PALETA MODO NOCHE (Executive Dark Fintech)
        # ==========================================
        bg_main = "#0B1120"          # Midnight Navy profundo
        bg_surface = "#111827"       # Superficie de tarjetas
        bg_input = "#1F2937"         # Fondo de campos de entrada
        border_input = "#374151"     # Borde neutro
        border_focus = "#3B82F6"     # Azul brillante al enfocar
        text_primary = "#F9FAFB"     # Blanco limpio de alto contraste
        text_secondary = "#9CA3AF"   # Gris medio para subtítulos
        table_alt = "#162032"        # Filas alternas
        table_grid = "#1F2937"       # Rejilla suave
        sidebar_bg = "#070D18"       # Barra lateral oscura ejecutiva
        card_bg = "#111827"          # Tarjeta financiera
        status_bg = "#070D18"
        status_border = "#1F2937"
        header_bg = "#0F2942"        # Encabezados de tabla en Azul Marino
        header_border = "#1E3A8A"
    else:
        # ==========================================
        # PALETA MODO DÍA (Corporate Light Banking)
        # ==========================================
        bg_main = "#F8FAFC"          # Slate gris blanquecino limpio
        bg_surface = "#FFFFFF"       # Superficie blanca pura
        bg_input = "#FFFFFF"         # Fondo blanco para escritura
        border_input = "#CBD5E1"     # Borde gris suave y delimitado
        border_focus = "#1D4ED8"     # Azul real corporativo
        text_primary = "#0F172A"     # Gris carbón casi negro (máxima legibilidad)
        text_secondary = "#475569"   # Gris pizarra para etiquetas secundarias
        table_alt = "#F1F5F9"        # Filas alternadas suaves
        table_grid = "#E2E8F0"       # Líneas sutiles de cuadrícula
        sidebar_bg = "#0F172A"       # Barra lateral institucional azul noche
        card_bg = "#FFFFFF"          # Fondo blanco de tarjetas
        status_bg = "#FFFFFF"
        status_border = "#E2E8F0"
        header_bg = "#0F2942"        # Encabezados Azul Marino Institucional
        header_border = "#1E3A8A"

    return f"""
        /* =======================================================
           TIPOGRAFÍA Y ESTILOS GLOBALES (INSTITUCIÓN FINANCIERA)
           ======================================================= */
        QMainWindow, QDialog {{
            background-color: {bg_main};
            color: {text_primary};
        }}
        QWidget {{
            color: {text_primary};
            font-family: "Segoe UI", "Inter", -apple-system, BlinkMacSystemFont, "Roboto", "Helvetica Neue", Arial, sans-serif;
            font-size: 13px;
        }}

        /* Barra Lateral (Sidebar Ejecutiva) */
        QFrame#sidebar {{
            background-color: {sidebar_bg};
            border-right: 1px solid #1E293B;
        }}
        QPushButton.nav-btn {{
            background-color: transparent;
            color: #CBD5E1;
            font-size: 13px;
            font-weight: 500;
            text-align: left;
            padding: 10px 14px;
            border: none;
            border-radius: 6px;
            margin: 2px 8px;
        }}
        QPushButton.nav-btn:hover {{
            background-color: #1E293B;
            color: #FFFFFF;
        }}
        QPushButton.nav-btn:checked {{
            background-color: #1D4ED8;
            color: #FFFFFF;
            font-weight: bold;
        }}

        /* Tarjetas, Grupos y Paneles de Información */
        QGroupBox {{
            background-color: {card_bg};
            border: 1.5px solid {border_input};
            border-radius: 8px;
            margin-top: 14px;
            font-weight: bold;
            color: {text_primary};
            padding: 14px 12px 12px 12px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 14px;
            padding: 0 8px;
            color: {text_primary};
            background-color: {card_bg};
            font-size: 13px;
            font-weight: bold;
        }}

        /* Etiquetas de Texto */
        QLabel {{
            color: {text_primary};
            background-color: transparent;
        }}
        QLabel[class="muted"] {{
            color: {text_secondary};
        }}

        /* =======================================================
           CAMPOS DE ENTRADA Y FORMULARIOS (ALTA VISIBILIDAD)
           ======================================================= */
        QLineEdit, QTextEdit, QPlainTextEdit,
        QSpinBox, QDoubleSpinBox, QDateEdit {{
            background-color: {bg_input} !important;
            color: {text_primary} !important;
            border: 1.5px solid {border_input};
            border-radius: 6px;
            padding: 7px 10px;
            font-size: 13px;
            selection-background-color: #1D4ED8;
            selection-color: #FFFFFF;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
        QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
            border: 2px solid {border_focus} !important;
            background-color: {bg_input} !important;
            color: {text_primary} !important;
        }}
        QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QDateEdit:disabled {{
            background-color: {table_alt} !important;
            color: {text_secondary} !important;
            border: 1px dashed {border_input};
        }}

        /* Selectores Desplegables (QComboBox) */
        QComboBox {{
            background-color: {bg_input} !important;
            color: {text_primary} !important;
            border: 1.5px solid {border_input};
            border-radius: 6px;
            padding: 6px 10px;
            min-height: 24px;
        }}
        QComboBox:focus {{
            border: 2px solid {border_focus} !important;
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 25px;
            border-left: 1px solid {border_input};
        }}
        QComboBox QAbstractItemView {{
            background-color: {bg_input} !important;
            color: {text_primary} !important;
            selection-background-color: #1D4ED8;
            selection-color: #FFFFFF;
            border: 1px solid {border_input};
            padding: 4px;
        }}

        /* =======================================================
           TABLAS FINANCIERAS (ENCABEZADOS AZUL MARINO Y CUADRÍCULA)
           ======================================================= */
        QTableWidget {{
            background-color: {card_bg};
            alternate-background-color: {table_alt};
            color: {text_primary};
            gridline-color: {table_grid};
            border: 1.5px solid {border_input};
            border-radius: 8px;
            selection-background-color: #1D4ED8;
            selection-color: #FFFFFF;
        }}
        QTableWidget QTableCornerButton::section {{
            background-color: {header_bg};
            border: 1px solid {header_border};
        }}
        QHeaderView::section {{
            background-color: {header_bg};
            color: #FFFFFF;
            font-weight: bold;
            font-size: 12px;
            padding: 8px;
            border: 0.5px solid {header_border};
        }}

        /* Pestañas (QTabWidget) */
        QTabWidget::pane {{
            border: 1px solid {border_input};
            background-color: {card_bg};
            border-radius: 8px;
            top: -1px;
        }}
        QTabBar::tab {{
            background-color: {table_alt};
            color: {text_secondary};
            padding: 8px 18px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            border: 1px solid {border_input};
            border-bottom: none;
            margin-right: 3px;
            font-weight: 500;
        }}
        QTabBar::tab:selected {{
            background-color: {card_bg};
            color: {text_primary};
            font-weight: bold;
            border-bottom: 2.5px solid #1D4ED8;
        }}
        QTabBar::tab:hover {{
            background-color: {bg_surface};
            color: {text_primary};
        }}

        /* Calendario de Vencimientos */
        QCalendarWidget QWidget#qt_calendar_navigationbar {{
            background-color: {header_bg};
            color: #FFFFFF;
        }}
        QCalendarWidget QToolButton {{
            color: #FFFFFF;
            background-color: transparent;
            font-weight: bold;
        }}
        QCalendarWidget QTableView {{
            background-color: {card_bg};
            color: {text_primary};
            selection-background-color: #1D4ED8;
            selection-color: #FFFFFF;
        }}
        QCalendarWidget QSpinBox {{
            color: #FFFFFF !important;
            background-color: #1E3A8A !important;
        }}

        /* =======================================================
           BOTONES DE ACCIÓN FINANCIERA (PALETA SEMÁNTICA)
           ======================================================= */
        QPushButton {{
            border-radius: 6px;
            padding: 7px 14px;
            font-weight: 600;
            font-size: 12.5px;
            border: none;
        }}
        QPushButton:hover {{
            opacity: 0.92;
        }}
        QPushButton:pressed {{
            opacity: 0.82;
        }}

        /* Botón Primario: Azul Marino Institucional */
        QPushButton[class="btn-primary"] {{
            background-color: #1D4ED8;
            color: #FFFFFF;
        }}
        /* Botón Éxito / Pagos: Verde Esmeralda */
        QPushButton[class="btn-success"] {{
            background-color: #059669;
            color: #FFFFFF;
        }}
        /* Botón Advertencia / Pendientes: Ámbar Dorado */
        QPushButton[class="btn-warning"] {{
            background-color: #D97706;
            color: #FFFFFF;
        }}
        /* Botón Peligro / Cancelación: Rojo Carmesí */
        QPushButton[class="btn-danger"] {{
            background-color: #DC2626;
            color: #FFFFFF;
        }}
        /* Botón Secundario / Neutro: Gris Pizarra */
        QPushButton[class="btn-secondary"] {{
            background-color: #475569;
            color: #FFFFFF;
        }}

        /* Barra de Desplazamiento (Scrollbar Elegante) */
        QScrollBar:vertical {{
            background: {bg_main};
            width: 10px;
            margin: 0px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical {{
            background: {border_input};
            min-height: 20px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: #94A3B8;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}

        /* Barra de Estado Inferior */
        QStatusBar {{
            background-color: {status_bg};
            border-top: 1px solid {status_border};
            color: {text_secondary};
            font-size: 12px;
            padding: 3px;
        }}
    """
