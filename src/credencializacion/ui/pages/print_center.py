"""
Centro de Impresión — gestión de colas de impresión.

Página con lista de colas, detalle de cola seleccionada,
vista previa y envío directo a impresora.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QCursor, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QProgressBar,
    QAbstractItemView,
    QSizePolicy,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QComboBox,
    QLineEdit,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
)

import qtawesome as qta

if TYPE_CHECKING:
    from credencializacion.db.models import ColaImpresion

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
WARNING = "#F59E0B"
ERROR = "#EF4444"


class StatCard(QFrame):
    """Tarjeta de estadística con número grande y label."""

    def __init__(
        self,
        title: str,
        value: int | str,
        color: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
                padding: 8px;
            }}
        """)
        self.setMinimumWidth(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._lbl_value = QLabel(str(value))
        self._lbl_value.setFont(QFont("Inter", 24, QFont.Weight.Bold))
        self._lbl_value.setStyleSheet(f"color: {color}; border: none;")
        self._lbl_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._lbl_value)

        lbl_title = QLabel(title)
        lbl_title.setFont(QFont("Inter", 11))
        lbl_title.setStyleSheet(f"color: {TEXT_LIGHT}; border: none;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_title)

    def set_value(self, value: int | str) -> None:
        """Actualiza el valor de la tarjeta."""
        self._lbl_value.setText(str(value))


class CopyQueueDialog(QDialog):
    """Diálogo para copiar una cola de impresión eligiendo la plantilla.

    Muestra el nombre propuesto para la copia y un selector con las
    plantillas de la escuela (cliente) de la cola original, con la
    plantilla actual preseleccionada.
    """

    def __init__(
        self,
        nombre_original: str,
        plantillas: list[tuple[int, str]],
        plantilla_actual_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Copiar cola de impresión")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"background-color: {CARD_BG}; color: {TEXT_DARK};")

        input_style = f"""
            background-color: {CARD_BG};
            border: 1px solid {BORDER};
            border-radius: 6px;
            padding: 8px;
            font-size: 13px;
            color: {TEXT_DARK};
        """

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        lbl_nombre = QLabel("Nombre de la copia:")
        lbl_nombre.setFont(QFont("Inter", 12, QFont.Weight.DemiBold))
        layout.addWidget(lbl_nombre)

        self._edit_nombre = QLineEdit(f"{nombre_original} — copia")
        self._edit_nombre.setStyleSheet(input_style)
        layout.addWidget(self._edit_nombre)

        lbl_plantilla = QLabel("Plantilla a aplicar:")
        lbl_plantilla.setFont(QFont("Inter", 12, QFont.Weight.DemiBold))
        layout.addWidget(lbl_plantilla)

        self._combo_plantillas = QComboBox()
        self._combo_plantillas.setStyleSheet(input_style)
        for pid, nombre in plantillas:
            self._combo_plantillas.addItem(nombre, pid)
        idx = self._combo_plantillas.findData(plantilla_actual_id)
        if idx >= 0:
            self._combo_plantillas.setCurrentIndex(idx)
        layout.addWidget(self._combo_plantillas)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_values(self) -> tuple[str, int]:
        """Devuelve (nombre de la copia, plantilla_id elegida)."""
        nombre = self._edit_nombre.text().strip() or "Cola copiada"
        return nombre, self._combo_plantillas.currentData()


class PrintCenter(QWidget):
    """Centro de Impresión — gestión de colas persistentes.

    Layout:
    - Stats cards (Total Impresas, Colas Activas, Errores)
    - Splitter con lista de colas (izq) + detalle de cola (der)
    - Status bar inferior

    Signals:
        queue_print_requested(int, str): (cola_id, cara) para imprimir.
    """

    queue_print_requested = Signal(int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selected_cola_id: int | None = None
        self._mark_workers: list = []
        self._render_worker = None
        self._render_on_done = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Construye el layout del centro de impresión."""
        self.setStyleSheet(f"background-color: {MAIN_BG};")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 16, 24, 8)
        main_layout.setSpacing(12)

        # ── Stats Cards ────────────────────────────────────────────
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)

        self._card_total = StatCard("Colas Totales", 0, PRIMARY)
        self._card_active = StatCard("Colas Activas", 0, WARNING)
        self._card_complete = StatCard("Completadas", 0, SUCCESS)
        self._card_registros = StatCard("Registros", 0, TEXT_DARK)

        stats_layout.addWidget(self._card_total)
        stats_layout.addWidget(self._card_active)
        stats_layout.addWidget(self._card_complete)
        stats_layout.addWidget(self._card_registros)

        main_layout.addLayout(stats_layout)

        # ── Splitter: Lista de colas + Detalle ─────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: transparent;
                width: 4px;
            }
        """)

        # Panel izquierdo: lista de colas
        left_panel = self._build_queue_list_panel()
        splitter.addWidget(left_panel)

        # Panel derecho: detalle de cola
        right_panel = self._build_queue_detail_panel()
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([250, 600])

        main_layout.addWidget(splitter, stretch=1)

        # ── Status bar ─────────────────────────────────────────────
        self._status_bar = QLabel("Listo")
        self._status_bar.setFont(QFont("Inter", 11))
        self._status_bar.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_LIGHT};
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 6px 12px;
            }}
        """)
        main_layout.addWidget(self._status_bar)

        # ── Progress bar (oculta por defecto) ──────────────────────
        self._progress_frame = QFrame()
        self._progress_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)
        progress_layout = QHBoxLayout(self._progress_frame)
        progress_layout.setContentsMargins(12, 8, 12, 8)
        progress_layout.setSpacing(12)

        self._lbl_progress = QLabel("🖨  Imprimiendo...")
        self._lbl_progress.setFont(QFont("Inter", 12, QFont.Weight.DemiBold))
        self._lbl_progress.setStyleSheet(f"color: {TEXT_DARK}; border: none;")
        progress_layout.addWidget(self._lbl_progress)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {MAIN_BG};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {PRIMARY};
                border-radius: 3px;
            }}
        """)
        progress_layout.addWidget(self._progress_bar, stretch=1)

        self._lbl_progress_count = QLabel("0 / 0")
        self._lbl_progress_count.setFont(QFont("Inter", 11))
        self._lbl_progress_count.setStyleSheet(f"color: {TEXT_LIGHT}; border: none;")
        progress_layout.addWidget(self._lbl_progress_count)

        self._progress_frame.setVisible(False)
        main_layout.addWidget(self._progress_frame)

    # ── Panel izquierdo: Lista de colas ────────────────────────────

    def _build_queue_list_panel(self) -> QFrame:
        """Construye el panel con la lista de colas de impresión."""
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Título
        lbl = QLabel("📋 Colas de Impresión")
        lbl.setFont(QFont("Inter", 13, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {TEXT_DARK}; border: none;")
        layout.addWidget(lbl)

        # Lista
        self._queue_list = QListWidget()
        self._queue_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {CARD_BG};
                border: none;
                font-family: 'Inter', sans-serif;
                font-size: 13px;
                color: {TEXT_DARK};
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px 8px;
                border-bottom: 1px solid {BORDER};
                border-radius: 6px;
                margin-bottom: 2px;
            }}
            QListWidget::item:selected {{
                background-color: #FEE2E2;
                color: {TEXT_DARK};
            }}
            QListWidget::item:hover {{
                background-color: {MAIN_BG};
            }}
        """)
        self._queue_list.currentItemChanged.connect(self._on_queue_selected)
        layout.addWidget(self._queue_list, stretch=1)

        # Botón eliminar cola
        btn_delete = QPushButton()
        btn_delete.setIcon(qta.icon("fa5s.trash-alt", color=ERROR))
        btn_delete.setIconSize(QSize(14, 14))
        btn_delete.setText("  Eliminar Cola")
        btn_delete.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_delete.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 8px;
                color: {TEXT_LIGHT};
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {ERROR};
                color: {ERROR};
            }}
        """)
        btn_delete.clicked.connect(self._delete_selected_queue)
        layout.addWidget(btn_delete)

        return panel

    # ── Panel derecho: Detalle de cola ─────────────────────────────

    def _build_queue_detail_panel(self) -> QFrame:
        """Construye el panel con detalle de la cola seleccionada."""
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header con info de la cola
        self._detail_header = QLabel("Selecciona una cola para ver sus detalles")
        self._detail_header.setFont(QFont("Inter", 14, QFont.Weight.Bold))
        self._detail_header.setStyleSheet(f"color: {TEXT_DARK}; border: none;")
        layout.addWidget(self._detail_header)

        self._detail_info = QLabel("")
        self._detail_info.setFont(QFont("Inter", 12))
        self._detail_info.setStyleSheet(f"color: {TEXT_LIGHT}; border: none;")
        layout.addWidget(self._detail_info)

        # Tabla de ítems de la cola
        self._detail_table = QTableWidget()
        self._detail_table.setColumnCount(6)
        self._detail_table.setHorizontalHeaderLabels([
            "#", "NOMBRE", "GRADO", "GRUPO", "ESTADO", "",
        ])

        h = self._detail_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self._detail_table.setColumnWidth(0, 50)
        self._detail_table.setColumnWidth(2, 70)
        self._detail_table.setColumnWidth(3, 70)
        self._detail_table.setColumnWidth(4, 140)
        self._detail_table.setColumnWidth(5, 50)

        self._detail_table.verticalHeader().setVisible(False)
        self._detail_table.setShowGrid(False)
        self._detail_table.setAlternatingRowColors(True)
        self._detail_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._detail_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._detail_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {CARD_BG};
                border: none;
                font-family: 'Inter', sans-serif;
                font-size: 13px;
                color: {TEXT_DARK};
            }}
            QTableWidget::item {{
                padding: 8px 6px;
                border-bottom: 1px solid {BORDER};
            }}
            QTableWidget::item:selected {{
                background-color: #FEE2E2;
                color: {TEXT_DARK};
            }}
            QTableWidget::item:alternate {{
                background-color: {MAIN_BG};
            }}
            QHeaderView::section {{
                background-color: {MAIN_BG};
                color: {TEXT_LIGHT};
                font-size: 11px;
                font-weight: 600;
                padding: 8px 6px;
                border: none;
                border-bottom: 2px solid {BORDER};
            }}
        """)

        layout.addWidget(self._detail_table, stretch=1)

        # Botones de acción
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        action_bar.addStretch()

        # Actualizar PDFs (borra los anteriores y regenera con la plantilla vigente)
        self._btn_update_pdfs = QPushButton()
        self._btn_update_pdfs.setIcon(qta.icon("fa5s.sync-alt", color=TEXT_DARK))
        self._btn_update_pdfs.setIconSize(QSize(16, 16))
        self._btn_update_pdfs.setText("  Actualizar PDFs")
        self._btn_update_pdfs.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_update_pdfs.setStyleSheet(self._action_btn_style(False))
        self._btn_update_pdfs.clicked.connect(self._update_queue_pdfs)
        action_bar.addWidget(self._btn_update_pdfs)

        # Copiar cola (duplica la cola eligiendo la plantilla a aplicar)
        self._btn_copy_queue = QPushButton()
        self._btn_copy_queue.setIcon(qta.icon("fa5s.copy", color=TEXT_DARK))
        self._btn_copy_queue.setIconSize(QSize(16, 16))
        self._btn_copy_queue.setText("  Copiar cola")
        self._btn_copy_queue.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_copy_queue.setStyleSheet(self._action_btn_style(False))
        self._btn_copy_queue.clicked.connect(self._copy_selected_queue)
        action_bar.addWidget(self._btn_copy_queue)

        # Abrir Frente (abre el PDF de frentes guardado en el visor del sistema)
        self._btn_print_front = QPushButton()
        self._btn_print_front.setIcon(qta.icon("fa5s.external-link-alt", color="#FFFFFF"))
        self._btn_print_front.setIconSize(QSize(16, 16))
        self._btn_print_front.setText("  Abrir Frente")
        self._btn_print_front.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_print_front.setStyleSheet(self._action_btn_style(True))
        self._btn_print_front.clicked.connect(lambda: self._open_side_pdf("frente"))
        action_bar.addWidget(self._btn_print_front)

        # Abrir Vuelta (abre el PDF de vueltas guardado en el visor del sistema)
        self._btn_print_back = QPushButton()
        self._btn_print_back.setIcon(qta.icon("fa5s.external-link-alt", color="#FFFFFF"))
        self._btn_print_back.setIconSize(QSize(16, 16))
        self._btn_print_back.setText("  Abrir Vuelta")
        self._btn_print_back.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_print_back.setStyleSheet(self._action_btn_style(True))
        self._btn_print_back.clicked.connect(lambda: self._open_side_pdf("vuelta"))
        action_bar.addWidget(self._btn_print_back)

        # Marcar impresas (notifica a la API: bulk-mark-ready)
        self._btn_mark_ready = QPushButton()
        self._btn_mark_ready.setIcon(qta.icon("fa5s.check-circle", color=TEXT_DARK))
        self._btn_mark_ready.setIconSize(QSize(16, 16))
        self._btn_mark_ready.setText("  Marcar impresas")
        self._btn_mark_ready.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_mark_ready.setStyleSheet(self._action_btn_style(False))
        self._btn_mark_ready.clicked.connect(self._mark_queue_ready)
        action_bar.addWidget(self._btn_mark_ready)

        layout.addLayout(action_bar)

        return panel

    @staticmethod
    def _action_btn_style(primary: bool) -> str:
        """Genera stylesheet para botones de acción."""
        if primary:
            return f"""
                QPushButton {{
                    background-color: {PRIMARY};
                    border: none;
                    border-radius: 8px;
                    padding: 10px 16px;
                    color: #FFFFFF;
                    font-size: 13px;
                    font-weight: 600;
                }}
                QPushButton:hover {{ background-color: #E04848; }}
                QPushButton:pressed {{ background-color: #C73E3E; }}
                QPushButton:disabled {{ background-color: {BORDER}; color: {TEXT_LIGHT}; }}
            """
        return f"""
            QPushButton {{
                background-color: transparent;
                border: 2px solid {BORDER};
                border-radius: 8px;
                padding: 10px 16px;
                color: {TEXT_DARK};
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {PRIMARY};
                color: {PRIMARY};
            }}
        """

    # ── Handlers ───────────────────────────────────────────────────

    def _on_queue_selected(self, current: QListWidgetItem | None, _prev) -> None:
        """Maneja la selección de una cola en la lista."""
        if current is None:
            self._selected_cola_id = None
            self._detail_header.setText("Selecciona una cola para ver sus detalles")
            self._detail_info.setText("")
            self._detail_table.setRowCount(0)
            return

        cola_id = current.data(Qt.ItemDataRole.UserRole)
        self._selected_cola_id = cola_id
        self._load_queue_detail(cola_id)

    @staticmethod
    def _escuelas_por_cola(session, cola_ids: list[int]) -> dict[int, str]:
        """Mapa ``cola_id -> nombre de la escuela`` (cliente) de cada cola.

        La cola no guarda la escuela; se resuelve a través de la plantilla de
        sus ítems (``ItemCola -> Plantilla -> Cliente``). Una cola usa una sola
        plantilla, así que basta el primer ítem; se toma el primero por cola.
        Las colas vacías o cuya plantilla/cliente ya no existan quedan fuera
        del mapa (el llamador usa un texto de respaldo).
        """
        from credencializacion.db.models import ItemCola, Plantilla, Cliente

        if not cola_ids:
            return {}

        filas = (
            session.query(ItemCola.cola_id, Cliente.nombre)
            .join(Plantilla, ItemCola.plantilla_id == Plantilla.id)
            .join(Cliente, Plantilla.cliente_id == Cliente.id)
            .filter(ItemCola.cola_id.in_(cola_ids))
            .order_by(ItemCola.cola_id, ItemCola.orden)
            .all()
        )
        escuelas: dict[int, str] = {}
        for cid, nombre in filas:
            escuelas.setdefault(cid, nombre)
        return escuelas

    def _load_queue_detail(self, cola_id: int) -> None:
        """Carga los detalles de una cola en el panel derecho."""
        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion, ItemCola

        try:
            with DatabaseSession() as session:
                cola = session.query(ColaImpresion).filter_by(id=cola_id).first()
                if not cola:
                    return

                escuela = self._escuelas_por_cola(session, [cola_id]).get(
                    cola_id, "Escuela desconocida"
                )
                self._detail_header.setText(f"📋 {cola.nombre}")
                estado = cola.estado_label
                fecha = cola.created_at.strftime("%d/%m/%Y %H:%M") if cola.created_at else ""
                self._detail_info.setText(
                    f"🏫 {escuela}  •  Estado: {estado}  •  "
                    f"Registros: {cola.total_registros}  •  Creada: {fecha}"
                )

                # Cargar ítems
                items = (
                    session.query(ItemCola)
                    .filter_by(cola_id=cola_id)
                    .order_by(ItemCola.orden)
                    .all()
                )

                self._detail_table.setRowCount(len(items))
                for row, item in enumerate(items):
                    # # (orden)
                    orden_item = QTableWidgetItem(str(item.orden))
                    orden_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    orden_item.setFont(QFont("Inter", 11))
                    self._detail_table.setItem(row, 0, orden_item)

                    # Nombre
                    nombre = ""
                    if item.registro:
                        datos = item.registro.datos or {}
                        nombre = f"{datos.get('nombre', '')} {datos.get('apellido', '')}".strip()
                    name_item = QTableWidgetItem(nombre or "Sin nombre")
                    name_item.setFont(QFont("Inter", 12, QFont.Weight.DemiBold))
                    self._detail_table.setItem(row, 1, name_item)

                    # Grado
                    grado = ""
                    if item.registro:
                        grado = (item.registro.datos or {}).get("grado", "")
                    grado_item = QTableWidgetItem(str(grado))
                    grado_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._detail_table.setItem(row, 2, grado_item)

                    # Grupo
                    grupo = ""
                    if item.registro:
                        grupo = (item.registro.datos or {}).get("grupo", "")
                    grupo_item = QTableWidgetItem(str(grupo))
                    grupo_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._detail_table.setItem(row, 3, grupo_item)

                    # Estado
                    estado_labels = {
                        "pendiente": "⏳ Pendiente",
                        "frente_impreso": "📄 Frente",
                        "vuelta_impresa": "📄 Vuelta",
                        "completado": "✅ Listo",
                    }
                    estado_item = QTableWidgetItem(
                        estado_labels.get(item.estado_item, item.estado_item)
                    )
                    estado_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    estado_item.setFont(QFont("Inter", 11))
                    self._detail_table.setItem(row, 4, estado_item)

                    # Botón para quitar el ítem de la cola
                    btn_remove = QPushButton()
                    btn_remove.setIcon(qta.icon("fa5s.times-circle", color=ERROR))
                    btn_remove.setIconSize(QSize(16, 16))
                    btn_remove.setToolTip("Quitar de la cola")
                    btn_remove.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    btn_remove.setStyleSheet("""
                        QPushButton {
                            background-color: transparent;
                            border: none;
                            padding: 4px;
                        }
                        QPushButton:hover { background-color: #FEE2E2; border-radius: 6px; }
                    """)
                    btn_remove.clicked.connect(
                        lambda _=False, iid=item.id, nom=nombre: self._remove_queue_item(iid, nom)
                    )
                    cell = QWidget()
                    cell_layout = QHBoxLayout(cell)
                    cell_layout.setContentsMargins(0, 0, 0, 0)
                    cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    cell_layout.addWidget(btn_remove)
                    self._detail_table.setCellWidget(row, 5, cell)

                    self._detail_table.setRowHeight(row, 42)

        except Exception as e:
            logger.error("Error al cargar detalle de cola: %s", e)
            self.set_status(f"❌ Error al cargar cola: {e}", "error")

    def _delete_selected_queue(self) -> None:
        """Elimina la cola seleccionada."""
        if not self._selected_cola_id:
            self.set_status("⚠️ Selecciona una cola para eliminar", "warning")
            return

        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion

        try:
            with DatabaseSession() as session:
                cola = session.query(ColaImpresion).filter_by(
                    id=self._selected_cola_id
                ).first()
                if cola:
                    nombre = cola.nombre
                    session.delete(cola)
                    session.commit()
                    self.set_status(f"🗑️ Cola '{nombre}' eliminada", "info")

            self._selected_cola_id = None
            self.refresh_queues()

        except Exception as e:
            self.set_status(f"❌ Error al eliminar: {e}", "error")

    def _remove_queue_item(self, item_id: int, nombre: str) -> None:
        """Quita un ítem de la cola seleccionada (no regenera PDFs).

        Los PDFs quedan desactualizados hasta pulsar "Actualizar PDFs",
        que renumera el orden (1..n) y los regenera.
        """
        if self._render_worker is not None:
            self.set_status("⏳ Espera a que termine la generación en curso", "warning", toast=False)
            return

        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion, ItemCola

        reply = QMessageBox.question(
            self,
            "Quitar de la cola",
            f"¿Quitar a «{nombre or 'este registro'}» de la cola?\n\n"
            "Los PDFs actuales quedarán desactualizados hasta que pulses "
            "«Actualizar PDFs».",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            with DatabaseSession() as session:
                item = session.query(ItemCola).get(item_id)
                if item is None:
                    return
                restantes = (
                    session.query(ItemCola)
                    .filter_by(cola_id=item.cola_id)
                    .count()
                )
                if restantes <= 1:
                    self.set_status(
                        "⚠️ Es el último registro de la cola; usa «Eliminar Cola»",
                        "warning",
                    )
                    return
                cola = session.query(ColaImpresion).get(item.cola_id)
                session.delete(item)
                if cola is not None:
                    cola.total_registros = restantes - 1
                session.commit()
        except Exception as e:
            self.set_status(f"❌ Error al quitar el registro: {e}", "error")
            return

        self.set_status(
            f"🗑️ «{nombre or 'Registro'}» quitado — pulsa «Actualizar PDFs» para regenerar",
            "info",
        )
        self.refresh_queues(keep_selection=True)

    def _update_queue_pdfs(self) -> None:
        """Regenera los PDFs de la cola con la configuración vigente de su plantilla.

        Borra los PDFs anteriores del disco, renumera el orden de los ítems
        (1..n, por si se quitaron registros) y vuelve a renderizar en segundo
        plano con la plantilla que la cola tiene guardada — que es la de la
        escuela y ya incluye los cambios hechos en el editor. El estado de la
        cola no se modifica.
        """
        if not self._selected_cola_id:
            self.set_status("⚠️ Selecciona una cola primero", "warning")
            return
        if self._render_worker is not None:
            self.set_status("⏳ Ya hay una generación en curso...", "warning", toast=False)
            return

        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion, ItemCola

        cola_id = self._selected_cola_id

        reply = QMessageBox.question(
            self,
            "Actualizar PDFs",
            "Se eliminarán los PDFs actuales y se regenerarán con la "
            "configuración vigente de la plantilla.\n\n¿Continuar?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            with DatabaseSession() as session:
                cola = session.query(ColaImpresion).get(cola_id)
                if cola is None:
                    self.set_status("⚠️ Cola no encontrada", "warning")
                    return
                items = (
                    session.query(ItemCola)
                    .filter_by(cola_id=cola_id)
                    .order_by(ItemCola.orden)
                    .all()
                )
                if not items:
                    self.set_status("⚠️ La cola está vacía", "warning")
                    return

                # Renumerar el orden (1..n) tras posibles registros quitados
                for nuevo_orden, item in enumerate(items, start=1):
                    item.orden = nuevo_orden
                cola.total_registros = len(items)

                # Borrar los PDFs anteriores del disco y limpiar sus rutas
                for pdf in (cola.pdf_frente_path, cola.pdf_vuelta_path):
                    if pdf:
                        Path(pdf).unlink(missing_ok=True)
                cola.pdf_frente_path = None
                cola.pdf_vuelta_path = None

                record_ids = [it.registro_id for it in items]
                plantilla_id = items[0].plantilla_id
                session.commit()
        except Exception as e:
            self.set_status(f"❌ Error al preparar la actualización: {e}", "error")
            return

        from credencializacion.utils.paths import get_cola_pdf_dir

        self.set_status("🔄 Actualizando PDFs de la cola...", "info", toast=False)
        self._start_render(
            record_ids,
            plantilla_id,
            str(get_cola_pdf_dir(cola_id)),
            lambda f, v: self._on_queue_pdfs_ready(
                cola_id, f, v, "✅ PDFs actualizados con la plantilla vigente"
            ),
        )

    def _copy_selected_queue(self) -> None:
        """Copia la cola seleccionada permitiendo elegir otra plantilla.

        Crea una cola nueva (estado pendiente) con los mismos registros en el
        mismo orden, aplicando la plantilla elegida en el diálogo, y genera
        sus PDFs en su propia carpeta. La cola original queda intacta.
        """
        if not self._selected_cola_id:
            self.set_status("⚠️ Selecciona una cola primero", "warning")
            return
        if self._render_worker is not None:
            self.set_status("⏳ Ya hay una generación en curso...", "warning", toast=False)
            return

        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion, ItemCola, Plantilla

        cola_id = self._selected_cola_id
        try:
            with DatabaseSession() as session:
                cola = session.query(ColaImpresion).get(cola_id)
                items = (
                    session.query(ItemCola)
                    .filter_by(cola_id=cola_id)
                    .order_by(ItemCola.orden)
                    .all()
                )
                if cola is None or not items:
                    self.set_status("⚠️ La cola está vacía", "warning")
                    return
                plantilla_actual = session.query(Plantilla).get(items[0].plantilla_id)
                if plantilla_actual is None:
                    self.set_status("⚠️ La plantilla de la cola ya no existe", "warning")
                    return
                plantillas = (
                    session.query(Plantilla)
                    .filter_by(cliente_id=plantilla_actual.cliente_id)
                    .order_by(Plantilla.nombre)
                    .all()
                )
                opciones = [(p.id, p.nombre) for p in plantillas]
                nombre_original = cola.nombre
                plantilla_actual_id = plantilla_actual.id
                record_ids = [it.registro_id for it in items]
        except Exception as e:
            self.set_status(f"❌ Error al leer la cola: {e}", "error")
            return

        dlg = CopyQueueDialog(nombre_original, opciones, plantilla_actual_id, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        nuevo_nombre, plantilla_id = dlg.result_values()
        if not plantilla_id:
            self.set_status("⚠️ Selecciona una plantilla", "warning")
            return

        try:
            with DatabaseSession() as session:
                nueva = ColaImpresion(
                    nombre=nuevo_nombre,
                    total_registros=len(record_ids),
                )
                session.add(nueva)
                session.flush()
                for orden, reg_id in enumerate(record_ids, start=1):
                    session.add(
                        ItemCola(
                            cola_id=nueva.id,
                            registro_id=reg_id,
                            plantilla_id=plantilla_id,
                            orden=orden,
                        )
                    )
                session.commit()
                nueva_id = nueva.id
        except Exception as e:
            self.set_status(f"❌ Error al copiar la cola: {e}", "error")
            return

        from credencializacion.utils.paths import get_cola_pdf_dir

        self.refresh_queues(keep_selection=True)
        self.set_status("📋 Generando PDFs de la copia...", "info", toast=False)

        def _on_copy_done(frentes: str, vueltas: str) -> None:
            # Seleccionar la copia al terminar para verla de inmediato
            self._selected_cola_id = nueva_id
            self._on_queue_pdfs_ready(
                nueva_id, frentes, vueltas, "✅ Cola copiada y PDFs generados"
            )

        self._start_render(
            record_ids,
            plantilla_id,
            str(get_cola_pdf_dir(nueva_id)),
            _on_copy_done,
        )

    def _on_queue_pdfs_ready(
        self, cola_id: int, frentes_pdf: str, vueltas_pdf: str, mensaje: str
    ) -> None:
        """Guarda las rutas de los PDFs regenerados y refresca la vista."""
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

        self.set_status(mensaje, "success")
        self.refresh_queues(keep_selection=True)

    # ── Render en segundo plano ─────────────────────────────────────

    def _start_render(self, record_ids, plantilla_id, out_dir, on_done) -> None:
        """Lanza un ``QueueRenderWorker`` y enruta sus señales.

        ``on_done`` se invoca en el hilo principal con (frentes_pdf,
        vueltas_pdf) cuando el render termina correctamente.
        """
        from credencializacion.ui.render_worker import QueueRenderWorker

        self._render_on_done = on_done
        self._render_worker = QueueRenderWorker(record_ids, plantilla_id, out_dir)
        self._render_worker.progress.connect(
            lambda m: self.set_status(m, "info", toast=False)
        )
        self._render_worker.finished_ok.connect(self._on_render_ok)
        self._render_worker.failed.connect(self._on_render_failed)
        self._render_worker.omitidos.connect(self._on_render_omitidos)
        self._render_worker.finished.connect(self._cleanup_render_worker)
        self._set_render_buttons_enabled(False)
        self._render_worker.start()

    def _on_render_ok(self, frentes_pdf: str, vueltas_pdf: str) -> None:
        cb = self._render_on_done
        if cb is not None:
            cb(frentes_pdf, vueltas_pdf)

    def _on_render_failed(self, message: str) -> None:
        self.set_status(f"❌ Error al generar PDFs: {message}", "error")

    def _on_render_omitidos(self, reporte: dict) -> None:
        """Informa qué registros quedaron fuera de los PDFs y por qué."""
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
            )

        if colapsados:
            self.set_status(
                f"ℹ️ {len(colapsados)} hermano(s) omitido(s): ya se incluyen en la "
                f"credencial de su familia ({', '.join(colapsados[:5])}"
                f"{' y más' if len(colapsados) > 5 else ''}).",
                "info",
            )

    def _cleanup_render_worker(self) -> None:
        self._render_worker = None
        self._render_on_done = None
        self._set_render_buttons_enabled(True)

    def _set_render_buttons_enabled(self, enabled: bool) -> None:
        self._btn_update_pdfs.setEnabled(enabled)
        self._btn_copy_queue.setEnabled(enabled)

    def _open_side_pdf(self, cara: str) -> None:
        """Abre el PDF guardado (frente o vuelta) de la cola en el visor del SO."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        if not self._selected_cola_id:
            self.set_status("⚠️ Selecciona una cola primero", "warning")
            return

        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion

        try:
            with DatabaseSession() as session:
                cola = session.query(ColaImpresion).filter_by(
                    id=self._selected_cola_id
                ).first()
                if cola is None:
                    self.set_status("⚠️ Cola no encontrada", "warning")
                    return
                pdf_path = (
                    cola.pdf_frente_path if cara == "frente" else cola.pdf_vuelta_path
                )

            cara_label = "frente" if cara == "frente" else "vuelta"
            if not pdf_path or not Path(pdf_path).exists():
                self.set_status(
                    f"⚠️ No hay PDF de {cara_label} guardado para esta cola",
                    "warning",
                )
                return

            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf_path)))
            if opened:
                self.set_status(f"📄 Abriendo {cara_label} en el visor del sistema", "info", toast=False)
            else:
                self.set_status(f"❌ No se pudo abrir el PDF de {cara_label}", "error")
        except Exception as e:
            logger.error("Error al abrir PDF de cola: %s", e)
            self.set_status(f"❌ Error al abrir PDF: {e}", "error")

    def _mark_queue_ready(self) -> None:
        """Marca las credenciales de la cola como 'Listas/Impresas' en la API.

        Recolecta los ``student_id`` de los registros de la cola y hace el POST
        a ``bulk-mark-ready`` en segundo plano. Al confirmar, marca la cola como
        completada localmente.
        """
        if not self._selected_cola_id:
            self.set_status("⚠️ Selecciona una cola primero", "warning")
            return

        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion, ItemCola

        try:
            with DatabaseSession() as session:
                items = (
                    session.query(ItemCola)
                    .filter_by(cola_id=self._selected_cola_id)
                    .order_by(ItemCola.orden)
                    .all()
                )
                if not items:
                    self.set_status("⚠️ La cola está vacía", "warning")
                    return

                student_ids: list[int] = []
                cliente_id = None
                for it in items:
                    reg = it.registro
                    if reg is None:
                        continue
                    if cliente_id is None:
                        cliente_id = reg.cliente_id
                    sid = (reg.datos or {}).get("student_id")
                    if sid in (None, ""):
                        continue
                    try:
                        student_ids.append(int(sid))
                    except (TypeError, ValueError):
                        continue
        except Exception as e:
            self.set_status(f"❌ Error al leer la cola: {e}", "error")
            return

        if not student_ids:
            self.set_status(
                "⚠️ Los registros no tienen student_id (vuelve a sincronizar)",
                "warning",
            )
            return

        base_url, api_key = self._client_api_credentials(cliente_id)

        from credencializacion.ui.status_worker import BulkMarkWorker

        cola_id = self._selected_cola_id
        worker = BulkMarkWorker(base_url, api_key, "ready", student_ids)
        self._mark_workers.append(worker)
        self.set_status("🔔 Marcando credenciales como impresas...", "info", toast=False)

        def _on_done(success: bool, message: str, updated: int) -> None:
            if success:
                self._mark_cola_completed(cola_id)
                self.set_status(
                    f"✅ {updated} credenciales marcadas como impresas", "success"
                )
                self.refresh_queues()
            else:
                self.set_status(
                    f"⚠️ No se pudo actualizar el estatus en la API: {message}",
                    "warning",
                )
            if worker in self._mark_workers:
                self._mark_workers.remove(worker)

        worker.done.connect(_on_done)
        worker.start()

    def _mark_cola_completed(self, cola_id: int) -> None:
        """Marca la cola como completada localmente."""
        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion

        try:
            with DatabaseSession() as session:
                cola = session.query(ColaImpresion).get(cola_id)
                if cola is not None:
                    cola.estado = "completada"
                    session.commit()
        except Exception as e:  # noqa: BLE001
            logger.error("No se pudo marcar la cola como completada: %s", e)

    @staticmethod
    def _client_api_credentials(cliente_id) -> tuple[str, str]:
        """Devuelve (base_url, api_key) del Cliente, con fallback a constantes."""
        base_url = "https://app.miescuela.net"
        api_key = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
        if cliente_id is None:
            return base_url, api_key
        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Cliente

        try:
            with get_session() as session:
                cliente = session.query(Cliente).get(cliente_id)
                if cliente is not None:
                    base_url = cliente.api_base_url or base_url
                    api_key = cliente.api_key or api_key
        except Exception:  # noqa: BLE001
            pass
        return base_url, api_key

    def _compute_fondo_overrides(self, session, items, cara: str) -> list[str | None]:
        """Calcula la imagen de fondo por ítem para un lado (multiplantillaje).

        Para cada ítem, si su diseño tiene `ConfiguracionLado` para ese lado, se
        evalúan las variantes contra los datos del registro y se devuelve la ruta
        elegida; si no hay configuración, se devuelve ``None`` (el render usa la
        imagen base del diseño). La config de cada diseño se cachea por id.
        """
        from credencializacion.db.repositories import LadoConfigRepository
        from credencializacion.services.image_selection import select_imagen

        cache: dict[int, object] = {}
        overrides: list[str | None] = []
        for item in items:
            pid = item.plantilla_id
            if pid not in cache:
                cache[pid] = LadoConfigRepository.get_config_lado(session, pid, cara)
            config = cache[pid]
            if config is None:
                overrides.append(None)
            else:
                overrides.append(select_imagen(item.registro.datos or {}, config))
        return overrides

    # ── Métodos públicos ───────────────────────────────────────────

    def refresh_queues(self, keep_selection: bool = False) -> None:
        """Recarga la lista de colas desde la BD.

        Con ``keep_selection`` se re-selecciona la cola que estaba activa
        (si sigue existiendo) para no perder el detalle en pantalla.
        """
        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion

        selected_id = self._selected_cola_id if keep_selection else None
        self._queue_list.clear()

        try:
            with DatabaseSession() as session:
                colas = (
                    session.query(ColaImpresion)
                    .order_by(ColaImpresion.created_at.desc())
                    .all()
                )

                total = len(colas)
                active = sum(1 for c in colas if c.estado not in ("completada", "error"))
                complete = sum(1 for c in colas if c.estado == "completada")
                total_regs = sum(c.total_registros for c in colas)

                self._card_total.set_value(total)
                self._card_active.set_value(active)
                self._card_complete.set_value(complete)
                self._card_registros.set_value(total_regs)

                escuelas = self._escuelas_por_cola(session, [c.id for c in colas])

                for cola in colas:
                    item = QListWidgetItem()
                    item.setData(Qt.ItemDataRole.UserRole, cola.id)

                    # Formato: ícono estado + nombre + escuela + conteo
                    estado_icons = {
                        "pendiente": "⏳",
                        "frentes_impresos": "📄",
                        "vueltas_impresas": "📄",
                        "completada": "✅",
                        "error": "❌",
                    }
                    icon = estado_icons.get(cola.estado, "❓")
                    fecha = cola.created_at.strftime("%d/%m %H:%M") if cola.created_at else ""
                    escuela = escuelas.get(cola.id, "Escuela desconocida")
                    item.setText(
                        f"{icon} {cola.nombre}\n"
                        f"      🏫 {escuela}\n"
                        f"      {fecha} · {cola.total_registros} reg."
                    )
                    item.setSizeHint(QSize(0, 68))

                    self._queue_list.addItem(item)
                    if selected_id is not None and cola.id == selected_id:
                        self._queue_list.setCurrentItem(item)

        except Exception as e:
            logger.error("Error al cargar colas: %s", e)
            self.set_status(f"❌ Error al cargar colas: {e}", "error")

    def set_status(self, message: str, level: str = "info", toast: bool = True) -> None:
        """Actualiza la barra de estado y, opcionalmente, muestra un toast.

        Args:
            message: Texto a mostrar.
            level: 'info', 'success', 'warning', 'error'.
            toast: Si es True (por defecto) muestra una notificación toast.
                   Usar False para pasos intermedios de un flujo de carga: el
                   progreso se refleja solo en el footer y se reserva el toast
                   para el resultado final.
        """
        from credencializacion.ui.widgets.toast import ToastManager
        colors = {
            "info": TEXT_LIGHT,
            "success": SUCCESS,
            "warning": WARNING,
            "error": ERROR,
            "sync": PRIMARY,
        }
        color = colors.get(level, TEXT_LIGHT)
        self._status_bar.setText(message)
        self._status_bar.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 600;
            }}
        """)
        # Toast notification (solo resultado final)
        if toast:
            ToastManager.instance().show_toast(message, level)

    def show_progress(self, current: int, total: int) -> None:
        """Muestra/actualiza la barra de progreso."""
        self._progress_frame.setVisible(True)
        self._lbl_progress_count.setText(f"{current} / {total}")
        if total > 0:
            self._progress_bar.setValue(int((current / total) * 100))
        if current >= total:
            self._lbl_progress.setText("✅  Impresión completada")

    def hide_progress(self) -> None:
        """Oculta la barra de progreso."""
        self._progress_frame.setVisible(False)
        self._progress_bar.setValue(0)
        self._lbl_progress.setText("🖨  Imprimiendo...")
