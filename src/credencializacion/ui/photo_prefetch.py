"""
Prefetch en segundo plano de las fotos de una escuela a la caché de disco.

Las fotos del servidor son chicas (~30 KB) pero su latencia por petición es
alta e inconsistente (0.2–8 s). Descargar solo las de la página visible deja
al usuario esperando cada vez que pagina. Este worker descarga TODAS las fotos
del cliente a la caché en disco en paralelo (varias conexiones a la vez), de
modo que tras un llenado inicial la navegación sea instantánea.

El worker NO toca la UI ni QPixmap: solo escribe bytes a disco y emite señales
de progreso. La aplicación de las fotos a la tabla la sigue haciendo el hilo
principal desde la caché (memoria/disco).
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)

# Conexiones simultáneas al servidor de fotos. Sube la concurrencia respecto
# al límite de QNetworkAccessManager (6/host) sin saturar al servidor.
_MAX_WORKERS = 10
_TIMEOUT = (10, 30)  # (conexión, lectura) en segundos


class PhotoPrefetchWorker(QThread):
    """Descarga a disco las fotos que aún no estén cacheadas.

    Emite ``progress(descargadas, total)`` conforme avanza y ``finished_ok``
    al terminar. Se puede detener con ``stop()`` (al cambiar de escuela).
    """

    progress = Signal(int, int)
    finished_ok = Signal()

    def __init__(self, urls: list[str], disk_path_for: Callable[[str], Path]) -> None:
        super().__init__()
        self._urls = list(urls)
        self._disk_path_for = disk_path_for
        self._stop = False

    def stop(self) -> None:
        """Solicita cancelar la descarga (las tareas pendientes se omiten)."""
        self._stop = True

    def run(self) -> None:  # noqa: D401
        import requests
        from requests.adapters import HTTPAdapter

        # Solo las que faltan en disco.
        pendientes = [
            u for u in self._urls
            if u and u.startswith("http") and not self._disk_path_for(u).exists()
        ]
        total = len(pendientes)
        if total == 0:
            self.finished_ok.emit()
            return

        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=_MAX_WORKERS, pool_maxsize=_MAX_WORKERS)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        done = 0

        def _fetch(url: str) -> None:
            if self._stop:
                return
            try:
                resp = session.get(url, timeout=_TIMEOUT)
                resp.raise_for_status()
                dest = self._disk_path_for(url)
                # Escritura atómica: archivo temporal + rename, para que un
                # lector nunca vea un archivo a medio escribir.
                tmp = dest.with_suffix(dest.suffix + ".part")
                tmp.write_bytes(resp.content)
                tmp.replace(dest)
            except Exception as e:  # noqa: BLE001
                logger.debug("Prefetch falló para %s: %s", url, e)

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futuros = [pool.submit(_fetch, u) for u in pendientes]
            # `as_completed` entrega cada futuro al terminar, así el progreso
            # refleja descargas reales (no el orden de envío).
            for _ in as_completed(futuros):
                done += 1
                self.progress.emit(done, total)
                if self._stop:
                    break

        session.close()
        self.finished_ok.emit()
