"""
Tabla de registros personalizada para el panel de control.

QTableWidget estilizado con thumbnails circulares, badges de estado,
botones de acción, y menú contextual. Diseño premium con la paleta
de colores del sistema.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import (
    QPixmap,
    QPainter,
    QBrush,
    QColor,
    QFont,
    QAction,
    QCursor,
    QPainterPath,
    QIcon,
)
from PySide6.QtWidgets import (
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QMenu,
    QAbstractItemView,
    QStyledItemDelegate,
)

if TYPE_CHECKING:
    from credencializacion.db.models import Registro

# ── Paleta de colores ──────────────────────────────────────────────────
PRIMARY = "#FB5252"
SECONDARY = "#FFD057"
TEXT_DARK = "#171A2B"
TEXT_LIGHT = "#64748B"
CARD_BG = "#FFFFFF"
BORDER = "#E2E8F0"
SUCCESS = "#22C55E"
WARNING = "#F59E0B"
ERROR = "#EF4444"
INFO_BLUE = "#3B82F6"
MAIN_BG = "#F5F7FA"

# Mapeo de estados a colores de badge
STATUS_COLORS: dict[str, tuple[str, str]] = {
    # estado: (background, text_color)
    "sin_foto": (WARNING, "#FFFFFF"),
    "sin_fotografia": (WARNING, "#FFFFFF"),
    "sin_formulario": ("#F97316", "#FFFFFF"),
    "pending": (WARNING, "#FFFFFF"),
    "pendiente": ("#94A3B8", "#FFFFFF"),
    "printing": (INFO_BLUE, "#FFFFFF"),
    "impreso": (SUCCESS, "#FFFFFF"),
    "error": (ERROR, "#FFFFFF"),
    "en_cola": (INFO_BLUE, "#FFFFFF"),
    "ready": (SUCCESS, "#FFFFFF"),
    "replacement_requested": (INFO_BLUE, "#FFFFFF"),
    "delivered": ("#8B5CF6", "#FFFFFF"),
}

# Columnas de la tabla
COLUMNS = [
    " ",                # 0: Checkbox
    "FOTO",             # 1: Thumbnail
    "ID",               # 2: Matrícula / enrollment code
    "NOMBRE",           # 3: Nombre(s)
    "APELLIDOS",        # 4: Apellidos
    "GRADO",            # 5: Grado
    "GRUPO",            # 6: Grupo
    "ESTADO",           # 7: Badge de estado (credential_display_status)
    "ACCIÓN",           # 8: Botón agregar a cola
]

# Índices de columna (única fuente de verdad para evitar descuadres).
COL_CHECK = 0
COL_PHOTO = 1
COL_ID = 2
COL_NOMBRE = 3
COL_APELLIDOS = 4
COL_GRADO = 5
COL_GRUPO = 6
COL_ESTADO = 7
COL_ACCION = 8

PHOTO_SIZE = 32


class StatusBadge(QLabel):
    """Label estilizado como badge/pill para mostrar estados."""

    def __init__(self, text: str, bg_color: str, text_color: str, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(24)
        self.setFont(QFont("Inter", 9, QFont.Weight.DemiBold))
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                border-radius: 12px;
                padding: 2px 12px;
                font-size: 11px;
                font-weight: 600;
            }}
        """)


