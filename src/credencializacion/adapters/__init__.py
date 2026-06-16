"""
Adaptadores de datos para el sistema de credencialización.

Provee una interfaz unificada para obtener registros de distintas
fuentes: API de MiEscuela, archivos CSV/Excel, Google Sheets.

Uso típico::

    from credencializacion.adapters import (
        MiEscuelaAdapter,
        FileAdapter,
        GoogleSheetsAdapter,
        DataNormalizer,
        ImageCacheManager,
    )
"""
from credencializacion.adapters.base import DataAdapter
from credencializacion.adapters.image_cache import ImageCacheManager
from credencializacion.adapters.miescuela import MiEscuelaAdapter
from credencializacion.adapters.normalizer import (
    DataNormalizer,
    MappingResult,
    STANDARD_ATTRIBUTES,
)
from credencializacion.adapters.sheets import FileAdapter, GoogleSheetsAdapter

__all__ = [
    "DataAdapter",
    "MiEscuelaAdapter",
    "FileAdapter",
    "GoogleSheetsAdapter",
    "DataNormalizer",
    "MappingResult",
    "STANDARD_ATTRIBUTES",
    "ImageCacheManager",
]
