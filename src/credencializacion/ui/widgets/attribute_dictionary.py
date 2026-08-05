"""
Sección de Configuración: diccionario de atributos y reconciliación.

Reúne en un solo lugar las tres cosas que hacen falta para que ningún dato se
pierda por cómo lo nombre el origen:

1. **Bandeja de claves sin clasificar** — lo que está llegando y todavía nadie
   asignó a un atributo. Es lo que convierte el problema de silencioso en
   visible.
2. **CRUD del diccionario** — atributos canónicos y las definiciones que
   apuntan a cada uno. Cambiar un país no significa tocar las cabeceras del
   origen, sino agregar aquí su palabra (``ine``, ``dni``, ``cedula``).
3. **Reconciliación de plantillas** — reescribe las configuraciones guardadas
   para que usen el nombre canónico, con vista previa y deshacer.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from credencializacion.db.engine import DatabaseSession
from credencializacion.services import diccionario as dic
from credencializacion.services import reconciliacion as rec
from credencializacion.ui.styles import COLORS

logger = logging.getLogger(__name__)


class _VistaPreviaDialog(QDialog):
    """Muestra el plan de reconciliación antes de aplicarlo."""

    def __init__(self, plan: rec.Plan, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Vista previa de la reconciliación")
        self.setMinimumSize(760, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        encabezado = QLabel(
            f"Se actualizarán <b>{plan.total_cambios}</b> referencia(s). "
            "Nada se aplica hasta que confirmes, y podrás deshacerlo después."
        )
        encabezado.setWordWrap(True)
        layout.addWidget(encabezado)

        tabla = QTableWidget()
        filas = len(plan.cambios_elemento) + len(plan.cambios_condicion)
        tabla.setRowCount(filas)
        tabla.setColumnCount(4)
        tabla.setHorizontalHeaderLabels(["Dónde", "Elemento", "Actual", "Nuevo"])
        tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabla.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        fila = 0
        for cambio in plan.cambios_elemento:
            origen = (
                "texto compuesto" if cambio.origen == "texto_compuesto" else "campo"
            )
            tabla.setItem(fila, 0, QTableWidgetItem(
                f"{cambio.plantilla_nombre} · {cambio.lado}"
            ))
            tabla.setItem(fila, 1, QTableWidgetItem(
                f"{cambio.etiqueta} ({origen})"
            ))
            tabla.setItem(fila, 2, QTableWidgetItem(cambio.actual))
            tabla.setItem(fila, 3, QTableWidgetItem(cambio.nuevo))
            fila += 1
        for cambio in plan.cambios_condicion:
            tabla.setItem(fila, 0, QTableWidgetItem(
                f"{cambio.plantilla_nombre} · {cambio.lado}"
            ))
            tabla.setItem(fila, 1, QTableWidgetItem(
                f"fondo condicional (= {cambio.valor})"
            ))
            tabla.setItem(fila, 2, QTableWidgetItem(cambio.actual))
            tabla.setItem(fila, 3, QTableWidgetItem(cambio.nuevo))
            fila += 1

        layout.addWidget(tabla)

        if plan.huerfanos:
            aviso = QLabel(
                f"⚠ {len(plan.huerfanos)} referencia(s) apuntan a claves que el "
                "diccionario no reconoce. No se tocan: defínelas arriba y vuelve "
                "a analizar."
            )
            aviso.setWordWrap(True)
            aviso.setStyleSheet(f"color: {COLORS['warning']}; font-size: 12px;")
            layout.addWidget(aviso)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        botones.button(QDialogButtonBox.StandardButton.Ok).setText("Aplicar")
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)


class AttributeDictionaryGroup(QGroupBox):
    """Sección completa de administración del diccionario de atributos."""

    diccionario_cambiado = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Diccionario de Atributos", parent)
        self._atributo_id: int | None = None
        self._ultimo_respaldo: int | None = None
        self._setup_ui()
        self.recargar()

    # ── Construcción ─────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setSpacing(12)

        ayuda = QLabel(
            "Cada atributo canónico es el nombre único con el que las plantillas "
            "se refieren a un dato. Las definiciones son las palabras con que "
            "cada origen o país lo nombra: agregar «ine» o «dni» aquí evita "
            "tener que modificar las cabeceras del origen."
        )
        ayuda.setWordWrap(True)
        ayuda.setStyleSheet(f"color: {COLORS['text_light']}; font-size: 12px;")
        raiz.addWidget(ayuda)

        raiz.addWidget(self._construir_bandeja())
        raiz.addLayout(self._construir_paneles())
        raiz.addWidget(self._construir_reconciliacion())

    def _construir_bandeja(self) -> QWidget:
        caja = QWidget()
        caja.setStyleSheet(
            f"background: {COLORS['warning_bg']}; border: 1px solid "
            f"{COLORS['warning']}; border-radius: 6px;"
        )
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        self._lbl_bandeja = QLabel()
        self._lbl_bandeja.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 12px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        lay.addWidget(self._lbl_bandeja)

        fila = QHBoxLayout()
        self._cb_sin_clasificar = QComboBox()
        self._cb_sin_clasificar.setMinimumWidth(220)
        fila.addWidget(self._cb_sin_clasificar, 2)

        fila.addWidget(QLabel("→"))

        self._cb_destino = QComboBox()
        self._cb_destino.setMinimumWidth(220)
        fila.addWidget(self._cb_destino, 2)

        btn_asignar = QPushButton("Asignar")
        btn_asignar.clicked.connect(self._asignar_sin_clasificar)
        fila.addWidget(btn_asignar)
        fila.addStretch()
        lay.addLayout(fila)

        self._caja_bandeja = caja
        return caja

    def _construir_paneles(self) -> QHBoxLayout:
        fila = QHBoxLayout()
        fila.setSpacing(16)

        # ── Izquierda: atributos canónicos ──
        izq = QVBoxLayout()
        izq.setSpacing(6)
        izq.addWidget(QLabel("<b>Atributos</b>"))

        self._buscador = QLineEdit()
        self._buscador.setPlaceholderText("Buscar atributo o definición…")
        self._buscador.textChanged.connect(self._filtrar)
        izq.addWidget(self._buscador)

        self._lista_atributos = QListWidget()
        self._lista_atributos.setMinimumHeight(240)
        self._lista_atributos.currentItemChanged.connect(self._seleccionar)
        izq.addWidget(self._lista_atributos)

        acciones_attr = QHBoxLayout()
        self._edit_nuevo = QLineEdit()
        self._edit_nuevo.setPlaceholderText("nuevo_atributo")
        self._edit_nuevo.returnPressed.connect(self._crear_atributo)
        acciones_attr.addWidget(self._edit_nuevo)
        btn_crear = QPushButton("Crear")
        btn_crear.clicked.connect(self._crear_atributo)
        acciones_attr.addWidget(btn_crear)
        izq.addLayout(acciones_attr)

        fila.addLayout(izq, 1)

        # ── Derecha: definiciones del seleccionado ──
        der = QVBoxLayout()
        der.setSpacing(6)

        self._lbl_detalle = QLabel("<b>Definiciones</b>")
        der.addWidget(self._lbl_detalle)

        self._lbl_ancla = QLabel()
        self._lbl_ancla.setWordWrap(True)
        self._lbl_ancla.setStyleSheet(
            f"color: {COLORS['text_light']}; font-size: 11px;"
        )
        der.addWidget(self._lbl_ancla)

        self._lista_definiciones = QListWidget()
        self._lista_definiciones.setMinimumHeight(200)
        der.addWidget(self._lista_definiciones)

        agregar = QHBoxLayout()
        self._edit_definicion = QLineEdit()
        self._edit_definicion.setPlaceholderText("nueva definición (ej. ine)")
        self._edit_definicion.returnPressed.connect(self._agregar_definicion)
        agregar.addWidget(self._edit_definicion)
        btn_agregar = QPushButton("Agregar")
        btn_agregar.clicked.connect(self._agregar_definicion)
        agregar.addWidget(btn_agregar)
        btn_quitar = QPushButton("Quitar")
        btn_quitar.clicked.connect(self._quitar_definicion)
        agregar.addWidget(btn_quitar)
        der.addLayout(agregar)

        opciones = QHBoxLayout()
        self._chk_visible = QCheckBox("Mostrar en el diseñador")
        self._chk_visible.clicked.connect(self._cambiar_visibilidad)
        opciones.addWidget(self._chk_visible)
        opciones.addStretch()
        self._btn_renombrar = QPushButton("Renombrar…")
        self._btn_renombrar.clicked.connect(self._renombrar_atributo)
        opciones.addWidget(self._btn_renombrar)
        self._btn_eliminar = QPushButton("Eliminar")
        self._btn_eliminar.clicked.connect(self._eliminar_atributo)
        opciones.addWidget(self._btn_eliminar)
        der.addLayout(opciones)

        fila.addLayout(der, 1)
        return fila

    def _construir_reconciliacion(self) -> QWidget:
        caja = QWidget()
        caja.setStyleSheet(
            f"background: {COLORS['info_bg']}; border: 1px solid "
            f"{COLORS['border']}; border-radius: 6px;"
        )
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        titulo = QLabel("<b>Reconciliación de plantillas</b>")
        titulo.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(titulo)

        detalle = QLabel(
            "Reescribe las plantillas y las condiciones de fondo para que usen "
            "el nombre canónico en lugar de una de sus definiciones. Se puede "
            "ejecutar cuantas veces haga falta: siempre se calcula contra el "
            "diccionario vigente. Las plantillas siguen imprimiendo bien aunque "
            "no se reconcilien."
        )
        detalle.setWordWrap(True)
        detalle.setStyleSheet(
            f"color: {COLORS['text_light']}; font-size: 11px; "
            "background: transparent; border: none;"
        )
        lay.addWidget(detalle)

        self._lbl_estado = QLabel("—")
        self._lbl_estado.setWordWrap(True)
        self._lbl_estado.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 12px; "
            "background: transparent; border: none;"
        )
        lay.addWidget(self._lbl_estado)

        fila = QHBoxLayout()
        btn_analizar = QPushButton("Analizar")
        btn_analizar.clicked.connect(self._analizar)
        fila.addWidget(btn_analizar)

        self._btn_aplicar = QPushButton("Reconciliar…")
        self._btn_aplicar.setProperty("variant", "primary")
        self._btn_aplicar.clicked.connect(self._reconciliar)
        fila.addWidget(self._btn_aplicar)

        self._btn_deshacer = QPushButton("Deshacer última")
        self._btn_deshacer.clicked.connect(self._deshacer)
        self._btn_deshacer.setEnabled(False)
        fila.addWidget(self._btn_deshacer)
        fila.addStretch()
        lay.addLayout(fila)
        return caja

    # ── Carga ────────────────────────────────────────────────────────

    def recargar(self) -> None:
        """Recarga atributos, bandeja y estado de reconciliación."""
        seleccionado = self._atributo_id
        indice = dic.obtener_indice()

        self._lista_atributos.clear()
        for attr in indice.atributos:
            texto = f"{attr.icono}  {attr.etiqueta}" if attr.icono else attr.etiqueta
            sufijo = f"  ·  {len(attr.definiciones)}"
            if attr.es_sistema:
                sufijo += "  🔒"
            item = QListWidgetItem(f"{texto}{sufijo}")
            item.setData(Qt.ItemDataRole.UserRole, attr.id)
            item.setToolTip(
                f"{attr.nombre}\nDefiniciones: "
                + (", ".join(attr.definiciones) or "—")
            )
            self._lista_atributos.addItem(item)
            if attr.id == seleccionado:
                self._lista_atributos.setCurrentItem(item)

        if self._lista_atributos.currentItem() is None and self._lista_atributos.count():
            self._lista_atributos.setCurrentRow(0)

        self._cb_destino.clear()
        for attr in indice.atributos:
            self._cb_destino.addItem(attr.etiqueta or attr.nombre, attr.id)

        self._recargar_bandeja(indice)
        self._analizar(silencioso=True)
        self._filtrar(self._buscador.text())

    def _recargar_bandeja(self, indice: dic.Indice) -> None:
        """Lista las claves que llegan del origen y no pertenecen a nadie."""
        from credencializacion.db.models import Cliente

        crudas: list[str] = []
        try:
            with DatabaseSession() as session:
                for cliente in session.query(Cliente).all():
                    conocidas = (cliente.config or {}).get("known_attributes") or []
                    if isinstance(conocidas, dict):
                        conocidas = list(conocidas.keys())
                    if isinstance(conocidas, (list, tuple)):
                        crudas.extend(str(c) for c in conocidas)
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo leer el catálogo de los clientes: %s", exc)

        pendientes = dic.claves_sin_clasificar(crudas, indice)

        self._cb_sin_clasificar.clear()
        for clave in pendientes:
            self._cb_sin_clasificar.addItem(clave, clave)

        self._lbl_bandeja.setText(
            f"⚠ {len(pendientes)} clave(s) sin clasificar — están llegando "
            "del origen y no pertenecen a ningún atributo."
        )
        # Sin pendientes la caja se oculta: es una alerta, no un panel fijo.
        self._caja_bandeja.setVisible(bool(pendientes))

    def _filtrar(self, texto: str) -> None:
        consulta = dic.normalizar(texto)
        indice = dic.obtener_indice()
        por_id = {a.id: a for a in indice.atributos}
        for i in range(self._lista_atributos.count()):
            item = self._lista_atributos.item(i)
            attr = por_id.get(item.data(Qt.ItemDataRole.UserRole))
            if attr is None:
                continue
            visible = (
                not consulta
                or consulta in dic.normalizar(attr.nombre)
                or consulta in dic.normalizar(attr.etiqueta)
                or any(consulta in dic.normalizar(d) for d in attr.definiciones)
            )
            item.setHidden(not visible)

    def _seleccionar(self, item: QListWidgetItem | None, _previo=None) -> None:
        self._lista_definiciones.clear()
        if item is None:
            self._atributo_id = None
            return

        self._atributo_id = item.data(Qt.ItemDataRole.UserRole)
        indice = dic.obtener_indice()
        attr = next(
            (a for a in indice.atributos if a.id == self._atributo_id), None
        )
        if attr is None:
            return

        self._lbl_detalle.setText(
            f"<b>Definiciones de «{attr.nombre}»</b>"
        )
        for definicion in attr.definiciones:
            self._lista_definiciones.addItem(definicion)

        self._chk_visible.setChecked(attr.visible)
        self._btn_renombrar.setEnabled(not attr.es_sistema)
        self._btn_eliminar.setEnabled(not attr.es_sistema)
        if attr.es_sistema:
            self._lbl_ancla.setText(
                "🔒 Atributo ancla: el motor lo referencia por este nombre, así "
                "que no puede renombrarse ni eliminarse. Sus definiciones sí son "
                "editables — es lo que permite adaptarlo a otro país."
            )
        else:
            self._lbl_ancla.setText("")

    # ── Operaciones ──────────────────────────────────────────────────

    def _error(self, mensaje: str) -> None:
        QMessageBox.warning(self, "Diccionario de atributos", mensaje)

    def _notificar_cambio(self) -> None:
        self.recargar()
        self.diccionario_cambiado.emit()

    def _crear_atributo(self) -> None:
        nombre = self._edit_nuevo.text().strip()
        if not nombre:
            return
        try:
            with DatabaseSession() as session:
                dic.crear_atributo(session, nombre, etiqueta=nombre)
        except dic.ErrorDiccionario as exc:
            self._error(str(exc))
            return
        self._edit_nuevo.clear()
        self._notificar_cambio()

    def _renombrar_atributo(self) -> None:
        if self._atributo_id is None:
            return
        nuevo = self._edit_nuevo.text().strip()
        if not nuevo:
            self._error(
                "Escribe el nombre nuevo en el campo de la izquierda y vuelve a "
                "pulsar Renombrar."
            )
            return
        try:
            with DatabaseSession() as session:
                dic.renombrar_atributo(session, self._atributo_id, nuevo)
        except dic.ErrorDiccionario as exc:
            self._error(str(exc))
            return
        self._edit_nuevo.clear()
        QMessageBox.information(
            self, "Diccionario de atributos",
            "Atributo renombrado. Ejecuta la reconciliación para que las "
            "plantillas que lo usaban apunten al nombre nuevo.",
        )
        self._notificar_cambio()

    def _eliminar_atributo(self) -> None:
        if self._atributo_id is None:
            return
        confirmar = QMessageBox.question(
            self, "Eliminar atributo",
            "Se eliminará el atributo y sus definiciones volverán a la bandeja "
            "de sin clasificar. Los datos de los registros no se tocan.\n\n"
            "¿Continuar?",
        )
        if confirmar != QMessageBox.StandardButton.Yes:
            return
        try:
            with DatabaseSession() as session:
                dic.eliminar_atributo(session, self._atributo_id)
        except dic.ErrorDiccionario as exc:
            self._error(str(exc))
            return
        self._atributo_id = None
        self._notificar_cambio()

    def _agregar_definicion(self, alias: str | None = None) -> None:
        if self._atributo_id is None:
            return
        texto = alias if isinstance(alias, str) and alias else self._edit_definicion.text()
        texto = texto.strip()
        if not texto:
            return
        try:
            with DatabaseSession() as session:
                dic.agregar_definicion(session, self._atributo_id, texto)
        except dic.ErrorDiccionario as exc:
            respuesta = QMessageBox.question(
                self, "Definición en uso",
                f"{exc}\n\n¿Moverla a este atributo?",
            )
            if respuesta != QMessageBox.StandardButton.Yes:
                return
            try:
                with DatabaseSession() as session:
                    dic.agregar_definicion(
                        session, self._atributo_id, texto, mover=True,
                    )
            except dic.ErrorDiccionario as exc2:
                self._error(str(exc2))
                return
        self._edit_definicion.clear()
        self._notificar_cambio()

    def _quitar_definicion(self) -> None:
        if self._atributo_id is None:
            return
        item = self._lista_definiciones.currentItem()
        if item is None:
            self._error("Selecciona la definición que quieres quitar.")
            return
        with DatabaseSession() as session:
            dic.quitar_definicion(session, self._atributo_id, item.text())
        self._notificar_cambio()

    def _cambiar_visibilidad(self) -> None:
        if self._atributo_id is None:
            return
        with DatabaseSession() as session:
            dic.fijar_visibilidad(
                session, self._atributo_id, self._chk_visible.isChecked(),
            )
        self.diccionario_cambiado.emit()

    def _asignar_sin_clasificar(self) -> None:
        clave = self._cb_sin_clasificar.currentData()
        destino = self._cb_destino.currentData()
        if not clave or destino is None:
            return
        try:
            with DatabaseSession() as session:
                dic.agregar_definicion(session, int(destino), str(clave))
        except dic.ErrorDiccionario as exc:
            self._error(str(exc))
            return
        self._notificar_cambio()

    # ── Reconciliación ───────────────────────────────────────────────

    def _analizar(self, silencioso: bool = False) -> rec.Plan | None:
        try:
            with DatabaseSession() as session:
                plan = rec.planificar(session)
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo analizar la reconciliación: %s", exc)
            self._lbl_estado.setText("No se pudo analizar el estado.")
            return None

        self._lbl_estado.setText(plan.resumen())
        self._btn_aplicar.setEnabled(not plan.vacio)
        if not silencioso and plan.vacio:
            QMessageBox.information(
                self, "Reconciliación",
                "No hay nada que reconciliar: todas las plantillas ya usan los "
                "nombres canónicos.",
            )
        return plan

    def _reconciliar(self) -> None:
        plan = self._analizar(silencioso=True)
        if plan is None or plan.vacio:
            return

        dialogo = _VistaPreviaDialog(plan, self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return

        with DatabaseSession() as session:
            resultado = rec.aplicar(session, plan, "desde Configuración")

        self._ultimo_respaldo = resultado.respaldo_id
        self._btn_deshacer.setEnabled(resultado.respaldo_id is not None)
        QMessageBox.information(
            self, "Reconciliación",
            f"Listo: {resultado.elementos} elemento(s) y "
            f"{resultado.condiciones} condición(es) actualizadas.",
        )
        self._analizar(silencioso=True)
        self.diccionario_cambiado.emit()

    def _deshacer(self) -> None:
        if self._ultimo_respaldo is None:
            return
        with DatabaseSession() as session:
            revertido = rec.deshacer(session, self._ultimo_respaldo)
        if revertido:
            QMessageBox.information(
                self, "Reconciliación", "Se restauró el estado anterior.",
            )
        self._ultimo_respaldo = None
        self._btn_deshacer.setEnabled(False)
        self._analizar(silencioso=True)
        self.diccionario_cambiado.emit()
