"""
Editor de plantillas de credenciales.

Vista compuesta que integra el canvas de diseño, toolbar de herramientas,
panel de propiedades y panel de capas. Permite editar frente y vuelta
de la plantilla con vista previa en tiempo real.
"""
from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QSize, QMimeData, QPoint
from PySide6.QtGui import QFont, QCursor, QIcon, QDrag, QMouseEvent, QFontDatabase
import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QFrame,
    QSplitter,
    QSpinBox,
    QButtonGroup,
    QSizePolicy,
    QScrollArea,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QFormLayout,
    QLineEdit,
    QDoubleSpinBox,
    QColorDialog,
    QStackedWidget,
    QCheckBox,
)

from credencializacion.ui.widgets.layers_panel import LayersPanel
from credencializacion.ui.widgets.canvas import CredentialView, CredentialScene, MM_TO_PX
if TYPE_CHECKING:
    from credencializacion.db.models import Plantilla, Registro

# ── Paleta de colores ──────────────────────────────────────────────────
PRIMARY = "#FB5252"
SECONDARY = "#FFD057"
TEXT_DARK = "#171A2B"
TEXT_LIGHT = "#64748B"
CARD_BG = "#FFFFFF"
BORDER = "#E2E8F0"
MAIN_BG = "#F5F7FA"
SIDEBAR_BG = "#0F1629"


# ── Canvas Toolbar (panel izquierdo) ───────────────────────────────────

class DraggableButton(QPushButton):
    """Botón que inicia una operación de arrastre (Drag & Drop)."""
    
    def __init__(self, text: str, drag_data: str, parent=None):
        super().__init__(text, parent)
        self.drag_data = drag_data
        self.drag_start_pos = QPoint()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.pos() - self.drag_start_pos).manhattanLength() < 5:
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(self.drag_data)
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.CopyAction)

class CanvasToolbar(QWidget):
    """Panel lateral izquierdo con atributos arrastrables.

    Muestra los atributos disponibles para agregar al canvas.
    Cada item se puede arrastrar al CredentialView.
    """

    item_dragged = Signal(str)  # Tipo de elemento arrastrado

    # Atributos estandarizados del sistema
    # Los campos (4ta columna) coinciden exactamente con los keys del registro
    DEFAULT_ATTRIBUTES = [
        ("composite",  "📝",  "Texto Compuesto",    "composite"),
        ("photo_path", "🖼",  "Imagen",              "photo_url"),
        ("text",       "👤",  "Nombre",              "nombre"),
        ("text",       "👤",  "Apellidos",           "apellido"),
        ("text",       "🏢",  "Escuela",             "escuela"),
        ("text",       "🏫",  "Nivel Escolar",       "nivel_escolar"),
        ("text",       "🔢",  "Matrícula",           "matricula"),
        ("text",       "🔢",  "CURP",                "curp"),
        ("text",       "📚",  "Grado",               "grado"),
        ("text",       "📚",  "Grupo",               "grupo"),
        ("text",       "⏰",  "Turno",               "turno"),
        ("text",       "📅",  "Fecha Nacimiento",    "fecha_nacimiento"),
        ("text",       "🩸",  "Tipo de Sangre",      "tipo_sangre"),
        ("text",       "📍",  "Domicilio",           "domicilio"),
        ("text",       "📞",  "Teléfono",            "telefono"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(210)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Construye el panel de herramientas."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.setStyleSheet(f"""
            CanvasToolbar {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)

        # Cabecera
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        h_lay = QVBoxLayout(header)
        h_lay.setContentsMargins(14, 14, 14, 6)
        h_lay.setSpacing(2)

        lbl_title = QLabel("Atributos")
        lbl_title.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {TEXT_DARK};")
        h_lay.addWidget(lbl_title)

        self._lbl_client = QLabel("Arrastra al lienzo")
        self._lbl_client.setStyleSheet(f"font-size: 11px; color: {TEXT_LIGHT};")
        self._lbl_client.setWordWrap(True)
        h_lay.addWidget(self._lbl_client)

        # Banner de alerta sync (oculto por defecto)
        self._banner_sync = QLabel("⚠ Sincroniza para ver\natributos del cliente")
        self._banner_sync.setStyleSheet("""
            background-color: #FFFBEB;
            border: 1px solid #F59E0B;
            border-radius: 6px;
            padding: 6px 8px;
            font-size: 11px;
            color: #92400E;
        """)
        self._banner_sync.setWordWrap(True)
        self._banner_sync.setVisible(False)
        h_lay.addWidget(self._banner_sync)

        outer.addWidget(header)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {BORDER}; max-height: 1px;")
        outer.addWidget(sep)

        # ScrollArea con los atributos
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; }
            QScrollBar:vertical {
                width: 6px; background: transparent; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #CBD5E1; border-radius: 3px; min-height: 20px;
            }
        """)
        outer.addWidget(scroll)

        btn_container = QWidget()
        btn_container.setStyleSheet("background: transparent;")
        self._attr_layout = QVBoxLayout(btn_container)
        self._attr_layout.setContentsMargins(10, 10, 10, 10)
        self._attr_layout.setSpacing(6)
        scroll.setWidget(btn_container)

        # Cargar atributos por defecto
        self._load_default_attributes()
        self._attr_layout.addStretch()

    def _load_default_attributes(self) -> None:
        """Carga los atributos por defecto en el panel."""
        for elem_type, icon, label, campo in self.DEFAULT_ATTRIBUTES:
            drag_data = f"{elem_type}:{campo}"
            btn = DraggableButton(f"{icon}  {label}", drag_data)
            btn.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))

            # estilo especial para Texto Compuesto
            if elem_type == "composite":
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: #EFF6FF;
                        border: 1px solid #93C5FD;
                        border-radius: 8px;
                        padding: 8px 10px;
                        text-align: left;
                        font-size: 12px;
                        font-weight: 600;
                        color: #1D4ED8;
                    }}
                    QPushButton:hover {{
                        background-color: #DBEAFE;
                        border-color: #3B82F6;
                    }}
                """)
            elif elem_type == "photo_path":
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: #F0FDF4;
                        border: 1px solid #86EFAC;
                        border-radius: 8px;
                        padding: 8px 10px;
                        text-align: left;
                        font-size: 12px;
                        color: #166534;
                    }}
                    QPushButton:hover {{
                        background-color: #DCFCE7;
                        border-color: #4ADE80;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {MAIN_BG};
                        border: 1px solid {BORDER};
                        border-radius: 6px;
                        padding: 6px 10px;
                        text-align: left;
                        font-size: 12px;
                        color: {TEXT_DARK};
                    }}
                    QPushButton:hover {{
                        background-color: #FEE2E2;
                        border-color: {PRIMARY};
                        color: {PRIMARY};
                    }}
                """)
            btn.clicked.connect(
                lambda checked, d=drag_data: self.item_dragged.emit(d)
            )
            self._attr_layout.addWidget(btn)

    def set_client_label(self, nombre: str, last_sync: str, *, sync_needed: bool = False) -> None:
        """Actualiza la etiqueta del cliente activo y el banner de sync."""
        if sync_needed:
            self._lbl_client.setText(f"🏫 {nombre}")
            self._banner_sync.setVisible(True)
        else:
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(last_sync)
                sync_str = dt.strftime("%d/%m %H:%M")
            except Exception:
                sync_str = last_sync[:16] if last_sync else "?"
            self._lbl_client.setText(f"🏫 {nombre}")
            self._banner_sync.setVisible(False)
            self._lbl_client.setToolTip(f"Última sync: {sync_str}")

    def load_attributes(self, attributes: list[str]) -> None:
        """Reemplaza los atributos dinámicamente (llamado desde TemplateEditor al cargar plantilla)."""
        # Limpiar layout actual
        while self._attr_layout.count():
            item = self._attr_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._load_default_attributes()

        # Agregar atributos extra si los hay
        for attr in attributes:
            if not any(attr == campo for _, _, _, campo in self.DEFAULT_ATTRIBUTES):
                btn = DraggableButton(f"📌  {attr}", f"text:{attr}")
                btn.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {MAIN_BG};
                        border: 1px dashed {BORDER};
                        border-radius: 6px;
                        padding: 6px 10px;
                        text-align: left;
                        font-size: 12px;
                        color: {TEXT_LIGHT};
                    }}
                    QPushButton:hover {{
                        background-color: {MAIN_BG};
                        color: {TEXT_DARK};
                        border-style: solid;
                    }}
                """)
                btn.clicked.connect(
                    lambda checked, a=attr: self.item_dragged.emit(f"text:{a}")
                )
                self._attr_layout.addWidget(btn)
        self._attr_layout.addStretch()


# ── Properties Panel (panel derecho superior) ──────────────────────────

