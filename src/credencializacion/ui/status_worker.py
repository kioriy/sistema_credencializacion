"""Worker en segundo plano para marcar el estatus de credenciales en la API.

Evita bloquear la UI al hacer los POST a los endpoints de marcado en lote
(``bulk-mark-printing`` / ``bulk-mark-ready``).
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class BulkMarkWorker(QThread):
    """Marca credenciales como 'En impresión' o 'Listas' sin bloquear la UI.

    Args:
        base_url: URL base de la API.
        api_key: Clave ``X-Credential-Key``.
        action: ``"printing"`` o ``"ready"``.
        student_ids: IDs de alumno (campo ``id`` del API).
        authorized_person_ids: IDs de autorizado (tarjetas de autorizado). No
            mueven el estatus del alumno.
    """

    # success, message, actualizados (alumnos + autorizados)
    done = Signal(bool, str, int)

    def __init__(
        self,
        base_url: str,
        api_key: str,
        action: str,
        student_ids: list[int],
        authorized_person_ids: list[int] | None = None,
    ) -> None:
        super().__init__()
        self._base_url = base_url
        self._api_key = api_key
        self._action = action
        self._student_ids = list(student_ids)
        self._authorized_ids = list(authorized_person_ids or [])

    def run(self) -> None:  # noqa: D401
        from credencializacion.adapters.miescuela import MiEscuelaAdapter

        try:
            adapter = MiEscuelaAdapter(self._base_url, self._api_key)
            if self._action == "ready":
                resp = adapter.mark_ready(self._student_ids, self._authorized_ids)
            else:
                resp = adapter.mark_printing(self._student_ids, self._authorized_ids)
            actualizados = int(resp.get("updated", len(self._student_ids)) or 0)
            if self._authorized_ids:
                actualizados += int(
                    resp.get("authorized_updated", len(self._authorized_ids)) or 0
                )
            mensaje = str(resp.get("message", ""))
            omitidos = resp.get("authorized_skipped") or []
            if omitidos:
                logger.warning(
                    "Autorizados no marcados (%s): %s", self._action, omitidos,
                )
                mensaje += f" ({len(omitidos)} autorizado(s) omitido(s))"
            self.done.emit(bool(resp.get("success", True)), mensaje, actualizados)
        except Exception as e:  # noqa: BLE001
            logger.error("Error al marcar estatus (%s): %s", self._action, e)
            self.done.emit(False, str(e), 0)


class ReposicionesWorker(QThread):
    """Consulta en segundo plano las reposiciones pendientes de una escuela.

    Emite ``finished_ok`` con ``(school_id, alumnos, con_autorizados)`` —ambas
    listas ya aplanadas por el adaptador— para que la UI cuente o cargue la
    cola. ``school_id`` viaja con el resultado para descartar respuestas de
    una escuela que el usuario ya dejó de ver.
    """

    finished_ok = Signal(int, list, list)
    failed = Signal(int, str)

    def __init__(self, base_url: str, api_key: str, school_id: int) -> None:
        super().__init__()
        self._base_url = base_url
        self._api_key = api_key
        self._school_id = int(school_id)

    def run(self) -> None:  # noqa: D401
        from credencializacion.adapters.miescuela import MiEscuelaAdapter

        try:
            adapter = MiEscuelaAdapter(self._base_url, self._api_key)
            alumnos, con_autorizados = adapter.fetch_reposiciones(self._school_id)
            self.finished_ok.emit(self._school_id, alumnos, con_autorizados)
        except Exception as e:  # noqa: BLE001
            logger.error("Error al consultar reposiciones: %s", e)
            self.failed.emit(self._school_id, str(e))
