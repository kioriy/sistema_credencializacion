"""
Wizard de importación de datos.
Guía al usuario paso a paso: selección de origen → preview → mapeo → importación.
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QTableWidget, QTableWidgetItem,
    QRadioButton, QButtonGroup, QLineEdit, QGroupBox,
    QProgressBar, QHeaderView, QComboBox, QCheckBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class SourceSelectionPage(QWizardPage):
    """Paso 1: Seleccionar origen de datos."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Seleccionar Origen de Datos")
        self.setSubTitle(
            "Elige de dónde importar los registros para las credenciales."
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        self.source_group = QButtonGroup(self)

        # Opción: Archivo CSV/Excel
        file_group = QGroupBox("Archivo Local")
        file_layout = QVBoxLayout(file_group)
        self.radio_file = QRadioButton("Importar desde archivo CSV o Excel")
        self.radio_file.setChecked(True)
        self.source_group.addButton(self.radio_file, 0)
        file_layout.addWidget(self.radio_file)

        file_select_layout = QHBoxLayout()
        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText("Selecciona un archivo...")
        self.file_path_input.setReadOnly(True)
        file_select_layout.addWidget(self.file_path_input)
        browse_btn = QPushButton("Examinar...")
        browse_btn.clicked.connect(self._browse_file)
        file_select_layout.addWidget(browse_btn)
        file_layout.addLayout(file_select_layout)
        layout.addWidget(file_group)

        # Opción: API miescuela.net
        api_group = QGroupBox("API miescuela.net")
        api_layout = QVBoxLayout(api_group)
        self.radio_api = QRadioButton("Conectar directamente a la plataforma")
        self.source_group.addButton(self.radio_api, 1)
        api_layout.addWidget(self.radio_api)
        api_layout.addWidget(QLabel(
            "Se usará la configuración del cliente seleccionado (API Key y URL base)."
        ))
        layout.addWidget(api_group)

        # Opción: Google Sheets
        sheets_group = QGroupBox("Google Sheets")
        sheets_layout = QVBoxLayout(sheets_group)
        self.radio_sheets = QRadioButton("Importar desde Google Sheets")
        self.source_group.addButton(self.radio_sheets, 2)
        sheets_layout.addWidget(self.radio_sheets)

        sheet_url_layout = QHBoxLayout()
        sheet_url_layout.addWidget(QLabel("URL del Sheet:"))
        self.sheet_url_input = QLineEdit()
        self.sheet_url_input.setPlaceholderText(
            "https://docs.google.com/spreadsheets/d/..."
        )
        sheet_url_layout.addWidget(self.sheet_url_input)
        sheets_layout.addLayout(sheet_url_layout)
        layout.addWidget(sheets_group)

        layout.addStretch()

        # Registrar campos para validación
        self.registerField("source_type*", self.radio_file)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar archivo de datos",
            "",
            "Archivos de datos (*.csv *.xlsx *.xls);;Todos los archivos (*)",
        )
        if path:
            self.file_path_input.setText(path)

    def get_source_type(self) -> int:
        return self.source_group.checkedId()

    def get_file_path(self) -> Path | None:
        text = self.file_path_input.text()
        return Path(text) if text else None

    def get_sheet_url(self) -> str:
        return self.sheet_url_input.text().strip()

    def isComplete(self) -> bool:
        source = self.source_group.checkedId()
        if source == 0:
            return bool(self.file_path_input.text())
        elif source == 1:
            return True
        elif source == 2:
            return bool(self.sheet_url_input.text())
        return False


