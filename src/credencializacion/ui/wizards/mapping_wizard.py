"""
Wizard de mapeo manual de columnas.
Se activa cuando el fuzzy matching detecta columnas ambiguas.
Permite al usuario confirmar o corregir los mapeos sugeridos.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QHeaderView,
    QWidget, QLineEdit, QMessageBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont


class MappingWizard(QDialog):
    """Ventana de mapeo manual de columnas a atributos estándar."""

    mapping_confirmed = Signal(dict)  # {columna_original: atributo_final}

    # Atributos estándar disponibles
    STANDARD_FIELDS = [
        "", "nombre", "apellido_paterno", "apellido_materno",
        "nombre_completo", "matricula", "curp", "grado", "grupo",
        "turno", "domicilio", "telefono", "email_tutor",
        "fecha_nacimiento", "tipo_sangre", "photo_url",
        "enrollment_code", "access_token",
    ]

    def __init__(self, mapping_result: dict, parent=None):
        """
        Args:
            mapping_result: Dict con claves 'auto_mapped', 'ambiguous', 'unmapped'
                auto_mapped: {col_original: (atributo, score)}
                ambiguous: {col_original: (atributo, score)}
                unmapped: {col_original: None}
        """
        super().__init__(parent)
        self.mapping_result = mapping_result
        self.final_mapping: dict[str, str] = {}
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("Mapeo de Columnas")
        self.setMinimumSize(700, 500)
        self.setStyleSheet("""
            QDialog { background-color: #F5F7FA; }
            QLabel#title { font-size: 18px; font-weight: bold; color: #171A2B; }
            QLabel#subtitle { font-size: 13px; color: #64748B; margin-bottom: 16px; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Título
        title = QLabel("Mapeo de Columnas")
        title.setObjectName("title")
        layout.addWidget(title)

        subtitle = QLabel(
            "Revisa y confirma cómo se mapean las columnas de tu archivo "
            "a los atributos estándar del sistema."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Tabla de mapeo
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Columna Original", "Mejor Coincidencia", "Confianza", "Atributo Final"
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        self._populate_table()
        layout.addWidget(self.table)

        # Crear nuevo atributo
        new_attr_layout = QHBoxLayout()
        new_attr_layout.addWidget(QLabel("Crear nuevo atributo:"))
        self.new_attr_input = QLineEdit()
        self.new_attr_input.setPlaceholderText("nombre_nuevo_atributo")
        new_attr_layout.addWidget(self.new_attr_input)
        add_btn = QPushButton("+ Agregar")
        add_btn.setObjectName("btn_outline")
        add_btn.clicked.connect(self._add_custom_attribute)
        new_attr_layout.addWidget(add_btn)
        layout.addLayout(new_attr_layout)

        # Botones
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setObjectName("btn_outline")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        apply_btn = QPushButton("Aplicar Mapeo")
        apply_btn.setObjectName("btn_primary")
        apply_btn.setStyleSheet("""
            QPushButton#btn_primary {
                background-color: #FB5252; color: white;
                border: none; border-radius: 8px;
                padding: 10px 24px; font-weight: bold; font-size: 14px;
            }
            QPushButton#btn_primary:hover { background-color: #E04848; }
        """)
        apply_btn.clicked.connect(self._apply_mapping)
        btn_layout.addWidget(apply_btn)

        layout.addLayout(btn_layout)

    def _populate_table(self):
        """Llena la tabla con los resultados del mapeo."""
        auto = self.mapping_result.get("auto_mapped", {})
        ambiguous = self.mapping_result.get("ambiguous", {})
        unmapped = self.mapping_result.get("unmapped", {})

        all_columns = {}
        for col, (attr, score) in auto.items():
            all_columns[col] = ("auto", attr, score)
        for col, (attr, score) in ambiguous.items():
            all_columns[col] = ("ambiguous", attr, score)
        for col in unmapped:
            all_columns[col] = ("unmapped", "", 0)

        self.table.setRowCount(len(all_columns))
        self.combo_boxes: dict[int, QComboBox] = {}

        for row, (col, (status, attr, score)) in enumerate(all_columns.items()):
            # Columna original
            item_col = QTableWidgetItem(col)
            item_col.setFlags(item_col.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item_col)

            # Mejor coincidencia
            match_text = attr if attr else "—"
            item_match = QTableWidgetItem(match_text)
            item_match.setFlags(item_match.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, item_match)

            # Confianza (con color)
            score_item = QTableWidgetItem(f"{score}%")
            score_item.setFlags(score_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if status == "auto":
                score_item.setForeground(QColor("#22C55E"))
            elif status == "ambiguous":
                score_item.setForeground(QColor("#F59E0B"))
            else:
                score_item.setForeground(QColor("#EF4444"))
            font = QFont()
            font.setBold(True)
            score_item.setFont(font)
            self.table.setItem(row, 2, score_item)

            # Atributo final (combo editable)
            combo = QComboBox()
            combo.addItems(self.STANDARD_FIELDS)
            if attr and attr in self.STANDARD_FIELDS:
                combo.setCurrentText(attr)
            elif attr:
                combo.addItem(attr)
                combo.setCurrentText(attr)
            combo.setProperty("original_column", col)
            self.combo_boxes[row] = combo
            self.table.setCellWidget(row, 3, combo)

    def _add_custom_attribute(self):
        """Agrega un nuevo atributo personalizado a todos los combos."""
        new_attr = self.new_attr_input.text().strip().lower().replace(" ", "_")
        if not new_attr:
            return
        if new_attr in self.STANDARD_FIELDS:
            QMessageBox.information(
                self, "Atributo existente",
                f"El atributo '{new_attr}' ya existe en la lista."
            )
            return

        self.STANDARD_FIELDS.append(new_attr)
        for combo in self.combo_boxes.values():
            combo.addItem(new_attr)
        self.new_attr_input.clear()

    def _apply_mapping(self):
        """Recoge el mapeo final y emite la señal."""
        self.final_mapping = {}
        for row, combo in self.combo_boxes.items():
            original = combo.property("original_column")
            target = combo.currentText()
            if target:  # Solo incluir mapeos no vacíos
                self.final_mapping[original] = target

        self.mapping_confirmed.emit(self.final_mapping)
        self.accept()

    def get_mapping(self) -> dict[str, str]:
        """Devuelve el mapeo final después de cerrar el diálogo."""
        return self.final_mapping
