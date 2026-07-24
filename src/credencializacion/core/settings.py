"""
Gestor de configuraciones globales de la aplicación.
Usa QSettings para persistencia nativa en el SO.
"""
import json

from PySide6.QtCore import QSettings

ORG_NAME = "MiEscuela"
APP_NAME = "Credencializacion"

# Nombre del perfil de posición por defecto (sembrado con los valores globales).
DEFAULT_PROFILE_NAME = "Predeterminado"


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

    # ── Sincronización con Google Sheets ────────────────────────────

    @staticmethod
    def get_sheets_credentials_path() -> str:
        """Ruta al archivo JSON de credenciales del service account de Google."""
        return str(get_settings().value("sheets/credentials_path", ""))

    @staticmethod
    def get_sheets_document_name() -> str:
        """Nombre del documento de Google Sheets a sincronizar."""
        s = get_settings()
        return str(s.value("sheets/document_name", "") or "clientes negocios")

    @staticmethod
    def set_sheets_config(credentials_path: str, document_name: str) -> None:
        """Guarda la configuración de sincronización con Google Sheets."""
        s = get_settings()
        s.setValue("sheets/credentials_path", credentials_path)
        s.setValue("sheets/document_name", document_name)
        s.sync()

    # ── Perfiles de posición (calibración por impresora) ────────────
    #
    # Cada perfil guarda la calibración de la charola: orígenes de las dos
    # ranuras, dimensiones de la hoja y la impresora asociada. Se almacenan
    # como un dict JSON en la key ``print/profiles`` ({nombre: perfil}). Un
    # perfil es: {slot1_x, slot1_y, slot2_x, slot2_y, page_width, page_height,
    # printer}. Tres impresoras del mismo modelo pueden requerir perfiles
    # distintos por diferencias de píxeles.

    @staticmethod
    def _read_profiles() -> dict:
        raw = get_settings().value("print/profiles", "")
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            return {}

    @staticmethod
    def _write_profiles(profiles: dict) -> None:
        s = get_settings()
        s.setValue("print/profiles", json.dumps(profiles))
        s.sync()

    @staticmethod
    def ensure_default_profile() -> None:
        """Siembra el perfil Predeterminado desde los valores globales.

        Se ejecuta al arrancar: si aún no hay perfiles (instalación previa a
        esta función), crea uno con la calibración global actual para no
        perder la configuración existente.
        """
        profiles = AppSettings._read_profiles()
        if profiles:
            return
        (x1, y1), (x2, y2) = AppSettings.get_print_origins()
        w, h = AppSettings.get_page_dimensions()
        profiles[DEFAULT_PROFILE_NAME] = {
            "slot1_x": x1, "slot1_y": y1,
            "slot2_x": x2, "slot2_y": y2,
            "page_width": w, "page_height": h,
            "printer": "",
        }
        AppSettings._write_profiles(profiles)

    @staticmethod
    def list_position_profiles() -> list[str]:
        """Nombres de los perfiles de posición, en orden alfabético."""
        return sorted(AppSettings._read_profiles().keys())

    @staticmethod
    def get_position_profile(name: str) -> dict | None:
        """Devuelve el perfil por nombre, o ``None`` si no existe.

        El dict incluye la clave ``name`` para conveniencia del llamador.
        """
        prof = AppSettings._read_profiles().get(name)
        if prof is None:
            return None
        return {**prof, "name": name}

    @staticmethod
    def save_position_profile(name: str, data: dict) -> None:
        """Crea o actualiza un perfil. ``data`` usa las claves del perfil."""
        name = (name or "").strip()
        if not name:
            return
        profiles = AppSettings._read_profiles()
        profiles[name] = {
            "slot1_x": float(data.get("slot1_x", 0.0)),
            "slot1_y": float(data.get("slot1_y", 0.0)),
            "slot2_x": float(data.get("slot2_x", 0.0)),
            "slot2_y": float(data.get("slot2_y", 5.4)),
            "page_width": float(data.get("page_width", 297.0)),
            "page_height": float(data.get("page_height", 320.0)),
            "printer": str(data.get("printer", "") or ""),
        }
        AppSettings._write_profiles(profiles)

    @staticmethod
    def delete_position_profile(name: str) -> None:
        """Elimina un perfil (no permite quedarse sin ninguno)."""
        profiles = AppSettings._read_profiles()
        if name in profiles and len(profiles) > 1:
            del profiles[name]
            AppSettings._write_profiles(profiles)

    @staticmethod
    def get_profile_for_printer(printer_name: str) -> str | None:
        """Nombre del perfil asociado a una impresora, o ``None``.

        Si varios perfiles apuntan a la misma impresora, devuelve el primero
        en orden alfabético (determinista).
        """
        printer_name = (printer_name or "").strip()
        if not printer_name:
            return None
        profiles = AppSettings._read_profiles()
        for name in sorted(profiles):
            if str(profiles[name].get("printer", "") or "").strip() == printer_name:
                return name
        return None
