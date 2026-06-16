"""
Panel de capas para el editor de credenciales.
Permite gestionar la visibilidad, nombre y orden z de los elementos en el lienzo.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon


class LayerItemWidget(QWidget):
    """Widget personalizado para representar una capa en la lista."""

    visibility_toggled = Signal(bool)

    def __init__(self, item_name: str, is_visible: bool = True, parent=None):
        super().__init__(parent)
        self._setup_ui(item_name, is_visible)

    def _setup_ui(self, item_name: str, is_visible: bool):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Botón de visibilidad (Ojo)
        self.btn_visible = QPushButton()
        self.btn_visible.setFixedSize(24, 24)
        self.btn_visible.setCheckable(True)
        self.btn_visible.setChecked(is_visible)
        self._update_eye_icon()
        self.btn_visible.clicked.connect(self._on_visibility_clicked)
        self.btn_visible.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.btn_visible)

        # Etiqueta de nombre
        self.lbl_name = QLabel(item_name)
        self.lbl_name.setStyleSheet("color: #171A2B;")
        layout.addWidget(self.lbl_name, stretch=1)

        # Icono de arrastre (drag handle)
        lbl_drag = QLabel("≡")
        lbl_drag.setStyleSheet("color: #64748B; font-weight: bold;")
        layout.addWidget(lbl_drag)

    def _update_eye_icon(self):
        # Usamos texto como placeholder, en un proyecto real se usaría un QIcon
        self.btn_visible.setText("👁" if self.btn_visible.isChecked() else "✖")

    def _on_visibility_clicked(self, checked):
        self._update_eye_icon()
        self.visibility_toggled.emit(checked)


class LayersPanel(QWidget):
    """Panel para administrar las capas del canvas."""

    # Señales emitidas por el panel
    layer_selected = Signal(object)  # Emite el QGraphicsItem correspondiente
    layer_visibility_changed = Signal(object, bool)
    layer_order_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._item_mapping = {}  # QListWidgetItem -> QGraphicsItem
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Cabecera
        header = QLabel("⚙ CAPAS")
        header.setStyleSheet("""
            background-color: #F5F7FA;
            color: #171A2B;
            font-weight: bold;
            font-size: 12px;
            padding: 8px 16px;
            border-bottom: 1px solid #E2E8F0;
        """)
        layout.addWidget(header)

        # Lista de capas
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: none;
                background-color: #FFFFFF;
                outline: none;
            }
            QListWidget::item {
                border-bottom: 1px solid #E2E8F0;
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #EFF6FF;
            }
        """)
        
        self.list_widget.itemSelectionChanged.connect(self._on_item_selected)
        # El modelo emite layoutChanged cuando se hace drop, pero en QListWidget
        # es más sencillo usar las señales del modelo directamente
        self.list_widget.model().rowsMoved.connect(self._on_rows_moved)

        layout.addWidget(self.list_widget)

    def add_layer(self, graphics_item, name: str, is_visible: bool = True):
        """Añade una nueva capa al inicio de la lista (por encima de las demás)."""
        list_item = QListWidgetItem()
        # Darle tamaño al item para que contenga el widget
        list_item.setSizeHint(LayerItemWidget(name).sizeHint())
        
        # Insertar al inicio (capa superior)
        self.list_widget.insertItem(0, list_item)
        
        # Crear y configurar el widget personalizado
        widget = LayerItemWidget(name, is_visible)
        widget.visibility_toggled.connect(
            lambda visible, item=graphics_item: self.layer_visibility_changed.emit(item, visible)
        )
        
        self.list_widget.setItemWidget(list_item, widget)
        self._item_mapping[list_item] = graphics_item

    def clear_layers(self):
        """Limpia todas las capas de la lista."""
        self.list_widget.clear()
        self._item_mapping.clear()

    def remove_layer(self, graphics_item):
        """Elimina una capa específica basada en su QGraphicsItem."""
        for list_item, item in list(self._item_mapping.items()):
            if item == graphics_item:
                row = self.list_widget.row(list_item)
                self.list_widget.takeItem(row)
                del self._item_mapping[list_item]
                break

    def select_layer(self, graphics_item):
        """Selecciona la fila correspondiente al QGraphicsItem especificado."""
        self.list_widget.blockSignals(True)
        self.list_widget.clearSelection()
        for list_item, item in self._item_mapping.items():
            if item == graphics_item:
                list_item.setSelected(True)
                break
        self.list_widget.blockSignals(False)

    def _on_item_selected(self):
        """Maneja la selección desde la interfaz de la lista."""
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            list_item = selected_items[0]
            graphics_item = self._item_mapping.get(list_item)
            if graphics_item:
                self.layer_selected.emit(graphics_item)

    def _on_rows_moved(self, parent, start, end, destination, row):
        """Maneja el reordenamiento drag & drop."""
        self.layer_order_changed.emit()
        
    def get_ordered_items(self) -> list:
        """Devuelve los QGraphicsItems en el orden actual de la lista (de arriba a abajo)."""
        items = []
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            graphics_item = self._item_mapping.get(list_item)
            if graphics_item:
                items.append(graphics_item)
        return items
