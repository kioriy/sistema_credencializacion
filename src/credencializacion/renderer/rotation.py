"""
Lógica de rotación para renderizado de credenciales.

Las credenciales horizontales se rotan 90° en el canvas PDF
para imprimirse correctamente en hojas verticales (letter/A4).
"""
from __future__ import annotations

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
