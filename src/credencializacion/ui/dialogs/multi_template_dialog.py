"""
Vista de Configuración de multiplantillaje por lado (Vista_Configuracion).

Para un diseño (Plantilla) y un lado (frente/vuelta), permite configurar varias
IMÁGENES DE FONDO: una fila por imagen con su vista previa, sus condiciones
`atributo = valor` en conjunción (Y) y una marca de imagen por defecto. NO crea
diseños/plantillas nuevas: las imágenes se guardan como rutas dentro de la
configuración del (diseño, lado).

Reglas del modelo:
- La imagen marcada como "por defecto" es el fallback (Imagen_Base_Por_Defecto)
  y se muestra en el diseñador/vista previa; no requiere condiciones.
- Las demás imágenes son Variantes y requieren al menos una condición completa.
- Guardar hace upsert de la única configuración del (diseño, lado).
"""
from __future__ import annotations

from pathlib import Path

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QRadioButton, QButtonGroup, QScrollArea,
    QVBoxLayout, QWidget,
)

from credencializacion.db.engine import DatabaseSession
from credencializacion.db.repositories import LadoConfigRepository
from credencializacion.services.image_selection import CondicionDTO, VarianteDTO
from credencializacion.services.template_validators import (
    validate_atributo_length,
    validate_valor_length,
)

_IMG_FILTER = "Imágenes (*.png *.jpg *.jpeg *.webp)"


