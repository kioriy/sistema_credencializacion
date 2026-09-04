"""
Composición de PDFs de impresión a partir de una CARPETA de diseños ya hechos.

Para clientes que entregan sus credenciales ya diseñadas (una imagen por
credencial), este módulo arma los PDF de frentes y vueltas colocando cada
imagen en su ranura de la charola, usando la MISMA calibración (perfil de
posición o configuración global) y el mismo layout de 2 por hoja que el flujo
normal del Centro de Impresión. No requiere registros ni plantillas del sistema.

Estructura de carpeta esperada:
- ``frente/``  con una imagen por credencial (obligatoria).
- ``vuelta/``  opcional. Casos soportados:
    * vacía / ausente      -> solo se genera el PDF de frentes.
    * una sola imagen      -> esa vuelta se repite para TODOS los frentes.
    * N imágenes (= N frentes) -> se emparejan por orden de nombre.
    * conteo distinto      -> se empareja por orden y se avisa (los huecos se
      dejan en blanco para no desalinear frente/vuelta al voltear la hoja).

Si la carpeta no tiene subcarpetas ``frente``/``vuelta``, se toman las imágenes
de la raíz como frentes (sin vueltas).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from reportlab.pdfgen.canvas import Canvas

from credencializacion.renderer.coordinates import (
    cm_to_points,
    mm_to_points,
    calculate_card_positions_from_config,
    calculate_card_positions_from_profile,
)

logger = logging.getLogger(__name__)

# Extensiones de imagen aceptadas para los diseños de entrada.
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# Dimensiones por defecto de la credencial (cm), tamaño estándar horizontal.
DEFAULT_CARD_W_CM = 8.5
DEFAULT_CARD_H_CM = 5.4


def _natural_key(p: Path) -> list:
    """Clave de orden natural: 'img2' < 'img10' (números como números)."""
    return [
        int(tok) if tok.isdigit() else tok.lower()
        for tok in re.split(r"(\d+)", p.name)
    ]


def list_images(folder: Path | None) -> list[Path]:
    """Lista las imágenes de una carpeta ordenadas de forma natural."""
    if not folder or not Path(folder).is_dir():
        return []
    return sorted(
        (
            f
            for f in Path(folder).iterdir()
            if f.is_file() and f.suffix.lower() in IMG_EXTS
        ),
        key=_natural_key,
    )


@dataclass
class FolderSides:
    """Resultado de analizar una carpeta de diseños.

    ``backs`` es ``None`` cuando no hay vueltas (solo se generan frentes). Cuando
    hay vueltas, es una lista alineada 1:1 con ``fronts`` donde cada elemento es
    la ruta de la vuelta o ``None`` (hueco en blanco para conservar el emparejado
    al voltear la hoja).
    """

    fronts: list[Path]
    backs: list[Path | None] | None
    n_front: int
    n_back: int
    mode: str  # "only_front" | "single_back" | "paired" | "mismatch" | "empty"
    warning: str | None = None


def resolve_folder_sides(root: Path | str) -> FolderSides:
    """Analiza la carpeta y decide cómo emparejar frentes y vueltas.

    No lee el contenido de las imágenes, solo sus nombres/rutas; es barato y se
    puede llamar desde la UI para previsualizar los conteos antes de componer.
    """
    root = Path(root)
    frente_dir = root / "frente" if (root / "frente").is_dir() else root
    vuelta_dir = root / "vuelta" if (root / "vuelta").is_dir() else None

    fronts = list_images(frente_dir)
    back_imgs = list_images(vuelta_dir) if vuelta_dir else []
    n_front, n_back = len(fronts), len(back_imgs)

    if not fronts:
        return FolderSides(
            fronts=[], backs=None, n_front=0, n_back=n_back, mode="empty",
            warning="No se encontraron imágenes de frente en la carpeta.",
        )

    if not back_imgs:
        return FolderSides(fronts, None, n_front, 0, "only_front")

    if n_back == 1 and n_front > 1:
        return FolderSides(
            fronts, [back_imgs[0]] * n_front, n_front, 1, "single_back",
        )

    if n_back == n_front:
        return FolderSides(fronts, list(back_imgs), n_front, n_back, "paired")

    # Conteo distinto: emparejar por orden y dejar huecos en blanco.
    backs: list[Path | None] = [
        back_imgs[i] if i < n_back else None for i in range(n_front)
    ]
    extra = max(0, n_back - n_front)
    warning = (
        f"Los frentes ({n_front}) y las vueltas ({n_back}) no coinciden. "
        "Se emparejan por orden de nombre; "
        + (
            f"faltan {n_front - n_back} vuelta(s) (se dejan en blanco)."
            if n_back < n_front
            else f"sobran {extra} vuelta(s) (se ignoran)."
        )
    )
    return FolderSides(fronts, backs, n_front, n_back, "mismatch", warning)


def _page_and_positions(perfil: dict | None) -> tuple[tuple[float, float], list]:
    """Tamaño de página (pts) y posiciones base de cada ranura (pts).

    Replica exactamente lo que hace ``PDFEngine.__init__`` para que las
    credenciales caigan en el mismo lugar físico que el flujo normal.
    """
    from credencializacion.core.settings import AppSettings

    if perfil:
        w_mm = float(perfil.get("page_width", 297.0))
        h_mm = float(perfil.get("page_height", 320.0))
        page = (mm_to_points(w_mm), mm_to_points(h_mm))
        positions = calculate_card_positions_from_profile(page, perfil)
    else:
        w_mm, h_mm = AppSettings.get_page_dimensions()
        page = (mm_to_points(w_mm), mm_to_points(h_mm))
        positions = calculate_card_positions_from_config(page, {})
    return page, positions


def _compose_side(
    image_paths: list[Path | None],
    out_path: Path,
    page_size: tuple[float, float],
    positions: list[tuple[float, float]],
    card_w_cm: float,
    card_h_cm: float,
    rotate: bool,
    cards_per_page: int = 2,
) -> Path:
    """Compone un PDF colocando una imagen por ranura (2 por hoja).

    Un elemento ``None`` deja la ranura en blanco pero CONSUME el espacio, para
    que frentes y vueltas queden alineados al voltear la hoja. El dibujado
    reproduce el bloque de imagen base de ``PDFEngine._render_card`` (incluida la
    rotación de credenciales verticales).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = Canvas(str(out_path), pagesize=page_size)
    card_w = cm_to_points(card_w_cm)
    card_h = cm_to_points(card_h_cm)

    for page_idx in range(0, len(image_paths), cards_per_page):
        page_imgs = image_paths[page_idx : page_idx + cards_per_page]
        for slot_idx, img in enumerate(page_imgs):
            if slot_idx >= len(positions):
                break
            if img is None:
                continue  # hueco en blanco: conserva el emparejado
            base = positions[slot_idx]
            c.saveState()
            if rotate:
                # Mismo transform que _render_card para credenciales verticales.
                c.translate(base[0] + card_h, base[1])
                c.rotate(90)
            else:
                c.translate(base[0], base[1])
            try:
                c.drawImage(
                    str(img), 0, 0,
                    width=card_w, height=card_h,
                    preserveAspectRatio=False, mask="auto",
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("No se pudo dibujar la imagen %s: %s", img, e)
            c.restoreState()
        c.showPage()

    c.save()
    logger.info("PDF compuesto desde carpeta: %s (%d ranuras)", out_path, len(image_paths))
    return out_path


def compose_from_folder(
    sides: FolderSides,
    out_dir: Path | str,
    *,
    card_w_cm: float = DEFAULT_CARD_W_CM,
    card_h_cm: float = DEFAULT_CARD_H_CM,
    rotate: bool = False,
    perfil: dict | None = None,
) -> tuple[str, str | None]:
    """Genera los PDFs de frentes y (si hay) vueltas desde una carpeta.

    Devuelve ``(frentes_pdf, vueltas_pdf | None)``.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    page_size, positions = _page_and_positions(perfil)

    frentes = _compose_side(
        list(sides.fronts), out_dir / "frentes.pdf",
        page_size, positions, card_w_cm, card_h_cm, rotate,
    )
    vueltas: Path | None = None
    if sides.backs is not None:
        vueltas = _compose_side(
            list(sides.backs), out_dir / "vueltas.pdf",
            page_size, positions, card_w_cm, card_h_cm, rotate,
        )
    return str(frentes), (str(vueltas) if vueltas else None)
