"""
Utilidades para carga y registro de fuentes tipográficas.
Soporta QFontDatabase (PySide6) y ReportLab (pdfmetrics).
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

from credencializacion.utils.paths import get_fonts_dir

logger = logging.getLogger(__name__)

# URL de Google Fonts para Inter (peso 100-900)
_INTER_GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2?family=Inter:wght@100..900&display=swap"
)

# Pesos de Inter que intentamos descargar como TTF estáticos
_INTER_WEIGHTS: dict[str, str] = {
    "Regular": "400",
    "Medium": "500",
    "SemiBold": "600",
    "Bold": "700",
    "ExtraBold": "800",
}


def _download_inter_fonts(target_dir: Path) -> list[Path]:
    """Descarga Inter desde Google Fonts si no existen localmente.

    Devuelve la lista de archivos TTF descargados / ya existentes.
    """
    import requests  # lazy import — solo necesario la primera vez

    downloaded: list[Path] = []
    for weight_name, weight_num in _INTER_WEIGHTS.items():
        filename = f"Inter-{weight_name}.ttf"
        filepath = target_dir / filename
        if filepath.exists():
            downloaded.append(filepath)
            continue

        # Google Fonts static URL pattern
        url = (
            f"https://raw.githubusercontent.com/google/fonts/main/"
            f"ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf"
        )
        # Intentamos la variable primero, si falla usamos static
        static_url = (
            f"https://raw.githubusercontent.com/rsms/inter/master/"
            f"docs/font-files/Inter-{weight_name}.woff2"
        )
        try:
            # Descargar la fuente variable (un solo archivo para todos los pesos)
            var_path = target_dir / "Inter-Variable.ttf"
            if not var_path.exists():
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200:
                    var_path.write_bytes(resp.content)
                    logger.info("Fuente Inter variable descargada: %s", var_path)
                    downloaded.append(var_path)
                    return downloaded  # Variable font cubre todo
            else:
                downloaded.append(var_path)
                return downloaded
        except Exception:
            logger.debug(
                "No se pudo descargar Inter variable, continuando sin ella."
            )
    return downloaded


def load_inter_font() -> str:
    """Carga Inter en QFontDatabase. Devuelve el family name registrado.

    Si Inter no está disponible ni descargable, devuelve el sans-serif
    del sistema.
    """
    fonts_dir = get_fonts_dir()

    # 1. Buscar fuentes Inter ya presentes en el directorio de recursos
    existing_fonts = list(fonts_dir.glob("Inter*.ttf")) + list(
        fonts_dir.glob("Inter*.otf")
    )

    # 2. Si no hay, intentar descargarla
    if not existing_fonts:
        existing_fonts = _download_inter_fonts(fonts_dir)

    # 3. Registrar todas las encontradas
    registered_family: str | None = None
    for font_path in existing_fonts:
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                registered_family = families[0]
                logger.info(
                    "Fuente registrada: %s desde %s", registered_family, font_path
                )

    # 3b. Cargar fuente de íconos (Material Symbols Outlined)
    icon_font_path = fonts_dir / "MaterialSymbolsOutlined.ttf"
    if icon_font_path.exists():
        idx = QFontDatabase.addApplicationFont(str(icon_font_path))
        if idx != -1:
            logger.info("Fuente de íconos Material Symbols cargada con éxito")

    # 4. Verificar si Inter ya está en el sistema
    if registered_family is None:
        all_families = QFontDatabase.families()
        for candidate in ("Inter", "Inter Display"):
            if candidate in all_families:
                registered_family = candidate
                break

    # 5. Fallback
    if registered_family is None:
        registered_family = QFont("sans-serif").family()
        logger.warning(
            "Inter no disponible, usando fallback: %s", registered_family
        )

    return registered_family


def load_system_fonts() -> list[str]:
    """Devuelve la lista de familias tipográficas del sistema."""
    return sorted(QFontDatabase.families())


def get_font_path(family: str) -> Path | None:
    """Busca el archivo TTF/OTF de una familia en el directorio de fuentes.

    Primero busca en ``resources/fonts/``, luego en las rutas del sistema.
    Devuelve ``None`` si no lo encuentra.
    """
    fonts_dir = get_fonts_dir()

    # Búsqueda local
    for ext in ("*.ttf", "*.otf"):
        for path in fonts_dir.glob(ext):
            # Comparación insensible a mayúsculas del nombre
            if family.lower().replace(" ", "") in path.stem.lower().replace(
                " ", ""
            ):
                return path

    # Búsqueda en rutas del sistema (macOS / Linux)
    system_dirs = [
        Path("/Library/Fonts"),
        Path.home() / "Library" / "Fonts",
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
    ]
    for sys_dir in system_dirs:
        if not sys_dir.exists():
            continue
        for ext in ("*.ttf", "*.otf"):
            for path in sys_dir.rglob(ext):
                if family.lower().replace(" ", "") in path.stem.lower().replace(
                    " ", ""
                ):
                    return path

    return None


def register_reportlab_font(family: str, path: Path) -> None:
    """Registra una fuente en ReportLab para generación de PDF.

    Parameters
    ----------
    family:
        Nombre con el que se referenciará la fuente en ReportLab.
    path:
        Ruta al archivo TTF.
    """
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    try:
        pdfmetrics.registerFont(TTFont(family, str(path)))
        # Registrar mapping por defecto (normal)
        addMapping(family, 0, 0, family)
        logger.info("Fuente '%s' registrada en ReportLab desde %s", family, path)
    except Exception as exc:
        logger.error("Error al registrar fuente '%s' en ReportLab: %s", family, exc)


def setup_all_fonts() -> str:
    """Inicializa todo el sistema de fuentes.

    - Registra Inter en Qt.
    - Registra Inter en ReportLab si está disponible.

    Devuelve el nombre de familia efectivo de Inter.
    """
    family = load_inter_font()

    # Intentar registrar en ReportLab
    font_path = get_font_path(family)
    if font_path is not None:
        register_reportlab_font(family, font_path)

    return family
