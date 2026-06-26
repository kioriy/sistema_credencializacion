"""Pruebas unitarias de la utilidad pura ``renderer/text_fit.py``.

Estas pruebas usan un ``measure_width`` lineal SIMULADO (ancho proporcional al
tamaño de fuente) para validar la lógica de ajuste y anclaje sin depender de Qt
ni de ReportLab.

Validates: Requirements 2.1, 2.2, 2.3
"""
from __future__ import annotations

import pytest

from credencializacion.renderer.text_fit import (
    compute_anchor_x,
    compute_start_x,
    fit_font_size,
)

# Constante de proporcionalidad del medidor simulado.
K = 0.5


def linear_measure(k: float = K):
    """Crea un ``measure_width`` lineal: ancho = len(text) * size * k.

    El ancho es proporcional al número de caracteres y al tamaño de fuente, lo
    que reproduce la monotonía de las métricas reales sin sus irregularidades.
    """

    def _measure(text: str, size: float) -> float:
        return len(text) * size * k

    return _measure


# ---------------------------------------------------------------------------
# fit_font_size
# ---------------------------------------------------------------------------

class TestFitFontSize:
    def test_texto_que_cabe_devuelve_base(self):
        # "Ana" a tamaño 10 mide 3 * 10 * 0.5 = 15, cabe en una caja de 100.
        measure = linear_measure()
        result = fit_font_size(measure, "Ana", box_width=100.0, base_font_size=10.0)
        assert result == 10.0

    def test_texto_que_cabe_justo_devuelve_base(self):
        # Ancho exacto en el límite (<=) debe conservar el tamaño base.
        measure = linear_measure()
        # 4 * 10 * 0.5 = 20 == box_width
        result = fit_font_size(measure, "ABCD", box_width=20.0, base_font_size=10.0)
        assert result == 10.0

    def test_texto_doble_de_ancho_devuelve_aprox_mitad(self):
        # El texto mide el doble del ancho de la caja con el tamaño base:
        # medido = 10 * 10 * 0.5 = 50; box_width = 25 -> proporcional ~ base/2.
        measure = linear_measure()
        result = fit_font_size(
            measure, "0123456789", box_width=25.0, base_font_size=10.0
        )
        # Considera el posible ajuste fino x0.98; tolerancia razonable.
        assert result == pytest.approx(5.0, rel=0.05)
        # Nunca debe superar la mitad teórica (el ajuste solo reduce).
        assert result <= 5.0 + 1e-9

    def test_respeta_min_font_size(self):
        # Texto enorme en caja diminuta: el proporcional caería por debajo del
        # mínimo, así que debe devolver exactamente min_font_size.
        measure = linear_measure()
        result = fit_font_size(
            measure,
            "texto larguísimo que no cabe de ninguna forma",
            box_width=1.0,
            base_font_size=10.0,
            min_font_size=4.0,
        )
        assert result == 4.0

    def test_padding_reduce_ancho_util(self):
        # A mayor padding, el tamaño efectivo debe ser menor o igual.
        measure = linear_measure()
        sin_padding = fit_font_size(
            measure, "0123456789", box_width=30.0, base_font_size=10.0, padding=0.0
        )
        con_padding = fit_font_size(
            measure, "0123456789", box_width=30.0, base_font_size=10.0, padding=5.0
        )
        assert con_padding <= sin_padding

    def test_padding_puede_forzar_reduccion(self):
        # Texto que cabe sin padding pero no con padding suficientemente grande.
        measure = linear_measure()
        # medido = 4 * 10 * 0.5 = 20; box=24 cabe; con padding 5 -> util=14 < 20.
        sin_padding = fit_font_size(
            measure, "ABCD", box_width=24.0, base_font_size=10.0, padding=0.0
        )
        con_padding = fit_font_size(
            measure, "ABCD", box_width=24.0, base_font_size=10.0, padding=5.0
        )
        assert sin_padding == 10.0
        assert con_padding < 10.0

    # --- Casos borde -------------------------------------------------------

    def test_texto_vacio_devuelve_base(self):
        measure = linear_measure()
        result = fit_font_size(measure, "", box_width=10.0, base_font_size=10.0)
        assert result == 10.0

    def test_box_width_cero_devuelve_min(self):
        measure = linear_measure()
        result = fit_font_size(
            measure, "Ana", box_width=0.0, base_font_size=10.0, min_font_size=2.0
        )
        assert result == 2.0

    def test_box_width_negativo_devuelve_min(self):
        measure = linear_measure()
        result = fit_font_size(
            measure, "Ana", box_width=-5.0, base_font_size=10.0, min_font_size=2.0
        )
        assert result == 2.0

    def test_measure_devuelve_cero_conserva_base(self):
        # Un medidor que siempre devuelve 0 (p. ej. texto sin glifos visibles)
        # se interpreta como "cabe" y conserva el tamaño base.
        result = fit_font_size(
            lambda text, size: 0.0,
            "loquesea",
            box_width=10.0,
            base_font_size=10.0,
        )
        assert result == 10.0

    def test_min_mayor_que_base_se_normaliza(self):
        # Si min_font_size > base_font_size, el límite superior manda.
        measure = linear_measure()
        result = fit_font_size(
            measure,
            "texto que no cabe nada",
            box_width=1.0,
            base_font_size=8.0,
            min_font_size=20.0,
        )
        assert result == 8.0

    # --- Garantía de encaje ------------------------------------------------

    @pytest.mark.parametrize(
        "text,box_width,base",
        [
            ("0123456789", 25.0, 10.0),
            ("María Guadalupe de la Concepción", 40.0, 12.0),
            ("XXXXXXXXXXXXXXXXXXXX", 13.0, 9.0),
            ("a b c d e f g", 7.0, 11.0),
        ],
    )
    def test_garantia_de_encaje_cuando_se_reduce(self, text, box_width, base):
        # Cuando hay que reducir, el ancho medido con el tamaño devuelto debe
        # caber en el ancho útil de la caja (box_width - 2*padding).
        measure = linear_measure()
        padding = 1.0
        result = fit_font_size(
            measure, text, box_width=box_width, base_font_size=base,
            min_font_size=0.5, padding=padding,
        )
        available = box_width - 2 * padding
        assert measure(text, result) <= available + 1e-9

    def test_resultado_siempre_dentro_del_rango(self):
        measure = linear_measure()
        result = fit_font_size(
            measure, "texto cualquiera", box_width=18.0, base_font_size=14.0,
            min_font_size=3.0,
        )
        assert 3.0 <= result <= 14.0


