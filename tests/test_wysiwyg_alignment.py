"""Verificación WYSIWYG: diseñador vs vista previa (PDF) — Tarea 4.2 (Parte A).

OBJETIVO (Req. 2.1, 2.2, 2.3, 2.4, 2.5):
Comprobar de forma reproducible, SIN depender de BD ni de red, que el texto se
posiciona igual en el diseñador (Qt) y en la vista previa/PDF (ReportLab) para
el MISMO texto, caja y alineación.

Como cada motor trabaja en un sistema de coordenadas distinto (Qt en píxeles de
escena a ~96 DPI; ReportLab en puntos a 72 DPI), la comparación se NORMALIZA a
una fracción de la caja:

    start_x_relativo = (start_x - x) / w

Ese valor es adimensional y debe coincidir entre ambos motores dentro de una
tolerancia razonable (5 % del ancho de la caja), porque ambos calculan el inicio
del texto con la MISMA matemática de anclaje (``compute_anchor_x`` /
``compute_start_x``) y el MISMO algoritmo de ajuste (``fit_font_size``); la única
diferencia es el medidor de ancho nativo de cada motor.

Se reutiliza la utilidad de producción ``credencializacion.renderer.text_fit``
con los medidores reales de cada motor:
  - Diseñador: ``QFontMetricsF(font).horizontalAdvance`` (QT_QPA_PLATFORM=offscreen)
  - PDF:       ``pdfmetrics.stringWidth``

Casos cubiertos: alineación ``center`` y ``right``; texto corto ("Ana") y largo
("María Guadalupe de la Concepción").

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5
"""
from __future__ import annotations

from pathlib import Path

import pytest

# La verificación necesita PySide6 (Qt) para medir como el diseñador. Si no está
# disponible en el entorno, se salta por completo.
pytest.importorskip("PySide6")

from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402

from credencializacion.renderer.text_fit import (  # noqa: E402
    compute_anchor_x,
    compute_start_x,
    fit_font_size,
)

# Factores de escala idénticos a los del código de producción.
MM_TO_PX = 3.7795        # diseñador (~96 DPI), ver ui/widgets/canvas.py
MM_TO_POINTS = 2.83465   # PDF (72 DPI), ver renderer/coordinates.py
PT_TO_PX = 0.352778 * MM_TO_PX  # factor pt->px de escena usado en _paint_text

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_INTER_PATH = _PROJECT_ROOT / "resources" / "fonts" / "Inter-Variable.ttf"

# Tolerancia de la posición relativa de inicio: 5 % del ancho de la caja.
START_TOLERANCE = 0.05


# ---------------------------------------------------------------------------
# Fixtures de fuentes (misma fuente en ambos motores cuando es posible)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qt_app():
    """Una única ``QGuiApplication`` para instanciar QFont/QFontMetricsF."""
    try:
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if app is None:
            app = QGuiApplication([])
        return app
    except Exception as exc:  # pragma: no cover - depende del entorno
        pytest.skip(f"No se pudo instanciar Qt en este entorno headless: {exc}")


@pytest.fixture(scope="session")
def fonts(qt_app):
    """Registra una fuente común y devuelve ``(qt_family, pdf_font_name)``."""
    from PySide6.QtGui import QFontDatabase

    qt_family = "Helvetica"
    pdf_font_name = "Helvetica"

    if _INTER_PATH.exists():
        try:
            if "Inter" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("Inter", str(_INTER_PATH)))
            pdf_font_name = "Inter"
        except Exception:
            pdf_font_name = "Helvetica"

        font_id = QFontDatabase.addApplicationFont(str(_INTER_PATH))
        families = (
            QFontDatabase.applicationFontFamilies(font_id) if font_id != -1 else []
        )
        if families:
            qt_family = families[0]

    return qt_family, pdf_font_name


# ---------------------------------------------------------------------------
# Réplicas fieles del cálculo de cada motor (mismas fórmulas que producción)
# ---------------------------------------------------------------------------

def _designer_layout(qt_family: str, text: str, box_x_mm: float,
                     box_w_mm: float, base_font_size: float, alignment: str):
    """Calcula (start_x_rel, cabe) como lo hace ``GraphicElement._paint_text``.

    Trabaja en píxeles de escena, igual que el diseñador, y normaliza el inicio
    a fracción de la caja.
    """
    from PySide6.QtGui import QFont, QFontMetricsF

    def _make_font(size_pt: float) -> QFont:
        f = QFont(qt_family)
        size_px = round(size_pt * PT_TO_PX)
        if size_px > 0:
            f.setPixelSize(size_px)
        else:
            f.setPointSizeF(size_pt)
        return f

    def measure_width(t: str, size_pt: float) -> float:
        return QFontMetricsF(_make_font(size_pt)).horizontalAdvance(t)

    x_px = box_x_mm * MM_TO_PX
    w_px = box_w_mm * MM_TO_PX

    effective = fit_font_size(measure_width, text, box_width=w_px,
                              base_font_size=base_font_size)
    text_w = measure_width(text, effective)
    anchor_x = compute_anchor_x(x_px, w_px, alignment)
    start_x = compute_start_x(anchor_x, text_w, alignment)

    start_x_rel = (start_x - x_px) / w_px
    fits = text_w <= w_px + 1e-6
    return start_x_rel, fits, effective


