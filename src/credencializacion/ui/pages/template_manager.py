"""
Gestión de Plantillas — permite ver, eliminar y copiar plantillas entre clientes.

Página del sistema que muestra todas las plantillas por cliente con opciones
de eliminar diseños y copiar/asignar configuraciones a otros clientes.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import qtawesome as qta
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QCursor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QFrame,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QMessageBox,
)

if TYPE_CHECKING:
    pass

# ── Paleta de colores ──────────────────────────────────────────────────
PRIMARY = "#FB5252"
SECONDARY = "#FFD057"
TEXT_DARK = "#171A2B"
TEXT_LIGHT = "#64748B"
CARD_BG = "#FFFFFF"
BORDER = "#E2E8F0"
MAIN_BG = "#F5F7FA"
SUCCESS = "#22C55E"


class TemplateManager(QWidget):
    """Página de gestión de plantillas.

    Permite:
    - Ver todas las plantillas de un cliente
    - Eliminar plantillas
    - Copiar plantillas a otro cliente
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plantilla_ids: list[int] = []
        self._setup_ui()
        self._connect_signals()
        self._load_clients()

    # ── UI ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"background-color: {MAIN_BG};")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Card principal
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        # ── Fila de filtros ──
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        combo_style = f"""
            QComboBox {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                color: {TEXT_DARK};
                min-height: 36px;
            }}
            QComboBox:hover {{
                border-color: {TEXT_LIGHT};
            }}
            QComboBox:focus {{
                border-color: {PRIMARY};
                background-color: {CARD_BG};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 28px;
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
                border-radius: 8px;
                selection-background-color: #EFF6FF;
                selection-color: {TEXT_DARK};
                padding: 4px;
                font-size: 13px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 12px;
                min-height: 32px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: #EFF6FF;
            }}
        """

        lbl_src = QLabel("Cliente:")
        lbl_src.setStyleSheet(f"color: {TEXT_DARK}; font-size: 13px; font-weight: 600;")
        filter_row.addWidget(lbl_src)

        self._combo_clients = QComboBox()
        self._combo_clients.setEditable(True)
        self._combo_clients.lineEdit().setPlaceholderText("Seleccionar escuela...")
        self._combo_clients.setCurrentIndex(-1)
        self._combo_clients.setStyleSheet(combo_style)
        filter_row.addWidget(self._combo_clients, stretch=1)

        filter_row.addSpacing(20)

        # Combo destino para copiar
        lbl_dest = QLabel("Copiar a:")
        lbl_dest.setStyleSheet(f"color: {TEXT_LIGHT}; font-size: 13px;")
        filter_row.addWidget(lbl_dest)

        self._combo_dest = QComboBox()
        self._combo_dest.setEditable(True)
        self._combo_dest.lineEdit().setPlaceholderText("Escuela destino...")
        self._combo_dest.setCurrentIndex(-1)
        self._combo_dest.setStyleSheet(combo_style)
        filter_row.addWidget(self._combo_dest, stretch=1)

        card_layout.addLayout(filter_row)

        # ── Separador ──
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet(f"background-color: {BORDER}; max-height: 1px;")
        card_layout.addWidget(separator)

        # ── Tabla de plantillas ──
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            "Nombre", "Tipo", "Orientación", "Dimensiones", "Fecha Creación"
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for i in range(1, 5):
            self._table.horizontalHeader().setSectionResizeMode(
                i, QHeaderView.ResizeMode.ResizeToContents
            )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 8px;
                gridline-color: {BORDER};
                font-size: 13px;
            }}
            QTableWidget::item {{
                padding: 8px 12px;
                border-bottom: 1px solid {BORDER};
            }}
            QTableWidget::item:selected {{
                background-color: #EFF6FF;
                color: {TEXT_DARK};
            }}
            QHeaderView::section {{
                background-color: #F8FAFC;
                color: {TEXT_LIGHT};
                font-weight: 600;
                font-size: 12px;
                padding: 8px 12px;
                border: none;
                border-bottom: 2px solid {BORDER};
            }}
        """)
        card_layout.addWidget(self._table, stretch=1)

        # ── Barra de acciones ──
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        action_row.addStretch()

        btn_style_danger = f"""
            QPushButton {{
                background-color: transparent;
                border: 2px solid #EF4444;
                border-radius: 8px;
                padding: 8px 20px;
                color: #EF4444;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #FEF2F2;
            }}
            QPushButton:disabled {{
                border-color: {BORDER};
                color: {TEXT_LIGHT};
            }}
        """

        btn_style_primary = f"""
            QPushButton {{
                background-color: {PRIMARY};
                border: none;
                border-radius: 8px;
                padding: 8px 20px;
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #E04848;
            }}
            QPushButton:disabled {{
                background-color: {BORDER};
                color: {TEXT_LIGHT};
            }}
        """

        self._btn_delete = QPushButton()
        self._btn_delete.setIcon(qta.icon("fa5s.trash", color="#EF4444"))
        self._btn_delete.setText("Eliminar Plantilla")
        self._btn_delete.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_delete.setMinimumHeight(40)
        self._btn_delete.setStyleSheet(btn_style_danger)
        self._btn_delete.setEnabled(False)
        action_row.addWidget(self._btn_delete)

        self._btn_copy = QPushButton()
        self._btn_copy.setIcon(qta.icon("fa5s.copy", color="#FFFFFF"))
        self._btn_copy.setText("Copiar a Cliente")
        self._btn_copy.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_copy.setMinimumHeight(40)
        self._btn_copy.setStyleSheet(btn_style_primary)
        self._btn_copy.setEnabled(False)
        action_row.addWidget(self._btn_copy)

        card_layout.addLayout(action_row)

        # ── Status bar ──
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

        main_layout.addWidget(card, stretch=1)

    # ── Señales ─────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._combo_clients.currentIndexChanged.connect(self._on_client_selected)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_copy.clicked.connect(self._on_copy)

    # ── Carga de datos ─────────────────────────────────────────────

    def _load_clients(self) -> None:
        """Carga la lista de clientes en ambos combos."""
        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Cliente

        self._combo_clients.blockSignals(True)
        self._combo_dest.blockSignals(True)

        self._combo_clients.clear()
        self._combo_dest.clear()

        with get_session() as session:
            clientes = session.query(Cliente).order_by(Cliente.nombre).all()
            for c in clientes:
                label = c.nombre or f"Cliente #{c.id}"
                self._combo_clients.addItem(label, c.id)
                self._combo_dest.addItem(label, c.id)

        self._combo_clients.setCurrentIndex(-1)
        self._combo_dest.setCurrentIndex(-1)

        self._combo_clients.blockSignals(False)
        self._combo_dest.blockSignals(False)

    def refresh_clients(self) -> None:
        """Refresca la lista de clientes (llamado externamente)."""
        self._load_clients()

    def _on_client_selected(self, index: int) -> None:
        """Carga las plantillas del cliente seleccionado."""
        cliente_id = self._combo_clients.itemData(index)
        if cliente_id is None:
            self._table.setRowCount(0)
            return

        self._load_templates(cliente_id)

    def _load_templates(self, cliente_id: int) -> None:
        """Carga las plantillas del cliente en la tabla."""
        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Plantilla

        self._table.setRowCount(0)
        self._plantilla_ids = []

        with get_session() as session:
            plantillas = (
                session.query(Plantilla)
                .filter_by(cliente_id=cliente_id)
                .order_by(Plantilla.nombre)
                .all()
            )
            for row_idx, p in enumerate(plantillas):
                self._table.insertRow(row_idx)
                self._table.setItem(row_idx, 0, QTableWidgetItem(p.nombre))
                self._table.setItem(row_idx, 1, QTableWidgetItem(p.tipo))
                self._table.setItem(row_idx, 2, QTableWidgetItem(p.orientacion))
                self._table.setItem(
                    row_idx, 3, QTableWidgetItem(f"{p.ancho} \u00d7 {p.alto} cm")
                )
                self._table.setItem(
                    row_idx, 4,
                    QTableWidgetItem(
                        p.created_at.strftime("%Y-%m-%d %H:%M")
                        if p.created_at else "\u2014"
                    ),
                )
                self._plantilla_ids.append(p.id)

        self.set_status(
            f"\U0001f4cb {len(self._plantilla_ids)} plantilla(s) del cliente.", "info"
        )

    def _on_selection_changed(self) -> None:
        """Habilita/deshabilita botones según selección."""
        has_sel = bool(self._table.selectedItems())
        self._btn_delete.setEnabled(has_sel)
        self._btn_copy.setEnabled(has_sel and self._combo_dest.currentIndex() >= 0)

    # ── Acciones ───────────────────────────────────────────────────

    def _on_delete(self) -> None:
        """Elimina la plantilla seleccionada."""
        row = self._table.currentRow()
        if row < 0 or row >= len(self._plantilla_ids):
            return

        plantilla_id = self._plantilla_ids[row]
        nombre = self._table.item(row, 0).text()

        reply = QMessageBox.question(
            self,
            "Confirmar eliminación",
            f"\u00bfEliminar la plantilla \u00ab{nombre}\u00bb?\n\nEsta acción no se puede deshacer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Plantilla

        with get_session() as session:
            p = session.query(Plantilla).get(plantilla_id)
            if p:
                session.delete(p)
                session.commit()

        # Recargar tabla
        cliente_id = self._combo_clients.currentData()
        if cliente_id:
            self._load_templates(cliente_id)
        self.set_status(f"\U0001f5d1 Plantilla \u00ab{nombre}\u00bb eliminada.", "warning")

    def _on_copy(self) -> None:
        """Copia la plantilla seleccionada al cliente destino."""
        row = self._table.currentRow()
        if row < 0 or row >= len(self._plantilla_ids):
            return

        dest_id = self._combo_dest.currentData()
        if dest_id is None:
            self.set_status("\u26a0 Selecciona un cliente destino.", "warning")
            return

        source_id = self._plantilla_ids[row]
        nombre = self._table.item(row, 0).text()

        # Verificar que no sea el mismo cliente
        src_client_id = self._combo_clients.currentData()
        if src_client_id == dest_id:
            self.set_status("\u26a0 El cliente origen y destino son el mismo.", "warning")
            return

        reply = QMessageBox.question(
            self,
            "Confirmar copia",
            f"\u00bfCopiar \u00ab{nombre}\u00bb al cliente \u00ab{self._combo_dest.currentText()}\u00bb?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Plantilla
        import copy

        with get_session() as session:
            original = session.query(Plantilla).get(source_id)
            if not original:
                self.set_status("\u274c No se encontró la plantilla original.", "error")
                return

            nueva = Plantilla(
                cliente_id=dest_id,
                nombre=f"{original.nombre} (copia)",
                tipo=original.tipo,
                orientacion=original.orientacion,
                ancho=original.ancho,
                alto=original.alto,
                elementos_frente=copy.deepcopy(original.elementos_frente),
                elementos_vuelta=copy.deepcopy(original.elementos_vuelta),
                posiciones_hoja=copy.deepcopy(original.posiciones_hoja),
                recursos=copy.deepcopy(original.recursos),
            )
            session.add(nueva)
            session.commit()

        dest_name = self._combo_dest.currentText()
        self.set_status(
            f"\u2705 \u00ab{nombre}\u00bb copiada a \u00ab{dest_name}\u00bb correctamente.", "success"
        )

    # ── Status bar ─────────────────────────────────────────────────

    def set_status(self, message: str, level: str = "info", toast: bool = True) -> None:
        """Actualiza la barra de estado y, opcionalmente, muestra un toast.

        Usar toast=False para pasos intermedios de un flujo de carga: el
        progreso se refleja solo en el footer y se reserva el toast para el
        resultado final.
        """
        from PySide6.QtCore import QCoreApplication
        from credencializacion.ui.widgets.toast import ToastManager
        colors = {
            "info": ("#1E293B", "#94A3B8"),
            "success": ("#052E16", "#4ADE80"),
            "error": ("#450A0A", "#FCA5A5"),
            "warning": ("#451A03", "#FCD34D"),
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
