"""
Panel de cola de impresión.

Rediseño basado en tarjetas (cards) e íconos vectoriales (qtawesome / Font Awesome 5).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
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

@dataclass
class QueueMeta:
    """Qué tarjeta del registro se imprime y con qué diseño.

    Las entradas normales (agregadas desde la tabla) no llevan metadatos: son
    la credencial del alumno con la plantilla elegida en el combo. Las de
    reposiciones traen su propia plantilla y, si son de un autorizado, su
    posición e id de persona.
    """

    tipo: str = "alumno"  # "alumno" | "autorizado"
    slot: int | None = None
    authorized_person_id: int | None = None
    solicitud: str | None = None  # "replacement" | "new"
    plantilla_id: int | None = None
    plantilla_nombre: str = ""
    etiqueta: str = ""
    nombre: str = ""
    foto: str = ""


def queue_key(registro: "Registro", meta: QueueMeta | None) -> str:
    """Identidad de una entrada: un alumno puede tener varias tarjetas."""
    if meta is None or meta.tipo != "autorizado":
        return f"{registro.id}:alumno"
    return f"{registro.id}:autorizado:{meta.authorized_person_id}"


def _qta_pixmap(icon_name: str, size: int = 16, color: str = "#64748B") -> "QPixmap":
    """Genera un QPixmap desde qtawesome."""
    return qta.icon(icon_name, color=color).pixmap(QSize(size, size))


class PrintQueueCard(QFrame):
    """Tarjeta individual para cada registro en la cola de impresión.
    
    Diseño basado en el mockup con bordes, foto, estado y botón 'x'.
    """

    remove_requested = Signal(str)

    def __init__(
        self,
        registro: "Registro",
        pixmap: QPixmap | None = None,
        parent: QWidget | None = None,
        meta: QueueMeta | None = None,
    ) -> None:
        super().__init__(parent)
        self._registro = registro
        self._registro_id = registro.id
        self._meta = meta
        self._key = queue_key(registro, meta)
        self._photo_path = (
            meta.foto if meta is not None and meta.tipo == "autorizado"
            else registro.photo_path
        )
        self._has_photo = bool(self._photo_path)
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
        
        # Foto cacheada o, si no, intento con la ruta local. Una URL que aún no
        # se descarga da un pixmap nulo: se muestra el ícono de imagen en vez
        # de un recuadro oscuro vacío (el PDF sí descarga la foto).
        pix = None
        if self._has_photo:
            pix = self._pixmap if self._pixmap else QPixmap(self._photo_path)
            if pix.isNull():
                pix = None

        if pix is not None:
            photo_container.setStyleSheet(f"background-color: {TEXT_DARK};")
            photo_layout = QVBoxLayout(photo_container)
            photo_layout.setContentsMargins(0, 0, 0, 0)
            photo_lbl = QLabel(photo_container)
            photo_lbl.setPixmap(pix.scaled(
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

        meta = self._meta
        # Nombre (en tarjetas de autorizado, el de la persona)
        nombre = (meta.nombre if meta and meta.nombre else None) or self._registro.datos.get(
            "nombre", f"Registro #{self._registro_id}"
        )
        name_lbl = QLabel(nombre)
        name_lbl.setStyleSheet(f"color: {TEXT_DARK}; font-weight: bold; font-size: 11px; border: none; background: transparent;")
        info_layout.addWidget(name_lbl)

        # Tipo de tarjeta (reposiciones): "Autorizado 2 · Nueva — de <alumno>"
        if meta and meta.etiqueta:
            texto = meta.etiqueta
            if meta.tipo == "autorizado":
                texto += f" — {self._registro.nombre_completo}"
            tipo_lbl = QLabel(texto)
            tipo_lbl.setWordWrap(True)
            tipo_lbl.setStyleSheet(f"color: {PRIMARY}; font-size: 10px; font-weight: bold; border: none; background: transparent;")
            info_layout.addWidget(tipo_lbl)

        # Plantilla
        template_lbl = QLabel(
            f"Plantilla: {meta.plantilla_nombre}" if meta and meta.plantilla_nombre
            else "Plantilla: Standard_v2"
        )
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
        """Emite la señal para eliminar esta tarjeta de la cola."""
        self.remove_requested.emit(self._key)


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

    def add_to_queue(
        self,
        registro: "Registro",
        pixmap: QPixmap | None = None,
        meta: QueueMeta | None = None,
        render: bool = True,
    ) -> None:
        """Agrega una tarjeta a la cola con su foto cacheada opcional.

        ``render=False`` permite agregar muchas y redibujar una sola vez.
        """
        key = queue_key(registro, meta)
        if any(queue_key(item[0], item[2]) == key for item in self._queue):
            return

        self._queue.append((registro, pixmap, meta))
        if render:
            self._render_queue()

    def remove_from_queue(self, key: str) -> None:
        """Elimina una tarjeta de la cola (por su clave)."""
        self._queue = [
            item for item in self._queue if queue_key(item[0], item[2]) != key
        ]
        self._render_queue()

    def clear_queue(self) -> None:
        """Limpia toda la cola."""
        self._queue.clear()
        self._render_queue()

    def get_queue(self) -> list["Registro"]:
        """Devuelve la lista actual de registros en cola."""
        return [item[0] for item in self._queue]

    def get_entries(self) -> list[tuple["Registro", QueueMeta | None]]:
        """Devuelve las tarjetas en cola con sus metadatos (o None)."""
        return [(item[0], item[2]) for item in self._queue]

    def refresh(self) -> None:
        """Redibuja la cola (tras agregar varias con ``render=False``)."""
        self._render_queue()

    def _render_queue(self) -> None:
        """Vuelve a dibujar todas las tarjetas basado en la lista actual."""
        while self._cards_layout.count():
            child = self._cards_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for reg, pixmap, meta in self._queue:
            card = PrintQueueCard(reg, pixmap, meta=meta)
            card.remove_requested.connect(self.remove_from_queue)
            self._cards_layout.addWidget(card)

        self._cards_layout.addStretch()
        self._update_ui_state()

    def _update_ui_state(self) -> None:
        """Actualiza el badge con la cantidad de registros."""
        count = len(self._queue)
        self._badge_lbl.setText(str(count))
