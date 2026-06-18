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
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Construye el layout del centro de impresión."""
        self.setStyleSheet(f"background-color: {MAIN_BG};")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 16, 24, 8)
        main_layout.setSpacing(12)

        # ── Header ─────────────────────────────────────────────────
        header = QHBoxLayout()
        lbl_title = QLabel("Centro de Impresión")
        lbl_title.setFont(QFont("Inter", 20, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {TEXT_DARK};")
        header.addWidget(lbl_title)
        header.addStretch()

        btn_refresh = QPushButton()
        btn_refresh.setIcon(qta.icon("fa5s.sync-alt", color=TEXT_DARK))
        btn_refresh.setIconSize(QSize(16, 16))
        btn_refresh.setText("  Actualizar")
        btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_refresh.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 2px solid {BORDER};
                border-radius: 8px;
                padding: 8px 16px;
                color: {TEXT_DARK};
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {PRIMARY};
                color: {PRIMARY};
            }}
        """)
        btn_refresh.clicked.connect(self.refresh_queues)
        header.addWidget(btn_refresh)

        main_layout.addLayout(header)

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
        self._detail_table.setColumnCount(5)
        self._detail_table.setHorizontalHeaderLabels([
            "#", "NOMBRE", "GRADO", "GRUPO", "ESTADO",
        ])

        h = self._detail_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self._detail_table.setColumnWidth(0, 50)
        self._detail_table.setColumnWidth(2, 70)
        self._detail_table.setColumnWidth(3, 70)
        self._detail_table.setColumnWidth(4, 140)

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

        # Combo de impresora
        self._combo_printer = QComboBox()
        self._combo_printer.addItem("Seleccionar impresora...")
        self._combo_printer.setMinimumWidth(200)
        self._combo_printer.setStyleSheet(f"""
            QComboBox {{
                background-color: {MAIN_BG};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
                color: {TEXT_DARK};
            }}
            QComboBox:hover {{
                border-color: {PRIMARY};
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
        """)
        action_bar.addWidget(self._combo_printer)

        action_bar.addStretch()

        # Vista Previa
        self._btn_preview = QPushButton()
        self._btn_preview.setIcon(qta.icon("fa5s.eye", color=TEXT_DARK))
        self._btn_preview.setIconSize(QSize(16, 16))
        self._btn_preview.setText("  Vista Previa")
        self._btn_preview.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_preview.setStyleSheet(self._action_btn_style(False))
        self._btn_preview.clicked.connect(self._preview_queue)
        action_bar.addWidget(self._btn_preview)

        # Imprimir Frentes
        self._btn_print_front = QPushButton()
        self._btn_print_front.setIcon(qta.icon("fa5s.print", color="#FFFFFF"))
        self._btn_print_front.setIconSize(QSize(16, 16))
        self._btn_print_front.setText("  Imprimir Frentes")
        self._btn_print_front.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_print_front.setStyleSheet(self._action_btn_style(True))
        self._btn_print_front.clicked.connect(lambda: self._print_queue("frente"))
        action_bar.addWidget(self._btn_print_front)

        # Imprimir Vueltas
        self._btn_print_back = QPushButton()
        self._btn_print_back.setIcon(qta.icon("fa5s.print", color="#FFFFFF"))
        self._btn_print_back.setIconSize(QSize(16, 16))
        self._btn_print_back.setText("  Imprimir Vueltas")
        self._btn_print_back.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_print_back.setStyleSheet(self._action_btn_style(True))
        self._btn_print_back.clicked.connect(lambda: self._print_queue("vuelta"))
        action_bar.addWidget(self._btn_print_back)

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

    def _load_queue_detail(self, cola_id: int) -> None:
        """Carga los detalles de una cola en el panel derecho."""
        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion, ItemCola

        try:
            with DatabaseSession() as session:
                cola = session.query(ColaImpresion).filter_by(id=cola_id).first()
                if not cola:
                    return

                self._detail_header.setText(f"📋 {cola.nombre}")
                estado = cola.estado_label
                fecha = cola.created_at.strftime("%d/%m/%Y %H:%M") if cola.created_at else ""
                self._detail_info.setText(
                    f"Estado: {estado}  •  Registros: {cola.total_registros}  •  Creada: {fecha}"
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

    def _preview_queue(self) -> None:
        """Muestra vista previa de la cola seleccionada."""
        if not self._selected_cola_id:
            self.set_status("⚠️ Selecciona una cola para vista previa", "warning")
            return

        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion, ItemCola, Plantilla
        from credencializacion.renderer.pdf_engine import PDFEngine
        import tempfile

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

                # Usar la plantilla del primer ítem
                plantilla = items[0].plantilla
                engine = PDFEngine(plantilla)

                # Preparar pares (registro, plantilla)
                render_items = [(item.registro, item.plantilla) for item in items]

                # Generar PDFs temporales
                tmp_dir = Path(tempfile.mkdtemp(prefix="credencial_preview_"))
                frentes_pdf = engine.render_queue(
                    render_items, "frente", tmp_dir / "frentes.pdf"
                )
                vueltas_pdf = engine.render_queue(
                    render_items, "vuelta", tmp_dir / "vueltas.pdf"
                )

            # Abrir diálogo de preview
            from credencializacion.ui.dialogs.preview_dialog import PreviewDialog
            dlg = PreviewDialog(
                frentes_pdf=frentes_pdf,
                vueltas_pdf=vueltas_pdf,
                parent=self,
            )
            dlg.exec()

        except Exception as e:
            logger.error("Error en vista previa: %s", e)
            self.set_status(f"❌ Error en vista previa: {e}", "error")

    def _print_queue(self, cara: str) -> None:
        """Genera PDF e imprime la cara indicada de la cola seleccionada.

        Args:
            cara: 'frente' o 'vuelta'.
        """
        if not self._selected_cola_id:
            self.set_status("⚠️ Selecciona una cola para imprimir", "warning")
            return

        # Validar impresora
        printer_name = self._combo_printer.currentText()
        if (
            not printer_name
            or printer_name == "Seleccionar impresora..."
        ):
            self.set_status("⚠️ Selecciona una impresora", "warning")
            return

        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion, ItemCola
        from credencializacion.renderer.pdf_engine import PDFEngine
        from credencializacion.core.printer import print_pdf
        import tempfile

        try:
            with DatabaseSession() as session:
                cola = session.query(ColaImpresion).filter_by(
                    id=self._selected_cola_id
                ).first()
                if not cola:
                    return

                items = (
                    session.query(ItemCola)
                    .filter_by(cola_id=cola.id)
                    .order_by(ItemCola.orden)
                    .all()
                )
                if not items:
                    self.set_status("⚠️ La cola está vacía", "warning")
                    return

                # Mostrar progreso
                self.show_progress(0, len(items))
                self.set_status(
                    f"🖨 Generando PDF de {cara}s ({len(items)} registros)...",
                    "info",
                )

                # Generar PDF
                plantilla = items[0].plantilla
                engine = PDFEngine(plantilla)
                render_items = [(item.registro, item.plantilla) for item in items]

                tmp_dir = Path(tempfile.mkdtemp(prefix=f"credencial_{cara}_"))
                pdf_path = engine.render_queue(
                    render_items, cara, tmp_dir / f"{cara}s.pdf"
                )

                # Enviar a impresora
                success = print_pdf(pdf_path, printer_name)

                if success:
                    # Actualizar estados
                    new_item_estado = (
                        "frente_impreso" if cara == "frente" else "vuelta_impresa"
                    )
                    for item in items:
                        if cara == "frente" and item.estado_item == "pendiente":
                            item.estado_item = new_item_estado
                        elif cara == "vuelta" and item.estado_item == "frente_impreso":
                            item.estado_item = "completado"

                    # Actualizar estado de la cola
                    if cara == "frente":
                        cola.estado = "frentes_impresos"
                    elif cara == "vuelta" and cola.estado == "frentes_impresos":
                        cola.estado = "completada"
                    cola.impresora = printer_name

                    session.commit()

                    cara_label = "Frentes" if cara == "frente" else "Vueltas"
                    self.set_status(
                        f"✅ {cara_label} enviados a '{printer_name}' ({len(items)} registros)",
                        "success",
                    )
                else:
                    self.set_status(
                        f"❌ Error al enviar a impresora '{printer_name}'",
                        "error",
                    )

                self.show_progress(len(items), len(items))
                self._load_queue_detail(cola.id)
                self.refresh_queues()

        except Exception as e:
            logger.error("Error al imprimir cola: %s", e)
            self.set_status(f"❌ Error de impresión: {e}", "error")
        finally:
            self.hide_progress()

    # ── Métodos públicos ───────────────────────────────────────────

    def refresh_queues(self) -> None:
        """Recarga la lista de colas desde la BD."""
        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import ColaImpresion

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

                for cola in colas:
                    item = QListWidgetItem()
                    item.setData(Qt.ItemDataRole.UserRole, cola.id)

                    # Formato: ícono estado + nombre + conteo
                    estado_icons = {
                        "pendiente": "⏳",
                        "frentes_impresos": "📄",
                        "vueltas_impresas": "📄",
                        "completada": "✅",
                        "error": "❌",
                    }
                    icon = estado_icons.get(cola.estado, "❓")
                    fecha = cola.created_at.strftime("%d/%m %H:%M") if cola.created_at else ""
                    item.setText(f"{icon} {cola.nombre}\n      {fecha} · {cola.total_registros} reg.")
                    item.setSizeHint(QSize(0, 52))

                    self._queue_list.addItem(item)

            # Cargar impresoras
            self._load_printers()

        except Exception as e:
            logger.error("Error al cargar colas: %s", e)
            self.set_status(f"❌ Error al cargar colas: {e}", "error")

    def _load_printers(self) -> None:
        """Carga las impresoras del sistema en el combo."""
        from credencializacion.core.printer import get_system_printers, get_default_printer

        current = self._combo_printer.currentText()
        self._combo_printer.clear()
        self._combo_printer.addItem("Seleccionar impresora...")

        printers = get_system_printers()
        default = get_default_printer()

        for name in printers:
            label = f"⭐ {name}" if name == default else name
            self._combo_printer.addItem(label, userData=name)

        # Restaurar selección previa si existe
        if current and current != "Seleccionar impresora...":
            idx = self._combo_printer.findText(current)
            if idx >= 0:
                self._combo_printer.setCurrentIndex(idx)

    def set_status(self, message: str, level: str = "info") -> None:
        """Actualiza la barra de estado.

        Args:
            message: Texto a mostrar.
            level: 'info', 'success', 'warning', 'error'.
        """
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
