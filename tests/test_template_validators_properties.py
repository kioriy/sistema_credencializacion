"""Pruebas basadas en propiedades (PBT) de los validadores de multiplantillaje.

Cubren las Properties 9, 10, 15 y 16 del diseño de la feature
``multiplantillaje-base`` sobre las funciones puras definidas en
``credencializacion.services.template_validators``.

Todas las pruebas son puras (sin base de datos ni Qt): operan sobre cadenas,
dicts y DTOs generados con Hypothesis. Cada propiedad se ejecuta con
``max_examples=100``.

Validates: Requirements 3.1, 3.4, 3.6, 6.4, 7.5, 8.5, 8.7
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from credencializacion.services.template_assignment import normalize
from credencializacion.services.template_validators import (
    ATRIBUTO_MAX_LEN,
    ATRIBUTO_MIN_LEN,
    VALOR_MAX_LEN,
    VALOR_MIN_LEN,
    detect_template_differences,
    validate_atributo_length,
    validate_destino_same_client,
    validate_valor_length,
)

# --- Estrategias compartidas -------------------------------------------------

# Cadenas que, tras recortar espacios, quedan vacías (cadena vacía o solo
# espacios en blanco): representan campos obligatorios vacíos.
_WHITESPACE_ONLY = st.text(alphabet=" \t\n\r\f\v", max_size=8)

# --- Property 9 --------------------------------------------------------------

# Feature: multiplantillaje-base, Property 9: Rechazo de reglas con campos
# obligatorios vacíos. Para todo atributo o valor vacío (cadena vacía o solo
# espacios), la validación lo rechaza (ok=False), por lo que el guardado no
# procede y la configuración previa se conserva.
# Validates: Requirements 3.6, 6.4.
@settings(max_examples=100)
@given(empty=_WHITESPACE_ONLY)
def test_property_9_empty_required_fields_rejected(empty):
    atributo_result = validate_atributo_length(empty)
    valor_result = validate_valor_length(empty)

    assert atributo_result.ok is False
    assert atributo_result.errors  # mensaje que identifica el campo faltante
    assert valor_result.ok is False
    assert valor_result.errors

    # None se trata también como campo vacío y se rechaza.
    assert validate_atributo_length(None).ok is False
    assert validate_valor_length(None).ok is False


# --- Property 10 -------------------------------------------------------------

# Feature: multiplantillaje-base, Property 10: Validación de longitud de
# atributo (aceptado iff longitud recortada en 1..100) y de valor (aceptado iff
# longitud recortada en 1..255). Las entradas fuera de rango se rechazan.
# Validates: Requirements 3.1, 3.4, 7.5.
@settings(max_examples=100)
@given(length=st.integers(min_value=0, max_value=120))
def test_property_10_atributo_length_boundaries(length):
    # Construcción determinista por longitud usando un núcleo fijo, rodeado de
    # espacios para verificar que la validación recorta antes de medir.
    core = "a" * length
    atributo = "  " + core + "  " if length else "   "

    result = validate_atributo_length(atributo)
    expected_ok = ATRIBUTO_MIN_LEN <= length <= ATRIBUTO_MAX_LEN
    assert result.ok is expected_ok
    if not expected_ok:
        assert result.errors


@settings(max_examples=100)
@given(length=st.integers(min_value=0, max_value=300))
def test_property_10_valor_length_boundaries(length):
    core = "v" * length
    valor = "  " + core + "  " if length else "   "

    result = validate_valor_length(valor)
    expected_ok = VALOR_MIN_LEN <= length <= VALOR_MAX_LEN
    assert result.ok is expected_ok
    if not expected_ok:
        assert result.errors


# --- Property 15 -------------------------------------------------------------

# Feature: multiplantillaje-base, Property 15: Solo plantillas del mismo cliente
# como destino. La selección se acepta iff la plantilla pertenece al cliente en
# edición; las plantillas de otros clientes se rechazan.
# Validates: Requirements 8.5.
@settings(max_examples=100)
@given(
    cliente_id=st.integers(min_value=1, max_value=1000),
    plantilla_cliente_id=st.integers(min_value=1, max_value=1000),
)
def test_property_15_destino_same_client(cliente_id, plantilla_cliente_id):
    plantilla = {"id": 7, "cliente_id": plantilla_cliente_id}
    result = validate_destino_same_client(plantilla, cliente_id)

    expected_ok = plantilla_cliente_id == cliente_id
    assert result.ok is expected_ok
    if not expected_ok:
        assert result.errors  # mensaje "solo plantillas del mismo cliente"

    # Una plantilla inexistente (None) siempre se rechaza.
    assert validate_destino_same_client(None, cliente_id).ok is False


# --- Property 16 -------------------------------------------------------------

# Orientaciones que pueden diferir solo en caso/espacios (normalize las iguala).
_ORIENT_POOL = ["horizontal", "vertical", "Horizontal", " vertical ", "HORIZONTAL"]
_DIM_POOL = [85, 86, 540, 1080]


@st.composite
def _plantilla(draw):
    return {
        "orientacion": draw(st.sampled_from(_ORIENT_POOL)),
        "ancho": draw(st.sampled_from(_DIM_POOL)),
        "alto": draw(st.sampled_from(_DIM_POOL)),
    }


def _oracle_has_difference(plantillas) -> bool:
    """Oráculo independiente: hay diferencia si algún PAR de plantillas difiere
    en orientación (normalizada) o en alguna dimensión (ancho/alto)."""
    n = len(plantillas)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = plantillas[i], plantillas[j]
            if normalize(a["orientacion"]) != normalize(b["orientacion"]):
                return True
            if a["ancho"] != b["ancho"]:
                return True
            if a["alto"] != b["alto"]:
                return True
    return False


# Feature: multiplantillaje-base, Property 16: Detección de diferencia de
# orientación o dimensiones. detect_template_differences dispara la advertencia
# (has_difference=True) iff existe al menos un par de plantillas mapeadas que
# difiere en orientación o en alguna dimensión de lienzo (ancho o alto).
# Validates: Requirements 8.7.
@settings(max_examples=100)
@given(plantillas=st.lists(_plantilla(), min_size=0, max_size=6))
def test_property_16_detect_template_differences(plantillas):
    result = detect_template_differences(plantillas)
    expected = _oracle_has_difference(plantillas)
    assert result.has_difference is expected
    if expected:
        assert result.message is not None
