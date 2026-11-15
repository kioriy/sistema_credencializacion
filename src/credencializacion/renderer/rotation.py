"""
Lógica de rotación para renderizado de credenciales.

Las credenciales horizontales se rotan 90° en el canvas PDF
para imprimirse correctamente en hojas verticales (letter/A4).
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reportlab.pdfgen.canvas import Canvas
    from credencializacion.db.models import Plantilla


def should_rotate(plantilla: "Plantilla") -> bool:
    """Determina si la credencial necesita rotación para impresión.

    Las plantillas horizontales deben rotarse 90° cuando se imprimen
    en hojas verticales estándar.

    Args:
        plantilla: Instancia del modelo Plantilla.

    Returns:
        True si la orientación es horizontal.
    """
    return plantilla.orientacion.lower() == "vertical"


def get_rotated_dimensions(width: float, height: float) -> tuple[float, float]:
    """Intercambia ancho y alto para rotación de 90°.

    Args:
        width: Ancho original.
        height: Alto original.

    Returns:
        Tupla (height, width) — dimensiones intercambiadas.
    """
    return (height, width)


def element_rotation(elem: dict) -> float:
    """Ángulo en grados de un elemento del diseño (0 si no tiene).

    Se guarda en ``properties["rotation"]`` y es el ángulo tal como se ve en
    el lienzo: positivo = en sentido de las manecillas del reloj.
    """
    try:
        angulo = float((elem.get("properties") or {}).get("rotation", 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    # Normaliza a (-180, 180]: girar 370° o -350° es lo mismo que 10°.
    angulo = angulo % 360.0
    if angulo > 180.0:
        angulo -= 360.0
    return angulo


def rotated_bounds(
    width: float, height: float, angle: float,
) -> tuple[float, float, float, float]:
    """Caja que ocupa un elemento girado, relativa a su ``x``/``y``.

    El giro es sobre el centro, así que el centro no se mueve pero la caja
    que ocupa en la tarjeta sí cambia: un texto ancho y bajo puesto de pie
    pasa a ser angosto y alto. Sin esto, el lienzo seguiría estorbando con
    el tamaño sin girar y el elemento no llegaría al borde.

    Args:
        width: Ancho sin girar.
        height: Alto sin girar.
        angle: Ángulo en grados (positivo = manecillas del reloj).

    Returns:
        ``(dx, dy, ancho, alto)``: el desplazamiento de la esquina superior
        izquierda respecto a ``x``/``y`` y el tamaño ya girado. Sin rotación
        es ``(0, 0, width, height)``.
    """
    if not angle:
        return 0.0, 0.0, width, height

    radianes = math.radians(angle)
    cos = abs(math.cos(radianes))
    sen = abs(math.sin(radianes))
    ancho = width * cos + height * sen
    alto = width * sen + height * cos
    return (width - ancho) / 2.0, (height - alto) / 2.0, ancho, alto


def element_bounds(elem: dict) -> tuple[float, float, float, float]:
    """Caja visual de un elemento del diseño: ``(x, y, ancho, alto)``."""
    dx, dy, ancho, alto = rotated_bounds(
        float(elem.get("width", 0) or 0),
        float(elem.get("height", 0) or 0),
        element_rotation(elem),
    )
    return (
        float(elem.get("x", 0) or 0) + dx,
        float(elem.get("y", 0) or 0) + dy,
        ancho,
        alto,
    )


def clamp_position(
    x: float,
    y: float,
    width: float,
    height: float,
    angle: float,
    card_width: float,
    card_height: float,
) -> tuple[float, float]:
    """Acerca ``(x, y)`` lo necesario para que el elemento quepa en la tarjeta.

    Topa con la caja YA GIRADA, que es la que se ve: un texto acostado puesto
    de pie debe poder llegar al borde izquierdo o derecho, cosa que no pasaba
    cuando el tope usaba el ancho sin girar. Un elemento más grande que la
    tarjeta se ancla a la esquina superior izquierda.

    Todas las medidas van en la misma unidad (mm o px).

    Returns:
        ``(x, y)`` ya ajustados; iguales a los de entrada si ya cabía.
    """
    dx, dy, ancho, alto = rotated_bounds(width, height, angle)

    min_x, max_x = -dx, card_width - dx - ancho
    min_y, max_y = -dy, card_height - dy - alto

    nueva_x = min(max(x, min_x), max_x) if max_x >= min_x else min_x
    nueva_y = min(max(y, min_y), max_y) if max_y >= min_y else min_y
    return nueva_x, nueva_y


def apply_rotation(
    canvas: "Canvas",
    x: float,
    y: float,
    angle: float,
) -> None:
    """Aplica rotación al canvas de ReportLab en un punto dado.

    Usa saveState/restoreState para aislar la transformación.
    El caller es responsable de llamar restoreState después de dibujar.

    Args:
        canvas: Canvas de ReportLab.
        x: Coordenada X del punto de rotación (puntos).
        y: Coordenada Y del punto de rotación (puntos).
        angle: Ángulo de rotación en grados (positivo = antihorario).
    """
    canvas.saveState()
    canvas.translate(x, y)
    canvas.rotate(angle)


def restore_rotation(canvas: "Canvas") -> None:
    """Restaura el estado del canvas tras una rotación.

    Args:
        canvas: Canvas de ReportLab.
    """
    canvas.restoreState()
