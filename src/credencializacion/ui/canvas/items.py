"""
Elementos arrastrables del lienzo de credenciales.

Cada clase representa un tipo de elemento que puede añadirse al
diseño de una credencial: texto, imagen, código QR, forma o código
de barras.  Todos comparten un *mixin* ``BaseCanvasItem`` que aporta
las banderas comunes de interacción, serialización y borde de
selección.
"""

from __future__ import annotations

import io
import json
from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_SELECTION_COLOR = QColor("#3B82F6")
_SELECTION_PEN = QPen(_SELECTION_COLOR, 2.0, Qt.PenStyle.SolidLine)
_PLACEHOLDER_COLOR = QColor("#64748B")


# ═══════════════════════════════════════════════════════════════════════════
# Mixin base
# ═══════════════════════════════════════════════════════════════════════════
class BaseCanvasItem:
    """Mixin que aporta funcionalidad común a todos los elementos del lienzo."""

    _campo_dato: str = ""

    # -- Banderas comunes ---------------------------------------------------
    def _init_flags(self) -> None:
        """Llama desde ``__init__`` de cada subclase para establecer las
        banderas de interacción."""
        item: QGraphicsItem = self  # type: ignore[assignment]
        item.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        item.setCursor(Qt.CursorShape.SizeAllCursor)

    # -- Propiedad campo_dato -----------------------------------------------
    @property
    def campo_dato(self) -> str:
        return self._campo_dato

    @campo_dato.setter
    def campo_dato(self, value: str) -> None:
        self._campo_dato = value

    # -- Tipo de elemento ---------------------------------------------------
    @property
    def element_type(self) -> str:  # pragma: no cover – sobrescrito
        raise NotImplementedError

    # -- Serialización ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Serializa las propiedades comunes.  Las subclases extienden."""
        item: QGraphicsItem = self  # type: ignore[assignment]
        return {
            "type": self.element_type,
            "x": item.x(),
            "y": item.y(),
            "campo_dato": self._campo_dato,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "BaseCanvasItem":
        """Fábrica: crea la subclase adecuada a partir de un diccionario."""
        builders: dict[str, type] = {
            "text": TextCanvasItem,
            "image": ImageCanvasItem,
            "qr": QRCanvasItem,
            "shape": ShapeCanvasItem,
            "barcode": BarcodeCanvasItem,
        }
        cls = builders.get(data.get("type", ""))
        if cls is None:
            raise ValueError(f"Tipo de elemento desconocido: {data.get('type')}")

        if data["type"] == "text":
            item = cls(text=data.get("text", ""))
            item.set_font_family(data.get("font_family", "Inter"))
            item.set_font_size(data.get("font_size", 12))
            item.set_font_weight(data.get("font_weight", "normal"))
            item.set_font_color(data.get("font_color", "#171A2B"))
            item.set_alignment(data.get("alignment", "left"))
        elif data["type"] == "image":
            item = cls(
                width=data.get("width", 100),
                height=data.get("height", 100),
            )
            if data.get("image_path"):
                item.set_image(data["image_path"])
        elif data["type"] == "qr":
            item = cls(size=data.get("size", 80))
            if data.get("qr_data"):
                item.set_qr_data(data["qr_data"])
        elif data["type"] == "shape":
            item = cls(
                width=data.get("width", 100),
                height=data.get("height", 50),
            )
            item.set_fill_color(data.get("fill_color", "#E2E8F0"))
            item.set_border_color(data.get("border_color", "#171A2B"))
            item.border_width = data.get("border_width", 1)
            item._apply_style()
        elif data["type"] == "barcode":
            item = cls(
                width=data.get("width", 150),
                height=data.get("height", 50),
            )
            if data.get("barcode_data"):
                item._barcode_data = data["barcode_data"]

        item.setPos(data.get("x", 0), data.get("y", 0))
        item.campo_dato = data.get("campo_dato", "")
        return item

    # -- Dibujar borde de selección -----------------------------------------
    def _draw_selection_rect(self, painter: QPainter, rect: QRectF) -> None:
        item: QGraphicsItem = self  # type: ignore[assignment]
        if item.isSelected():
            painter.setPen(_SELECTION_PEN)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(-1, -1, 1, 1))
            # Tiradores (handles) en las esquinas
            handle = 5.0
            for corner in (
                rect.topLeft(),
                rect.topRight(),
                rect.bottomLeft(),
                rect.bottomRight(),
            ):
                painter.setBrush(QBrush(QColor("#FFFFFF")))
                painter.drawRect(QRectF(
                    corner.x() - handle / 2,
                    corner.y() - handle / 2,
                    handle,
                    handle,
                ))