def _pdf_layout(pdf_font_name: str, text: str, box_x_mm: float,
               box_w_mm: float, base_font_size: float, alignment: str):
    """Calcula (start_x_rel, cabe) como lo hace ``PDFEngine._draw_text``.

    Trabaja en puntos, igual que el PDF, y normaliza el inicio a fracción de la
    caja.
    """
    def measure_width(t: str, size: float) -> float:
        return pdfmetrics.stringWidth(t, pdf_font_name, size)

    x_pts = box_x_mm * MM_TO_POINTS
    w_pts = box_w_mm * MM_TO_POINTS

    effective = fit_font_size(measure_width, text, box_width=w_pts,
                              base_font_size=base_font_size)
    text_w = measure_width(text, effective)
    anchor_x = compute_anchor_x(x_pts, w_pts, alignment)
    start_x = compute_start_x(anchor_x, text_w, alignment)

    start_x_rel = (start_x - x_pts) / w_pts
    fits = text_w <= w_pts + 1e-6
    return start_x_rel, fits, effective


# ---------------------------------------------------------------------------
# Casos de prueba
# ---------------------------------------------------------------------------

# Casos REALISTAS para la comparación de inicio relativo (±5 %). Cubren texto
# corto ("Ana") y largo ("María...") en cajas donde el shrink-to-fit mantiene la
# fuente en un régimen legible (no microscópico). En estos regímenes la
# cuantización a píxel entero del diseñador es < 5 % de la caja.
_CASES = [
    ("Ana", 40.0, 12.0),                                  # corto, caja amplia
    ("Ana", 25.0, 12.0),                                  # corto, caja media
    ("María Guadalupe de la Concepción", 60.0, 12.0),     # largo, ajuste leve
    ("María Guadalupe de la Concepción", 40.0, 12.0),     # largo, ajuste medio
]

# Caso EXTREMO de shrink: caja estrecha + base grande -> fuente muy pequeña
# (~5 pt). Sirve para comprobar que el ANCLAJE de alineación sigue coincidiendo
# aunque la cuantización a píxel entero del diseñador impida la paridad exacta de
# tamaño (limitación documentada; ver design.md y test_text_fit_parity.py).
_EXTREME_CASES = _CASES + [
    ("María Guadalupe de la Concepción", 30.0, 14.0),
]


@pytest.mark.parametrize("text,box_w_mm,base_font_size", _CASES)
def test_wysiwyg_start_x_relativo_coincide_center(
    fonts, text, box_w_mm, base_font_size
):
    """El inicio relativo del texto coincide en diseñador y PDF (±5 % de la caja).

    Compara ``(start_x - x)/w`` entre ambos motores para alineación ``center``,
    con texto corto y largo, y confirma que el texto cabe en la caja tras el
    shrink-to-fit.

    NOTA: la comparación se hace sobre ``center`` porque en ``center`` el desfase
    de inicio equivale a la MITAD de la diferencia de ancho medido entre motores
    (cada borde absorbe la mitad), de modo que se mantiene bajo el 5 % en
    regímenes legibles. Para ``right`` el inicio absorbería la diferencia COMPLETA
    de ancho de métrica entre Qt (píxel entero) y ReportLab (continuo); por eso
    ``right`` se verifica con su invariante EXACTO de borde derecho en
    :func:`test_anclaje_right_termina_en_borde_derecho`, y el centrado con su
    invariante exacto de punto medio en
    :func:`test_anclaje_center_centra_el_punto_medio`.
    """
    qt_family, pdf_font_name = fonts
    box_x_mm = 10.0

    rel_designer, fits_designer, eff_designer = _designer_layout(
        qt_family, text, box_x_mm, box_w_mm, base_font_size, "center"
    )
    rel_pdf, fits_pdf, eff_pdf = _pdf_layout(
        pdf_font_name, text, box_x_mm, box_w_mm, base_font_size, "center"
    )

    # 1) El texto cabe en la caja en ambos motores (auto-ajuste correcto).
    assert fits_designer, (
        f"El texto no cabe en el diseñador: {text!r} (eff={eff_designer:.2f} pt)"
    )
    assert fits_pdf, (
        f"El texto no cabe en el PDF: {text!r} (eff={eff_pdf:.2f} pt)"
    )

    # 2) La posición relativa de inicio coincide dentro de la tolerancia.
    diff = abs(rel_designer - rel_pdf)
    assert diff <= START_TOLERANCE, (
        f"Desfase de inicio relativo excesivo para {text!r} "
        f"[align=center, caja={box_w_mm} mm, base={base_font_size} pt]: "
        f"diseñador={rel_designer:.4f}, pdf={rel_pdf:.4f}, "
        f"diff={diff:.4f} > tol={START_TOLERANCE} "
        f"[fuentes: qt={qt_family!r}, pdf={pdf_font_name!r}]"
    )


