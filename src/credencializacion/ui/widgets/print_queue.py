"""
Panel de cola de impresión.

Rediseño basado en tarjetas (cards) e íconos vectoriales (qtawesome / Font Awesome 5).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QSize
import qtawesome as qta
from PySide6.QtGui import QFont, QPixmap, QColor, QPainter, QPainterPath, QCursor, QIcon
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QComboBox,
    QSizePolicy,
    QFrame,
    QScrollArea,
)

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
SUCCESS = "#1D4ED8" # Azul oscuro para "LISTO" según mockup
SUCCESS_BG = "#EFF6FF"
WARNING = "#EF4444" # Rojo para "FALTA FOTO"
WARNING_BG = "#FEF2F2"
MAIN_BG = "#F5F7FA"

def _qta_pixmap(icon_name: str, size: int = 16, color: str = "#64748B") -> "QPixmap":
    """Genera un QPixmap desde qtawesome."""
    return qta.icon(icon_name, color=color).pixmap(QSize(size, size))


class PrintQueueCard(QFrame):
    """Tarjeta individual para cada registro en la cola de impresión.
    
    Diseño basado en el mockup con bordes, foto, estado y botón 'x'.
    """

    remove_requested = Signal(int)

    def __init__(self, registro: "Registro", pixmap: QPixmap | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registro = registro
        self._registro_id = registro.id
        self._has_photo = bool(registro.photo_path)
        self._pixmap = pixmap
        
        self.setObjectName("QueueCard")
        self.setFixedHeight(90)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Construye el layout de la tarjeta."""
        border_color = WARNING if not self._has_photo else BORDER
        bg_color = WARNING_BG if not self._has_photo else CARD_BG
        
        self.setStyleSheet(f"""
            QFrame#QueueCard {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 2px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        # 1. Contenedor de la foto (Izquierda)
        photo_container = QFrame()
        photo_container.setFixedSize(50, 65)
        
        if self._has_photo:
            photo_container.setStyleSheet(f"background-color: {TEXT_DARK};")
            photo_layout = QVBoxLayout(photo_container)
            photo_layout.setContentsMargins(0, 0, 0, 0)
            photo_lbl = QLabel(photo_container)
            
            if self._pixmap:
                photo_lbl.setPixmap(self._pixmap.scaled(
                    50, 65, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
                ))
            else:
                # Intento de cargar ruta local
                photo_lbl.setPixmap(QPixmap(self._registro.photo_path).scaled(
                    50, 65, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
                ))
                
            photo_lbl.setFixedSize(50, 65)
            photo_layout.addWidget(photo_lbl)
        else:
            photo_container.setStyleSheet(f"background-color: #E2E8F0;")
            photo_layout = QVBoxLayout(photo_container)
            photo_layout.setContentsMargins(0, 0, 0, 0)
            icon_lbl = QLabel(photo_container)
            icon_lbl.setPixmap(_qta_pixmap("fa5s.image", 24, "#94A3B8"))
            icon_lbl.setStyleSheet("background: transparent; border: none;")
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setFixedSize(50, 65)
            photo_layout.addWidget(icon_lbl)

        layout.addWidget(photo_container)

        # 2. Información Central
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        info_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Nombre
        name_lbl = QLabel(self._registro.datos.get("nombre", f"Registro #{self._registro_id}"))
        name_lbl.setStyleSheet(f"color: {TEXT_DARK}; font-weight: bold; font-size: 11px; border: none; background: transparent;")
        info_layout.addWidget(name_lbl)

        # Plantilla
        template_lbl = QLabel("Plantilla: Standard_v2")
        template_lbl.setStyleSheet(f"color: {TEXT_LIGHT}; font-size: 11px; font-family: monospace; border: none; background: transparent;")
        info_layout.addWidget(template_lbl)

        # Estado
        status_layout = QHBoxLayout()
        status_layout.setSpacing(4)
        status_icon = QLabel()
        status_icon.setFixedSize(12, 12)
        status_text = QLabel()
        
        if self._has_photo:
            status_icon.setPixmap(_qta_pixmap("fa5s.check-circle", 12, SUCCESS))
            status_text.setText("LISTO PARA IMPRIMIR")
            status_text.setStyleSheet(f"color: {SUCCESS}; font-size: 9px; font-weight: bold; border: none; background: transparent;")
        else:
            status_icon.setPixmap(_qta_pixmap("fa5s.exclamation-triangle", 12, WARNING))
            status_text.setText("FALTA FOTO")
            status_text.setStyleSheet(f"color: {WARNING}; font-size: 9px; font-weight: bold; border: none; background: transparent;")

        status_layout.addWidget(status_icon)
        status_layout.addWidget(status_text)
        status_layout.addStretch()
        
        status_widget = QWidget()
        status_widget.setStyleSheet("border: none; background: transparent;")
        status_widget.setLayout(status_layout)
        status_layout.setContentsMargins(0, 2, 0, 0)
        
        info_layout.addWidget(status_widget)
        layout.addLayout(info_layout)
        layout.addStretch()

        # 3. Botón de Cerrar (X) - Superior Derecha
        btn_close = QPushButton()
        btn_close.setIcon(qta.icon("fa5s.times", color=TEXT_LIGHT))
        btn_close.setIconSize(QSize(12, 12))
        btn_close.setFixedSize(16, 16)
        btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_LIGHT};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding-bottom: 1px;
            }}
            QPushButton:hover {{
                background-color: #F1F5F9;
                color: {TEXT_DARK};
            }}
        """)
        btn_close.clicked.connect(self._on_remove_clicked)
        
        close_layout = QVBoxLayout()
        close_layout.setContentsMargins(0,0,0,0)
        close_layout.addWidget(btn_close)
        close_layout.addStretch()
        layout.addLayout(close_layout)

    def _on_remove_clicked(self) -> None:
        """Emite la señal para eliminar este registro de la cola."""
        self.remove_requested.emit(self._registro_id)


