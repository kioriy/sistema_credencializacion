"""
Panel de propiedades del elemento seleccionado.

Muestra secciones colapsables con controles de tipografía, posición /
tamaño y campo de dato vinculado.  Se actualiza en tiempo real.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from credencializacion.ui.canvas.items import (
    BaseCanvasItem,
    TextCanvasItem,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
CM_TO_PX: float = 37.795275591
_PX_TO_MM: float = 10.0 / CM_TO_PX  # px → mm

_FIELDS = [
    "Ninguno",
    "nombre",
    "apellidos",
    "matricula",
    "escuela",
    "carrera",
    "semestre",
    "grupo",
    "turno",
    "curp",
    "foto",
    "codigo_qr",
    "codigo_barras",
]


# ═══════════════════════════════════════════════════════════════════════════
# Sección colapsable
# ═══════════════════════════════════════════════════════════════════════════
class _CollapsibleSection(QWidget):
    """Contenedor con título clicable que expande / colapsa su contenido."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Cabecera
        self._header = QPushButton(f"▼  {title}")
        self._header.setFlat(True)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setStyleSheet(
            """
            QPushButton {
                text-align: left;
                font-size: 11px;
                font-weight: 700;
                color: #64748B;
                letter-spacing: 1px;
                padding: 10px 12px;
                background: transparent;
                border: none;
                border-bottom: 1px solid #E2E8F0;
            }
            QPushButton:hover { color: #171A2B; }
            """
        )
        self._header.clicked.connect(self._toggle)
        layout.addWidget(self._header)

        # Contenido
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 10, 12, 10)
        self._content_layout.setSpacing(8)
        layout.addWidget(self._content)

        self._expanded = True
        self._title = title

    @property
    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        arrow = "▼" if self._expanded else "▶"
        self._header.setText(f"{arrow}  {self._title}")

    def set_visible_section(self, visible: bool) -> None:
        self.setVisible(visible)


