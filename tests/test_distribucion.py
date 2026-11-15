"""Distribución de varios elementos del diseño entre sí.

Las dos reglas de oro: los extremos no se mueven (quien distribuye ya los
colocó donde los quería) y cada elemento recupera su posición en el mismo
orden en que entró, para poder devolvérsela a su elemento del lienzo.
"""
from __future__ import annotations

import pytest

from credencializacion.services.distribucion import (
    HORIZONTAL_CENTROS,
    HORIZONTAL_ESPACIO,
    MINIMO_ELEMENTOS,
    VERTICAL_CENTROS,
    VERTICAL_ESPACIO,
    distribuir,
)


def _xs(cajas, resultado):
    return [round(x, 2) for x, _y in resultado]


def _ys(cajas, resultado):
    return [round(y, 2) for _x, y in resultado]


# ── Centros equidistantes ────────────────────────────────────────────


def test_centros_equidistantes_en_horizontal():
    # Tres cajas de 10 de ancho: extremos en 0 y 100, la de en medio pegada.
    cajas = [(0, 0, 10, 5), (15, 0, 10, 5), (100, 0, 10, 5)]

    resultado = distribuir(cajas, HORIZONTAL_CENTROS)

    # Centros: 5, 55, 105 → la de en medio arranca en 50.
    assert _xs(cajas, resultado) == [0, 50, 100]
    # El eje que no se distribuye no se toca.
    assert _ys(cajas, resultado) == [0, 0, 0]


def test_centros_equidistantes_con_tamanos_distintos():
    """Lo que se reparte es el centro, no la orilla."""
    cajas = [(0, 0, 10, 5), (20, 0, 30, 5), (100, 0, 10, 5)]

    resultado = distribuir(cajas, HORIZONTAL_CENTROS)

    centros = [x + c[2] / 2 for (x, _y), c in zip(resultado, cajas)]
    assert centros == [5.0, 55.0, 105.0]


def test_centros_equidistantes_en_vertical():
    cajas = [(0, 0, 10, 10), (0, 5, 10, 10), (0, 90, 10, 10)]

    resultado = distribuir(cajas, VERTICAL_CENTROS)

    assert _ys(cajas, resultado) == [0, 45, 90]
    assert _xs(cajas, resultado) == [0, 0, 0]


# ── Espaciado igual ──────────────────────────────────────────────────


def test_espaciado_igual_deja_el_mismo_hueco():
    cajas = [(0, 0, 10, 5), (20, 0, 30, 5), (100, 0, 10, 5)]

    resultado = distribuir(cajas, HORIZONTAL_ESPACIO)

    xs = _xs(cajas, resultado)
    anchos = [c[2] for c in cajas]
    huecos = [
        xs[i + 1] - (xs[i] + anchos[i]) for i in range(len(xs) - 1)
    ]
    assert huecos[0] == pytest.approx(huecos[1])
    # Los extremos siguen donde estaban.
    assert xs[0] == 0 and xs[-1] == 100


def test_espaciado_igual_en_vertical():
    cajas = [(0, 0, 10, 10), (0, 12, 10, 30), (0, 80, 10, 10)]

    resultado = distribuir(cajas, VERTICAL_ESPACIO)

    ys = _ys(cajas, resultado)
    altos = [c[3] for c in cajas]
    huecos = [ys[i + 1] - (ys[i] + altos[i]) for i in range(len(ys) - 1)]
    assert huecos[0] == pytest.approx(huecos[1])
    assert ys[0] == 0 and ys[-1] == 80


def test_si_no_caben_se_encima_lo_mismo_entre_todos():
    """Mejor un encimado parejo que amontonarlos al principio."""
    cajas = [(0, 0, 40, 5), (10, 0, 40, 5), (20, 0, 40, 5)]

    xs = _xs(cajas, distribuir(cajas, HORIZONTAL_ESPACIO))

    assert xs[0] == 0 and xs[-1] == 20
    assert xs[1] - xs[0] == pytest.approx(xs[2] - xs[1])


# ── Orden y casos límite ─────────────────────────────────────────────


def test_se_reparte_por_el_orden_visual_no_por_el_de_seleccion():
    """Da igual en qué orden se hayan ido sumando con Alt + clic."""
    cajas = [(100, 0, 10, 5), (15, 0, 10, 5), (0, 0, 10, 5)]

    resultado = distribuir(cajas, HORIZONTAL_CENTROS)

    # Cada caja conserva su lugar en la lista, con su posición nueva.
    assert _xs(cajas, resultado) == [100, 50, 0]


