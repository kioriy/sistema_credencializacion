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
    """

    done = Signal(bool, str, int)  # success, message, updated

    def __init__(
        self,
        base_url: str,
        api_key: str,
        action: str,
        student_ids: list[int],
    ) -> None:
        super().__init__()
        self._base_url = base_url
        self._api_key = api_key
        self._action = action
        self._student_ids = list(student_ids)

    def run(self) -> None:  # noqa: D401
        from credencializacion.adapters.miescuela import MiEscuelaAdapter

        try:
            adapter = MiEscuelaAdapter(self._base_url, self._api_key)
            if self._action == "ready":
                resp = adapter.mark_ready(self._student_ids)
            else:
                resp = adapter.mark_printing(self._student_ids)
            self.done.emit(
                bool(resp.get("success", True)),
                str(resp.get("message", "")),
                int(resp.get("updated", len(self._student_ids))),
            )
        except Exception as e:  # noqa: BLE001
            logger.error("Error al marcar estatus (%s): %s", self._action, e)
            self.done.emit(False, str(e), 0)
