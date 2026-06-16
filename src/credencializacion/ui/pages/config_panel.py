from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QDoubleSpinBox, QPushButton, QGroupBox, QSpacerItem, QSizePolicy, QMessageBox, QComboBox
)
from PySide6.QtCore import Qt
from credencializacion.core.settings import AppSettings
from credencializacion.ui.styles import COLORS

class ConfigPanel(QWidget):
    """Panel de Configuración Global de la Aplicación."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("configPanel")
        self.setStyleSheet(f"""
            QWidget#configPanel {{
                background-color: {COLORS['bg_main']};
            }}
            QGroupBox {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                margin-top: 1.5em;
                font-weight: bold;
                padding: 16px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: {COLORS['text']};
            }}
            QLabel {{
                color: {COLORS['text']};
                font-size: 13px;
            }}
            QLabel.help-text {{
                color: {COLORS['text_light']};
                font-size: 12px;
                margin-bottom: 12px;
            }}
        """)
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(24)

        # Título principal
        title = QLabel("Configuración Global")
        title.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {COLORS['text']};")
        layout.addWidget(title)

        desc = QLabel("Los ajustes definidos aquí aplicarán para todo el sistema y todas las plantillas.")
        desc.setStyleSheet(f"color: {COLORS['text_light']}; font-size: 14px;")
        layout.addWidget(desc)

        # Grupo: Orígenes de Impresión
        print_group = QGroupBox("Calibración de Bandeja de Impresión (PVC)")
        print_layout = QVBoxLayout(print_group)
        
        help_text = QLabel("Configura el punto de origen (X, Y) superior izquierdo para las dos ranuras de la charola de tu impresora.\nLos valores están en centímetros.")
        help_text.setProperty("class", "help-text")
        print_layout.addWidget(help_text)

        # Ranura 1
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("<b>Ranura 1 (Superior)</b>"))
        h1.addStretch()
        h1.addWidget(QLabel("Origen X (cm):"))
        self.sp_x1 = self._create_spinbox()
        h1.addWidget(self.sp_x1)
        h1.addSpacing(20)
        h1.addWidget(QLabel("Origen Y (cm):"))
        self.sp_y1 = self._create_spinbox()
        h1.addWidget(self.sp_y1)
        print_layout.addLayout(h1)

        print_layout.addSpacing(16)

        # Ranura 2
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("<b>Ranura 2 (Inferior)</b>"))
        h2.addStretch()
        h2.addWidget(QLabel("Origen X (cm):"))
        self.sp_x2 = self._create_spinbox()
        h2.addWidget(self.sp_x2)
        h2.addSpacing(20)
        h2.addWidget(QLabel("Origen Y (cm):"))
        self.sp_y2 = self._create_spinbox()
        h2.addWidget(self.sp_y2)
        print_layout.addLayout(h2)

        layout.addWidget(print_group)

        # Grupo: Dimensiones de Hoja
        page_group = QGroupBox("Dimensiones del Papel/Charola")
        page_layout = QVBoxLayout(page_group)
        
        help_page = QLabel("Configura el ancho y alto total de la hoja o charola. Esto afecta cómo se centra y ubica el documento a la hora de exportarlo a PDF.")
        help_page.setProperty("class", "help-text")
        page_layout.addWidget(help_page)
        
        h_page = QHBoxLayout()
        h_page.addWidget(QLabel("Tamaño:"))
        self.cb_page_size = QComboBox()
        self.cb_page_size.addItems(["A4 (210 x 297 mm)", "Carta (215.9 x 279.4 mm)", "Oficio/Legal (215.9 x 355.6 mm)", "Personalizado"])
        self.cb_page_size.currentIndexChanged.connect(self._on_page_size_changed)
        h_page.addWidget(self.cb_page_size)
        
        h_page.addSpacing(20)
        h_page.addWidget(QLabel("Ancho (mm):"))
        self.sp_page_w = self._create_spinbox()
        self.sp_page_w.setRange(50, 1000)
        h_page.addWidget(self.sp_page_w)
        
        h_page.addSpacing(20)
        h_page.addWidget(QLabel("Alto (mm):"))
        self.sp_page_h = self._create_spinbox()
        self.sp_page_h.setRange(50, 1000)
        h_page.addWidget(self.sp_page_h)
        
        h_page.addStretch()
        page_layout.addLayout(h_page)
        layout.addWidget(page_group)

        # Acciones
        actions_layout = QHBoxLayout()
        actions_layout.addStretch()
        
        btn_reset = QPushButton("Restaurar Predeterminados")
        btn_reset.setProperty("variant", "secondary")
        btn_reset.clicked.connect(self._reset_settings)
        actions_layout.addWidget(btn_reset)
        
        btn_save = QPushButton("Guardar Configuración")
        btn_save.setProperty("variant", "primary")
        btn_save.clicked.connect(self._save_settings)
        actions_layout.addWidget(btn_save)
        
        layout.addLayout(actions_layout)

        # Spacer al final para empujar todo hacia arriba
        layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

    def _create_spinbox(self) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(-20.0, 50.0)
        sp.setDecimals(2)
        sp.setSingleStep(0.1)
        sp.setFixedWidth(80)
        return sp

    def _load_settings(self) -> None:
        (x1, y1), (x2, y2) = AppSettings.get_print_origins()
        self.sp_x1.setValue(x1)
        self.sp_y1.setValue(y1)
        self.sp_x2.setValue(x2)
        self.sp_y2.setValue(y2)
        
        w_mm, h_mm = AppSettings.get_page_dimensions()
        self.sp_page_w.setValue(w_mm)
        self.sp_page_h.setValue(h_mm)
        
        # Seleccionar combo apropiado
        if abs(w_mm - 210.0) < 0.1 and abs(h_mm - 297.0) < 0.1:
            self.cb_page_size.setCurrentIndex(0)
            self._on_page_size_changed(0)
        elif abs(w_mm - 215.9) < 0.1 and abs(h_mm - 279.4) < 0.1:
            self.cb_page_size.setCurrentIndex(1)
            self._on_page_size_changed(1)
        elif abs(w_mm - 215.9) < 0.1 and abs(h_mm - 355.6) < 0.1:
            self.cb_page_size.setCurrentIndex(2)
            self._on_page_size_changed(2)
        else:
            self.cb_page_size.setCurrentIndex(3)
            self._on_page_size_changed(3)

    def _on_page_size_changed(self, index: int) -> None:
        if index == 0: # A4
            self.sp_page_w.setValue(210.0)
            self.sp_page_h.setValue(297.0)
            self.sp_page_w.setEnabled(False)
            self.sp_page_h.setEnabled(False)
        elif index == 1: # Carta
            self.sp_page_w.setValue(215.9)
            self.sp_page_h.setValue(279.4)
            self.sp_page_w.setEnabled(False)
            self.sp_page_h.setEnabled(False)
        elif index == 2: # Oficio/Legal
            self.sp_page_w.setValue(215.9)
            self.sp_page_h.setValue(355.6)
            self.sp_page_w.setEnabled(False)
            self.sp_page_h.setEnabled(False)
        else: # Personalizado
            self.sp_page_w.setEnabled(True)
            self.sp_page_h.setEnabled(True)

    def _save_settings(self) -> None:
        AppSettings.set_print_origins(
            self.sp_x1.value(), self.sp_y1.value(),
            self.sp_x2.value(), self.sp_y2.value()
        )
        AppSettings.set_page_dimensions(self.sp_page_w.value(), self.sp_page_h.value())
        QMessageBox.information(self, "Configuración Guardada", "Los ajustes se guardaron correctamente en el sistema.")

    def _reset_settings(self) -> None:
        self.sp_x1.setValue(0.0)
        self.sp_y1.setValue(0.0)
        self.sp_x2.setValue(0.0)
        self.sp_y2.setValue(5.4)
        
        self.cb_page_size.setCurrentIndex(0)
        self._on_page_size_changed(0)
