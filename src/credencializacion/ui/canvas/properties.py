"""
Panel de propiedades del elemento seleccionado.

Muestra secciones colapsables con controles de tipografía, posición /
tamaño y campo de dato vinculado.  Se actualiza en tiempo real.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
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
# Color Swatch — botón de color compatible con macOS
# ═══════════════════════════════════════════════════════════════════════════
class ColorSwatch(QFrame):
    """Cuadro de color que dibuja directamente con QPainter.

    Evita el bug de macOS donde QPushButton con background-color
    en stylesheet se renderiza completamente negro.
    """

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor("#171A2B")
        self.setFixedSize(36, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.NoFrame)

    def set_color(self, hex_color: str) -> None:
        self._color = QColor(hex_color)
        self.update()

    def color_hex(self) -> str:
        return self._color.name()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = self.rect().adjusted(2, 2, -2, -2)

        # Fondo de color
        p.setBrush(QBrush(self._color))
        p.setPen(QPen(QColor("#CBD5E1"), 1.5))
        p.drawRoundedRect(r, 4, 4)
        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setStyleSheet("border: 1.5px solid #3B82F6; border-radius: 4px;")
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setStyleSheet("")
        super().leaveEvent(event)


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

    property_changed = Signal(str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_item: BaseCanvasItem | None = None
        self._current_data: dict | None = None   # datos dict para GraphicElement
        self._updating = False  # Evita bucles de retroalimentación
        self._available_attributes: list[str] = []

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

        # ── Fila: Negrita + Cursiva ────────────────────────────────────────
        style_row = QHBoxLayout()
        style_row.setSpacing(4)

        self._btn_bold = QPushButton("B")
        self._btn_bold.setFixedSize(36, 30)
        self._btn_bold.setCheckable(True)
        self._btn_bold.setStyleSheet(self._style_btn_style(False, bold=True))
        self._btn_bold.toggled.connect(self._on_bold_toggled)
        style_row.addWidget(self._btn_bold)

        self._btn_italic = QPushButton("I")
        self._btn_italic.setFixedSize(36, 30)
        self._btn_italic.setCheckable(True)
        self._btn_italic.setStyleSheet(self._style_btn_style(False, italic=True))
        self._btn_italic.toggled.connect(self._on_italic_toggled)
        style_row.addWidget(self._btn_italic)

        style_row.addStretch()

        lbl_style = QLabel("Estilo")
        lbl_style.setFixedWidth(60)
        lbl_style.setStyleSheet("font-size: 12px; color: #64748B;")
        row_wrap_style = QHBoxLayout()
        row_wrap_style.setSpacing(8)
        row_wrap_style.addWidget(lbl_style)
        row_wrap_style.addLayout(style_row)
        cl.addLayout(row_wrap_style)

        # Alineación — 4 botones toggle
        align_row = QHBoxLayout()
        align_row.setSpacing(2)
        self._align_buttons: dict[str, QPushButton] = {}
        for symbol, value in [("◀☰", "left"), ("☰", "center"), ("☰▶", "right"), ("☰☰", "justify")]:
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

        # Color — usando ColorSwatch (compatible macOS)
        self._color_swatch = ColorSwatch()
        self._color_swatch.clicked.connect(self._pick_color)
        cl.addLayout(_make_row("Color", self._color_swatch))

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

    @staticmethod
    def _style_btn_style(active: bool, bold: bool = False, italic: bool = False) -> str:
        font_style = "font-weight: 900;" if bold else ""
        font_style += "font-style: italic;" if italic else ""
        if active:
            return (
                f"QPushButton {{ background: #3B82F6; color: white; border: none; "
                f"border-radius: 4px; font-size: 13px; {font_style} }}"
            )
        return (
            f"QPushButton {{ background: #F5F7FA; color: #64748B; border: 1px solid #E2E8F0; "
            f"border-radius: 4px; font-size: 13px; {font_style} }}"
            "QPushButton:hover { background: #E2E8F0; }"
        )

    def _show_empty(self, empty: bool) -> None:
        self._empty_label.setVisible(empty)
        self._sec_typo.setVisible(not empty)
        self._sec_pos.setVisible(not empty)
        self._sec_field.setVisible(not empty)

    # ── Establecer atributos disponibles ───────────────────────────────────
    def set_available_attributes(self, attributes: list[str]) -> None:
        """Actualiza la lista de atributos en el combo de campo de dato."""
        self._available_attributes = attributes
        self._field_combo.blockSignals(True)
        current = self._field_combo.currentText()
        self._field_combo.clear()
        self._field_combo.addItem("Ninguno")
        self._field_combo.addItems(attributes)
        idx = self._field_combo.findText(current)
        self._field_combo.setCurrentIndex(max(idx, 0))
        self._field_combo.blockSignals(False)

    # ── Actualizar desde dict (GraphicElement) ─────────────────────────────
    def update_properties(self, data: dict | None) -> None:
        """Actualiza el panel desde un dict de GraphicElement.

        Args:
            data: Dict con keys type, x, y, width, height, campo_dato, properties.
                  None para mostrar estado vacío.
        """
        self._current_data = data
        self._current_item = None

        if data is None:
            self._show_empty(True)
            return

        self._updating = True
        self._show_empty(False)

        elem_type = data.get("type", "")
        props = data.get("properties", {})

        # Mostrar tipografía solo para texto/composite
        is_text = elem_type in ("text", "composite")
        self._sec_typo.set_visible_section(is_text)

        if is_text:
            # Fuente
            family = props.get("font_family", "Inter")
            self._font_combo.blockSignals(True)
            self._font_combo.setCurrentFont(QFont(family))
            self._font_combo.blockSignals(False)

            # Tamaño
            self._size_spin.blockSignals(True)
            self._size_spin.setValue(int(props.get("font_size", 12)))
            self._size_spin.blockSignals(False)

            # Negrita
            is_bold = props.get("font_weight", "normal") == "bold"
            self._btn_bold.blockSignals(True)
            self._btn_bold.setChecked(is_bold)
            self._btn_bold.setStyleSheet(self._style_btn_style(is_bold, bold=True))
            self._btn_bold.blockSignals(False)

            # Cursiva
            is_italic = bool(props.get("font_italic", False))
            self._btn_italic.blockSignals(True)
            self._btn_italic.setChecked(is_italic)
            self._btn_italic.setStyleSheet(self._style_btn_style(is_italic, italic=True))
            self._btn_italic.blockSignals(False)

            # Alineación
            self._set_active_align(props.get("alignment", "left"))

            # Color
            color_hex = props.get("color", "#171A2B")
            self._color_swatch.set_color(color_hex)

        # Posición y tamaño
        self._spin_x.blockSignals(True)
        self._spin_y.blockSignals(True)
        self._spin_w.blockSignals(True)
        self._spin_h.blockSignals(True)
        self._spin_x.setValue(float(data.get("x", 0)))
        self._spin_y.setValue(float(data.get("y", 0)))
        self._spin_w.setValue(float(data.get("width", 0)))
        self._spin_h.setValue(float(data.get("height", 0)))
        self._spin_x.blockSignals(False)
        self._spin_y.blockSignals(False)
        self._spin_w.blockSignals(False)
        self._spin_h.blockSignals(False)

        # Campo de dato
        cd = data.get("campo_dato") or "Ninguno"
        self._field_combo.blockSignals(True)
        idx = self._field_combo.findText(cd)
        if idx < 0:
            # Agregar dinámicamente si no está
            self._field_combo.addItem(cd)
            idx = self._field_combo.count() - 1
        self._field_combo.setCurrentIndex(idx)
        self._field_combo.blockSignals(False)

        self._updating = False

    # ── Establecer elemento (BaseCanvasItem legacy) ────────────────────────
    def set_item(self, item: BaseCanvasItem | None) -> None:
        """Actualiza el panel con las propiedades de *item* (API legacy)."""
        self._current_item = item
        self._current_data = None

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

            is_bold = text_item.font_weight == "bold"
            self._btn_bold.blockSignals(True)
            self._btn_bold.setChecked(is_bold)
            self._btn_bold.setStyleSheet(self._style_btn_style(is_bold, bold=True))
            self._btn_bold.blockSignals(False)

            self._btn_italic.blockSignals(True)
            self._btn_italic.setChecked(False)
            self._btn_italic.setStyleSheet(self._style_btn_style(False, italic=True))
            self._btn_italic.blockSignals(False)

            self._set_active_align(text_item.alignment)
            self._color_swatch.set_color(text_item.font_color)

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
        if self._updating:
            return
        self.property_changed.emit(prop_name, value)

    # ── Alineación ─────────────────────────────────────────────────────────
    def _on_align(self, value: str) -> None:
        self._set_active_align(value)
        self._emit("alignment", value)

    def _set_active_align(self, value: str) -> None:
        for v, btn in self._align_buttons.items():
            active = v == value
            btn.setChecked(active)
            btn.setStyleSheet(self._align_btn_style(active))

    # ── Negrita / Cursiva ──────────────────────────────────────────────────
    def _on_bold_toggled(self, checked: bool) -> None:
        self._btn_bold.setStyleSheet(self._style_btn_style(checked, bold=True))
        self._emit("font_weight", "bold" if checked else "normal")

    def _on_italic_toggled(self, checked: bool) -> None:
        self._btn_italic.setStyleSheet(self._style_btn_style(checked, italic=True))
        self._emit("font_italic", checked)

    # ── Selector de color ──────────────────────────────────────────────────
    def _pick_color(self) -> None:
        color = QColorDialog.getColor(
            self._color_swatch._color, self, "Seleccionar color"
        )
        if color.isValid():
            self._color_swatch.set_color(color.name())
            self._emit("color", color.name())