class DataPreviewPage(QWizardPage):
    """Paso 2: Vista previa de los datos importados y mapeo de columnas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Vista Previa de Datos")
        self.setSubTitle(
            "Verifica los datos y mapea las columnas a los atributos del sistema."
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Info
        self.info_label = QLabel("Cargando datos...")
        self.info_label.setStyleSheet("color: #64748B; font-size: 13px;")
        layout.addWidget(self.info_label)

        # Tabla de preview
        self.preview_table = QTableWidget()
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.verticalHeader().setVisible(False)
        self.preview_table.setMaximumHeight(250)
        layout.addWidget(self.preview_table)

        # Mapeo
        mapping_label = QLabel("Mapeo de Columnas")
        mapping_label.setFont(QFont("Inter", 14, QFont.Weight.Bold))
        layout.addWidget(mapping_label)

        self.mapping_table = QTableWidget()
        self.mapping_table.setColumnCount(3)
        self.mapping_table.setHorizontalHeaderLabels([
            "Columna Original", "Confianza", "Mapear a..."
        ])
        self.mapping_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.mapping_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.mapping_table.setAlternatingRowColors(True)
        self.mapping_table.verticalHeader().setVisible(False)
        layout.addWidget(self.mapping_table)

        self._data: list[dict] = []
        self._mapping: dict[str, str] = {}

    def set_data(self, records: list[dict], mapping_result: dict):
        """Carga los datos y resultados del mapeo en la UI."""
        self._data = records

        # Preview table (primeras 5 filas)
        if records:
            columns = list(records[0].keys())
            preview = records[:5]
            self.preview_table.setColumnCount(len(columns))
            self.preview_table.setHorizontalHeaderLabels(columns)
            self.preview_table.setRowCount(len(preview))
            for row, record in enumerate(preview):
                for col, key in enumerate(columns):
                    item = QTableWidgetItem(str(record.get(key, "")))
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.preview_table.setItem(row, col, item)
            self.info_label.setText(
                f"Se encontraron {len(records)} registros con {len(columns)} columnas."
            )

        # Mapping table
        all_mappings = {}
        for col, (attr, score) in mapping_result.get("auto_mapped", {}).items():
            all_mappings[col] = (attr, score, "auto")
        for col, (attr, score) in mapping_result.get("ambiguous", {}).items():
            all_mappings[col] = (attr, score, "ambiguous")
        for col in mapping_result.get("unmapped", {}):
            all_mappings[col] = ("", 0, "unmapped")

        self.mapping_table.setRowCount(len(all_mappings))
        self._combos: dict[str, QComboBox] = {}

        standard_attrs = [
            "", "nombre", "apellido_paterno", "apellido_materno",
            "nombre_completo", "matricula", "curp", "grado", "grupo",
            "turno", "domicilio", "telefono", "email_tutor",
            "fecha_nacimiento", "tipo_sangre", "photo_url",
        ]

        for row, (col, (attr, score, status)) in enumerate(all_mappings.items()):
            # Columna original
            self.mapping_table.setItem(row, 0, QTableWidgetItem(col))

            # Score con color
            score_item = QTableWidgetItem(f"{score}%")
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if status == "auto":
                score_item.setForeground(Qt.GlobalColor.darkGreen)
            elif status == "ambiguous":
                score_item.setForeground(Qt.GlobalColor.darkYellow)
            else:
                score_item.setForeground(Qt.GlobalColor.red)
            self.mapping_table.setItem(row, 1, score_item)

            # Combo
            combo = QComboBox()
            combo.addItems(standard_attrs)
            if attr:
                combo.setCurrentText(attr)
            self._combos[col] = combo
            self.mapping_table.setCellWidget(row, 2, combo)

    def get_final_mapping(self) -> dict[str, str]:
        """Devuelve el mapeo final seleccionado por el usuario."""
        mapping = {}
        for col, combo in self._combos.items():
            target = combo.currentText()
            if target:
                mapping[col] = target
        return mapping


class CompositeFieldsPage(QWizardPage):
    """Paso 3: Configuración de campos compuestos (QR, nombre completo)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Campos Compuestos")
        self.setSubTitle(
            "Configura campos que se generan combinando otros datos."
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # QR Data
        qr_group = QGroupBox("Datos del Código QR")
        qr_layout = QVBoxLayout(qr_group)
        self.qr_check = QCheckBox("Generar código QR automáticamente")
        self.qr_check.setChecked(True)
        qr_layout.addWidget(self.qr_check)

        qr_url_layout = QHBoxLayout()
        qr_url_layout.addWidget(QLabel("Plantilla URL:"))
        self.qr_url_template = QLineEdit()
        self.qr_url_template.setText(
            "https://app.miescuela.net/q/{access_token}"
        )
        self.qr_url_template.setPlaceholderText(
            "https://example.com/q/{access_token}"
        )
        qr_url_layout.addWidget(self.qr_url_template)
        qr_layout.addLayout(qr_url_layout)

        qr_layout.addWidget(QLabel(
            "Usa {campo} para insertar valores del registro. "
            "Ej: {access_token}, {matricula}"
        ))
        layout.addWidget(qr_group)

        # Nombre completo
        name_group = QGroupBox("Nombre Completo")
        name_layout = QVBoxLayout(name_group)
        self.name_check = QCheckBox("Generar nombre completo automáticamente")
        self.name_check.setChecked(True)
        name_layout.addWidget(self.name_check)
        name_layout.addWidget(QLabel(
            "Se combinará: {nombre} {apellido_paterno} {apellido_materno}"
        ))
        layout.addWidget(name_group)

        # Descarga de imágenes
        img_group = QGroupBox("Caché de Imágenes")
        img_layout = QVBoxLayout(img_group)
        self.img_check = QCheckBox("Descargar fotos automáticamente")
        self.img_check.setChecked(True)
        img_layout.addWidget(self.img_check)
        img_layout.addWidget(QLabel(
            "Las fotos se descargarán localmente para evitar latencia al imprimir."
        ))
        layout.addWidget(img_group)

        layout.addStretch()


class ConfirmationPage(QWizardPage):
    """Paso 4: Confirmación y progreso de importación."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Confirmar Importación")
        self.setSubTitle("Revisa el resumen y procede con la importación.")

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        self.summary_label = QLabel("Resumen de la importación:")
        self.summary_label.setFont(QFont("Inter", 14, QFont.Weight.Bold))
        layout.addWidget(self.summary_label)

        self.details_label = QLabel()
        self.details_label.setWordWrap(True)
        self.details_label.setStyleSheet("color: #64748B; font-size: 13px;")
        layout.addWidget(self.details_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                text-align: center;
                height: 24px;
            }
            QProgressBar::chunk {
                background-color: #FB5252;
                border-radius: 7px;
            }
        """)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #22C55E; font-weight: bold;")
        layout.addWidget(self.status_label)

        layout.addStretch()

    def set_summary(self, total_records: int, mapped_fields: int,
                    download_images: bool):
        self.details_label.setText(
            f"• Registros a importar: {total_records}\n"
            f"• Campos mapeados: {mapped_fields}\n"
            f"• Descargar imágenes: {'Sí' if download_images else 'No'}\n"
        )

    def set_progress(self, current: int, total: int):
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def set_completed(self, count: int):
        self.status_label.setText(
            f"✅ Importación completada: {count} registros procesados."
        )


class ImportWizard(QWizard):
    """Wizard completo de importación de datos."""

    import_completed = Signal(int)  # Cantidad de registros importados

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Importar Datos")
        self.setMinimumSize(750, 550)
        self.setStyleSheet("""
            QWizard { background-color: #F5F7FA; }
            QWizardPage { background-color: #FFFFFF; border-radius: 8px; }
        """)

        # Páginas
        self.source_page = SourceSelectionPage()
        self.preview_page = DataPreviewPage()
        self.composite_page = CompositeFieldsPage()
        self.confirm_page = ConfirmationPage()

        self.addPage(self.source_page)
        self.addPage(self.preview_page)
        self.addPage(self.composite_page)
        self.addPage(self.confirm_page)

        # Botones personalizados
        self.setButtonText(QWizard.WizardButton.NextButton, "Siguiente →")
        self.setButtonText(QWizard.WizardButton.BackButton, "← Anterior")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Importar")
        self.setButtonText(QWizard.WizardButton.CancelButton, "Cancelar")
