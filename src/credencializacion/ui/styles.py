"""
Sistema de estilos y paleta de colores para la UI.
Proporciona un stylesheet QSS completo con look premium moderno.
"""

# ---------------------------------------------------------------------------
# Paleta de colores centralizada
# ---------------------------------------------------------------------------
COLORS: dict[str, str] = {
    # Primario — rojo / coral
    "primary": "#FB5252",
    "primary_hover": "#E04848",
    "primary_pressed": "#D43D3D",
    # Secundario — dorado
    "secondary": "#FFD057",
    "secondary_hover": "#F0C34E",
    # Texto
    "text": "#171A2B",
    "text_light": "#64748B",
    "text_white": "#FFFFFF",
    # Fondos
    "bg_sidebar": "#FFFFFF",
    "bg_sidebar_hover": "#F8FAFC",
    "bg_sidebar_active": "#FEE2E2",
    "bg_main": "#F5F7FA",
    "bg_card": "#FFFFFF",
    # Bordes
    "border": "#E2E8F0",
    "border_focus": "#FB5252",
    # Estado — éxito
    "success": "#22C55E",
    "success_bg": "#F0FDF4",
    # Estado — advertencia
    "warning": "#F59E0B",
    "warning_bg": "#FFFBEB",
    # Estado — error
    "error": "#EF4444",
    "error_bg": "#FEF2F2",
    # Estado — informativo
    "info": "#3B82F6",
    "info_bg": "#EFF6FF",
}

# Familia tipográfica principal (se registra en runtime)
FONT_FAMILY = "'Inter', 'SF Pro Display', 'Segoe UI', 'Helvetica Neue', sans-serif"
FONT_SIZE_BASE = "13px"
FONT_SIZE_SM = "12px"
FONT_SIZE_LG = "15px"
FONT_SIZE_XL = "18px"
BORDER_RADIUS = "8px"
BORDER_RADIUS_SM = "6px"
BORDER_RADIUS_LG = "12px"


