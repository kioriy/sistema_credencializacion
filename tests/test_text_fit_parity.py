"""Prueba de paridad de medición entre el diseñador (Qt) y el PDF (ReportLab).

OBJETIVO (Req. 2.4 - coincidencia visual práctica diseñador vs vista previa):
Para una misma fuente, texto y caja, se compara el tamaño de fuente EFECTIVO
(``effective_pt``) que produce el shrink-to-fit (``fit_font_size``) usando dos
medidores distintos:

- Qt: ``QFontMetricsF(font).horizontalAdvance(text)`` con la fuente escalada a
  píxeles de escena mediante ``size_pt * 0.352778 * MM_TO_PX`` (factor del
  diseñador, ver ``ui/widgets/canvas.py``), y ``box_width`` en píxeles de escena
  (``ancho_caja_mm * MM_TO_PX``).
- ReportLab: ``pdfmetrics.stringWidth(text, fontName, size_pt)`` en puntos, con
  ``box_width`` en puntos (``ancho_caja_mm * MM_TO_POINTS``).

Cada motor usa su propio sistema de unidades de caja consistente, de modo que la
comparación de los ``effective_pt`` resultantes es justa: ambos representan el
tamaño en PUNTOS al que se reduce la fuente para caber en la MISMA caja física.

LIMITACIÓN DOCUMENTADA: las métricas de QFontMetricsF y de ReportLab no son
idénticas al píxel (difieren por hinting, kerning, redondeo a pixelSize entero y
la propia implementación del motor de fuentes). Esta prueba NO busca exactitud
perfecta, sino DETECTAR DIVERGENCIAS GROSERAS de paridad; por eso usa una
tolerancia generosa. Es una prueba OPCIONAL/TOLERANTE cuyo fin es documentar y
vigilar la paridad, no bloquear la entrega.

Para una comparación lo más fiel posible se intenta usar la fuente Inter del
proyecto (``resources/fonts/Inter-Variable.ttf``), registrándola en ReportLab
con ``TTFont`` y cargándola en Qt con ``QFontDatabase.addApplicationFont``. Si
no estuviera disponible, se cae a la familia lógica 'Helvetica' en ambos
motores (métricas no idénticas, de ahí la tolerancia generosa).

Validates: Requirements 2.4
"""
from __future__ import annotations

from pathlib import Path

import pytest

# La prueba requiere PySide6 (Qt). Si no está disponible, se salta por completo.
pytest.importorskip("PySide6")

from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402

from credencializacion.renderer.text_fit import fit_font_size  # noqa: E402

# Factores de escala de cada motor (idénticos a los del código de producción).
MM_TO_PX = 3.7795        # diseñador (~96 DPI), ver ui/widgets/canvas.py
MM_TO_POINTS = 2.83465   # PDF (72 DPI), ver renderer/coordinates.py
PT_TO_PX = 0.352778 * MM_TO_PX  # factor pt->px de escena usado en _paint_text

# Ruta de la fuente Inter del proyecto.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_INTER_PATH = _PROJECT_ROOT / "resources" / "fonts" / "Inter-Variable.ttf"


@pytest.fixture(scope="session")
def qt_app():
    """Crea una única ``QGuiApplication`` para instanciar QFont/QFontMetricsF.

    Requiere un backend de plataforma; en CI/headless se usa
    ``QT_QPA_PLATFORM=offscreen``. Si Qt no puede instanciarse en este entorno,
    la prueba se salta con un motivo claro (entrega válida de tarea opcional).
    """
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
    """Registra una fuente común en ambos motores y devuelve sus nombres lógicos.

    Returns:
        Tupla ``(qt_family, pdf_font_name)`` con la familia a usar en Qt y el
        nombre registrado en ReportLab. Se prefiere Inter del proyecto; si no
        está disponible se cae a 'Helvetica' en ambos motores.
    """
    from PySide6.QtGui import QFontDatabase

    qt_family = "Helvetica"
    pdf_font_name = "Helvetica"

    if _INTER_PATH.exists():
        # Registrar Inter en ReportLab.
        try:
            if "Inter" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("Inter", str(_INTER_PATH)))
            pdf_font_name = "Inter"
        except Exception:
            pdf_font_name = "Helvetica"

        # Cargar Inter en Qt y obtener su familia real.
        font_id = QFontDatabase.addApplicationFont(str(_INTER_PATH))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id != -1 else []
        if families:
            qt_family = families[0]

    return qt_family, pdf_font_name


