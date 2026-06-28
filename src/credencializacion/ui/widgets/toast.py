"""
Toast Notification System — Sistema de Credencialización
=========================================================
Proporciona notificaciones emergentes estilo "toast" que se muestran en la
esquina inferior-derecha de la ventana principal.

Uso:
    from credencializacion.ui.widgets.toast import ToastManager
    ToastManager.instance().show_toast("Mensaje", level="success")

Niveles disponibles: 'info', 'success', 'error', 'warning', 'sync'
"""
from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QWidget

# ── Paleta de colores para cada nivel ──────────────────────────────────────
_LEVEL_COLORS: dict[str, dict[str, str]] = {
    "info": {
        "bg": "#1E293B",
        "border": "#334155",
        "fg": "#94A3B8",
        "icon": "ℹ️",
        "accent": "#3B82F6",
    },
    "success": {
        "bg": "#052E16",
        "border": "#14532D",
        "fg": "#4ADE80",
        "icon": "✅",
        "accent": "#22C55E",
    },
    "error": {
        "bg": "#450A0A",
        "border": "#7F1D1D",
        "fg": "#FCA5A5",
        "icon": "❌",
        "accent": "#EF4444",
    },
    "warning": {
        "bg": "#451A03",
        "border": "#78350F",
        "fg": "#FCD34D",
        "icon": "⚠️",
        "accent": "#F59E0B",
    },
    "sync": {
        "bg": "#0F172A",
        "border": "#1E3A5F",
        "fg": "#93C5FD",
        "icon": "🔄",
        "accent": "#2563EB",
    },
}

_DURATION_MS = 3500   # tiempo visible (ms)
_ANIM_IN_MS  = 280    # duración animación entrada
_ANIM_OUT_MS = 320    # duración animación salida
_WIDTH       = 340    # ancho del toast
_HEIGHT      = 68     # alto del toast
_MARGIN_RIGHT = 20    # margen derecho desde el borde de la ventana
_MARGIN_TOP  = 20     # margen superior desde el borde de la ventana
_MARGIN_BOTTOM = 20   # margen inferior base (no usado en modo superior)
_SPACING      = 10    # espacio entre toasts apilados


def _anchor_geometry() -> "QRect":
    """Geometría (coords globales) a la que se anclan los toasts.

    Usa el área de la ventana principal de la app para que los toasts aparezcan
    **dentro** de la aplicación (esquina superior derecha). Si no hay ventana
    principal visible, cae al área disponible de la pantalla.
    """
    app = QApplication.instance()
    if app is not None:
        from PySide6.QtWidgets import QMainWindow

        for w in app.topLevelWidgets():
            if isinstance(w, QMainWindow) and w.isVisible():
                return w.geometry()
    screen = QApplication.primaryScreen()
    return screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)