class MultiTemplateDialog(QDialog):
    """Vista_Configuracion de multiplantillaje para un (diseño, lado)."""

    # Se emite con (plantilla_id, lado) cuando la configuración se guarda o borra.
    config_saved = Signal(int, str)
    config_deleted = Signal(int, str)

    def __init__(
        self,
        plantilla_id: int,
        cliente_id: int,
        lado: str,
        rutas_iniciales: list[str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.plantilla_id = plantilla_id
        self.cliente_id = cliente_id
        self.lado = lado  # "frente" | "vuelta"
        self._available_attributes: list[str] = []
        self._rows: list[dict] = []
        self._default_group = QButtonGroup(self)
        self._default_group.setExclusive(True)

        self.setModal(True)
        self._setup_ui()
        self._load_initial_state(rutas_iniciales or [])

    # ------------------------------------------------------------------ UI ---
    def _setup_ui(self):
        self.setWindowTitle(f"Multiplantillaje — {self.lado.upper()}")
        self.setMinimumWidth(680)
        self.setMinimumHeight(480)
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; }
            QFrame#card { border: 1px solid #E2E8F0; border-radius: 8px;
                          background-color: #FFFFFF; }
            QComboBox, QLineEdit { border: 1px solid #E2E8F0; border-radius: 6px;
                          padding: 6px 8px; background-color: #FFFFFF; }
            QComboBox:focus, QLineEdit:focus { border: 1px solid #FB5252; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel(f"Imágenes de fondo — lado {self.lado}")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #171A2B;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Marca la imagen por defecto y, para cada otra imagen, define las "
            "condiciones (atributo = valor) que la activan."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #64748B; font-size: 13px;")
        layout.addWidget(subtitle)

        # Área desplazable con una tarjeta por imagen.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self._rows_layout = QVBoxLayout(container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(12)
        self._rows_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        # Botonera.
        btns = QHBoxLayout()
        self._add_btn = QPushButton("+ Agregar imágenes…")
        self._add_btn.setStyleSheet(self._secondary_btn_style())
        self._add_btn.clicked.connect(self._on_add_images)
        btns.addWidget(self._add_btn)

        self._delete_btn = QPushButton("Eliminar configuración")
        self._delete_btn.setStyleSheet("""
            QPushButton { background-color: #FFFFFF; color: #DC2626;
                border: 1px solid #FCA5A5; border-radius: 8px;
                padding: 10px 18px; font-size: 14px; }
            QPushButton:hover { background-color: #FEE2E2; }
        """)
        self._delete_btn.clicked.connect(self._on_delete_config)
        self._delete_btn.setVisible(False)
        btns.addWidget(self._delete_btn)

        btns.addStretch()

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setStyleSheet(self._secondary_btn_style())
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)

        self._save_btn = QPushButton("Guardar")
        self._save_btn.setStyleSheet("""
            QPushButton { background-color: #FB5252; color: white; border: none;
                border-radius: 8px; padding: 10px 24px; font-weight: bold;
                font-size: 14px; }
            QPushButton:hover { background-color: #E04848; }
            QPushButton:disabled { background-color: #F1A8A8; }
        """)
        self._save_btn.clicked.connect(self._on_save)
        btns.addWidget(self._save_btn)

        layout.addLayout(btns)

    def _secondary_btn_style(self) -> str:
        return """
            QPushButton { background-color: #F5F7FA; color: #171A2B;
                border: 1px solid #E2E8F0; border-radius: 8px;
                padding: 10px 18px; font-size: 14px; }
            QPushButton:hover { background-color: #E2E8F0; }
        """

    # -------------------------------------------------------------- Carga ---
    def _load_initial_state(self, rutas_iniciales: list[str]):
        """Carga atributos disponibles, la config existente y las rutas iniciales."""
        try:
            with DatabaseSession() as session:
                self._available_attributes = (
                    LadoConfigRepository.available_attributes(session, self.cliente_id)
                )
                config = LadoConfigRepository.get_config_lado(
                    session, self.plantilla_id, self.lado
                )
        except Exception as exc:  # noqa: BLE001
            self._available_attributes = []
            config = None
            QMessageBox.warning(
                self, "Error al cargar",
                f"No se pudo cargar la configuración existente.\n\nDetalle: {exc}",
            )

        existing_paths: list[str] = []
        default_path: str | None = None
        cond_by_path: dict[str, list[dict]] = {}
        if config is not None:
            self._delete_btn.setVisible(True)
            default_path = config.imagen_default_path
            if default_path:
                existing_paths.append(default_path)
            for var in config.variantes:
                existing_paths.append(var.imagen_path)
                cond_by_path[var.imagen_path] = [
                    {"atributo": c.atributo, "valor": c.valor} for c in var.condiciones
                ]

        # Combinar rutas existentes + nuevas (sin duplicar), conservando orden.
        seen: set[str] = set()
        todas: list[str] = []
        for p in [*existing_paths, *rutas_iniciales]:
            if p and p not in seen:
                seen.add(p)
                todas.append(p)

        for idx, ruta in enumerate(todas):
            es_default = (default_path is not None and ruta == default_path) or (
                default_path is None and idx == 0
            )
            self._add_row(ruta, cond_by_path.get(ruta, []), es_default)

        self._update_save_enabled()

    # ----------------------------------------------------------- Filas ---
    def _add_row(self, imagen_path: str, condiciones: list[dict], es_default: bool):
        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 14, 14, 14)
        cl.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(self._build_preview(imagen_path))

        name = QLabel(Path(imagen_path).name)
        name.setStyleSheet("font-size: 13px; font-weight: bold; color: #171A2B;")
        header.addWidget(name)
        header.addStretch()

        default_radio = QRadioButton("Imagen por defecto")
        default_radio.setStyleSheet("color: #475569; font-size: 12px;")
        default_radio.setChecked(es_default)
        self._default_group.addButton(default_radio)
        default_radio.toggled.connect(self._on_default_toggled)
        header.addWidget(default_radio)

        reassign = QPushButton("Reasignar…")
        reassign.setStyleSheet(self._secondary_btn_style())
        remove = QPushButton()
        remove.setIcon(qta.icon("fa5s.trash-alt", color="#DC2626"))
        remove.setFixedSize(30, 30)
        remove.setToolTip("Quitar esta imagen del set")
        remove.setStyleSheet("""
            QPushButton { background-color: #FFFFFF;
                border: 1px solid #FCA5A5; border-radius: 6px; }
            QPushButton:hover { background-color: #FEE2E2; }
        """)
        header.addWidget(reassign)
        header.addWidget(remove)
        cl.addLayout(header)

        cond_container = QWidget()
        cond_layout = QVBoxLayout(cond_container)
        cond_layout.setContentsMargins(0, 0, 0, 0)
        cond_layout.setSpacing(6)
        cl.addWidget(cond_container)

        add_cond = QPushButton("+ Agregar condición (Y)")
        add_cond.setStyleSheet("""
            QPushButton { background-color: #F5F7FA; color: #1D4ED8;
                border: 1px dashed #93C5FD; border-radius: 6px;
                padding: 6px 10px; font-size: 12px; }
            QPushButton:hover { background-color: #EFF6FF; }
        """)
        cl.addWidget(add_cond, alignment=Qt.AlignmentFlag.AlignLeft)

        row = {
            "card": card,
            "imagen_path": imagen_path,
            "name_label": name,
            "default_radio": default_radio,
            "cond_layout": cond_layout,
            "cond_rows": [],
            "add_cond_btn": add_cond,
        }
        self._rows.append(row)

        add_cond.clicked.connect(lambda _, r=row: self._add_condition(r))
        reassign.clicked.connect(lambda _, r=row: self._reassign_image(r))
        remove.clicked.connect(lambda _, r=row: self._remove_row(r))

        for cond in condiciones:
            self._add_condition(row, cond.get("atributo", ""), cond.get("valor", ""))
        if not condiciones:
            # Siempre se ofrece una condición vacía para capturar. Marcar una
            # imagen como "por defecto" NO le quita la capacidad de tener
            # atributo/valor: la imagen por defecto también puede ser una variante.
            self._add_condition(row)

        # Insertar antes del stretch final.
        self._rows_layout.insertWidget(self._rows_layout.count() - 1, card)

    def _build_preview(self, imagen_path: str) -> QLabel:
        label = QLabel()
        label.setFixedSize(72, 46)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "border: 1px solid #E2E8F0; border-radius: 4px; "
            "background-color: #F8FAFC; color: #94A3B8; font-size: 9px;"
        )
        pix = None
        if imagen_path and Path(imagen_path).exists():
            cand = QPixmap(str(imagen_path))
            if not cand.isNull():
                pix = cand.scaled(
                    72, 46, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
        if pix is not None:
            label.setPixmap(pix)
        else:
            label.setText("sin\nvista")
            label.setToolTip("Vista previa no disponible")
        return label

    def _add_condition(self, row: dict, atributo: str = "", valor: str = ""):
        w = QWidget()
        fl = QHBoxLayout(w)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(8)

        combo = QComboBox()
        empty = len(self._available_attributes) == 0
        combo.setEditable(empty)
        if empty:
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            combo.lineEdit().setPlaceholderText("Nombre del atributo")
        else:
            combo.addItem("Selecciona un atributo…", "")
            for a in self._available_attributes:
                combo.addItem(a, a)
        if atributo:
            if combo.isEditable():
                combo.setEditText(atributo)
            else:
                i = combo.findData(atributo)
                if i < 0:
                    combo.addItem(atributo, atributo)
                    i = combo.findData(atributo)
                combo.setCurrentIndex(i)
        fl.addWidget(QLabel("Atributo:"))
        fl.addWidget(combo, 1)

        val = QLineEdit()
        val.setPlaceholderText("Valor")
        if valor:
            val.setText(valor)
        fl.addWidget(QLabel("igual a"))
        fl.addWidget(val, 1)

        rm = QPushButton()
        rm.setIcon(qta.icon("fa5s.times", color="#DC2626"))
        rm.setFixedSize(28, 28)
        rm.setToolTip("Quitar esta condición")
        rm.setStyleSheet("""
            QPushButton { background-color: #FFFFFF;
                border: 1px solid #FCA5A5; border-radius: 6px; }
            QPushButton:hover { background-color: #FEE2E2; }
        """)
        fl.addWidget(rm)

        cond = {"widget": w, "combo": combo, "val": val}
        row["cond_rows"].append(cond)
        row["cond_layout"].addWidget(w)
        rm.clicked.connect(lambda _, r=row, c=cond: self._remove_condition(r, c))

    def _remove_condition(self, row: dict, cond: dict):
        if cond in row["cond_rows"]:
            row["cond_rows"].remove(cond)
        cond["widget"].setParent(None)
        cond["widget"].deleteLater()

    def _on_default_toggled(self, _checked: bool):
        # Marcar una imagen como por defecto NO oculta sus condiciones: la
        # imagen por defecto también puede tener atributo/valor (ser variante).
        self._update_save_enabled()

    def _reassign_image(self, row: dict):
        path, _ = QFileDialog.getOpenFileName(
            self, "Reasignar imagen", str(Path.home()), _IMG_FILTER
        )
        if not path:
            return
        dest = self._copy_image(path)
        if dest is None:
            return
        row["imagen_path"] = str(dest)
        row["name_label"].setText(Path(dest).name)
        # Rehacer la vista previa: reconstruir la tarjeta es costoso; basta con
        # actualizar el tooltip del nombre. La miniatura se verá al reabrir.
        row["name_label"].setToolTip(str(dest))

    def _remove_row(self, row: dict):
        if len(self._rows) <= 1:
            self._show_status("Debe quedar al menos una imagen.", error=True)
            return
        self._rows.remove(row)
        self._default_group.removeButton(row["default_radio"])
        row["card"].setParent(None)
        row["card"].deleteLater()
        # Si se quitó la que era por defecto, marcar la primera restante.
        if not any(r["default_radio"].isChecked() for r in self._rows):
            self._rows[0]["default_radio"].setChecked(True)
        self._update_save_enabled()

    def _on_add_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Agregar imágenes de fondo", str(Path.home()), _IMG_FILTER
        )
        if not paths:
            return
        existentes = {r["imagen_path"] for r in self._rows}
        for p in paths:
            dest = self._copy_image(p)
            if dest is None:
                continue
            if str(dest) in existentes:
                continue
            self._add_row(str(dest), [], es_default=False)
            existentes.add(str(dest))
        self._update_save_enabled()

    def _copy_image(self, path_str: str) -> Path | None:
        """Copia la imagen a la carpeta estable de plantilla_base."""
        import shutil
        from credencializacion.utils.paths import get_plantilla_base_dir

        src = Path(path_str)
        dest_folder = get_plantilla_base_dir()
        dest = dest_folder / src.name
        if src.resolve() != dest.resolve():
            try:
                shutil.copy2(src, dest)
            except Exception as e:  # noqa: BLE001
                self._show_status(f"No se pudo copiar la imagen: {e}", error=True)
                return None
        return dest

    # ----------------------------------------------------- Guardado ---
    def _update_save_enabled(self):
        # Guardar habilitado si hay al menos una imagen y una marcada por defecto.
        tiene_default = any(r["default_radio"].isChecked() for r in self._rows)
        self._save_btn.setEnabled(bool(self._rows) and tiene_default)

    def _collect(self):
        """Devuelve (default_path, variantes:list[VarianteDTO], errores:list[str]).

        La imagen marcada por defecto fija ``default_path`` (fallback) y, si
        además tiene condiciones, también se incluye como variante. Las imágenes
        NO marcadas por defecto deben tener al menos una condición completa.
        """
        errores: list[str] = []
        default_path: str | None = None
        variantes: list[VarianteDTO] = []
        condition_sets: list[frozenset] = []

        orden = 0
        for row in self._rows:
            is_default = row["default_radio"].isChecked()
            if is_default:
                default_path = row["imagen_path"]

            nombre = Path(row["imagen_path"]).name
            conds: list[CondicionDTO] = []
            pares = set()
            for cond in row["cond_rows"]:
                attr = (
                    cond["combo"].currentText().strip()
                    if cond["combo"].isEditable()
                    else (cond["combo"].currentData() or "").strip()
                )
                val = cond["val"].text().strip()
                if not attr and not val:
                    continue
                ar = validate_atributo_length(attr)
                vr = validate_valor_length(val)
                if not ar.ok:
                    errores.extend(f"[{nombre}] {m}" for m in ar.errors)
                if not vr.ok:
                    errores.extend(f"[{nombre}] {m}" for m in vr.errors)
                if ar.ok and vr.ok:
                    conds.append(CondicionDTO(attr, val, len(conds)))
                    pares.add((attr.lower(), val.lower()))

            if conds:
                cs = frozenset(pares)
                if cs in condition_sets:
                    errores.append(
                        f"[{nombre}] Conjunto de condiciones duplicado con otra "
                        "imagen."
                    )
                condition_sets.append(cs)
                variantes.append(VarianteDTO(row["imagen_path"], orden, tuple(conds)))
                orden += 1
            elif not is_default:
                errores.append(
                    f"[{nombre}] Define al menos una condición (atributo y valor) "
                    "o márcala como imagen por defecto."
                )

        if default_path is None:
            errores.append("Marca una imagen como imagen por defecto.")
        return default_path, variantes, errores

    def _on_save(self):
        default_path, variantes, errores = self._collect()
        if errores:
            QMessageBox.warning(
                self, "Revisa la configuración",
                "Corrige lo siguiente antes de guardar:\n\n"
                + "\n".join(f"• {e}" for e in errores),
            )
            self._show_status("No se pudo guardar: corrige los errores.", error=True)
            return

        try:
            with DatabaseSession() as session:
                LadoConfigRepository.save_config_lado(
                    session, self.plantilla_id, self.lado, variantes, default_path
                )
                # Reflejar la imagen por defecto en Plantilla.recursos[fondo_lado]
                # para el diseñador y la vista previa.
                self._reflect_default_in_plantilla(session, default_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, "Error al guardar",
                "No se pudo guardar la configuración. Tus cambios siguen en "
                f"pantalla.\n\nDetalle: {exc}",
            )
            self._show_status(f"No se pudo guardar: {exc}", error=True)
            return

        self.config_saved.emit(self.plantilla_id, self.lado)
        self.accept()

    def _reflect_default_in_plantilla(self, session, default_path: str | None):
        from credencializacion.db.models import Plantilla
        from sqlalchemy.orm.attributes import flag_modified

        if not default_path:
            return
        plantilla = session.query(Plantilla).get(self.plantilla_id)
        if plantilla is None:
            return
        recursos = dict(plantilla.recursos or {})
        recursos[f"fondo_{self.lado}"] = default_path
        plantilla.recursos = recursos
        flag_modified(plantilla, "recursos")

    def _on_delete_config(self):
        reply = QMessageBox.question(
            self, "Eliminar configuración",
            f"¿Eliminar la configuración de multiplantillaje del lado "
            f"{self.lado}?\n\nPodrás volver a asignar la imagen base desde "
            f"{self.lado.upper()}.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            with DatabaseSession() as session:
                LadoConfigRepository.delete_config_lado(
                    session, self.plantilla_id, self.lado
                )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, "Error al eliminar",
                f"No se pudo eliminar la configuración.\n\nDetalle: {exc}",
            )
            return
        self.config_deleted.emit(self.plantilla_id, self.lado)
        self.accept()

    def _show_status(self, message: str, *, error: bool = False):
        color = "#DC2626" if error else "#64748B"
        self._status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._status_label.setText(message)
        self._status_label.setVisible(True)
