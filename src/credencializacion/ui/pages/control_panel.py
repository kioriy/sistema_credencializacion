"""
Panel de Control principal del sistema de credencialización.

Vista central con barra de herramientas, filtros, tabla de registros,
y paginación. Permite seleccionar registros para impresión/vista previa.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from PySide6.QtCore import Qt, Signal, QSize, QThread, Slot, QUrl
from PySide6.QtGui import QFont, QCursor, QIcon, QPixmap, QPainter, QPainterPath, QColor
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QCheckBox,
    QFrame,
    QSizePolicy,
    QSpacerItem,
    QMessageBox,
    QProgressDialog,
    QTableWidgetItem,
    QCompleter,
)

from credencializacion.ui.widgets.record_table import RecordTable
from credencializacion.ui.widgets.print_queue import PrintQueuePanel

if TYPE_CHECKING:
    from credencializacion.db.models import Registro

logger = logging.getLogger(__name__)

# ── Paleta de colores ──────────────────────────────────────────────────
PRIMARY = "#FB5252"
SECONDARY = "#FFD057"
TEXT_DARK = "#171A2B"
TEXT_LIGHT = "#64748B"
CARD_BG = "#FFFFFF"
BORDER = "#E2E8F0"
MAIN_BG = "#F5F7FA"
SUCCESS = "#22C55E"

# Credenciales de la API MiEscuela (fallback si el Cliente no las tiene).
_API_BASE_URL = "https://app.miescuela.net"
_API_KEY = "7c9e6679-7425-40de-944b-e07fc1f90ae7"


class QueueRenderWorker(QThread):
    """Renderiza en segundo plano los PDFs (frentes y vueltas) de una cola.

    Trabaja con IDs de registro + id de plantilla y produce dos PDFs (2 diseños
    por hoja) en ``out_dir``. Abre su propia sesión de BD (solo lectura) en el
    hilo del worker. Emite ``progress`` con mensajes de estado para el footer,
    ``finished_ok`` con las rutas resultantes y ``failed`` ante un error.
    """

    progress = Signal(str)
    finished_ok = Signal(str, str)  # frentes_pdf, vueltas_pdf
    failed = Signal(str)

    def __init__(self, record_ids: list[int], plantilla_id: int, out_dir: str) -> None:
        super().__init__()
        self._record_ids = list(record_ids)
        self._plantilla_id = plantilla_id
        self._out_dir = out_dir

    def run(self) -> None:  # noqa: D401
        try:
            from pathlib import Path
            from credencializacion.db.engine import DatabaseSession
            from credencializacion.db.models import Plantilla, Registro
            from credencializacion.db.repositories import LadoConfigRepository
            from credencializacion.services.image_selection import select_imagen
            from credencializacion.renderer.pdf_engine import PDFEngine

            out_dir = Path(self._out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)

            with DatabaseSession() as session:
                plantilla = session.query(Plantilla).get(self._plantilla_id)
                if plantilla is None:
                    self.failed.emit("Plantilla no encontrada")
                    return

                regs_by_id = {
                    r.id: r
                    for r in session.query(Registro)
                    .filter(Registro.id.in_(self._record_ids))
                    .all()
                }
                render_items = [
                    (regs_by_id[i], plantilla)
                    for i in self._record_ids
                    if i in regs_by_id
                ]
                if not render_items:
                    self.failed.emit("No hay registros para renderizar")
                    return

                def _overrides(cara: str) -> list[str | None]:
                    cfg = LadoConfigRepository.get_config_lado(
                        session, self._plantilla_id, cara
                    )
                    if cfg is None:
                        return [None] * len(render_items)
                    return [
                        select_imagen(reg.datos or {}, cfg)
                        for reg, _ in render_items
                    ]

                engine = PDFEngine(plantilla)

                self.progress.emit("🖼 Generando PDF de frentes...")
                frentes_pdf = engine.render_queue(
                    render_items, "frente", out_dir / "frentes.pdf",
                    fondo_overrides=_overrides("frente"),
                )

                self.progress.emit("🖼 Generando PDF de vueltas...")
                vueltas_pdf = engine.render_queue(
                    render_items, "vuelta", out_dir / "vueltas.pdf",
                    fondo_overrides=_overrides("vuelta"),
                )

            self.finished_ok.emit(str(frentes_pdf), str(vueltas_pdf))
        except Exception as e:  # noqa: BLE001
            logger.error("Error al renderizar cola en segundo plano: %s", e)
            self.failed.emit(str(e))


class ControlPanel(QWidget):
    """Panel de control principal con tabla de registros.

    Contiene:
    - Barra de herramientas con acciones de impresión
    - Filtros por cliente, búsqueda, plantilla, atributos e impresora
    - Tabla de registros con checkboxes, fotos y estados
    - Paginación inferior

    Signals:
        print_front_requested(list[int]): IDs seleccionados para imprimir frente.
        print_back_requested(list[int]): IDs seleccionados para imprimir vuelta.
        preview_requested(list[int]): IDs seleccionados para vista previa.
    """

    print_front_requested = Signal(list)
    print_back_requested = Signal(list)
    preview_requested = Signal(list)
    add_to_queue_requested = Signal()  # Emitted after successfully adding to queue

    # ── Constantes de paginación ───────────────────────────────────
    PAGE_SIZE = 25

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._all_records: list["Registro"] = []
        self._filtered_records: list[dict] | None = None  # None = sin filtro
        self._active_status_filter: str | None = None
        self._current_page = 0
        self._total_records = 0
        # Network manager para descargar fotos async
        self._net_manager = QNetworkAccessManager(self)
        self._photo_cache: dict[str, QPixmap] = {}  # url -> pixmap circular
        self._raw_photo_cache: dict[str, QPixmap] = {} # url -> pixmap original
        self._pending_photos: dict[int, str] = {}  # reply_id -> url
        self._setup_ui()
        self._connect_signals()
        self._render_worker = None
        self._render_on_done = None
        self._mark_workers = []

    # ── Construcción de UI ─────────────────────────────────────────

    def _setup_ui(self) -> None:
        """Ensambla el layout completo del panel de control."""
        self.setStyleSheet(f"background-color: {MAIN_BG};")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0) # Quitar margenes externos
        main_layout.setSpacing(0)

        # Card principal (fondo blanco con bordes redondeados opcionales o sin borde)
        self._card = QFrame()
        self._card.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        # Barra de filtros
        card_layout.addLayout(self._build_filter_bar())

        # Numeralias / contadores de estado (filtros clickeables)
        card_layout.addLayout(self._build_status_counters())

        # Separador sutil
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet(f"background-color: {BORDER}; max-height: 1px;")
        card_layout.addWidget(separator)

        # Tabla de registros
        self._table = RecordTable()
        card_layout.addWidget(self._table, stretch=1)

        # Barra de paginación inferior
        card_layout.addLayout(self._build_pagination_bar())

        # Footer de estado (dentro del card, ancho del contenedor central)
        self._status_bar = QLabel("")
        self._status_bar.setFixedHeight(28)
        self._status_bar.setStyleSheet(f"""
            QLabel {{
                background-color: #1E293B;
                color: #94A3B8;
                font-family: 'Inter', sans-serif;
                font-size: 12px;
                padding: 0 12px;
                border: none;
                border-radius: 0;
            }}
        """)
        card_layout.addWidget(self._status_bar)

        # Contenedor horizontal para la tabla y la cola de impresión
        h_layout = QHBoxLayout()
        h_layout.setSpacing(0)
        h_layout.setContentsMargins(0, 0, 0, 0)
        
        h_layout.addWidget(self._card, stretch=3)

        # Panel de Cola de Impresión
        self._queue_panel = PrintQueuePanel()
        h_layout.addWidget(self._queue_panel, stretch=1)

        main_layout.addLayout(h_layout, stretch=1)

    def _build_toolbar(self) -> QHBoxLayout:
        # Metodo sin uso (el título se pidió eliminar)
        return QHBoxLayout()

    def _build_filter_bar(self) -> QVBoxLayout:
        """Construye la barra de filtros con selectores en 2 filas.

        Fila 1: Selector de Clientes + Búsqueda
        Fila 2: Selector de Plantillas + Selector de Impresoras

        Returns:
            Layout vertical con los controles.
        """
        filter_bar = QVBoxLayout()
        filter_bar.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        # Estilos compartidos para combos
        combo_style = f"""
            QComboBox {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                color: {TEXT_DARK};
                font-family: 'Inter', sans-serif;
                min-width: 100px;
            }}
            QComboBox:hover {{
                border-color: {PRIMARY};
            }}
            QComboBox:focus {{
                border-color: {PRIMARY};
                outline: none;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 28px;
                padding-right: 8px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid {TEXT_LIGHT};
                width: 0;
                height: 0;
                margin-right: 8px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 4px;
                color: {TEXT_DARK};
                selection-background-color: #FEE2E2;
                selection-color: {TEXT_DARK};
                font-size: 13px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 12px;
                min-height: 28px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {MAIN_BG};
            }}
        """

        # --- Fila 1: Cliente + Búsqueda ---
        self._combo_clients = QComboBox()
        self._combo_clients.setEditable(True)
        self._combo_clients.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._combo_clients.lineEdit().setPlaceholderText("Buscar escuela...")
        self._combo_clients.completer().setCompletionMode(
            QCompleter.CompletionMode.PopupCompletion
        )
        self._combo_clients.completer().setFilterMode(
            Qt.MatchFlag.MatchContains
        )
        self._combo_clients.completer().popup().setStyleSheet(f"""
            QAbstractItemView {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 4px;
                color: {TEXT_DARK};
                selection-background-color: #FEE2E2;
                selection-color: {TEXT_DARK};
                font-size: 13px;
                outline: none;
            }}
            QAbstractItemView::item {{
                padding: 6px 12px;
                min-height: 28px;
            }}
            QAbstractItemView::item:hover {{
                background-color: {MAIN_BG};
            }}
        """)
        self._combo_clients.setCurrentIndex(-1)
        self._combo_clients.setStyleSheet(combo_style)
        row1.addWidget(self._combo_clients, stretch=1)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍 Buscar por nombre, ID, grado+grupo (ej: 1A)...")
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {MAIN_BG};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 13px;
                color: {TEXT_DARK};
                font-family: 'Inter', sans-serif;
            }}
            QLineEdit:focus {{
                border-color: {PRIMARY};
                background-color: {CARD_BG};
            }}
            QLineEdit::placeholder {{
                color: {TEXT_LIGHT};
            }}
        """)
        row1.addWidget(self._search_input, stretch=1)

        # Etiqueta de resultados de filtro
        self._lbl_filter_count = QLabel("")
        self._lbl_filter_count.setStyleSheet(f"""
            QLabel {{
                background-color: #FEE2E2;
                color: {PRIMARY};
                border: 1px solid {PRIMARY};
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
                font-family: 'Inter', sans-serif;
            }}
        """)
        self._lbl_filter_count.setVisible(False)
        row1.addWidget(self._lbl_filter_count)

        # --- Fila 2: Plantilla ---
        self._combo_templates = QComboBox()
        self._combo_templates.addItem("Plantillas")
        self._combo_templates.setStyleSheet(combo_style)
        row2.addWidget(self._combo_templates, stretch=1)

        filter_bar.addLayout(row1)
        filter_bar.addLayout(row2)

        return filter_bar

    def _build_status_counters(self) -> QHBoxLayout:
        """Construye la fila de numeralias/contadores de estado clickeables."""
        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 0, 0, 0)

        pill_base = """
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 14px;
                padding: 4px 14px;
                font-family: 'Inter', sans-serif;
                font-size: 12px;
                font-weight: 600;
                min-height: 28px;
            }}
            QPushButton:hover {{
                border-color: {hover_border};
                background-color: {hover_bg};
            }}
            QPushButton:checked {{
                background-color: {active_bg};
                color: #FFFFFF;
                border-color: {active_bg};
            }}
        """

        self._pill_all = QPushButton("📋 Todos: 0")
        self._pill_all.setCheckable(True)
        self._pill_all.setChecked(True)
        self._pill_all.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pill_all.setStyleSheet(pill_base.format(
            bg=MAIN_BG, fg=TEXT_DARK, border=BORDER,
            hover_border=PRIMARY, hover_bg="#FEE2E2",
            active_bg=TEXT_DARK,
        ))

        self._pill_ready = QPushButton("✅ Listos: 0")
        self._pill_ready.setCheckable(True)
        self._pill_ready.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pill_ready.setStyleSheet(pill_base.format(
            bg="#F0FDF4", fg="#16A34A", border="#BBF7D0",
            hover_border="#16A34A", hover_bg="#DCFCE7",
            active_bg="#16A34A",
        ))

        self._pill_no_photo = QPushButton("📷 Sin foto: 0")
        self._pill_no_photo.setCheckable(True)
        self._pill_no_photo.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pill_no_photo.setStyleSheet(pill_base.format(
            bg="#FFFBEB", fg="#D97706", border="#FDE68A",
            hover_border="#D97706", hover_bg="#FEF3C7",
            active_bg="#D97706",
        ))

        self._pill_no_form = QPushButton("📋 Sin formulario: 0")
        self._pill_no_form.setCheckable(True)
        self._pill_no_form.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pill_no_form.setStyleSheet(pill_base.format(
            bg="#FFF7ED", fg="#EA580C", border="#FED7AA",
            hover_border="#EA580C", hover_bg="#FFEDD5",
            active_bg="#EA580C",
        ))

        self._pill_pending = QPushButton("📝 Pendientes: 0")
        self._pill_pending.setCheckable(True)
        self._pill_pending.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pill_pending.setStyleSheet(pill_base.format(
            bg="#EFF6FF", fg="#2563EB", border="#BFDBFE",
            hover_border="#2563EB", hover_bg="#DBEAFE",
            active_bg="#2563EB",
        ))

        self._pill_all.clicked.connect(lambda: self._apply_status_filter(None))
        self._pill_ready.clicked.connect(lambda: self._apply_status_filter("ready"))
        self._pill_no_photo.clicked.connect(lambda: self._apply_status_filter("sin_fotografia"))
        self._pill_no_form.clicked.connect(lambda: self._apply_status_filter("sin_formulario"))
        self._pill_pending.clicked.connect(lambda: self._apply_status_filter("pending"))

        row.addWidget(self._pill_all)
        row.addWidget(self._pill_ready)
        row.addWidget(self._pill_no_photo)
        row.addWidget(self._pill_no_form)
        row.addWidget(self._pill_pending)
        row.addStretch()

        return row

    def _build_pagination_bar(self) -> QHBoxLayout:
        """Construye la barra de paginación inferior.

        Returns:
            Layout horizontal con info de registros y botones de paginación.
        """
        pagination = QHBoxLayout()
        pagination.setSpacing(8)

        # Select All checkbox
        self._chk_select_all = QCheckBox("Seleccionar todo")
        self._chk_select_all.setStyleSheet(f"""
            QCheckBox {{
                color: {TEXT_LIGHT};
                font-size: 12px;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 2px solid {BORDER};
                border-radius: 4px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {PRIMARY};
                border-color: {PRIMARY};
            }}
        """)
        pagination.addWidget(self._chk_select_all)

        pagination.addStretch()

        # Label de conteo
        self._lbl_page_info = QLabel("Mostrando 0-0 de 0 registros")
        self._lbl_page_info.setFont(QFont("Inter", 12))
        self._lbl_page_info.setStyleSheet(f"color: {TEXT_LIGHT};")
        pagination.addWidget(self._lbl_page_info)

        # Botones de navegación
        nav_btn_style = f"""
            QPushButton {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 6px 12px;
                color: {TEXT_DARK};
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {PRIMARY};
                color: {PRIMARY};
            }}
            QPushButton:disabled {{
                color: {BORDER};
                border-color: {BORDER};
            }}
        """

        self._btn_prev = QPushButton("‹")
        self._btn_prev.setFixedSize(36, 36)
        self._btn_prev.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_prev.setStyleSheet(nav_btn_style)
        self._btn_prev.setEnabled(False)
        pagination.addWidget(self._btn_prev)

        self._btn_next = QPushButton("›")
        self._btn_next.setFixedSize(36, 36)
        self._btn_next.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_next.setStyleSheet(nav_btn_style)
        pagination.addWidget(self._btn_next)

        return pagination

    # ── Conexión de señales ────────────────────────────────────────

    def _connect_signals(self) -> None:
        """Conecta señales internas del panel."""
        self._btn_prev.clicked.connect(self._prev_page)
        self._btn_next.clicked.connect(self._next_page)
        self._chk_select_all.toggled.connect(self._table.select_all)
        self._search_input.textChanged.connect(self._on_search_changed)
        self._combo_clients.currentIndexChanged.connect(self._on_client_selected)
        self._table.add_to_queue_clicked.connect(self._add_single_to_queue)

    # ── Métodos públicos ───────────────────────────────────────────

    def load_records(self, records: list["Registro"]) -> None:
        """Carga registros en la tabla con paginación.

        Args:
            records: Lista completa de registros a mostrar.
        """
        self._all_records = records
        self._filtered_records = None
        self._active_status_filter = None
        self._total_records = len(records)
        self._current_page = 1
        self._update_status_counters()
        self._refresh_page()

    def get_selected_records(self) -> list[int]:
        """Obtiene los IDs de los registros seleccionados.

        Returns:
            Lista de IDs de registros con checkbox marcado.
        """
        return self._table.get_selected_ids()

    def set_clients(self, clients: list[tuple[int, str]]) -> None:
        """Actualiza el combo de clientes.

        Args:
            clients: Lista de tuplas (id, nombre) de clientes.
        """
        self._combo_clients.clear()
        self._combo_clients.addItem("Todos los Clientes")
        for client_id, name in clients:
            self._combo_clients.addItem(name, userData=client_id)

    def set_templates(self, templates: list[tuple[int, str]]) -> None:
        """Actualiza el combo de plantillas.

        Args:
            templates: Lista de tuplas (id, nombre) de plantillas.
        """
        self._combo_templates.clear()
        self._combo_templates.addItem("Plantillas")
        for tmpl_id, name in templates:
            self._combo_templates.addItem(name, userData=tmpl_id)

    def set_printers(self, printers: list[str]) -> None:
        """Compatibilidad: el selector de impresoras fue retirado.

        Se conserva el método como no-op para no romper llamadas externas.
        """
        return



    # ── Helpers de UI ──────────────────────────────────────────────

    def _create_icon_button(self, icon_name: str, label_text: str, primary: bool = False) -> QPushButton:
        """Crea un botón que combina un ícono qtawesome con texto."""
        btn = QPushButton()
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setMinimumHeight(40)
        
        if primary:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {PRIMARY};
                    border: none;
                    border-radius: 8px;
                    color: #FFFFFF;
                }}
                QPushButton:hover {{ background-color: #E04848; }}
                QPushButton:pressed {{ background-color: #C73E3E; }}
                QPushButton:disabled {{ background-color: {BORDER}; }}
            """)
            icon_color = "#FFFFFF"
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: 2px solid {BORDER};
                    border-radius: 8px;
                    color: {TEXT_DARK};
                }}
                QPushButton:hover {{
                    border-color: {PRIMARY};
                    color: {PRIMARY};
                }}
            """)
            icon_color = TEXT_DARK

        btn_layout = QHBoxLayout(btn)
        btn_layout.setContentsMargins(12, 0, 12, 0)
        btn_layout.setSpacing(8)
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(18, 18)
        icon_lbl.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(QSize(18, 18)))
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        
        text_lbl = QLabel(label_text)
        text_color = "#FFFFFF" if primary else TEXT_DARK
        text_lbl.setStyleSheet(f"background: transparent; border: none; font-weight: bold; font-size: 13px; color: {text_color};")
        
        btn_layout.addWidget(icon_lbl)
        btn_layout.addWidget(text_lbl)
        return btn

    # ── Handlers de acciones ───────────────────────────────────────

    def _on_preview(self) -> None:
        """Genera la vista previa de la cola de impresión sin bloquear la app.

        El render (frentes y vueltas, 2 diseños por hoja) se ejecuta en un hilo
        en segundo plano; el progreso se refleja en el footer y, al terminar, se
        abre el diálogo de vista previa.
        """
        queue_records = self._queue_panel.get_queue()
        if not queue_records:
            self.set_status("⚠️ La cola de impresión está vacía", "warning")
            return

        plantilla_id = self._combo_templates.currentData()
        if not plantilla_id:
            self.set_status("⚠️ Selecciona una plantilla primero", "warning")
            return

        if getattr(self, "_render_worker", None) is not None:
            self.set_status("⏳ Ya hay una generación en curso...", "warning", toast=False)
            return

        import tempfile

        ids = [r.id for r in queue_records]
        out_dir = tempfile.mkdtemp(prefix="credencial_preview_")

        self.set_status("🖼 Generando vista previa...", "info", toast=False)
        self._start_render(ids, plantilla_id, out_dir, self._on_preview_ready)

    def _on_preview_ready(self, frentes_pdf: str, vueltas_pdf: str) -> None:
        """Abre el diálogo de vista previa con los PDFs ya generados."""
        from pathlib import Path
        from credencializacion.ui.dialogs.preview_dialog import PreviewDialog

        self.set_status("✅ Vista previa generada", "success", toast=False)
        dlg = PreviewDialog(
            frentes_pdf=Path(frentes_pdf),
            vueltas_pdf=Path(vueltas_pdf),
            parent=self,
        )
        dlg.exec()

    # ── Render en segundo plano (compartido) ───────────────────────

    def _start_render(self, ids, plantilla_id, out_dir, on_done) -> None:
        """Lanza un ``QueueRenderWorker`` y enruta sus señales.

        ``on_done`` se invoca en el hilo principal con (frentes_pdf, vueltas_pdf)
        cuando el render termina correctamente.
        """
        self._render_on_done = on_done
        self._render_worker = QueueRenderWorker(ids, plantilla_id, out_dir)
        self._render_worker.progress.connect(
            lambda m: self.set_status(m, "info", toast=False)
        )
        self._render_worker.finished_ok.connect(self._on_render_ok)
        self._render_worker.failed.connect(self._on_render_failed)
        self._render_worker.finished.connect(self._cleanup_render_worker)
        self._render_worker.start()

    @Slot(str, str)
    def _on_render_ok(self, frentes_pdf: str, vueltas_pdf: str) -> None:
        cb = getattr(self, "_render_on_done", None)
        if cb is not None:
            cb(frentes_pdf, vueltas_pdf)

    @Slot(str)
    def _on_render_failed(self, message: str) -> None:
        self.set_status(f"❌ Error al generar PDFs: {message}", "error")

    def _cleanup_render_worker(self) -> None:
        self._render_worker = None
        self._render_on_done = None

    def _on_print_front(self) -> None:
        """Envía la cola en memoria al Centro de Impresión (genera y guarda PDFs)."""
        self._send_queue_to_print_center()

    def _add_single_to_queue(self, reg_id: int) -> None:
        """Agrega un único registro a la cola visual."""
        template_id = self._combo_templates.currentData()
        if not template_id:
            self.set_status("⚠️ Selecciona una plantilla primero", "warning")
            return

        reg = next((r for r in self._all_records if r.id == reg_id), None)
        if reg:
            # Obtener foto del caché si existe
            url = reg.photo_path
            pixmap = self._raw_photo_cache.get(url) if url else None
            self._queue_panel.add_to_queue(reg, pixmap)

    def _add_selected_to_queue(self) -> None:
        """Agrega los registros seleccionados a la cola visual."""
        template_id = self._combo_templates.currentData()
        if not template_id:
            self.set_status("⚠️ Selecciona una plantilla primero", "warning")
            return

        selected_ids = self.get_selected_records()
        if not selected_ids:
            self.set_status("⚠️ Selecciona al menos un registro", "warning")
            return

        added = 0
        for reg_id in selected_ids:
            reg = next((r for r in self._all_records if r.id == reg_id), None)
            if reg:
                url = reg.photo_path
                pixmap = self._raw_photo_cache.get(url) if url else None
                self._queue_panel.add_to_queue(reg, pixmap)
                added += 1

        if added > 0:
            self.set_status(f"✅ {added} registros agregados a la cola", "success")

    def _send_queue_to_print_center(self) -> None:
        """Crea la cola en BD y genera/guarda sus PDFs sin bloquear la app.

        Crea la ``ColaImpresion`` y sus ítems, luego renderiza en segundo plano
        los PDFs de frentes y vueltas (2 diseños por hoja) en una carpeta estable
        (build-safe) y guarda sus rutas en la cola. Al terminar, limpia la cola
        visual y refresca el Centro de Impresión.
        """
        queue_records = self._queue_panel.get_queue()
        if not queue_records:
            self.set_status("⚠️ La cola de impresión está vacía", "warning")
            return

        plantilla_id = self._combo_templates.currentData()
        if not plantilla_id:
            self.set_status("⚠️ Selecciona una plantilla", "warning")
            return

        if getattr(self, "_render_worker", None) is not None:
            self.set_status("⏳ Ya hay una generación en curso...", "warning", toast=False)
            return

        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion, ItemCola

        ids = [r.id for r in queue_records]
        try:
            with DatabaseSession() as session:
                plantilla_nombre = self._combo_templates.currentText()
                cola = ColaImpresion(
                    nombre=f"{plantilla_nombre} — {len(queue_records)} registros",
                    total_registros=len(queue_records),
                )
                session.add(cola)
                session.flush()

                # Todos los ítems usan el diseño seleccionado. El multiplantillaje
                # solo intercambia la imagen de fondo por lado, resuelto al
                # renderizar consultando la ConfiguracionLado del diseño.
                for orden, reg in enumerate(queue_records, start=1):
                    session.add(
                        ItemCola(
                            cola_id=cola.id,
                            registro_id=reg.id,
                            plantilla_id=plantilla_id,
                            orden=orden,
                        )
                    )
                cola.total_registros = len(queue_records)
                session.commit()
                cola_id = cola.id
        except Exception as e:
            self.set_status(f"❌ Error al guardar cola: {e}", "error")
            return

        from credencializacion.utils.paths import get_cola_pdf_dir

        out_dir = str(get_cola_pdf_dir(cola_id))
        self.set_status("📤 Enviando al Centro de Impresión...", "info", toast=False)

        # Marcar credenciales como 'En impresión' en la API (en segundo plano).
        first_cliente_id = getattr(queue_records[0], "cliente_id", None)
        student_ids = self._collect_student_ids(queue_records)
        if student_ids and first_cliente_id:
            self._start_bulk_mark(first_cliente_id, "printing", student_ids)

        self._start_render(
            ids,
            plantilla_id,
            out_dir,
            lambda f, v: self._on_queue_pdfs_ready(cola_id, f, v),
        )

    @staticmethod
    def _collect_student_ids(registros) -> list[int]:
        """Extrae los ``student_id`` (id del API) de una lista de registros."""
        ids: list[int] = []
        for reg in registros:
            sid = reg.get_dato("student_id", None) if hasattr(reg, "get_dato") else None
            if sid in (None, ""):
                continue
            try:
                ids.append(int(sid))
            except (TypeError, ValueError):
                continue
        return ids

    def _client_api_credentials(self, cliente_id: int) -> tuple[str, str]:
        """Devuelve (base_url, api_key) del Cliente, con fallback a constantes."""
        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Cliente

        base_url, api_key = _API_BASE_URL, _API_KEY
        try:
            with get_session() as session:
                cliente = session.query(Cliente).get(cliente_id)
                if cliente is not None:
                    base_url = cliente.api_base_url or base_url
                    api_key = cliente.api_key or api_key
        except Exception:  # noqa: BLE001
            pass
        return base_url, api_key

    def _start_bulk_mark(
        self, cliente_id: int, action: str, student_ids: list[int]
    ) -> None:
        """Lanza un ``BulkMarkWorker`` para marcar estatus sin bloquear la UI."""
        from credencializacion.ui.status_worker import BulkMarkWorker

        base_url, api_key = self._client_api_credentials(cliente_id)
        worker = BulkMarkWorker(base_url, api_key, action, student_ids)
        self._mark_workers.append(worker)

        def _on_done(success: bool, message: str, updated: int) -> None:
            if success:
                self.set_status(
                    f"🔔 Estatus actualizado: {updated} credenciales", "info", toast=False
                )
            else:
                self.set_status(
                    f"⚠️ No se pudo actualizar el estatus en la API: {message}",
                    "warning",
                )
            if worker in self._mark_workers:
                self._mark_workers.remove(worker)

        worker.done.connect(_on_done)
        worker.start()

    def _on_queue_pdfs_ready(
        self, cola_id: int, frentes_pdf: str, vueltas_pdf: str
    ) -> None:
        """Guarda las rutas de PDF en la cola y refresca el Centro de Impresión."""
        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion

        try:
            with DatabaseSession() as session:
                cola = session.query(ColaImpresion).get(cola_id)
                if cola is not None:
                    cola.pdf_frente_path = frentes_pdf
                    cola.pdf_vuelta_path = vueltas_pdf
                    session.commit()
        except Exception as e:
            self.set_status(f"❌ Error al guardar PDFs de la cola: {e}", "error")
            return

        self.set_status("✅ Cola enviada al Centro de Impresión", "success")
        self._queue_panel.clear_queue()
        self.add_to_queue_requested.emit()

    def _on_search_changed(self, text: str) -> None:
        """Filtra registros por texto de búsqueda en cualquier campo."""
        self._apply_filters()

    @staticmethod
    def _display_status(reg: "Registro") -> str:
        """Estado visible de la credencial (credential_display_status del API).

        Si el registro no trae el campo, cae a una heurística equivalente.
        """
        val = (reg.get_dato("credential_display_status", "") or "").strip()
        if val:
            return val
        if not reg.photo_path:
            return "sin_fotografia"
        if reg.credential_status == "ready":
            return "ready"
        return "pending"

    def _apply_status_filter(self, status: str | None) -> None:
        """Aplica un filtro de estado y actualiza las pills."""
        self._active_status_filter = status
        # Actualizar estado checked de las pills
        self._pill_all.setChecked(status is None)
        self._pill_ready.setChecked(status == "ready")
        self._pill_no_photo.setChecked(status == "sin_fotografia")
        self._pill_no_form.setChecked(status == "sin_formulario")
        self._pill_pending.setChecked(status == "pending")
        self._apply_filters()

    def _apply_filters(self) -> None:
        """Aplica búsqueda de texto + filtro de estado combinados.

        Soporta búsqueda compuesta grado+grupo: si el texto coincide con
        un patrón como '1a', '3B', '2 A', filtra grado=1 AND grupo=A.
        Si no coincide con el patrón, realiza búsqueda general.
        """
        if not hasattr(self, '_all_records') or not self._all_records:
            return

        records = list(self._all_records)

        # Filtro de estado por credential_display_status.
        status = self._active_status_filter
        if status:
            records = [r for r in records if self._display_status(r) == status]

        # Filtro de texto
        query = self._search_input.text().strip().lower()
        if query:
            # Intentar patrón compuesto grado+grupo (ej: "1a", "3B", "2 A")
            import re
            match = re.match(r'^(\d+)\s*([a-zA-Z])$', query.strip())
            if match:
                grado_q = match.group(1)
                grupo_q = match.group(2).upper()
                records = [
                    r for r in records
                    if str(r.get_dato("grado", "")).strip() == grado_q
                    and str(r.get_dato("grupo", "")).strip().upper() == grupo_q
                ]
            else:
                def matches(rec: "Registro") -> bool:
                    searchable = " ".join(
                        str(v) for v in [
                            rec.nombre_completo,
                            rec.enrollment_code,
                            rec.get_dato("grado", ""),
                            rec.get_dato("grupo", ""),
                            rec.get_dato("turno", ""),
                            rec.credential_status,
                        ]
                    ).lower()
                    return query in searchable
                records = [r for r in records if matches(r)]

        if not self._active_status_filter and not query:
            self._filtered_records = None
            self._lbl_filter_count.setVisible(False)
        else:
            self._filtered_records = records
            self._lbl_filter_count.setText(f"🔍 {len(records)} encontrados")
            self._lbl_filter_count.setVisible(True)
        self._current_page = 1
        self._refresh_page()

    def _update_status_counters(self) -> None:
        """Actualiza las numeralias con los conteos de la data actual."""
        if not hasattr(self, '_all_records') or not self._all_records:
            self._pill_all.setText("📋 Todos: 0")
            self._pill_ready.setText("✅ Listos: 0")
            self._pill_no_photo.setText("📷 Sin foto: 0")
            self._pill_no_form.setText("📋 Sin formulario: 0")
            self._pill_pending.setText("📝 Pendientes: 0")
            return

        total = len(self._all_records)
        estados = [self._display_status(r) for r in self._all_records]
        ready = sum(1 for e in estados if e == "ready")
        no_photo = sum(1 for e in estados if e == "sin_fotografia")
        no_form = sum(1 for e in estados if e == "sin_formulario")
        pending = sum(1 for e in estados if e == "pending")

        self._pill_all.setText(f"📋 Todos: {total}")
        self._pill_ready.setText(f"✅ Listos: {ready}")
        self._pill_no_photo.setText(f"📷 Sin foto: {no_photo}")
        self._pill_no_form.setText(f"📋 Sin formulario: {no_form}")
        self._pill_pending.setText(f"📝 Pendientes: {pending}")

    def _load_client_templates(self, cliente_id: int) -> None:
        """Carga las plantillas del cliente seleccionado en el combo de plantillas.

        Args:
            cliente_id: ID del cliente en la BD local.
        """
        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Plantilla

        self._combo_templates.clear()
        self._combo_templates.addItem("Seleccionar plantilla...")

        with get_session() as session:
            plantillas = (
                session.query(Plantilla)
                .filter_by(cliente_id=cliente_id)
                .order_by(Plantilla.nombre)
                .all()
            )
            for p in plantillas:
                self._combo_templates.addItem(
                    f"{p.nombre} ({p.tipo})", p.id
                )

        if self._combo_templates.count() > 1:
            self.set_status(
                f"📋 {self._combo_templates.count() - 1} plantilla(s) disponible(s).",
                "info",
            )

    def set_status(self, message: str, level: str = "info", toast: bool = True) -> None:
        """Actualiza el footer de estado con un mensaje y, opcionalmente, muestra un toast.

        Args:
            message: Texto a mostrar.
            level: 'info', 'success', 'error', 'warning', 'sync'.
            toast: Si es True (por defecto) muestra una notificación toast.
                   Usar False para pasos intermedios de un flujo de carga: el
                   progreso se refleja solo en el footer y se reserva el toast
                   para el resultado final.
        """
        from PySide6.QtCore import QCoreApplication, QTimer
        from credencializacion.ui.widgets.toast import ToastManager
        colors = {
            "info": ("#1E293B", "#94A3B8"),
            "success": ("#052E16", "#4ADE80"),
            "error": ("#450A0A", "#FCA5A5"),
            "warning": ("#451A03", "#FCD34D"),
            "sync": ("#EFF6FF", "#2563EB"), # Background azul muy claro, texto azul vibrante
        }
        bg, fg = colors.get(level, colors["info"])
        self._status_bar.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                font-family: 'Inter', sans-serif;
                font-size: 12px;
                padding: 0 12px;
                border: none;
            }}
        """)
        self._status_bar.setText(message)
        QCoreApplication.processEvents()
        # Toast notification (solo resultado final)
        if toast:
            ToastManager.instance().show_toast(message, level)

    def _on_sync_api(self) -> None:
        """Sincroniza escuelas y alumnos desde la API y los guarda en la BD."""
        from credencializacion.adapters.miescuela import MiEscuelaAdapter
        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import Cliente, Registro
        from datetime import datetime

        BASE_URL = "https://app.miescuela.net"
        API_KEY = "7c9e6679-7425-40de-944b-e07fc1f90ae7"

        self.set_status("⏳ Sincronizando escuelas con MiEscuela.net...", "info", toast=False)

        try:
            adapter = MiEscuelaAdapter(base_url=BASE_URL, api_key=API_KEY)

            # ── 1. Obtener lista de escuelas ───────────────────────────
            try:
                schools = adapter.fetch_schools()
            except ConnectionError:
                self.set_status("⚠ Endpoint /schools no disponible, usando fallback...", "warning", toast=False)
                records = adapter.fetch_records(school_id=1, status="all")
                if records:
                    school_name = records[0].get("escuela", "Escuela 1")
                    schools = [{
                        "id": 1,
                        "name": school_name,
                        "cct": "",
                        "school_level": records[0].get("nivel_escolar", ""),
                        "status": "active",
                        "address": "",
                        "logo_url": records[0].get("logo_escuela", ""),
                        "total_students": len(records),
                    }]
                else:
                    schools = []

            if not schools:
                self.set_status("⚠ No se encontraron escuelas asociadas a esta clave API.", "warning")
                return

            self.set_status(f"💾 Guardando {len(schools)} escuelas...", "info", toast=False)

            # ── 2. Upsert de escuelas en `clientes` ────────────────────
            cliente_map: dict[int, int] = {}  # api_id → local cliente.id
            with DatabaseSession() as session:
                for school_data in schools:
                    api_id = school_data.get("id")
                    existing = session.query(Cliente).filter_by(
                        school_api_id=api_id
                    ).first()

                    if existing:
                        existing.nombre = school_data.get("name", existing.nombre)
                        existing.cct = school_data.get("cct")
                        existing.school_level = school_data.get("school_level")
                        existing.address = school_data.get("address")
                        existing.logo_path = school_data.get("logo_url")
                        existing.total_students = school_data.get("total_students")
                        session.flush()
                        cliente_map[api_id] = existing.id
                    else:
                        nuevo = Cliente(
                            nombre=school_data.get("name", "Sin nombre"),
                            tipo="escuela",
                            api_key=API_KEY,
                            api_base_url=BASE_URL,
                            school_api_id=api_id,
                            cct=school_data.get("cct"),
                            school_level=school_data.get("school_level"),
                            address=school_data.get("address"),
                            logo_path=school_data.get("logo_url"),
                            total_students=school_data.get("total_students"),
                        )
                        session.add(nuevo)
                        session.flush()
                        cliente_map[api_id] = nuevo.id

            # ── 3. Para cada escuela: fetch alumnos y hacer upsert ─────
            total_alumnos = 0
            for school_data in schools:
                api_id = school_data.get("id")
                local_cliente_id = cliente_map.get(api_id)
                if not local_cliente_id:
                    continue

                self.set_status(
                    f"⬇ Descargando alumnos de {school_data.get('name', '')}...", "info", toast=False
                )
                try:
                    raw_records = adapter.fetch_records(school_id=api_id, status="all")
                except Exception:
                    continue

                if not raw_records:
                    continue

                # Atributos conocidos = unión de claves ESCALARES en todos los
                # registros (student_record es dinámico por escuela, así que no
                # basta con la primera fila). Se excluyen listas/dicts.
                from credencializacion.utils.images import detect_image_attributes

                known_attrs: list[str] = []
                _seen_attr: set[str] = set()
                for _rec in raw_records:
                    if not isinstance(_rec, dict):
                        continue
                    for _k, _v in _rec.items():
                        if _k in _seen_attr or isinstance(_v, (list, dict)):
                            continue
                        _seen_attr.add(_k)
                        known_attrs.append(_k)
                # Atributos de imagen (foto alumno, logo, fotos de autorizados…).
                image_attrs = detect_image_attributes(raw_records)

                with DatabaseSession() as session:
                    # Upsert de registros: clave = (cliente_id, enrollment_code)
                    for rec_data in raw_records:
                        enrollment = rec_data.get("enrollment_code") or rec_data.get("matricula", "")
                        existing_reg = session.query(Registro).filter_by(
                            cliente_id=local_cliente_id,
                            enrollment_code=enrollment,
                        ).first()

                        if existing_reg:
                            existing_reg.datos = rec_data
                            existing_reg.credential_status = rec_data.get("estado_credencial")
                            existing_reg.qr_data = rec_data.get("qr_data") or rec_data.get("photo_url", "")
                            existing_reg.photo_path = rec_data.get("photo_url", "")
                        else:
                            nuevo_reg = Registro(
                                cliente_id=local_cliente_id,
                                datos=rec_data,
                                enrollment_code=enrollment,
                                credential_status=rec_data.get("estado_credencial"),
                                qr_data=rec_data.get("qr_data") or rec_data.get("photo_url", ""),
                                photo_path=rec_data.get("photo_url", ""),
                                estado_impresion="pendiente",
                            )
                            session.add(nuevo_reg)

                    # Guardar known_attributes en cliente.config
                    cliente_obj = session.query(Cliente).get(local_cliente_id)
                    if cliente_obj:
                        cfg = dict(cliente_obj.config or {})
                        cfg["known_attributes"] = known_attrs
                        cfg["image_attributes"] = image_attrs
                        cfg["last_sync"] = datetime.now().isoformat()
                        cliente_obj.config = cfg

                total_alumnos += len(raw_records)


            self._load_clients_combo()  # Refrescar combo de clientes con los datos sincronizados

            self.set_status(
                f"✅ Sincronización completada — {len(schools)} escuelas, {total_alumnos} alumnos guardados.",
                "success",
            )

        except Exception as e:
            self.set_status(f"❌ Error de sincronización: {str(e)}", "error")


    def _load_clients_combo(self) -> None:
        """Carga las escuelas desde la BD al combobox de clientes."""
        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Cliente

        self._combo_clients.blockSignals(True)
        self._combo_clients.clear()

        session = get_session()
        clientes = session.query(Cliente).filter(
            Cliente.school_api_id.isnot(None)
        ).order_by(Cliente.nombre).all()

        for cliente in clientes:
            label = cliente.nombre
            if cliente.total_students:
                label += f" ({cliente.total_students} alumnos)"
            self._combo_clients.addItem(label, cliente.school_api_id)

        session.close()
        self._combo_clients.setCurrentIndex(-1)
        self._combo_clients.blockSignals(False)

    def _on_client_selected(self, index: int) -> None:
        """Al seleccionar una escuela, muestra sus alumnos desde la BD local."""
        school_id = self._combo_clients.itemData(index)
        if school_id is None:
            self._table.setRowCount(0)
            self._lbl_page_info.setText("Mostrando 0 de 0 registros")
            self._combo_templates.clear()
            self._combo_templates.addItem("Plantillas")
            return

        school_name = self._combo_clients.currentText()

        # ── Intentar cargar desde la BD local ──────────────────────────────
        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Cliente, Registro

        with get_session() as session:
            cliente = session.query(Cliente).filter_by(school_api_id=school_id).first()
            if cliente:
                db_registros = (
                    session.query(Registro)
                    .filter_by(cliente_id=cliente.id)
                    .all()
                )
                if db_registros:
                    # Desvincular de la sesión para poder usarlos en la UI después de cerrar la sesión
                    session.expunge_all()
                    
                    # Usar el método oficial para cargar registros reales
                    self.load_records(db_registros)
                    self._load_client_templates(cliente.id)
                    self.set_status(
                        f"✅ {len(db_registros)} alumnos de {school_name} (datos locales).",
                        "success",
                    )
                    return

        # ── Fallback: cargar desde la API si no hay datos locales ──────────
        from credencializacion.adapters.miescuela import MiEscuelaAdapter

        BASE_URL = "https://app.miescuela.net"
        API_KEY = "7c9e6679-7425-40de-944b-e07fc1f90ae7"

        self.set_status(f"⏳ Descargando alumnos de {school_name}...", "info")

        try:
            adapter = MiEscuelaAdapter(base_url=BASE_URL, api_key=API_KEY)
            api_records = adapter.fetch_records(school_id=school_id, status="all")

            # Guardar en BD para que tengan ID y puedan agregarse a la cola
            from credencializacion.db.engine import DatabaseSession
            from credencializacion.db.models import Registro, Cliente

            with DatabaseSession() as session:
                cliente = session.query(Cliente).filter_by(school_api_id=school_id).first()
                if not cliente:
                    cliente = Cliente(school_api_id=school_id, nombre=school_name)
                    session.add(cliente)
                    session.flush()

                for rec in api_records:
                    matricula = rec.get("matricula", "")
                    reg = session.query(Registro).filter_by(
                        cliente_id=cliente.id, 
                        enrollment_code=matricula
                    ).first()
                    
                    if not reg:
                        reg = Registro(cliente_id=cliente.id, enrollment_code=matricula)
                        session.add(reg)
                    
                    reg.datos = rec
                    reg.credential_status = rec.get("estado_credencial", "pending")
                    reg.photo_path = rec.get("photo_url", "")
                
                session.commit()
                # Recuperar como modelos Registro reales
                records = session.query(Registro).filter_by(cliente_id=cliente.id).all()
                session.expunge_all()

            # Usar el método oficial para cargar registros
            self.load_records(records)
            self._load_client_templates(cliente.id)

            self.set_status(
                f"✅ {len(records)} alumnos cargados de {school_name}.",
                "success",
            )

        except Exception as e:
            self.set_status(f"❌ Error al cargar alumnos: {str(e)}", "error")


    def _refresh_page(self) -> None:
        """Actualiza la tabla con los registros de la página actual."""
        source = self._filtered_records if self._filtered_records is not None else self._all_records
        self._total_records = len(source)
        start = (self._current_page - 1) * self.PAGE_SIZE
        end = min(start + self.PAGE_SIZE, self._total_records)
        page_records = source[start:end]

        self._table.set_records(page_records)

        # Actualizar label de conteo
        if self._total_records > 0:
            self._lbl_page_info.setText(
                f"Mostrando {start + 1}-{end} de {self._total_records} registros"
            )
        else:
            self._lbl_page_info.setText("Sin registros")

        # Estado de botones de navegación
        self._btn_prev.setEnabled(self._current_page > 1)
        self._btn_next.setEnabled(end < self._total_records)

        # Iniciar descarga de fotos asíncrona
        self._download_visible_photos(page_records)

    def _prev_page(self) -> None:
        """Navega a la página anterior."""
        if self._current_page > 1:
            self._current_page -= 1
            self._refresh_page()

    def _next_page(self) -> None:
        """Navega a la siguiente página."""
        max_page = max(1, (self._total_records - 1) // self.PAGE_SIZE + 1)
        if self._current_page < max_page:
            self._current_page += 1
            self._refresh_page()

    def _filter_records(self, text: str) -> None:
        """Filtra registros y vuelve a la página 1."""
        text = text.lower().strip()
        if not text and not self._active_status_filter:
            self._filtered_records = None
            self._total_records = len(self._all_records)
        else:
            self._filtered_records = []
            for rec in self._all_records:
                match_text = True
                if text:
                    # Validar matrícula, nombre, grado o grupo
                    searchable = f"{rec.enrollment_code} {rec.nombre_completo} {rec.get_dato('grado', '')} {rec.get_dato('grupo', '')}".lower()
                    match_text = text in searchable
                
                match_status = True
                if self._active_status_filter:
                    estado = rec.credential_status or "pending"
                    if not rec.photo_path and self._active_status_filter == "no_photo":
                        pass
                    elif self._active_status_filter == "no_photo":
                        match_status = False
                    else:
                        match_status = (estado == self._active_status_filter)

                if match_text and match_status:
                    self._filtered_records.append(rec)
            
            self._total_records = len(self._filtered_records)

        self._current_page = 1
        self._refresh_page()

    def _filter_by_status(self, status: str | None) -> None:
        """Filtra los registros por estado de credencial (pills)."""
        self._active_status_filter = status
        self._filter_records(self._search_input.text())

    # ── Descarga async de fotos ────────────────────────────────────

    @staticmethod
    def _make_placeholder(size: int = 32) -> QPixmap:
        """Crea un pixmap circular gris como placeholder."""
        from credencializacion.ui.widgets.record_table import BORDER as _BORDER
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(_BORDER))
        result = QPixmap(size, size)
        result.fill(QColor(0, 0, 0, 0))
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return result

    @staticmethod
    def _make_circular(source: QPixmap, size: int = 32) -> QPixmap:
        """Recorta un pixmap en forma circular."""
        scaled = source.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        if scaled.width() > size or scaled.height() > size:
            x = (scaled.width() - size) // 2
            y = (scaled.height() - size) // 2
            scaled = scaled.copy(x, y, size, size)

        result = QPixmap(size, size)
        result.fill(QColor(0, 0, 0, 0))
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        return result

    def _download_visible_photos(self, page_records: list["Registro"]) -> None:
        """Inicia descarga async de fotos de la página visible o aplica las cacheadas."""
        for row, rec in enumerate(page_records):
            url = rec.photo_path
            if not url or not url.startswith("http"):
                # Si ya es un path local, RecordTable ya lo maneja
                continue

            if url in self._photo_cache:
                # Aplicar foto desde la caché usando ID real
                self._table.set_photo_by_id(rec.id, self._photo_cache[url])
                continue

            request = QNetworkRequest(QUrl(url))
            reply = self._net_manager.get(request)
            reply.setProperty("row", row)
            reply.setProperty("photo_url", url)
            reply.setProperty("reg_id", rec.id)
            reply.finished.connect(lambda r=reply: self._on_photo_downloaded(r))

    def _on_photo_downloaded(self, reply: "QNetworkReply") -> None:
        """Callback cuando una foto termina de descargarse."""
        row = reply.property("row")
        url = reply.property("photo_url")
        reg_id = reply.property("reg_id")

        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            pixmap.loadFromData(data.data())

            if not pixmap.isNull():
                self._raw_photo_cache[url] = pixmap
                circular = self._make_circular(pixmap, 32)
                self._photo_cache[url] = circular

                # Actualizar el ícono en la tabla usando el ID (por si se reordenó)
                self._table.set_photo_by_id(reg_id, circular)

        reply.deleteLater()

