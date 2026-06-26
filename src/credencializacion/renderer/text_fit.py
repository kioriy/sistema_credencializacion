"""
Utilidad compartida de ajuste y anclaje de texto.

Provee funciones puras y agnósticas del framework de render para:

- Calcular el tamaño de fuente efectivo (shrink-to-fit) de modo que un texto
  quepa dentro del ancho útil de una caja fija.
- Resolver el punto de anclaje horizontal y el punto de inicio del texto según
  la alineación, sin depender del centrado automático de Qt o ReportLab.

El mismo algoritmo se inyecta tanto en el diseñador (QFontMetricsF) como en el
motor PDF (pdfmetrics.stringWidth); la única diferencia es el callable
`measure_width` que mide el ancho del texto en las unidades nativas de cada
motor.
"""
from __future__ import annotations

from typing import Callable

# Tipo del medidor de ancho de texto: (texto, tamaño_de_fuente) -> ancho
MeasureWidth = Callable[[str, float], float]


def fit_font_size(
    measure_width: MeasureWidth,
    text: str,
    box_width: float,
    base_font_size: float,
    min_font_size: float = 1.0,
    padding: float = 0.0,
) -> float:
    """Calcula el mayor tamaño de fuente <= ``base_font_size`` que hace caber el texto.

    Devuelve el mayor tamaño de fuente menor o igual a ``base_font_size`` tal que
    ``measure_width(text, size) <= box_width - 2 * padding``. Si el texto ya cabe
    con ``base_font_size``, se devuelve ``base_font_size`` sin cambios. El
    resultado se acota inferiormente por ``min_font_size``.

    Como el ancho del texto es monótono respecto al tamaño de fuente, se calcula
    un primer estimado proporcional
    ``effective = base * min(1, available_width / measured_at_base)`` y luego se
    aplica un ajuste fino decreciente para garantizar el encaje exacto.

    Args:
        measure_width: Callable ``(text, font_size) -> ancho`` que mide el ancho
            del texto en las mismas unidades que ``box_width``.
        text: Texto a medir y ajustar.
        box_width: Ancho de la caja del elemento (mismas unidades que el ancho
            devuelto por ``measure_width``).
        base_font_size: Tamaño de fuente definido por el usuario (límite superior).
        min_font_size: Tamaño de fuente mínimo permitido (límite inferior).
        padding: Relleno aplicado a cada lado; reduce el ancho útil en
            ``2 * padding``.

    Returns:
        El tamaño de fuente efectivo, acotado al rango
        ``[min_font_size, base_font_size]``.
    """
    # Normaliza los límites por si llegan invertidos.
    if min_font_size > base_font_size:
        min_font_size = base_font_size

    # Texto vacío: nada que ajustar, conserva el tamaño base.
    if not text:
        return base_font_size

    available_width = box_width - 2.0 * padding

    # Ancho útil nulo o negativo: no se puede ajustar de forma significativa;
    # se devuelve el mínimo de forma segura (sin dividir por cero).
    if available_width <= 0:
        return min_font_size

    measured_at_base = measure_width(text, base_font_size)

    # Métrica nula o no positiva (p. ej. texto sin glifos visibles): se considera
    # que cabe y se conserva el tamaño base, evitando la división por cero.
    if measured_at_base <= 0:
        return base_font_size

    # Si ya cabe con el tamaño base, no se reduce nada.
    if measured_at_base <= available_width:
        return base_font_size

    # Estimado proporcional inicial (el ancho es monótono respecto al tamaño).
    effective = base_font_size * (available_width / measured_at_base)

    # Acota al rango permitido.
    if effective > base_font_size:
        effective = base_font_size
    if effective < min_font_size:
        return min_font_size

    # Ajuste fino decreciente para garantizar el encaje exacto pese a métricas
    # no perfectamente lineales (hinting, kerning, redondeos).
    for _ in range(64):
        if measure_width(text, effective) <= available_width:
            break
        next_effective = effective * 0.98
        if next_effective < min_font_size:
            return min_font_size
        effective = next_effective

    return effective


def compute_anchor_x(x: float, w: float, alignment: str) -> float:
    """Calcula el ancla horizontal del texto dentro de la caja fija.

    Args:
        x: Borde izquierdo de la caja.
        w: Ancho de la caja.
        alignment: ``"left"``, ``"center"``, ``"right"`` o ``"justify"``.
            Cualquier otro valor se trata como ``"left"``.

    Returns:
        La coordenada x del punto de anclaje:
        ``left -> x``, ``center -> x + w/2``, ``right -> x + w``,
        ``justify -> x``.
    """
    if alignment == "center":
        return x + w / 2.0
    if alignment == "right":
        return x + w
    # "left", "justify" y cualquier valor desconocido se anclan a la izquierda.
    return x


def compute_start_x(anchor_x: float, text_width: float, alignment: str) -> float:
    """Calcula el punto de inicio (x) del texto a partir del ancla y su ancho real.

    Args:
        anchor_x: Punto de anclaje horizontal (ver :func:`compute_anchor_x`).
        text_width: Ancho real del texto medido con el tamaño de fuente efectivo.
        alignment: ``"left"``, ``"center"``, ``"right"`` o ``"justify"``.
            Cualquier otro valor se trata como ``"left"``.

    Returns:
        La coordenada x desde la que debe dibujarse el texto:
        ``left -> anchor_x``, ``center -> anchor_x - text_width/2``,
        ``right -> anchor_x - text_width``, ``justify -> anchor_x``.
    """
    if alignment == "center":
        return anchor_x - text_width / 2.0
    if alignment == "right":
        return anchor_x - text_width
    # "left", "justify" y cualquier valor desconocido inician en el ancla.
    return anchor_x