@pytest.mark.parametrize("n", [0, 1])
def test_con_un_solo_elemento_no_se_mueve_nada(n):
    cajas = [(i * 7, i * 3, 10, 5) for i in range(n)]

    assert distribuir(cajas, HORIZONTAL_CENTROS) == [(c[0], c[1]) for c in cajas]
    assert MINIMO_ELEMENTOS == 2


def test_un_modo_desconocido_no_mueve_nada():
    cajas = [(0, 0, 10, 5), (15, 0, 10, 5), (100, 0, 10, 5)]

    assert distribuir(cajas, "diagonal") == [(c[0], c[1]) for c in cajas]


def test_los_extremos_nunca_se_mueven():
    cajas = [(3, 1, 10, 5), (40, 1, 8, 5), (12, 1, 6, 5), (70, 1, 10, 5)]

    for modo in (HORIZONTAL_CENTROS, HORIZONTAL_ESPACIO):
        resultado = distribuir(cajas, modo)
        xs = {round(x, 2) for x, _y in resultado}
        assert 3 in xs      # el de más a la izquierda
        assert 70 in xs     # el de más a la derecha


# ── Los centros equidistantes además alinean ─────────────────────────
#
# Es lo que convierte una escalera en una fila (o una columna): sin esto,
# con elementos del mismo tamaño y ya repartidos, la opción no movía nada y
# parecía descompuesta.


def test_horizontal_centros_deja_los_elementos_en_una_fila():
    # Tres cajas iguales en escalera, como se ven en el diseñador.
    cajas = [(14, 5, 24, 10), (20, 14, 24, 10), (8, 23, 24, 10)]

    resultado = distribuir(cajas, HORIZONTAL_CENTROS)

    # Todos a la misma altura: el centro del bloque (de 5 a 33) es 19, así
    # que una caja de 10 de alto arranca en 14.
    assert _ys(cajas, resultado) == [14, 14, 14]
    # Y los centros horizontales quedan a la misma distancia.
    centros = sorted(x + c[2] / 2 for (x, _y), c in zip(resultado, cajas))
    assert centros[1] - centros[0] == pytest.approx(centros[2] - centros[1])


def test_vertical_centros_deja_los_elementos_en_una_columna():
    cajas = [(14, 5, 24, 10), (20, 14, 24, 10), (8, 23, 24, 10)]

    resultado = distribuir(cajas, VERTICAL_CENTROS)

    # Misma X para todos (el bloque va de 8 a 44, centro 26; caja de 24 → 14).
    assert _xs(cajas, resultado) == [14, 14, 14]
    centros = sorted(y + c[3] / 2 for (_x, y), c in zip(resultado, cajas))
    assert centros[1] - centros[0] == pytest.approx(centros[2] - centros[1])


def test_el_centro_comun_usa_el_bloque_no_el_promedio():
    """Dos juntas y una lejos: el conjunto no se corre hacia las dos juntas."""
    cajas = [(0, 0, 10, 10), (20, 2, 10, 10), (40, 40, 10, 10)]

    resultado = distribuir(cajas, HORIZONTAL_CENTROS)

    # El bloque va de y=0 a y=50 → centro 25 → una caja de 10 arranca en 20.
    assert _ys(cajas, resultado) == [20, 20, 20]


def test_el_espaciado_igual_no_toca_el_otro_eje():
    """La que ya funcionaba se queda como estaba."""
    cajas = [(14, 5, 24, 10), (20, 14, 24, 10), (8, 23, 24, 10)]

    assert _ys(cajas, distribuir(cajas, HORIZONTAL_ESPACIO)) == [5, 14, 23]
    assert _xs(cajas, distribuir(cajas, VERTICAL_ESPACIO)) == [14, 20, 8]


# ── La fila se abre lo justo para no encimarse ───────────────────────
#
# El caso que reportó el operador: tres textos del mismo tamaño en escalera.
# Sus centros ya estaban equidistantes, así que repartir "a secas" no movía
# nada; y al ponerlos en fila con esa separación se montaban unos sobre otros.

_TARJETA = (85.0, 54.0)  # tarjeta horizontal, en mm


def test_la_fila_se_abre_para_que_no_se_encimen():
    cajas = [(14, 5, 24, 10), (20, 14, 24, 10), (8, 23, 24, 10)]

    resultado = distribuir(cajas, HORIZONTAL_CENTROS, _TARJETA)

    xs = sorted(round(x, 2) for x, _y in resultado)
    # Cajas de 24 mm: una tras otra, sin traslape.
    assert xs == [0, 24, 48]