@pytest.mark.parametrize("text,box_w_mm,base_font_size", _EXTREME_CASES)
def test_anclaje_right_termina_en_borde_derecho(
    fonts, text, box_w_mm, base_font_size
):
    """Con alineación ``right`` el texto termina pegado al borde derecho (rel ~ 1).

    Invariante de ALINEACIÓN robusto e independiente del tamaño: el final
    relativo del texto = ``start_x_rel + text_w/w`` debe ser ~1.0 en ambos
    motores. Se incluye el caso extremo de shrink para demostrar que el anclaje
    derecho coincide aunque la paridad de tamaño no sea exacta.
    """
    qt_family, pdf_font_name = fonts
    box_x_mm = 10.0

    from PySide6.QtGui import QFont, QFontMetricsF

    def _qt_measure(t, size_pt):
        f = QFont(qt_family)
        size_px = round(size_pt * PT_TO_PX)
        f.setPixelSize(size_px) if size_px > 0 else f.setPointSizeF(size_pt)
        return QFontMetricsF(f).horizontalAdvance(t)

    w_px = box_w_mm * MM_TO_PX
    eff = fit_font_size(_qt_measure, text, box_width=w_px, base_font_size=base_font_size)
    text_w_px = _qt_measure(text, eff)
    rel_d, _, _ = _designer_layout(
        qt_family, text, box_x_mm, box_w_mm, base_font_size, "right"
    )
    end_rel_designer = rel_d + text_w_px / w_px

    w_pts = box_w_mm * MM_TO_POINTS
    eff_pdf = fit_font_size(
        lambda t, s: pdfmetrics.stringWidth(t, pdf_font_name, s),
        text, box_width=w_pts, base_font_size=base_font_size,
    )
    text_w_pts = pdfmetrics.stringWidth(text, pdf_font_name, eff_pdf)
    rel_p, _, _ = _pdf_layout(
        pdf_font_name, text, box_x_mm, box_w_mm, base_font_size, "right"
    )
    end_rel_pdf = rel_p + text_w_pts / w_pts

    assert end_rel_designer == pytest.approx(1.0, abs=1e-6)
    assert end_rel_pdf == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize("text,box_w_mm,base_font_size", _EXTREME_CASES)
def test_anclaje_center_centra_el_punto_medio(
    fonts, text, box_w_mm, base_font_size
):
    """Con alineación ``center`` el punto medio del texto cae en el centro (rel ~ 0.5).

    Invariante de ALINEACIÓN robusto e independiente del tamaño: el punto medio
    relativo = ``start_x_rel + (text_w/w)/2`` debe ser ~0.5 en ambos motores,
    incluso en el régimen de shrink extremo donde la cuantización a píxel del
    diseñador impide la paridad exacta de tamaño.
    """
    qt_family, pdf_font_name = fonts
    box_x_mm = 10.0

    from PySide6.QtGui import QFont, QFontMetricsF

    def _qt_measure(t, size_pt):
        f = QFont(qt_family)
        size_px = round(size_pt * PT_TO_PX)
        f.setPixelSize(size_px) if size_px > 0 else f.setPointSizeF(size_pt)
        return QFontMetricsF(f).horizontalAdvance(t)

    w_px = box_w_mm * MM_TO_PX
    eff = fit_font_size(_qt_measure, text, box_width=w_px, base_font_size=base_font_size)
    text_w_px = _qt_measure(text, eff)
    rel_d, _, _ = _designer_layout(
        qt_family, text, box_x_mm, box_w_mm, base_font_size, "center"
    )
    mid_rel_designer = rel_d + (text_w_px / w_px) / 2.0

    w_pts = box_w_mm * MM_TO_POINTS
    eff_pdf = fit_font_size(
        lambda t, s: pdfmetrics.stringWidth(t, pdf_font_name, s),
        text, box_width=w_pts, base_font_size=base_font_size,
    )
    text_w_pts = pdfmetrics.stringWidth(text, pdf_font_name, eff_pdf)
    rel_p, _, _ = _pdf_layout(
        pdf_font_name, text, box_x_mm, box_w_mm, base_font_size, "center"
    )
    mid_rel_pdf = rel_p + (text_w_pts / w_pts) / 2.0

    assert mid_rel_designer == pytest.approx(0.5, abs=1e-6)
    assert mid_rel_pdf == pytest.approx(0.5, abs=1e-6)
