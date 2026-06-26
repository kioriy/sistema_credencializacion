"""Pruebas ligeras de independencia de ranura en ``renderer/pdf_engine.py``.

Estas pruebas confirman (Tarea 3.2) que el render de texto NO depende del
índice de slot/ranura: ambas ranuras reutilizan la misma cadena
``render → _render_card → _render_element → _draw_text`` y el posicionamiento
por ranura ocurre únicamente en ``_render_card`` vía ``canvas.translate``.

Se usan objetos Plantilla/Registro MÍNIMOS (stubs) para no depender de BD ni de
red. La verificación se centra en:
  - que se genera un PDF con 2 registros sin excepción (2 tarjetas),
  - que ``_render_card`` se invoca una vez por ranura,
  - que ``_draw_text`` recibe coordenadas YA trasladadas (idénticas en ambas
    ranuras), demostrando que no depende del slot.

Validates: Requirements 2.5, 3.1, 3.4
"""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from credencializacion.renderer.pdf_engine import PDFEngine


class _StubRegistro:
    """Registro mínimo con la interfaz que usa PDFEngine."""

    def __init__(self, datos: dict, photo_path: str | None = None) -> None:
        self._datos = datos
        self.photo_path = photo_path

    def get_dato(self, key: str, default=""):
        return self._datos.get(key, default)


def _make_plantilla() -> SimpleNamespace:
    """Plantilla horizontal mínima con un único elemento de texto."""
    elementos_frente = [
        {
            "type": "text",
            "x": 10.0,
            "y": 8.0,
            "width": 50.0,
            "height": 10.0,
            "z_order": 1,
            "campo_dato": "nombre",
            "properties": {
                "font_family": "Helvetica",
                "font_size": 12,
                "alignment": "center",
                "color": "#000000",
            },
        }
    ]
    return SimpleNamespace(
        orientacion="horizontal",
        ancho=8.5,
        alto=5.4,
        elementos_frente=elementos_frente,
        elementos_vuelta=[],
        recursos={},
        posiciones_hoja={},  # Ignorado por calculate_card_positions_from_config
    )


def test_render_dos_registros_genera_pdf(tmp_path: Path):
    """Renderizar 2 registros crea un PDF no vacío sin excepción."""
    plantilla = _make_plantilla()
    engine = PDFEngine(plantilla)
    registros = [
        _StubRegistro({"nombre": "Ana"}),
        _StubRegistro({"nombre": "María Guadalupe de la Concepción"}),
    ]

    out = tmp_path / "salida.pdf"
    result = engine.render(registros, "frente", out)

    assert result.exists()
    assert result.stat().st_size > 0


def test_render_invoca_render_card_por_ranura(tmp_path: Path):
    """``_render_card`` se ejecuta una vez por ranura (2 tarjetas)."""
    plantilla = _make_plantilla()
    engine = PDFEngine(plantilla)

    base_positions = []
    original = engine._render_card

    def _spy(canvas, registro, elementos, base_pos):
        base_positions.append(base_pos)
        return original(canvas, registro, elementos, base_pos)

    engine._render_card = _spy  # type: ignore[assignment]

    registros = [
        _StubRegistro({"nombre": "Ana"}),
        _StubRegistro({"nombre": "Luis"}),
    ]
    engine.render(registros, "frente", tmp_path / "dos.pdf")

    # Dos tarjetas renderizadas, una por ranura, con posiciones base distintas.
    assert len(base_positions) == 2
    assert base_positions[0] != base_positions[1]


def test_draw_text_recibe_coordenadas_identicas_en_ambas_ranuras(tmp_path: Path):
    """``_draw_text`` recibe las MISMAS coordenadas relativas en ambas ranuras.

    El desplazamiento por ranura lo aplica ``_render_card`` con
    ``canvas.translate``; por eso ``_draw_text`` (aguas abajo) recibe siempre
    las coordenadas del elemento relativas al origen de la tarjeta,
    independientemente del slot.
    """
    plantilla = _make_plantilla()
    engine = PDFEngine(plantilla)

    captured: list[tuple] = []
    original = engine._draw_text

    def _spy(canvas, registro, x, y, w, h, elem, props):
        captured.append((x, y, w, h))
        return original(canvas, registro, x, y, w, h, elem, props)

    engine._draw_text = _spy  # type: ignore[assignment]

    registros = [
        _StubRegistro({"nombre": "Ana"}),
        _StubRegistro({"nombre": "Luis"}),
    ]
    engine.render(registros, "frente", tmp_path / "coords.pdf")

    # Un texto por tarjeta -> dos llamadas, con coordenadas idénticas.
    assert len(captured) == 2
    assert captured[0] == captured[1]


def test_draw_text_no_tiene_parametro_de_slot():
    """La firma de ``_draw_text`` no contiene ningún parámetro de slot/ranura."""
    params = set(inspect.signature(PDFEngine._draw_text).parameters)
    assert not (params & {"slot", "slot_idx", "ranura", "base_pos"})
