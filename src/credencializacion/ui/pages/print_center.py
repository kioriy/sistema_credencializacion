"""
Centro de Impresión — historial y estadísticas de trabajos.

Página con tabla de historial, tarjetas de estadísticas,
y barra de progreso para trabajos activos.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
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
)

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
    """Tarjeta de estadística con número grande y label.

    Diseño: número coloreado grande + descripción pequeña abajo.
    """

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
        self.setMinimumWidth(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._lbl_value = QLabel(str(value))
        self._lbl_value.setFont(QFont("Inter", 28, QFont.Weight.Bold))
        self._lbl_value.setStyleSheet(f"color: {color}; border: none;")
        self._lbl_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._lbl_value)

        lbl_title = QLabel(title)
        lbl_title.setFont(QFont("Inter", 12))
        lbl_title.setStyleSheet(f"color: {TEXT_LIGHT}; border: none;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_title)

    def set_value(self, value: int | str) -> None:
        """Actualiza el valor de la tarjeta."""
        self._lbl_value.setText(str(value))


class PrintCenter(QWidget):
    """Centro de Impresión — historial y estadísticas.

    Muestra:
    - Tarjetas de estadísticas (total, pendientes, errores)
    - Barra de progreso para trabajo activo
    - Tabla de historial de impresión

    Methods:
        refresh_history(): Recarga los datos del historial.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Construye el layout del centro de impresión."""
        self.setStyleSheet(f"background-color: {MAIN_BG};")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # ── Header ─────────────────────────────────────────────────
        header = QHBoxLayout()
        lbl_title = QLabel("Centro de Impresión")
        lbl_title.setFont(QFont("Inter", 20, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {TEXT_DARK};")
        header.addWidget(lbl_title)
        header.addStretch()

        btn_refresh = QPushButton("🔄  Actualizar")
        btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_refresh.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 2px solid {BORDER};
                border-radius: 8px;
                padding: 8px 20px;
                color: {TEXT_DARK};
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {PRIMARY};
                color: {PRIMARY};
            }}
        """)
        btn_refresh.clicked.connect(self.refresh_history)
        header.addWidget(btn_refresh)

        main_layout.addLayout(header)

        # ── Tarjetas de estadísticas ───────────────────────────────
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(16)

        self._card_total = StatCard("Total Impresas", 0, SUCCESS)
        self._card_pending = StatCard("Pendientes", 0, WARNING)
        self._card_errors = StatCard("Errores", 0, ERROR)

        stats_layout.addWidget(self._card_total)
        stats_layout.addWidget(self._card_pending)
        stats_layout.addWidget(self._card_errors)

        main_layout.addLayout(stats_layout)

        # ── Barra de progreso (trabajo activo) ─────────────────────
        self._progress_frame = QFrame()
        self._progress_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        progress_layout = QVBoxLayout(self._progress_frame)
        progress_layout.setContentsMargins(16, 12, 16, 12)
        progress_layout.setSpacing(8)

        progress_header = QHBoxLayout()
        self._lbl_progress_title = QLabel("🖨  Imprimiendo...")
        self._lbl_progress_title.setFont(QFont("Inter", 13, QFont.Weight.DemiBold))
        self._lbl_progress_title.setStyleSheet(f"color: {TEXT_DARK};")
        progress_header.addWidget(self._lbl_progress_title)
        progress_header.addStretch()

        self._lbl_progress_count = QLabel("0 / 0")
        self._lbl_progress_count.setFont(QFont("Inter", 12))
        self._lbl_progress_count.setStyleSheet(f"color: {TEXT_LIGHT};")
        progress_header.addWidget(self._lbl_progress_count)
        progress_layout.addLayout(progress_header)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {MAIN_BG};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {PRIMARY};
                border-radius: 4px;
            }}
        """)
        progress_layout.addWidget(self._progress_bar)

        self._progress_frame.setVisible(False)  # Oculto por defecto
        main_layout.addWidget(self._progress_frame)

        # ── Tabla de historial ─────────────────────────────────────
        history_card = QFrame()
        history_card.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        history_layout = QVBoxLayout(history_card)
        history_layout.setContentsMargins(16, 16, 16, 16)
        history_layout.setSpacing(8)

        lbl_history = QLabel("Historial de Impresión")
        lbl_history.setFont(QFont("Inter", 14, QFont.Weight.Bold))
        lbl_history.setStyleSheet(f"color: {TEXT_DARK};")
        history_layout.addWidget(lbl_history)

        self._history_table = QTableWidget()
        self._history_table.setColumnCount(5)
        self._history_table.setHorizontalHeaderLabels([
            "FECHA", "PLANTILLA", "REGISTROS", "ESTADO", "ACCIONES",
        ])

        h = self._history_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self._history_table.setColumnWidth(2, 100)
        self._history_table.setColumnWidth(3, 120)
        self._history_table.setColumnWidth(4, 100)

        self._history_table.verticalHeader().setVisible(False)
        self._history_table.setShowGrid(False)
        self._history_table.setAlternatingRowColors(True)
        self._history_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._history_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        self._history_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {CARD_BG};
                border: none;
                font-family: 'Inter', sans-serif;
                font-size: 13px;
                color: {TEXT_DARK};
            }}
            QTableWidget::item {{
                padding: 10px 8px;
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
                padding: 10px 8px;
                border: none;
                border-bottom: 2px solid {BORDER};
            }}
        """)

        history_layout.addWidget(self._history_table, stretch=1)
        main_layout.addWidget(history_card, stretch=1)

    # ── Métodos públicos ───────────────────────────────────────────

    def refresh_history(self) -> None:
        """Recarga los datos del historial de impresión.

        En la implementación real, consultará la base de datos
        para obtener los trabajos de impresión recientes.
        """
        # Placeholder — se llenará con datos reales desde la BD
        pass

    def update_stats(
        self,
        total: int,
        pending: int,
        errors: int,
    ) -> None:
        """Actualiza las tarjetas de estadísticas.

        Args:
            total: Total de credenciales impresas.
            pending: Cantidad de trabajos pendientes.
            errors: Cantidad de errores.
        """
        self._card_total.set_value(total)
        self._card_pending.set_value(pending)
        self._card_errors.set_value(errors)

    def show_progress(self, current: int, total: int) -> None:
        """Muestra/actualiza la barra de progreso de impresión activa.

        Args:
            current: Número actual de registros procesados.
            total: Total de registros en el lote.
        """
        self._progress_frame.setVisible(True)
        self._lbl_progress_count.setText(f"{current} / {total}")

        if total > 0:
            percent = int((current / total) * 100)
            self._progress_bar.setValue(percent)

        if current >= total:
            self._lbl_progress_title.setText("✅  Impresión completada")

    def hide_progress(self) -> None:
        """Oculta la barra de progreso."""
        self._progress_frame.setVisible(False)
        self._progress_bar.setValue(0)
        self._lbl_progress_title.setText("🖨  Imprimiendo...")

    def add_history_entry(
        self,
        date: str,
        template_name: str,
        record_count: int,
        status: str,
    ) -> None:
        """Agrega una entrada al historial de impresión.

        Args:
            date: Fecha/hora del trabajo.
            template_name: Nombre de la plantilla usada.
            record_count: Número de registros impresos.
            status: Estado del trabajo ('completado', 'error', 'cancelado').
        """
        row = self._history_table.rowCount()
        self._history_table.insertRow(row)

        self._history_table.setItem(row, 0, QTableWidgetItem(date))
        self._history_table.setItem(row, 1, QTableWidgetItem(template_name))
        self._history_table.setItem(row, 2, QTableWidgetItem(str(record_count)))

        # Badge de estado
        status_item = QTableWidgetItem(status)
        color_map = {
            "completado": QColor(SUCCESS),
            "error": QColor(ERROR),
            "cancelado": QColor(WARNING),
            "en_progreso": QColor(PRIMARY),
        }
        status_item.setForeground(color_map.get(status, QColor(TEXT_LIGHT)))
        status_item.setFont(QFont("Inter", 11, QFont.Weight.DemiBold))
        self._history_table.setItem(row, 3, status_item)

        # Botón de acción
        btn_view = QPushButton("Ver PDF")
        btn_view.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_view.setStyleSheet(f"""
            QPushButton {{
                background-color: {MAIN_BG};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 4px 12px;
                color: {TEXT_LIGHT};
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {BORDER};
                color: {TEXT_DARK};
            }}
        """)
        self._history_table.setCellWidget(row, 4, btn_view)
        self._history_table.setRowHeight(row, 48)
