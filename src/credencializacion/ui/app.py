"""
Configuración y creación de QApplication.
Aplica el stylesheet global, carga fuentes y establece metadatos de la app.
"""
from __future__ import annotations

import logging
import sys
from typing import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from credencializacion.ui.styles import FONT_FAMILY, get_main_stylesheet
from credencializacion.utils.fonts import setup_all_fonts
from credencializacion.utils.paths import get_icons_dir

logger = logging.getLogger(__name__)

# Metadatos de la aplicación
APP_NAME = "Sistema de Credencialización"
APP_ORG = "miescuela.net"
APP_DOMAIN = "miescuela.net"
APP_VERSION = "0.1.0"


def create_app(argv: Sequence[str] | None = None) -> QApplication:
    """Crea y configura la instancia de QApplication.

    Parameters
    ----------
    argv:
        Argumentos de línea de comandos.  Si es ``None`` usa ``sys.argv``.

    Returns
    -------
    QApplication
        La aplicación configurada, lista para ``exec()``.
    """
    if argv is None:
        argv = sys.argv

    # Habilitar High-DPI automático (Qt6 lo tiene por defecto, pero
    # lo dejamos explícito por claridad)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(list(argv))

    # --- Metadatos ---
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setOrganizationDomain(APP_DOMAIN)
    app.setApplicationVersion(APP_VERSION)

    # --- Fuentes ---
    font_family = setup_all_fonts()
    logger.info("Familia de fuente activa: %s", font_family)

    # Fuente base de la aplicación
    base_font = QFont(font_family, 13)
    base_font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(base_font)

    # --- Stylesheet global ---
    app.setStyleSheet(get_main_stylesheet())

    # --- Ícono de la app ---
    icon_path = get_icons_dir() / "app_icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    else:
        logger.debug(
            "Ícono de app no encontrado en %s, usando ícono por defecto.", icon_path
        )

    return app
