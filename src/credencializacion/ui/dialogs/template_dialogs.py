from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)
from PySide6.QtCore import Qt
from credencializacion.db.engine import get_session
from credencializacion.db.models import Cliente, Plantilla
from credencializacion.ui.styles import COLORS

class SaveTemplateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Guardar Plantilla")
        self.setFixedSize(400, 200)
        self.setStyleSheet(f"background-color: {COLORS['bg_main']}; color: {COLORS['text']};")
        
        self.cliente_id: int | None = None
        self.template_name: str = ""
        
        self._setup_ui()
        self._load_clientes()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Cliente
        layout.addWidget(QLabel("Seleccionar Cliente:"))
        self.cb_clientes = QComboBox()
        self.cb_clientes.setStyleSheet(f"background-color: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 5px;")
        layout.addWidget(self.cb_clientes)
        
        # Nombre de la Plantilla
        layout.addWidget(QLabel("Nombre de la Plantilla:"))
        self.le_nombre = QLineEdit()
        self.le_nombre.setStyleSheet(f"background-color: {COLORS['bg_card']}; border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 5px;")
        layout.addWidget(self.le_nombre)
        
        # Botones
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setProperty("variant", "secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        
        btn_save = QPushButton("Guardar")
        btn_save.setProperty("variant", "primary")
        btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(btn_save)
        
        layout.addLayout(btn_layout)

    def _load_clientes(self):
        with get_session() as session:
            clientes = session.query(Cliente).all()
            for c in clientes:
                self.cb_clientes.addItem(c.nombre, c.id)
                
    def _on_save(self):
        name = self.le_nombre.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "El nombre de la plantilla no puede estar vacío.")
            return
            
        cliente_id = self.cb_clientes.currentData()
        if cliente_id is None:
            QMessageBox.warning(self, "Error", "Debes seleccionar un cliente. Si no hay clientes registrados, sincroniza desde el Panel de Control.")
            return
            
        self.cliente_id = cliente_id
        self.template_name = name
        self.accept()

class OpenTemplateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Abrir Plantilla")
        self.resize(600, 400)
        self.setStyleSheet(f"background-color: {COLORS['bg_main']}; color: {COLORS['text']};")
        
        self.selected_plantilla_id: int | None = None
        
        self._setup_ui()
        self._load_templates()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID", "Nombre", "Cliente"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setStyleSheet(f"background-color: {COLORS['bg_card']}; border: 1px solid {COLORS['border']};")
        self.table.doubleClicked.connect(self._on_open)
        layout.addWidget(self.table)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setProperty("variant", "secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        
        btn_open = QPushButton("Abrir")
        btn_open.setProperty("variant", "primary")
        btn_open.clicked.connect(self._on_open)
        btn_layout.addWidget(btn_open)
        
        layout.addLayout(btn_layout)

    def _load_templates(self):
        with get_session() as session:
            plantillas = session.query(Plantilla).join(Cliente).all()
            self.table.setRowCount(len(plantillas))
            for i, p in enumerate(plantillas):
                item_id = QTableWidgetItem(str(p.id))
                item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, 0, item_id)
                self.table.setItem(i, 1, QTableWidgetItem(p.nombre))
                self.table.setItem(i, 2, QTableWidgetItem(p.cliente.nombre if p.cliente else "N/A"))

    def _on_open(self):
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Error", "Selecciona una plantilla para abrir.")
            return
            
        row = selected[0].row()
        self.selected_plantilla_id = int(self.table.item(row, 0).text())
        self.accept()


