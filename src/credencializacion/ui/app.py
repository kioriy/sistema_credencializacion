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
from credencializacion.utils.paths import get_app_icon_path

logger = logging.getLogger(__name__)

# Metadatos de la aplicación
APP_NAME = "Sistema de Credencialización"
APP_ORG = "miescuela.net"
APP_DOMAIN = "miescuela.net"
APP_VERSION = "0.1.0"
# Identificador de modelo de usuario de la app (Windows). Necesario para que la
# barra de tareas agrupe la app bajo nuestro icono (y no el de python/host) y
# para que el icono se conserve al anclarla.
APP_USER_MODEL_ID = "miescuela.credencializacion.app"


def _set_windows_app_user_model_id() -> None:
    """Asocia un AppUserModelID propio en Windows (no-op en otros SO).

    Debe llamarse lo antes posible, antes de crear ventanas, para que el icono
    de la barra de tareas sea el de la app y se mantenga al anclarla.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("No se pudo establecer el AppUserModelID: %s", e)


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

    # AppUserModelID (Windows): antes de crear QApplication/ventanas para que la
    # barra de tareas use el icono de la app y lo conserve al anclarla.
    _set_windows_app_user_model_id()

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

    # --- Paleta de tooltips (contraste legible, también en estilo nativo macOS) ---
    # El estilo nativo respeta ToolTipBase/ToolTipText de la paleta; se fija un
    # fondo claro con texto oscuro para garantizar contraste.
    from PySide6.QtGui import QColor, QPalette
    from credencializacion.ui.styles import COLORS

    _pal = app.palette()
    _pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#FFFFFF"))
    _pal.setColor(QPalette.ColorRole.ToolTipText, QColor(COLORS["text"]))
    app.setPalette(_pal)

    # --- Ícono de la app ---
    icon_path = get_app_icon_path()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))
    else:
        logger.debug("Ícono de app no encontrado en resources/icons; usando el por defecto.")

    return app
