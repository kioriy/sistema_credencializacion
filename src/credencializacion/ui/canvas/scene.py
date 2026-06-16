"""
Escena gráfica del lienzo de credenciales.

Gestiona la representación visual de la tarjeta de credencial,
incluyendo fondo, cuadrícula y los elementos de diseño del usuario.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
)

from credencializacion.ui.canvas.items import (
    BaseCanvasItem,
    BarcodeCanvasItem,
    ImageCanvasItem,
    QRCanvasItem,
    ShapeCanvasItem,
    TextCanvasItem,
)

# ---------------------------------------------------------------------------
# Constantes de conversión y dimensiones
# ---------------------------------------------------------------------------
CM_TO_PX: float = 37.795275591  # 1 cm → px a 96 DPI

DEFAULT_CARD_WIDTH_CM: float = 8.5
DEFAULT_CARD_HEIGHT_CM: float = 5.4

CARD_CORNER_RADIUS: float = 8.0
SCENE_MARGIN: float = 80.0  # margen alrededor de la tarjeta

GRID_STEP_MM: float = 5.0  # cuadrícula cada 5 mm
GRID_STEP_PX: float = GRID_STEP_MM * CM_TO_PX / 10.0


class CredentialScene(QGraphicsScene):
    """Escena que contiene la tarjeta de credencial y sus elementos."""

    # Señales ---------------------------------------------------------------
    item_selected = Signal(object)

    def __init__(
        self,
        card_width_cm: float = DEFAULT_CARD_WIDTH_CM,
        card_height_cm: float = DEFAULT_CARD_HEIGHT_CM,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)

        self._card_w = card_width_cm * CM_TO_PX
        self._card_h = card_height_cm * CM_TO_PX
        self._grid_visible = False

        # Definir el área de escena (tarjeta + márgenes)
        total_w = self._card_w + SCENE_MARGIN * 2
        total_h = self._card_h + SCENE_MARGIN * 2
        self.setSceneRect(0, 0, total_w, total_h)

        # Color de fondo de la escena
        self.setBackgroundBrush(QBrush(QColor("#F5F7FA")))

        # Crear la tarjeta (rectángulo de fondo blanco)
        self._card_rect = QGraphicsRectItem(
            SCENE_MARGIN,
            SCENE_MARGIN,
            self._card_w,
            self._card_h,
        )
        self._card_rect.setBrush(QBrush(QColor("#FFFFFF")))
        self._card_rect.setPen(QPen(Qt.PenStyle.NoPen))
        self._card_rect.setZValue(-100)
        # No seleccionable
        self._card_rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._card_rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        # Sombra
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 35))
        self._card_rect.setGraphicsEffect(shadow)
        self.addItem(self._card_rect)

        # Borde punteado
        self._card_border = QGraphicsRectItem(
            SCENE_MARGIN,
            SCENE_MARGIN,
            self._card_w,
            self._card_h,
        )
        pen = QPen(QColor("#CBD5E1"), 1.0, Qt.PenStyle.DashLine)
        self._card_border.setPen(pen)
        self._card_border.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._card_border.setZValue(-99)
        self._card_border.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._card_border.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.addItem(self._card_border)

        # Conectar selección
        self.selectionChanged.connect(self._on_selection_changed)

    # ── Propiedades ────────────────────────────────────────────────────────
    @property
    def card_width(self) -> float:
        return self._card_w

    @property
    def card_height(self) -> float:
        return self._card_h

    @property
    def card_rect(self) -> QRectF:
        """Rectángulo de la tarjeta en coordenadas de escena."""
        return QRectF(SCENE_MARGIN, SCENE_MARGIN, self._card_w, self._card_h)

    # ── Cuadrícula ─────────────────────────────────────────────────────────
    def set_grid_visible(self, visible: bool) -> None:
        self._grid_visible = visible
        self.update()

    @property
    def grid_visible(self) -> bool:
        return self._grid_visible

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        super().drawBackground(painter, rect)

        if not self._grid_visible:
            return

        card = self.card_rect
        painter.setPen(QPen(QColor(200, 200, 200, 80), 0.5))

        # Verticales
        x = card.left()
        while x <= card.right():
            painter.drawLine(
                int(x), int(card.top()), int(x), int(card.bottom())
            )
            x += GRID_STEP_PX

        # Horizontales
        y = card.top()
        while y <= card.bottom():
            painter.drawLine(
                int(card.left()), int(y), int(card.right()), int(y)
            )
            y += GRID_STEP_PX

    # ── Agregar elementos ──────────────────────────────────────────────────
    def add_text_item(
        self, text: str = "", x: float = 0, y: float = 0, **kwargs: Any
    ) -> TextCanvasItem:
        item = TextCanvasItem(text=text)
        item.setPos(SCENE_MARGIN + x, SCENE_MARGIN + y)
        if "font_family" in kwargs:
            item.set_font_family(kwargs["font_family"])
        if "font_size" in kwargs:
            item.set_font_size(kwargs["font_size"])
        if "font_weight" in kwargs:
            item.set_font_weight(kwargs["font_weight"])
        if "font_color" in kwargs:
            item.set_font_color(kwargs["font_color"])
        if "alignment" in kwargs:
            item.set_alignment(kwargs["alignment"])
        if "campo_dato" in kwargs:
            item.campo_dato = kwargs["campo_dato"]
        self.addItem(item)
        return item

    def add_image_item(
        self, x: float = 0, y: float = 0, w: int = 100, h: int = 100
    ) -> ImageCanvasItem:
        item = ImageCanvasItem(width=w, height=h)
        item.setPos(SCENE_MARGIN + x, SCENE_MARGIN + y)
        self.addItem(item)
        return item

    def add_qr_item(
        self, x: float = 0, y: float = 0, size: int = 80
    ) -> QRCanvasItem:
        item = QRCanvasItem(size=size)
        item.setPos(SCENE_MARGIN + x, SCENE_MARGIN + y)
        self.addItem(item)
        return item

    def add_shape_item(
        self, x: float = 0, y: float = 0, w: float = 100, h: float = 50, **kwargs: Any
    ) -> ShapeCanvasItem:
        item = ShapeCanvasItem(width=w, height=h)
        item.setPos(SCENE_MARGIN + x, SCENE_MARGIN + y)
        if "fill_color" in kwargs:
            item.set_fill_color(kwargs["fill_color"])
        if "border_color" in kwargs:
            item.set_border_color(kwargs["border_color"])
        if "border_width" in kwargs:
            item.border_width = kwargs["border_width"]
            item._apply_style()
        self.addItem(item)
        return item

    def add_barcode_item(
        self, x: float = 0, y: float = 0, w: int = 150, h: int = 50
    ) -> BarcodeCanvasItem:
        item = BarcodeCanvasItem(width=w, height=h)
        item.setPos(SCENE_MARGIN + x, SCENE_MARGIN + y)
        self.addItem(item)
        return item

    # ── Gestión de elementos ───────────────────────────────────────────────
    def custom_items(self) -> list[BaseCanvasItem]:
        """Devuelve solo los elementos del usuario (no el fondo)."""
        return [
            it
            for it in self.items()
            if isinstance(it, BaseCanvasItem)
        ]

    def clear_items(self) -> None:
        """Elimina todos los elementos excepto el fondo de la tarjeta."""
        for it in self.custom_items():
            self.removeItem(it)

    # ── Serialización ──────────────────────────────────────────────────────
    def serialize(self) -> list[dict[str, Any]]:
        """Serializa todos los elementos del usuario a una lista de dicts."""
        return [it.to_dict() for it in self.custom_items()]

    def deserialize(self, elements: list[dict[str, Any]]) -> None:
        """Limpia y restaura elementos desde una lista de dicts."""
        self.clear_items()
        for data in elements:
            item = BaseCanvasItem.from_dict(data)
            self.addItem(item)  # type: ignore[arg-type]

    # ── Señal de selección ─────────────────────────────────────────────────
    def _on_selection_changed(self) -> None:
        selected = self.selectedItems()
        if selected:
            item = selected[0]
            if isinstance(item, BaseCanvasItem):
                self.item_selected.emit(item)
        else:
            self.item_selected.emit(None)