def test_la_columna_tambien_se_abre():
    cajas = [(10, 5, 24, 10), (10, 8, 24, 10), (10, 11, 24, 10)]

    resultado = distribuir(cajas, VERTICAL_CENTROS, _TARJETA)

    ys = sorted(round(y, 2) for _x, y in resultado)
    assert [round(ys[i + 1] - ys[i], 2) for i in (0, 1)] == [10, 10]


def test_la_fila_no_se_pasa_del_borde_de_la_tarjeta():
    # Pegadas al borde derecho: al abrirse tendría que recorrerse hacia dentro.
    cajas = [(60, 5, 24, 10), (62, 14, 24, 10), (58, 23, 24, 10)]

    resultado = distribuir(cajas, HORIZONTAL_CENTROS, _TARJETA)

    bordes = [(x, x + c[2]) for (x, _y), c in zip(resultado, cajas)]
    assert min(b[0] for b in bordes) >= -0.01
    assert max(b[1] for b in bordes) <= _TARJETA[0] + 0.01


def test_si_no_caben_en_la_tarjeta_se_reparten_dentro():
    """Cuatro cajas de 24 mm no caben en 85: se encima lo mínimo, adentro."""
    cajas = [(2, 5, 24, 10), (10, 8, 24, 10), (18, 11, 24, 10), (26, 14, 24, 10)]

    resultado = distribuir(cajas, HORIZONTAL_CENTROS, _TARJETA)

    xs = sorted(x for x, _y in resultado)
    assert xs[0] >= -0.01
    assert xs[-1] + 24 <= _TARJETA[0] + 0.01
    # El reparto sigue siendo parejo aunque se toquen.
    pasos = [xs[i + 1] - xs[i] for i in range(3)]
    assert pasos[1] == pytest.approx(pasos[0], abs=0.01)
    assert pasos[2] == pytest.approx(pasos[0], abs=0.01)


def test_sin_limite_la_fila_se_abre_igual():
    """Sin tarjeta que respetar, manda no encimarse."""
    cajas = [(14, 5, 24, 10), (20, 14, 24, 10), (8, 23, 24, 10)]

    xs = sorted(round(x, 2) for x, _y in distribuir(cajas, HORIZONTAL_CENTROS))

    assert [round(xs[i + 1] - xs[i], 2) for i in (0, 1)] == [24, 24]


# ── Con dos elementos ────────────────────────────────────────────────
#
# Emparejar dos textos es de lo más común, así que dos basta: los centros
# los dejan en fila, uno junto al otro.


def test_dos_elementos_quedan_en_fila_pegados():
    cajas = [(5, 5, 24, 10), (9, 20, 24, 10)]

    resultado = distribuir(cajas, HORIZONTAL_CENTROS, _TARJETA)

    # Misma altura: el bloque va de 5 a 30, centro 17.5 → caja de 10 en 12.5.
    assert _ys(cajas, resultado) == [12.5, 12.5]
    # Y uno tras otro, sin encimarse (24 mm de ancho cada uno).
    xs = sorted(round(x, 2) for x, _y in resultado)
    assert xs[1] - xs[0] == 24


def test_dos_elementos_en_columna():
    cajas = [(5, 5, 24, 10), (40, 8, 24, 10)]

    resultado = distribuir(cajas, VERTICAL_CENTROS, _TARJETA)

    # Misma X: el bloque va de 5 a 64, centro 34.5 → caja de 24 en 22.5.
    assert _xs(cajas, resultado) == [22.5, 22.5]
    ys = sorted(round(y, 2) for _x, y in resultado)
    assert ys[1] - ys[0] == 10


def test_dos_elementos_separados_no_se_juntan():
    """Si ya no se encimaban, solo se alinean: la separación se respeta."""
    cajas = [(0, 5, 24, 10), (50, 20, 24, 10)]

    resultado = distribuir(cajas, HORIZONTAL_CENTROS, _TARJETA)

    assert _xs(cajas, resultado) == [0, 50]
    assert _ys(cajas, resultado) == [12.5, 12.5]


def test_dos_elementos_con_espaciado_igual_se_quedan_donde_estan():
    """No hay hueco intermedio que repartir; el editor lo avisa."""
    cajas = [(5, 5, 24, 10), (40, 20, 24, 10)]

    assert distribuir(cajas, HORIZONTAL_ESPACIO, _TARJETA) == [(5, 5), (40, 20)]
    assert distribuir(cajas, VERTICAL_ESPACIO, _TARJETA) == [(5, 5), (40, 20)]