def _make_qt_measure(qt_family: str):
    """Crea un medidor Qt en píxeles de escena, igual que el diseñador."""
    from PySide6.QtGui import QFont, QFontMetricsF

    def measure_qt(text: str, size_pt: float) -> float:
        font = QFont(qt_family)
        size_px = round(size_pt * PT_TO_PX)
        if size_px > 0:
            font.setPixelSize(size_px)
        else:
            font.setPointSizeF(size_pt)
        return QFontMetricsF(font).horizontalAdvance(text)

    return measure_qt


def _make_pdf_measure(pdf_font_name: str):
    """Crea un medidor ReportLab en puntos."""

    def measure_pdf(text: str, size_pt: float) -> float:
        return pdfmetrics.stringWidth(text, pdf_font_name, size_pt)

    return measure_pdf


# Tolerancia relativa generosa: las métricas entre motores no son idénticas.
# El objetivo es detectar divergencias groseras, no exactitud perfecta.
PARITY_TOLERANCE = 0.25  # 25 % del tamaño base


@pytest.mark.parametrize(
    "text,box_width_mm,base_font_size",
    [
        # Texto corto que probablemente cabe sin reducir en una caja amplia.
        ("Ana", 40.0, 12.0),
        # Texto largo en una caja estrecha que FUERZA reducción en ambos motores.
        ("María Guadalupe de la Concepción", 30.0, 12.0),
        ("María Guadalupe de la Concepción", 20.0, 14.0),
        # Caso intermedio.
        ("Juan Pérez", 25.0, 12.0),
    ],
)
def test_paridad_effective_size_qt_vs_pdf(fonts, text, box_width_mm, base_font_size):
    """El ``effective_pt`` del diseñador y del PDF difieren bajo la tolerancia.

    Cada motor mide en sus unidades nativas con su propia caja consistente
    (Qt en px de escena, ReportLab en puntos), pero ``fit_font_size`` devuelve
    en ambos casos un tamaño en PUNTOS. Esos puntos efectivos deben coincidir
    de forma aproximada para que el diseñador sea visualmente equivalente a la
    vista previa.
    """
    qt_family, pdf_font_name = fonts

    measure_qt = _make_qt_measure(qt_family)
    measure_pdf = _make_pdf_measure(pdf_font_name)

    box_width_px = box_width_mm * MM_TO_PX
    box_width_pts = box_width_mm * MM_TO_POINTS

    effective_pt_qt = fit_font_size(
        measure_qt, text, box_width=box_width_px, base_font_size=base_font_size
    )
    effective_pt_pdf = fit_font_size(
        measure_pdf, text, box_width=box_width_pts, base_font_size=base_font_size
    )

    diff_rel = abs(effective_pt_qt - effective_pt_pdf) / base_font_size

    assert diff_rel <= PARITY_TOLERANCE, (
        f"Divergencia de paridad excesiva para {text!r} "
        f"(caja {box_width_mm} mm, base {base_font_size} pt): "
        f"Qt={effective_pt_qt:.3f} pt, PDF={effective_pt_pdf:.3f} pt, "
        f"diff_rel={diff_rel:.3f} > tol={PARITY_TOLERANCE} "
        f"[fuentes: qt={qt_family!r}, pdf={pdf_font_name!r}]"
    )


def test_ambos_motores_reducen_texto_largo(fonts):
    """Sanity check: un texto largo en caja estrecha reduce por debajo del base.

    Confirma que la prueba ejerce realmente la ruta de shrink-to-fit en ambos
    motores (si no redujera, la paridad sería trivial y poco informativa).
    """
    qt_family, pdf_font_name = fonts
    measure_qt = _make_qt_measure(qt_family)
    measure_pdf = _make_pdf_measure(pdf_font_name)

    text = "María Guadalupe de la Concepción"
    box_width_mm = 20.0
    base = 14.0

    eff_qt = fit_font_size(
        measure_qt, text, box_width=box_width_mm * MM_TO_PX, base_font_size=base
    )
    eff_pdf = fit_font_size(
        measure_pdf, text, box_width=box_width_mm * MM_TO_POINTS, base_font_size=base
    )

    assert eff_qt < base
    assert eff_pdf < base
