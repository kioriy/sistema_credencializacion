from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QPushButton, QGroupBox, QSpacerItem, QSizePolicy, QMessageBox, QComboBox,
    QLineEdit, QFileDialog, QFormLayout, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
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
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QWidget#configContent {{
                background-color: {COLORS['bg_main']};
            }}
        """)
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        # El contenido se monta dentro de un QScrollArea: su alto natural
        # (~980 px) supera el disponible en la ventana mínima (700 px) y en
        # la de arranque (800 px). Sin scroll, QVBoxLayout comprime a los
        # hijos por debajo de su mínimo y las etiquetas de descripción
        # quedan aplastadas y superpuestas con los campos de abajo.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget()
        content.setObjectName("configContent")
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
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
        
        help_text = self._make_help_label(
            "Configura el punto de origen (X, Y) superior izquierdo para las dos ranuras de la charola de tu impresora.\nLos valores están en centímetros.",
            lines=2,
        )
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
        
        help_page = self._make_help_label(
            "Configura el ancho y alto total de la hoja o charola. Esto afecta cómo se centra y ubica el documento a la hora de exportarlo a PDF.",
            lines=2,
        )
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

        # Grupo: Sincronización con Google Sheets
        sheets_group = QGroupBox("Sincronización con Google Sheets — Clientes Negocios")
        sheets_layout = QVBoxLayout(sheets_group)

        help_sheets = self._make_help_label(
            "Sincroniza un documento de Google Sheets donde cada pestaña es un "
            "cliente (negocio) y sus columnas son los atributos de sus "
            "registros. La primera columna de cada pestaña identifica a cada "
            "fila de forma única.",
            lines=3,
        )
        sheets_layout.addWidget(help_sheets)

        sheets_form = QFormLayout()

        cred_row = QHBoxLayout()
        self.sheets_cred_input = QLineEdit()
        self.sheets_cred_input.setReadOnly(True)
        self.sheets_cred_input.setPlaceholderText("credenciales-service-account.json")
        cred_row.addWidget(self.sheets_cred_input)
        btn_browse_cred = QPushButton("Examinar...")
        btn_browse_cred.clicked.connect(self._browse_sheets_credentials)
        cred_row.addWidget(btn_browse_cred)
        sheets_form.addRow("Archivo de credenciales:", cred_row)

        self.sheets_service_email = QLabel("—")
        self.sheets_service_email.setWordWrap(True)
        self.sheets_service_email.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        sheets_form.addRow("Compartir el documento con:", self.sheets_service_email)

        self.sheets_doc_name_input = QLineEdit()
        self.sheets_doc_name_input.setPlaceholderText("clientes negocios")
        sheets_form.addRow("Nombre del documento:", self.sheets_doc_name_input)

        sheets_layout.addLayout(sheets_form)
        layout.addWidget(sheets_group)

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

    @staticmethod
    def _make_help_label(text: str, lines: int = 2) -> QLabel:
        """Crea una etiqueta de descripción con un alto fijo reservado.

        QVBoxLayout no reposiciona correctamente a los hermanos de un QLabel
        con word-wrap cuando solo se ajusta ``minimumHeight``: el layout usa
        el `sizeHint()` de una sola línea para calcular dónde empieza el
        siguiente widget, aunque el label termine ocupando más alto en
        pantalla — el resultado es texto recortado o superpuesto con los
        campos de abajo. ``setFixedHeight`` sí fija la política vertical a
        Fixed, así que el layout usa ese alto como autoritativo.
        """
        lbl = QLabel(text)
        lbl.setProperty("class", "help-text")
        lbl.setWordWrap(True)
        fm = QFontMetrics(lbl.font())
        lbl.setFixedHeight(fm.lineSpacing() * lines + 6)
        return lbl

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

        cred_path = AppSettings.get_sheets_credentials_path()
        self.sheets_cred_input.setText(cred_path)
        self.sheets_doc_name_input.setText(AppSettings.get_sheets_document_name())
        self._refresh_service_email(cred_path)

    def _browse_sheets_credentials(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar credenciales de Google (service account)",
            "", "JSON (*.json);;Todos los archivos (*)",
        )
        if path:
            self.sheets_cred_input.setText(path)
            self._refresh_service_email(path)

    def _refresh_service_email(self, cred_path: str) -> None:
        """Muestra el correo del service account leído del JSON, si es válido."""
        if not cred_path:
            self.sheets_service_email.setText("—")
            return
        try:
            from pathlib import Path
            from credencializacion.adapters.sheets import get_service_account_email
            email = get_service_account_email(Path(cred_path))
            self.sheets_service_email.setText(email or "—")
        except Exception as e:  # noqa: BLE001
            self.sheets_service_email.setText(f"⚠ No se pudo leer el archivo: {e}")

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
        AppSettings.set_sheets_config(
            self.sheets_cred_input.text().strip(),
            self.sheets_doc_name_input.text().strip() or "clientes negocios",
        )
        QMessageBox.information(self, "Configuración Guardada", "Los ajustes se guardaron correctamente en el sistema.")

    def _reset_settings(self) -> None:
        self.sp_x1.setValue(0.0)
        self.sp_y1.setValue(0.0)
        self.sp_x2.setValue(0.0)
        self.sp_y2.setValue(5.4)

        self.cb_page_size.setCurrentIndex(0)
        self._on_page_size_changed(0)

        self.sheets_cred_input.setText("")
        self.sheets_doc_name_input.setText("")
        self.sheets_service_email.setText("—")
