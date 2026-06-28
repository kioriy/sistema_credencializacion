"""
Utilidades para identificar atributos de imagen.

Un "atributo de imagen" es una clave de los datos de un registro cuyo valor es
(o se espera que sea) una URL/ruta de imagen: la foto del alumno, el logo de la
escuela, la foto de una persona autorizada, etc. Se usan para poblar el combobox
de "origen: atributo" del elemento imagen en el diseñador.
"""
from __future__ import annotations

# Pistas por nombre de atributo (subcadena, insensible a mayúsculas).
_IMAGE_NAME_HINTS = ("photo", "foto", "logo", "imagen", "image", "url_parent")

# Extensiones de imagen reconocidas en URLs/rutas.
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def is_image_value(value: object) -> bool:
    """Indica si un valor parece una URL/ruta de imagen."""
    if not isinstance(value, str):
        return False
    v = value.strip().lower()
    if not v:
        return False
    if v.startswith(("http://", "https://")) or v.startswith("/") or ":" in v[:3]:
        if v.split("?")[0].endswith(_IMAGE_EXTS):
            return True
        # Rutas típicas de almacenamiento de imágenes del backend.
        if "/storage/" in v and ("photo" in v or "logo" in v or "image" in v):
            return True
    return v.split("?")[0].endswith(_IMAGE_EXTS)


def is_image_attribute(key: str, value: object = None) -> bool:
    """Indica si una clave es un atributo de imagen, por nombre o por valor.

    Se considera de imagen si el nombre contiene una pista conocida (photo, foto,
    logo, imagen, image, url_parent) o si el valor de muestra parece una imagen.
    """
    if isinstance(key, str):
        k = key.lower()
        if any(hint in k for hint in _IMAGE_NAME_HINTS):
            return True
    return is_image_value(value)


def detect_image_attributes(records: list[dict]) -> list[str]:
    """Devuelve las claves de imagen presentes en una lista de registros.

    Recorre los registros (basta con una muestra) y clasifica cada clave; una
    clave se considera de imagen si lo es por nombre o si en algún registro su
    valor parece imagen. Conserva el orden de primera aparición.
    """
    vistos: list[str] = []
    seen: set[str] = set()
    # Acumular por nombre en todas las claves vistas y por valor en muestras.
    by_value: set[str] = set()
    for rec in records:
        if not isinstance(rec, dict):
            continue
        for key, value in rec.items():
            if key in seen:
                if is_image_value(value):
                    by_value.add(key)
                continue
            seen.add(key)
            vistos.append(key)
            if is_image_value(value):
                by_value.add(key)

    result: list[str] = []
    for key in vistos:
        if is_image_attribute(key) or key in by_value:
            result.append(key)
    return result