class PropertiesPanel(QWidget):
    """Panel de propiedades del elemento seleccionado.

    Muestra y permite editar las propiedades del elemento activo
    en el canvas: posición, tamaño, fuente, color, etc.

    Signals:
        property_changed(str, object): (nombre_propiedad, nuevo_valor)
    """

    property_changed = Signal(str, object)
    # Solicita al editor abrir el explorador para elegir un archivo de imagen.
    image_file_requested = Signal()

    # Mapeo índice del combo de alineación → valor almacenado en properties.
    _ALIGN_VALUES = ["left", "center", "right"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._current_element = None
        self._img_attributes: list[str] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Construye el panel de propiedades."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.setStyleSheet(f"""
            PropertiesPanel {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)

        # Título y tipo de elemento
        title_layout = QHBoxLayout()
        lbl_title = QLabel("Propiedades")
        lbl_title.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {TEXT_DARK};")
        title_layout.addWidget(lbl_title)

        self._lbl_element_type = QLabel("-")
        self._lbl_element_type.setStyleSheet(
            f"color: {PRIMARY}; font-weight: bold; font-size: 11px; "
            "margin-left: 8px;"
        )
        title_layout.addWidget(self._lbl_element_type)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # Contenedor principal de propiedades
        self._props_container = QWidget()
        self._form = QFormLayout(self._props_container)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setSpacing(8)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Posición X
        self._spin_x = QDoubleSpinBox()
        self._spin_x.setSuffix(" mm")
        self._spin_x.setRange(0, 300)
        self._spin_x.setDecimals(1)
        self._spin_x.setStyleSheet(self._input_style())
        self._spin_x.valueChanged.connect(lambda v: self.property_changed.emit("x", v))
        self._form.addRow("X:", self._spin_x)

        # Posición Y
        self._spin_y = QDoubleSpinBox()
        self._spin_y.setSuffix(" mm")
        self._spin_y.setRange(0, 300)
        self._spin_y.setDecimals(1)
        self._spin_y.setStyleSheet(self._input_style())
        self._spin_y.valueChanged.connect(lambda v: self.property_changed.emit("y", v))
        self._form.addRow("Y:", self._spin_y)

        # Ancho
        self._spin_w = QDoubleSpinBox()
        self._spin_w.setSuffix(" mm")
        self._spin_w.setRange(1, 300)
        self._spin_w.setDecimals(1)
        self._spin_w.setStyleSheet(self._input_style())
        self._spin_w.valueChanged.connect(
            lambda v: self.property_changed.emit("width", v)
        )
        self._form.addRow("Ancho:", self._spin_w)

        # Alto
        self._spin_h = QDoubleSpinBox()
        self._spin_h.setSuffix(" mm")
        self._spin_h.setRange(1, 300)
        self._spin_h.setDecimals(1)
        self._spin_h.setStyleSheet(self._input_style())
        self._spin_h.valueChanged.connect(
            lambda v: self.property_changed.emit("height", v)
        )
        self._form.addRow("Alto:", self._spin_h)

        # Fuente
        self._combo_font = QComboBox()
        db = QFontDatabase()
        self._combo_font.addItems(db.families())
        self._combo_font.setStyleSheet(self._input_style())
        self._combo_font.currentTextChanged.connect(
            lambda v: self.property_changed.emit("font_family", v)
        )
        self._form.addRow("Fuente:", self._combo_font)

        # Tamaño de fuente
        self._spin_font_size = QSpinBox()
        self._spin_font_size.setSuffix(" pt")
        self._spin_font_size.setRange(6, 72)
        self._spin_font_size.setValue(12)
        self._spin_font_size.setStyleSheet(self._input_style())
        self._spin_font_size.valueChanged.connect(
            lambda v: self.property_changed.emit("font_size", v)
        )
        self._form.addRow("Tamaño:", self._spin_font_size)

        # Negrita
        self._chk_bold = QCheckBox("Negrita")
        self._chk_bold.setStyleSheet(f"color: {TEXT_DARK}; font-size: 12px;")
        self._chk_bold.toggled.connect(
            lambda checked: self.property_changed.emit(
                "font_weight", "bold" if checked else "normal"
            )
        )
        self._form.addRow("Estilo:", self._chk_bold)

        # Color
        self._btn_color = QPushButton("  #171A2B")
        self._btn_color.setStyleSheet(f"""
            QPushButton {{
                background-color: {TEXT_DARK};
                color: #FFFFFF;
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
            }}
        """)
        self._btn_color.clicked.connect(self._pick_color)
        self._form.addRow("Color:", self._btn_color)

        # --- Propiedades dinámicas comunes (Render as, etc) ---
        self._w_dynamic_group = QWidget()
        self._f_dyn = QFormLayout(self._w_dynamic_group)
        self._f_dyn.setContentsMargins(0, 0, 0, 0)
        self._f_dyn.setSpacing(8)
        self._f_dyn.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._f_dyn.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._f_dyn.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._combo_render_as = QComboBox()
        self._combo_render_as.addItems(["Texto", "Código QR", "Código de Barras"])
        self._combo_render_as.setStyleSheet(self._input_style())
        self._stretch_combo(self._combo_render_as)
        self._combo_render_as.currentTextChanged.connect(self._on_render_as_changed)
        self._f_dyn.addRow("Formato:", self._combo_render_as)

        # Alineación del texto dentro de su caja (left / center / right).
        # El orden del combo coincide con _ALIGN_VALUES para mapear índice→valor.
        self._combo_align = QComboBox()
        self._combo_align.addItems(["Izquierda", "Centro", "Derecha"])
        self._combo_align.setStyleSheet(self._input_style())
        self._stretch_combo(self._combo_align)
        self._combo_align.currentIndexChanged.connect(
            lambda i: self.property_changed.emit(
                "alignment", self._ALIGN_VALUES[i] if 0 <= i < len(self._ALIGN_VALUES) else "left"
            )
        )
        self._row_align = self._f_dyn.addRow("Alineación:", self._combo_align)

        self._combo_barcode_format = QComboBox()
        self._combo_barcode_format.addItems(["Code128", "EAN13"])
        self._combo_barcode_format.setStyleSheet(self._input_style())
        self._stretch_combo(self._combo_barcode_format)
        self._combo_barcode_format.currentTextChanged.connect(
            lambda v: self.property_changed.emit("barcode_format", v)
        )
        self._row_barcode = self._f_dyn.addRow("Codificación:", self._combo_barcode_format)

        self._edit_test_text = QLineEdit()
        self._edit_test_text.setPlaceholderText("Dato de prueba...")
        self._edit_test_text.setStyleSheet(self._input_style())
        self._edit_test_text.textChanged.connect(
            lambda v: self.property_changed.emit("test_text", v)
        )
        self._row_test = self._f_dyn.addRow("Dato prueba:", self._edit_test_text)
        
        self._edit_composite = QLineEdit()
        self._edit_composite.setPlaceholderText("Ej: {grado}º {grupo}")
        self._edit_composite.setStyleSheet(self._input_style())
        self._edit_composite.textChanged.connect(
            lambda v: self.property_changed.emit("composite_template", v)
        )
        self._row_comp = self._f_dyn.addRow("Plantilla:", self._edit_composite)

        # Regla de transformación de texto (abreviar, primer nombre, etc.)
        from credencializacion.services.text_rules import TEXT_RULES
        self._combo_text_rule = QComboBox()
        self._combo_text_rule.setStyleSheet(self._input_style())
        self._stretch_combo(self._combo_text_rule)
        for _rule in TEXT_RULES:
            self._combo_text_rule.addItem(_rule["label"], _rule["id"])
        self._combo_text_rule.currentIndexChanged.connect(
            lambda _i: self.property_changed.emit(
                "text_rule", self._combo_text_rule.currentData() or ""
            )
        )
        self._row_text_rule = self._f_dyn.addRow("Regla de texto:", self._combo_text_rule)

        # ── Origen de imagen (solo elementos imagen) ──────────────────────
        self._combo_img_source = QComboBox()
        self._combo_img_source.addItems(["Atributo", "Archivo"])
        self._combo_img_source.setStyleSheet(self._input_style())
        self._stretch_combo(self._combo_img_source)
        self._combo_img_source.currentTextChanged.connect(self._on_img_source_changed)
        self._row_img_source = self._f_dyn.addRow("Origen:", self._combo_img_source)

        self._edit_img_label = QLineEdit()
        self._edit_img_label.setPlaceholderText("(opcional; por defecto el origen)")
        self._edit_img_label.setStyleSheet(self._input_style())
        self._edit_img_label.textChanged.connect(
            lambda v: self.property_changed.emit("label", v)
        )
        self._row_img_label = self._f_dyn.addRow("Etiqueta:", self._edit_img_label)

        self._combo_img_attr = QComboBox()
        self._combo_img_attr.setStyleSheet(self._input_style())
        self._stretch_combo(self._combo_img_attr)
        self._combo_img_attr.currentIndexChanged.connect(
            lambda _i: self.property_changed.emit(
                "campo_dato", self._combo_img_attr.currentData() or ""
            )
        )
        self._row_img_attr = self._f_dyn.addRow("Atributo imagen:", self._combo_img_attr)

        self._btn_img_file = QPushButton("Elegir archivo…")
        self._btn_img_file.setStyleSheet(self._input_style())
        self._btn_img_file.clicked.connect(self.image_file_requested.emit)
        self._row_img_file = self._f_dyn.addRow("Archivo:", self._btn_img_file)

        self._form.addRow(self._w_dynamic_group)

        layout.addWidget(self._props_container)

        # Placeholder vacío
        self._lbl_empty = QLabel("Selecciona un elemento\nen el canvas")
        self._lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_empty.setFont(QFont("Inter", 11))
        self._lbl_empty.setStyleSheet(f"color: {TEXT_LIGHT};")
        layout.addWidget(self._lbl_empty)

        layout.addStretch()

    @staticmethod
    def _stretch_combo(combo: QComboBox) -> None:
        """Hace que un QComboBox llene el ancho del contenedor de propiedades.

        Por defecto el combo ajusta su ancho al contenido; con esto se expande
        al ancho disponible del formulario sin que los textos largos lo
        desborden.
        """
        combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(0)

    def _input_style(self) -> str:
        """Retorna stylesheet compartido para inputs del panel."""
        return f"""
            QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit {{
                background-color: {MAIN_BG};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 12px;
                color: {TEXT_DARK};
            }}
            QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QLineEdit:focus {{
                border-color: {PRIMARY};
            }}
            QSpinBox::up-button, QDoubleSpinBox::up-button {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 20px;
                border: none;
                border-left: 1px solid {BORDER};
                border-top-right-radius: 6px;
            }}
            QSpinBox::down-button, QDoubleSpinBox::down-button {{
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 20px;
                border: none;
                border-left: 1px solid {BORDER};
                border-bottom-right-radius: 6px;
            }}
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 4px solid {TEXT_LIGHT};
                width: 0;
                height: 0;
            }}
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid {TEXT_LIGHT};
                width: 0;
                height: 0;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid {TEXT_LIGHT};
                width: 0;
                height: 0;
                margin-right: 6px;
            }}
        """

    def update_properties(self, element: dict | None) -> None:
        """Actualiza el panel con las propiedades del elemento seleccionado.

        Args:
            element: Dict del elemento o None si se deseleccionó.
        """
        if element is None:
            self._lbl_empty.setVisible(True)
            self._props_container.setVisible(False)
            self._lbl_element_type.setText("-")
            self._current_element = None
            return

        self._lbl_empty.setVisible(False)
        self._props_container.setVisible(True)
        self._current_element = element
        props = element.get("properties", {})
        elem_type = element.get("type", "unknown")
        
        self._lbl_element_type.setText(elem_type.upper())

        # Ocultar paneles específicos primero
        self._w_dynamic_group.setVisible(False)
        self._f_dyn.setRowVisible(self._combo_barcode_format, False)
        self._f_dyn.setRowVisible(self._edit_test_text, False)
        self._f_dyn.setRowVisible(self._edit_composite, False)
        self._f_dyn.setRowVisible(self._combo_align, False)
        self._f_dyn.setRowVisible(self._combo_img_source, False)
        self._f_dyn.setRowVisible(self._combo_img_attr, False)
        self._f_dyn.setRowVisible(self._btn_img_file, False)
        self._f_dyn.setRowVisible(self._edit_img_label, False)
        self._f_dyn.setRowVisible(self._combo_text_rule, False)
        # Por defecto, mostrar las filas de fuente (se ocultan solo en imagen).
        for _w in (self._combo_font, self._spin_font_size, self._chk_bold, self._btn_color):
            self._form.setRowVisible(_w, True)

        # Bloquear señales
        for widget in (self._spin_x, self._spin_y, self._spin_w, self._spin_h, 
                       self._combo_font, self._spin_font_size, self._chk_bold,
                       self._combo_render_as,
                       self._combo_barcode_format, self._edit_test_text, self._edit_composite,
                       self._combo_align):
            widget.blockSignals(True)

        self._spin_x.setValue(element.get("x", 0))
        self._spin_y.setValue(element.get("y", 0))
        self._spin_w.setValue(element.get("width", 0))
        self._spin_h.setValue(element.get("height", 0))

        if elem_type in ("text", "composite"):
            self._w_dynamic_group.setVisible(True)
            self._f_dyn.setRowVisible(self._combo_render_as, True)
            self._combo_font.setCurrentText(props.get("font_family", "Inter"))
            self._spin_font_size.setValue(props.get("font_size", 12))
            self._chk_bold.setChecked(props.get("font_weight", "normal") == "bold")
            
            render_as = props.get("render_as", "Texto")
            self._combo_render_as.setCurrentText(render_as)
            
            if render_as == "Código de Barras":
                self._f_dyn.setRowVisible(self._combo_barcode_format, True)
                self._combo_barcode_format.setCurrentText(props.get("barcode_format", "Code128"))
            
            if render_as == "Texto":
                self._f_dyn.setRowVisible(self._edit_test_text, True)
                self._edit_test_text.setText(props.get("test_text", ""))
                # Alineación solo aplica al texto renderizado como texto.
                self._f_dyn.setRowVisible(self._combo_align, True)
                alignment = props.get("alignment", "left")
                try:
                    self._combo_align.setCurrentIndex(self._ALIGN_VALUES.index(alignment))
                except ValueError:
                    self._combo_align.setCurrentIndex(0)

                # Regla de transformación de texto.
                self._f_dyn.setRowVisible(self._combo_text_rule, True)
                self._combo_text_rule.blockSignals(True)
                rule_id = props.get("text_rule", "") or ""
                ridx = self._combo_text_rule.findData(rule_id)
                self._combo_text_rule.setCurrentIndex(ridx if ridx >= 0 else 0)
                self._combo_text_rule.blockSignals(False)
                
            if elem_type == "composite":
                self._f_dyn.setRowVisible(self._edit_composite, True)
                self._edit_composite.setText(props.get("composite_template", ""))

        elif elem_type in ("image", "photo_path"):
            self._w_dynamic_group.setVisible(True)
            # La imagen no usa formato de texto ni fuente/tamaño/color.
            self._f_dyn.setRowVisible(self._combo_render_as, False)
            for _w in (self._combo_font, self._spin_font_size, self._chk_bold,
                       self._btn_color):
                self._form.setRowVisible(_w, False)

            campo = element.get("campo_dato") or ""
            src = props.get("src", "")
            source = props.get("img_source") or ("file" if (src and not campo) else "attribute")

            self._combo_img_source.blockSignals(True)
            self._combo_img_source.setCurrentText(
                "Archivo" if source == "file" else "Atributo"
            )
            self._combo_img_source.blockSignals(False)

            self._combo_img_attr.blockSignals(True)
            idx = self._combo_img_attr.findData(campo) if campo else 0
            self._combo_img_attr.setCurrentIndex(idx if idx >= 0 else 0)
            self._combo_img_attr.blockSignals(False)

            from pathlib import Path as _PathImg
            self._btn_img_file.setText(
                _PathImg(src).name if src else "Elegir archivo…"
            )

            self._f_dyn.setRowVisible(self._combo_img_source, True)
            is_file = source == "file"
            self._f_dyn.setRowVisible(self._combo_img_attr, not is_file)
            self._f_dyn.setRowVisible(self._btn_img_file, is_file)

            # Etiqueta del elemento imagen (opcional).
            self._edit_img_label.blockSignals(True)
            self._edit_img_label.setText(props.get("label", "") or "")
            self._edit_img_label.blockSignals(False)
            self._f_dyn.setRowVisible(self._edit_img_label, True)

        for widget in (self._spin_x, self._spin_y, self._spin_w, self._spin_h, 
                       self._combo_font, self._spin_font_size, self._chk_bold,
                       self._combo_render_as,
                       self._combo_barcode_format, self._edit_test_text, self._edit_composite,
                       self._combo_align):
            widget.blockSignals(False)

    def _on_render_as_changed(self, value: str) -> None:
        self.property_changed.emit("render_as", value)
        if self._current_element:
            self.update_properties(self._current_element)

    def set_available_attributes(self, attributes: list[str]) -> None:
        pass

    def set_image_attributes(self, attributes: list[str]) -> None:
        """Puebla el combobox de atributos de imagen (origen 'Atributo')."""
        self._img_attributes = list(attributes or [])
        self._combo_img_attr.blockSignals(True)
        self._combo_img_attr.clear()
        self._combo_img_attr.addItem("Selecciona un atributo…", "")
        for attr in self._img_attributes:
            self._combo_img_attr.addItem(attr, attr)
        self._combo_img_attr.blockSignals(False)

    def _on_img_source_changed(self, text: str) -> None:
        """Cambia el origen del elemento imagen (Atributo / Archivo)."""
        is_file = text == "Archivo"
        self.property_changed.emit("img_source", "file" if is_file else "attribute")
        # Mostrar el control correspondiente.
        self._f_dyn.setRowVisible(self._combo_img_attr, not is_file)
        self._f_dyn.setRowVisible(self._btn_img_file, is_file)

    def _pick_color(self) -> None:
        """Abre el selector de color nativo."""
        color = QColorDialog.getColor(
            Qt.GlobalColor.black, self, "Seleccionar Color"
        )
        if color.isValid():
            hex_color = color.name()
            self._btn_color.setText(f"  {hex_color}")
            self._btn_color.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hex_color};
                    color: {'#FFFFFF' if color.lightness() < 128 else '#000000'};
                    border: 1px solid {BORDER};
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 12px;
                }}
            """)
            self.property_changed.emit("color", hex_color)


# ── Layers Panel (panel derecho inferior) ──────────────────────────────

class LayersPanel(QWidget):
    """Panel de capas del diseño.

    Muestra la lista de elementos ordenados por z_order con controles
    de visibilidad y selección.

    Signals:
        layer_selected(int): Índice del elemento seleccionado.
        layer_order_changed(int, int): (from_index, to_index).
    """

    layer_selected = Signal(int)
    layer_order_changed = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Construye el panel de capas."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.setStyleSheet(f"""
            LayersPanel {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)

        # Header
        header = QHBoxLayout()
        lbl_title = QLabel("Capas")
        lbl_title.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {TEXT_DARK};")
        header.addWidget(lbl_title)
        header.addStretch()

        # Botones de orden
        btn_up = QPushButton("▲")
        btn_up.setFixedSize(24, 24)
        btn_up.setStyleSheet(self._mini_btn_style())
        btn_up.clicked.connect(self._move_up)
        header.addWidget(btn_up)

        btn_down = QPushButton("▼")
        btn_down.setFixedSize(24, 24)
        btn_down.setStyleSheet(self._mini_btn_style())
        btn_down.clicked.connect(self._move_down)
        header.addWidget(btn_down)

        layout.addLayout(header)

        # Lista de capas
        self._list = QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget {{
                background-color: {MAIN_BG};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-radius: 4px;
                font-size: 12px;
                color: {TEXT_DARK};
            }}
            QListWidget::item:selected {{
                background-color: #FEE2E2;
                color: {TEXT_DARK};
            }}
            QListWidget::item:hover {{
                background-color: #F0F4FF;
            }}
        """)
        self._list.currentRowChanged.connect(self.layer_selected.emit)
        layout.addWidget(self._list, stretch=1)

    def _mini_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: {MAIN_BG};
                border: 1px solid {BORDER};
                border-radius: 4px;
                font-size: 10px;
                color: {TEXT_LIGHT};
            }}
            QPushButton:hover {{
                background: {BORDER};
                color: {TEXT_DARK};
            }}
        """

    def set_layers(self, elements: list[dict]) -> None:
        """Actualiza la lista de capas con los elementos del diseño.

        Args:
            elements: Lista de dicts de elementos, ordenados por z_order.
        """
        self._list.clear()
        for i, elem in enumerate(
            sorted(elements, key=lambda e: e.get("z_order", 0), reverse=True)
        ):
            elem_type = elem.get("type", "?")
            campo = elem.get("campo_dato", "")
            label = f"{elem_type.upper()}"
            if campo:
                label += f" — {campo}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, i)
            self._list.addItem(item)

    def _move_up(self) -> None:
        """Mueve la capa seleccionada hacia arriba (mayor z_order)."""
        row = self._list.currentRow()
        if row > 0:
            self.layer_order_changed.emit(row, row - 1)

    def _move_down(self) -> None:
        """Mueve la capa seleccionada hacia abajo (menor z_order)."""
        row = self._list.currentRow()
        if row < self._list.count() - 1:
            self.layer_order_changed.emit(row, row + 1)


