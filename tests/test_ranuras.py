"""Impresión en una sola ranura de la charola.

La charola tiene dos ranuras y normalmente se imprimen dos credenciales por
hoja. Cuando solo se puede usar una (la otra está ocupada o dañada), se elige
la ranura y entonces sale UNA credencial por hoja, en esa posición.

Lo que se prueba es que no se pierda ninguna credencial al reducir las
ranuras —el riesgo real: el motor metía dos tarjetas por hoja aunque solo
hubiera una posición— y que elegir «ambas» deje el PDF idéntico a como era.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest

from credencializacion.renderer.coordinates import (
    RANURAS_AMBAS,
    cm_to_points,
    filtrar_por_ranura,
)
from credencializacion.renderer.folder_compose import FolderSides, compose_from_folder
from credencializacion.renderer.pdf_engine import PDFEngine

# Perfil de charola de prueba. El origen Y de una ranura es el borde INFERIOR
# de la tarjeta medido desde arriba de la hoja, así que la 1 (la más cercana
# al borde) lleva el valor menor.
_SEPARACION_CM = 6.0
_PERFIL = {
    "slot1_x": 1.0, "slot1_y": 6.0,
    "slot2_x": 1.0, "slot2_y": 6.0 + _SEPARACION_CM,
    "page_width": 210.0, "page_height": 297.0,
    "printer": "",
}


class _Reg:
    def __init__(self, nombre: str) -> None:
        self.id = 0
        self.enrollment_code = nombre
        self.photo_path = None
        self.datos = {"nombre": nombre}

    def get_dato(self, key, default=""):
        return self.datos.get(key, default)


def _plantilla() -> SimpleNamespace:
    return SimpleNamespace(
        id=1, nombre="Alumno", orientacion="horizontal", ancho=8.5, alto=5.4,
        elementos_frente=[{
            "type": "text", "x": 5.0, "y": 5.0, "width": 70.0, "height": 8.0,
            "z_order": 1, "campo_dato": "nombre",
            "properties": {"font_size": 10, "color": "#000000"},
        }],
        elementos_vuelta=[], recursos={}, posiciones_hoja={},
    )


def _textos_por_pagina(pdf: Path) -> list[list[str]]:
    with fitz.open(pdf) as doc:
        return [
            [b[4].strip() for b in page.get_text("blocks") if b[4].strip()]
            for page in doc
        ]


def _posiciones(pdf: Path) -> list[tuple[float, float]]:
    """Esquina inferior izquierda de cada texto, por página (en puntos)."""
    with fitz.open(pdf) as doc:
        salida = []
        for page in doc:
            for b in page.get_text("blocks"):
                if b[4].strip():
                    salida.append((round(b[0], 1), round(page.rect.height - b[3], 1)))
        return salida


# ── Recorte de posiciones ────────────────────────────────────────────


def test_filtrar_por_ranura_deja_solo_la_pedida():
    posiciones = [(0.0, 100.0), (0.0, 50.0)]

    assert filtrar_por_ranura(posiciones, RANURAS_AMBAS) == posiciones
    assert filtrar_por_ranura(posiciones, None) == posiciones
    assert filtrar_por_ranura(posiciones, "1") == [(0.0, 100.0)]
    assert filtrar_por_ranura(posiciones, 2) == [(0.0, 50.0)]
    # Una ranura que no existe no debe dejar la hoja vacía.
    assert filtrar_por_ranura(posiciones, "3") == posiciones
    assert filtrar_por_ranura(posiciones, "x") == posiciones


# ── Motor de PDF ─────────────────────────────────────────────────────


@pytest.mark.parametrize("ranura", ["1", "2"])
def test_una_sola_ranura_imprime_una_credencial_por_hoja(tmp_path, ranura):
    registros = [_Reg("Ana"), _Reg("Beto"), _Reg("Caro")]

    engine = PDFEngine(_plantilla(), perfil=_PERFIL, ranuras=ranura)
    pdf = engine.render(registros, "frente", tmp_path / f"r{ranura}.pdf")

    # Ninguna credencial se pierde: una por hoja, en orden.
    assert _textos_por_pagina(pdf) == [["Ana"], ["Beto"], ["Caro"]]
    # Todas caen en la misma posición de la hoja (la de esa ranura).
    assert len(set(_posiciones(pdf))) == 1


def test_cada_ranura_imprime_en_su_lugar_de_la_hoja(tmp_path):
    """La ranura 2 queda más abajo que la 1, por su separación en la charola."""
    reg = [_Reg("Ana")]
    y1 = _posiciones(
        PDFEngine(_plantilla(), perfil=_PERFIL, ranuras="1")
        .render(reg, "frente", tmp_path / "a.pdf")
    )[0][1]
    y2 = _posiciones(
        PDFEngine(_plantilla(), perfil=_PERFIL, ranuras="2")
        .render(reg, "frente", tmp_path / "b.pdf")
    )[0][1]

    assert y1 - y2 == pytest.approx(cm_to_points(_SEPARACION_CM), abs=0.5)

    # Y coinciden con las posiciones que usa el modo de dos por hoja.
    ambas = _posiciones(
        PDFEngine(_plantilla(), perfil=_PERFIL)
        .render([_Reg("Ana"), _Reg("Beto")], "frente", tmp_path / "c.pdf")
    )
    assert [round(y, 1) for _, y in ambas] == [round(y1, 1), round(y2, 1)]


def test_ambas_ranuras_sigue_dando_dos_por_hoja(tmp_path):
    registros = [_Reg("Ana"), _Reg("Beto"), _Reg("Caro")]

    engine = PDFEngine(_plantilla(), perfil=_PERFIL)
    pdf = engine.render(registros, "frente", tmp_path / "ambas.pdf")

    assert _textos_por_pagina(pdf) == [["Ana", "Beto"], ["Caro"]]


def test_la_cola_tambien_respeta_la_ranura(tmp_path):
    plantilla = _plantilla()
    items = [(_Reg("Ana"), plantilla), (_Reg("Beto"), plantilla)]

    engine = PDFEngine(plantilla, perfil=_PERFIL, ranuras="2")
    pdf = engine.render_queue(items, "frente", tmp_path / "cola.pdf")

    assert _textos_por_pagina(pdf) == [["Ana"], ["Beto"]]


def test_la_ranura_puede_venir_dentro_del_perfil(tmp_path):
    """Compatibilidad: una cola guardada con la ranura en el perfil."""
    engine = PDFEngine(_plantilla(), perfil={**_PERFIL, "ranuras": "1"})
    pdf = engine.render([_Reg("Ana"), _Reg("Beto")], "frente", tmp_path / "p.pdf")

    assert _textos_por_pagina(pdf) == [["Ana"], ["Beto"]]


# ── Diseños desde carpeta ────────────────────────────────────────────


def _imagen(path: Path) -> Path:
    doc = fitz.open()
    pagina = doc.new_page(width=100, height=60)
    pagina.draw_rect(pagina.rect, fill=(1, 1, 1))
    pagina.get_pixmap().save(path)
    doc.close()
    return path


def test_desde_carpeta_una_sola_ranura_es_una_imagen_por_hoja(tmp_path):
    imgs = [_imagen(tmp_path / f"{i}.png") for i in range(3)]
    sides = FolderSides(
        fronts=imgs, backs=list(reversed(imgs)), n_front=3, n_back=3, mode="paired",
    )

    frentes, vueltas = compose_from_folder(
        sides, tmp_path / "out", perfil=_PERFIL, ranuras="2",
    )

    with fitz.open(frentes) as doc:
        assert doc.page_count == 3
    # Frentes y vueltas mantienen el mismo número de hojas para que coincidan
    # al voltear.
    with fitz.open(vueltas) as doc:
        assert doc.page_count == 3


def test_desde_carpeta_ambas_ranuras_no_cambia(tmp_path):
    imgs = [_imagen(tmp_path / f"{i}.png") for i in range(3)]
    sides = FolderSides(
        fronts=imgs, backs=None, n_front=3, n_back=0, mode="only_front",
    )

    frentes, vueltas = compose_from_folder(sides, tmp_path / "out", perfil=_PERFIL)

    assert vueltas is None
    with fitz.open(frentes) as doc:
        assert doc.page_count == 2  # 2 + 1
