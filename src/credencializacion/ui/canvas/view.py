"""
Vista del lienzo de credenciales.

Proporciona zoom (Ctrl + rueda), paneo (botón central) y zona de
*drop* para recibir elementos arrastrados desde la barra de herramientas.
"""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QWheelEvent
from PySide6.QtWidgets import QGraphicsView

# ---------------------------------------------------------------------------
# Constantes de zoom
# ---------------------------------------------------------------------------
ZOOM_MIN = 25
ZOOM_MAX = 400
ZOOM_STEP = 10
ZOOM_DEFAULT = 100


class CredentialView(QGraphicsView):
    """Vista del lienzo con zoom, paneo y soporte de *drag & drop*."""

    # Señales ---------------------------------------------------------------
    zoom_changed = Signal(int)
    element_dropped = Signal(str, QPointF)  # (tipo_elemento, posición_escena)

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._zoom_percent = ZOOM_DEFAULT

        # Configuración de renderizado
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.TextAntialiasing
        )
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(
            QGraphicsView.ViewportAnchor.AnchorViewCenter
        )
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate
        )

        # Fondo
        self.setStyleSheet("QGraphicsView { background-color: #F5F7FA; border: none; }")

        # Aceptar drops
        self.setAcceptDrops(True)

    # ── Zoom ───────────────────────────────────────────────────────────────
    @property
    def zoom_percent(self) -> int:
        return self._zoom_percent

    def zoom_to(self, percent: int) -> None:
        """Establece el nivel de zoom al porcentaje dado."""
        percent = max(ZOOM_MIN, min(ZOOM_MAX, percent))
        factor = percent / self._zoom_percent
        self._zoom_percent = percent
        self.scale(factor, factor)
        self.zoom_changed.emit(self._zoom_percent)

    def zoom_in(self) -> None:
        self.zoom_to(self._zoom_percent + ZOOM_STEP)

    def zoom_out(self) -> None:
        self.zoom_to(self._zoom_percent - ZOOM_STEP)

    def zoom_reset(self) -> None:
        self.zoom_to(ZOOM_DEFAULT)

    # ── Wheel event (Ctrl + rueda) ─────────────────────────────────────────
    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)

    # ── Pan con botón central ──────────────────────────────────────────────
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            # Emular un clic izquierdo para activar el arrastre
            fake = QMouseEvent(
                event.type(),
                event.position(),
                event.globalPosition(),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                event.modifiers(),
            )
            super().mousePressEvent(fake)
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            fake = QMouseEvent(
                event.type(),
                event.position(),
                event.globalPosition(),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                event.modifiers(),
            )
            super().mouseReleaseEvent(fake)
            return
        super().mouseReleaseEvent(event)

    # ── Drag & Drop ────────────────────────────────────────────────────────
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat("application/x-canvas-element"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat("application/x-canvas-element"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat("application/x-canvas-element"):
            raw = bytes(event.mimeData().data("application/x-canvas-element"))
            try:
                data = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                event.ignore()
                return

            scene_pos = self.mapToScene(event.position().toPoint())
            self.element_dropped.emit(
                json.dumps(data),
                scene_pos,
            )
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
