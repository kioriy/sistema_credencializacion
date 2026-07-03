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
                )

                self.progress.emit("🖼 Generando PDF de vueltas...")
                vueltas_pdf = engine.render_queue(
                    render_items, "vuelta", out_dir / "vueltas.pdf",
                    fondo_overrides=_overrides("vuelta"),
                )

            self.finished_ok.emit(str(frentes_pdf), str(vueltas_pdf))
        except Exception as e:  # noqa: BLE001
            logger.error("Error al renderizar cola en segundo plano: %s", e)
            self.failed.emit(str(e))