# ═══════════════════════════════════════════════════════════════════════════
# TextCanvasItem
# ═══════════════════════════════════════════════════════════════════════════
class TextCanvasItem(BaseCanvasItem, QGraphicsTextItem):
    """Elemento de texto editable."""

    def __init__(self, text: str = "", parent: QGraphicsItem | None = None) -> None:
        QGraphicsTextItem.__init__(self, parent)
        self._init_flags()

        self._font_family = "Inter"
        self._font_size = 12
        self._font_weight = "normal"
        self._font_color = "#171A2B"
        self._alignment = "left"
        self._user_text = text

        self._apply_font()
        if text:
            self.setPlainText(text)

    # -- Propiedad element_type ---------------------------------------------
    @property
    def element_type(self) -> str:
        return "text"

    # -- Font helpers -------------------------------------------------------
    @property
    def font_family(self) -> str:
        return self._font_family

    def set_font_family(self, family: str) -> None:
        self._font_family = family
        self._apply_font()

    @property
    def font_size(self) -> int:
        return self._font_size

    def set_font_size(self, size: int) -> None:
        self._font_size = max(1, size)
        self._apply_font()

    @property
    def font_weight(self) -> str:
        return self._font_weight

    def set_font_weight(self, weight: str) -> None:
        self._font_weight = weight
        self._apply_font()

    @property
    def font_color(self) -> str:
        return self._font_color

    def set_font_color(self, color: str) -> None:
        self._font_color = color
        self.setDefaultTextColor(QColor(color))

    @property
    def alignment(self) -> str:
        return self._alignment

    def set_alignment(self, align: str) -> None:
        self._alignment = align

    def _apply_font(self) -> None:
        weight_map = {
            "normal": QFont.Weight.Normal,
            "bold": QFont.Weight.Bold,
            "light": QFont.Weight.Light,
        }
        f = QFont(self._font_family, self._font_size)
        f.setWeight(weight_map.get(self._font_weight, QFont.Weight.Normal))
        self.setFont(f)
        self.setDefaultTextColor(QColor(self._font_color))

    # -- Paint override -----------------------------------------------------
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        # Placeholder
        if not self.toPlainText().strip():
            painter.setPen(QPen(_PLACEHOLDER_COLOR))
            painter.setFont(self.font())
            painter.drawText(
                self.boundingRect(),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "Texto de ejemplo",
            )
        else:
            # Dibujar el texto normal sin el punteado predeterminado de QGraphicsTextItem
            option.state &= ~QStyleOptionGraphicsItem.StateFlag.State_Selected  # type: ignore[attr-defined]
            QGraphicsTextItem.paint(self, painter, option, widget)

        self._draw_selection_rect(painter, self.boundingRect())

    # -- Serialización ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update(
            text=self.toPlainText(),
            font_family=self._font_family,
            font_size=self._font_size,
            font_weight=self._font_weight,
            font_color=self._font_color,
            alignment=self._alignment,
            width=self.boundingRect().width(),
            height=self.boundingRect().height(),
        )
        return d


