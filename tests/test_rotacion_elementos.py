"""Rotación por elemento en el diseño.

El ángulo vive en ``properties["rotation"]`` y es el mismo que muestra el
lienzo: positivo gira en sentido de las manecillas del reloj. El motor de PDF
gira el lienzo alrededor del centro del elemento, así que todos los tipos
(texto, imagen, QR…) quedan girados sin tocar su dibujo.

Lo que más importa probar es que la rotación se deshaga después de dibujar:
si el estado del canvas no se restaura, el elemento rotado se lleva girados a
todos los que vienen detrás.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest

from credencializacion.renderer.pdf_engine import PDFEngine
from credencializacion.renderer.rotation import (
    clamp_position,
    element_bounds,
    element_rotation,
    rotated_bounds,
)


class _Reg:
    def __init__(self, datos: dict) -> None:
        self.id = 1
        self.enrollment_code = "1"
        self.photo_path = None
        self.datos = datos

    def get_dato(self, key, default=""):
        return self.datos.get(key, default)


def _texto(
    campo: str, x: float, y: float, rotation: float | None = None,
    alignment: str = "left",
) -> dict:
    props = {"font_size": 10, "color": "#000000", "alignment": alignment}
    if rotation is not None:
        props["rotation"] = rotation
    return {
        "type": "text", "x": x, "y": y, "width": 40.0, "height": 8.0,
        "z_order": 1, "campo_dato": campo, "properties": props,
    }


def _plantilla(elementos: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(
        id=1, nombre="Prueba", orientacion="horizontal", ancho=8.5, alto=5.4,
        elementos_frente=elementos, elementos_vuelta=[], recursos={},
        posiciones_hoja={"cards_per_page": 1},
    )


def _bloques(pdf: Path) -> dict[str, fitz.Rect]:
    """Caja de cada texto del PDF, por su contenido."""
    with fitz.open(pdf) as doc:
        cajas: dict[str, fitz.Rect] = {}
        for bloque in doc[0].get_text("blocks"):
            texto = bloque[4].strip()
            if texto:
                cajas[texto] = fitz.Rect(bloque[:4])
        return cajas


def _render(tmp_path: Path, elementos: list[dict], datos: dict) -> Path:
    engine = PDFEngine(_plantilla(elementos), perfil=None)
    return engine.render([_Reg(datos)], "frente", tmp_path / "salida.pdf")


# ── El ángulo guardado ───────────────────────────────────────────────


def test_el_angulo_se_lee_de_las_propiedades():
    assert element_rotation(_texto("n", 0, 0, 90)) == 90.0
    assert element_rotation(_texto("n", 0, 0)) == 0.0


@pytest.mark.parametrize("guardado,esperado", [
    (370, 10.0), (-350, 10.0), (360, 0.0), (270, -90.0), (180, 180.0),
])
def test_el_angulo_se_normaliza(guardado, esperado):
    """Dar varias vueltas es lo mismo que girar una vez."""
    assert element_rotation(_texto("n", 0, 0, guardado)) == esperado


def test_un_angulo_invalido_no_rompe_el_render():
    elem = _texto("nombre", 5, 5)
    elem["properties"]["rotation"] = "noventa"

    assert element_rotation(elem) == 0.0


# ── Lo que sale en el PDF ────────────────────────────────────────────


def test_un_texto_rotado_90_queda_vertical(tmp_path):
    # Centrado en su caja: así el centro del texto coincide con el centro de
    # giro y se puede comprobar que gira en su lugar.
    horizontal = _render(
        tmp_path / "h", [_texto("nombre", 5, 5, alignment="center")],
        {"nombre": "ABCDEFGH"},
    )
    vertical = _render(
        tmp_path / "v", [_texto("nombre", 5, 5, 90, alignment="center")],
        {"nombre": "ABCDEFGH"},
    )

    caja_h = _bloques(horizontal)["ABCDEFGH"]
    caja_v = _bloques(vertical)["ABCDEFGH"]

    assert caja_h.width > caja_h.height   # acostado, como siempre
    assert caja_v.height > caja_v.width   # de pie tras rotar

    # Gira sobre su propio centro: no se va a otra parte de la tarjeta.
    assert caja_v.x0 + caja_v.width / 2 == pytest.approx(
        caja_h.x0 + caja_h.width / 2, abs=4
    )
    assert caja_v.y0 + caja_v.height / 2 == pytest.approx(
        caja_h.y0 + caja_h.height / 2, abs=4
    )


def test_la_rotacion_no_arrastra_al_siguiente_elemento(tmp_path):
    """Si no se restaura el canvas, lo que sigue también sale girado."""
    pdf = _render(
        tmp_path,
        [_texto("uno", 5, 5, 90), _texto("dos", 5, 25)],
        {"uno": "ROTADO", "dos": "DERECHO"},
    )

    cajas = _bloques(pdf)

    assert cajas["ROTADO"].height > cajas["ROTADO"].width
    assert cajas["DERECHO"].width > cajas["DERECHO"].height


def test_sin_rotacion_el_pdf_no_cambia(tmp_path):
    """Los diseños que ya existen (sin el campo) salen exactamente igual."""
    sin_campo = _render(tmp_path / "a", [_texto("nombre", 5, 5)], {"nombre": "IGUAL"})
    con_cero = _render(tmp_path / "b", [_texto("nombre", 5, 5, 0)], {"nombre": "IGUAL"})

    assert _bloques(sin_campo)["IGUAL"] == _bloques(con_cero)["IGUAL"]


# ── La caja que ocupa un elemento girado ─────────────────────────────


def test_girar_90_intercambia_ancho_y_alto_sin_mover_el_centro():
    dx, dy, ancho, alto = rotated_bounds(40, 10, 90)

    assert (ancho, alto) == (pytest.approx(10), pytest.approx(40))
    # El centro no se mueve: la esquina se corre la mitad de la diferencia.
    assert (dx, dy) == (pytest.approx(15.0), pytest.approx(-15.0))
    assert 0 + dx + ancho / 2 == pytest.approx(0 + 40 / 2)
    assert 0 + dy + alto / 2 == pytest.approx(0 + 10 / 2)


def test_sin_rotacion_la_caja_es_la_misma():
    assert rotated_bounds(40, 10, 0) == (0.0, 0.0, 40, 10)  # exacto, sin trigonometría
    assert element_bounds(_texto("n", 5, 7)) == (5.0, 7.0, 40.0, 8.0)


def test_girar_45_agranda_la_caja():
    _dx, _dy, ancho, alto = rotated_bounds(40, 10, 45)

    assert ancho == pytest.approx(35.36, abs=0.01)
    assert alto == pytest.approx(35.36, abs=0.01)


def test_la_caja_visual_incluye_la_posicion():
    x, y, ancho, alto = element_bounds(_texto("n", 10, 20, 90))

    # 40×8 de pie: 8 de ancho, centrada donde estaba.
    assert (round(ancho, 2), round(alto, 2)) == (8.0, 40.0)
    assert x == pytest.approx(10 + 16)
    assert y == pytest.approx(20 - 16)



# ── El tope contra el borde de la tarjeta ────────────────────────────
#
# Lo que reportó el operador: girado el elemento, el tope seguía usando el
# ancho sin girar y no se podía pegar al borde.

_TARJETA = (54.0, 85.6)  # tarjeta vertical, en mm


def test_un_elemento_girado_llega_al_borde_izquierdo():
    x, _y = clamp_position(-999, 20, 40, 10, 90, *_TARJETA)

    # Su caja visual (10 mm de ancho) queda pegada al borde.
    assert x + rotated_bounds(40, 10, 90)[0] == pytest.approx(0)


def test_un_elemento_girado_llega_al_borde_derecho():
    x, _y = clamp_position(999, 20, 40, 10, 90, *_TARJETA)

    dx, _dy, ancho, _alto = rotated_bounds(40, 10, 90)
    assert x + dx + ancho == pytest.approx(_TARJETA[0])


def test_el_tope_sin_rotacion_no_cambia():
    assert clamp_position(999, 999, 40, 10, 0, *_TARJETA) == (
        _TARJETA[0] - 40, _TARJETA[1] - 10,
    )
    # Lo que ya cabía se queda donde está.
    assert clamp_position(5, 5, 40, 10, 0, *_TARJETA) == (5, 5)


def test_un_elemento_mas_grande_que_la_tarjeta_se_ancla_a_la_esquina():
    x, y = clamp_position(30, 30, 200, 200, 0, *_TARJETA)

    assert (x, y) == (0, 0)
