"""
Manejo de rutas multiplataforma con pathlib.
Centraliza todas las rutas del proyecto para Windows y macOS.
"""
from pathlib import Path
import sys


def get_app_root() -> Path:
    """Raíz del proyecto (donde está pyproject.toml)."""
    # En desarrollo: subir desde src/credencializacion/utils/
    dev_root = Path(__file__).resolve().parent.parent.parent.parent
    if (dev_root / "pyproject.toml").exists():
        return dev_root
    # Fallback: directorio actual
    return Path.cwd()


def get_data_dir() -> Path:
    """Directorio de datos de runtime (BD, caché, etc.)."""
    data = get_app_root() / "data"
    data.mkdir(parents=True, exist_ok=True)
    return data


def get_db_path() -> Path:
    """Ruta completa al archivo SQLite."""
    return get_data_dir() / "credencializacion.db"


def get_image_cache_dir(cliente_id: int | None = None) -> Path:
    """Directorio de caché de imágenes descargadas."""
    cache = get_data_dir() / "image_cache"
    if cliente_id is not None:
        cache = cache / str(cliente_id)
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def get_resources_dir() -> Path:
    """Directorio de recursos estáticos (iconos, fuentes, plantillas)."""
    return get_app_root() / "resources"


def get_fonts_dir() -> Path:
    """Directorio de fuentes tipográficas custom."""
    fonts = get_resources_dir() / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    return fonts


def get_icons_dir() -> Path:
    """Directorio de iconos de la UI."""
    return get_resources_dir() / "icons"


def get_default_templates_dir() -> Path:
    """Directorio de plantillas por defecto."""
    return get_resources_dir() / "default_templates"


def get_temp_dir() -> Path:
    """Directorio temporal para PDFs generados antes de impresión."""
    temp = get_data_dir() / "temp"
    temp.mkdir(parents=True, exist_ok=True)
    return temp
