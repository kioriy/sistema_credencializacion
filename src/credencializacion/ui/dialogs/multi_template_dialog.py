"""
Diálogo modal de configuración de multiplantillaje (Dialogo_Multiplantillaje).

Permite, para un Cliente, listar sus plantillas/diseños, seleccionar varias y
abrir una ventana flotante de asignación donde, por cada plantilla, se define un
Atributo y un valor y se marca la Plantilla_Por_Defecto.

- Tarea 6.1 (base): apertura modal recibiendo `cliente_id`, carga de plantillas
  vía `MultiTemplateRepository`, listado del nombre visible y manejo del fallo
  de carga manteniendo deshabilitado el guardado.
- Tarea 6.2 (esta): selección de una o más plantillas (Req 2.3), advertencia de
  "se requieren al menos dos plantillas" (Req 2.4), ventana flotante de
  asignación por plantilla con selector de Atributo poblado desde
  `available_attributes` (Req 3.2) y entrada manual si no hay atributos
  (Req 3.3, 7.4), campo de valor (Req 3.1), marca de Plantilla_Por_Defecto y
  representación "Atributo igual a valor asigna Plantilla_Destino" (Req 3.5).

Las validaciones de guardado (duplicados, longitudes, cliente ajeno,
orientación/dimensiones) corresponden a la tarea 6.3; el modo edición y la
persistencia a la 6.4; y la asignación global de diseño único (Decisión 5) a la
tarea 6.5: cuando el cliente tiene una sola plantilla no se abre la ventana de
reglas; esa plantilla queda como Plantilla_Por_Defecto y la configuración se
guarda sin reglas (Req 3.8, 5.7).
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox,
    QComboBox, QLineEdit, QRadioButton, QButtonGroup, QFrame,
    QScrollArea, QWidget,
)
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QPixmap

from credencializacion.db.engine import DatabaseSession
from credencializacion.db.repositories import MultiTemplateRepository
from credencializacion.services.template_assignment import CondicionDTO, ReglaDTO
from credencializacion.services.template_validators import (
    detect_duplicate_pairs,
    detect_template_differences,
    validate_atributo_length,
    validate_condiciones,
    validate_single_default,
    validate_valor_length,
)


class TemplateAssignmentWindow(QDialog):
    """Ventana flotante de asignación de reglas por plantilla (Req 3.x).

    Recibe el conjunto de plantillas seleccionadas y los Atributos_Disponibles
    del cliente. Por cada plantilla muestra una fila con: selector de Atributo
    (poblado desde `available_attributes`, Req 3.2; con entrada manual si no hay
    atributos, Req 3.3/7.4), campo de valor (Req 3.1), una marca de
    Plantilla_Por_Defecto (radio exclusivo) y una vista previa textual de la
    forma "Atributo igual a valor asigna Plantilla_Destino" (Req 3.5).

    Al aceptar, expone `assignments` (lista de dicts) y `default_template_id`
    para que el diálogo principal los valide (tarea 6.3) y persista (tarea 6.4).
    """

    def __init__(
        self,
        templates: list[dict],
        available_attributes: list[str],
        initial_conditions: dict[int, list[dict]] | None = None,
        initial_default_id: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        # Cada plantilla: dict con id, nombre, orientacion, ancho, alto, recursos.
        self._templates = templates
        self._available_attributes = list(available_attributes)
        # Condiciones precargadas por plantilla (modo edición / reapertura):
        # `initial_conditions` mapea `plantilla_id -> [{"atributo","valor"}, ...]`.
        self._initial_conditions = initial_conditions or {}
        self._initial_default_id = initial_default_id
        # Si no hay atributos disponibles, se permite entrada manual (Req 7.4) y
        # se informa que no existen atributos (Req 3.3).
        self._attributes_empty = len(self._available_attributes) == 0

        # Estructuras por fila para recolectar la asignación al aceptar.
        self._rows: list[dict] = []
        # Resultados publicados tras aceptar.
        self.assignments: list[dict] = []
        self.default_template_id: int | None = None

        # Grupo exclusivo para la marca de Plantilla_Por_Defecto (Req 3.8).
        self._default_group = QButtonGroup(self)
        self._default_group.setExclusive(True)

        self.setModal(True)
        self._setup_ui()

    # ------------------------------------------------------------------ UI ---
    def _setup_ui(self):
        self.setWindowTitle("Asignación de plantillas por atributo")
        self.setMinimumWidth(620)
        self.setMinimumHeight(420)
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; }
            QFrame#ruleCard {
                border: 1px solid #E2E8F0; border-radius: 8px;
                background-color: #FFFFFF;
            }
            QComboBox, QLineEdit {
                border: 1px solid #E2E8F0; border-radius: 6px;
                padding: 6px 8px; background-color: #FFFFFF;
            }
            QComboBox:focus, QLineEdit:focus { border: 1px solid #FB5252; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Asignación de plantillas por atributo")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #171A2B;"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "Define, para cada plantilla, el atributo y el valor que disparan su "
            "asignación, y marca la plantilla por defecto."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #64748B; font-size: 13px;")
        layout.addWidget(subtitle)

        # Aviso cuando no existen Atributos_Disponibles (Req 3.3 + 7.4).
        if self._attributes_empty:
            no_attrs = QLabel(
                "Este cliente no tiene atributos disponibles. Escribe "
                "manualmente el nombre del atributo en cada plantilla."
            )
            no_attrs.setWordWrap(True)
            no_attrs.setStyleSheet(
                "color: #B45309; background-color: #FEF3C7; "
                "border-radius: 6px; padding: 8px; font-size: 12px;"
            )
            layout.addWidget(no_attrs)

        # Área desplazable con una tarjeta por plantilla seleccionada.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self._rows_layout = QVBoxLayout(container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(12)

        for index, template in enumerate(self._templates):
            self._rows_layout.addWidget(self._build_rule_card(index, template))

        self._rows_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

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

        accept_btn = QPushButton("Aceptar")
        accept_btn.setStyleSheet("""
            QPushButton {
                background-color: #FB5252; color: white; border: none;
                border-radius: 8px; padding: 10px 24px;
                font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #E04848; }
        """)
        accept_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(accept_btn)

        layout.addLayout(btn_layout)

    def _build_rule_card(self, index: int, template: dict) -> QFrame:
        """Construye la tarjeta de asignación de una plantilla.

        Incluye: vista previa del diseño base (Req 2.3/2.4), marca de plantilla
        por defecto (Req 3.8), una o más condiciones atributo+valor en conjunción
        (Req 3.1-3.3) con botones para agregar/quitar, y una representación
        textual de la regla como conjunción (Req 3.7).
        """
        card = QFrame()
        card.setObjectName("ruleCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)

        nombre = template["nombre"]

        # Encabezado: vista previa + nombre + marca de por defecto (Req 3.8).
        header = QHBoxLayout()
        header.setSpacing(10)

        preview = self._build_preview_widget(template)
        header.addWidget(preview)

        name_label = QLabel(nombre)
        name_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #171A2B;"
        )
        header.addWidget(name_label)
        header.addStretch()

        default_radio = QRadioButton("Plantilla por defecto")
        default_radio.setStyleSheet("color: #475569; font-size: 12px;")
        if self._initial_default_id is not None:
            default_radio.setChecked(template["id"] == self._initial_default_id)
        else:
            default_radio.setChecked(index == 0)
        self._default_group.addButton(default_radio, index)
        header.addWidget(default_radio)
        card_layout.addLayout(header)

        # Contenedor de condiciones (cada una: atributo + valor + quitar).
        cond_container = QWidget()
        cond_layout = QVBoxLayout(cond_container)
        cond_layout.setContentsMargins(0, 0, 0, 0)
        cond_layout.setSpacing(6)
        card_layout.addWidget(cond_container)

        # Vista previa textual "atributo igual a valor [Y ...] asigna Plantilla".
        preview_label = QLabel()
        preview_label.setWordWrap(True)
        preview_label.setStyleSheet("color: #64748B; font-size: 12px;")
        card_layout.addWidget(preview_label)

        # Botón para agregar una condición más (conjunción AND, Req 3.3).
        add_btn = QPushButton("+ Agregar condición (Y)")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #F5F7FA; color: #1D4ED8;
                border: 1px dashed #93C5FD; border-radius: 6px;
                padding: 6px 10px; font-size: 12px;
            }
            QPushButton:hover { background-color: #EFF6FF; }
        """)
        card_layout.addWidget(add_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        row = {
            "plantilla_id": template["id"],
            "nombre": nombre,
            "default_radio": default_radio,
            "preview_label": preview_label,
            "cond_layout": cond_layout,
            "cond_rows": [],
        }
        self._rows.append(row)

        add_btn.clicked.connect(lambda _, r=row: self._add_condition_row(r))

        # Precarga de condiciones (modo edición/reapertura). Si no hay ninguna,
        # se añade una condición vacía para que el usuario pueda completarla.
        iniciales = self._initial_conditions.get(template["id"], [])
        if iniciales:
            for cond in iniciales:
                self._add_condition_row(
                    row,
                    atributo=(cond.get("atributo") or "").strip(),
                    valor=(cond.get("valor") or "").strip(),
                )
        else:
            self._add_condition_row(row)

        self._update_preview(row)
        return card

    def _build_preview_widget(self, template: dict) -> QLabel:
        """Crea un thumbnail del diseño base de la plantilla (Req 2.3/2.4).

        Usa la imagen de fondo de `recursos` (`fondo_frente` o, en su defecto,
        `fondo_vuelta`). Si no hay imagen o no se puede cargar, muestra un
        indicador de "vista previa no disponible" (Req 2.4).
        """
        from pathlib import Path

        label = QLabel()
        label.setFixedSize(64, 40)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "border: 1px solid #E2E8F0; border-radius: 4px; "
            "background-color: #F8FAFC; color: #94A3B8; font-size: 9px;"
        )

        recursos = template.get("recursos") or {}
        ruta = recursos.get("fondo_frente") or recursos.get("fondo_vuelta")
        pixmap = None
        if ruta and Path(ruta).exists():
            candidate = QPixmap(str(ruta))
            if not candidate.isNull():
                pixmap = candidate.scaled(
                    64, 40,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
        if pixmap is not None:
            label.setPixmap(pixmap)
            label.setToolTip("Vista previa del diseño base")
        else:
            label.setText("sin\nvista")
            label.setToolTip("Vista previa no disponible")
        return label

    def _add_condition_row(self, row: dict, atributo: str = "", valor: str = ""):
        """Agrega una fila de condición (atributo + valor) a una plantilla."""
        cond_widget = QWidget()
        fields = QHBoxLayout(cond_widget)
        fields.setContentsMargins(0, 0, 0, 0)
        fields.setSpacing(8)

        attr_combo = QComboBox()
        attr_combo.setEditable(self._attributes_empty)
        if self._attributes_empty:
            attr_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            attr_combo.lineEdit().setPlaceholderText("Nombre del atributo")
        else:
            attr_combo.addItem("Selecciona un atributo…", "")
            for attr in self._available_attributes:
                attr_combo.addItem(attr, attr)
        if atributo:
            if attr_combo.isEditable():
                attr_combo.setEditText(atributo)
            else:
                idx = attr_combo.findData(atributo)
                if idx < 0:
                    attr_combo.addItem(atributo, atributo)
                    idx = attr_combo.findData(atributo)
                attr_combo.setCurrentIndex(idx)

        fields.addWidget(QLabel("Atributo:"))
        fields.addWidget(attr_combo, 1)

        valor_input = QLineEdit()
        valor_input.setPlaceholderText("Valor")
        if valor:
            valor_input.setText(valor)
        fields.addWidget(QLabel("igual a"))
        fields.addWidget(valor_input, 1)

        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(26, 26)
        remove_btn.setToolTip("Quitar esta condición")
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF; color: #DC2626;
                border: 1px solid #FCA5A5; border-radius: 6px; font-size: 12px;
            }
            QPushButton:hover { background-color: #FEE2E2; }
        """)
        fields.addWidget(remove_btn)

        cond = {
            "widget": cond_widget,
            "attr_combo": attr_combo,
            "valor_input": valor_input,
            "remove_btn": remove_btn,
        }
        row["cond_rows"].append(cond)
        row["cond_layout"].addWidget(cond_widget)

        def _refresh():
            self._update_preview(row)

        valor_input.textChanged.connect(_refresh)
        attr_combo.currentTextChanged.connect(_refresh)
        if attr_combo.isEditable():
            attr_combo.editTextChanged.connect(_refresh)
        remove_btn.clicked.connect(lambda _, r=row, c=cond: self._remove_condition_row(r, c))

        self._update_preview(row)

    def _remove_condition_row(self, row: dict, cond: dict):
        """Quita una condición, manteniendo al menos una por regla (Req 3.3)."""
        if len(row["cond_rows"]) <= 1:
            # Mantener al menos una condición: se limpian sus campos en lugar de
            # eliminar la última fila.
            cond["valor_input"].clear()
            if cond["attr_combo"].isEditable():
                cond["attr_combo"].setEditText("")
            else:
                cond["attr_combo"].setCurrentIndex(0)
            self._update_preview(row)
            return
        row["cond_rows"].remove(cond)
        cond["widget"].setParent(None)
        cond["widget"].deleteLater()
        self._update_preview(row)

    def _condition_attribute(self, cond: dict) -> str:
        """Atributo actual de una condición (texto manual o seleccionado)."""
        combo = cond["attr_combo"]
        if combo.isEditable():
            return combo.currentText().strip()
        return (combo.currentData() or "").strip()

    def _row_conditions(self, row: dict) -> list[dict]:
        """Condiciones no vacías de una fila (atributo y valor capturados)."""
        condiciones: list[dict] = []
        for cond in row["cond_rows"]:
            atributo = self._condition_attribute(cond)
            valor = cond["valor_input"].text().strip()
            if atributo or valor:
                condiciones.append({"atributo": atributo, "valor": valor})
        return condiciones

    def _update_preview(self, row: dict):
        """Refresca la representación textual de la regla como conjunción (Req 3.7)."""
        condiciones = self._row_conditions(row)
        if condiciones:
            partes = " Y ".join(
                f"\"{c['atributo'] or '(atributo)'}\" igual a "
                f"\"{c['valor'] or '(valor)'}\""
                for c in condiciones
            )
        else:
            partes = "(sin condiciones)"
        row["preview_label"].setText(f"{partes} asigna {row['nombre']}")

    def _on_accept(self):
        """Recolecta la asignación de cada fila y cierra aceptando.

        Las validaciones de guardado (longitudes, duplicados, etc.) las realiza
        el diálogo principal (`_validate_assignments`). Aquí solo se materializa
        lo capturado: por cada plantilla, su lista de condiciones (puede quedar
        vacía → configuración parcial) y la marca de plantilla por defecto.
        """
        default_id = self._default_group.checkedId()
        assignments: list[dict] = []
        for index, row in enumerate(self._rows):
            assignments.append(
                {
                    "plantilla_id": row["plantilla_id"],
                    "nombre": row["nombre"],
                    "condiciones": self._row_conditions(row),
                    "is_default": index == default_id,
                }
            )

        self.assignments = assignments
        self.default_template_id = (
            self._rows[default_id]["plantilla_id"]
            if 0 <= default_id < len(self._rows)
            else None
        )
        self.accept()


class MultiTemplateDialog(QDialog):
    """Diálogo modal de configuración de multiplantillaje para un Cliente."""

    # Se emite con el `cliente_id` cuando la configuración se guarda con éxito.
    # La emisión real se conecta en subtareas posteriores (6.4).
    config_saved = Signal(int)

    def __init__(self, cliente_id: int, parent=None):
        super().__init__(parent)
        self.cliente_id = cliente_id
        # Datos de las plantillas del cliente como dicts planos extraídos dentro
        # de la sesión para no arrastrar instancias ORM desacopladas (Req
        # 2.1/2.2). Se capturan también orientación y dimensiones para la
        # advertencia de diferencias de la tarea 6.3 (Req 8.7).
        self._templates: list[dict] = []
        # Atributos_Disponibles del cliente para poblar el selector (Req 3.2).
        self._available_attributes: list[str] = []
        # Indica si la carga inicial tuvo éxito; gobierna si se puede guardar.
        self._load_ok = False
        # Asignaciones capturadas en la ventana flotante (para 6.3/6.4).
        self._assignments: list[dict] = []
        self._default_template_id: int | None = None
        # Modo edición (tarea 6.4): se activa al abrir un cliente que ya tiene
        # una Configuracion_Multiplantillaje (Req 4.4). En este modo el conjunto
        # de plantillas queda bloqueado (Decisión 3) y se ofrece eliminar la
        # configuración completa (Decisión 4).
        self._edit_mode = False
        self._set_locked = False
        self._locked_template_ids: set[int] = set()
        # Asignación global para diseño único (Decisión 5, tarea 6.5): cuando el
        # cliente tiene una sola plantilla no se abre la ventana de reglas; esa
        # plantilla es la Plantilla_Por_Defecto y la configuración no lleva
        # reglas. En este modo, guardar persiste una config global (reglas vacías
        # + default), por lo que la validación de cero reglas es válida solo aquí
        # (Req 3.8, 5.7).
        self._global_single_mode = False

        self.setModal(True)
        self._setup_ui()
        self._load_templates()

    # ------------------------------------------------------------------ UI ---
    def _setup_ui(self):
        self.setWindowTitle("Configuración de multiplantillaje")
        self.setMinimumWidth(520)
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; }
            QListWidget {
                border: 1px solid #E2E8F0; border-radius: 8px;
                background-color: #FFFFFF; padding: 4px; outline: none;
            }
            QListWidget::item { padding: 8px; border-radius: 4px; }
            QListWidget::item:selected {
                background-color: #FEE2E2; color: #171A2B;
            }
            QListWidget::item:hover { background-color: #F0F4FF; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Título
        title = QLabel("Configuración de multiplantillaje")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #171A2B;"
        )
        layout.addWidget(title)

        subtitle = QLabel("Selecciona los diseños del cliente para el set")
        subtitle.setStyleSheet("color: #64748B; font-size: 13px;")
        layout.addWidget(subtitle)

        # Lista de plantillas/diseños del cliente (Req 2.2: nombre visible).
        # Selección múltiple mediante CASILLAS (Req 2.3): cada plantilla tiene un
        # checkbox que se alterna con un clic. Esto evita por completo los
        # atajos de teclado de selección (Ctrl/Cmd/Shift), que en macOS resultan
        # poco fiables, y deja claro qué plantillas integran el set.
        self._template_list = QListWidget()
        self._template_list.setSelectionMode(
            QListWidget.SelectionMode.NoSelection
        )
        self._template_list.itemChanged.connect(self._on_selection_changed)
        # Un clic en cualquier parte de la fila alterna su casilla. En macOS el
        # indicador nativo es diminuto y, con `NoSelection`, pulsar el nombre no
        # hacía nada; eso daba la sensación de que no se podían seleccionar
        # varias plantillas. Capturamos el clic en el viewport para alternar la
        # casilla de toda la fila, consumiendo el evento para evitar que el
        # estilo nativo lo alterne de nuevo (doble-toggle).
        self._template_list.viewport().installEventFilter(self)
        layout.addWidget(self._template_list)

        # Mensaje informativo/estado (carga, errores, advertencias).
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #64748B; font-size: 12px;")
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        # Botones
        btn_layout = QHBoxLayout()

        # Abre la ventana flotante de asignación para las plantillas
        # seleccionadas (Req 3.x). Se habilita al seleccionar al menos una.
        self._assign_btn = QPushButton("Configurar asignación…")
        self._assign_btn.setStyleSheet("""
            QPushButton {
                background-color: #F5F7FA; color: #171A2B;
                border: 1px solid #E2E8F0; border-radius: 8px;
                padding: 10px 24px; font-size: 14px;
            }
            QPushButton:hover { background-color: #E2E8F0; }
            QPushButton:disabled { color: #94A3B8; }
        """)
        self._assign_btn.setEnabled(False)
        self._assign_btn.clicked.connect(self._open_assignment_window)
        btn_layout.addWidget(self._assign_btn)

        # Botón de eliminación de la configuración completa (Decisión 4). Solo se
        # muestra en modo edición; al eliminar se desbloquea la reselección del
        # set de plantillas.
        self._delete_btn = QPushButton("Eliminar configuración")
        self._delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF; color: #DC2626;
                border: 1px solid #FCA5A5; border-radius: 8px;
                padding: 10px 24px; font-size: 14px;
            }
            QPushButton:hover { background-color: #FEE2E2; }
        """)
        self._delete_btn.clicked.connect(self._on_delete_config)
        self._delete_btn.setVisible(False)
        btn_layout.addWidget(self._delete_btn)

        btn_layout.addStretch()

        self._cancel_btn = QPushButton("Cancelar")
        self._cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #F5F7FA; color: #171A2B;
                border: 1px solid #E2E8F0; border-radius: 8px;
                padding: 10px 24px; font-size: 14px;
            }
            QPushButton:hover { background-color: #E2E8F0; }
        """)
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)

        self._save_btn = QPushButton("Guardar")
        self._save_btn.setStyleSheet("""
            QPushButton {
                background-color: #FB5252; color: white; border: none;
                border-radius: 8px; padding: 10px 24px;
                font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #E04848; }
            QPushButton:disabled { background-color: #F1A8A8; }
        """)
        # Guardar arranca deshabilitado: la habilitación final (Req 2.6) y la
        # persistencia se completan en la subtarea 6.4.
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self._save_btn)

        layout.addLayout(btn_layout)

    # -------------------------------------------------------------- Carga ---
    def _load_templates(self):
        """Carga las plantillas y atributos del cliente (Req 2.1, 2.2, 3.2).

        Si la carga falla, muestra un mensaje de error indicando el fallo y
        mantiene deshabilitada la acción de guardar (Req 2.5, 4.7).
        """
        try:
            with DatabaseSession() as session:
                plantillas = MultiTemplateRepository.list_templates(
                    session, self.cliente_id
                )
                # Materializar los datos necesarios mientras la sesión sigue
                # abierta: las instancias ORM quedan desacopladas al cerrarla.
                self._templates = [
                    {
                        "id": p.id,
                        "nombre": p.nombre,
                        "orientacion": p.orientacion,
                        "ancho": p.ancho,
                        "alto": p.alto,
                        "recursos": dict(p.recursos or {}),
                    }
                    for p in plantillas
                ]
                # Atributos_Disponibles para el selector de la ventana de
                # asignación (Req 3.2, 7.1-7.3).
                self._available_attributes = (
                    MultiTemplateRepository.available_attributes(
                        session, self.cliente_id
                    )
                )
        except Exception as exc:  # noqa: BLE001 - se reporta el fallo al usuario
            self._load_ok = False
            self._templates = []
            self._available_attributes = []
            self._save_btn.setEnabled(False)
            self._assign_btn.setEnabled(False)
            self._show_status(
                "No se pudieron cargar las plantillas del cliente: "
                f"{exc}",
                error=True,
            )
            QMessageBox.critical(
                self,
                "Error al cargar plantillas",
                "No se pudo cargar la lista de plantillas del cliente.\n\n"
                f"Detalle: {exc}",
            )
            return

        self._load_ok = True
        self._populate_template_list()
        # Tras cargar las plantillas, intenta cargar una configuración previa
        # del cliente para entrar en modo edición (Req 4.4 / 4.7).
        self._load_existing_config()

    def _load_existing_config(self):
        """Carga la configuración existente del cliente y entra en modo edición.

        Si el cliente ya tiene una `Configuracion_Multiplantillaje`, se precargan
        sus reglas y la Plantilla_Por_Defecto (Req 4.4) y se bloquea la selección
        del set de plantillas (Decisión 3). Si la carga de la configuración falla,
        el diálogo se abre sin reglas precargadas y se muestra un mensaje de error
        que indica la causa (Req 4.7).
        """
        if not self._load_ok:
            return

        try:
            with DatabaseSession() as session:
                config = MultiTemplateRepository.get_config(
                    session, self.cliente_id
                )
        except Exception as exc:  # noqa: BLE001 - se reporta el fallo al usuario
            # Req 4.7: abrir sin reglas precargadas, informando la causa.
            self._edit_mode = False
            self._show_status(
                "No se pudo cargar la configuración existente; se abre sin "
                f"reglas precargadas. Detalle: {exc}",
                error=True,
            )
            QMessageBox.warning(
                self,
                "Error al cargar la configuración",
                "No se pudo cargar la configuración de multiplantillaje "
                "existente. El diálogo se abre sin reglas precargadas.\n\n"
                f"Detalle: {exc}",
            )
            return

        if config is None:
            # Sin configuración previa: modo creación normal.
            return

        self._enter_edit_mode(config)

    def _enter_edit_mode(self, config):
        """Activa el modo edición precargando reglas con sus condiciones (Req 4.4, 9.4).

        Materializa `config.reglas` (cada una con su lista de condiciones) en
        `_assignments`, fija la Plantilla_Por_Defecto y marca las casillas de las
        plantillas incluidas. A diferencia del diseño anterior, **no** bloquea la
        selección del set (Decisión 3 revisada): el usuario puede reelegir
        plantillas y completar las que aún no tienen condiciones (Req 9.2, 9.4).
        """
        id_to_nombre = {t["id"]: t["nombre"] for t in self._templates}

        assignments: list[dict] = []
        for regla in config.reglas:
            condiciones = [
                {"atributo": c.atributo, "valor": c.valor}
                for c in regla.condiciones
            ]
            assignments.append(
                {
                    "plantilla_id": regla.plantilla_destino_id,
                    "nombre": id_to_nombre.get(regla.plantilla_destino_id, ""),
                    "condiciones": condiciones,
                    "is_default": (
                        regla.plantilla_destino_id
                        == config.plantilla_default_id
                    ),
                }
            )

        self._assignments = assignments
        self._default_template_id = config.plantilla_default_id

        # Conjunto de plantillas de la configuración (destinos de regla + default).
        incluidas = {a["plantilla_id"] for a in assignments}
        if config.plantilla_default_id is not None:
            incluidas.add(config.plantilla_default_id)
        self._locked_template_ids = set()  # ya no se bloquea (Decisión 3 revisada)

        # Refleja el set en la lista marcando sus casillas, manteniéndolas
        # editables para permitir reelección (Req 9.2).
        self._template_list.blockSignals(True)
        for i in range(self._template_list.count()):
            item = self._template_list.item(i)
            is_in = item.data(Qt.ItemDataRole.UserRole) in incluidas
            item.setCheckState(
                Qt.CheckState.Checked if is_in else Qt.CheckState.Unchecked
            )
            item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
        self._template_list.blockSignals(False)
        self._set_locked = False
        self._edit_mode = True

        # Mostrar el botón de eliminación (Decisión 4) y habilitar reedición.
        self._delete_btn.setVisible(True)
        if self._global_single_mode:
            # Diseño único (Decisión 5): la configuración es global (default sin
            # reglas); no se ofrece la ventana de asignación, solo guardar/borrar.
            self._assign_btn.setVisible(False)
            self._show_status(
                "Editando la configuración global de la única plantilla del "
                "cliente. Pulsa «Guardar» para conservarla o «Eliminar "
                "configuración» para rehacerla.",
                error=False,
            )
        else:
            self._assign_btn.setEnabled(True)
            self._show_pending_status()
        self._update_save_enabled()

    def _templates_without_conditions(self) -> list[str]:
        """Nombres de plantillas seleccionadas que aún no tienen condiciones (Req 9.5)."""
        return [
            a.get("nombre", "")
            for a in self._assignments
            if not a.get("condiciones")
        ]

    def _show_pending_status(self):
        """Indica visualmente las plantillas sin condiciones (Req 9.5)."""
        pendientes = self._templates_without_conditions()
        if pendientes:
            self._show_status(
                "Configuración parcial: sin condiciones aún → "
                + ", ".join(pendientes)
                + ". Puedes guardarlas así y completarlas luego con «Configurar "
                "asignación…».",
                error=False,
            )
        else:
            self._show_status(
                "Pulsa «Configurar asignación…» para editar las reglas o el "
                "valor por defecto.",
                error=False,
            )

    def _exit_edit_mode(self):
        """Sale del modo edición y desbloquea la reselección del set (Decisión 4).

        Se invoca tras eliminar la configuración: limpia las asignaciones, libera
        el bloqueo del set y restablece la selección múltiple para que el usuario
        pueda elegir un nuevo conjunto de plantillas.
        """
        self._edit_mode = False
        self._set_locked = False
        self._locked_template_ids = set()
        self._assignments = []
        self._default_template_id = None

        # Reactiva las casillas y limpia las marcas para rehacer la selección.
        self._template_list.blockSignals(True)
        for i in range(self._template_list.count()):
            item = self._template_list.item(i)
            item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            item.setCheckState(Qt.CheckState.Unchecked)
        self._template_list.blockSignals(False)
        self._delete_btn.setVisible(False)
        self._on_selection_changed()

    def _populate_template_list(self):
        """Rellena la lista con el nombre visible de cada plantilla (Req 2.2)."""
        self._template_list.clear()

        # Bloquear señales mientras se llena: insertar ítems con estado de
        # casilla dispara `itemChanged` y reentraría en `_on_selection_changed`.
        self._template_list.blockSignals(True)
        for template in self._templates:
            item = QListWidgetItem(template["nombre"])
            # Se conserva el id de la plantilla para la lógica de selección y
            # asignación.
            item.setData(Qt.ItemDataRole.UserRole, template["id"])
            # Casilla por plantilla (selección múltiple). `ItemIsUserCheckable`
            # es necesario para que el indicador se dibuje con el estilo nativo
            # de macOS; el alternado por fila lo gobierna `eventFilter`.
            item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            item.setCheckState(Qt.CheckState.Unchecked)
            self._template_list.addItem(item)
        self._template_list.blockSignals(False)

        # Advertencia "se requieren al menos dos plantillas" para multiplantillaje
        # (Req 2.4) y caso de diseño único (Decisión 5, tarea 6.5).
        if not self._templates:
            self._global_single_mode = False
            self._show_status(
                "Este cliente no tiene plantillas disponibles.",
                error=False,
            )
        elif len(self._templates) == 1:
            # Asignación global para diseño único (Decisión 5): no se abre la
            # ventana de reglas. Esa única plantilla queda como Plantilla_Por_
            # Defecto y la configuración no lleva reglas; guardar persiste una
            # config global (Req 3.8, 5.7). Si el cliente ya tiene una config
            # guardada, `_load_existing_config` ajusta el default cargado.
            self._global_single_mode = True
            self._default_template_id = self._templates[0]["id"]
            self._assignments = []
            # La ventana de asignación no es necesaria en este caso.
            self._assign_btn.setVisible(False)
            self._show_status(
                "Este cliente tiene una sola plantilla. Se guardará como "
                "configuración global: esa plantilla se aplicará a todos los "
                "registros sin reglas. Pulsa «Guardar».",
                error=False,
            )
        else:
            self._global_single_mode = False
            self._status_label.setVisible(False)

        self._update_save_enabled()

    # ----------------------------------------------------- Selección / set ---
    def _checked_template_ids(self) -> set[int]:
        """Ids de las plantillas con la casilla marcada en la lista."""
        ids: set[int] = set()
        for i in range(self._template_list.count()):
            item = self._template_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                ids.add(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _selected_templates(self) -> list[dict]:
        """Plantillas actualmente marcadas en la lista (Req 2.5, 9.2).

        La selección del set siempre se lee de las casillas, también en modo
        edición (Decisión 3 revisada): el set no se bloquea hasta guardar.
        """
        checked_ids = self._checked_template_ids()
        return [t for t in self._templates if t["id"] in checked_ids]

    def _reconcile_assignments_with_selection(self):
        """Sincroniza `_assignments` con las casillas marcadas (Req 9.2).

        Conserva las condiciones de las plantillas que siguen marcadas y descarta
        las desmarcadas; si la Plantilla_Por_Defecto deja de estar marcada, se
        limpia. Las plantillas recién marcadas se incorporan al abrir la ventana
        de asignación.
        """
        checked = self._checked_template_ids()
        self._assignments = [
            a for a in self._assignments if a["plantilla_id"] in checked
        ]
        if self._default_template_id not in checked:
            self._default_template_id = None

    def eventFilter(self, obj, event):
        """Alterna la casilla al hacer clic en cualquier parte de la fila.

        Se intercepta el clic en el viewport de la lista para que pulsar el
        nombre de la plantilla (no solo el diminuto indicador) marque/desmarque
        la casilla. Se consumen press y release del botón izquierdo para impedir
        que el estilo nativo alterne también la casilla (doble-toggle).
        """
        if obj is self._template_list.viewport():
            et = event.type()
            if (
                et in (
                    QEvent.Type.MouseButtonPress,
                    QEvent.Type.MouseButtonDblClick,
                )
                and event.button() == Qt.MouseButton.LeftButton
            ):
                # El cambio se aplica en el release; aquí solo evitamos el
                # toggle nativo.
                return True
            if (
                et == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
            ):
                item = self._template_list.itemAt(event.position().toPoint())
                if item is not None:
                    self._toggle_item(item)
                return True
        return super().eventFilter(obj, event)

    def _toggle_item(self, item):
        """Invierte el estado de la casilla de una fila respetando los bloqueos.

        En modo edición el set está bloqueado (Decisión 3) y en diseño único
        (Decisión 5) no hay selección de set, por lo que el clic no altera nada.
        """
        if self._set_locked or self._global_single_mode:
            return
        if not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        new_state = (
            Qt.CheckState.Unchecked
            if item.checkState() == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )
        # Dispara `itemChanged` -> `_on_selection_changed`.
        item.setCheckState(new_state)

    def _on_selection_changed(self, *args):
        """Habilita la asignación cuando hay al menos una plantilla marcada."""
        if self._global_single_mode:
            # Diseño único (Decisión 5): no se usa la ventana de reglas; el
            # guardado depende solo de tener la Plantilla_Por_Defecto fijada.
            self._update_save_enabled()
            return
        # El set nunca se bloquea hasta guardar (Decisión 3 revisada): sincroniza
        # las asignaciones con las casillas marcadas (Req 9.2).
        self._reconcile_assignments_with_selection()
        has_selection = len(self._checked_template_ids()) > 0
        self._assign_btn.setEnabled(self._load_ok and has_selection)
        if self._edit_mode and has_selection:
            self._show_pending_status()
        self._update_save_enabled()

    def _open_assignment_window(self):
        """Abre la ventana flotante de asignación para el set seleccionado.

        Por cada plantilla seleccionada se solicita Atributo y valor y se marca
        la Plantilla_Por_Defecto (Req 3.1, 3.2, 3.5, 3.8). Si no hay atributos
        disponibles, la ventana habilita la entrada manual (Req 3.3, 7.4). En
        modo edición se precargan las reglas y la Plantilla_Por_Defecto previas
        para permitir editar atributo/valor/destino y cambiar el default
        (Req 4.4, 6.1, 6.2, 6.7).
        """
        seleccionadas = self._selected_templates()
        if not seleccionadas:
            return

        # Precarga de condiciones cuando ya existen asignaciones (modo edición o
        # reapertura), conservando lo ya ingresado por plantilla.
        initial_conditions: dict[int, list[dict]] = {}
        for a in self._assignments:
            initial_conditions[a["plantilla_id"]] = [
                {"atributo": c.get("atributo", ""), "valor": c.get("valor", "")}
                for c in a.get("condiciones", [])
            ]
        initial_default_id = self._default_template_id

        window = TemplateAssignmentWindow(
            seleccionadas,
            self._available_attributes,
            initial_conditions=initial_conditions or None,
            initial_default_id=initial_default_id,
            parent=self,
        )
        if window.exec() == QDialog.DialogCode.Accepted:
            # Se conservan las asignaciones capturadas para la validación
            # y la persistencia.
            self._assignments = window.assignments
            self._default_template_id = window.default_template_id
            pendientes = self._templates_without_conditions()
            sufijo = (
                f" ({len(pendientes)} sin condiciones; se guardarán como "
                "configuración parcial)"
                if pendientes else ""
            )
            self._show_status(
                f"Asignación configurada para {len(self._assignments)} "
                f"plantilla(s){sufijo}.",
                error=False,
            )
            self._update_save_enabled()

    # --------------------------------------------------------- Guardado ---
    def _update_save_enabled(self):
        """Determina si la acción de guardar debe estar habilitada.

        El guardado nunca se habilita si la carga falló (Req 2.5, 4.7). Mientras
        el usuario no tenga al menos una plantilla destino asignada, el guardado
        permanece deshabilitado (Req 2.6). La validación detallada de cada regla
        se ejecuta al pulsar Guardar (`_on_save`).
        """
        if not self._load_ok:
            self._save_btn.setEnabled(False)
            return

        # Diseño único (Decisión 5): la configuración global es válida con cero
        # reglas siempre que exista la Plantilla_Por_Defecto (Req 3.8, 5.7).
        if self._global_single_mode:
            self._save_btn.setEnabled(self._default_template_id is not None)
            return

        # Hay plantilla(s) destino cuando la ventana de asignación produjo al
        # menos una asignación y se designó una Plantilla_Por_Defecto (Req 2.6).
        has_destino = bool(self._assignments) and self._default_template_id is not None
        self._save_btn.setEnabled(has_destino)

    def _client_template_ids(self) -> set[int]:
        """Ids de las plantillas del cliente en edición (Req 8.5).

        Todas las plantillas cargadas pertenecen al cliente (se obtienen vía
        `list_templates(cliente_id)`), por lo que la pertenencia a este conjunto
        equivale a "plantilla del mismo cliente".
        """
        return {t["id"] for t in self._templates}

    def _validate_assignments(self) -> bool:
        """Valida las asignaciones antes de persistir, sin alterarlas (Req 3, 7, 8, 9).

        Rechaza el guardado y conserva los datos ya ingresados cuando:
        - una condición tiene atributo o valor vacío/fuera de rango (Req 3.6/3.4/7.5);
        - el destino no pertenece al cliente en edición (Req 8.5);
        - dos reglas tienen el mismo conjunto de condiciones (Req 3.9);
        - no hay exactamente una Plantilla_Por_Defecto válida (Req 3.8).

        Las plantillas seleccionadas SIN condiciones se aceptan como configuración
        parcial (Req 9.3): no provocan error, pero tampoco coincidirán al imprimir.

        Muestra un mensaje por cada problema detectado y devuelve ``False`` si
        alguno aplica; ``True`` cuando todas las reglas son válidas.
        """
        if not self._load_ok:
            return False

        if not self._assignments:
            # Diseño único (Decisión 5): la configuración global es válida sin
            # reglas, siempre que la Plantilla_Por_Defecto exista y pertenezca al
            # cliente (Req 3.8, 5.8). En cualquier otro caso, se exige al menos
            # una plantilla destino seleccionada (Req 2.8).
            if self._global_single_mode:
                default_result = validate_single_default(
                    self._default_template_id, self._client_template_ids()
                )
                if not default_result.ok:
                    self._show_validation_errors(list(default_result.errors))
                    return False
                return True
            self._show_status(
                "Selecciona al menos una plantilla destino y configura su "
                "asignación antes de guardar.",
                error=True,
            )
            return False

        errors: list[str] = []
        client_ids = self._client_template_ids()

        for assignment in self._assignments:
            nombre = assignment.get("nombre", "")
            condiciones = assignment.get("condiciones", [])
            plantilla_id = assignment.get("plantilla_id")

            # Las condiciones presentes deben ser válidas (longitud/no vacías).
            # Una plantilla sin condiciones es válida (configuración parcial).
            if condiciones:
                cond_result = validate_condiciones({"condiciones": condiciones})
                if not cond_result.ok:
                    errors.extend(f"[{nombre}] {msg}" for msg in cond_result.errors)

            # Destino de otro cliente (Req 8.5): conservar la selección previa.
            if plantilla_id not in client_ids:
                errors.append(
                    f"[{nombre}] Solo se permiten plantillas del mismo cliente "
                    "como destino."
                )

        # Conjuntos de condiciones duplicados de forma normalizada (Req 3.9).
        for i, j in detect_duplicate_pairs(self._assignments):
            ni = self._assignments[i].get("nombre", "")
            nj = self._assignments[j].get("nombre", "")
            errors.append(
                f"Regla duplicada: \"{ni}\" y \"{nj}\" comparten el mismo "
                "conjunto de condiciones."
            )

        # Exactamente una Plantilla_Por_Defecto del cliente (Req 3.8).
        default_result = validate_single_default(
            self._default_template_id, client_ids
        )
        if not default_result.ok:
            errors.extend(default_result.errors)

        if errors:
            self._show_validation_errors(errors)
            return False

        return True

    def _confirm_template_differences(self) -> bool:
        """Advierte si las plantillas mapeadas difieren antes de guardar (Req 8.7).

        Compara orientación y dimensiones de lienzo de las plantillas con regla
        asignada. Si difieren, muestra una advertencia describiendo la diferencia
        y permite al usuario confirmar o cancelar el guardado. Devuelve ``True``
        para continuar con el guardado y ``False`` si el usuario cancela.
        """
        mapped_ids = {a.get("plantilla_id") for a in self._assignments}
        mapeadas = [t for t in self._templates if t["id"] in mapped_ids]

        diff = detect_template_differences(mapeadas)
        if not diff.has_difference:
            return True

        reply = QMessageBox.question(
            self,
            "Diferencias entre plantillas",
            f"{diff.message}\n\n¿Deseas guardar la configuración de todos modos?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _show_validation_errors(self, errors: list[str]):
        """Muestra los errores de validación al usuario sin cerrar el diálogo."""
        resumen = "\n".join(f"• {e}" for e in errors)
        self._show_status(
            "No se pudo guardar: corrige los errores indicados.", error=True
        )
        QMessageBox.warning(
            self,
            "Revisa la configuración",
            "Corrige lo siguiente antes de guardar:\n\n" + resumen,
        )

    def _on_save(self):
        """Valida la configuración y, si procede, la persiste.

        Primero ejecuta las validaciones de reglas (Req 3.6, 3.7, 7.5, 8.5) y la
        designación de la Plantilla_Por_Defecto (Req 3.8); si fallan, conserva
        los datos en pantalla y no cierra el diálogo. Luego, si las plantillas
        mapeadas difieren en orientación/dimensiones, pide confirmación (Req 8.7).
        La persistencia real (`MultiTemplateRepository.save_config`) y la
        confirmación de éxito se implementan en la subtarea 6.4.
        """
        if not self._validate_assignments():
            return

        if not self._confirm_template_differences():
            return

        # Persiste la configuración (reemplazo total, Req 4.1), muestra la
        # confirmación visible de éxito (Req 4.3), emite `config_saved` y maneja
        # los fallos de persistencia conservando el estado en pantalla (Req 4.6).
        self._persist_config()

    def _persist_config(self):
        """Persiste la configuración vía repositorio (Req 4.1, 4.3, 4.6, 6.5, 6.6).

        Convierte las asignaciones en pantalla a `list[ReglaDTO]` (con `orden`
        según la posición) y delega en `MultiTemplateRepository.save_config`, que
        reemplaza por completo cualquier configuración previa del cliente
        (Req 4.1). El guardado ocurre dentro de un `DatabaseSession` que confirma
        al salir sin excepción.

        - Éxito: muestra una confirmación visible (Req 4.3), emite `config_saved`
          y cierra el diálogo aceptando.
        - Fallo: conserva intactos los cambios en pantalla y muestra un mensaje
          de error con la causa (Req 4.6, 6.6); el diálogo permanece abierto.
        """
        reglas = [
            ReglaDTO(
                plantilla_destino_id=assignment.get("plantilla_id"),
                orden=posicion,
                condiciones=tuple(
                    CondicionDTO(
                        atributo=c.get("atributo", ""),
                        valor=c.get("valor", ""),
                        orden=c_pos,
                    )
                    for c_pos, c in enumerate(assignment.get("condiciones", []))
                ),
            )
            for posicion, assignment in enumerate(self._assignments)
        ]

        try:
            with DatabaseSession() as session:
                MultiTemplateRepository.save_config(
                    session,
                    self.cliente_id,
                    reglas,
                    self._default_template_id,
                )
        except Exception as exc:  # noqa: BLE001 - se reporta el fallo al usuario
            # Req 4.6 / 6.6: el estado en pantalla se conserva sin modificación y
            # se informa la causa del fallo; el diálogo no se cierra.
            self._show_status(
                f"No se pudo guardar la configuración: {exc}", error=True
            )
            QMessageBox.critical(
                self,
                "Error al guardar",
                "No se pudo guardar la configuración de multiplantillaje. Tus "
                "cambios siguen en pantalla.\n\n"
                f"Detalle: {exc}",
            )
            return

        # Req 4.3: confirmación visible de guardado exitoso.
        self._notify_success(
            "La configuración de multiplantillaje se guardó correctamente."
        )
        self.config_saved.emit(self.cliente_id)
        self.accept()

    def _on_delete_config(self):
        """Elimina la configuración completa del cliente (Decisión 4, Req 6.x).

        Pide confirmación y, si el usuario acepta, borra la configuración vía
        `MultiTemplateRepository.delete_config` dentro de un `DatabaseSession`.
        Tras eliminar con éxito, se desbloquea la reselección del set
        (`_exit_edit_mode`) para que el usuario pueda rehacer la selección. Si la
        eliminación falla, se conserva el estado y se informa la causa.
        """
        reply = QMessageBox.question(
            self,
            "Eliminar configuración",
            "¿Eliminar la configuración de multiplantillaje de este cliente?\n\n"
            "Podrás volver a seleccionar el conjunto de plantillas.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            with DatabaseSession() as session:
                MultiTemplateRepository.delete_config(session, self.cliente_id)
        except Exception as exc:  # noqa: BLE001 - se reporta el fallo al usuario
            self._show_status(
                f"No se pudo eliminar la configuración: {exc}", error=True
            )
            QMessageBox.critical(
                self,
                "Error al eliminar",
                "No se pudo eliminar la configuración de multiplantillaje.\n\n"
                f"Detalle: {exc}",
            )
            return

        self._exit_edit_mode()
        self._notify_success(
            "Configuración eliminada. Selecciona un nuevo conjunto de "
            "plantillas para volver a configurar."
        )

    def _notify_success(self, message: str):
        """Muestra una confirmación visible de éxito (Req 4.3).

        Usa el sistema de toasts de la aplicación (convención de la UI) y, como
        respaldo, refleja el mensaje en la barra de estado del diálogo.
        """
        try:
            from credencializacion.ui.widgets.toast import ToastManager

            ToastManager.instance().show_toast(message, "success")
        except Exception:  # noqa: BLE001 - el toast es complementario al estado
            pass
        self._show_status(message, error=False)

    # ----------------------------------------------------------- Utilidad ---
    def _show_status(self, message: str, *, error: bool = False):
        """Muestra un mensaje de estado bajo la lista."""
        color = "#DC2626" if error else "#64748B"
        self._status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._status_label.setText(message)
        self._status_label.setVisible(True)