class ToastWidget(QWidget):
    """Un único toast flotante animado."""

    closed = Signal(object)  # emite self al cerrarse

    def __init__(self, message: str, level: str = "info", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._level = level
        self._colors = _LEVEL_COLORS.get(level, _LEVEL_COLORS["info"])
        self._message = message

        # Sin marco de ventana, siempre encima, sin foco
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(_WIDTH, _HEIGHT)

        self._build_ui()
        self._anim_in: QPropertyAnimation | None = None
        self._anim_out: QPropertyAnimation | None = None
        self._reposition_anim: QPropertyAnimation | None = None
        self._closing: bool = False
        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.timeout.connect(self._start_fade_out)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        c = self._colors

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)

        # Barra de acento izquierda (simulada por margen + fondo)
        accent_bar = QWidget()
        accent_bar.setFixedWidth(4)
        accent_bar.setStyleSheet(f"background-color: {c['accent']}; border-radius: 2px;")
        layout.addWidget(accent_bar)

        # Icono
        icon_lbl = QLabel(c["icon"])
        icon_lbl.setStyleSheet("background: transparent; font-size: 18px;")
        icon_lbl.setFixedWidth(28)
        layout.addWidget(icon_lbl)

        # Mensaje
        msg_lbl = QLabel(self._message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(f"""
            QLabel {{
                background: transparent;
                color: {c['fg']};
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 12px;
                font-weight: 600;
            }}
        """)
        layout.addWidget(msg_lbl, stretch=1)

        # Botón cerrar
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {c['fg']};
                border: none;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: #FFFFFF;
            }}
        """)
        close_btn.clicked.connect(self._start_fade_out)
        layout.addWidget(close_btn)

    def paintEvent(self, event) -> None:  # noqa: N802
        """Dibuja fondo redondeado con borde coloreado."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        c = self._colors
        bg = QColor(c["bg"])
        bg.setAlpha(int(self.windowOpacity() * 240))

        border = QColor(c["border"])

        path = QPainterPath()
        path.addRoundedRect(self.rect(), 12, 12)

        painter.fillPath(path, bg)
        painter.setPen(border)
        painter.drawPath(path)

    # --------------------------------------------------------------- slots
    def show_animated(self, target_pos: QPoint) -> None:
        """Muestra el toast con animación de deslizamiento desde la derecha."""
        geo = _anchor_geometry()
        start_pos = QPoint(geo.right() + 20, target_pos.y())

        self.move(start_pos)
        self.show()

        self._anim_in = QPropertyAnimation(self, b"pos", self)
        self._anim_in.setDuration(_ANIM_IN_MS)
        self._anim_in.setStartValue(start_pos)
        self._anim_in.setEndValue(target_pos)
        self._anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_in.start()

        self._close_timer.start(_DURATION_MS)

    def _start_fade_out(self) -> None:
        """Inicia animación de desvanecimiento y slide hacia la derecha."""
        if self._closing:
            return
        self._closing = True
        self._close_timer.stop()

        # Detener cualquier animación de reposicionamiento en curso para que no
        # compita con la salida (dos animaciones sobre `pos` se interfieren y la
        # salida nunca termina, dejando el toast fijo en pantalla).
        if self._reposition_anim is not None:
            self._reposition_anim.stop()
            self._reposition_anim = None

        geo = _anchor_geometry()

        self._anim_out = QPropertyAnimation(self, b"pos", self)
        self._anim_out.setDuration(_ANIM_OUT_MS)
        self._anim_out.setStartValue(self.pos())
        self._anim_out.setEndValue(QPoint(geo.right() + 20, self.pos().y()))
        self._anim_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim_out.finished.connect(self._on_closed)
        self._anim_out.start()

    def _on_closed(self) -> None:
        self.closed.emit(self)
        self.hide()
        self.deleteLater()


# ── Gestor global (Singleton) ───────────────────────────────────────────────

class ToastManager:
    """Singleton que gestiona el apilamiento y posicionamiento de toasts."""

    _instance: ClassVar[ToastManager | None] = None
    _active: list[ToastWidget]

    def __init__(self) -> None:
        self._active = []

    @classmethod
    def instance(cls) -> "ToastManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ---------------------------------------------------------------- API
    def show_toast(self, message: str, level: str = "info") -> None:
        """Muestra un toast en la esquina superior-derecha de la ventana."""
        toast = ToastWidget(message, level)
        toast.closed.connect(self._on_toast_closed)
        self._active.append(toast)
        self._reposition_all()

    # ----------------------------------------------------------- internals
    def _reposition_all(self) -> None:
        """Recalcula la posición de los toasts (apilados de arriba hacia abajo).

        Se anclan a la esquina superior derecha del área de la ventana principal
        (dentro de la app); el más reciente queda debajo del anterior. Los toasts
        que ya están cerrándose se excluyen para no interferir con su animación
        de salida.
        """
        geo = _anchor_geometry()

        x = geo.right() - _WIDTH - _MARGIN_RIGHT
        y_top = geo.top() + _MARGIN_TOP

        visibles = [t for t in self._active if not getattr(t, "_closing", False)]
        for i, toast in enumerate(visibles):
            y = y_top + i * (_HEIGHT + _SPACING)
            target = QPoint(x, y)

            if toast.isVisible():
                # Ya visible → mover suavemente (guardado como atributo para
                # poder detenerlo si el toast empieza a cerrarse).
                anim = QPropertyAnimation(toast, b"pos", toast)
                anim.setDuration(200)
                anim.setEndValue(target)
                anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                toast._reposition_anim = anim
                anim.start()
            else:
                # Nuevo → mostrar con animación de entrada
                toast.show_animated(target)

    def _on_toast_closed(self, toast: ToastWidget) -> None:
        if toast in self._active:
            self._active.remove(toast)
        self._reposition_all()
