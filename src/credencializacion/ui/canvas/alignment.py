"""
Utilidades de alineación y ajuste a cuadrícula.

Contiene funciones libres para centrar/alinear/distribuir elementos
y la clase ``AlignmentGuides`` que dibuja guías temporales.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsLineItem, QGraphicsScene

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_GUIDE_COLOR = QColor("#3B82F6")
_GUIDE_PEN = QPen(_GUIDE_COLOR, 1.0, Qt.PenStyle.DashLine)


# ═══════════════════════════════════════════════════════════════════════════
# Funciones libres de alineación
# ═══════════════════════════════════════════════════════════════════════════

def center_horizontally(item: QGraphicsItem, scene_width: float) -> None:
    """Centra *item* horizontalmente dentro del ancho dado."""
    br = item.boundingRect()
    item.setX((scene_width - br.width()) / 2)


def center_vertically(item: QGraphicsItem, scene_height: float) -> None:
    """Centra *item* verticalmente dentro de la altura dada."""
    br = item.boundingRect()
    item.setY((scene_height - br.height()) / 2)


def center_both(
    item: QGraphicsItem, scene_width: float, scene_height: float
) -> None:
    """Centra *item* en ambos ejes."""
    center_horizontally(item, scene_width)
    center_vertically(item, scene_height)


def snap_to_grid(pos: QPointF, grid_size: float = 5.0) -> QPointF:
    """Devuelve la posición ajustada al punto de cuadrícula más cercano."""
    return QPointF(
        round(pos.x() / grid_size) * grid_size,
        round(pos.y() / grid_size) * grid_size,
    )


# ── Alinear varios elementos ──────────────────────────────────────────────

def align_items_left(items: list[QGraphicsItem]) -> None:
    """Alinea todos los elementos a la coordenada X del más a la izquierda."""
    if len(items) < 2:
        return
    min_x = min(it.x() for it in items)
    for it in items:
        it.setX(min_x)


def align_items_right(items: list[QGraphicsItem]) -> None:
    """Alinea todos los elementos al borde derecho del más a la derecha."""
    if len(items) < 2:
        return
    max_right = max(it.x() + it.boundingRect().width() for it in items)
    for it in items:
        it.setX(max_right - it.boundingRect().width())


def align_items_top(items: list[QGraphicsItem]) -> None:
    """Alinea todos los elementos al borde superior del más arriba."""
    if len(items) < 2:
        return
    min_y = min(it.y() for it in items)
    for it in items:
        it.setY(min_y)


def align_items_bottom(items: list[QGraphicsItem]) -> None:
    """Alinea todos los elementos al borde inferior del más abajo."""
    if len(items) < 2:
        return
    max_bottom = max(it.y() + it.boundingRect().height() for it in items)
    for it in items:
        it.setY(max_bottom - it.boundingRect().height())


def distribute_horizontally(items: list[QGraphicsItem]) -> None:
    """Distribuye los elementos uniformemente en el eje horizontal."""
    if len(items) < 3:
        return
    sorted_items = sorted(items, key=lambda it: it.x())
    first = sorted_items[0]
    last = sorted_items[-1]
    total_span = (last.x() + last.boundingRect().width()) - first.x()
    total_item_width = sum(it.boundingRect().width() for it in sorted_items)
    gap = (total_span - total_item_width) / (len(sorted_items) - 1)

    current_x = first.x()
    for it in sorted_items:
        it.setX(current_x)
        current_x += it.boundingRect().width() + gap


def distribute_vertically(items: list[QGraphicsItem]) -> None:
    """Distribuye los elementos uniformemente en el eje vertical."""
    if len(items) < 3:
        return
    sorted_items = sorted(items, key=lambda it: it.y())
    first = sorted_items[0]
    last = sorted_items[-1]
    total_span = (last.y() + last.boundingRect().height()) - first.y()
    total_item_height = sum(it.boundingRect().height() for it in sorted_items)
    gap = (total_span - total_item_height) / (len(sorted_items) - 1)

    current_y = first.y()
    for it in sorted_items:
        it.setY(current_y)
        current_y += it.boundingRect().height() + gap


# ═══════════════════════════════════════════════════════════════════════════
# AlignmentGuides
# ═══════════════════════════════════════════════════════════════════════════

class AlignmentGuides:
    """Muestra y oculta guías de alineación temporales en la escena."""

    def __init__(self, scene: QGraphicsScene) -> None:
        self._scene = scene
        self._guides: list[QGraphicsLineItem] = []

    # -- Mostrar una guía ---------------------------------------------------
    def show_guide(self, orientation: str, position: float) -> None:
        """Crea y muestra una guía en la *position* dada.

        Args:
            orientation: ``'horizontal'`` o ``'vertical'``.
            position: Coordenada Y (horizontal) o X (vertical) de la guía.
        """
        sr = self._scene.sceneRect()
        if orientation == "horizontal":
            line = QGraphicsLineItem(sr.left(), position, sr.right(), position)
        else:
            line = QGraphicsLineItem(position, sr.top(), position, sr.bottom())

        line.setPen(_GUIDE_PEN)
        line.setZValue(1000)
        line.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        line.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._scene.addItem(line)
        self._guides.append(line)

    # -- Ocultar todas las guías --------------------------------------------
    def hide_guides(self) -> None:
        """Elimina todas las guías de la escena."""
        for guide in self._guides:
            self._scene.removeItem(guide)
        self._guides.clear()

    # -- Verificar alineación -----------------------------------------------
    def check_alignment(
        self,
        item: QGraphicsItem,
        all_items: list[QGraphicsItem],
        threshold: float = 3.0,
    ) -> list[QPointF]:
        """Comprueba si *item* se alinea con otros elementos.

        Muestra guías automáticamente y devuelve los puntos de *snap*
        sugeridos.
        """
        self.hide_guides()
        snaps: list[QPointF] = []

        item_rect = item.sceneBoundingRect()
        item_cx = item_rect.center().x()
        item_cy = item_rect.center().y()

        for other in all_items:
            if other is item:
                continue
            other_rect = other.sceneBoundingRect()
            other_cx = other_rect.center().x()
            other_cy = other_rect.center().y()

            # Centro horizontal
            if abs(item_cx - other_cx) < threshold:
                self.show_guide("vertical", other_cx)
                snaps.append(QPointF(other_cx - item_rect.width() / 2, item.y()))

            # Centro vertical
            if abs(item_cy - other_cy) < threshold:
                self.show_guide("horizontal", other_cy)
                snaps.append(QPointF(item.x(), other_cy - item_rect.height() / 2))

            # Borde izquierdo
            if abs(item_rect.left() - other_rect.left()) < threshold:
                self.show_guide("vertical", other_rect.left())

            # Borde superior
            if abs(item_rect.top() - other_rect.top()) < threshold:
                self.show_guide("horizontal", other_rect.top())

            # Borde derecho
            if abs(item_rect.right() - other_rect.right()) < threshold:
                self.show_guide("vertical", other_rect.right())

            # Borde inferior
            if abs(item_rect.bottom() - other_rect.bottom()) < threshold:
                self.show_guide("horizontal", other_rect.bottom())

        return snaps
