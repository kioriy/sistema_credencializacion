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
    QDialog,
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
    """Sincroniza escuelas y alumnos desde la API de MiEscuela.

    Args:
        school_api_id: si se indica, sincroniza SOLO esa escuela (sus datos y
            su padrón); si es ``None``, todas las escuelas de la clave. La
            sincronización completa crece con la base, así que la individual
            es la de uso diario.
    """

    progress = Signal(str, str, bool)
    finished_ok = Signal(int, int, dict)  # escuelas, alumnos, reporte de depuración
    failed = Signal(str)

    def __init__(self, school_api_id: int | None = None) -> None:
        super().__init__()
        self._school_api_id = school_api_id

    def run(self) -> None:
        from credencializacion.adapters.miescuela import MiEscuelaAdapter
        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import Cliente, Registro
        from datetime import datetime

        BASE_URL = "https://app.miescuela.net"
        API_KEY = "7c9e6679-7425-40de-944b-e07fc1f90ae7"

        solo = self._school_api_id
        self.progress.emit(
            "⏳ Sincronizando la escuela seleccionada con MiEscuela.net..."
            if solo is not None else "⏳ Sincronizando escuelas con MiEscuela.net...",
            "info", False,
        )

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
                fallback_id = solo if solo is not None else 1
                records = adapter.fetch_records(school_id=fallback_id, status="all")
                if records:
                    school_name = records[0].get("escuela", f"Escuela {fallback_id}")
                    schools = [{
                        "id": fallback_id,
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

            if solo is not None:
                schools = [s for s in schools if s.get("id") == solo]
                if not schools:
                    self.failed.emit(
                        "La escuela seleccionada ya no está en la plataforma "
                        "(se conserva localmente)."
                    )
                    return

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
                except Exception as exc:
                    if solo is not None:
                        # Individual: saltarla diría "completada" sin datos.
                        self.failed.emit(f"No se pudieron descargar los alumnos: {exc}")
                        return
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
            # (Solo en la sincronización completa: la individual no ve el
            # resto de las escuelas y daría falsos faltantes.)
            if schools_confiables and solo is None:
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
        # Encadenado de renders cuando la cola tiene varias plantillas.
        self._render_jobs: list[dict] = []
        self._render_jobs_results: list[tuple[str, str]] = []
        self._render_jobs_done = None
        self._mark_workers = []
        # Reposiciones: consulta en segundo plano de la escuela actual.
        self.btn_reposiciones = None  # lo asigna la ventana principal
        self._repos_worker = None
        self._repos_requery = False
        self._repos_load_on_done = False
        
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
        # Después de cargar la escuela: conteo de reposiciones en el botón.
        self._combo_clients.currentIndexChanged.connect(self._on_client_changed_reposiciones)
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
        abre el diálogo de vista previa. Si la cola mezcla plantillas (p. ej.
        reposiciones de alumno y de autorizados), se renderiza un grupo por
        plantilla y los PDFs se unen para verlos juntos.
        """
        grupos = self._queue_groups()
        if grupos is None:
            return

        if getattr(self, "_render_worker", None) is not None:
            self.set_status("⏳ Ya hay una generación en curso...", "warning", toast=False)
            return

        import tempfile
        from pathlib import Path

        base_dir = Path(tempfile.mkdtemp(prefix="credencial_preview_"))
        self.set_status("🖼 Generando vista previa...", "info", toast=False)

        if len(grupos) == 1:
            g = grupos[0]
            self._start_render(
                g["ids"], g["plantilla_id"], str(base_dir), self._on_preview_ready,
                autorizados=g["autorizados"],
            )
            return

        jobs = [
            {
                "ids": g["ids"],
                "plantilla_id": g["plantilla_id"],
                "out_dir": str(base_dir / f"grupo_{i}"),
                "autorizados": g["autorizados"],
            }
            for i, g in enumerate(grupos, start=1)
        ]

        def _unir(resultados: list[tuple[str, str]]) -> None:
            if not resultados:
                return
            frentes = self._merge_pdfs([f for f, _ in resultados], base_dir / "frentes.pdf")
            vueltas = self._merge_pdfs([v for _, v in resultados], base_dir / "vueltas.pdf")
            self._on_preview_ready(str(frentes), str(vueltas))

        self._run_render_jobs(jobs, _unir)

    @staticmethod
    def _merge_pdfs(rutas: list[str], destino) -> "Path":
        """Concatena PDFs (en orden) en ``destino``.

        Cada grupo ya trae sus páginas completas (2 diseños por hoja), así que
        concatenar frentes y vueltas por separado conserva la correspondencia
        página a página al voltear la hoja.
        """
        from pathlib import Path
        import fitz  # PyMuPDF

        salida = fitz.open()
        for ruta in rutas:
            if ruta and Path(ruta).exists():
                with fitz.open(ruta) as doc:
                    salida.insert_pdf(doc)
        salida.save(str(destino))
        salida.close()
        return Path(destino)

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

    def _start_render(self, ids, plantilla_id, out_dir, on_done, autorizados=None) -> None:
        """Lanza un ``QueueRenderWorker`` y enruta sus señales.

        ``on_done`` se invoca en el hilo principal con (frentes_pdf, vueltas_pdf)
        cuando el render termina correctamente. ``autorizados`` (alineada a
        ``ids``) marca los ítems que son la tarjeta de un autorizado.
        """
        self._render_on_done = on_done
        self._render_worker = QueueRenderWorker(
            ids, plantilla_id, out_dir, autorizados=autorizados
        )
        self._render_worker.progress.connect(
            lambda m: self.set_status(m, "info", toast=False)
        )
        self._render_worker.finished_ok.connect(self._on_render_ok)
        self._render_worker.failed.connect(self._on_render_failed)
        self._render_worker.omitidos.connect(self._on_render_omitidos)
        self._render_worker.finished.connect(self._cleanup_render_worker)
        self._render_worker.start()

    def _run_render_jobs(self, jobs, on_all_done) -> None:
        """Renderiza varios grupos uno tras otro (un worker a la vez).

        ``jobs`` es una lista de dicts ``{ids, plantilla_id, out_dir,
        autorizados, on_ok?}``; ``on_ok(frentes, vueltas)`` se llama al
        terminar bien ese grupo. Al terminar todos se llama ``on_all_done`` con la lista de
        ``(frentes_pdf, vueltas_pdf)`` de los que salieron bien, en orden. El
        siguiente grupo arranca al terminar el hilo anterior
        (``_cleanup_render_worker``), no en su señal de éxito: si arrancara
        antes, la limpieza del hilo viejo borraría la referencia al nuevo.
        """
        self._render_jobs = list(jobs)
        self._render_jobs_results = []
        self._render_jobs_done = on_all_done
        self._next_render_job()

    def _next_render_job(self) -> None:
        if not self._render_jobs:
            done = self._render_jobs_done
            resultados = self._render_jobs_results
            self._render_jobs_done = None
            self._render_jobs_results = []
            if done is not None:
                done(resultados)
            return
        job = self._render_jobs.pop(0)

        def _ok(frentes: str, vueltas: str) -> None:
            self._render_jobs_results.append((frentes, vueltas))
            if job.get("on_ok") is not None:
                job["on_ok"](frentes, vueltas)

        self._start_render(
            job["ids"], job["plantilla_id"], job["out_dir"], _ok,
            autorizados=job.get("autorizados"),
        )

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
        # Encadenado de grupos (colas con varias plantillas).
        if getattr(self, "_render_jobs_done", None) is not None:
            self._next_render_job()

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

    def _queue_groups(self) -> list[dict] | None:
        """Agrupa la cola visual por plantilla.

        Las tarjetas de reposiciones traen su propia plantilla; las agregadas
        desde la tabla usan la del combo. Cada grupo es una cola (y un par de
        PDFs) en el Centro de Impresión.

        Returns:
            Lista de grupos ``{plantilla_id, nombre, reposicion, entries, ids,
            autorizados}`` en orden de aparición, o ``None`` (con aviso en el
            footer) si la cola está vacía o falta elegir plantilla.
        """
        entries = self._queue_panel.get_entries()
        if not entries:
            self.set_status("⚠️ La cola de impresión está vacía", "warning")
            return None

        combo_id = self._combo_templates.currentData()
        combo_nombre = self._combo_templates.currentText()
        grupos: dict[int, dict] = {}
        for reg, meta in entries:
            propia = meta is not None and meta.plantilla_id is not None
            pid = meta.plantilla_id if propia else combo_id
            if not pid:
                self.set_status("⚠️ Selecciona una plantilla primero", "warning")
                return None
            g = grupos.setdefault(pid, {
                "plantilla_id": pid,
                "nombre": meta.plantilla_nombre if propia else combo_nombre,
                "reposicion": False,
                "entries": [],
                "ids": [],
                "autorizados": [],
            })
            g["reposicion"] = g["reposicion"] or propia
            g["entries"].append((reg, meta))
            g["ids"].append(reg.id)
            g["autorizados"].append(
                meta.authorized_person_id
                if meta is not None and meta.tipo == "autorizado" else None
            )
        return list(grupos.values())

    def _send_queue_to_print_center(self) -> None:
        """Crea las colas en BD y genera/guarda sus PDFs sin bloquear la app.

        Crea una ``ColaImpresion`` por plantilla (una cola normal produce una
        sola; las reposiciones, una por tipo de tarjeta: alumno, autorizado 1,
        2…), luego renderiza en segundo plano los PDFs de frentes y vueltas
        (2 diseños por hoja) de cada una en su carpeta estable (build-safe) y
        guarda sus rutas. Al terminar, limpia la cola visual y refresca el
        Centro de Impresión.
        """
        grupos = self._queue_groups()
        if grupos is None:
            return

        registros_unicos = list({reg.id: reg for g in grupos for reg, _ in g["entries"]}.values())
        if not self._confirmar_incidencias(registros_unicos):
            return

        if getattr(self, "_render_worker", None) is not None:
            self.set_status("⏳ Ya hay una generación en curso...", "warning", toast=False)
            return

        from types import SimpleNamespace

        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion, ItemCola
        from credencializacion.services.reposiciones import separar_ids

        # Perfil de posición por defecto para la cola nueva (el primero
        # disponible). Luego puede regenerarse con otro perfil desde el
        # Centro de Impresión.
        from credencializacion.core.settings import AppSettings
        AppSettings.ensure_default_profile()
        perfiles = AppSettings.list_position_profiles()
        perfil_defecto = perfiles[0] if perfiles else None

        cola_ids: list[int] = []
        try:
            with DatabaseSession() as session:
                for g in grupos:
                    n = len(g["entries"])
                    nombre = (
                        f"Reposiciones · {g['nombre']} — {n} registros"
                        if g["reposicion"] else f"{g['nombre']} — {n} registros"
                    )
                    cola = ColaImpresion(
                        nombre=nombre,
                        total_registros=n,
                        perfil_posicion=perfil_defecto,
                    )
                    session.add(cola)
                    session.flush()

                    # Todos los ítems del grupo usan el mismo diseño. El
                    # multiplantillaje solo intercambia la imagen de fondo por
                    # lado, resuelto al renderizar consultando la
                    # ConfiguracionLado del diseño.
                    for orden, (reg, meta) in enumerate(g["entries"], start=1):
                        es_aut = meta is not None and meta.tipo == "autorizado"
                        session.add(
                            ItemCola(
                                cola_id=cola.id,
                                registro_id=reg.id,
                                plantilla_id=g["plantilla_id"],
                                orden=orden,
                                tipo_item="autorizado" if es_aut else "alumno",
                                autorizado_slot=meta.slot if es_aut else None,
                                authorized_person_id=(
                                    meta.authorized_person_id if es_aut else None
                                ),
                                credential_request=meta.solicitud if meta else None,
                            )
                        )
                    cola_ids.append(cola.id)
                session.commit()
        except Exception as e:
            self.set_status(f"❌ Error al guardar cola: {e}", "error")
            return

        from credencializacion.utils.paths import get_cola_pdf_dir

        self.set_status(
            "📤 Enviando al Centro de Impresión"
            + (f" ({len(grupos)} colas)..." if len(grupos) > 1 else "..."),
            "info", toast=False,
        )

        # Marcar credenciales como 'En impresión' en la API (en segundo plano).
        # Las tarjetas de autorizado van por `authorized_person_ids`: nunca
        # deben mover el estatus del alumno.
        first_cliente_id = getattr(grupos[0]["entries"][0][0], "cliente_id", None)
        student_ids, authorized_ids = separar_ids(
            SimpleNamespace(
                tipo_item=meta.tipo if meta else "alumno",
                authorized_person_id=meta.authorized_person_id if meta else None,
                datos=reg.datos,
            )
            for g in grupos for reg, meta in g["entries"]
        )
        if (student_ids or authorized_ids) and first_cliente_id:
            self._start_bulk_mark(
                first_cliente_id, "printing", student_ids, authorized_ids
            )

        jobs = [
            {
                "ids": g["ids"],
                "plantilla_id": g["plantilla_id"],
                "out_dir": str(get_cola_pdf_dir(cola_id)),
                "autorizados": g["autorizados"],
                "on_ok": (lambda f, v, cid=cola_id: self._save_cola_pdfs(cid, f, v)),
            }
            for g, cola_id in zip(grupos, cola_ids)
        ]
        self._run_render_jobs(jobs, lambda res: self._on_queues_sent(len(cola_ids), len(res)))

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
        self,
        cliente_id: int,
        action: str,
        student_ids: list[int],
        authorized_ids: list[int] | None = None,
    ) -> None:
        """Lanza un ``BulkMarkWorker`` para marcar estatus sin bloquear la UI."""
        from credencializacion.ui.status_worker import BulkMarkWorker

        base_url, api_key = self._client_api_credentials(cliente_id)
        worker = BulkMarkWorker(base_url, api_key, action, student_ids, authorized_ids)
        self._mark_workers.append(worker)

        def _on_done(success: bool, message: str, updated: int) -> None:
            if success:
                self.set_status(
                    f"🔔 Estatus actualizado: {updated} credenciales", "info", toast=False
                )
                # Lo marcado 'En impresión' sale de las reposiciones pendientes.
                self._refresh_reposiciones_count()
            else:
                self.set_status(
                    f"⚠️ No se pudo actualizar el estatus en la API: {message}",
                    "warning",
                )
            if worker in self._mark_workers:
                self._mark_workers.remove(worker)

        worker.done.connect(_on_done)
        worker.start()

    def _save_cola_pdfs(self, cola_id: int, frentes_pdf: str, vueltas_pdf: str) -> None:
        """Guarda las rutas de los PDFs generados en su cola."""
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

    def _on_queues_sent(self, total: int, generadas: int) -> None:
        """Cierra el envío: limpia la cola visual y refresca el Centro de Impresión."""
        if generadas == total:
            self.set_status(
                "✅ Cola enviada al Centro de Impresión" if total == 1
                else f"✅ {total} colas enviadas al Centro de Impresión",
                "success",
            )
        else:
            self.set_status(
                f"⚠️ Se generaron {generadas} de {total} colas; revisa en el "
                "Centro de Impresión las que quedaron sin PDF.",
                "warning",
            )
        self._queue_panel.clear_queue()
        self.add_to_queue_requested.emit()

    # ── Reposiciones ──────────────────────────────────────────────

    def _current_school(self) -> tuple[int | None, int | None]:
        """``(school_api_id, cliente_id)`` de la escuela seleccionada.

        ``(None, None)`` si no hay selección o es un cliente de Google Sheets
        (las reposiciones solo existen en la API de MiEscuela).
        """
        idx = self._combo_clients.currentIndex()
        item_data = self._combo_clients.itemData(idx) if idx >= 0 else None
        if not item_data:
            return None, None
        kind, value = item_data
        if kind != "escuela":
            return None, None

        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Cliente

        with get_session() as session:
            cliente = session.query(Cliente).filter_by(school_api_id=value).first()
            return value, (cliente.id if cliente is not None else None)

    def _set_reposiciones_label(self, total: int | None) -> None:
        btn = getattr(self, "btn_reposiciones", None)
        if btn is None:
            return
        btn.setText("Reposiciones" if total is None else f"Reposiciones ({total})")

    def _on_client_changed_reposiciones(self, _index: int) -> None:
        """Al cambiar de escuela, reinicia y vuelve a consultar el conteo."""
        self._repos_load_on_done = False
        self._set_reposiciones_label(None)
        school_id, _ = self._current_school()
        btn = getattr(self, "btn_reposiciones", None)
        if btn is not None:
            btn.setEnabled(school_id is not None)
        self._refresh_reposiciones_count()

    def _refresh_reposiciones_count(self) -> None:
        """Consulta en segundo plano las reposiciones de la escuela actual."""
        school_id, cliente_id = self._current_school()
        if school_id is None or cliente_id is None:
            return
        worker = getattr(self, "_repos_worker", None)
        if worker is not None and worker.isRunning():
            # Al terminar se compara la escuela y, si cambió, se reconsulta.
            self._repos_requery = True
            return

        from credencializacion.ui.status_worker import ReposicionesWorker

        self._repos_requery = False
        base_url, api_key = self._client_api_credentials(cliente_id)
        self._repos_worker = ReposicionesWorker(base_url, api_key, school_id)
        self._repos_worker.finished_ok.connect(self._on_reposiciones_ready)
        self._repos_worker.failed.connect(self._on_reposiciones_failed)
        self._repos_worker.finished.connect(self._on_repos_worker_finished)
        self._repos_worker.start()

    def _on_repos_worker_finished(self) -> None:
        self._repos_worker = None
        if getattr(self, "_repos_requery", False):
            self._refresh_reposiciones_count()

    def _on_reposiciones(self) -> None:
        """Botón «Reposiciones»: carga lo pendiente de la escuela en la cola."""
        school_id, cliente_id = self._current_school()
        if school_id is None or cliente_id is None:
            self.set_status(
                "⚠️ Selecciona una escuela de MiEscuela para ver sus reposiciones.",
                "warning",
            )
            return
        self._repos_load_on_done = True
        self.set_status("⏳ Consultando reposiciones pendientes...", "info", toast=False)
        worker = getattr(self, "_repos_worker", None)
        if worker is not None and worker.isRunning():
            # La consulta en curso puede ser de otra escuela: reconsultar al
            # terminar garantiza que se cargue la actual.
            self._repos_requery = True
            return
        self._refresh_reposiciones_count()

    @Slot(int, str)
    def _on_reposiciones_failed(self, school_id: int, message: str) -> None:
        if school_id != self._current_school()[0]:
            return
        if self._repos_load_on_done:
            self._repos_load_on_done = False
            self.set_status(f"❌ No se pudieron consultar las reposiciones: {message}", "error")

    @Slot(int, list, list)
    def _on_reposiciones_ready(self, school_id: int, alumnos: list, con_autorizados: list) -> None:
        from credencializacion.services import reposiciones

        current_school, cliente_id = self._current_school()
        if school_id != current_school or cliente_id is None:
            return  # respuesta de una escuela que ya no se está viendo

        tarjetas = (
            reposiciones.tarjetas_de_alumnos(alumnos)
            + reposiciones.tarjetas_de_autorizados(con_autorizados)
        )
        self._set_reposiciones_label(len(tarjetas))
        # Ya es la escuela correcta: no hace falta reconsultar.
        self._repos_requery = False

        if not self._repos_load_on_done:
            return
        self._repos_load_on_done = False
        if not tarjetas:
            self.set_status("✅ No hay reposiciones pendientes en esta escuela.", "success")
            return
        self._cargar_reposiciones(cliente_id, alumnos + con_autorizados, tarjetas)

    def _upsert_registros_api(self, cliente_id: int, registros: list[dict]) -> None:
        """Actualiza (o crea) los registros locales con lo recién descargado.

        Así la tarjeta se imprime con los datos vigentes (foto o autorizado
        recién cambiados) aunque no se haya sincronizado la escuela completa.
        """
        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import Registro

        vistos: set[str] = set()
        with DatabaseSession() as session:
            for rec in registros:
                enrollment = rec.get("enrollment_code") or rec.get("matricula", "")
                if enrollment in vistos:
                    continue
                vistos.add(enrollment)
                reg = session.query(Registro).filter_by(
                    cliente_id=cliente_id, enrollment_code=enrollment,
                ).first()
                if reg is None:
                    reg = Registro(
                        cliente_id=cliente_id,
                        enrollment_code=enrollment,
                        estado_impresion="pendiente",
                    )
                    session.add(reg)
                reg.datos = rec
                reg.credential_status = rec.get("estado_credencial")
                reg.qr_data = rec.get("qr_data") or rec.get("photo_url", "")
                reg.photo_path = rec.get("photo_url", "")
            session.commit()

    def _cached_pixmap(self, url: str) -> "QPixmap | None":
        """Foto desde el caché en memoria o en disco (sin descargar)."""
        if not url:
            return None
        pixmap = self._raw_photo_cache.get(url)
        if pixmap is not None:
            return pixmap
        try:
            ruta = self._photo_disk_path(url)
            if ruta.exists():
                pixmap = QPixmap(str(ruta))
                if not pixmap.isNull():
                    return pixmap
        except Exception:  # noqa: BLE001
            pass
        return None

    def _plantillas_reposicion(self, cliente_id: int) -> tuple[list[tuple[int, str]], dict[str, int]]:
        """Plantillas de la escuela y el mapa vigente tipo de tarjeta → plantilla."""
        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Cliente, Plantilla
        from credencializacion.services import reposiciones

        with get_session() as session:
            plantillas = [
                (p.id, p.nombre)
                for p in session.query(Plantilla)
                .filter_by(cliente_id=cliente_id)
                .order_by(Plantilla.nombre)
                .all()
            ]
            cliente = session.query(Cliente).get(cliente_id)
            cfg = dict((cliente.config or {}) if cliente is not None else {})
        mapa = reposiciones.resolver_plantillas(
            plantillas, cfg.get(reposiciones.CONFIG_PLANTILLAS)
        )
        return plantillas, mapa

    def _on_configurar_plantillas_reposicion(self) -> None:
        """Menú «Plantillas de reposición…»: asigna el diseño de cada tarjeta."""
        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import Cliente
        from credencializacion.services.reposiciones import CONFIG_PLANTILLAS
        from credencializacion.ui.dialogs.reposicion_plantillas_dialog import (
            ReposicionPlantillasDialog,
        )

        _, cliente_id = self._current_school()
        if cliente_id is None:
            self.set_status("⚠️ Selecciona una escuela primero.", "warning")
            return
        plantillas, mapa = self._plantillas_reposicion(cliente_id)
        if not plantillas:
            self.set_status("⚠️ Esta escuela no tiene plantillas.", "warning")
            return
        dlg = ReposicionPlantillasDialog(plantillas, mapa, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        with DatabaseSession() as session:
            cliente = session.query(Cliente).get(cliente_id)
            if cliente is None:
                return
            cfg = dict(cliente.config or {})
            cfg[CONFIG_PLANTILLAS] = dlg.result_map()
            cliente.config = cfg
            session.commit()
        self.set_status("✅ Plantillas de reposición guardadas.", "success")

    def _cargar_reposiciones(self, cliente_id: int, registros_api: list[dict], tarjetas: list) -> None:
        """Llena la cola visual con las tarjetas de reposición de la escuela.

        Cada tarjeta lleva su plantilla: la de alumno, o la del autorizado N.
        Si un autorizado N no tiene plantilla propia se usa la de otro
        autorizado (el render copia los datos de la persona a esa posición);
        si falta la de alumno, se usa la elegida en el combo. Lo que siga sin
        plantilla no se agrega y se avisa.
        """
        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Registro
        from credencializacion.services import reposiciones
        from credencializacion.ui.widgets.print_queue import QueueMeta

        try:
            self._upsert_registros_api(cliente_id, registros_api)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"❌ Error al guardar los registros: {e}", "error")
            return

        # Recargar la tabla para que muestre los datos recién guardados.
        with get_session() as session:
            db_registros = session.query(Registro).filter_by(cliente_id=cliente_id).all()
            session.expunge_all()
        self.load_records(db_registros)
        por_matricula = {r.enrollment_code: r for r in db_registros}

        plantillas, mapa = self._plantillas_reposicion(cliente_id)
        nombres = dict(plantillas)
        combo_id = self._combo_templates.currentData()
        respaldo_aut = next(
            (mapa[f"autorizado_{n}"] for n in reposiciones.SLOTS_AUTORIZADO
             if f"autorizado_{n}" in mapa),
            None,
        )

        orden = sorted(
            tarjetas,
            key=lambda t: (t.tipo != reposiciones.TIPO_ALUMNO, t.slot or 0),
        )
        agregadas = {"alumno": 0, "autorizado": 0}
        sin_plantilla: list[str] = []
        prestadas: set[int] = set()
        for t in orden:
            reg = por_matricula.get(t.enrollment_code)
            if reg is None:
                continue
            pid = mapa.get(t.clave_plantilla)
            if pid is None and t.tipo == reposiciones.TIPO_ALUMNO:
                pid = combo_id
            if pid is None and t.tipo == reposiciones.TIPO_AUTORIZADO and respaldo_aut:
                pid = respaldo_aut
                prestadas.add(t.slot)
            if pid is None:
                sin_plantilla.append(
                    "Alumno" if t.tipo == reposiciones.TIPO_ALUMNO else f"Autorizado {t.slot}"
                )
                continue

            es_aut = t.tipo == reposiciones.TIPO_AUTORIZADO
            foto = str(reg.get_dato(f"autorizado_{t.slot}_foto", "") or "") if es_aut else ""
            meta = QueueMeta(
                tipo=t.tipo,
                slot=t.slot,
                authorized_person_id=t.authorized_person_id,
                solicitud=t.solicitud,
                plantilla_id=pid,
                plantilla_nombre=nombres.get(pid, self._combo_templates.currentText()),
                etiqueta=t.etiqueta,
                nombre=t.nombre,
                foto=foto,
            )
            pixmap = self._cached_pixmap(foto if es_aut else (reg.photo_path or ""))
            self._queue_panel.add_to_queue(reg, pixmap, meta=meta, render=False)
            agregadas[t.tipo] += 1
        self._queue_panel.refresh()

        total = agregadas["alumno"] + agregadas["autorizado"]
        partes = []
        if agregadas["alumno"]:
            partes.append(f"{agregadas['alumno']} de alumno")
        if agregadas["autorizado"]:
            partes.append(f"{agregadas['autorizado']} de autorizado")
        mensaje = f"✅ {total} reposición(es) en la cola" + (
            f" ({', '.join(partes)})." if partes else "."
        )
        nivel = "success"
        if prestadas:
            mensaje += (
                " Autorizado " + ", ".join(str(n) for n in sorted(prestadas))
                + " sin plantilla propia: se usa la de otro autorizado."
            )
            nivel = "warning"
        if sin_plantilla:
            faltan = sorted(set(sin_plantilla))
            mensaje += (
                f" ⚠️ {len(sin_plantilla)} sin plantilla ({', '.join(faltan)}): "
                "asígnala en Reposiciones ▸ Plantillas de reposición…"
            )
            nivel = "warning"
        self.set_status(mensaje, nivel)

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

    def _on_refresh_photos(self, todas: bool = False) -> None:
        """Actualiza las fotos del cliente cargado (servidor y/o Google Sheets).

        Con ``todas=True`` el alcance son las fotos de TODAS las escuelas y
        clientes: se limpian del caché y se re-descargan las de la escuela
        visible; las demás se vuelven a bajar al abrir su escuela o al
        imprimir (el caché se llena solo, bajo demanda).

        - Fotos del servidor (URL http): se borran del caché en disco y se
          vuelven a descargar (prefetch).
        - Fotos LOCALES de Google Sheets (rutas en ``sheets_local_fotos``): no
          hay nada que descargar; se relee la carpeta (por si agregaste o
          reemplazaste archivos) limpiando el índice y la caché en memoria.

        Úsalo si una foto quedó desactualizada, la reemplazaste o no cargó.
        """
        from PySide6.QtWidgets import QMessageBox

        records = getattr(self, "_all_records", []) or []
        if todas:
            from credencializacion.db.engine import get_session
            from credencializacion.db.models import Registro

            with get_session() as session:
                rutas = [
                    p for (p,) in session.query(Registro.photo_path)
                    .filter(Registro.photo_path.isnot(None), Registro.photo_path != "")
                    .all()
                ]
        else:
            rutas = [r.photo_path for r in records if getattr(r, "photo_path", "")]
        urls = {str(p) for p in rutas if str(p).startswith("http")}
        locales = [p for p in rutas if not str(p).startswith("http")]

        if not rutas:
            self.set_status(
                "⚠️ No hay fotos que actualizar."
                if todas else
                "⚠️ No hay fotos que actualizar (selecciona una escuela primero).",
                "warning",
            )
            return

        partes = []
        if urls:
            partes.append(f"{len(urls)} del servidor (se re-descargan)")
        if locales:
            partes.append(f"{len(locales)} locales de Google Sheets (se releen)")
        alcance = (
            "de TODAS las escuelas" if todas else "de la escuela seleccionada"
        )
        nota = (
            "\n\nSe re-descargan ahora las de la escuela visible; las demás, "
            "al abrir su escuela o al imprimir."
            if todas else ""
        )
        resp = QMessageBox.question(
            self,
            "Actualizar fotos",
            f"Se actualizarán las fotos {alcance}: " + " y ".join(partes) + "."
            + nota + "\n\n"
            "Úsalo si cambiaste una foto o alguna no carga. ¿Continuar?",
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        # Detener el prefetch en curso antes de borrar (las tareas en vuelo que
        # alcancen a reescribir un archivo solo lo dejan con contenido fresco).
        prev = getattr(self, "_prefetch_worker", None)
        if prev is not None:
            prev.stop()

        # Limpiar cachés en memoria y el índice de carpetas locales, para que las
        # fotos locales agregadas/reemplazadas se vuelvan a leer del disco.
        try:
            self._raw_photo_cache.clear()
        except Exception:  # noqa: BLE001
            pass
        try:
            from credencializacion.utils import images as _images
            _images._folder_index_cache.clear()
        except Exception:  # noqa: BLE001
            pass

        borradas = 0
        if urls:
            from credencializacion.adapters.image_cache import clear_url_cache
            borradas = clear_url_cache(urls)

        if urls and locales:
            msg = f"🧹 {borradas} del servidor y {len(locales)} locales actualizadas. Recargando..."
        elif urls:
            msg = f"🧹 {borradas} foto(s) del servidor limpiadas del caché. Re-descargando..."
        else:
            msg = f"🔄 {len(locales)} foto(s) locales releídas del disco. Recargando..."
        self.set_status(msg, "info", toast=False)

        # Relanzar el prefetch (solo afecta a las URLs http) y refrescar la
        # página: las fotos aparecerán conforme se re-descarguen o se relean.
        self._start_photo_prefetch(records)
        self._refresh_page()

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

    def has_client_selected(self) -> bool:
        """True si hay una escuela o cliente elegido en el combo."""
        return self._combo_clients.currentData() is not None

    def _on_sync_selected(self) -> None:
        """Sincroniza solo el cliente seleccionado, desde su propio origen.

        Una escuela de MiEscuela se baja de la API; un cliente de Google
        Sheets, de su pestaña. Es mucho más rápida que la sincronización
        completa, que crece con la base.
        """
        item_data = self._combo_clients.currentData()
        if item_data is None:
            self.set_status(
                "⚠️ Selecciona una escuela para sincronizarla, o usa «Sincronizar todo».",
                "warning",
            )
            return
        kind, value = item_data
        if kind == "escuela":
            self._on_sync_api(school_api_id=value)
            return

        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Cliente

        with get_session() as session:
            cliente = session.query(Cliente).get(value)
            nombre = cliente.nombre if cliente is not None else None
        if nombre is None:
            self.set_status("⚠️ Cliente no encontrado", "warning")
            return
        self._on_sync_sheets(solo_cliente=nombre)

    def _sync_label(self) -> str:
        """Nombre visible del cliente seleccionado (sin el conteo de alumnos)."""
        texto = self._combo_clients.currentText()
        return texto.split(" (")[0].replace("🏢 ", "").strip()

    def _restore_client_selection(self) -> None:
        """Tras recargar el combo, vuelve a elegir el cliente que se veía.

        Al reelegirlo se recargan sus registros (ya con lo sincronizado) y el
        conteo de reposiciones. Si ya no está, queda sin selección.
        """
        item_data = getattr(self, "_sync_keep_selection", None)
        self._sync_keep_selection = None
        if item_data is None:
            return
        # `findData` no compara bien las tuplas ("escuela", id) guardadas como
        # objeto Python: se busca a mano.
        for idx in range(self._combo_clients.count()):
            if self._combo_clients.itemData(idx) == item_data:
                self._combo_clients.setCurrentIndex(idx)
                return

    def _on_sync_api(self, school_api_id: int | None = None) -> None:
        """Sincroniza desde la API de MiEscuela (asíncrono).

        ``school_api_id`` limita la sincronización a esa escuela; sin él se
        sincronizan todas.
        """
        if getattr(self, "_sync_worker", None) is not None:
            self.set_status("⏳ Ya hay una sincronización en curso...", "warning", toast=False)
            return

        self._set_sync_enabled(False)
        self._sync_keep_selection = self._combo_clients.currentData()
        self._sync_single = self._sync_label() if school_api_id is not None else None
        self.set_status(
            f"Iniciando sincronización de «{self._sync_single}»..."
            if self._sync_single else "Iniciando sincronización de todas las escuelas...",
            "info", toast=False,
        )

        self._sync_worker = SyncWorker(school_api_id)
        self._sync_worker.progress.connect(self.set_status)
        self._sync_worker.finished_ok.connect(self._on_sync_finished)
        self._sync_worker.failed.connect(self._on_sync_failed)
        self._sync_worker.start()

    def _on_sync_finished(
        self, count_schools: int, count_students: int, reporte: dict
    ) -> None:
        self._set_sync_enabled(True)
        self._load_clients_combo()
        self._restore_client_selection()

        if getattr(self, "_sync_single", None):
            msg = f"✅ «{self._sync_single}» sincronizada — {count_students} alumnos guardados."
        else:
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
        self._sync_keep_selection = None
        self.set_status(f"❌ Error de sincronización: {error_msg}", "error", toast=True)
        self._sync_worker = None

    def _on_sync_sheets(self, solo_cliente: str | None = None) -> None:
        """Sincroniza el documento de Google Sheets configurado (asíncrono).

        ``solo_cliente`` limita la sincronización a la pestaña de ese cliente.

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
        self._sync_keep_selection = self._combo_clients.currentData()
        self._sync_single = solo_cliente
        self.set_status(
            f"Iniciando sincronización de «{solo_cliente}»..." if solo_cliente
            else f"Iniciando sincronización de «{document_name}»...",
            "info", toast=False,
        )

        self._sync_worker = SheetsSyncWorker(
            credentials_path, document_name, solo_cliente=solo_cliente
        )
        self._sync_worker.progress.connect(self.set_status)
        self._sync_worker.finished_ok.connect(self._on_sheets_sync_finished)
        self._sync_worker.failed.connect(self._on_sync_failed)
        self._sync_worker.start()

    def _on_sheets_sync_finished(
        self, count_clientes: int, count_registros: int, reporte: dict
    ) -> None:
        self._set_sync_enabled(True)
        self._load_clients_combo()
        self._restore_client_selection()

        if getattr(self, "_sync_single", None):
            msg = f"✅ «{self._sync_single}» sincronizado — {count_registros} registros guardados."
        else:
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

        duplicados = reporte.get("encabezados_duplicados") or []
        if duplicados:
            self.set_status(
                "ℹ️ Encabezados repetidos (se usó la primera columna de cada "
                f"nombre): {'; '.join(duplicados)}",
                "info",
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
        cada vez: es la causa principal de la lentitud de carga. Delega en el
        helper compartido para que el motor de PDF reutilice EXACTAMENTE estos
        mismos archivos (si las claves divergieran, la impresión volvería a
        depender de la red y algunas fotos saldrían en blanco al azar).
        """
        from credencializacion.adapters.image_cache import photo_url_cache_path
        return photo_url_cache_path(url)

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

