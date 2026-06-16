"""
Diálogo de configuración general del sistema.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QCheckBox, QSpinBox,
    QTabWidget, QWidget, QGroupBox, QFileDialog,
)
from PySide6.QtCore import Signal


class SettingsDialog(QDialog):
    """Configuración general del sistema de credencialización."""

    settings_saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración")
        self.setMinimumSize(600, 500)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; }
            QGroupBox {
                font-weight: bold; color: #171A2B;
                border: 1px solid #E2E8F0; border-radius: 8px;
                margin-top: 16px; padding-top: 20px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 16px; padding: 0 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("⚙ Configuración")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #171A2B;"
        )
        layout.addWidget(title)

        # Tabs
        tabs = QTabWidget()

        # Tab: General
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)

        # Impresión
        print_group = QGroupBox("Impresión")
        print_form = QFormLayout(print_group)

        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["Carta (Letter)", "A4", "Oficio (Legal)"])
        print_form.addRow("Tamaño de hoja:", self.page_size_combo)

        self.cards_per_page = QSpinBox()
        self.cards_per_page.setRange(1, 4)
        self.cards_per_page.setValue(2)
        print_form.addRow("Credenciales por hoja:", self.cards_per_page)

        self.auto_print = QCheckBox("Enviar a impresora automáticamente")
        self.auto_print.setChecked(True)
        print_form.addRow("", self.auto_print)

        general_layout.addWidget(print_group)

        # Caché
        cache_group = QGroupBox("Caché de Imágenes")
        cache_form = QFormLayout(cache_group)

        self.max_image_size = QSpinBox()
        self.max_image_size.setRange(200, 2000)
        self.max_image_size.setValue(800)
        self.max_image_size.setSuffix(" px")
        cache_form.addRow("Tamaño máximo:", self.max_image_size)

        self.auto_download = QCheckBox("Descargar fotos al importar")
        self.auto_download.setChecked(True)
        cache_form.addRow("", self.auto_download)

        cache_dir_layout = QHBoxLayout()
        self.cache_dir_input = QLineEdit()
        self.cache_dir_input.setReadOnly(True)
        self.cache_dir_input.setPlaceholderText("data/image_cache/")
        cache_dir_layout.addWidget(self.cache_dir_input)
        cache_browse = QPushButton("Cambiar...")
        cache_browse.clicked.connect(self._browse_cache_dir)
        cache_dir_layout.addWidget(cache_browse)
        cache_form.addRow("Directorio:", cache_dir_layout)

        general_layout.addWidget(cache_group)
        general_layout.addStretch()
        tabs.addTab(general_tab, "General")

        # Tab: Apariencia
        appearance_tab = QWidget()
        appearance_layout = QVBoxLayout(appearance_tab)

        theme_group = QGroupBox("Tema")
        theme_form = QFormLayout(theme_group)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Claro", "Oscuro", "Sistema"])
        theme_form.addRow("Tema:", self.theme_combo)

        self.default_font = QComboBox()
        self.default_font.addItems(["Inter", "Roboto", "Arial", "Helvetica"])
        theme_form.addRow("Fuente predeterminada:", self.default_font)

        appearance_layout.addWidget(theme_group)
        appearance_layout.addStretch()
        tabs.addTab(appearance_tab, "Apariencia")

        # Tab: Google Sheets
        sheets_tab = QWidget()
        sheets_layout = QVBoxLayout(sheets_tab)

        sheets_group = QGroupBox("Credenciales de Google")
        sheets_form = QFormLayout(sheets_group)

        cred_layout = QHBoxLayout()
        self.cred_path_input = QLineEdit()
        self.cred_path_input.setPlaceholderText("credentials.json")
        self.cred_path_input.setReadOnly(True)
        cred_layout.addWidget(self.cred_path_input)
        cred_browse = QPushButton("Examinar...")
        cred_browse.clicked.connect(self._browse_credentials)
        cred_layout.addWidget(cred_browse)
        sheets_form.addRow("Archivo de credenciales:", cred_layout)

        sheets_form.addRow("", QLabel(
            "Descarga el archivo JSON de la cuenta de servicio\n"
            "desde Google Cloud Console."
        ))

        sheets_layout.addWidget(sheets_group)
        sheets_layout.addStretch()
        tabs.addTab(sheets_tab, "Google Sheets")

        layout.addWidget(tabs)

        # Botones
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #F5F7FA; color: #171A2B;
                border: 1px solid #E2E8F0; border-radius: 8px;
                padding: 10px 24px; font-size: 14px;
            }
            QPushButton:hover { background-color: #E2E8F0; }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Guardar Configuración")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #FB5252; color: white; border: none;
                border-radius: 8px; padding: 10px 24px;
                font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #E04848; }
        """)
        save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _browse_cache_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Seleccionar directorio de caché"
        )
        if path:
            self.cache_dir_input.setText(path)

    def _browse_credentials(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar credenciales Google",
            "", "JSON (*.json);;Todos (*)",
        )
        if path:
            self.cred_path_input.setText(path)

    def _save_settings(self):
        self.settings_saved.emit()
        self.accept()