# ═══════════════════════════════════════════════════════════════════════════
# Fila de label + widget helper
# ═══════════════════════════════════════════════════════════════════════════
def _make_row(label_text: str, widget: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    lbl = QLabel(label_text)
    lbl.setFixedWidth(60)
    lbl.setStyleSheet("font-size: 12px; color: #64748B;")
    row.addWidget(lbl)
    row.addWidget(widget, 1)
    return row


# ═══════════════════════════════════════════════════════════════════════════
# PropertiesPanel
# ═══════════════════════════════════════════════════════════════════════════
class PropertiesPanel(QWidget):
    """Panel lateral que muestra y edita las propiedades del elemento
    seleccionado en el lienzo."""

    property_changed = Signal(object, str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_item: BaseCanvasItem | None = None
        self._updating = False  # Evita bucles de retroalimentación

        self.setMinimumWidth(260)
        self.setMaximumWidth(320)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self._build_ui()

    # ── Construcción de UI ─────────────────────────────────────────────────
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Título
        title = QLabel("Propiedades")
        title.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #171A2B; padding: 16px 16px 8px;"
        )
        outer.addWidget(title)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        container = QWidget()
        self._main_layout = QVBoxLayout(container)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)
        scroll.setWidget(container)

        # Placeholder «sin selección»
        self._empty_label = QLabel("Selecciona un elemento")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            "color: #64748B; font-size: 13px; padding: 40px 12px;"
        )
        self._main_layout.addWidget(self._empty_label)

        # ── Sección: Tipografía ────────────────────────────────────────────
        self._sec_typo = _CollapsibleSection("TIPOGRAFÍA")
        cl = self._sec_typo.content_layout

        self._font_combo = QFontComboBox()
        self._font_combo.setCurrentFont(QFont("Inter"))
        self._font_combo.currentFontChanged.connect(
            lambda f: self._emit("font_family", f.family())
        )
        cl.addLayout(_make_row("Fuente", self._font_combo))

        self._size_spin = QSpinBox()
        self._size_spin.setRange(6, 144)
        self._size_spin.setValue(12)
        self._size_spin.setSuffix(" pt")
        self._size_spin.valueChanged.connect(
            lambda v: self._emit("font_size", v)
        )
        cl.addLayout(_make_row("Tamaño", self._size_spin))

        self._weight_combo = QComboBox()
        self._weight_combo.addItems(["Regular", "Negrita", "Ligera"])
        self._weight_combo.currentIndexChanged.connect(
            lambda _: self._emit(
                "font_weight",
                {"Regular": "normal", "Negrita": "bold", "Ligera": "light"}[
                    self._weight_combo.currentText()
                ],
            )
        )
        cl.addLayout(_make_row("Peso", self._weight_combo))

        # Alineación — 4 botones toggle
        align_row = QHBoxLayout()
        align_row.setSpacing(2)
        self._align_buttons: dict[str, QPushButton] = {}
        for symbol, value in [("☰ ◀", "left"), ("☰", "center"), ("▶ ☰", "right"), ("☰☰", "justify")]:
            btn = QPushButton(symbol)
            btn.setFixedSize(36, 30)
            btn.setCheckable(True)
            btn.setStyleSheet(self._align_btn_style(False))
            btn.clicked.connect(lambda checked, v=value: self._on_align(v))
            self._align_buttons[value] = btn
            align_row.addWidget(btn)
        align_row.addStretch()
        lbl_align = QLabel("Alinear")
        lbl_align.setFixedWidth(60)
        lbl_align.setStyleSheet("font-size: 12px; color: #64748B;")
        row_wrap = QHBoxLayout()
        row_wrap.setSpacing(8)
        row_wrap.addWidget(lbl_align)
        row_wrap.addLayout(align_row)
        cl.addLayout(row_wrap)

        # Color
        self._color_btn = QPushButton("")
        self._color_btn.setFixedSize(36, 30)
        self._color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._current_color = "#171A2B"
        self._update_color_btn()
        self._color_btn.clicked.connect(self._pick_color)
        cl.addLayout(_make_row("Color", self._color_btn))

        self._main_layout.addWidget(self._sec_typo)

        # ── Sección: Posición y tamaño ─────────────────────────────────────
        self._sec_pos = _CollapsibleSection("POSICIÓN Y TAMAÑO")
        cl2 = self._sec_pos.content_layout

        self._spin_x = self._make_mm_spin()
        self._spin_x.valueChanged.connect(lambda v: self._emit("x", v))
        cl2.addLayout(_make_row("X", self._spin_x))

        self._spin_y = self._make_mm_spin()
        self._spin_y.valueChanged.connect(lambda v: self._emit("y", v))
        cl2.addLayout(_make_row("Y", self._spin_y))

        self._spin_w = self._make_mm_spin()
        self._spin_w.valueChanged.connect(lambda v: self._emit("width", v))
        cl2.addLayout(_make_row("Ancho", self._spin_w))

        self._spin_h = self._make_mm_spin()
        self._spin_h.valueChanged.connect(lambda v: self._emit("height", v))
        cl2.addLayout(_make_row("Alto", self._spin_h))

        self._main_layout.addWidget(self._sec_pos)

        # ── Sección: Campo de dato ─────────────────────────────────────────
        self._sec_field = _CollapsibleSection("CAMPO DE DATO")
        cl3 = self._sec_field.content_layout

        self._field_combo = QComboBox()
        self._field_combo.addItems(_FIELDS)
        self._field_combo.currentTextChanged.connect(
            lambda t: self._emit("campo_dato", "" if t == "Ninguno" else t)
        )
        cl3.addLayout(_make_row("Campo", self._field_combo))

        self._main_layout.addWidget(self._sec_field)

        # Espaciador final
        self._main_layout.addStretch()

        # Estado inicial: sin selección
        self._show_empty(True)

    # ── Helpers de UI ──────────────────────────────────────────────────────
    @staticmethod
    def _make_mm_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0, 300)
        spin.setDecimals(1)
        spin.setSuffix(" mm")
        spin.setSingleStep(0.5)
        return spin

    @staticmethod
    def _align_btn_style(active: bool) -> str:
        if active:
            return (
                "QPushButton { background: #3B82F6; color: white; border: none; "
                "border-radius: 4px; font-size: 11px; font-weight: 700; }"
            )
        return (
            "QPushButton { background: #F5F7FA; color: #64748B; border: 1px solid #E2E8F0; "
            "border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background: #E2E8F0; }"
        )

    def _update_color_btn(self) -> None:
        self._color_btn.setStyleSheet(
            f"QPushButton {{ background-color: {self._current_color}; "
            f"border: 2px solid #E2E8F0; border-radius: 4px; }}"
            f"QPushButton:hover {{ border-color: #3B82F6; }}"
        )

    def _show_empty(self, empty: bool) -> None:
        self._empty_label.setVisible(empty)
        self._sec_typo.setVisible(not empty)
        self._sec_pos.setVisible(not empty)
        self._sec_field.setVisible(not empty)

    # ── Establecer elemento ────────────────────────────────────────────────
    def set_item(self, item: BaseCanvasItem | None) -> None:
        """Actualiza el panel con las propiedades de *item*."""
        self._current_item = item

        if item is None:
            self._show_empty(True)
            return

        self._updating = True
        self._show_empty(False)

        # Tipografía solo para texto
        is_text = isinstance(item, TextCanvasItem)
        self._sec_typo.set_visible_section(is_text)

        if is_text:
            text_item: TextCanvasItem = item  # type: ignore[assignment]
            self._font_combo.setCurrentFont(QFont(text_item.font_family))
            self._size_spin.setValue(text_item.font_size)

            weight_map_rev = {"normal": "Regular", "bold": "Negrita", "light": "Ligera"}
            idx = self._weight_combo.findText(
                weight_map_rev.get(text_item.font_weight, "Regular")
            )
            self._weight_combo.setCurrentIndex(max(idx, 0))

            self._set_active_align(text_item.alignment)

            self._current_color = text_item.font_color
            self._update_color_btn()

        # Posición y tamaño
        gitem = item  # type: ignore[assignment]
        self._spin_x.setValue(gitem.x() * _PX_TO_MM)
        self._spin_y.setValue(gitem.y() * _PX_TO_MM)
        br = gitem.boundingRect()
        self._spin_w.setValue(br.width() * _PX_TO_MM)
        self._spin_h.setValue(br.height() * _PX_TO_MM)

        # Campo de dato
        cd = item.campo_dato or "Ninguno"
        idx = self._field_combo.findText(cd)
        self._field_combo.setCurrentIndex(max(idx, 0))

        self._updating = False

    # ── Emisión de cambios ─────────────────────────────────────────────────
    def _emit(self, prop_name: str, value: Any) -> None:
        if self._updating or self._current_item is None:
            return
        self.property_changed.emit(self._current_item, prop_name, value)

    # ── Alineación ─────────────────────────────────────────────────────────
    def _on_align(self, value: str) -> None:
        self._set_active_align(value)
        self._emit("alignment", value)

    def _set_active_align(self, value: str) -> None:
        for v, btn in self._align_buttons.items():
            active = v == value
            btn.setChecked(active)
            btn.setStyleSheet(self._align_btn_style(active))

    # ── Selector de color ──────────────────────────────────────────────────
    def _pick_color(self) -> None:
        color = QColorDialog.getColor(
            QColor(self._current_color), self, "Seleccionar color"
        )
        if color.isValid():
            self._current_color = color.name()
            self._update_color_btn()
            self._emit("font_color", self._current_color)