class PrintQueuePanel(QWidget):
    """Panel derecho principal para la cola de impresión."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._queue: list["Registro"] = []
        self.setMinimumWidth(280)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Construye la UI del panel lateral."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.setStyleSheet(f"""
            PrintQueuePanel {{
                background-color: {CARD_BG};
            }}
        """)

        # --- 1. Cabecera (Título y Badge) ---
        header_widget = QFrame()
        header_widget.setFixedHeight(60)
        header_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header_widget.setStyleSheet("QFrame { background-color: #0F1629; border: none; }")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(16, 0, 16, 0)
        header_layout.setSpacing(10)

        icon_title = QLabel()
        icon_title.setFixedSize(20, 20)
        icon_title.setPixmap(_qta_pixmap("fa5s.print", 20, "#FFFFFF"))
        icon_title.setStyleSheet("background: transparent; border: none;")
        
        title_lbl = QLabel("Cola de Impresión")
        title_lbl.setStyleSheet("color: white; font-size: 15px; font-weight: bold;")
        
        self._badge_lbl = QLabel("0")
        self._badge_lbl.setFixedSize(20, 20)
        self._badge_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge_lbl.setStyleSheet(f"""
            background-color: {PRIMARY};
            color: white;
            border-radius: 10px;
            font-size: 10px;
            font-weight: bold;
        """)

        header_layout.addWidget(icon_title)
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        header_layout.addWidget(self._badge_lbl)
        layout.addWidget(header_widget)

        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.HLine)
        line1.setStyleSheet(f"color: {BORDER};")
        layout.addWidget(line1)



        # --- 3. Lista de Tarjetas (Scroll Area) ---
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setStyleSheet("background: transparent;")
        
        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(16, 16, 16, 16)
        self._cards_layout.setSpacing(12)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self._scroll_area.setWidget(self._cards_container)
        layout.addWidget(self._scroll_area, stretch=1)

        self._update_ui_state()

    def add_to_queue(self, registro: "Registro", pixmap: QPixmap | None = None) -> None:
        """Agrega un registro a la cola con su foto cacheada opcional."""
        if any(item[0].id == registro.id for item in self._queue):
            return

        self._queue.append((registro, pixmap))
        self._render_queue()

    def remove_from_queue(self, registro_id: int) -> None:
        """Elimina un registro de la cola."""
        self._queue = [item for item in self._queue if item[0].id != registro_id]
        self._render_queue()

    def clear_queue(self) -> None:
        """Limpia toda la cola."""
        self._queue.clear()
        self._render_queue()

    def get_queue(self) -> list["Registro"]:
        """Devuelve la lista actual de registros en cola."""
        return [item[0] for item in self._queue]

    def _render_queue(self) -> None:
        """Vuelve a dibujar todas las tarjetas basado en la lista actual."""
        while self._cards_layout.count():
            child = self._cards_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for reg, pixmap in self._queue:
            card = PrintQueueCard(reg, pixmap)
            card.remove_requested.connect(self.remove_from_queue)
            self._cards_layout.addWidget(card)

        self._cards_layout.addStretch()
        self._update_ui_state()

    def _update_ui_state(self) -> None:
        """Actualiza el badge con la cantidad de registros."""
        count = len(self._queue)
        self._badge_lbl.setText(str(count))
