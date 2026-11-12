"""
Layout que acomoda los widgets en fila y baja de renglón cuando no caben.

Se usa en la fila de numeralias del Panel de Control: son siete u ocho pills
y el panel comparte el ancho con la cola de impresión, así que en una sola
línea el texto se corta ("📋 Sin formulari…") justo donde está el número que
se quiere leer.

Es el patrón FlowLayout clásico de Qt, reducido a lo que aquí se necesita.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QSizePolicy, QWidget


class FlowLayout(QLayout):
    """Coloca los widgets de izquierda a derecha, envolviendo por ancho."""

    def __init__(
        self,
        parent: QWidget | None = None,
        margin: int = 0,
        spacing: int = 8,
    ) -> None:
        super().__init__(parent)
        self._items: list = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    # ── Interfaz de QLayout ──────────────────────────────────────────

    def addItem(self, item) -> None:  # noqa: N802 (API de Qt)
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), probe=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, probe=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )

    # ── Acomodo ──────────────────────────────────────────────────────

    def _do_layout(self, rect: QRect, probe: bool) -> int:
        """Acomoda (o solo mide, con ``probe``) y devuelve el alto usado."""
        margins = self.contentsMargins()
        efectivo = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x, y = efectivo.x(), efectivo.y()
        alto_linea = 0
        espacio = self.spacing()

        for item in self._items:
            ancho = item.sizeHint().width()
            alto = item.sizeHint().height()
            siguiente = x + ancho
            if siguiente > efectivo.right() + 1 and alto_linea > 0:
                # No cabe en este renglón: bajar al siguiente.
                x = efectivo.x()
                y = y + alto_linea + espacio
                siguiente = x + ancho
                alto_linea = 0
            if not probe:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = siguiente + espacio
            alto_linea = max(alto_linea, alto)

        return y + alto_linea - rect.y() + margins.bottom()
