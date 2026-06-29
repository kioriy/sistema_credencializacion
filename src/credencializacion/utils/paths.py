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
    """Raíz del proyecto (donde está pyproject.toml) o del ejecutable.

    - Empaquetada (PyInstaller): directorio que contiene el ejecutable. NUNCA
      depende del directorio de trabajo actual (cwd), que al relanzarse vía el
      script de actualización puede ser ``C:/Windows/System32``.
    - Desarrollo: raíz del proyecto (sube desde src/credencializacion/utils/);
      si no se encuentra pyproject.toml, usa el cwd.
    """
    if _is_frozen():
        try:
            return Path(sys.executable).resolve().parent
        except Exception:  # noqa: BLE001
            pass
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
    """Directorio de recursos estáticos (iconos, fuentes, plantillas).

    En la app empaquetada los recursos se incluyen en el bundle de PyInstaller:
    se resuelven desde ``sys._MEIPASS`` (o junto al ejecutable / ``_internal``),
    que son de SOLO LECTURA. En desarrollo, bajo la raíz del proyecto.
    """
    if _is_frozen():
        candidates: list[Path] = []
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "resources")
        try:
            exe_dir = Path(sys.executable).resolve().parent
            candidates.append(exe_dir / "resources")
            candidates.append(exe_dir / "_internal" / "resources")
        except Exception:  # noqa: BLE001
            pass
        for c in candidates:
            try:
                if c.exists():
                    return c
            except Exception:  # noqa: BLE001
                continue
        # Fallback razonable (aunque no exista aún): junto al bundle.
        if meipass:
            return Path(meipass) / "resources"
    return get_app_root() / "resources"


def get_fonts_dir() -> Path:
    """Directorio de fuentes tipográficas custom.

    No falla si el directorio no puede crearse (en build empaquetado los
    recursos son de solo lectura): en ese caso devuelve la ruta tal cual.
    """
    fonts = get_resources_dir() / "fonts"
    try:
        fonts.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Recursos de solo lectura (app empaquetada) o ruta protegida: las
        # fuentes ya vienen incluidas en el bundle, no es necesario crearla.
        pass
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


def get_plantilla_base_dir() -> Path:
    """Directorio donde se guardan las imágenes base de las plantillas.

    - Desarrollo: ``<raíz del proyecto>/plantilla_base`` (comportamiento previo).
    - Empaquetada: dentro de la carpeta de datos estable del usuario, fuera del
      directorio de la app, para que las actualizaciones no borren las imágenes
      base subidas por el usuario.

    Crea el directorio si no existe (primera ejecución/actualización).
    """
    if _is_frozen():
        d = get_data_dir() / "plantilla_base"
    else:
        d = get_app_root() / "plantilla_base"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_bundled_plantilla_base() -> Path | None:
    """Carpeta ``plantilla_base`` empaquetada/legada (solo lectura), si existe.

    Se usa para sembrar las imágenes base por defecto en la carpeta de datos del
    usuario y para recuperar imágenes tras mover la ubicación. Devuelve ``None``
    si no se encuentra ninguna ubicación candidata.
    """
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "plantilla_base")
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "plantilla_base")
        candidates.append(exe_dir / "_internal" / "plantilla_base")
    except Exception:  # noqa: BLE001
        pass
    candidates.append(get_app_root() / "plantilla_base")
    candidates.append(Path.cwd() / "plantilla_base")

    for c in candidates:
        try:
            if c.exists():
                return c
        except Exception:  # noqa: BLE001
            continue
    return None


def _slugify(nombre: str) -> str:
    """Convierte un nombre de cliente en un nombre de carpeta seguro."""
    import re

    base = (nombre or "cliente").strip().lower()
    base = re.sub(r"[^a-z0-9._-]+", "_", base)
    base = base.strip("_") or "cliente"
    return base[:80]


def get_img_dir(cliente_nombre: str | None = None) -> Path:
    """Directorio de imágenes subidas desde archivo (build-safe, estable).

    Igual que ``plantilla_base``: en la app empaquetada vive en la carpeta de
    datos estable del usuario (fuera del directorio de la app, para que las
    actualizaciones no la borren); en desarrollo, bajo la raíz del proyecto.
    La estructura es ``.../data/img/{nombre_cliente}`` (Decisión del usuario).

    Crea el directorio si no existe.
    """
    base = get_data_dir() / "img"
    if cliente_nombre:
        base = base / _slugify(cliente_nombre)
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_cola_pdf_dir(cola_id: int | None = None) -> Path:
    """Directorio estable (build-safe) para los PDFs de las colas de impresión.

    Igual que ``plantilla_base``/``img``: en la app empaquetada vive en la
    carpeta de datos estable del usuario (fuera del directorio de la app, para
    que las actualizaciones no la borren); en desarrollo, bajo la raíz del
    proyecto (``data/colas_pdf``). Si se indica ``cola_id`` se devuelve la
    subcarpeta de esa cola. Crea el directorio si no existe.
    """
    base = get_data_dir() / "colas_pdf"
    if cola_id is not None:
        base = base / str(cola_id)
    base.mkdir(parents=True, exist_ok=True)
    return base