# ── Template Editor (vista principal) ──────────────────────────────────

class TemplateEditor(QWidget):
    """Editor de plantillas de credenciales.

    Vista compuesta con:
    - Toolbar superior: toggle frente/vuelta, zoom, orientación
    - Panel izquierdo: CanvasToolbar (herramientas y atributos)
    - Centro: Canvas/CredentialView (placeholder hasta integrar QGraphicsView)
    - Panel derecho: PropertiesPanel + LayersPanel
    - Botones inferiores: Vista Previa + Guardar

    La integración con CredentialView (QGraphicsView/Scene) se realizará
    al conectar los canvas items existentes.
    """

    template_saved = Signal()
    preview_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_side: str = "frente"  # "frente" | "vuelta"
        self._plantilla: "Plantilla | None" = None
        self._local_frente: list[dict] = []
        self._local_vuelta: list[dict] = []
        self._local_orientation: str = "horizontal"
        self._zoom_level: int = 100
        self._undo_stack: list[tuple[list[dict], list[dict]]] = []
        self._redo_stack: list[tuple[list[dict], list[dict]]] = []
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Construye el layout completo del editor."""
        self.setStyleSheet(f"background-color: {MAIN_BG};")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Toolbar superior ───────────────────────────────────────
        main_layout.addWidget(self._build_top_toolbar())

        # ── Área de trabajo (3 columnas) ───────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {BORDER};
                width: 1px;
            }}
        """)

        # Panel izquierdo: herramientas
        self._canvas_toolbar = CanvasToolbar()
        splitter.addWidget(self._canvas_toolbar)

        # Centro: Canvas (placeholder)
        self._canvas_container = self._build_canvas_area()
        splitter.addWidget(self._canvas_container)

        # Panel derecho: propiedades + capas
        right_panel = self._build_right_panel()
        splitter.addWidget(right_panel)

        # Proporciones del splitter (200 : stretch : 340)
        splitter.setSizes([200, 560, 340])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        main_layout.addWidget(splitter, stretch=1)

        # ── Barra inferior (acciones) ──────────────────────────────
        main_layout.addWidget(self._build_bottom_bar())


    def _build_top_toolbar(self) -> QFrame:
        """Toolbar superior mínima del editor (los controles principales viven en MainWindow)."""
        toolbar = QFrame()
        toolbar.setFixedHeight(0)  # Oculta — la toolbar principal está en MainWindow
        return toolbar

    def _build_canvas_area(self) -> QWidget:
        """Construye el área central del canvas con QScrollArea.
        Muestra ambos lienzos (Frente y Vuelta) apilados verticalmente.
        """
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {MAIN_BG};
            }}
        """)

        container = QWidget()
        # Añadimos un grid ligero de fondo por estilo (css background)
        container.setStyleSheet(f"""
            QWidget {{
                background-color: {MAIN_BG};
                background-image: radial-gradient({BORDER} 1px, transparent 1px);
                background-size: 20px 20px;
            }}
        """)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        self._scene_frente = CredentialScene(self)
        self._scene_frente.set_physical_size(8.5, 5.4) # default horizontal
        self._scene_frente.item_updated.connect(self._on_item_updated)
        self._scene_frente.selectionChanged.connect(self._on_scene_selection_changed)
        
        self._view_frente = CredentialView(self._scene_frente)
        self._view_frente.setMinimumHeight(320)

        self._scene_vuelta = CredentialScene(self)
        self._scene_vuelta.set_physical_size(8.5, 5.4)
        self._scene_vuelta.item_updated.connect(self._on_item_updated)
        self._scene_vuelta.selectionChanged.connect(self._on_scene_selection_changed)
        
        self._view_vuelta = CredentialView(self._scene_vuelta)
        self._view_vuelta.setMinimumHeight(320)

        # Contenedores con títulos clicables (abren selector de imagen base)
        _preview_btn_style = f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {BORDER};
                border-radius: 5px;
                padding: 2px 6px;
                color: {TEXT_LIGHT};
                font-size: 14px;
            }}
            QPushButton:hover {{
                border-color: {PRIMARY};
                color: {PRIMARY};
                background-color: #EFF6FF;
            }}
        """

        def make_side_header(title: str, side: str) -> "QWidget":
            """Crea una barra de cabecera con etiqueta clicable y botón de preview."""
            from PySide6.QtWidgets import QLabel, QHBoxLayout
            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(6)

            lbl = QLabel(f"🖼 {title}  <span style='font-size:10px; color:#94A3B8;'>(clic para imagen base)</span>")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setFont(QFont("Inter", 10, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color: {TEXT_LIGHT}; padding: 4px 0px;")
            lbl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            lbl.mousePressEvent = lambda e, s=side: self._select_base_image(s)
            row_lay.addWidget(lbl, stretch=1)

            # Botón vista previa solo icono (icon font)
            btn_prev = QPushButton()
            btn_prev.setIcon(qta.icon("fa5s.eye", color="#64748B"))
            btn_prev.setIconSize(QSize(16, 16))
            btn_prev.setToolTip(f"Vista previa — {title} (2 registros)")
            btn_prev.setFixedSize(28, 24)
            btn_prev.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_prev.setStyleSheet(_preview_btn_style)
            btn_prev.clicked.connect(lambda _, s=side: self.preview_template(cara=s))
            row_lay.addWidget(btn_prev)

            # Botón de configuración de multiplantillaje (icono engranaje, Req 1.1/1.2).
            # Solo icono, sin etiqueta. Se habilita únicamente cuando la plantilla
            # está guardada y asociada a un Cliente (Req 1.5). El estado y tooltip
            # se ajustan en _update_config_buttons_state tras cargar/guardar.
            btn_config = QPushButton()
            # color_disabled visible: qtawesome, por defecto, dibuja el icono
            # deshabilitado en un gris tan tenue que parece no mostrarse. La
            # plantilla aún no guardada deja el botón deshabilitado, así que sin
            # esto el engranaje resultaba invisible.
            btn_config.setIcon(
                qta.icon("fa5s.cog", color="#64748B", color_disabled="#CBD5E1")
            )
            btn_config.setIconSize(QSize(16, 16))
            btn_config.setFixedSize(28, 24)
            btn_config.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_config.setStyleSheet(_preview_btn_style)
            btn_config.clicked.connect(lambda _, s=side: self._open_multi_template_dialog(s))
            row_lay.addWidget(btn_config)

            if side == "frente":
                self._lbl_frente_header = lbl
                self._btn_preview_frente = btn_prev
                self._btn_config_frente = btn_config
            else:
                self._lbl_vuelta_header = lbl
                self._btn_preview_vuelta = btn_prev
                self._btn_config_vuelta = btn_config

            # Estado inicial coherente (deshabilitado mientras no haya plantilla guardada).
            self._update_config_buttons_state()

            return row

        def wrap_view(title: str, view: QWidget, side: str) -> QWidget:
            wrapper = QWidget()
            w_layout = QVBoxLayout(wrapper)
            w_layout.setContentsMargins(0, 0, 0, 0)
            w_layout.setSpacing(4)
            header_row = make_side_header(title, side)
            w_layout.addWidget(header_row)
            w_layout.addWidget(view)
            return wrapper

        self._canvas_frente = wrap_view("FRENTE", self._view_frente, "frente")
        self._canvas_vuelta = wrap_view("VUELTA", self._view_vuelta, "vuelta")

        layout.addWidget(self._canvas_frente)
        layout.addWidget(self._canvas_vuelta)
        
        scroll.setWidget(container)
        return scroll


    def _build_right_panel(self) -> QWidget:
        """Construye el panel derecho con propiedades y capas.

        Returns:
            Widget con PropertiesPanel y LayersPanel apilados.
        """
        panel = QWidget()
        panel.setFixedWidth(340)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 8, 8)
        layout.setSpacing(8)

        self._properties_panel = PropertiesPanel()

        prop_scroll = QScrollArea()
        prop_scroll.setWidgetResizable(True)
        prop_scroll.setFrameShape(QFrame.Shape.NoFrame)
        prop_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        prop_scroll.setWidget(self._properties_panel)

        # stretch 3:1 — propiedades recibe 3x más espacio que capas
        layout.addWidget(prop_scroll, stretch=3)

        self._layers_panel = LayersPanel()
        self._layers_panel.setMaximumHeight(160)
        layout.addWidget(self._layers_panel, stretch=1)

        return panel

    def _build_bottom_bar(self) -> QLabel:
        """Construye la barra inferior de notificaciones (tipo status bar).

        Returns:
            QLabel con estilo de notificaciones.
        """
        bar = QLabel("")
        bar.setFixedHeight(28)
        bar.setStyleSheet(f"""
            QLabel {{
                background-color: #1E293B;
                color: #94A3B8;
                font-family: 'Inter', sans-serif;
                font-size: 12px;
                padding: 0 12px;
                border: none;
                border-radius: 0;
            }}
        """)
        self._status_bar = bar
        return bar

    def set_status(self, message: str, level: str = "info", toast: bool = True) -> None:
        """Actualiza la barra de notificaciones con un mensaje y, opcionalmente, muestra un toast.

        Args:
            message: Texto a mostrar.
            level: 'info', 'success', 'error', 'warning'.
            toast: Si es True (por defecto) muestra una notificación toast.
                   Usar False para pasos intermedios de un flujo de carga: el
                   progreso se refleja solo en el footer y se reserva el toast
                   para el resultado final.
        """
        from PySide6.QtCore import QCoreApplication
        from credencializacion.ui.widgets.toast import ToastManager
        colors = {
            "info": ("#1E293B", "#94A3B8"),
            "success": ("#052E16", "#4ADE80"),
            "error": ("#450A0A", "#FCA5A5"),
            "warning": ("#451A03", "#FCD34D"),
        }
        bg, fg = colors.get(level, colors["info"])
        self._status_bar.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                font-family: 'Inter', sans-serif;
                font-size: 12px;
                padding: 0 12px;
                border: none;
            }}
        """)
        self._status_bar.setText(message)
        QCoreApplication.processEvents()
        # Toast notification (solo resultado final)
        if toast:
            ToastManager.instance().show_toast(message, level)

    # ── Conexiones ─────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        """Conecta señales internas del editor."""
        self._canvas_toolbar.item_dragged.connect(self._on_tool_dragged)
        self._layers_panel.layer_selected.connect(self._on_layer_selected)
        self._properties_panel.property_changed.connect(self._on_property_changed)
        self._properties_panel.image_file_requested.connect(
            self._on_image_file_requested
        )

    # ── Métodos públicos ───────────────────────────────────────────

    def load_template(self, plantilla: "Plantilla") -> None:
        """Carga una plantilla en el editor.

        Args:
            plantilla: Modelo Plantilla a editar.
        """
        self._plantilla = plantilla
        self.set_orientation(plantilla.orientacion == "horizontal")

        # Actualizar canvas
        from credencializacion.ui.widgets.canvas import GraphicElement
        self._scene_frente.clear()
        self._scene_vuelta.clear()
        for data in plantilla.elementos_frente:
            self._scene_frente.addItem(GraphicElement(data))
        for data in plantilla.elementos_vuelta:
            self._scene_vuelta.addItem(GraphicElement(data))

        # Restaurar imágenes base guardadas en plantilla.recursos
        recursos = plantilla.recursos or {}
        from pathlib import Path
        for side, key in (("frente", "fondo_frente"), ("vuelta", "fondo_vuelta")):
            img_path_str = recursos.get(key, "")
            if img_path_str and Path(img_path_str).exists():
                self._apply_base_image_to_scene(side, Path(img_path_str))
                self._update_header_label(side, Path(img_path_str).name)

        elementos = (
            plantilla.elementos_frente
            if self._current_side == "frente"
            else plantilla.elementos_vuelta
        )
        self._layers_panel.set_layers(elementos)
        self._properties_panel.update_properties(None)

        # Cargar atributos del cliente asociado a la plantilla
        self._load_client_attributes(plantilla.cliente_id)

        # Reflejar el estado guardado en el botón de configuración (Req 1.5).
        self._update_config_buttons_state()

    def _update_config_buttons_state(self) -> None:
        """Actualiza el ⚙ y el estado de FRENTE/VUELTA por lado.

        Por cada lado: si existe una ConfiguracionLado para (plantilla, lado), el
        ⚙ de ese lado se habilita (para editar/eliminar) y el encabezado queda
        inhabilitado para asignación directa; si no existe, el ⚙ se deshabilita y
        el encabezado queda disponible. El ⚙ requiere además plantilla guardada
        (Req 2.3/2.4).
        """
        saved = bool(
            getattr(self, "_plantilla", None) is not None
            and getattr(self._plantilla, "cliente_id", None)
        )
        self._lado_tiene_config = {"frente": False, "vuelta": False}
        if saved:
            try:
                from credencializacion.db.engine import DatabaseSession
                from credencializacion.db.repositories import LadoConfigRepository

                with DatabaseSession() as session:
                    for side in ("frente", "vuelta"):
                        cfg = LadoConfigRepository.get_config_lado(
                            session, self._plantilla.id, side
                        )
                        self._lado_tiene_config[side] = cfg is not None
            except Exception:  # noqa: BLE001
                pass

        for side, attr in (
            ("frente", "_btn_config_frente"),
            ("vuelta", "_btn_config_vuelta"),
        ):
            btn = getattr(self, attr, None)
            if btn is None:
                continue
            has_config = self._lado_tiene_config.get(side, False)
            btn.setEnabled(saved and has_config)
            if not saved:
                btn.setToolTip(
                    "Guarda la plantilla antes de configurar el multiplantillaje"
                )
            elif has_config:
                btn.setToolTip(f"Editar multiplantillaje del {side}")
            else:
                btn.setToolTip(
                    f"Selecciona 2+ imágenes en {side.upper()} para crear el "
                    "multiplantillaje"
                )

    def _open_lado_config(self, side: str, rutas_iniciales: list[str] | None = None) -> None:
        """Abre la Vista_Configuracion del lado (crea o edita la config).

        Requiere plantilla guardada (para conocer plantilla_id y cliente_id). Si
        no lo está, ofrece guardar primero. Al guardar/eliminar la configuración,
        recarga la imagen base por defecto del lado y refresca los botones.
        """
        from PySide6.QtWidgets import QMessageBox

        if getattr(self, "_plantilla", None) is None or not getattr(
            self._plantilla, "cliente_id", None
        ):
            reply = QMessageBox.question(
                self,
                "Guardar diseño",
                "Para configurar el multiplantillaje hay que guardar primero el "
                "diseño. ¿Guardar ahora?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_template()
            if getattr(self, "_plantilla", None) is None or not getattr(
                self._plantilla, "cliente_id", None
            ):
                return

        try:
            from credencializacion.ui.dialogs.multi_template_dialog import (
                MultiTemplateDialog,
            )

            dialog = MultiTemplateDialog(
                self._plantilla.id,
                self._plantilla.cliente_id,
                side,
                rutas_iniciales,
                self,
            )
            dialog.config_saved.connect(
                lambda _pid, lado: self._on_lado_config_changed(lado)
            )
            dialog.config_deleted.connect(
                lambda _pid, lado: self._on_lado_config_changed(lado)
            )
            dialog.exec()
        except Exception as e:  # noqa: BLE001 — mantener el editor sin cambios (Req 1.6)
            QMessageBox.critical(
                self,
                "Multiplantillaje",
                f"No se pudo abrir la configuración de multiplantillaje.\n\n{e}",
            )

    def _on_lado_config_changed(self, side: str) -> None:
        """Tras guardar/eliminar la config de un lado, recarga el fondo y botones."""
        self._reload_base_image_from_db(side)
        self._update_config_buttons_state()

    def _reload_base_image_from_db(self, side: str) -> None:
        """Recarga la imagen base por defecto del lado desde la BD y la aplica."""
        from pathlib import Path
        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Plantilla

        if not self._plantilla:
            return
        with get_session() as session:
            p = session.query(Plantilla).get(self._plantilla.id)
            if not p:
                return
            recursos = dict(p.recursos or {})
        self._plantilla.recursos = recursos
        path = recursos.get(f"fondo_{side}")
        if path and Path(path).exists():
            self._apply_base_image_to_scene(side, Path(path))
            self._update_header_label(side, Path(path).name)

    def _open_multi_template_dialog(self, side: str) -> None:
        """Abre la configuración de multiplantillaje del lado desde el ⚙ (Req 1.3)."""
        self._open_lado_config(side)

    def _load_client_attributes(self, cliente_id: int) -> None:
        """Carga los atributos conocidos del cliente en el toolbar.

        Si el cliente ya fue sincronizado, usa sus `known_attributes`.
        Si no, usa el catálogo fijo como fallback y muestra un banner.
        """
        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Cliente

        with get_session() as session:
            cliente = session.query(Cliente).get(cliente_id)
            if not cliente:
                return

            cfg = cliente.config or {}
            known_attrs = cfg.get("known_attributes", [])
            image_attrs = cfg.get("image_attributes", [])
            last_sync = cfg.get("last_sync", "")
            nombre_cliente = cliente.nombre

        # Poblar el combobox de atributos de imagen del panel de propiedades.
        self._properties_panel.set_image_attributes(image_attrs)

        if known_attrs:
            # Atributos reales del cliente — actualizar el toolbar
            self._canvas_toolbar.load_attributes(known_attrs)
            self._properties_panel.set_available_attributes(known_attrs)
            # Actualizar título del toolbar para indicar el cliente activo
            self._canvas_toolbar.set_client_label(nombre_cliente, last_sync)
        else:
            # Sin sincronización aún — catálogo fijo como fallback
            self._canvas_toolbar.set_client_label(
                nombre_cliente, "", sync_needed=True
            )

    # ── Plantilla base (imagen de fondo) ───────────────────────────────────

    def _select_base_image(self, side: str) -> None:
        """Selecciona la(s) imagen(es) base del lado desde el explorador.

        - Si el lado ya tiene configuración de multiplantillaje, la asignación
          directa está inhabilitada: se indica usar el ⚙ para editarla.
        - 1 imagen → se asigna como fondo del lado (sin multiplantillaje).
        - 2+ imágenes → se abre la Vista_Configuracion del lado para definir las
          variantes (no se crean diseños nuevos).
        """
        from PySide6.QtWidgets import QFileDialog
        from pathlib import Path

        if getattr(self, "_lado_tiene_config", {}).get(side):
            self.set_status(
                f"El lado {side} usa multiplantillaje. Edítalo con el botón ⚙ "
                f"junto a {side.upper()}.",
                "info",
            )
            return

        paths, _ = QFileDialog.getOpenFileNames(
            self,
            f"Seleccionar imagen base — {side.upper()} "
            "(elige varias para multiplantillaje)",
            str(Path.home()),
            "Imágenes (*.png *.jpg *.jpeg *.webp)",
        )
        if not paths:
            return

        if len(paths) == 1:
            self._apply_single_base_image(side, paths[0])
            return

        # 2+ imágenes → multiplantillaje del lado: copiar imágenes y abrir la
        # Vista_Configuracion (no se crean diseños/plantillas nuevas).
        rutas: list[str] = []
        for p in paths:
            dest = self._copy_to_plantilla_base(p)
            if dest is not None:
                rutas.append(str(dest))
        if not rutas:
            return
        self._open_lado_config(side, rutas)

    def _copy_to_plantilla_base(self, path_str: str) -> "Path | None":
        """Copia una imagen a la carpeta de imágenes base y devuelve su ruta destino.

        El destino es la carpeta estable del usuario (`get_plantilla_base_dir`),
        fuera del directorio de la app, de modo que las actualizaciones no borren
        las imágenes base. Devuelve ``None`` si la copia falla.
        """
        from pathlib import Path
        import shutil
        from credencializacion.utils.paths import get_plantilla_base_dir

        src = Path(path_str)
        dest_folder = get_plantilla_base_dir()  # crea el directorio si no existe
        dest_folder.mkdir(parents=True, exist_ok=True)
        dest = dest_folder / src.name

        if src.resolve() != dest.resolve():
            try:
                shutil.copy2(src, dest)
            except Exception as e:  # noqa: BLE001
                self.set_status(f"❌ No se pudo copiar la imagen: {e}", "error")
                return None
        return dest

    def _apply_single_base_image(self, side: str, path_str: str) -> None:
        """Asigna una única imagen como fondo del lado indicado del diseño actual."""
        from pathlib import Path

        dest = self._copy_to_plantilla_base(path_str)
        if dest is None:
            return

        # Guardar la ruta en los recursos de la plantilla (en memoria y DB)
        self._save_base_image_path(side, str(dest))
        # Aplicar al canvas inmediatamente
        self._apply_base_image_to_scene(side, dest)
        # Actualizar etiqueta del header
        self._update_header_label(side, Path(path_str).name)

    def _save_base_image_path(self, side: str, path: str) -> None:
        """Persiste la ruta de la imagen base en Plantilla.recursos."""
        key = f"fondo_{side}"  # "fondo_frente" o "fondo_vuelta"

        if self._plantilla:
            from credencializacion.db.engine import get_session
            from credencializacion.db.models import Plantilla
            from sqlalchemy.orm.attributes import flag_modified

            # Actualizar en memoria
            recursos = dict(self._plantilla.recursos or {})
            recursos[key] = path
            self._plantilla.recursos = recursos

            # Persistir en DB
            with get_session() as session:
                plantilla_db = session.query(Plantilla).get(self._plantilla.id)
                if plantilla_db:
                    db_recursos = dict(plantilla_db.recursos or {})
                    db_recursos[key] = path
                    plantilla_db.recursos = db_recursos
                    flag_modified(plantilla_db, "recursos")
                    session.commit()
        else:
            # Plantilla no guardada aún — guardar en estado local
            if not hasattr(self, "_local_recursos"):
                self._local_recursos = {}
            self._local_recursos[key] = path

    def _apply_base_image_to_scene(self, side: str, image_path: "Path") -> None:
        """Dibuja la imagen de fondo en la escena del canvas indicado.

        La imagen se muestra como BackgroundItem en z_order=−1 para estar
        detrás de todos los elementos de diseño.
        """
        from credencializacion.ui.widgets.canvas import GraphicElement, MM_TO_PX
        from pathlib import Path

        scene = self._scene_frente if side == "frente" else self._scene_vuelta

        # Obtener dimensiones del lienzo en cm a partir del sceneRect actual,
        # que es la fuente de verdad de la orientación vigente (vertical u
        # horizontal). Así la imagen base respeta la orientación del lienzo en
        # lugar de forzar un tamaño horizontal por defecto.
        rect = scene.sceneRect()
        if rect.width() > 0 and rect.height() > 0:
            plantilla_ancho = rect.width() / (10 * MM_TO_PX)   # px → cm
            plantilla_alto = rect.height() / (10 * MM_TO_PX)
        elif self._plantilla:
            plantilla_ancho = self._plantilla.ancho
            plantilla_alto = self._plantilla.alto
        elif getattr(self, "_local_orientation", "horizontal") == "vertical":
            plantilla_ancho, plantilla_alto = 5.4, 8.5
        else:
            plantilla_ancho, plantilla_alto = 8.5, 5.4

        # Eliminar cualquier fondo base anterior
        items_to_remove = [
            item for item in scene.items()
            if isinstance(item, GraphicElement) and item.data_dict().get("type") == "base_image"
        ]
        for item in items_to_remove:
            scene.removeItem(item)

        # Crear elemento de imagen base que ocupa todo el lienzo
        elem_data = {
            "type": "base_image",
            "x": 0.0,
            "y": 0.0,
            "width": plantilla_ancho * 10,   # cm → mm
            "height": plantilla_alto * 10,   # cm → mm
            "z_order": -1,
            "campo_dato": None,
            "properties": {
                "src": str(image_path),
            },
        }
        item = GraphicElement(elem_data)
        scene.addItem(item)

    def _update_header_label(self, side: str, filename: str) -> None:
        """Actualiza la etiqueta del header para mostrar el nombre de la imagen cargada."""
        lbl = self._lbl_frente_header if side == "frente" else self._lbl_vuelta_header
        title = "FRENTE" if side == "frente" else "VUELTA"
        lbl.setText(
            f"🖼 {title}  "
            f"<span style='font-size:10px; color:#22C55E;'>✓ {filename}</span>"
            f"<span style='font-size:10px; color:#94A3B8;'>  (clic para cambiar)</span>"
        )


    def save_template(self) -> None:
        """Guarda el estado actual del editor en la base de datos."""
        # Sincronizar posiciones actuales del canvas con el modelo antes de guardar
        self._sync_scene_to_model()
        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Plantilla
        from credencializacion.ui.dialogs.template_dialogs import SaveTemplateDialog
        from PySide6.QtWidgets import QMessageBox

        if not self._plantilla:
            dialog = SaveTemplateDialog(self)
            if dialog.exec() == SaveTemplateDialog.DialogCode.Accepted:
                with get_session() as session:
                    nueva = Plantilla(
                        cliente_id=dialog.cliente_id,
                        nombre=dialog.template_name,
                        elementos_frente=self._local_frente,
                        elementos_vuelta=self._local_vuelta,
                        orientacion=self._local_orientation,
                        ancho=8.5 if self._local_orientation == "horizontal" else 5.4,
                        alto=5.4 if self._local_orientation == "horizontal" else 8.5,
                        recursos=dict(getattr(self, "_local_recursos", {}) or {}),
                        posiciones_hoja={
                            "page_size": "custom_297_320",
                            "cards_per_page": 2,
                            "positions": [
                                {"x_cm": 10.6, "y_cm": 20.0},
                                {"x_cm": 10.6, "y_cm": 10.0},
                            ]
                        }
                    )
                    session.add(nueva)
                    session.commit()
                    session.refresh(nueva)
                    session.expunge(nueva)
                    self.load_template(nueva)
                    self.set_status("✅ Plantilla guardada correctamente.", "success")
        else:
            with get_session() as session:
                from sqlalchemy.orm.attributes import flag_modified
                plantilla_db = session.query(Plantilla).get(self._plantilla.id)
                if plantilla_db:
                    plantilla_db.elementos_frente = list(self._plantilla.elementos_frente)
                    plantilla_db.elementos_vuelta = list(self._plantilla.elementos_vuelta)
                    plantilla_db.orientacion = self._plantilla.orientacion
                    plantilla_db.ancho = self._plantilla.ancho
                    plantilla_db.alto = self._plantilla.alto
                    plantilla_db.recursos = dict(self._plantilla.recursos or {})
                    flag_modified(plantilla_db, "elementos_frente")
                    flag_modified(plantilla_db, "elementos_vuelta")
                    flag_modified(plantilla_db, "recursos")
                    session.commit()
                    self.set_status("✅ Plantilla actualizada.", "success")
                    # Reflejar el estado guardado en el botón de configuración (Req 1.5).
                    self._update_config_buttons_state()

    def open_template_dialog(self) -> None:
        """Abre el diálogo para cargar una plantilla guardada."""
        from credencializacion.db.engine import get_session
        from credencializacion.db.models import Plantilla
        from credencializacion.ui.dialogs.template_dialogs import OpenTemplateDialog
        
        dialog = OpenTemplateDialog(self)
        if dialog.exec() == OpenTemplateDialog.DialogCode.Accepted and dialog.selected_plantilla_id:
            with get_session() as session:
                plantilla = session.query(Plantilla).get(dialog.selected_plantilla_id)
                if plantilla:
                    session.expunge(plantilla)
                    self.load_template(plantilla)

    def _reset_header_label(self, side: str) -> None:
        """Restablece la etiqueta de cabecera de un lado a su estado inicial."""
        lbl = self._lbl_frente_header if side == "frente" else self._lbl_vuelta_header
        title = "FRENTE" if side == "frente" else "VUELTA"
        lbl.setText(
            f"🖼 {title}  "
            f"<span style='font-size:10px; color:#94A3B8;'>(clic para imagen base)</span>"
        )

    def new_template(self) -> None:
        """Crea una plantilla nueva en blanco e inicializa los lienzos.

        Descarta el diseño abierto previamente (sin guardarlo ni tocar la base
        de datos): limpia ambas escenas, el estado local y la plantilla en
        memoria, restablece la orientación por defecto y deja el editor listo
        para diseñar desde cero. Resuelve el caso de quedar con los lienzos de
        una plantilla abierta previamente al empezar una nueva.
        """
        # Estado en memoria (no guardado todavía).
        self._plantilla = None
        self._local_frente = []
        self._local_vuelta = []
        self._local_recursos = {}
        self._current_side = "frente"
        self._undo_stack.clear()
        self._redo_stack.clear()

        # Limpiar ambas escenas (elementos e imágenes base).
        self._scene_frente.clear()
        self._scene_vuelta.clear()

        # Orientación por defecto (horizontal) — también reajusta el tamaño de
        # los lienzos a 8.5×5.4 cm.
        self.set_orientation(True)

        # Restablecer cabeceras y paneles.
        self._reset_header_label("frente")
        self._reset_header_label("vuelta")
        self._layers_panel.set_layers([])
        self._properties_panel.update_properties(None)

        # Sin plantilla guardada: botones de multiplantillaje deshabilitados.
        self._update_config_buttons_state()

        self.set_status("📄 Nueva plantilla. Diseña y pulsa Guardar.", "info")



    def preview_template(self, cara: str | None = None) -> None:
        """Genera la vista previa con los primeros dos registros reales.

        El frente y la vuelta se generan en documentos PDF separados (uno por
        cada cara) y se muestran en el diálogo de vista previa con pestañas.

        Args:
            cara: 'frente', 'vuelta', o 'both'. Cuando es 'both' (o None) se
                  generan ambas caras en documentos independientes.
        """
        # Sincronizar posiciones actuales del canvas con el modelo antes de renderizar
        self._sync_scene_to_model()
        from credencializacion.renderer.pdf_engine import PDFEngine
        from credencializacion.db.models import Registro
        from credencializacion.db.engine import get_session
        from credencializacion.ui.dialogs.preview_dialog import PreviewDialog
        from PySide6.QtWidgets import QMessageBox
        from pathlib import Path
        import tempfile
        import os

        cara = cara or "both"

        # La plantilla debe estar guardada para conocer el cliente_id
        if not self._plantilla:
            reply = QMessageBox.question(
                self,
                "Guardar Plantilla",
                "Para generar la vista previa con datos reales, primero guarda la plantilla.\n\n¿Deseas guardarla ahora?",
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_template()
            if not self._plantilla:
                return

        # Buscar los primeros 2 registros del cliente en la BD
        registros: list[Registro] = []
        with get_session() as session:
            rows = (
                session.query(Registro)
                .filter(Registro.cliente_id == self._plantilla.cliente_id)
                .limit(2)
                .all()
            )
            for r in rows:
                session.expunge(r)
                registros.append(r)

        # Si no hay registros, ofrecer sincronizar ahora
        if not registros:
            reply = QMessageBox.question(
                self,
                "Sin datos sincronizados",
                "No hay alumnos sincronizados para este cliente.\n\n"
                "Ve al Panel de Control → Sincronizar → app.miescuela.net para descargar los datos.\n\n"
                "¿Deseas ir al Panel de Control ahora?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                parent = self.parent()
                while parent and not hasattr(parent, "_stack"):
                    parent = parent.parent()
                if parent and hasattr(parent, "_stack"):
                    parent._stack.setCurrentIndex(0)
            return

        engine = PDFEngine(self._plantilla)

        def _mk_temp(cara_name: str) -> Path:
            fd, path_str = tempfile.mkstemp(
                suffix=".pdf", prefix=f"preview_{cara_name}_"
            )
            os.close(fd)
            return Path(path_str)

        try:
            frentes_pdf: Path | None = None
            vueltas_pdf: Path | None = None

            if cara in ("frente", "both"):
                frentes_pdf = _mk_temp("frente")
                engine.render(registros, "frente", frentes_pdf)

            if cara in ("vuelta", "both"):
                vueltas_pdf = _mk_temp("vuelta")
                engine.render(registros, "vuelta", vueltas_pdf)

            dlg = PreviewDialog(
                frentes_pdf=frentes_pdf,
                vueltas_pdf=vueltas_pdf,
                parent=self,
            )
            dlg.exec()
        except Exception as e:
            self.set_status(f"❌ Error de vista previa: {e}", "error")




    def _sync_scene_to_model(self) -> None:
        """Sincroniza las posiciones y propiedades actuales de los GraphicElement
        del canvas con el modelo de datos (plantilla o _local_*).

        Esto es necesario porque cuando el usuario mueve un elemento en el lienzo,
        las coordenadas se actualizan en el QGraphicsItem pero no se propagan
        automáticamente al dict JSON del modelo. Este método fuerza la sincronización
        antes de cualquier operación de render o guardado.
        """
        from credencializacion.ui.widgets.canvas import GraphicElement

        for side, scene in (("frente", self._scene_frente), ("vuelta", self._scene_vuelta)):
            # Recopilar datos actualizados de todos los GraphicElement del canvas
            canvas_items = [
                item for item in scene.items()
                if isinstance(item, GraphicElement)
            ]
            if not canvas_items:
                continue

            # get_data() sincroniza pos().x/y → data["x"],data["y"] en mm
            synced_data = [item.get_data() for item in canvas_items]

            # Actualizar el modelo con la lista sincronizada
            self._set_elementos(side, synced_data)

    def _get_elementos(self, side: str) -> list[dict]:
        if self._plantilla:
            return self._plantilla.elementos_frente if side == "frente" else self._plantilla.elementos_vuelta
        return self._local_frente if side == "frente" else self._local_vuelta

    def _set_elementos(self, side: str, elements: list[dict]) -> None:
        if self._plantilla:
            if side == "frente":
                self._plantilla.elementos_frente = elements
            else:
                self._plantilla.elementos_vuelta = elements
        else:
            if side == "frente":
                self._local_frente = elements
            else:
                self._local_vuelta = elements

    def _push_undo_state(self) -> None:
        """Guarda el estado actual en la pila de deshacer."""
        frente = copy.deepcopy(self._get_elementos("frente"))
        vuelta = copy.deepcopy(self._get_elementos("vuelta"))
        self._undo_stack.append((frente, vuelta))
        self._redo_stack.clear()
        
        # Limitar historial a 30
        if len(self._undo_stack) > 30:
            self._undo_stack.pop(0)

    def _restore_state(self, state: tuple[list[dict], list[dict]]) -> None:
        """Restaura un estado de la plantilla y recarga los lienzos."""
        frente, vuelta = state
        self._set_elementos("frente", copy.deepcopy(frente))
        self._set_elementos("vuelta", copy.deepcopy(vuelta))
        
        # Recargar canvas
        self._scene_frente.clear()
        self._scene_vuelta.clear()
        
        from credencializacion.ui.widgets.canvas import GraphicElement
        for data in self._get_elementos("frente"):
            self._scene_frente.addItem(GraphicElement(data))
        for data in self._get_elementos("vuelta"):
            self._scene_vuelta.addItem(GraphicElement(data))
            
        # Actualizar capas
        elementos = self._get_elementos(self._current_side)
        self._layers_panel.set_layers(elementos)
        self._properties_panel.update_properties(None)

    def undo(self) -> None:
        """Deshacer la última acción."""
        if not self._undo_stack:
            return
            
        # Push actual state to redo
        curr_frente = copy.deepcopy(self._get_elementos("frente"))
        curr_vuelta = copy.deepcopy(self._get_elementos("vuelta"))
        self._redo_stack.append((curr_frente, curr_vuelta))
        
        prev_state = self._undo_stack.pop()
        self._restore_state(prev_state)

    def redo(self) -> None:
        """Rehacer la acción deshecha."""
        if not self._redo_stack:
            return
            
        # Push actual state to undo
        curr_frente = copy.deepcopy(self._get_elementos("frente"))
        curr_vuelta = copy.deepcopy(self._get_elementos("vuelta"))
        self._undo_stack.append((curr_frente, curr_vuelta))
        
        next_state = self._redo_stack.pop()
        self._restore_state(next_state)

    def set_attributes(self, attributes: list[str]) -> None:
        """Carga la lista de atributos dinámicamente en la barra de herramientas."""
        self._canvas_toolbar.load_attributes(attributes)
        self._properties_panel.set_available_attributes(attributes)

    def set_preview_data(self, registro: "Registro") -> None:
        """Establece datos de un registro para vista previa en el canvas.

        Args:
            registro: Registro para sustituir campos en la vista previa.
        """
        # Se integrará con CredentialView para renderizar con datos reales
        pass

    # ── Handlers internos ──────────────────────────────────────────

    def _switch_side(self, side: str) -> None:
        """Cambia el lado activo (frente/vuelta) para edición de capas.

        El editor muestra ambos lienzos apilados, por lo que solo se actualiza
        el lado activo y el panel de capas; no hay botones toggle que estilizar.

        Args:
            side: 'frente' o 'vuelta'.
        """
        self._current_side = side

        # Recargar capas del lado activo
        elementos = self._get_elementos(side)
        self._layers_panel.set_layers(elementos)

    def _zoom_in(self) -> None:
        """Incrementa el zoom 10%."""
        self._zoom_level = min(200, self._zoom_level + 10)
        self._lbl_zoom.setText(f"{self._zoom_level}%")

    def _zoom_out(self) -> None:
        """Decrementa el zoom 10%."""
        self._zoom_level = max(25, self._zoom_level - 10)
        self._lbl_zoom.setText(f"{self._zoom_level}%")

    def _on_tool_dragged(self, tool_type: str) -> None:
        """Maneja la selección de herramienta o atributo.

        Args:
            tool_type: Formato 'tipo:campo' o 'tool:tipo_herramienta'.
        """
        scene = self._scene_frente if self._current_side == "frente" else self._scene_vuelta
        w = self._plantilla.ancho if self._plantilla else 8.5
        h = self._plantilla.alto if self._plantilla else 5.4

        # Parsear el formato tipo:campo
        if ":" in tool_type:
            elem_type, campo = tool_type.split(":", 1)
        else:
            elem_type, campo = tool_type, ""

        # Mapa de tipos a datos de elemento
        if elem_type == "composite":
            new_elem = {
                "type": "composite",
                "campo_dato": campo,
                "x": 5, "y": 5,
                "width": 40, "height": 10,
                "z_order": len(scene.items()) + 1,
                "properties": {
                    "composite_template": "",
                    "font_family": "Inter",
                    "font_size": 12,
                    "color": "#171A2B",
                    "render_as": "Texto",
                    "test_text": "",
                }
            }
        elif elem_type == "photo_path":
            new_elem = {
                "type": "photo_path",
                "campo_dato": campo,
                "x": 5, "y": 5,
                "width": 25, "height": 30,
                "z_order": len(scene.items()) + 1,
                "properties": {}
            }
        elif elem_type == "text":
            new_elem = {
                "type": "text",
                "campo_dato": campo,
                "x": 5, "y": 5,
                "width": 40, "height": 10,
                "z_order": len(scene.items()) + 1,
                "properties": {
                    "font_family": "Inter",
                    "font_size": 12,
                    "color": "#171A2B",
                    "alignment": "left",
                    "render_as": "Texto",
                    "test_text": "",
                    "is_static": False,
                }
            }
        else:
            return  # tipo desconocido

        from credencializacion.ui.widgets.canvas import GraphicElement
        item = GraphicElement(new_elem)
        scene.addItem(item)
        self._on_item_updated(new_elem)

    def _on_layer_selected(self, index: int) -> None:
        """Maneja la selección de una capa en el panel de capas.

        Args:
            index: Índice de la capa seleccionada.
        """
        # Se conectará al scene para seleccionar el item correspondiente
        elementos = self._get_elementos(self._current_side)
        sorted_elems = sorted(
            elementos, key=lambda e: e.get("z_order", 0), reverse=True
        )
        if 0 <= index < len(sorted_elems):
            self._properties_panel.update_properties(sorted_elems[index])

    def _on_item_updated(self, item_data: dict) -> None:
        """Llamado cuando el scene añade o mueve un elemento."""
        elementos = self._get_elementos(self._current_side)
        if item_data not in elementos:
            self._push_undo_state()
            elementos.append(item_data)
        
        self._properties_panel.update_properties(item_data)
        # Actualizar layers
        self._layers_panel.set_layers(elementos)

    def _on_scene_selection_changed(self) -> None:
        """Llamado cuando cambia la selección en el scene activo."""
        scene = self.sender()
        if scene == self._scene_frente:
            if self._current_side != "frente":
                self._switch_side("frente")
        elif scene == self._scene_vuelta:
            if self._current_side != "vuelta":
                self._switch_side("vuelta")
        else:
            scene = self._scene_frente if self._current_side == "frente" else self._scene_vuelta
            
        selected = scene.selectedItems()
        if selected:
            # selected[0] es GraphicElement
            self._properties_panel.update_properties(selected[0].get_data())
        else:
            self._properties_panel.update_properties(None)
            
    def set_orientation(self, is_horizontal: bool) -> None:
        """Actualiza la orientación de los lienzos."""
        if self._plantilla:
            self._plantilla.orientacion = "horizontal" if is_horizontal else "vertical"
            w = self._plantilla.ancho
            h = self._plantilla.alto
            if is_horizontal and h > w:
                self._plantilla.ancho, self._plantilla.alto = h, w
            elif not is_horizontal and w > h:
                self._plantilla.ancho, self._plantilla.alto = h, w
            
            self._scene_frente.set_physical_size(self._plantilla.ancho, self._plantilla.alto)
            self._scene_vuelta.set_physical_size(self._plantilla.ancho, self._plantilla.alto)
        else:
            self._local_orientation = "horizontal" if is_horizontal else "vertical"
            w = 8.5 if is_horizontal else 5.4
            h = 5.4 if is_horizontal else 8.5
            self._scene_frente.set_physical_size(w, h)
            self._scene_vuelta.set_physical_size(w, h)

    def _on_property_changed(self, key: str, value: Any) -> None:
        """Actualiza el elemento seleccionado en el canvas cuando el panel cambia."""
        scene = self._scene_frente if self._current_side == "frente" else self._scene_vuelta
        selected = scene.selectedItems()
        if not selected:
            return
            
        item = selected[0]
        data = item.get_data()
        
        # Ignorar si no hay cambio real
        if data.get(key) == value or data.get("properties", {}).get(key) == value:
            return
            
        self._push_undo_state()
        
        # Actualizar datos dependiendo de la propiedad
        if key in ("x", "y", "width", "height", "campo_dato"):
            data[key] = value
        else:
            if "properties" not in data:
                data["properties"] = {}
            data["properties"][key] = value
            
        item.set_data(data)
        
        if key == "is_static":
            self._properties_panel.update_properties(item.get_data())
    def align_selected(self, alignment: str) -> None:
        """Alinea el elemento seleccionado en el lienzo actual."""
        scene = self._scene_frente if self._current_side == "frente" else self._scene_vuelta
        selected = scene.selectedItems()
        if not selected:
            return
            
        self._push_undo_state()
        
        item = selected[0]
        data = item.get_data()
        w = data.get("width", 0)
        
        canvas_width = scene.sceneRect().width() / MM_TO_PX
        
        if alignment == "left":
            data["x"] = 0
        elif alignment == "center":
            data["x"] = (canvas_width - w) / 2
        elif alignment == "right":
            data["x"] = canvas_width - w

        # Para texto/compuesto, alinear también el contenido dentro de la caja,
        # no solo la posición de la caja. Así, al centrar la caja en el lienzo,
        # el texto queda anclado al mismo eje central y los atributos de distinta
        # longitud comparten el centro (no se anclan por el borde izquierdo).
        if data.get("type") in ("text", "composite"):
            data.setdefault("properties", {})["alignment"] = alignment
            
        item.set_data(data)
        self._properties_panel.update_properties(item.get_data())

    def delete_selected(self) -> None:
        """Elimina el elemento seleccionado."""
        scene = self._scene_frente if self._current_side == "frente" else self._scene_vuelta
        selected = scene.selectedItems()
        if not selected:
            return
            
        self._push_undo_state()
            
        item = selected[0]
        data = item.get_data()
        scene.removeItem(item)
        
        # Remover del JSON
        elementos = self._get_elementos(self._current_side)
        if data in elementos:
            elementos.remove(data)

        # Si era una imagen con origen archivo, borrar el archivo copiado solo si
        # no se usa en otra parte (otro lado, otra plantilla del cliente, o una
        # configuración de multiplantillaje) — Decisión del usuario.
        self._maybe_cleanup_image_file(data)

        self._layers_panel.set_layers(elementos)
        
        self._properties_panel.update_properties(None)

    def _on_image_file_requested(self) -> None:
        """Abre el explorador para asignar un archivo de imagen al elemento."""
        from PySide6.QtWidgets import QFileDialog
        from pathlib import Path

        scene = self._scene_frente if self._current_side == "frente" else self._scene_vuelta
        selected = scene.selectedItems()
        if not selected:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Elegir imagen", str(Path.home()),
            "Imágenes (*.png *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        dest = self._copy_to_img_dir(path)
        if dest is None:
            return
        item = selected[0]
        data = item.get_data()
        props = data.setdefault("properties", {})
        props["src"] = str(dest)
        props["img_source"] = "file"
        data["campo_dato"] = None  # origen archivo: no usa atributo
        self._push_undo_state()
        item.set_data(data)
        self._properties_panel.update_properties(item.get_data())

    def _copy_to_img_dir(self, path_str: str) -> "Path | None":
        """Copia (o reutiliza) una imagen en data/img/{cliente} y devuelve su ruta.

        Si ya existe un archivo con el mismo nombre y tamaño, se reutiliza en
        lugar de volver a copiar (evita duplicados).
        """
        from pathlib import Path
        import shutil
        from credencializacion.utils.paths import get_img_dir

        cliente_nombre = None
        if self._plantilla and getattr(self._plantilla, "cliente_id", None):
            from credencializacion.db.engine import get_session
            from credencializacion.db.models import Cliente

            with get_session() as s:
                c = s.query(Cliente).get(self._plantilla.cliente_id)
                cliente_nombre = c.nombre if c else None

        src = Path(path_str)
        dest_folder = get_img_dir(cliente_nombre)
        dest = dest_folder / src.name

        if src.resolve() == dest.resolve():
            return dest
        # Reutilizar si ya está copiada (mismo nombre y tamaño).
        try:
            if dest.exists() and dest.stat().st_size == src.stat().st_size:
                return dest
        except Exception:  # noqa: BLE001
            pass
        try:
            shutil.copy2(src, dest)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"❌ No se pudo copiar la imagen: {e}", "error")
            return None
        return dest

    def _maybe_cleanup_image_file(self, data: dict) -> None:
        """Borra el archivo de imagen del elemento si ya no se usa en ninguna parte."""
        from pathlib import Path
        from credencializacion.utils.paths import get_img_dir

        if (data or {}).get("type") not in ("image", "photo_path"):
            return
        src = (data.get("properties") or {}).get("src", "")
        if not src:
            return
        try:
            src_path = Path(src)
            img_root = get_img_dir()  # data/img (raíz)
            # Solo gestionamos archivos dentro de nuestra carpeta de imágenes.
            if img_root not in src_path.resolve().parents:
                return
            if not src_path.exists():
                return
            if self._image_src_used_elsewhere(src):
                return
            src_path.unlink()
        except Exception:  # noqa: BLE001
            pass

    def _image_src_used_elsewhere(self, src: str) -> bool:
        """Indica si una ruta de imagen se usa en otro elemento/plantilla/config."""
        # 1) Otro lado del diseño en edición (escenas actuales).
        from credencializacion.ui.widgets.canvas import GraphicElement

        for scene in (self._scene_frente, self._scene_vuelta):
            for it in scene.items():
                if isinstance(it, GraphicElement):
                    if (it.data_dict().get("properties") or {}).get("src") == src:
                        return True

        if not (self._plantilla and getattr(self._plantilla, "cliente_id", None)):
            return False

        # 2) Plantillas del cliente (elementos) y configuraciones por lado.
        try:
            from credencializacion.db.engine import get_session
            from credencializacion.db.models import (
                Plantilla, VarianteImagen, ConfiguracionLado,
            )

            with get_session() as s:
                plantillas = (
                    s.query(Plantilla)
                    .filter_by(cliente_id=self._plantilla.cliente_id)
                    .all()
                )
                for p in plantillas:
                    for elementos in (p.elementos_frente or [], p.elementos_vuelta or []):
                        for el in elementos:
                            if (el.get("properties") or {}).get("src") == src:
                                return True
                    if src in (dict(p.recursos or {})).values():
                        return True
                # Variantes de multiplantillaje (rutas de imagen) del cliente.
                q = (
                    s.query(VarianteImagen.imagen_path)
                    .join(ConfiguracionLado)
                    .join(Plantilla, Plantilla.id == ConfiguracionLado.plantilla_id)
                    .filter(Plantilla.cliente_id == self._plantilla.cliente_id)
                )
                if any(row[0] == src for row in q.all()):
                    return True
                if (
                    s.query(ConfiguracionLado)
                    .join(Plantilla, Plantilla.id == ConfiguracionLado.plantilla_id)
                    .filter(Plantilla.cliente_id == self._plantilla.cliente_id)
                    .filter(ConfiguracionLado.imagen_default_path == src)
                    .count()
                ):
                    return True
        except Exception:  # noqa: BLE001
            return True  # ante la duda, no borrar
        return False
