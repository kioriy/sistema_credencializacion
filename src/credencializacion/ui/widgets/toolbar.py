"""
Barra de herramientas con elementos arrastrables.

Contiene botones estilizados que el usuario puede arrastrar al lienzo
para añadir campos a la credencial.
"""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QMimeData, QPoint, QSize, Qt
from PySide6.QtGui import QCursor, QDrag, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# ═══════════════════════════════════════════════════════════════════════════
# Elemento arrastrable
# ═══════════════════════════════════════════════════════════════════════════
class DraggableElementButton(QFrame):
    """Tarjeta arrastrable que representa un tipo de elemento de credencial."""

    def __init__(
        self,
        label: str,
        element_type: str,
        icon_text: str,
        campo_dato: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._element_type = element_type
        self._icon_text = icon_text
        self._campo_dato = campo_dato
        self._drag_start: QPoint | None = None

        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFixedHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.setStyleSheet(
            """
            DraggableElementButton {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                padding: 0 12px;
            }
            DraggableElementButton:hover {
                background-color: #F8FAFC;
                border-color: #CBD5E1;
            }
            """
        )

        # Layout
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        # Ícono
        icon = QLabel(icon_text)
        icon.setFixedSize(28, 28)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            "background-color: #EFF6FF; border-radius: 6px; font-size: 14px;"
        )
        lay.addWidget(icon)

        # Texto
        text = QLabel(label)
        text.setStyleSheet(
            "font-size: 13px; font-weight: 500; color: #171A2B; background: transparent; border: none;"
        )
        lay.addWidget(text, 1)

        # Grip
        grip = QLabel("⠿")
        grip.setStyleSheet(
            "font-size: 16px; color: #CBD5E1; background: transparent; border: none;"
        )
        lay.addWidget(grip)

    # -- Drag ---------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_start is None:
            return
        if (event.position().toPoint() - self._drag_start).manhattanLength() < 10:
            return

        data = {
            "type": self._element_type,
            "campo_dato": self._campo_dato,
            "label": self._label,
        }

        mime = QMimeData()
        mime.setData(
            "application/x-canvas-element",
            json.dumps(data).encode("utf-8"),
        )

        drag = QDrag(self)
        drag.setMimeData(mime)

        # Pixmap semi-transparente
        pix = self.grab()
        pix.setDevicePixelRatio(2.0)
        drag.setPixmap(pix.scaled(
            pix.size() * 0.8,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        drag.setHotSpot(QPoint(pix.width() // 4, pix.height() // 4))

        drag.exec(Qt.DropAction.CopyAction)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start = None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start = None
        super().mouseReleaseEvent(event)


# ═══════════════════════════════════════════════════════════════════════════
# CanvasToolbar
# ═══════════════════════════════════════════════════════════════════════════
class CanvasToolbar(QWidget):
    """Panel lateral con los elementos arrastrables disponibles."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(240)
        self.setMaximumWidth(280)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Cabecera
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        h_lay = QVBoxLayout(header)
        h_lay.setContentsMargins(16, 16, 16, 12)
        h_lay.setSpacing(4)

        title = QLabel("Atributos")
        title.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #171A2B;"
        )
        h_lay.addWidget(title)

        subtitle = QLabel("Arrastra elementos al lienzo")
        subtitle.setStyleSheet(
            "font-size: 12px; color: #64748B;"
        )
        h_lay.addWidget(subtitle)

        outer.addWidget(header)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #E2E8F0; max-height: 1px;")
        outer.addWidget(sep)

        # ScrollArea con botones
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        btn_container = QWidget()
        self._btn_layout = QVBoxLayout(btn_container)
        self._btn_layout.setContentsMargins(12, 12, 12, 12)
        self._btn_layout.setSpacing(8)
        scroll.setWidget(btn_container)

        # Elementos
        elements: list[dict[str, str]] = [
            {"label": "Texto Compuesto", "type": "composite", "icon": "📝", "campo_dato": "composite"},
            # ── Imágenes ──
            {"label": "Foto Estudiante",  "type": "photo_path", "icon": "📷", "campo_dato": "photo_url"},
            {"label": "Foto Papá",        "type": "photo_path", "icon": "👨", "campo_dato": "url_foto_papa"},
            {"label": "Foto Mamá",        "type": "photo_path", "icon": "👩", "campo_dato": "url_foto_mama"},
            {"label": "Foto Autorizado",  "type": "photo_path", "icon": "🧑", "campo_dato": "url_foto_autorizado"},
            {"label": "Logo Escuela",     "type": "photo_path", "icon": "🏫", "campo_dato": "logo_escuela"},
            # ── Texto ──
            {"label": "Nombre", "type": "text", "icon": "𝐀", "campo_dato": "nombre"},
            {"label": "Apellido Paterno", "type": "text", "icon": "𝐀", "campo_dato": "apellido_paterno"},
            {"label": "Apellido Materno", "type": "text", "icon": "𝐀", "campo_dato": "apellido_materno"},
            {"label": "Matrícula", "type": "text", "icon": "𝐀", "campo_dato": "matricula"},
            {"label": "CURP", "type": "text", "icon": "𝐀", "campo_dato": "curp"},
            {"label": "Grado", "type": "text", "icon": "𝐀", "campo_dato": "grado"},
            {"label": "Grupo", "type": "text", "icon": "𝐀", "campo_dato": "grupo"},
            {"label": "Turno", "type": "text", "icon": "𝐀", "campo_dato": "turno"},
            {"label": "Nivel Educativo", "type": "text", "icon": "𝐀", "campo_dato": "nivel_educativo"},
        ]

        for el in elements:
            btn = DraggableElementButton(
                label=el["label"],
                element_type=el["type"],
                icon_text=el["icon"],
                campo_dato=el.get("campo_dato", ""),
            )
            self._btn_layout.addWidget(btn)

        self._btn_layout.addStretch()
