"""
Caché local de imágenes descargadas (fotos de alumnos).

Descarga fotos desde URLs remotas, las almacena localmente en
``data/image_cache/{cliente_id}/{registro_id}.jpg`` y opcionalmente
las redimensiona para optimizar el uso de disco y velocidad de
renderizado.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

import requests
from PIL import Image

from credencializacion.utils.paths import get_image_cache_dir

logger = logging.getLogger(__name__)

# ── Configuración ────────────────────────────────────────────────────
_MAX_DIMENSION = 800       # px, lado mayor máximo
_JPEG_QUALITY = 85         # Calidad JPEG al guardar
_DOWNLOAD_TIMEOUT = 15     # segundos por descarga
_MAX_FILE_SIZE_MB = 10     # Rechazar archivos > 10 MB

# Tipo para callback de progreso: (current, total) → None
ProgressCallback = Callable[[int, int], None]


class ImageCacheManager:
    """Gestiona la descarga y caché local de imágenes de credenciales.

    Las imágenes se guardan en ``data/image_cache/{cliente_id}/``
    con nombre ``{registro_id}.jpg``.

    Ejemplo::

        cache = ImageCacheManager()
        local_path = cache.cache_image(
            url="https://escuela.com/storage/photos/42.jpg",
            cliente_id=1,
            registro_id=42,
        )
        # → data/image_cache/1/42.jpg
    """

    def __init__(self, max_dimension: int = _MAX_DIMENSION) -> None:
        """
        Args:
            max_dimension: Lado máximo en píxeles. Si la imagen es más
                           grande, se redimensiona manteniendo proporción.
        """
        self._max_dimension = max_dimension

    # ── Caché individual ─────────────────────────────────────────────

    def cache_image(
        self,
        url: str,
        cliente_id: int,
        registro_id: int,
        force: bool = False,
    ) -> Path | None:
        """Descarga y cachea una imagen.

        Args:
            url: URL remota de la imagen.
            cliente_id: ID del cliente (subdirectorio).
            registro_id: ID del registro (nombre del archivo).
            force: Si True, re-descarga aunque ya exista en caché.

        Returns:
            ``Path`` al archivo local, o ``None`` si falla la descarga.
        """
        if not url:
            logger.debug("URL vacía para registro %d, omitiendo.", registro_id)
            return None

        cache_dir = get_image_cache_dir(cliente_id)
        local_path = cache_dir / f"{registro_id}.jpg"

        # Verificar si ya está cacheada
        if local_path.exists() and not force:
            logger.debug("Imagen ya cacheada: %s", local_path)
            return local_path

        # Descargar
        try:
            response = requests.get(url, timeout=_DOWNLOAD_TIMEOUT, stream=True)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning(
                "Error descargando imagen para registro %d: %s",
                registro_id, exc,
            )
            return None

        # Validar tamaño antes de leer todo en memoria
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > _MAX_FILE_SIZE_MB * 1024 * 1024:
            logger.warning(
                "Imagen demasiado grande (%.1f MB) para registro %d, omitiendo.",
                int(content_length) / (1024 * 1024), registro_id,
            )
            return None

        # Leer contenido
        image_data = response.content

        # Procesar con Pillow: redimensionar si es necesario y guardar como JPEG
        try:
            local_path = self._process_and_save(image_data, local_path)
        except Exception as exc:
            logger.warning(
                "Error procesando imagen para registro %d: %s",
                registro_id, exc,
            )
            return None

        logger.debug("Imagen cacheada: %s", local_path)
        return local_path

    # ── Caché por lote ───────────────────────────────────────────────

    def cache_batch(
        self,
        records: list[dict[str, Any]],
        cliente_id: int,
        url_field: str = "photo_url",
        id_field: str = "registro_id",
        progress_callback: ProgressCallback | None = None,
    ) -> dict[int, Path]:
        """Descarga y cachea imágenes de múltiples registros.

        Args:
            records: Lista de diccionarios con datos de registros.
            cliente_id: ID del cliente.
            url_field: Clave del diccionario que contiene la URL de la foto.
            id_field: Clave del diccionario con el ID del registro.
            progress_callback: Función ``(current, total) → None`` para
                               reportar progreso a la UI.

        Returns:
            Diccionario ``{registro_id: Path}`` con las rutas locales
            de las imágenes descargadas exitosamente.
        """
        results: dict[int, Path] = {}
        total = len(records)

        for i, record in enumerate(records):
            url = record.get(url_field, "")
            registro_id = record.get(id_field, i)

            if not isinstance(registro_id, int):
                try:
                    registro_id = int(registro_id)
                except (TypeError, ValueError):
                    registro_id = i

            if url:
                local_path = self.cache_image(
                    url=str(url),
                    cliente_id=cliente_id,
                    registro_id=registro_id,
                )
                if local_path is not None:
                    results[registro_id] = local_path

            # Reportar progreso
            if progress_callback is not None:
                progress_callback(i + 1, total)

        logger.info(
            "Caché por lote: %d/%d imágenes descargadas para cliente %d.",
            len(results), total, cliente_id,
        )
        return results

    # ── Procesamiento de imagen ──────────────────────────────────────

    def _process_and_save(
        self,
        image_data: bytes,
        target_path: Path,
    ) -> Path:
        """Redimensiona y guarda la imagen como JPEG.

        Args:
            image_data: Bytes crudos de la imagen descargada.
            target_path: Ruta donde guardar el archivo.

        Returns:
            Ruta al archivo guardado.
        """
        import io

        img = Image.open(io.BytesIO(image_data))

        # Convertir a RGB si es necesario (e.g. PNG con alpha)
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Redimensionar si excede el máximo
        if max(img.size) > self._max_dimension:
            img.thumbnail(
                (self._max_dimension, self._max_dimension),
                Image.Resampling.LANCZOS,
            )

        # Guardar como JPEG optimizado
        img.save(
            target_path,
            format="JPEG",
            quality=_JPEG_QUALITY,
            optimize=True,
        )
        return target_path

    # ── Utilidades ───────────────────────────────────────────────────

    @staticmethod
    def clear_cache(cliente_id: int) -> int:
        """Elimina todas las imágenes cacheadas de un cliente.

        Args:
            cliente_id: ID del cliente cuyo caché se limpiará.

        Returns:
            Número de archivos eliminados.
        """
        cache_dir = get_image_cache_dir(cliente_id)
        count = 0
        for file in cache_dir.glob("*.jpg"):
            file.unlink()
            count += 1
        logger.info(
            "Caché limpiado: %d imágenes eliminadas para cliente %d.",
            count, cliente_id,
        )
        return count

    @staticmethod
    def get_cached_path(cliente_id: int, registro_id: int) -> Path | None:
        """Retorna la ruta cacheada si existe, None si no.

        Args:
            cliente_id: ID del cliente.
            registro_id: ID del registro.

        Returns:
            ``Path`` si el archivo existe, ``None`` en caso contrario.
        """
        cache_dir = get_image_cache_dir(cliente_id)
        path = cache_dir / f"{registro_id}.jpg"
        return path if path.exists() else None
