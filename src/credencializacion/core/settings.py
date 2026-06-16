"""
Gestor de configuraciones globales de la aplicación.
Usa QSettings para persistencia nativa en el SO.
"""
from PySide6.QtCore import QSettings

ORG_NAME = "MiEscuela"
APP_NAME = "Credencializacion"

def get_settings() -> QSettings:
    return QSettings(ORG_NAME, APP_NAME)

class AppSettings:
    """Clase helper para acceder a configuraciones fuertemente tipadas."""
    
    @staticmethod
    def get_print_origins() -> tuple[tuple[float, float], tuple[float, float]]:
        """Obtiene los orígenes de las ranuras 1 y 2 en cm.
        Returns:
            ((x1, y1), (x2, y2))
        """
        s = get_settings()
        # Default: ranura 1 en (0, 0), ranura 2 en (0, 5.4)
        x1 = float(s.value("print/slot1_x", 0.0))
        y1 = float(s.value("print/slot1_y", 0.0))
        x2 = float(s.value("print/slot2_x", 0.0))
        y2 = float(s.value("print/slot2_y", 5.4))
        return ((x1, y1), (x2, y2))

    @staticmethod
    def set_print_origins(x1: float, y1: float, x2: float, y2: float) -> None:
        """Guarda los orígenes de las ranuras 1 y 2 en cm."""
        s = get_settings()
        s.setValue("print/slot1_x", x1)
        s.setValue("print/slot1_y", y1)
        s.setValue("print/slot2_x", x2)
        s.setValue("print/slot2_y", y2)
        s.sync()

    @staticmethod
    def get_page_dimensions() -> tuple[float, float]:
        """Obtiene las dimensiones de la hoja (ancho, alto) en mm.
        Returns:
            (ancho_mm, alto_mm)
        """
        s = get_settings()
        # Default fallback to 297x320 mm (Custom size requested earlier by user)
        w = float(s.value("print/page_width", 297.0))
        h = float(s.value("print/page_height", 320.0))
        return (w, h)

    @staticmethod
    def set_page_dimensions(width_mm: float, height_mm: float) -> None:
        """Guarda las dimensiones de la hoja en mm."""
        s = get_settings()
        s.setValue("print/page_width", width_mm)
        s.setValue("print/page_height", height_mm)
        s.sync()
