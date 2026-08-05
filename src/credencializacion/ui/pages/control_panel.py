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
from credencializacion.ui.render_worker import QueueRenderWorker

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


class SyncWorker(QThread):
    progress = Signal(str, str, bool)
    finished_ok = Signal(int, int, dict)  # escuelas, alumnos, reporte de depuración
    failed = Signal(str)

    def run(self) -> None:
        from credencializacion.adapters.miescuela import MiEscuelaAdapter
        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import Cliente, Registro
        from datetime import datetime

        BASE_URL = "https://app.miescuela.net"
        API_KEY = "7c9e6679-7425-40de-944b-e07fc1f90ae7"

        self.progress.emit("⏳ Sincronizando escuelas con MiEscuela.net...", "info", False)

        # Reporte de depuración acumulado durante la corrida.
        total_depurados = 0
        colas_afectadas: list[str] = []
        escuelas_faltantes: list[str] = []
        # Solo se comparan escuelas si /schools respondió de verdad (el
        # fallback construye una escuela artificial y daría falsos faltantes).
        schools_confiables = True

        try:
            adapter = MiEscuelaAdapter(base_url=BASE_URL, api_key=API_KEY)

            # ── 1. Obtener lista de escuelas ───────────────────────────
            try:
                schools = adapter.fetch_schools()
            except ConnectionError:
                self.progress.emit("⚠ Endpoint /schools no disponible, usando fallback...", "warning", False)
                schools_confiables = False
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
                self.progress.emit("⚠ No se encontraron escuelas asociadas a esta clave API.", "warning", True)
                return

            self.progress.emit(f"💾 Guardando {len(schools)} escuelas...", "info", False)

            # ── 2. Upsert de escuelas en `clientes` ────────────────────
            cliente_map: dict[int, int] = {}
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

                self.progress.emit(
                    f"⬇ Descargando alumnos de {school_data.get('name', '')}...", "info", False
                )
                try:
                    raw_records = adapter.fetch_records(school_id=api_id, status="all")
                except Exception:
                    continue

                if not raw_records:
                    continue

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
                        
                image_attrs = detect_image_attributes(raw_records)

                with DatabaseSession() as session:
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

                    cliente_obj = session.query(Cliente).get(local_cliente_id)
                    if cliente_obj:
                        cfg = dict(cliente_obj.config or {})
                        cfg["known_attributes"] = known_attrs
                        cfg["image_attributes"] = image_attrs
                        cfg["last_sync"] = datetime.now().isoformat()
                        cliente_obj.config = cfg

                    # ── Depuración: registros borrados en la plataforma ──
                    # El API devuelve el padrón completo de la escuela, así que
                    # todo registro local que ya no venga en la respuesta fue
                    # eliminado en app.miescuela.net. Solo se llega aquí si la
                    # descarga tuvo datos (guard `if not raw_records` arriba),
                    # y todo ocurre en la misma transacción que el upsert.
                    from credencializacion.services.sync_registros import (
                        purge_stale_records,
                    )
                    depurados, colas = purge_stale_records(
                        session, local_cliente_id, raw_records
                    )
                    total_depurados += depurados
                    for nombre_cola in colas:
                        if nombre_cola not in colas_afectadas:
                            colas_afectadas.append(nombre_cola)

                total_alumnos += len(raw_records)

            # ── 4. Reportar escuelas que ya no existen en la plataforma ──
            # No se eliminan localmente (arrastrarían en cascada sus
            # plantillas y colas); solo se avisa para depuración manual.
            if schools_confiables:
                api_school_ids = {s.get("id") for s in schools}
                with DatabaseSession() as session:
                    faltantes = (
                        session.query(Cliente)
                        .filter(
                            Cliente.school_api_id.isnot(None),
                            Cliente.school_api_id.notin_(api_school_ids),
                        )
                        .order_by(Cliente.nombre)
                        .all()
                    )
                    escuelas_faltantes = [c.nombre for c in faltantes]

            reporte = {
                "depurados": total_depurados,
                "colas_afectadas": colas_afectadas,
                "escuelas_faltantes": escuelas_faltantes,
            }
            self.finished_ok.emit(len(schools), total_alumnos, reporte)

        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Error en sincronización API: %s", e)
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
        # Footer de dos segmentos (mensaje | progreso de fotos) y prefetch.
        self._main_status: str = ""
        self._photo_status: str = ""
        self._prefetch_worker = None
        self._setup_ui()
        self._connect_signals()
        self._render_worker = None
        self._render_on_done = None
        self._mark_workers = []
        
        # Cargar datos locales al iniciar
        self._load_clients_combo()

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

        self._pill_with_photo = QPushButton("📸 Con foto: 0")
        self._pill_with_photo.setCheckable(True)
        self._pill_with_photo.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pill_with_photo.setStyleSheet(pill_base.format(
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

        self._pill_with_form = QPushButton("📝 Con formulario: 0")
        self._pill_with_form.setCheckable(True)
        self._pill_with_form.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pill_with_form.setStyleSheet(pill_base.format(
            bg="#EFF6FF", fg="#2563EB", border="#BFDBFE",
            hover_border="#2563EB", hover_bg="#DBEAFE",
            active_bg="#2563EB",
        ))

        self._pill_no_form = QPushButton("📋 Sin formulario: 0")
        self._pill_no_form.setCheckable(True)
        self._pill_no_form.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pill_no_form.setStyleSheet(pill_base.format(
            bg="#FFF7ED", fg="#EA580C", border="#FED7AA",
            hover_border="#EA580C", hover_bg="#FFEDD5",
            active_bg="#EA580C",
        ))

        self._pill_siblings = QPushButton("👨‍👩‍👦 Hermanos: 0")
        self._pill_siblings.setCheckable(True)
        self._pill_siblings.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pill_siblings.setToolTip(
            "Alumnos que comparten el correo del tutor con al menos otro alumno."
        )
        self._pill_siblings.setStyleSheet(pill_base.format(
            bg="#F5F3FF", fg="#7C3AED", border="#DDD6FE",
            hover_border="#7C3AED", hover_bg="#EDE9FE",
            active_bg="#7C3AED",
        ))

        # Naranja, el mismo de la fila marcada en la tabla: la pill y el
        # resaltado tienen que leerse como la misma señal.
        self._pill_incidencias = QPushButton("⚠ Incidencias: 0")
        self._pill_incidencias.setCheckable(True)
        self._pill_incidencias.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pill_incidencias.setToolTip(
            "Alumnos con datos que conviene revisar antes de imprimir: CURP que "
            "no concuerda con el nombre, CURP repetida o exceso de personas "
            "autorizadas."
        )
        self._pill_incidencias.setStyleSheet(pill_base.format(
            bg="#FFEDD5", fg="#9A3412", border="#FDBA74",
            hover_border="#C2410C", hover_bg="#FED7AA",
            active_bg="#C2410C",
        ))
        self._pill_incidencias.setVisible(False)  # solo si hay algo que revisar

        self._pill_all.clicked.connect(lambda: self._apply_status_filter(None))
        self._pill_with_photo.clicked.connect(lambda: self._apply_status_filter("con_foto"))
        self._pill_no_photo.clicked.connect(lambda: self._apply_status_filter("sin_foto"))
        self._pill_with_form.clicked.connect(lambda: self._apply_status_filter("con_formulario"))
        self._pill_no_form.clicked.connect(lambda: self._apply_status_filter("sin_formulario"))
        self._pill_siblings.clicked.connect(lambda: self._apply_status_filter("hermanos"))
        self._pill_incidencias.clicked.connect(
            lambda: self._apply_status_filter("incidencias")
        )

        row.addWidget(self._pill_all)
        row.addWidget(self._pill_with_photo)
        row.addWidget(self._pill_no_photo)
        row.addWidget(self._pill_with_form)
        row.addWidget(self._pill_no_form)
        row.addWidget(self._pill_siblings)
        row.addWidget(self._pill_incidencias)
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
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

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
        # Las incidencias se calculan una sola vez sobre el padrón completo,
        # no por página: la pill cuenta sobre todo el cliente, y "CURP
        # repetida" solo se puede detectar comparando registros entre sí.
        self._incidencias_lote = self._analizar_incidencias(records)
        self._update_status_counters()
        self._refresh_page()
        # Prefetch en segundo plano de TODAS las fotos del cliente a disco,
        # para que paginar sea instantáneo tras el llenado inicial.
        self._start_photo_prefetch(records)

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
        self._render_worker.omitidos.connect(self._on_render_omitidos)
        self._render_worker.finished.connect(self._cleanup_render_worker)
        self._render_worker.start()

    @Slot(dict)
    def _on_render_omitidos(self, reporte: dict) -> None:
        """Informa qué registros quedaron fuera del PDF y por qué."""
        sin_req = reporte.get("sin_requeridos") or []
        colapsados = reporte.get("hermanos_colapsados") or []

        if sin_req:
            detalle = "; ".join(
                f"{nombre} (falta: {', '.join(attrs)})" for nombre, attrs in sin_req[:5]
            )
            if len(sin_req) > 5:
                detalle += f" y {len(sin_req) - 5} más"
            self.set_status(
                f"⚠️ {len(sin_req)} registro(s) sin credencial por atributos "
                f"requeridos faltantes: {detalle}",
                "warning",
                toast=True,
            )

        if colapsados:
            self.set_status(
                f"ℹ️ {len(colapsados)} hermano(s) omitido(s): ya se incluyen en la "
                f"credencial de su familia ({', '.join(colapsados[:5])}"
                f"{' y más' if len(colapsados) > 5 else ''}).",
                "info",
                toast=True,
            )

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

    def _on_selection_changed(self) -> None:
        """Resume en el footer las incidencias de lo que está seleccionado.

        Solo escribe cuando hay algo que decir: con la selección vacía o sin
        incidencias entre lo seleccionado, no pisa el mensaje que el footer ya
        traía (resultado de una sincronización, por ejemplo).
        """
        from credencializacion.services.incidencias import resumir

        seleccionados = self._table.get_selected_ids()
        if not seleccionados:
            return

        hallazgos = [
            inc for reg_id in seleccionados
            for inc in self._table.incidencias_de(reg_id)
        ]
        if not hallazgos:
            if self._table.total_con_incidencias:
                self.set_status(
                    f"{len(seleccionados)} seleccionado(s) · sin incidencias "
                    f"({self._table.total_con_incidencias} en el padrón)",
                    "info", toast=False,
                )
            return

        afectados = sum(
            1 for reg_id in seleccionados if self._table.incidencias_de(reg_id)
        )
        self.set_status(
            f"⚠ {afectados} de {len(seleccionados)} seleccionado(s) requieren "
            f"revisión: {resumir(hallazgos)}",
            "warning", toast=False,
        )

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

    def _confirmar_incidencias(self, registros: list) -> bool:
        """Pide confirmación si la cola incluye registros con incidencias.

        Es el último punto donde el error todavía sale barato: después de aquí
        se generan los PDFs y se imprime. No bloquea —el operador puede tener
        razones para imprimir de todas formas— pero obliga a verlo.

        Returns:
            True si se puede continuar; False si el operador canceló.
        """
        from credencializacion.services.incidencias import resumir

        mapa = self._incidencias()
        if not mapa:
            return True

        afectados = [r for r in registros if r.id in mapa]
        if not afectados:
            return True

        hallazgos = [inc for r in afectados for inc in mapa[r.id]]
        detalle = "\n".join(
            f"• {r.nombre_completo or r.enrollment_code}: "
            + "; ".join(i.titulo for i in mapa[r.id])
            for r in afectados
        )

        dialogo = QMessageBox(self)
        dialogo.setIcon(QMessageBox.Icon.Warning)
        dialogo.setWindowTitle("Registros con incidencias")
        dialogo.setText(
            f"<b>{len(afectados)} de {len(registros)} credenciales de esta cola "
            "tienen datos que conviene revisar.</b>"
        )
        dialogo.setInformativeText(
            f"Se detectó: {resumir(hallazgos)}.\n\n"
            "Una CURP que no concuerda suele ser la de un hermano filtrada al "
            "expediente, así que la credencial saldría con el dato de otro "
            "alumno."
        )
        dialogo.setDetailedText(detalle)

        btn_imprimir = dialogo.addButton(
            "Imprimir de todas formas", QMessageBox.ButtonRole.DestructiveRole,
        )
        btn_revisar = dialogo.addButton(
            "Revisar primero", QMessageBox.ButtonRole.RejectRole,
        )
        dialogo.setDefaultButton(btn_revisar)
        dialogo.exec()

        if dialogo.clickedButton() is btn_imprimir:
            return True

        # "Revisar primero" deja el filtro puesto en las incidencias, para que
        # el operador caiga directamente en los registros que debe mirar.
        self._apply_status_filter("incidencias")
        self.set_status(
            f"⚠ {len(afectados)} registro(s) de la cola requieren revisión: "
            f"{resumir(hallazgos)}",
            "warning", toast=False,
        )
        return False

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

        if not self._confirmar_incidencias(queue_records):
            return

        if getattr(self, "_render_worker", None) is not None:
            self.set_status("⏳ Ya hay una generación en curso...", "warning", toast=False)
            return

        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion, ItemCola

        # Perfil de posición por defecto para la cola nueva (el primero
        # disponible). Luego puede regenerarse con otro perfil desde el
        # Centro de Impresión.
        from credencializacion.core.settings import AppSettings
        AppSettings.ensure_default_profile()
        perfiles = AppSettings.list_position_profiles()
        perfil_defecto = perfiles[0] if perfiles else None

        ids = [r.id for r in queue_records]
        try:
            with DatabaseSession() as session:
                plantilla_nombre = self._combo_templates.currentText()
                cola = ColaImpresion(
                    nombre=f"{plantilla_nombre} — {len(queue_records)} registros",
                    total_registros=len(queue_records),
                    perfil_posicion=perfil_defecto,
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
    def _has_photo(reg: "Registro") -> bool:
        """Indica si el registro tiene fotografía."""
        return bool(reg.photo_path)

    @staticmethod
    def _has_form(reg: "Registro") -> bool:
        """Indica si el alumno completó su formulario (``form_status`` del API).

        Si el registro no trae el campo (sincronizaciones viejas), se infiere
        del ``credential_display_status``: el backend reporta "sin_formulario"
        con prioridad sobre cualquier otro estado.
        """
        val = reg.get_dato("form_status", None)
        if val is not None:
            return bool(val)
        display = (reg.get_dato("credential_display_status", "") or "").strip()
        return display != "sin_formulario"

    def _sibling_groups(self) -> dict[str, list]:
        """Agrupa los registros cargados por familia (``tutor_email``).

        Los registros sin correo de tutor quedan fuera: agruparlos por cadena
        vacía convertiría a todos los alumnos sin tutor en una sola familia.
        """
        from credencializacion.services.print_rules import group_by_tutor

        return group_by_tutor(getattr(self, "_all_records", []) or [])

    def _has_siblings(self, reg: "Registro") -> bool:
        """Indica si el alumno comparte tutor con al menos otro alumno."""
        from credencializacion.services.print_rules import has_siblings

        return has_siblings(reg, self._sibling_groups())

    @staticmethod
    def _analizar_incidencias(records: list) -> dict:
        """Incidencias de integridad del padrón, por ``registro.id``.

        Un fallo del detector no debe dejar al operador sin ver su padrón: se
        devuelve vacío y la tabla se comporta como antes.
        """
        try:
            from credencializacion.services.incidencias import analizar_lote

            return analizar_lote(records)
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudieron analizar las incidencias: %s", exc)
            return {}

    def _incidencias(self) -> dict:
        """Mapa ``{registro_id: [Incidencia…]}`` del padrón cargado."""
        return getattr(self, "_incidencias_lote", {}) or {}

    def _tiene_incidencias(self, reg: "Registro") -> bool:
        return reg.id in self._incidencias()

    def _status_filter_predicate(self, status: str):
        """Devuelve el predicado de filtrado para una pill de estado."""
        if status == "hermanos":
            # El agrupado se calcula una sola vez para todo el filtrado, no
            # una vez por registro.
            from credencializacion.services.print_rules import has_siblings

            grupos = self._sibling_groups()
            return lambda r: has_siblings(r, grupos)

        return {
            "con_foto": self._has_photo,
            "sin_foto": lambda r: not self._has_photo(r),
            "con_formulario": self._has_form,
            "sin_formulario": lambda r: not self._has_form(r),
            "incidencias": self._tiene_incidencias,
        }.get(status)

    def _apply_status_filter(self, status: str | None) -> None:
        """Aplica un filtro de estado y actualiza las pills."""
        self._active_status_filter = status
        # Actualizar estado checked de las pills
        self._pill_all.setChecked(status is None)
        self._pill_with_photo.setChecked(status == "con_foto")
        self._pill_no_photo.setChecked(status == "sin_foto")
        self._pill_with_form.setChecked(status == "con_formulario")
        self._pill_no_form.setChecked(status == "sin_formulario")
        self._pill_siblings.setChecked(status == "hermanos")
        self._pill_incidencias.setChecked(status == "incidencias")
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

        # Filtro de estado (pills): foto/formulario según los datos del registro.
        status = self._active_status_filter
        if status:
            pred = self._status_filter_predicate(status)
            if pred is not None:
                records = [r for r in records if pred(r)]

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
                    # Los apellidos se incluyen explícitamente además de
                    # `nombre_completo`: según el origen de los datos vienen
                    # en `apellido` (API) o separados en paterno/materno
                    # (importación de archivo).
                    searchable = " ".join(
                        str(v) for v in [
                            rec.nombre_completo,
                            rec.get_dato("nombre", ""),
                            rec.get_dato("apellido", ""),
                            rec.get_dato("apellido_paterno", ""),
                            rec.get_dato("apellido_materno", ""),
                            rec.enrollment_code,
                            rec.get_dato("matricula", ""),
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
            self._pill_with_photo.setText("📸 Con foto: 0")
            self._pill_no_photo.setText("📷 Sin foto: 0")
            self._pill_with_form.setText("📝 Con formulario: 0")
            self._pill_no_form.setText("📋 Sin formulario: 0")
            self._pill_siblings.setText("👨‍👩‍👦 Hermanos: 0")
            self._pill_incidencias.setText("⚠ Incidencias: 0")
            self._pill_incidencias.setVisible(False)
            return

        from credencializacion.services.print_rules import has_siblings

        total = len(self._all_records)
        with_photo = sum(1 for r in self._all_records if self._has_photo(r))
        with_form = sum(1 for r in self._all_records if self._has_form(r))
        # Mismo criterio que el filtro, para que el número de la pill siempre
        # coincida con las filas que muestra la tabla.
        grupos = self._sibling_groups()
        with_siblings = sum(1 for r in self._all_records if has_siblings(r, grupos))

        self._pill_all.setText(f"📋 Todos: {total}")
        self._pill_with_photo.setText(f"📸 Con foto: {with_photo}")
        self._pill_no_photo.setText(f"📷 Sin foto: {total - with_photo}")
        self._pill_with_form.setText(f"📝 Con formulario: {with_form}")
        self._pill_no_form.setText(f"📋 Sin formulario: {total - with_form}")
        self._pill_siblings.setText(f"👨‍👩‍👦 Hermanos: {with_siblings}")

        # La pill de incidencias solo aparece cuando hay algo que revisar: un
        # "⚠ Incidencias: 0" permanente entrena a ignorar el aviso.
        con_incidencias = len(self._incidencias())
        self._pill_incidencias.setText(f"⚠ Incidencias: {con_incidencias}")
        self._pill_incidencias.setVisible(con_incidencias > 0)
        if not con_incidencias and self._active_status_filter == "incidencias":
            self._apply_status_filter(None)

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

    def reload_templates(self) -> None:
        """Recarga el combo de plantillas del cliente activo (p. ej. tras
        renombrar una plantilla en el editor), conservando la selección."""
        idx = self._combo_clients.currentIndex()
        if idx < 0:
            return
        item_data = self._combo_clients.itemData(idx)
        if item_data is None:
            return
        kind, value = item_data

        if kind == "empresa":
            cliente_id = value
        else:
            from credencializacion.db.engine import get_session
            from credencializacion.db.models import Cliente

            with get_session() as session:
                cliente = session.query(Cliente).filter_by(
                    school_api_id=value
                ).first()
                if cliente is None:
                    return
                cliente_id = cliente.id

        selected_tpl = self._combo_templates.currentData()
        self._load_client_templates(cliente_id)
        if selected_tpl is not None:
            i = self._combo_templates.findData(selected_tpl)
            if i >= 0:
                self._combo_templates.setCurrentIndex(i)

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
        # El footer tiene dos segmentos divididos por " | ": el mensaje
        # (transitorio) y el progreso de fotos (persistente). Una notificación
        # nueva solo reemplaza el mensaje, sin pisar el progreso de fotos.
        self._main_status = message
        self._render_footer()
        QCoreApplication.processEvents()
        # Toast notification (solo resultado final)
        if toast:
            ToastManager.instance().show_toast(message, level)

    def _render_footer(self) -> None:
        """Compone el footer: ``mensaje | progreso de fotos``."""
        main = getattr(self, "_main_status", "") or ""
        photo = getattr(self, "_photo_status", "") or ""
        if photo:
            self._status_bar.setText(f"{main}  |  {photo}" if main else photo)
        else:
            self._status_bar.setText(main)

    def _set_photo_status(self, text: str) -> None:
        """Actualiza solo el segmento de progreso de fotos del footer."""
        self._photo_status = text
        self._render_footer()

    # ── Prefetch de fotos en segundo plano ──────────────────────────

    def _start_photo_prefetch(self, records: list["Registro"]) -> None:
        """Descarga a disco todas las fotos http del cliente (sin bloquear).

        Reemplaza cualquier prefetch en curso (al cambiar de escuela). El
        progreso se muestra en el segmento de fotos del footer.
        """
        from credencializacion.ui.photo_prefetch import PhotoPrefetchWorker

        # Detener el prefetch anterior (otra escuela) y desconectar sus
        # señales para que, mientras se drena, no altere el footer.
        prev = getattr(self, "_prefetch_worker", None)
        if prev is not None:
            prev.stop()
            try:
                prev.progress.disconnect()
                prev.finished_ok.disconnect()
            except (RuntimeError, TypeError):
                pass

        urls = []
        vistos = set()
        for r in records:
            u = r.photo_path
            if u and u.startswith("http") and u not in vistos:
                vistos.add(u)
                urls.append(u)

        if not urls:
            self._set_photo_status("")
            return

        worker = PhotoPrefetchWorker(urls, self._photo_disk_path)
        worker.progress.connect(self._on_prefetch_progress)
        worker.finished_ok.connect(lambda w=worker: self._on_prefetch_done(w))
        self._prefetch_worker = worker
        worker.start()

    def _on_prefetch_progress(self, done: int, total: int) -> None:
        """Actualiza el segmento de fotos del footer con el avance."""
        self._set_photo_status(f"📷 Fotos: {done}/{total}")

    def _on_prefetch_done(self, worker) -> None:
        """Al terminar: aplica las fotos ya cacheadas a la página visible y
        limpia el segmento de progreso del footer."""
        # Solo el worker vigente limpia el estado (evita que uno viejo, ya
        # reemplazado, borre el progreso del actual).
        if worker is not getattr(self, "_prefetch_worker", None):
            return
        self._set_photo_status("")
        self._prefetch_worker = None
        # Refrescar la página actual: las fotos que faltaban ya están en disco.
        self._refresh_page()

    def _set_sync_enabled(self, enabled: bool) -> None:
        """Habilita/deshabilita el botón Sincronizar de la toolbar.

        El botón vive en ``MainWindow``, que inyecta su referencia como
        ``btn_sync_api`` al conectar señales; si el panel se usa sin esa
        referencia (tests, standalone), simplemente no hay botón que tocar.
        """
        btn = getattr(self, "btn_sync_api", None)
        if btn is not None:
            btn.setEnabled(enabled)

    def _on_sync_api(self) -> None:
        """Sincroniza escuelas y alumnos desde la API de MiEscuela (asíncrono)."""
        if getattr(self, "_sync_worker", None) is not None:
            self.set_status("⏳ Ya hay una sincronización en curso...", "warning", toast=False)
            return

        self._set_sync_enabled(False)
        self.set_status("Iniciando sincronización...", "info", toast=False)

        self._sync_worker = SyncWorker()
        self._sync_worker.progress.connect(self.set_status)
        self._sync_worker.finished_ok.connect(self._on_sync_finished)
        self._sync_worker.failed.connect(self._on_sync_failed)
        self._sync_worker.start()

    def _on_sync_finished(
        self, count_schools: int, count_students: int, reporte: dict
    ) -> None:
        self._set_sync_enabled(True)
        self._load_clients_combo()

        msg = f"✅ Sincronización completada — {count_schools} escuelas, {count_students} alumnos guardados."
        depurados = reporte.get("depurados", 0)
        if depurados:
            msg += f" 🧹 {depurados} registros depurados (borrados en la plataforma)."
        self.set_status(msg, "success", toast=True)

        colas = reporte.get("colas_afectadas") or []
        if colas:
            self.set_status(
                f"⚠️ La depuración quitó registros de estas colas: {', '.join(colas)}. "
                "Usa «Actualizar PDFs» en el Centro de Impresión para regenerarlas.",
                "warning",
                toast=True,
            )
            # Refrescar el Centro de Impresión con los conteos nuevos
            self.add_to_queue_requested.emit()

        faltantes = reporte.get("escuelas_faltantes") or []
        if faltantes:
            self.set_status(
                f"ℹ️ Escuelas que ya no están en la plataforma (se conservan localmente): "
                f"{', '.join(faltantes)}",
                "warning",
                toast=True,
            )

        self._sync_worker = None

    def _on_sync_failed(self, error_msg: str) -> None:
        self._set_sync_enabled(True)
        self.set_status(f"❌ Error de sincronización: {error_msg}", "error", toast=True)
        self._sync_worker = None

    def _on_sync_sheets(self) -> None:
        """Sincroniza el documento de Google Sheets configurado (asíncrono).

        Comparte el mismo guardián de "sincronización en curso" y el mismo
        botón que la sincronización de la API miescuela.net: solo puede
        haber una sincronización corriendo a la vez.
        """
        if getattr(self, "_sync_worker", None) is not None:
            self.set_status("⏳ Ya hay una sincronización en curso...", "warning", toast=False)
            return

        from credencializacion.core.settings import AppSettings
        from credencializacion.ui.sheets_sync_worker import SheetsSyncWorker

        credentials_path = AppSettings.get_sheets_credentials_path()
        document_name = AppSettings.get_sheets_document_name()
        if not credentials_path:
            self.set_status(
                "⚠️ Configura las credenciales de Google en Configuración → "
                "Sincronización con Google Sheets antes de sincronizar.",
                "warning",
                toast=True,
            )
            return

        self._set_sync_enabled(False)
        self.set_status(f"Iniciando sincronización de «{document_name}»...", "info", toast=False)

        self._sync_worker = SheetsSyncWorker(credentials_path, document_name)
        self._sync_worker.progress.connect(self.set_status)
        self._sync_worker.finished_ok.connect(self._on_sheets_sync_finished)
        self._sync_worker.failed.connect(self._on_sync_failed)
        self._sync_worker.start()

    def _on_sheets_sync_finished(
        self, count_clientes: int, count_registros: int, reporte: dict
    ) -> None:
        self._set_sync_enabled(True)
        self._load_clients_combo()

        msg = (
            f"✅ Sincronización de Google Sheets completada — "
            f"{count_clientes} clientes, {count_registros} registros guardados."
        )
        depurados = reporte.get("depurados", 0)
        if depurados:
            msg += f" 🧹 {depurados} registros depurados (borrados en el documento)."
        self.set_status(msg, "success", toast=True)

        colas = reporte.get("colas_afectadas") or []
        if colas:
            self.set_status(
                f"⚠️ La depuración quitó registros de estas colas: {', '.join(colas)}. "
                "Usa «Actualizar PDFs» en el Centro de Impresión para regenerarlas.",
                "warning",
                toast=True,
            )
            self.add_to_queue_requested.emit()

        sin_atributos = reporte.get("sin_atributos") or []
        if sin_atributos:
            self.set_status(
                f"ℹ️ Clientes sin atributos dinámicos (solo plantilla base): "
                f"{', '.join(sin_atributos)}",
                "info",
                toast=True,
            )

        errores = reporte.get("errores_pestanas") or []
        if errores:
            self.set_status(
                f"⚠️ No se pudieron leer estas pestañas: {', '.join(errores)}",
                "warning",
                toast=True,
            )

        self._sync_worker = None



    def _load_clients_combo(self) -> None:
        """Carga escuelas y negocios desde la BD al combobox de clientes.

        El itemData es una tupla ``("escuela", school_api_id)`` o
        ``("empresa", cliente_id)`` — las escuelas se identifican por su id
        remoto de la API (histórico, permite refrescar desde ahí si no hay
        datos locales); los negocios de Google Sheets no tienen id remoto,
        así que se identifican directamente por su id local.
        """
        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Cliente

        self._combo_clients.blockSignals(True)
        self._combo_clients.clear()

        session = get_session()
        escuelas = session.query(Cliente).filter(
            Cliente.school_api_id.isnot(None)
        ).order_by(Cliente.nombre).all()
        negocios = session.query(Cliente).filter(
            Cliente.tipo == "empresa"
        ).order_by(Cliente.nombre).all()

        for cliente in escuelas:
            label = cliente.nombre
            if cliente.total_students:
                label += f" ({cliente.total_students} alumnos)"
            self._combo_clients.addItem(label, ("escuela", cliente.school_api_id))

        for cliente in negocios:
            self._combo_clients.addItem(f"🏢 {cliente.nombre}", ("empresa", cliente.id))

        session.close()
        self._combo_clients.setCurrentIndex(-1)
        self._combo_clients.blockSignals(False)

    def _on_client_selected(self, index: int) -> None:
        """Al seleccionar un cliente (escuela o negocio), muestra sus registros."""
        item_data = self._combo_clients.itemData(index)
        if item_data is None:
            self._table.setRowCount(0)
            self._lbl_page_info.setText("Mostrando 0 de 0 registros")
            self._combo_templates.clear()
            self._combo_templates.addItem("Plantillas")
            return

        kind, value = item_data
        client_name = self._combo_clients.currentText()

        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Cliente, Registro

        if kind == "empresa":
            # Cliente de Google Sheets: no tiene id remoto, así que todos sus
            # datos ya viven localmente tras la sincronización — no hay
            # fallback a ninguna API posible ni necesario.
            with get_session() as session:
                cliente = session.query(Cliente).get(value)
                if cliente is None:
                    self._table.setRowCount(0)
                    self.set_status("⚠️ Cliente no encontrado", "warning")
                    return
                db_registros = (
                    session.query(Registro).filter_by(cliente_id=cliente.id).all()
                )
                session.expunge_all()

            self.load_records(db_registros)
            self._load_client_templates(value)
            self.set_status(
                f"✅ {len(db_registros)} registros de {client_name} (Google Sheets).",
                "success",
            )
            return

        # kind == "escuela": comportamiento existente (API miescuela.net)
        school_id = value
        school_name = client_name

        # ── Intentar cargar desde la BD local ──────────────────────────────
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

        self._table.set_records(page_records, self._incidencias())

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

    # ── Descarga async de fotos ────────────────────────────────────

    @staticmethod
    def _make_placeholder(size: int = 32) -> QPixmap:
        """Crea un pixmap circular gris como placeholder (HiDPI-aware)."""
        from credencializacion.ui.widgets.record_table import (
            BORDER as _BORDER, make_circular_pixmap,
        )
        src = QPixmap(size, size)
        src.fill(QColor(_BORDER))
        return make_circular_pixmap(src, size)

    @staticmethod
    def _make_circular(source: QPixmap, size: int = 32) -> QPixmap:
        """Recorta un pixmap en círculo (HiDPI-aware, ver record_table)."""
        from credencializacion.ui.widgets.record_table import make_circular_pixmap
        return make_circular_pixmap(source, size)

    @staticmethod
    def _photo_disk_path(url: str) -> "Path":
        """Ruta de caché en disco para una URL de foto (nombre = hash de la URL).

        La caché persiste entre sesiones, así que las fotos no se re-descargan
        cada vez: es la causa principal de la lentitud de carga.
        """
        import hashlib
        from pathlib import Path
        from credencializacion.utils.paths import get_image_cache_dir
        nombre = hashlib.sha1(url.encode("utf-8")).hexdigest() + ".img"
        return get_image_cache_dir() / nombre

    def _cache_photo(self, url: str, pixmap: "QPixmap") -> None:
        """Guarda el pixmap en memoria (raw + circular)."""
        self._raw_photo_cache[url] = pixmap
        self._photo_cache[url] = self._make_circular(pixmap, 32)

    def _download_visible_photos(self, page_records: list["Registro"]) -> None:
        """Aplica las fotos cacheadas (memoria/disco) o las descarga async."""
        from pathlib import Path

        for row, rec in enumerate(page_records):
            url = rec.photo_path
            if not url or not url.startswith("http"):
                # Si ya es un path local, RecordTable ya lo maneja
                continue

            # 1) Caché en memoria (misma sesión): instantáneo.
            if url in self._photo_cache:
                self._table.set_photo_by_id(rec.id, self._photo_cache[url])
                continue

            # 2) Caché en disco (sesiones previas): sin red.
            disk = self._photo_disk_path(url)
            if disk.exists():
                pixmap = QPixmap()
                if pixmap.load(str(disk)) and not pixmap.isNull():
                    self._cache_photo(url, pixmap)
                    self._table.set_photo_by_id(rec.id, self._photo_cache[url])
                    continue

            # 3) Descarga en red (una sola vez; luego queda en disco).
            request = QNetworkRequest(QUrl(url))
            reply = self._net_manager.get(request)
            reply.setProperty("row", row)
            reply.setProperty("photo_url", url)
            reply.setProperty("reg_id", rec.id)
            reply.finished.connect(lambda r=reply: self._on_photo_downloaded(r))

    def _on_photo_downloaded(self, reply: "QNetworkReply") -> None:
        """Callback cuando una foto termina de descargarse."""
        url = reply.property("photo_url")
        reg_id = reply.property("reg_id")

        if reply.error() == QNetworkReply.NetworkError.NoError:
            raw = reply.readAll().data()
            pixmap = QPixmap()
            pixmap.loadFromData(raw)

            if not pixmap.isNull():
                self._cache_photo(url, pixmap)
                # Persistir en disco para no re-descargar en el futuro.
                try:
                    self._photo_disk_path(url).write_bytes(raw)
                except Exception:  # noqa: BLE001
                    pass
                # Actualizar el ícono usando el ID (por si se reordenó)
                self._table.set_photo_by_id(reg_id, self._photo_cache[url])

        reply.deleteLater()

