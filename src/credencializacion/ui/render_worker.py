"""
Worker compartido para renderizar los PDFs de una cola de impresión.

Usado por el Panel de Control (al enviar una cola al Centro de Impresión)
y por el Centro de Impresión (al actualizar o copiar una cola).
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class QueueRenderWorker(QThread):
    """Renderiza en segundo plano los PDFs (frentes y vueltas) de una cola.

    Trabaja con IDs de registro + id de plantilla y produce dos PDFs (2 diseños
    por hoja) en ``out_dir``. Abre su propia sesión de BD (solo lectura) en el
    hilo del worker. Emite ``progress`` con mensajes de estado para el footer,
    ``finished_ok`` con las rutas resultantes y ``failed`` ante un error.
    """

    progress = Signal(str)
    finished_ok = Signal(str, str)  # frentes_pdf, vueltas_pdf
    failed = Signal(str)
    # Registros que no se imprimieron y por qué (atributo requerido faltante o
    # hermano ya representado por otra credencial de la misma familia).
    omitidos = Signal(dict)

    def __init__(self, record_ids: list[int], plantilla_id: int, out_dir: str) -> None:
        super().__init__()
        self._record_ids = list(record_ids)
        self._plantilla_id = plantilla_id
        self._out_dir = out_dir

    def run(self) -> None:  # noqa: D401
        try:
            from pathlib import Path
            from credencializacion.db.engine import DatabaseSession
            from credencializacion.db.models import Plantilla, Registro
            from credencializacion.db.repositories import LadoConfigRepository
            from credencializacion.services.image_selection import select_imagen
            from credencializacion.renderer.pdf_engine import PDFEngine

            out_dir = Path(self._out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)

            with DatabaseSession() as session:
                plantilla = session.query(Plantilla).get(self._plantilla_id)
                if plantilla is None:
                    self.failed.emit("Plantilla no encontrada")
                    return

                regs_by_id = {
                    r.id: r
                    for r in session.query(Registro)
                    .filter(Registro.id.in_(self._record_ids))
                    .all()
                }
                render_items = [
                    (regs_by_id[i], plantilla)
                    for i in self._record_ids
                    if i in regs_by_id
                ]
                if not render_items:
                    self.failed.emit("No hay registros para renderizar")
                    return

                # ── Reglas de impresión ────────────────────────────────
                # Se aplican UNA sola vez y el resultado alimenta las dos
                # caras: si cada cara filtrara por su cuenta, los frentes y
                # las vueltas quedarían desalineados al voltear la hoja.
                render_items, extras, reporte = self._aplicar_reglas(
                    session, plantilla, render_items
                )
                if not render_items:
                    self.failed.emit(
                        "Ningún registro cumple los atributos requeridos "
                        "para impresión"
                    )
                    return
                if reporte["sin_requeridos"] or reporte["hermanos_colapsados"]:
                    self.omitidos.emit(reporte)

                def _overrides(cara: str) -> list[str | None]:
                    cfg = LadoConfigRepository.get_config_lado(
                        session, self._plantilla_id, cara
                    )
                    if cfg is None:
                        return [None] * len(render_items)
                    return [
                        select_imagen(reg.datos or {}, cfg)
                        for reg, _ in render_items
                    ]

                engine = PDFEngine(plantilla)

                self.progress.emit("🖼 Generando PDF de frentes...")
                frentes_pdf = engine.render_queue(
                    render_items, "frente", out_dir / "frentes.pdf",
                    fondo_overrides=_overrides("frente"),
                    datos_extra=extras,
                )

                self.progress.emit("🖼 Generando PDF de vueltas...")
                vueltas_pdf = engine.render_queue(
                    render_items, "vuelta", out_dir / "vueltas.pdf",
                    fondo_overrides=_overrides("vuelta"),
                    datos_extra=extras,
                )

            self.finished_ok.emit(str(frentes_pdf), str(vueltas_pdf))
        except Exception as e:  # noqa: BLE001
            logger.error("Error al renderizar cola en segundo plano: %s", e)
            self.failed.emit(str(e))

    @staticmethod
    def _aplicar_reglas(session, plantilla, render_items):
        """Aplica las reglas de impresión antes de renderizar.

        Orden de ejecución:

        1. Si el diseño usa slots de hermanos, se colapsan las familias
           (una sola credencial por familia, la primera de la cola).
        2. Se resuelven las fotos de hermanos de cada registro consultando
           TODOS los alumnos del cliente que comparten ``tutor_email``, no
           solo los que estén en la cola: la credencial de autorizado debe
           mostrar a todos los alumnos que esa persona puede recoger.
        3. Se descartan los registros que no cumplen los atributos marcados
           como requeridos, evaluando frente y vuelta en conjunto.

        Returns:
            ``(items_finales, extras_alineados, reporte)``
        """
        from credencializacion.db.models import Registro
        from credencializacion.services import print_rules

        reporte: dict[str, list] = {"sin_requeridos": [], "hermanos_colapsados": []}

        # 1. Colapsado por familia (solo si el diseño usa slots de hermanos).
        if print_rules.template_uses_sibling_slots(plantilla):
            indices, descartados = print_rules.collapse_families(render_items)
            if descartados:
                render_items = [render_items[i] for i in indices]
                reporte["hermanos_colapsados"] = [
                    reg.nombre_completo or reg.enrollment_code or f"#{reg.id}"
                    for reg, _ in descartados
                ]

        # 2. Fotos de hermanos: se agrupan por tutor TODOS los registros del
        #    cliente, no solo los encolados.
        cliente_ids = {
            getattr(reg, "cliente_id", None) for reg, _ in render_items
        }
        cliente_ids.discard(None)
        universo = (
            session.query(Registro)
            .filter(Registro.cliente_id.in_(cliente_ids))
            .all()
            if cliente_ids
            else []
        )
        grupos = print_rules.group_by_tutor(universo)

        # Orden visual de los slots de hermano en la plantilla: los hermanos se
        # asignan siguiendo la disposición del diseño (izquierda→derecha,
        # arriba→abajo), no por el número del atributo. Evita el hueco cuando
        # el usuario coloca los slots en orden distinto al numérico.
        slot_order = print_rules.template_sibling_slots_in_order(plantilla)

        extras = [
            print_rules.sibling_photo_extras(reg, grupos, slot_order)
            for reg, _ in render_items
        ]

        # 3. Atributos requeridos, evaluando ambas caras en conjunto.
        elementos_ambas_caras = list(plantilla.elementos_frente or []) + list(
            plantilla.elementos_vuelta or []
        )
        items_ok: list = []
        extras_ok: list[dict] = []
        for (reg, pla), extra in zip(render_items, extras):
            faltantes = print_rules.missing_required_attributes(
                elementos_ambas_caras, reg, extra
            )
            if faltantes:
                nombre = reg.nombre_completo or reg.enrollment_code or f"#{reg.id}"
                reporte["sin_requeridos"].append((nombre, faltantes))
                logger.info(
                    "Omitiendo registro id=%s ('%s'): faltan atributos "
                    "requeridos para impresión: %s",
                    reg.id, nombre, ", ".join(faltantes),
                )
                continue
            items_ok.append((reg, pla))
            extras_ok.append(extra)

        return items_ok, extras_ok, reporte
