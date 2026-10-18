"""
Utilidades de conversión de coordenadas para impresión.

Convierte entre cm, mm y puntos tipográficos (points) de PostScript/PDF.
Calcula posiciones de tarjetas en la hoja para impresión multi-credencial.
"""
from __future__ import annotations
from credencializacion.core.settings import AppSettings

# Factor de conversión estándar PostScript: 1 inch = 72 points, 1 inch = 2.54 cm
CM_TO_POINTS = 28.3465  # 72 / 2.54
MM_TO_POINTS = 2.83465  # 72 / 25.4


def cm_to_points(cm: float) -> float:
    """Convierte centímetros a puntos PDF/PostScript."""
    return cm * CM_TO_POINTS


def mm_to_points(mm: float) -> float:
    """Convierte milímetros a puntos PDF/PostScript."""
    return mm * MM_TO_POINTS


def points_to_cm(pts: float) -> float:
    """Convierte puntos PDF/PostScript a centímetros."""
    return pts / CM_TO_POINTS


def points_to_mm(pts: float) -> float:
    """Convierte puntos PDF/PostScript a milímetros."""
    return pts / MM_TO_POINTS


def calculate_card_positions(
    page_size: tuple[float, float],
    card_size: tuple[float, float],
    cards_per_page: int,
    margins: dict[str, float],
) -> list[tuple[float, float]]:
    """Calcula las posiciones base (en puntos) de cada credencial en la hoja.

    Args:
        page_size: (ancho, alto) de la página en puntos.
        card_size: (ancho, alto) de la tarjeta en cm.
        cards_per_page: Número de tarjetas por página (normalmente 2).
        margins: Dict con 'top_cm' y 'left_cm' como márgenes.

    Returns:
        Lista de tuplas (x_pts, y_pts) con la esquina inferior-izquierda
        de cada tarjeta, en coordenadas PDF (origen abajo-izquierda).
    """
    page_w, page_h = page_size
    card_w_pts = cm_to_points(card_size[0])
    card_h_pts = cm_to_points(card_size[1])

    margin_top = cm_to_points(margins.get("top_cm", 1.5))
    margin_left = cm_to_points(margins.get("left_cm", 5.0))

    positions: list[tuple[float, float]] = []
    for i in range(cards_per_page):
        x = margin_left
        # PDF tiene origen abajo-izquierda; la primera tarjeta va arriba
        y = page_h - margin_top - (i + 1) * card_h_pts
        positions.append((x, y))

    return positions


def calculate_card_positions_from_config(
    page_size: tuple[float, float],
    posiciones_hoja: dict,  # Param kept for backwards compatibility but ignored
) -> list[tuple[float, float]]:
    """Calcula posiciones a partir de la configuración global de la app.

    Ignora el JSON de la plantilla y utiliza QSettings para asegurar
    que la charola mantenga la misma calibración en todo el sistema.

    Args:
        page_size: (ancho, alto) de la página en puntos.
        posiciones_hoja: Ignorado.

    Returns:
        Lista de tuplas (x_pts, y_pts) en coordenadas PDF.
    """
    page_w, page_h = page_size
    origins = AppSettings.get_print_origins()

    positions: list[tuple[float, float]] = []
    for origin in origins:
        x_cm, y_cm = origin
        x = cm_to_points(x_cm)
        # PDF origin is bottom-left; convert top-down y_cm to bottom-up
        y = page_h - cm_to_points(y_cm)
        positions.append((x, y))

    return positions


# Valor de "usar las dos ranuras" en los selectores de ranura. La ranura 1 es
# la más cercana al borde de la hoja; la 2, la siguiente.
RANURAS_AMBAS = "ambas"


def filtrar_por_ranura(
    positions: list[tuple[float, float]], ranuras: str | None,
) -> list[tuple[float, float]]:
    """Deja solo la ranura pedida, o todas si no se pide una.

    Imprimir en una sola ranura es lo que permite usar charolas con una
    ranura ocupada o dañada: la hoja sale con una credencial en esa posición
    en vez de dos. Como frentes, vueltas y la composición desde carpeta parten
    de esta misma lista, el recorte aplica a los tres por igual.

    Args:
        positions: Posiciones base de cada ranura, en orden (1, 2, …).
        ranuras: ``"ambas"``/``None`` para todas, o el número de ranura
            (``"1"``, ``"2"``, o un entero).

    Returns:
        La lista recortada; si la ranura pedida no existe, se devuelve sin
        cambios (mejor imprimir en las dos que no imprimir nada).
    """
    if ranuras in (None, "", RANURAS_AMBAS):
        return positions
    try:
        indice = int(ranuras) - 1
    except (TypeError, ValueError):
        return positions
    if 0 <= indice < len(positions):
        return [positions[indice]]
    return positions


def calculate_card_positions_from_profile(
    page_size: tuple[float, float],
    profile: dict,
) -> list[tuple[float, float]]:
    """Calcula posiciones a partir de un perfil de posición explícito.

    Igual que ``calculate_card_positions_from_config`` pero leyendo los
    orígenes de las ranuras del ``profile`` (dict con ``slot1_x/y`` y
    ``slot2_x/y`` en cm) en vez del QSettings global. Permite renderizar una
    cola con la calibración de una impresora concreta.

    Args:
        page_size: (ancho, alto) de la página en puntos.
        profile: Dict de perfil de posición.

    Returns:
        Lista de tuplas (x_pts, y_pts) en coordenadas PDF.
    """
    page_w, page_h = page_size
    origins = (
        (float(profile.get("slot1_x", 0.0)), float(profile.get("slot1_y", 0.0))),
        (float(profile.get("slot2_x", 0.0)), float(profile.get("slot2_y", 5.4))),
    )

    positions: list[tuple[float, float]] = []
    for x_cm, y_cm in origins:
        x = cm_to_points(x_cm)
        y = page_h - cm_to_points(y_cm)
        positions.append((x, y))

    return positions


def final_coordinate(
    base: tuple[float, float],
    element_pos: tuple[float, float],
) -> tuple[float, float]:
    """Coordenada final = posición base de la tarjeta + posición del elemento.

    La posición del elemento se espera en mm (como viene del JSON del diseño).
    El resultado está en puntos PDF.

    Args:
        base: (x, y) posición base de la tarjeta en puntos.
        element_pos: (x_mm, y_mm) posición del elemento dentro de la tarjeta.

    Returns:
        (x_pts, y_pts) coordenada final en el PDF.
    """
    base_x, base_y = base
    elem_x_mm, elem_y_mm = element_pos

    x = base_x + mm_to_points(elem_x_mm)
    # Elemento y va de arriba-abajo; restar para coordenadas PDF
    y = base_y - mm_to_points(elem_y_mm)

    return (x, y)
