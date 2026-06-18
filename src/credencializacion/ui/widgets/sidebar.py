"""
Widget de barra lateral (sidebar) reutilizable.
Implementa navegación vertical con ítems seleccionables, separador,
logo y botón CTA.
"""
from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from credencializacion.ui.styles import COLORS


class SidebarItem(QPushButton):
    """Botón de navegación para la sidebar con ícono y texto.

    Gestiona su propio estado activo (estilo resaltado con línea de
    acento a la izquierda).
    """

    def __init__(
        self,
        icon_text: str,
        label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setMinimumHeight(42)

        # Create layout for icon and text
        btn_layout = QHBoxLayout(self)
        btn_layout.setContentsMargins(16, 0, 16, 0)
        btn_layout.setSpacing(12)

        # Setup Icon Label via qtawesome
        self._icon_lbl = QLabel()
        self._icon_name = icon_text  # store for color updates
        self._icon_lbl.setFixedSize(20, 20)
        self._icon_lbl.setPixmap(
            qta.icon(icon_text, color=COLORS["text_light"]).pixmap(QSize(20, 20))
        )
        self._icon_lbl.setStyleSheet("background: transparent; border: none;")

        # Setup Text Label
        self._text_lbl = QLabel(label)
        self._text_lbl.setStyleSheet("background: transparent; border: none;")
        font = self.font()
        font.setPointSize(12)
        font.setWeight(QFont.Weight.Medium)
        self._text_lbl.setFont(font)

        btn_layout.addWidget(self._icon_lbl)
        btn_layout.addWidget(self._text_lbl)
        btn_layout.addStretch()

        self._apply_base_style()

    # ------------------------------------------------------------------ style
    def _apply_base_style(self) -> None:
        self.setStyleSheet(self._build_stylesheet(active=False))

    def set_active(self, active: bool) -> None:
        """Marca/desmarca el ítem como activo."""
        self.setChecked(active)
        self.setStyleSheet(self._build_stylesheet(active=active))
        # Actualizar color del ícono
        icon_color = COLORS["primary"] if active else COLORS["text_light"]
        self._icon_lbl.setPixmap(
            qta.icon(self._icon_name, color=icon_color).pixmap(QSize(20, 20))
        )

    @staticmethod
    def _build_stylesheet(*, active: bool) -> str:
        c = COLORS
        if active:
            return f"""
                QPushButton {{
                    background-color: {c["bg_sidebar_active"]};
                    color: {c["primary"]};
                    border: none;
                    border-left: 3px solid {c["primary"]};
                    border-radius: 0;
                    text-align: left;
                    padding: 10px 16px 10px 13px;
                    font-weight: 600;
                }}
            """
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {c["text_light"]};
                border: none;
                border-left: 3px solid transparent;
                border-radius: 0;
                text-align: left;
                padding: 10px 16px 10px 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {c["bg_sidebar_hover"]};
                color: {c["text"]};
            }}
        """


class Sidebar(QWidget):
    """Barra lateral de navegación principal.

    Emite ``page_changed(int)`` cuando el usuario cambia de sección.
    """

    page_changed = Signal(int)

    # Definición de ítems de navegación
    # (icono_qta, etiqueta, es_seccion_inferior)
    NAV_ITEMS: list[tuple[str, str, bool]] = [
        ("fa5s.th-large", "Panel de Control", False),
        ("fa5s.palette", "Editor de Plantillas", False),
        ("fa5s.clone", "Gestión Plantillas", False),
        ("fa5s.print", "Centro de Impresión", False),
    ]

    BOTTOM_ITEMS: list[tuple[str, str, bool]] = [
        ("fa5s.cog", "Configuración", True),
        ("fa5s.life-ring", "Soporte", True),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(220)
        self.setMinimumHeight(600)

        self._items: list[SidebarItem] = []
        self._current_index: int = 0

        self._setup_ui()
        # Activar primer ítem por defecto
        if self._items:
            self._items[0].set_active(True)

    # ------------------------------------------------------------------ UI
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Logo ---
        layout.addWidget(self._create_logo_area())

        # --- Separador sutil ---
        layout.addWidget(self._create_separator())

        # --- Ítems de navegación principal ---
        for icon, label, _ in self.NAV_ITEMS:
            item = SidebarItem(icon, label)
            item.clicked.connect(
                lambda checked, idx=len(self._items): self._on_item_clicked(idx)
            )
            layout.addWidget(item)
            self._items.append(item)

        # --- Spacer flexible ---
        layout.addItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

        # --- Separador inferior ---
        layout.addWidget(self._create_separator())

        # --- Ítems inferiores ---
        for icon, label, _ in self.BOTTOM_ITEMS:
            item = SidebarItem(icon, label)
            item.clicked.connect(
                lambda checked, idx=len(self._items): self._on_item_clicked(idx)
            )
            layout.addWidget(item)
            self._items.append(item)

        layout.addSpacing(12)

        # Padding inferior
        layout.addSpacing(16)

    def _create_logo_area(self) -> QWidget:
        """Crea el área de logo con icono + título + subtítulo."""
        from pathlib import Path
        from PySide6.QtGui import QPixmap

        container = QWidget()
        container.setFixedHeight(70)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 8)
        layout.setSpacing(8)

        # Ícono de la app (desde resources/icon.png)
        icon_label = QLabel()
        icon_label.setFixedSize(40, 40)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("background: transparent; border: none;")
        icon_path = Path(__file__).parent.parent.parent / "resources" / "icon.png"
        if icon_path.exists():
            pix = QPixmap(str(icon_path)).scaled(
                40, 40,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            icon_label.setPixmap(pix)
        else:
            # Fallback: cuadro rojo con "ME"
            icon_label.setText("ME")
            icon_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {COLORS["primary"]};
                    color: {COLORS["text_white"]};
                    border-radius: 10px;
                    font-size: 15px;
                    font-weight: 800;
                }}
            """)
        layout.addWidget(icon_label)

        # Texto al lado del ícono (centrado verticalmente, sin espacio)
        text_container = QWidget()
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        title = QLabel("miescuela.net")
        title.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["text"]};
                font-size: 16px;
                font-weight: 800;
                line-height: 1;
            }}
        """)
        text_layout.addWidget(title)

        subtitle = QLabel("Credencialización")
        subtitle.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["text_light"]};
                font-size: 11px;
                font-weight: 500;
                line-height: 1;
            }}
        """)
        text_layout.addWidget(subtitle)

        layout.addWidget(text_container)
        layout.addStretch()

        return container

    @staticmethod
    def _create_separator() -> QFrame:
        """Línea separadora sutil."""
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 0.08);
                border: none;
                margin: 8px 16px;
            }
        """)
        return sep

    # --------------------------------------------------------------- slots
    def _on_item_clicked(self, index: int) -> None:
        """Maneja el clic en un ítem de navegación."""
        if index == self._current_index:
            return

        # Desactivar anterior
        if 0 <= self._current_index < len(self._items):
            self._items[self._current_index].set_active(False)

        # Activar nuevo
        self._current_index = index
        self._items[index].set_active(True)

        self.page_changed.emit(index)

    # --------------------------------------------------------------- API
    def set_current_index(self, index: int) -> None:
        """Cambia programáticamente la sección activa."""
        self._on_item_clicked(index)

    @property
    def current_index(self) -> int:
        return self._current_index
