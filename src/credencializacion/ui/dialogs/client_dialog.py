"""
Diálogo de CRUD para clientes/organizaciones.
Permite crear, editar y eliminar clientes del sistema.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QFileDialog,
    QDialogButtonBox, QGroupBox, QMessageBox,
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QPixmap

from credencializacion.db.models import Cliente
from credencializacion.db.engine import DatabaseSession


class ClientDialog(QDialog):
    """Diálogo para crear o editar un cliente."""

    client_saved = Signal(int)  # ID del cliente guardado

    TIPOS = ["escuela", "empresa", "gobierno", "otro"]

    def __init__(self, client: Cliente | None = None, parent=None):
        super().__init__(parent)
        self.client = client
        self.is_editing = client is not None
        self._setup_ui()
        if self.is_editing:
            self._load_client()

    def _setup_ui(self):
        title = "Editar Cliente" if self.is_editing else "Nuevo Cliente"
        self.setWindowTitle(title)
        self.setMinimumWidth(500)
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; }
            QGroupBox {
                font-weight: bold; color: #171A2B;
                border: 1px solid #E2E8F0; border-radius: 8px;
                margin-top: 16px; padding-top: 20px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 16px; padding: 0 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Título
        title_label = QLabel(title)
        title_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #171A2B;"
        )
        layout.addWidget(title_label)

        # Datos básicos
        basic_group = QGroupBox("Información General")
        form = QFormLayout(basic_group)
        form.setSpacing(12)

        self.nombre_input = QLineEdit()
        self.nombre_input.setPlaceholderText("Nombre de la organización")
        form.addRow("Nombre:", self.nombre_input)

        self.tipo_combo = QComboBox()
        self.tipo_combo.addItems(self.TIPOS)
        form.addRow("Tipo:", self.tipo_combo)

        # Logo
        logo_layout = QHBoxLayout()
        self.logo_path_input = QLineEdit()
        self.logo_path_input.setPlaceholderText("Ruta al logo (opcional)")
        self.logo_path_input.setReadOnly(True)
        logo_layout.addWidget(self.logo_path_input)
        logo_btn = QPushButton("Examinar...")
        logo_btn.clicked.connect(self._browse_logo)
        logo_layout.addWidget(logo_btn)
        form.addRow("Logo:", logo_layout)

        layout.addWidget(basic_group)

        # Configuración API
        api_group = QGroupBox("Conexión API (Opcional)")
        api_form = QFormLayout(api_group)
        api_form.setSpacing(12)

        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Token de la escuela en miescuela.net")
        api_form.addRow("Token:", self.token_input)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("X-Credential-Key para API export")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_form.addRow("API Key:", self.api_key_input)

        self.api_url_input = QLineEdit()
        self.api_url_input.setPlaceholderText("https://app.miescuela.net")
        api_form.addRow("URL Base:", self.api_url_input)

        layout.addWidget(api_group)

        # Botones
        button_box = QDialogButtonBox()
        save_btn = button_box.addButton("Guardar", QDialogButtonBox.ButtonRole.AcceptRole)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #FB5252; color: white; border: none;
                border-radius: 8px; padding: 10px 24px;
                font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #E04848; }
        """)
        cancel_btn = button_box.addButton(
            "Cancelar", QDialogButtonBox.ButtonRole.RejectRole
        )
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #F5F7FA; color: #171A2B; border: 1px solid #E2E8F0;
                border-radius: 8px; padding: 10px 24px; font-size: 14px;
            }
            QPushButton:hover { background-color: #E2E8F0; }
        """)

        button_box.accepted.connect(self._save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _browse_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar logo",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.svg);;Todos (*)",
        )
        if path:
            self.logo_path_input.setText(path)

    def _load_client(self):
        """Carga los datos del cliente existente en el formulario."""
        if not self.client:
            return
        self.nombre_input.setText(self.client.nombre)
        idx = self.tipo_combo.findText(self.client.tipo)
        if idx >= 0:
            self.tipo_combo.setCurrentIndex(idx)
        if self.client.logo_path:
            self.logo_path_input.setText(self.client.logo_path)
        if self.client.token:
            self.token_input.setText(self.client.token)
        if self.client.api_key:
            self.api_key_input.setText(self.client.api_key)
        if self.client.api_base_url:
            self.api_url_input.setText(self.client.api_base_url)

    def _save(self):
        """Guarda el cliente en la base de datos."""
        nombre = self.nombre_input.text().strip()
        if not nombre:
            QMessageBox.warning(
                self, "Campo requerido", "El nombre del cliente es obligatorio."
            )
            return

        with DatabaseSession() as session:
            if self.is_editing and self.client:
                client = session.get(Cliente, self.client.id)
                if not client:
                    QMessageBox.critical(
                        self, "Error", "Cliente no encontrado en la base de datos."
                    )
                    return
            else:
                client = Cliente()
                session.add(client)

            client.nombre = nombre
            client.tipo = self.tipo_combo.currentText()
            client.logo_path = self.logo_path_input.text() or None
            client.token = self.token_input.text().strip() or None
            client.api_key = self.api_key_input.text().strip() or None
            client.api_base_url = self.api_url_input.text().strip() or None

            session.flush()
            client_id = client.id

        self.client_saved.emit(client_id)
        self.accept()