def get_main_stylesheet() -> str:
    """Devuelve el stylesheet QSS global de la aplicación.

    El stylesheet cubre **todos** los widgets estándar de Qt y las clases
    custom del sistema (sidebar, cards, badges, etc.).  Se inyecta una
    sola vez en ``QApplication.setStyleSheet()``.
    """
    c = COLORS  # alias corto

    return f"""
    /* ================================================================
       GLOBAL
       ================================================================ */
    * {{
        font-family: {FONT_FAMILY};
        font-size: {FONT_SIZE_BASE};
        color: {c["text"]};
        outline: none;
    }}

    QMainWindow {{
        background-color: {c["bg_main"]};
    }}

    QWidget {{
        background-color: transparent;
    }}

    QWidget#centralWidget {{
        background-color: {c["bg_main"]};
    }}

    /* ================================================================
       TOOLTIPS
       ================================================================ */
    QToolTip {{
        background-color: {c["text"]};
        color: {c["text_white"]};
        border: none;
        border-radius: 4px;
        padding: 6px 10px;
        font-size: {FONT_SIZE_SM};
    }}

    /* ================================================================
       LABELS
       ================================================================ */
    QLabel {{
        background-color: transparent;
        padding: 0;
    }}

    QLabel#headerTitle {{
        font-size: {FONT_SIZE_XL};
        font-weight: 700;
        color: {c["text"]};
    }}

    QLabel#subtitleLabel {{
        font-size: {FONT_SIZE_SM};
        color: {c["text_light"]};
    }}

    /* ================================================================
       BUTTONS — variants via objectName
       ================================================================ */
    QPushButton {{
        background-color: {c["bg_card"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: {BORDER_RADIUS};
        padding: 8px 20px;
        font-weight: 600;
        font-size: {FONT_SIZE_BASE};
        min-height: 20px;
    }}
    QPushButton:hover {{
        background-color: {c["bg_main"]};
        border-color: {c["text_light"]};
    }}
    QPushButton:pressed {{
        background-color: {c["border"]};
    }}
    QPushButton:disabled {{
        background-color: {c["bg_main"]};
        color: {c["text_light"]};
        border-color: {c["border"]};
    }}

    /* --- Primary --- */
    QPushButton#primaryButton,
    QPushButton[variant="primary"] {{
        background-color: {c["primary"]};
        color: {c["text_white"]};
        border: none;
    }}
    QPushButton#primaryButton:hover,
    QPushButton[variant="primary"]:hover {{
        background-color: {c["primary_hover"]};
    }}
    QPushButton#primaryButton:pressed,
    QPushButton[variant="primary"]:pressed {{
        background-color: {c["primary_pressed"]};
    }}
    QPushButton#primaryButton:disabled,
    QPushButton[variant="primary"]:disabled {{
        background-color: #F8A0A0;
        color: #FFFFFF;
    }}

    /* --- Secondary --- */
    QPushButton#secondaryButton,
    QPushButton[variant="secondary"] {{
        background-color: {c["secondary"]};
        color: {c["text"]};
        border: none;
        font-weight: 700;
    }}
    QPushButton#secondaryButton:hover,
    QPushButton[variant="secondary"]:hover {{
        background-color: {c["secondary_hover"]};
    }}
    QPushButton#secondaryButton:pressed,
    QPushButton[variant="secondary"]:pressed {{
        background-color: #E0B744;
    }}

    /* --- Outline --- */
    QPushButton#outlineButton,
    QPushButton[variant="outline"] {{
        background-color: transparent;
        color: {c["primary"]};
        border: 1.5px solid {c["primary"]};
    }}
    QPushButton#outlineButton:hover,
    QPushButton[variant="outline"]:hover {{
        background-color: {c["error_bg"]};
    }}
    QPushButton#outlineButton:pressed,
    QPushButton[variant="outline"]:pressed {{
        background-color: #FDD;
    }}

    /* --- Danger --- */
    QPushButton#dangerButton,
    QPushButton[variant="danger"] {{
        background-color: {c["error"]};
        color: {c["text_white"]};
        border: none;
    }}
    QPushButton#dangerButton:hover,
    QPushButton[variant="danger"]:hover {{
        background-color: #DC2626;
    }}
    QPushButton#dangerButton:pressed,
    QPushButton[variant="danger"]:pressed {{
        background-color: #B91C1C;
    }}

    /* --- Ghost / icon-only --- */
    QPushButton#ghostButton,
    QPushButton[variant="ghost"] {{
        background-color: transparent;
        border: none;
        padding: 6px;
    }}
    QPushButton#ghostButton:hover,
    QPushButton[variant="ghost"]:hover {{
        background-color: {c["border"]};
        border-radius: {BORDER_RADIUS};
    }}

    /* ================================================================
       LINE EDIT
       ================================================================ */
    QLineEdit {{
        background-color: {c["bg_card"]};
        border: 1.5px solid {c["border"]};
        border-radius: {BORDER_RADIUS};
        padding: 8px 12px;
        font-size: {FONT_SIZE_BASE};
        color: {c["text"]};
        selection-background-color: {c["primary"]};
        selection-color: {c["text_white"]};
    }}
    QLineEdit:focus {{
        border-color: {c["border_focus"]};
    }}
    QLineEdit:disabled {{
        background-color: {c["bg_main"]};
        color: {c["text_light"]};
    }}
    QLineEdit::placeholder {{
        color: {c["text_light"]};
    }}

    /* ================================================================
       COMBOBOX
       ================================================================ */
    QComboBox {{
        background-color: {c["bg_card"]};
        border: 1.5px solid {c["border"]};
        border-radius: {BORDER_RADIUS};
        padding: 8px 12px;
        padding-right: 28px;
        font-size: {FONT_SIZE_BASE};
        color: {c["text"]};
        min-height: 20px;
    }}
    QComboBox:focus,
    QComboBox:on {{
        border-color: {c["border_focus"]};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: center right;
        width: 28px;
        border: none;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {c["text_light"]};
        margin-right: 8px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {c["bg_card"]};
        border: 1px solid {c["border"]};
        border-radius: {BORDER_RADIUS_SM};
        padding: 4px;
        selection-background-color: {c["bg_main"]};
        selection-color: {c["text"]};
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{
        padding: 6px 10px;
        border-radius: 4px;
        min-height: 24px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: {c["bg_main"]};
    }}

    /* ================================================================
       SPINBOX
       ================================================================ */
    QSpinBox,
    QDoubleSpinBox {{
        background-color: {c["bg_card"]};
        border: 1.5px solid {c["border"]};
        border-radius: {BORDER_RADIUS};
        padding: 8px 12px;
        font-size: {FONT_SIZE_BASE};
        color: {c["text"]};
    }}
    QSpinBox:focus,
    QDoubleSpinBox:focus {{
        border-color: {c["border_focus"]};
    }}
    QSpinBox::up-button,
    QDoubleSpinBox::up-button {{
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 22px;
        border: none;
        border-left: 1px solid {c["border"]};
        border-top-right-radius: {BORDER_RADIUS};
    }}
    QSpinBox::down-button,
    QDoubleSpinBox::down-button {{
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 22px;
        border: none;
        border-left: 1px solid {c["border"]};
        border-bottom-right-radius: {BORDER_RADIUS};
    }}
    QSpinBox::up-arrow,
    QDoubleSpinBox::up-arrow {{
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-bottom: 4px solid {c["text_light"]};
    }}
    QSpinBox::down-arrow,
    QDoubleSpinBox::down-arrow {{
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 4px solid {c["text_light"]};
    }}

    /* ================================================================
       TABLE WIDGET
       ================================================================ */
    QTableWidget,
    QTableView {{
        background-color: {c["bg_card"]};
        alternate-background-color: {c["bg_main"]};
        border: 1px solid {c["border"]};
        border-radius: {BORDER_RADIUS};
        gridline-color: {c["border"]};
        selection-background-color: {c["error_bg"]};
        selection-color: {c["text"]};
        font-size: {FONT_SIZE_SM};
    }}
    QTableWidget::item,
    QTableView::item {{
        padding: 8px 12px;
        border: none;
    }}
    QTableWidget::item:selected,
    QTableView::item:selected {{
        background-color: {c["error_bg"]};
        color: {c["text"]};
    }}
    QHeaderView {{
        background-color: transparent;
    }}
    QHeaderView::section {{
        background-color: {c["bg_main"]};
        color: {c["text_light"]};
        font-weight: 600;
        font-size: {FONT_SIZE_SM};
        text-transform: uppercase;
        padding: 10px 12px;
        border: none;
        border-bottom: 2px solid {c["border"]};
        border-right: 1px solid {c["border"]};
    }}
    QHeaderView::section:last {{
        border-right: none;
    }}

    /* ================================================================
       TAB WIDGET / TAB BAR
       ================================================================ */
    QTabWidget::pane {{
        background-color: {c["bg_card"]};
        border: 1px solid {c["border"]};
        border-radius: {BORDER_RADIUS};
        border-top-left-radius: 0;
        padding: 12px;
    }}
    QTabBar {{
        background-color: transparent;
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {c["text_light"]};
        padding: 10px 20px;
        font-weight: 600;
        font-size: {FONT_SIZE_BASE};
        border: none;
        border-bottom: 3px solid transparent;
        margin-right: 4px;
    }}
    QTabBar::tab:hover {{
        color: {c["text"]};
        border-bottom-color: {c["border"]};
    }}
    QTabBar::tab:selected {{
        color: {c["primary"]};
        border-bottom-color: {c["primary"]};
    }}

    /* ================================================================
       SCROLLBAR — moderno / delgado
       ================================================================ */
    QScrollBar:vertical {{
        background-color: transparent;
        width: 8px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background-color: {c["border"]};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {c["text_light"]};
    }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {{
        background: none;
        height: 0;
        border: none;
    }}

    QScrollBar:horizontal {{
        background-color: transparent;
        height: 8px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {c["border"]};
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {c["text_light"]};
    }}
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal,
    QScrollBar::sub-page:horizontal {{
        background: none;
        width: 0;
        border: none;
    }}

    /* ================================================================
       GROUPBOX
       ================================================================ */
    QGroupBox {{
        background-color: {c["bg_card"]};
        border: 1px solid {c["border"]};
        border-radius: {BORDER_RADIUS};
        margin-top: 16px;
        padding: 20px 16px 16px 16px;
        font-weight: 600;
        font-size: {FONT_SIZE_BASE};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 4px 12px;
        color: {c["text"]};
        font-weight: 700;
    }}

    /* ================================================================
       CHECKBOX
       ================================================================ */
    QCheckBox {{
        spacing: 8px;
        font-size: {FONT_SIZE_BASE};
        color: {c["text"]};
        background-color: transparent;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid {c["border"]};
        border-radius: 4px;
        background-color: {c["bg_card"]};
    }}
    QCheckBox::indicator:hover {{
        border-color: {c["primary"]};
    }}
    QCheckBox::indicator:checked {{
        background-color: {c["primary"]};
        border-color: {c["primary"]};
    }}

    /* ================================================================
       RADIO BUTTON
       ================================================================ */
    QRadioButton {{
        spacing: 8px;
        font-size: {FONT_SIZE_BASE};
        color: {c["text"]};
        background-color: transparent;
    }}
    QRadioButton::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid {c["border"]};
        border-radius: 9px;
        background-color: {c["bg_card"]};
    }}
    QRadioButton::indicator:hover {{
        border-color: {c["primary"]};
    }}
    QRadioButton::indicator:checked {{
        background-color: {c["primary"]};
        border-color: {c["primary"]};
    }}

    /* ================================================================
       PROGRESS BAR
       ================================================================ */
    QProgressBar {{
        background-color: {c["border"]};
        border: none;
        border-radius: 4px;
        height: 8px;
        text-align: center;
        font-size: 0;
    }}
    QProgressBar::chunk {{
        background-color: {c["primary"]};
        border-radius: 4px;
    }}

    /* ================================================================
       MENU BAR & MENUS
       ================================================================ */
    QMenuBar {{
        background-color: {c["bg_card"]};
        border-bottom: 1px solid {c["border"]};
        padding: 2px;
    }}
    QMenuBar::item {{
        padding: 6px 12px;
        border-radius: 4px;
    }}
    QMenuBar::item:selected {{
        background-color: {c["bg_main"]};
    }}
    QMenu {{
        background-color: {c["bg_card"]};
        border: 1px solid {c["border"]};
        border-radius: {BORDER_RADIUS};
        padding: 6px;
    }}
    QMenu::item {{
        padding: 8px 24px 8px 12px;
        border-radius: 4px;
        font-size: {FONT_SIZE_BASE};
    }}
    QMenu::item:selected {{
        background-color: {c["bg_main"]};
    }}
    QMenu::separator {{
        height: 1px;
        background-color: {c["border"]};
        margin: 4px 8px;
    }}

    /* ================================================================
       SPLITTER
       ================================================================ */
    QSplitter::handle {{
        background-color: {c["border"]};
    }}
    QSplitter::handle:horizontal {{
        width: 1px;
    }}
    QSplitter::handle:vertical {{
        height: 1px;
    }}

    /* ================================================================
       STATUS BAR
       ================================================================ */
    QStatusBar {{
        background-color: {c["bg_card"]};
        border-top: 1px solid {c["border"]};
        font-size: {FONT_SIZE_SM};
        color: {c["text_light"]};
        padding: 4px 12px;
    }}

    /* ================================================================
       TEXT EDIT / PLAIN TEXT
       ================================================================ */
    QTextEdit,
    QPlainTextEdit {{
        background-color: {c["bg_card"]};
        border: 1.5px solid {c["border"]};
        border-radius: {BORDER_RADIUS};
        padding: 8px 12px;
        font-size: {FONT_SIZE_BASE};
        color: {c["text"]};
        selection-background-color: {c["primary"]};
        selection-color: {c["text_white"]};
    }}
    QTextEdit:focus,
    QPlainTextEdit:focus {{
        border-color: {c["border_focus"]};
    }}

    /* ================================================================
       DIALOG
       ================================================================ */
    QDialog {{
        background-color: {c["bg_card"]};
        border-radius: {BORDER_RADIUS_LG};
    }}

    /* ================================================================
       CUSTOM CLASSES — Sidebar
       ================================================================ */
    QWidget#sidebar {{
        background-color: {c["bg_sidebar"]};
    }}

    /* ================================================================
       CUSTOM CLASSES — Card
       ================================================================ */
    QFrame#card,
    QWidget#card {{
        background-color: {c["bg_card"]};
        border: 1px solid {c["border"]};
        border-radius: {BORDER_RADIUS_LG};
        padding: 20px;
    }}

    /* ================================================================
       CUSTOM CLASSES — Badges
       ================================================================ */
    QLabel#badgeSuccess {{
        background-color: {c["success_bg"]};
        color: {c["success"]};
        border-radius: 10px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 700;
    }}
    QLabel#badgeWarning {{
        background-color: {c["warning_bg"]};
        color: {c["warning"]};
        border-radius: 10px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 700;
    }}
    QLabel#badgeError {{
        background-color: {c["error_bg"]};
        color: {c["error"]};
        border-radius: 10px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 700;
    }}
    QLabel#badgeInfo {{
        background-color: {c["info_bg"]};
        color: {c["info"]};
        border-radius: 10px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 700;
    }}

    /* ================================================================
       CUSTOM CLASSES — Stat card header
       ================================================================ */
    QLabel#statValue {{
        font-size: 28px;
        font-weight: 800;
        color: {c["text"]};
    }}
    QLabel#statLabel {{
        font-size: {FONT_SIZE_SM};
        font-weight: 500;
        color: {c["text_light"]};
    }}

    /* ================================================================
       CUSTOM — Header bar
       ================================================================ */
    QFrame#headerBar {{
        background-color: {c["bg_card"]};
        border-bottom: 1px solid {c["border"]};
        min-height: 56px;
        padding: 0 20px;
    }}

    QPushButton#headerIconBtn {{
        background-color: transparent;
        border: none;
        border-radius: 20px;
        padding: 8px;
        font-size: 16px;
        min-width: 36px;
        max-width: 36px;
        min-height: 36px;
        max-height: 36px;
    }}
    QPushButton#headerIconBtn:hover {{
        background-color: {c["bg_main"]};
    }}

    /* ================================================================
       CUSTOM — Sidebar CTA button
       ================================================================ */
    QPushButton#sidebarCta {{
        background-color: {c["primary"]};
        color: {c["text_white"]};
        border: none;
        border-radius: {BORDER_RADIUS};
        padding: 10px 16px;
        font-weight: 700;
        font-size: {FONT_SIZE_SM};
    }}
    QPushButton#sidebarCta:hover {{
        background-color: {c["primary_hover"]};
    }}
    QPushButton#sidebarCta:pressed {{
        background-color: {c["primary_pressed"]};
    }}

    /* ================================================================
       SEARCH BAR (in header)
       ================================================================ */
    QLineEdit#searchBar {{
        border-radius: 20px;
        padding: 8px 16px 8px 36px;
        min-width: 240px;
        background-color: {c["bg_main"]};
        border: 1px solid {c["border"]};
    }}
    QLineEdit#searchBar:focus {{
        border-color: {c["border_focus"]};
        background-color: {c["bg_card"]};
    }}
    """
