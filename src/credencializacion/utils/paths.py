"""
Manejo de rutas multiplataforma con pathlib.
Centraliza todas las rutas del proyecto para Windows y macOS.
"""
from pathlib import Path
import logging
import os
import platform
import shutil
import sys

logger = logging.getLogger(__name__)

# Nombre de la carpeta de datos de usuario (en la ubicación estable del SO).
_APP_DIR_NAME = "Credencializacion"

# Caché de la ruta de datos resuelta (evita recomputar/migrar repetidamente).
_data_dir_cache: Path | None = None


def _is_frozen() -> bool:
    """True cuando la app corre como ejecutable empaquetado (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def get_app_root() -> Path:
    """Raíz del proyecto (donde está pyproject.toml)."""
    # En desarrollo: subir desde src/credencializacion/utils/
    dev_root = Path(__file__).resolve().parent.parent.parent.parent
    if (dev_root / "pyproject.toml").exists():
        return dev_root
    # Fallback: directorio actual
    return Path.cwd()


def _user_data_base() -> Path:
    """Ubicación estable por usuario para datos de la app (solo empaquetada).

    - Windows: ``%APPDATA%/Credencializacion``
    - macOS:   ``~/Library/Application Support/Credencializacion``
    - Linux:   ``$XDG_DATA_HOME/Credencializacion`` o ``~/.local/share/...``

    Mantener los datos fuera del directorio de la aplicación garantiza que una
    actualización (que reemplaza la carpeta del ejecutable) NUNCA toque la base
    de datos ni la caché del usuario.
    """
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / _APP_DIR_NAME
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / _APP_DIR_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / _APP_DIR_NAME


def _migrate_legacy_data(new_data: Path) -> None:
    """Migra la BD/caché desde ubicaciones legadas a la nueva carpeta estable.

    Solo actúa si la nueva ubicación aún no tiene base de datos. Busca la BD en
    ubicaciones antiguas (junto al ejecutable o en el cwd) y la copia, junto con
    sus archivos WAL/SHM y la caché de imágenes, preservando los datos del
    usuario tras introducir la ubicación estable.
    """
    new_db = new_data / "credencializacion.db"
    if new_db.exists():
        return

    candidates: list[Path] = []
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "data")
        candidates.append(exe_dir.parent / "data")
    except Exception:  # noqa: BLE001
        pass
    candidates.append(Path.cwd() / "data")

    for legacy in candidates:
        try:
            legacy_db = legacy / "credencializacion.db"
            if not legacy_db.exists():
                continue
            if legacy.resolve() == new_data.resolve():
                continue
        except Exception:  # noqa: BLE001
            continue

        try:
            for suffix in ("", "-wal", "-shm"):
                src = legacy / f"credencializacion.db{suffix}"
                if src.exists():
                    shutil.copy2(src, new_data / src.name)
            legacy_cache = legacy / "image_cache"
            dst_cache = new_data / "image_cache"
            if legacy_cache.exists() and not dst_cache.exists():
                shutil.copytree(legacy_cache, dst_cache)
            logger.info("Datos migrados desde ubicación legada: %s", legacy)
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudo migrar datos desde %s: %s", legacy, e)
        break


def get_data_dir() -> Path:
    """Directorio de datos de runtime (BD, caché, etc.).

    - En desarrollo: ``<raíz del proyecto>/data`` (comportamiento previo).
    - Empaquetada: carpeta estable del usuario en el SO, fuera del directorio
      de la app, para que las actualizaciones no afecten la base de datos.
    """
    global _data_dir_cache
    if _data_dir_cache is not None:
        return _data_dir_cache

    if _is_frozen():
        data = _user_data_base() / "data"
        data.mkdir(parents=True, exist_ok=True)
        _migrate_legacy_data(data)
    else:
        data = get_app_root() / "data"
        data.mkdir(parents=True, exist_ok=True)

    _data_dir_cache = data
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
