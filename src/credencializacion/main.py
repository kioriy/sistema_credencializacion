"""
Punto de entrada principal del Sistema de Credencialización.
Inicializa la base de datos, la aplicación Qt y muestra la ventana principal.
"""
from __future__ import annotations

import logging
import sys

# Configurar logging antes de cualquier otra cosa
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Flujo principal de inicio de la aplicación."""
    logger.info("Iniciando Sistema de Credencialización…")

    # 1. Inicializar base de datos
    from credencializacion.db.migrations import init_database, seed_default_data

    init_database()
    seed_default_data()
    logger.info("Base de datos inicializada correctamente.")

    # 2. Crear la aplicación Qt (debe existir antes de cualquier widget)
    from credencializacion.ui.app import create_app

    app = create_app(sys.argv)

    # 3. Crear y mostrar la ventana principal
    from credencializacion.ui.main_window import MainWindow

    window = MainWindow()
    window.show()
    logger.info("Ventana principal visible. Esperando interacción del usuario…")

    # 4. Verificar actualizaciones en segundo plano (solo en ejecutable compilado)
    try:
        from credencializacion.core.updater import check_for_updates, UpdateEventFilter
        UpdateEventFilter(app)          # Instala filtro de eventos para recibir notificación
        check_for_updates(window)       # Lanza hilo de verificación
    except Exception as e:
        logger.debug("Verificación de actualizaciones no disponible: %s", e)

    # 5. Event loop
    sys.exit(app.exec())



if __name__ == "__main__":
    main()