# ---------------------------------------------------------------------------
# compute_anchor_x
# ---------------------------------------------------------------------------

class TestComputeAnchorX:
    def test_left(self):
        assert compute_anchor_x(10.0, 40.0, "left") == pytest.approx(10.0)

    def test_center(self):
        assert compute_anchor_x(10.0, 40.0, "center") == pytest.approx(30.0)

    def test_right(self):
        assert compute_anchor_x(10.0, 40.0, "right") == pytest.approx(50.0)

    def test_justify_se_trata_como_left(self):
        assert compute_anchor_x(10.0, 40.0, "justify") == pytest.approx(10.0)

    def test_valor_desconocido_se_trata_como_left(self):
        assert compute_anchor_x(10.0, 40.0, "loquesea") == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# compute_start_x
# ---------------------------------------------------------------------------

class TestComputeStartX:
    def test_left(self):
        # left inicia en el ancla, sin importar el ancho del texto.
        assert compute_start_x(10.0, 20.0, "left") == pytest.approx(10.0)

    def test_center(self):
        # center: anchor - text_width/2
        assert compute_start_x(30.0, 20.0, "center") == pytest.approx(20.0)

    def test_right(self):
        # right: anchor - text_width
        assert compute_start_x(50.0, 20.0, "right") == pytest.approx(30.0)

    def test_justify_se_trata_como_left(self):
        assert compute_start_x(10.0, 20.0, "justify") == pytest.approx(10.0)

    def test_valor_desconocido_se_trata_como_left(self):
        assert compute_start_x(10.0, 20.0, "otro") == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Integración anchor + start: el texto queda dentro de la caja
# ---------------------------------------------------------------------------

class TestAnclajeDentroDeCaja:
    @pytest.mark.parametrize("alignment", ["left", "center", "right"])
    def test_texto_que_cabe_no_se_sale_de_la_caja(self, alignment):
        x, w = 10.0, 40.0
        measure = linear_measure()
        text = "Ana"
        base = 10.0
        size = fit_font_size(measure, text, box_width=w, base_font_size=base)
        text_w = measure(text, size)
        anchor_x = compute_anchor_x(x, w, alignment)
        start_x = compute_start_x(anchor_x, text_w, alignment)
        # El texto cabe (text_w <= w), por lo que su extensión queda dentro.
        assert start_x >= x - 1e-9
        assert start_x + text_w <= x + w + 1e-9
