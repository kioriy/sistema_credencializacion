"""
Ventana principal del Sistema de Credencialización.
Sidebar fija a la izquierda + content area con QStackedWidget.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFont, QCursor
import qtawesome as qta
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QToolBar,
    QToolButton,
    QMenu,
)

from credencializacion.ui.styles import COLORS
from credencializacion.ui.widgets.sidebar import Sidebar
from credencializacion.ui.pages.control_panel import ControlPanel
from credencializacion.ui.pages.template_editor import TemplateEditor
from credencializacion.ui.pages.template_manager import TemplateManager
from credencializacion.ui.pages.print_center import PrintCenter
from credencializacion.ui.pages.config_panel import ConfigPanel


class MainWindow(QMainWindow):
    """Ventana principal con sidebar de navegación y área de contenido."""

    WINDOW_TITLE = "Sistema de Credencialización — miescuela.net"
    MIN_WIDTH = 1100
    MIN_HEIGHT = 700

    # Títulos de las páginas (orden = mismo que sidebar items)
    PAGE_TITLES: list[str] = [
        "Panel de Control",
        "Editor de Plantillas",
        "Gestión Plantillas",
        "Centro de Impresión",
        "Configuración",
        "Soporte",
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(1280, 800)

        # Widgets principales
        self._sidebar: Sidebar | None = None
        self._stack: QStackedWidget | None = None

        self._setup_ui()

    # ------------------------------------------------------------------ UI
    def _setup_ui(self) -> None:
        """Construye el layout: sidebar | (header + content stack)."""
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ---- Sidebar ----
        self._sidebar = Sidebar()
        self._sidebar.page_changed.connect(self._on_page_changed)
        self._sidebar.update_requested.connect(self._on_update_requested)
        root_layout.addWidget(self._sidebar)

        # ---- Columna derecha: header + stack ----
        right_column = QWidget()
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Stacked pages
        self._stack = QStackedWidget()
        self._stack.setObjectName("contentStack")
        
        # Añadir páginas reales (ordenadas igual que el sidebar)
        self._control_panel = ControlPanel()
        self._template_editor = TemplateEditor()
        self._template_manager = TemplateManager()
        self._stack.addWidget(self._control_panel)
        self._stack.addWidget(self._template_editor)
        self._stack.addWidget(self._template_manager)
        self._print_center = PrintCenter()
        self._stack.addWidget(self._print_center)
        
        # Toolbar por sección (stacked)
        self._toolbar_stack = QStackedWidget()
        self._toolbar_stack.setFixedHeight(56)
        self._create_toolbars()
        right_layout.addWidget(self._toolbar_stack)
        
        # Configuración (Página 4) y Soporte (Placeholder 5)
        self._stack.addWidget(ConfigPanel())
        self._stack.addWidget(self._create_placeholder_page(self.PAGE_TITLES[5], 5))
        
        right_layout.addWidget(self._stack)

        root_layout.addWidget(right_column)

        # Conectar botones de toolbar con handlers del ControlPanel
        self.btn_print_front.clicked.connect(self._control_panel._on_print_front)
        self.btn_print_back.clicked.connect(self._control_panel._on_print_back)
        self.btn_preview.clicked.connect(self._control_panel._on_preview)
        self.btn_add_queue.clicked.connect(self._control_panel._add_selected_to_queue)
        self.btn_sync.clicked.connect(self._control_panel._on_sync_api)

    # --------------------------------------------------------- toolbars
    def _create_toolbars(self) -> None:
        """Crea una toolbar personalizada por cada sección del menú."""
        # 0 — Panel de Control
        tb_control = self._make_toolbar_frame()
        tb_layout = tb_control.layout()
        self.btn_print_front = self._make_toolbar_btn("fa5s.print", "Imprimir Frente", primary=True)
        self.btn_print_back = self._make_toolbar_btn("fa5s.print", "Imprimir Vuelta", primary=True)
        self.btn_preview = self._make_toolbar_btn("fa5s.eye", "Vista Previa", primary=False)
        
        self.btn_sync = QToolButton()
        self.btn_sync.setText("Sincronizar")
        self.btn_sync.setIcon(qta.icon("fa5s.sync-alt", color=COLORS["text"]))
        self.btn_sync.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_sync.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.btn_sync.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_sync.setMinimumHeight(40)
        self.btn_sync.setStyleSheet(self._toolbar_btn_style(False).replace("QPushButton", "QToolButton") + """
            QToolButton::menu-button {
                border-left: 1px solid #E2E8F0;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                width: 28px;
            }
            QToolButton::menu-arrow {
                width: 16px;
                height: 16px;
            }
        """)
        
        self.menu_sync = QMenu(self.btn_sync)
        self.action_sync_app = self.menu_sync.addAction("app.miescuela.net")
        self.action_sync_sheets = self.menu_sync.addAction("Google Sheets")
        self.action_sync_file = self.menu_sync.addAction("Importar archivo (xlsx/csv)")
        self.btn_sync.setMenu(self.menu_sync)
        
        self.action_sync_app.triggered.connect(
            lambda: self._control_panel.set_status("Origen de sincronización: app.miescuela.net", "sync")
        )
        self.action_sync_sheets.triggered.connect(
            lambda: self._control_panel.set_status("Origen de sincronización: Google Sheets", "sync")
        )
        self.action_sync_file.triggered.connect(
            lambda: self._control_panel.set_status("Origen de sincronización: Importar archivo (xlsx/csv)", "sync")
        )

        tb_layout.addWidget(self.btn_print_front)
        tb_layout.addWidget(self.btn_print_back)
        tb_layout.addWidget(self.btn_preview)

        self.btn_add_queue = self._make_toolbar_btn("fa5s.plus-circle", "Agregar a Cola", primary=False)
        tb_layout.addWidget(self.btn_add_queue)

        tb_layout.addWidget(self.btn_sync)
        tb_layout.addStretch()
        self._toolbar_stack.addWidget(tb_control)

        # 1 — Editor de Plantillas
        tb_editor = self._make_toolbar_frame()
        tb_ed_layout = tb_editor.layout()
        
        self.btn_editor_save = self._make_toolbar_btn("fa5s.save", "Guardar", primary=True)
        tb_ed_layout.addWidget(self.btn_editor_save)

        self.btn_editor_open = self._make_toolbar_btn("fa5s.folder-open", "Abrir", primary=False)
        tb_ed_layout.addWidget(self.btn_editor_open)
        
        self.btn_editor_preview = self._make_toolbar_btn("fa5s.eye", "Vista Previa", primary=False)
        tb_ed_layout.addWidget(self.btn_editor_preview)
        
        # Botones de alineación y eliminar
        tb_ed_layout.addSpacing(20)
        self.btn_editor_align_left = self._make_icon_only_btn("fa5s.align-left", "Alinear Izquierda")
        self.btn_editor_align_center = self._make_icon_only_btn("fa5s.align-center", "Centrar")
        self.btn_editor_align_right = self._make_icon_only_btn("fa5s.align-right", "Alinear Derecha")
        
        self.btn_editor_undo = self._make_icon_only_btn("fa5s.undo", "Deshacer")
        self.btn_editor_redo = self._make_icon_only_btn("fa5s.redo", "Rehacer")
        
        self.btn_editor_delete = self._make_icon_only_btn("fa5s.trash", "Eliminar Seleccionado")
        
        tb_ed_layout.addWidget(self.btn_editor_align_left)
        tb_ed_layout.addWidget(self.btn_editor_align_center)
        tb_ed_layout.addWidget(self.btn_editor_align_right)
        tb_ed_layout.addSpacing(10)
        tb_ed_layout.addWidget(self.btn_editor_undo)
        tb_ed_layout.addWidget(self.btn_editor_redo)
        tb_ed_layout.addSpacing(10)
        tb_ed_layout.addWidget(self.btn_editor_delete)

        tb_ed_layout.addStretch()
        self.btn_editor_horizontal = self._make_icon_only_btn("mdi.crop-landscape", "Horizontal")
        self.btn_editor_vertical = self._make_icon_only_btn("mdi.crop-portrait", "Vertical")
        tb_ed_layout.addWidget(self.btn_editor_horizontal)
        tb_ed_layout.addWidget(self.btn_editor_vertical)
        self._toolbar_stack.addWidget(tb_editor)

        # Conectar botones del editor
        self.btn_editor_horizontal.clicked.connect(lambda: self._template_editor.set_orientation(True))
        self.btn_editor_vertical.clicked.connect(lambda: self._template_editor.set_orientation(False))
        self.btn_editor_align_left.clicked.connect(lambda: self._template_editor.align_selected("left"))
        self.btn_editor_align_center.clicked.connect(lambda: self._template_editor.align_selected("center"))
        self.btn_editor_align_right.clicked.connect(lambda: self._template_editor.align_selected("right"))
        self.btn_editor_delete.clicked.connect(self._template_editor.delete_selected)
        self.btn_editor_open.clicked.connect(self._template_editor.open_template_dialog)
        self.btn_editor_save.clicked.connect(self._template_editor.save_template)
        self.btn_editor_preview.clicked.connect(
            lambda: self._template_editor.preview_template(cara="both")
        )
        self.btn_editor_undo.clicked.connect(self._template_editor.undo)
        self.btn_editor_redo.clicked.connect(self._template_editor.redo)

        # 2 — Gestión de Plantillas
        tb_manager = self._make_toolbar_frame()
        tb_mg_layout = tb_manager.layout()
        self.btn_manager_refresh = self._make_toolbar_btn("fa5s.sync-alt", "Refrescar", primary=False)
        tb_mg_layout.addWidget(self.btn_manager_refresh)
        tb_mg_layout.addStretch()
        self._toolbar_stack.addWidget(tb_manager)

        # Conectar botón refrescar
        self.btn_manager_refresh.clicked.connect(self._template_manager.refresh_clients)

        # 3 — Centro de Impresión
        tb_print = self._make_toolbar_frame()
        tb_pr_layout = tb_print.layout()
        self.btn_print_refresh = self._make_toolbar_btn("fa5s.sync-alt", "Actualizar Colas", primary=False)
        self.btn_print_refresh.clicked.connect(self._print_center.refresh_queues)
        tb_pr_layout.addWidget(self.btn_print_refresh)
        tb_pr_layout.addStretch()
        self._toolbar_stack.addWidget(tb_print)

        # Conectar señal de cola creada → auto-refrescar Centro de Impresión
        self._control_panel.add_to_queue_requested.connect(
            self._print_center.refresh_queues
        )

        # 4 — Configuración
        tb_config = self._make_toolbar_frame()
        tb_config_layout = tb_config.layout()
        tb_config_layout.addStretch()
        self._toolbar_stack.addWidget(tb_config)

        # 5 — Soporte
        tb_support = self._make_toolbar_frame()
        tb_support.layout().addStretch()
        self._toolbar_stack.addWidget(tb_support)

    def _make_toolbar_frame(self) -> QFrame:
        """Crea el contenedor base de una toolbar."""
        bar = QFrame()
        bar.setObjectName("toolBar")
        bar.setFixedHeight(56)
        bar.setStyleSheet(f"""
            QFrame#toolBar {{
                background-color: {COLORS['bg_card']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(10)
        return bar

    def _make_icon_only_btn(self, icon_name: str, tooltip: str) -> QPushButton:
        """Crea un botón cuadrado solo con ícono (sin texto)."""
        c = COLORS
        btn = QPushButton()
        btn.setIcon(qta.icon(icon_name, color=c["text"]))
        btn.setIconSize(QSize(22, 22))
        btn.setFixedSize(40, 40)
        btn.setToolTip(tooltip)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 2px solid {c['border']};
                border-radius: 8px;
            }}
            QPushButton:hover {{
                border-color: {c['primary']};
            }}
        """)
        return btn

    def _make_toolbar_btn(
        self, icon_name: str, text: str, *, primary: bool = False
    ) -> QPushButton:
        """Crea un botón para la toolbar con icono qtawesome y texto."""
        btn = QPushButton(text)
        btn.setIcon(qta.icon(icon_name, color="#FFF" if primary else COLORS["text"]))
        btn.setIconSize(QSize(18, 18))
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setMinimumHeight(40)
        btn.setMinimumWidth(140)
        btn.setStyleSheet(self._toolbar_btn_style(primary))
        return btn

    @staticmethod
    def _toolbar_btn_style(primary: bool) -> str:
        c = COLORS
        if primary:
            return f"""
                QPushButton {{
                    background-color: {c['primary']};
                    color: #FFFFFF;
                    border: none;
                    border-radius: 8px;
                    padding: 8px 20px;
                    font-size: 13px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ background-color: {c['primary_hover']}; }}
                QPushButton:pressed {{ background-color: {c['primary_pressed']}; }}
            """
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {c['text']};
                border: 2px solid {c['border']};
                border-radius: 8px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border-color: {c['primary']};
                color: {c['primary']};
            }}
        """

    # -------------------------------------------------------- placeholder
    def _create_placeholder_page(self, title: str, index: int) -> QWidget:
        """Página de marcador de posición mientras se construyen las reales."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        # Card contenedora
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(12)

        # Ícono grande
        icon_label = QLabel(["📊", "🎨", "📋", "🖨️", "⚙️", "🔧"][index])
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 48px;")
        card_layout.addWidget(icon_label)

        # Título
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(f"""
            QLabel {{
                font-size: 20px;
                font-weight: 700;
                color: {COLORS["text"]};
            }}
        """)
        card_layout.addWidget(title_label)

        # Subtítulo
        desc = QLabel("Esta sección está en construcción.")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet(f"""
            QLabel {{
                font-size: 14px;
                color: {COLORS["text_light"]};
            }}
        """)
        card_layout.addWidget(desc)

        layout.addWidget(card)
        layout.addStretch()

        return page

    # --------------------------------------------------------------- slots
    def _on_page_changed(self, index: int) -> None:
        """Cambia la página del stack y la toolbar correspondiente."""
        if 0 <= index < self._stack.count():
            self._stack.setCurrentIndex(index)
        if 0 <= index < self._toolbar_stack.count():
            self._toolbar_stack.setCurrentIndex(index)

        # Auto-refrescar colas al navegar al Centro de Impresión (índice 3)
        if index == 3:
            self._print_center.refresh_queues()

    def _on_update_requested(self) -> None:
        """Ejecuta una comprobación manual de actualizaciones."""
        try:
            from credencializacion.core.updater import check_for_updates
            check_for_updates(self, manual=True)
        except Exception as e:
            from credencializacion.ui.widgets.toast import ToastManager
            ToastManager.instance().show_toast(f"Error: {e}", "error")