class AddToQueueButton(QWidget):
    """Botón de acción para agregar un registro a la cola de impresión."""

    add_clicked = Signal(int)

    def __init__(self, registro_id: int, parent=None):
        super().__init__(parent)
        self._registro_id = registro_id

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        import qtawesome as qta
        self.btn_add = QPushButton()
        self.btn_add.setIcon(qta.icon("fa5s.plus-circle", color=PRIMARY))
        self.btn_add.setIconSize(QSize(16, 16))
        self.btn_add.setToolTip("Agregar a cola de impresión")
        self.btn_add.setFixedSize(26, 26)
        self.btn_add.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_add.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: #FEE2E2;
                border-color: {PRIMARY};
            }}
        """)
        self.btn_add.clicked.connect(
            lambda: self.add_clicked.emit(self._registro_id)
        )
        layout.addWidget(self.btn_add)


def _create_circular_pixmap(path: str, size: int = PHOTO_SIZE) -> QPixmap:
    """Crea un pixmap circular a partir de una ruta de imagen.

    Si la imagen no existe, devuelve un placeholder gris.

    Args:
        path: Ruta a la imagen.
        size: Diámetro del círculo en píxeles.

    Returns:
        QPixmap circular.
    """
    from pathlib import Path as PathLib

    source = QPixmap()
    if path and PathLib(path).exists():
        source.load(path)
    else:
        # Placeholder gris con silueta
        source = QPixmap(size, size)
        source.fill(QColor(BORDER))

    # Escalar al tamaño deseado
    source = source.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )

    # Recortar al centro si es rectangular
    if source.width() > size or source.height() > size:
        x = (source.width() - size) // 2
        y = (source.height() - size) // 2
        source = source.copy(x, y, size, size)

    # Aplicar máscara circular
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)

    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path_clip = QPainterPath()
    path_clip.addEllipse(0, 0, size, size)
    painter.setClipPath(path_clip)
    painter.drawPixmap(0, 0, source)
    painter.end()

    return result


class RecordTable(QTableWidget):
    """Tabla de registros con estilo premium para el panel de control.

    Muestra registros con foto circular, nombre, institución, estado
    como badge pill, y botones de acción. Soporta selección múltiple
    con checkboxes, sorting, y menú contextual.

    Signals:
        record_double_clicked(int): ID del registro al hacer doble clic.
        add_to_queue_clicked(int): ID del registro al hacer clic en agregar a cola.
    """

    record_double_clicked = Signal(int)
    add_to_queue_clicked = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._records: list["Registro"] = []
        self._registro_ids: list[int] = []  # IDs en orden de filas
        self._setup_table()
        self._setup_style()

    def _setup_table(self) -> None:
        """Configura columnas, headers y comportamiento de la tabla."""
        self.setColumnCount(len(COLUMNS))
        self.setHorizontalHeaderLabels(COLUMNS)

        # Configurar anchos de columna
        header = self.horizontalHeader()
        header.setSectionResizeMode(COL_CHECK, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_PHOTO, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_ID, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_NOMBRE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_APELLIDOS, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_GRADO, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_GRUPO, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_ESTADO, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_ACCION, QHeaderView.ResizeMode.Fixed)

        self.setColumnWidth(COL_CHECK, 40)
        self.setColumnWidth(COL_PHOTO, 50)
        self.setColumnWidth(COL_ID, 80)
        self.setColumnWidth(COL_GRADO, 70)
        self.setColumnWidth(COL_GRUPO, 70)
        self.setColumnWidth(COL_ESTADO, 130)
        self.setColumnWidth(COL_ACCION, 70)

        # Comportamiento
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Doble clic
        self.cellDoubleClicked.connect(self._on_double_click)

        # Menú contextual
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _setup_style(self) -> None:
        """Aplica stylesheet premium a la tabla."""
        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 12px;
                gridline-color: transparent;
                font-family: 'Inter', sans-serif;
                font-size: 13px;
                color: {TEXT_DARK};
            }}
            QTableWidget::item {{
                padding: 8px 4px;
                border-bottom: 1px solid {BORDER};
            }}
            QTableWidget::item:selected {{
                background-color: #FECACA;
                color: {TEXT_DARK};
            }}
            QTableWidget::item:alternate {{
                background-color: {MAIN_BG};
            }}
            QTableWidget::item:alternate:selected {{
                background-color: #FECACA;
                color: {TEXT_DARK};
            }}
            QHeaderView::section {{
                background-color: {MAIN_BG};
                color: {TEXT_LIGHT};
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                padding: 10px 8px;
                border: none;
                border-bottom: 2px solid {BORDER};
            }}
            QHeaderView::section:hover {{
                color: {TEXT_DARK};
            }}
        """)

    def set_records(self, records: list["Registro"]) -> None:
        """Carga registros en la tabla.

        Args:
            records: Lista de modelos Registro a mostrar.
        """
        self._records = records
        self._registro_ids.clear()
        self.setSortingEnabled(False)  # Desactivar durante carga
        self.setRowCount(len(records))

        for row, reg in enumerate(records):
            self._registro_ids.append(reg.id)
            self._populate_row(row, reg)
        self.setSortingEnabled(True)

    def set_photo_by_id(self, reg_id: int, pixmap: QPixmap) -> None:
        """Asigna una foto circular a la fila que corresponda al ID dado."""
        for row in range(self.rowCount()):
            chk_item = self.item(row, COL_CHECK)
            if chk_item and chk_item.data(Qt.ItemDataRole.UserRole) == reg_id:
                photo_item = self.item(row, COL_PHOTO)
                if photo_item:
                    photo_item.setIcon(QIcon(pixmap))
                break

    def _populate_row(self, row: int, reg: "Registro") -> None:
        """Llena una fila con los datos de un registro.

        Args:
            row: Índice de fila.
            reg: Modelo Registro.
        """
        # Col 0: Checkbox
        checkbox_item = QTableWidgetItem()
        checkbox_item.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )
        checkbox_item.setCheckState(Qt.CheckState.Unchecked)
        checkbox_item.setData(Qt.ItemDataRole.UserRole, reg.id)
        self.setItem(row, COL_CHECK, checkbox_item)

        # Col 1: Foto circular
        photo_item = QTableWidgetItem()
        pixmap = _create_circular_pixmap(reg.photo_path or "", PHOTO_SIZE)
        photo_item.setIcon(QIcon(pixmap))
        photo_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.setItem(row, COL_PHOTO, photo_item)

        # Col 2: ID
        enrollment = reg.enrollment_code or "—"
        id_item = QTableWidgetItem(enrollment)
        id_item.setFont(QFont("Inter", 11))
        id_item.setForeground(QColor(TEXT_LIGHT))
        self.setItem(row, COL_ID, id_item)

        # Col 3: NOMBRE(S)
        nombre = reg.get_dato("nombre", "") or reg.nombre_completo or "Sin nombre"
        name_item = QTableWidgetItem(nombre)
        name_item.setFont(QFont("Inter", 12, QFont.Weight.DemiBold))
        name_item.setForeground(QColor(TEXT_DARK))
        self.setItem(row, COL_NOMBRE, name_item)

        # Col 4: APELLIDOS
        apellidos = reg.get_dato("apellido", "") or reg.get_dato("apellidos", "") or "—"
        apellidos_item = QTableWidgetItem(apellidos)
        apellidos_item.setFont(QFont("Inter", 12))
        apellidos_item.setForeground(QColor(TEXT_DARK))
        self.setItem(row, COL_APELLIDOS, apellidos_item)

        # Col 5: Grado
        grado_item = QTableWidgetItem(reg.get_dato("grado", "—"))
        grado_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        grado_item.setFont(QFont("Inter", 11))
        self.setItem(row, COL_GRADO, grado_item)

        # Col 6: Grupo
        group_item = QTableWidgetItem(reg.get_dato("grupo", "—"))
        group_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        group_item.setFont(QFont("Inter", 11))
        self.setItem(row, COL_GRUPO, group_item)

        # Col 7: Estado badge (credential_display_status del endpoint)
        estado = self._determine_status(reg)
        bg, fg = STATUS_COLORS.get(estado, (TEXT_LIGHT, "#FFFFFF"))
        badge = StatusBadge(self._status_label(estado), bg, fg)
        self.setCellWidget(row, COL_ESTADO, badge)

        # Col 8: Botón agregar a cola
        actions = AddToQueueButton(reg.id)
        actions.add_clicked.connect(lambda rid: self.add_to_queue_clicked.emit(rid)) 
        self.setCellWidget(row, COL_ACCION, actions)

        # Altura de fila
        self.setRowHeight(row, 56)

    def _determine_status(self, reg: "Registro") -> str:
        """Determina el estado visual usando `credential_display_status` del API.

        Si el endpoint provee `credential_display_status` se usa tal cual (es la
        fuente de verdad del backend). Si no, cae al comportamiento previo
        (falta foto > credential_status > estado_impresion).
        """
        display = (reg.get_dato("credential_display_status", "") or "").strip()
        if display:
            return display
        if not reg.photo_path:
            return "sin_foto"
        if reg.credential_status == "replacement_requested":
            return "replacement_requested"
        if reg.credential_status == "ready":
            return "ready"
        if reg.estado_impresion and reg.estado_impresion != "pendiente":
            return reg.estado_impresion
        return "pendiente"

    def _status_label(self, estado: str) -> str:
        """Convierte un estado interno al texto visible en español."""
        labels = {
            "sin_foto": "⚠ Falta Foto",
            "sin_fotografia": "⚠ Sin Fotografía",
            "sin_formulario": "📋 Sin Formulario",
            "pending": "📝 Pendiente",
            "pendiente": "📝 Pendiente",
            "printing": "🖨 En Impresión",
            "impreso": "✅ Impreso",
            "error": "❌ Error",
            "en_cola": "🔵 En Cola",
            "ready": "✅ Listo",
            "replacement_requested": "🔄 Renovación",
            "delivered": "📦 Entregado",
        }
        return labels.get(estado, estado.replace("_", " ").capitalize())

    def get_selected_ids(self) -> list[int]:
        """Obtiene los IDs de las filas seleccionadas (selección de fila Qt).

        Lee el reg.id almacenado en UserRole de la columna 0 (checkbox).

        Returns:
            Lista de IDs de registros seleccionados.
        """
        selected_rows = set()
        for index in self.selectedIndexes():
            selected_rows.add(index.row())

        selected: list[int] = []
        for row in sorted(selected_rows):
            item = self.item(row, COL_CHECK)  # Col 0 = checkbox con reg.id en UserRole
            if item:
                reg_id = item.data(Qt.ItemDataRole.UserRole)
                if reg_id is not None:
                    selected.append(reg_id)
        return selected

    def select_all(self, checked: bool) -> None:
        """Selecciona o deselecciona todas las filas.

        Args:
            checked: True para seleccionar todo, False para deseleccionar.
        """
        if checked:
            self.selectAll()
        else:
            self.clearSelection()

    def _on_double_click(self, row: int, _column: int) -> None:
        """Emite señal con el ID del registro al hacer doble clic."""
        item = self.item(row, COL_CHECK)
        if item:
            reg_id = item.data(Qt.ItemDataRole.UserRole)
            if reg_id is not None:
                self.record_double_clicked.emit(int(reg_id))

    def _show_context_menu(self, pos) -> None:
        """Muestra menú contextual con opciones para el registro."""
        row = self.rowAt(pos.y())
        if row < 0:
            return

        item = self.item(row, COL_CHECK)
        if not item:
            return
        reg_id = item.data(Qt.ItemDataRole.UserRole)

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                font-size: 13px;
                color: {TEXT_DARK};
            }}
            QMenu::item:selected {{
                background-color: #FEE2E2;
                border-radius: 4px;
            }}
        """)

        action_detail = QAction("👁  Ver detalle", self)
        action_detail.triggered.connect(
            lambda: self.record_double_clicked.emit(int(reg_id))
        )

        action_queue = QAction("📋  Agregar a cola", self)
        # La conexión se hará desde ControlPanel

        action_status = QAction("🔄  Cambiar estado", self)
        # La conexión se hará desde ControlPanel

        menu.addAction(action_detail)
        menu.addAction(action_queue)
        menu.addSeparator()
        menu.addAction(action_status)

        menu.exec(self.viewport().mapToGlobal(pos))