# ═══════════════════════════════════════════════════════════════════════════
# Helpers para pixmaps placeholder
# ═══════════════════════════════════════════════════════════════════════════
def _make_placeholder_pixmap(
    width: int,
    height: int,
    icon_text: str,
    bg_color: str = "#EEF2F7",
    fg_color: str = "#94A3B8",
) -> QPixmap:
    """Genera un pixmap placeholder con un ícono central."""
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(bg_color))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Borde
    pen = QPen(QColor("#CBD5E1"), 1, Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.drawRect(0, 0, width - 1, height - 1)

    # Ícono central
    painter.setPen(QPen(QColor(fg_color)))
    font = QFont("Segoe UI Emoji", min(width, height) // 3)
    painter.setFont(font)
    painter.drawText(
        QRectF(0, 0, width, height),
        Qt.AlignmentFlag.AlignCenter,
        icon_text,
    )
    painter.end()
    return pixmap


# ═══════════════════════════════════════════════════════════════════════════
# ImageCanvasItem
# ═══════════════════════════════════════════════════════════════════════════
class ImageCanvasItem(BaseCanvasItem, QGraphicsPixmapItem):
    """Elemento de imagen (foto del estudiante, logotipo, etc.)."""

    def __init__(
        self,
        width: int = 100,
        height: int = 100,
        parent: QGraphicsItem | None = None,
    ) -> None:
        QGraphicsPixmapItem.__init__(self, parent)
        self._init_flags()
        self._width = width
        self._height = height
        self._image_path: str = ""
        self._set_placeholder()

    @property
    def element_type(self) -> str:
        return "image"

    @property
    def image_path(self) -> str:
        return self._image_path

    def _set_placeholder(self) -> None:
        self.setPixmap(_make_placeholder_pixmap(self._width, self._height, "📷"))

    def set_image(self, path: str) -> None:
        """Carga una imagen manteniendo la relación de aspecto."""
        self._image_path = path
        pix = QPixmap(path)
        if pix.isNull():
            self._set_placeholder()
            return
        pix = pix.scaled(
            self._width,
            self._height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(pix)

    # -- Paint override -----------------------------------------------------
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        QGraphicsPixmapItem.paint(self, painter, option, widget)
        self._draw_selection_rect(painter, self.boundingRect())

    # -- Serialización ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update(
            image_path=self._image_path,
            width=self._width,
            height=self._height,
        )
        return d


# ═══════════════════════════════════════════════════════════════════════════
# QRCanvasItem
# ═══════════════════════════════════════════════════════════════════════════
class QRCanvasItem(BaseCanvasItem, QGraphicsPixmapItem):
    """Elemento de código QR."""

    def __init__(
        self, size: int = 80, parent: QGraphicsItem | None = None
    ) -> None:
        QGraphicsPixmapItem.__init__(self, parent)
        self._init_flags()
        self._size = size
        self._qr_data: str = ""
        self._set_placeholder()

    @property
    def element_type(self) -> str:
        return "qr"

    @property
    def qr_data(self) -> str:
        return self._qr_data

    def _set_placeholder(self) -> None:
        """Dibuja un placeholder con un patrón QR simplificado."""
        pix = QPixmap(self._size, self._size)
        pix.fill(QColor("#EEF2F7"))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Borde
        p.setPen(QPen(QColor("#CBD5E1"), 1, Qt.PenStyle.DashLine))
        p.drawRect(0, 0, self._size - 1, self._size - 1)

        # Patrón QR simplificado — 3 cuadrados de posición
        cell = self._size // 8
        pen = QPen(QColor("#94A3B8"))
        brush = QBrush(QColor("#94A3B8"))
        p.setPen(pen)
        p.setBrush(brush)
        for ox, oy in ((cell, cell), (self._size - 4 * cell, cell), (cell, self._size - 4 * cell)):
            p.drawRect(ox, oy, 3 * cell, 3 * cell)
            p.setBrush(QBrush(QColor("#EEF2F7")))
            p.drawRect(ox + cell // 2, oy + cell // 2, 2 * cell, 2 * cell)
            p.setBrush(brush)
            p.drawRect(ox + cell, oy + cell, cell, cell)

        # Texto
        p.setPen(QPen(QColor("#94A3B8")))
        font = QFont("Inter", 8)
        p.setFont(font)
        p.drawText(
            QRectF(0, self._size * 0.65, self._size, self._size * 0.3),
            Qt.AlignmentFlag.AlignCenter,
            "QR",
        )
        p.end()
        self.setPixmap(pix)

    def set_qr_data(self, data: str) -> None:
        """Genera un código QR real a partir de *data*."""
        self._qr_data = data
        if not data:
            self._set_placeholder()
            return
        try:
            import qrcode  # type: ignore[import-untyped]
            from PIL import Image as PILImage  # type: ignore[import-untyped]

            qr = qrcode.QRCode(box_size=4, border=2)
            qr.add_data(data)
            qr.make(fit=True)
            img: PILImage.Image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            img = img.resize((self._size, self._size), PILImage.Resampling.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)

            qimg = QImage()
            qimg.loadFromData(buf.read())
            self.setPixmap(QPixmap.fromImage(qimg))
        except Exception:
            self._set_placeholder()

    # -- Paint override -----------------------------------------------------
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        QGraphicsPixmapItem.paint(self, painter, option, widget)
        self._draw_selection_rect(painter, self.boundingRect())

    # -- Serialización ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update(qr_data=self._qr_data, size=self._size)
        return d


# ═══════════════════════════════════════════════════════════════════════════
# ShapeCanvasItem
# ═══════════════════════════════════════════════════════════════════════════
class ShapeCanvasItem(BaseCanvasItem, QGraphicsRectItem):
    """Elemento de forma rectangular configurable."""

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 100,
        height: float = 50,
        parent: QGraphicsItem | None = None,
    ) -> None:
        QGraphicsRectItem.__init__(self, 0, 0, width, height, parent)
        self._init_flags()
        self._fill_color = "#E2E8F0"
        self._border_color = "#171A2B"
        self.border_width = 1
        self._width = width
        self._height = height
        self._apply_style()

    @property
    def element_type(self) -> str:
        return "shape"

    @property
    def fill_color(self) -> str:
        return self._fill_color

    def set_fill_color(self, color: str) -> None:
        self._fill_color = color
        self._apply_style()

    @property
    def border_color(self) -> str:
        return self._border_color

    def set_border_color(self, color: str) -> None:
        self._border_color = color
        self._apply_style()

    def _apply_style(self) -> None:
        self.setBrush(QBrush(QColor(self._fill_color)))
        self.setPen(QPen(QColor(self._border_color), self.border_width))

    # -- Paint override -----------------------------------------------------
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        QGraphicsRectItem.paint(self, painter, option, widget)
        self._draw_selection_rect(painter, self.rect())

    # -- Serialización ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update(
            fill_color=self._fill_color,
            border_color=self._border_color,
            border_width=self.border_width,
            width=self.rect().width(),
            height=self.rect().height(),
        )
        return d


# ═══════════════════════════════════════════════════════════════════════════
# BarcodeCanvasItem
# ═══════════════════════════════════════════════════════════════════════════
class BarcodeCanvasItem(BaseCanvasItem, QGraphicsPixmapItem):
    """Elemento de código de barras."""

    def __init__(
        self,
        width: int = 150,
        height: int = 50,
        parent: QGraphicsItem | None = None,
    ) -> None:
        QGraphicsPixmapItem.__init__(self, parent)
        self._init_flags()
        self._width = width
        self._height = height
        self._barcode_data: str = ""
        self._set_placeholder()

    @property
    def element_type(self) -> str:
        return "barcode"

    @property
    def barcode_data(self) -> str:
        return self._barcode_data

    @barcode_data.setter
    def barcode_data(self, value: str) -> None:
        self._barcode_data = value

    def _set_placeholder(self) -> None:
        """Genera un placeholder con patrón de líneas verticales."""
        pix = QPixmap(self._width, self._height)
        pix.fill(QColor("#EEF2F7"))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Borde
        p.setPen(QPen(QColor("#CBD5E1"), 1, Qt.PenStyle.DashLine))
        p.drawRect(0, 0, self._width - 1, self._height - 1)

        # Líneas de código de barras
        import random

        random.seed(42)  # Determinista para el placeholder
        bar_x = 10
        color = QColor("#94A3B8")
        while bar_x < self._width - 10:
            w = random.choice([1, 2, 3])
            if random.random() > 0.4:
                p.fillRect(bar_x, 6, w, self._height - 18, color)
            bar_x += w + random.choice([1, 2])

        # Texto inferior
        p.setPen(QPen(QColor("#94A3B8")))
        font = QFont("Inter", 7)
        p.setFont(font)
        p.drawText(
            QRectF(0, self._height - 14, self._width, 12),
            Qt.AlignmentFlag.AlignCenter,
            "CÓDIGO DE BARRAS",
        )
        p.end()
        self.setPixmap(pix)

    # -- Paint override -----------------------------------------------------
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        QGraphicsPixmapItem.paint(self, painter, option, widget)
        self._draw_selection_rect(painter, self.boundingRect())

    # -- Serialización ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update(
            barcode_data=self._barcode_data,
            width=self._width,
            height=self._height,
        )
        return d
