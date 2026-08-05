"""Pruebas de las reglas de transformación de texto del diseñador.

Los casos usan nombres con la forma real del padrón: el origen entrega
``nombre`` (nombres de pila) y ``apellido`` (los dos apellidos juntos) por
separado, y ``nombre_completo`` con todo.
"""
from __future__ import annotations

import pytest

from credencializacion.services.text_rules import TEXT_RULES, apply_text_rule


def test_las_reglas_tienen_id_unico_y_etiqueta():
    ids = [r["id"] for r in TEXT_RULES]

    assert len(ids) == len(set(ids))
    assert all(r.get("label") for r in TEXT_RULES)


# ── Nombres de pila ──────────────────────────────────────────────────────

@pytest.mark.parametrize("valor, esperado", [
    ("Carlos Daniel", "Daniel"),
    ("Carlos Daniel Alberto", "Daniel"),
    ("Carlos", ""),                       # no tiene segundo nombre
    ("", ""),
    # Sobre el nombre completo funciona si hay dos nombres de pila.
    ("Carlos Daniel Aceves Barrón", "Daniel"),
    # Partícula: "de la Luz" es un solo nombre.
    ("María de la Luz", "de la Luz"),
])
def test_segundo_nombre(valor, esperado):
    assert apply_text_rule(valor, "segundo_nombre") == esperado


@pytest.mark.parametrize("valor, esperado", [
    ("Ana María José", "José"),
    ("Carlos Daniel", ""),
    ("Carlos", ""),
])
def test_tercer_nombre(valor, esperado):
    assert apply_text_rule(valor, "tercer_nombre") == esperado


# ── Apellidos ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("valor, paterno, materno", [
    # Sobre el atributo `apellido`, que es el uso natural.
    ("Aceves Barrón", "Aceves", "Barrón"),
    ("Lopez Espinoza", "Lopez", "Espinoza"),
    # Sobre el nombre completo también, porque cuenta desde el final.
    ("Carlos Daniel Aceves Barrón", "Aceves", "Barrón"),
    ("Santiago Lopez Espinoza", "Lopez", "Espinoza"),
    # Partículas: casos reales del padrón (142 registros).
    ("De La Torre Marquez", "De La Torre", "Marquez"),
    ("Delgadillo de la Cruz", "Delgadillo", "de la Cruz"),
    ("Reyes de León", "Reyes", "de León"),
    ("De Anda López", "De Anda", "López"),
    # Un solo apellido registrado: no hay materno que devolver.
    ("Gómez", "Gómez", ""),
    ("", "", ""),
])
def test_apellidos(valor, paterno, materno):
    assert apply_text_rule(valor, "apellido_paterno") == paterno
    assert apply_text_rule(valor, "apellido_materno") == materno


def test_apellido_de_nombre_completo_con_particula():
    """El caso que rompería una heurística de 'penúltima palabra'."""
    completo = "Madisson Lucia De La Torre Marquez"

    assert apply_text_rule(completo, "apellido_paterno") == "De La Torre"
    assert apply_text_rule(completo, "apellido_materno") == "Marquez"


# ── Que no se rompió lo que ya existía ───────────────────────────────────

@pytest.mark.parametrize("regla, valor, esperado", [
    ("", "Carlos Daniel", "Carlos Daniel"),
    ("primer_nombre", "Carlos Daniel Aceves", "Carlos"),
    ("nombre_apellido", "Hugo Rafael Hernandez Llamas", "Hugo Hernandez"),
    ("abreviar_iniciales", "Hernandez Carranza", "H. C."),
    ("mayusculas", "Carlos daniel", "CARLOS DANIEL"),
    ("capitalizar", "carlos DANIEL", "Carlos Daniel"),
    ("regla_inexistente", "Carlos", "Carlos"),
])
def test_reglas_previas(regla, valor, esperado):
    assert apply_text_rule(valor, regla) == esperado


def test_ninguna_regla_lanza_excepcion():
    """El render no debe caerse por un valor raro."""
    for r in TEXT_RULES:
        for valor in ("", "   ", "X", "a b c d e f", "De", "de la"):
            apply_text_rule(valor, r["id"])
