"""
Gestor de Temas (Modo Día / Modo Noche) para la aplicación PySide6.
Garantiza contraste óptimo y visibilidad absoluta de tipografías en todos los campos de entrada.
"""

def get_theme_stylesheet(theme: str = "claro") -> str:
    is_dark = (theme.lower() == "oscuro")

    if is_dark:
        # Paleta Modo Noche (Dark)
        bg_main = "#0B0F19"
        bg_surface = "#151E2E"
        bg_input = "#1E293B"
        border_input = "#475569"
        border_focus = "#3B82F6"
        text_primary = "#F8FAFC"
        text_secondary = "#94A3B8"
        table_alt = "#1E293B"
        table_grid = "#334155"
        sidebar_bg = "#0A0D14"
        card_bg = "#151E2E"
        status_bg = "#0F172A"
        status_border = "#1E293B"
    else:
        # Paleta Modo Día (Light)
        bg_main = "#F8FAFC"
        bg_surface = "#FFFFFF"
        bg_input = "#FFFFFF"
        border_input = "#CBD5E1"
        border_focus = "#2563EB"
        text_primary = "#0F172A"
        text_secondary = "#475569"
        table_alt = "#F1F5F9"
        table_grid = "#E2E8F0"
        sidebar_bg = "#0F172A"
        card_bg = "#FFFFFF"
        status_bg = "#FFFFFF"
        status_border = "#E2E8F0"

    return f"""
        /* Estilos Globales de Ventanas y Diálogos */
        QMainWindow, QDialog {{
            background-color: {bg_main};
            color: {text_primary};
        }}
        QWidget {{
            color: {text_primary};
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            font-size: 13px;
        }}

        /* Barra Lateral (Sidebar) */
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
            background-color: #2563EB;
            color: #FFFFFF;
            font-weight: bold;
        }}

        /* Tarjetas, Grupos y Paneles */
        QGroupBox {{
            background-color: {card_bg};
            border: 1px solid {border_input};
            border-radius: 8px;
            margin-top: 14px;
            font-weight: bold;
            color: {text_primary};
            padding: 14px 10px 10px 10px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 6px;
            color: {text_primary};
            background-color: {card_bg};
        }}

        /* Etiquetas */
        QLabel {{
            color: {text_primary};
            background-color: transparent;
        }}
        QLabel[class="muted"] {{
            color: {text_secondary};
        }}

        /* CAMPOS DE TEXTO Y ENTRADA (VISIBILIDAD 100% GARANTIZADA) */
        QLineEdit, QTextEdit, QPlainTextEdit,
        QSpinBox, QDoubleSpinBox, QDateEdit {{
            background-color: {bg_input} !important;
            color: {text_primary} !important;
            border: 1.5px solid {border_input};
            border-radius: 6px;
            padding: 7px 10px;
            font-size: 13px;
            selection-background-color: #2563EB;
            selection-color: #FFFFFF;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
        QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
            border: 2px solid {border_focus} !important;
            background-color: {bg_input} !important;
            color: {text_primary} !important;
        }}
        QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
            background-color: {table_alt} !important;
            color: {text_secondary} !important;
        }}

        /* Menús desplegables (QComboBox) */
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
            selection-background-color: #2563EB;
            selection-color: #FFFFFF;
            border: 1px solid {border_input};
            padding: 4px;
        }}

        /* Tablas */
        QTableWidget {{
            background-color: {card_bg};
            alternate-background-color: {table_alt};
            color: {text_primary};
            gridline-color: {table_grid};
            border: 1px solid {border_input};
            border-radius: 6px;
            selection-background-color: #2563EB;
            selection-color: #FFFFFF;
        }}
        QTableWidget QTableCornerButton::section {{
            background-color: #1E3A8A;
            border: 1px solid #1E3A8A;
        }}
        QHeaderView::section {{
            background-color: #1E3A8A;
            color: #FFFFFF;
            font-weight: bold;
            font-size: 12px;
            padding: 6px;
            border: 0.5px solid #1E40AF;
        }}

        /* Pestañas (QTabWidget) */
        QTabWidget::pane {{
            border: 1px solid {border_input};
            background-color: {card_bg};
            border-radius: 6px;
            top: -1px;
        }}
        QTabBar::tab {{
            background-color: {table_alt};
            color: {text_secondary};
            padding: 8px 16px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            border: 1px solid {border_input};
            border-bottom: none;
            margin-right: 2px;
            font-weight: 500;
        }}
        QTabBar::tab:selected {{
            background-color: {card_bg};
            color: {text_primary};
            font-weight: bold;
            border-bottom: 2px solid #2563EB;
        }}
        QTabBar::tab:hover {{
            background-color: {bg_surface};
            color: {text_primary};
        }}

        /* Calendario (QCalendarWidget) */
        QCalendarWidget QWidget#qt_calendar_navigationbar {{
            background-color: #1E3A8A;
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
            selection-background-color: #2563EB;
            selection-color: #FFFFFF;
        }}
        QCalendarWidget QSpinBox {{
            color: #FFFFFF !important;
            background-color: #1E40AF !important;
        }}

        /* Botones Generales */
        QPushButton {{
            border-radius: 6px;
            padding: 7px 14px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            opacity: 0.9;
        }}

        /* Barra de Estado */
        QStatusBar {{
            background-color: {status_bg};
            border-top: 1px solid {status_border};
            color: {text_secondary};
            font-size: 12px;
        }}
    """


