"""Pruebas basadas en propiedades (PBT) del Motor de Asignación.

Cubren las Properties 1–6 del diseño de la feature ``multiplantillaje-base``
sobre la función pura ``resolve_template`` y el helper ``normalize`` definidos
en ``credencializacion.services.template_assignment``.

Todas las pruebas son puras (sin base de datos): operan sobre ``ConfigDTO``
generados con Hypothesis. Cada propiedad se ejecuta con ``max_examples=100``.

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.8, 8.1, 8.2, 8.3, 8.4, 8.6, 8.8
"""
from __future__ import annotations

import copy

from hypothesis import given, settings
from hypothesis import strategies as st

from credencializacion.services.template_assignment import (
    AssignmentResult,
    CondicionDTO,
    ConfigDTO,
    ReglaDTO,
    normalize,
    resolve_template,
)

# --- Estrategias compartidas -------------------------------------------------

# Atributos usados por las reglas. Conjunto pequeño para forzar colisiones y
# así ejercitar la precedencia (varias reglas sobre el mismo atributo).
_ATTR_POOL = ["grado", "grupo", "nivel", "seccion", "turno"]
# Atributos que SOLO aparecen en los datos del registro (disjuntos de _ATTR_POOL)
# para construir escenarios garantizados de "sin coincidencia".
_DISJOINT_KEYS = ["x", "y", "z", "campo_extra"]
_VAL_POOL = ["1", "2", "primaria", "secundaria", "a", "b", "X"]


def _cond(atributo: str, valor: str, orden: int = 0) -> CondicionDTO:
    return CondicionDTO(atributo=atributo, valor=valor, orden=orden)


@st.composite
def _condicion(draw):
    return _cond(draw(st.sampled_from(_ATTR_POOL)), draw(st.sampled_from(_VAL_POOL)))


@st.composite
def _regla(draw, dest_ids=st.integers(min_value=1, max_value=8)):
    # 1..2 condiciones en conjunción (AND) para ejercitar la semántica compuesta.
    conds = draw(st.lists(_condicion(), min_size=1, max_size=2))
    conds = tuple(
        CondicionDTO(c.atributo, c.valor, i) for i, c in enumerate(conds)
    )
    return ReglaDTO(
        plantilla_destino_id=draw(dest_ids),
        orden=draw(st.integers(min_value=0, max_value=40)),
        condiciones=conds,
    )


def _regla_coincide_ref(regla, datos, keys) -> bool:
    """Oráculo: la regla coincide si TODAS sus condiciones se cumplen (AND)."""
    if not regla.condiciones:
        return False
    for cond in regla.condiciones:
        original = keys.get(normalize(cond.atributo))
        if original is None:
            return False
        if normalize(datos[original]) != normalize(cond.valor):
            return False
    return True


def _reference_match(datos: dict, config: ConfigDTO):
    """Oráculo independiente: índice (en orden de precedencia) y destino de la
    PRIMERA regla cuyas condiciones se cumplen todas (AND) y cuyo destino sigue
    vigente. Devuelve ``None`` si ninguna aplica."""
    keys = {normalize(k): k for k in datos.keys()}
    ordered = sorted(config.reglas, key=lambda r: r.orden)
    for idx, regla in enumerate(ordered):
        if not _regla_coincide_ref(regla, datos, keys):
            continue
        if regla.plantilla_destino_id in config.plantillas_existentes:
            return idx, regla.plantilla_destino_id
    return None


# --- Property 1 --------------------------------------------------------------

# Feature: multiplantillaje-base, Property 1: Resolución determinista por
# precedencia (orden ascendente, ignora reglas con atributo ausente, gana la
# primera coincidencia normalizada; dos llamadas iguales producen el mismo
# resultado). Validates: Requirements 5.1, 5.2, 5.4, 8.1.
@settings(max_examples=100)
@given(
    reglas=st.lists(_regla(), min_size=0, max_size=8),
    datos=st.dictionaries(
        keys=st.sampled_from(_ATTR_POOL + _DISJOINT_KEYS),
        values=st.sampled_from(_VAL_POOL),
        max_size=6,
    ),
    default_id=st.integers(min_value=1, max_value=8),
    cola_id=st.integers(min_value=100, max_value=110),
)
def test_property_1_deterministic_precedence(reglas, datos, default_id, cola_id):
    dest_ids = {r.plantilla_destino_id for r in reglas}
    existentes = frozenset(dest_ids | {default_id})
    config = ConfigDTO(
        cliente_id=1,
        plantilla_default_id=default_id,
        reglas=tuple(reglas),
        plantillas_existentes=existentes,
    )

    r1 = resolve_template(datos, config, cola_id)
    r2 = resolve_template(dict(datos), config, cola_id)

    # Determinismo: misma entrada → mismo resultado.
    assert r1 == r2

    expected = _reference_match(datos, config)
    if expected is not None:
        idx, dest = expected
        assert r1.status == "matched"
        assert r1.plantilla_id == dest
        assert r1.rule_index == idx


# --- Property 2 --------------------------------------------------------------

def _whitespace():
    return st.text(alphabet=" \t\n\r", max_size=4)


@st.composite
def _case_ws_variant(draw, base: str):
    """Genera una variante de ``base`` que difiere SOLO en mayúsculas/minúsculas
    y en espacios circundantes (no toca el interior)."""
    flipped = "".join(
        (ch.upper() if draw(st.booleans()) else ch.lower()) if ch.isalpha() else ch
        for ch in base
    )
    return draw(_whitespace()) + flipped + draw(_whitespace())


# Alfabeto ASCII (letras, dígitos, espacio) para evitar mapeos de caso unicode
# que cambian de longitud (p. ej. 'ß' -> 'SS'), ajenos a esta propiedad.
_BASE_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "


@st.composite
def _matching_pair(draw):
    base = draw(st.text(alphabet=_BASE_ALPHABET, max_size=12))
    return base, draw(_case_ws_variant(base=base)), draw(_case_ws_variant(base=base))


# Feature: multiplantillaje-base, Property 2: Idempotencia e invariancia de
# normalize (normalize(normalize(x)) == normalize(x); valores que difieren solo
# en mayúsculas/espacios circundantes se consideran coincidentes).
# Validates: Requirements 5.2, 8.8.
@settings(max_examples=100)
@given(pair=_matching_pair(), dest=st.integers(min_value=1, max_value=8))
def test_property_2_normalize_idempotence_and_invariance(pair, dest):
    base, variant_a, variant_b = pair

    # Idempotencia de normalize.
    assert normalize(normalize(base)) == normalize(base)
    assert normalize(normalize(variant_a)) == normalize(variant_a)

    # Invariancia: variantes que solo difieren en caso/espacios normalizan igual.
    assert normalize(variant_a) == normalize(variant_b)

    # El Motor_Asignacion las considera coincidentes: regla.valor = variant_a,
    # dato del registro = variant_b → status "matched".
    config = ConfigDTO(
        cliente_id=1,
        plantilla_default_id=99,
        reglas=(ReglaDTO(plantilla_destino_id=dest, orden=0,
                         condiciones=(_cond("grado", variant_a),)),),
        plantillas_existentes=frozenset({dest, 99}),
    )
    result = resolve_template({"grado": variant_b}, config, None)
    assert result.status == "matched"
    assert result.plantilla_id == dest


# --- Property 3 --------------------------------------------------------------

# Feature: multiplantillaje-base, Property 3: Fallback a la Plantilla_Por_Defecto
# cuando ninguna regla coincide y existe un default válido y vigente.
# Validates: Requirements 5.3, 8.2.
@settings(max_examples=100)
@given(
    reglas=st.lists(_regla(), min_size=0, max_size=8),
    # Datos con claves DISJUNTAS de los atributos de las reglas → ninguna regla
    # tiene su atributo presente, por lo que ninguna coincide (Req 8.1) y no se
    # activa el caso de destino inexistente (eso es Property 6).
    datos=st.dictionaries(
        keys=st.sampled_from(_DISJOINT_KEYS),
        values=st.sampled_from(_VAL_POOL),
        max_size=4,
    ),
    default_id=st.integers(min_value=1, max_value=8),
    cola_id=st.integers(min_value=100, max_value=110),
)
def test_property_3_fallback_to_default(reglas, datos, default_id, cola_id):
    existentes = frozenset({r.plantilla_destino_id for r in reglas} | {default_id})
    config = ConfigDTO(
        cliente_id=1,
        plantilla_default_id=default_id,
        reglas=tuple(reglas),
        plantillas_existentes=existentes,
    )
    result = resolve_template(datos, config, cola_id)
    assert result.status == "default"
    assert result.plantilla_id == default_id
    assert result.rule_index is None
    assert result.message is None


# --- Property 4 --------------------------------------------------------------

# Feature: multiplantillaje-base, Property 4: Fallback a la plantilla de la cola
# cuando no hay coincidencia ni default pero sí plantilla_cola_id, con
# advertencia que identifica al registro. Validates: Requirements 8.3.
@settings(max_examples=100)
@given(
    reglas=st.lists(_regla(), min_size=0, max_size=8),
    otras_claves=st.dictionaries(
        keys=st.sampled_from(_DISJOINT_KEYS),
        values=st.sampled_from(_VAL_POOL),
        max_size=3,
    ),
    reg_id=st.integers(min_value=1, max_value=9999),
    cola_id=st.integers(min_value=100, max_value=110),
)
def test_property_4_fallback_to_queue_template(reglas, otras_claves, reg_id, cola_id):
    datos = dict(otras_claves)
    datos["id"] = reg_id  # identificador del registro para el mensaje
    config = ConfigDTO(
        cliente_id=1,
        plantilla_default_id=None,  # sin default
        reglas=tuple(reglas),
        plantillas_existentes=frozenset({r.plantilla_destino_id for r in reglas}),
    )
    result = resolve_template(datos, config, cola_id)
    assert result.status == "fallback_cola"
    assert result.plantilla_id == cola_id
    assert result.message is not None
    # La advertencia identifica al registro (por su id).
    assert "registro" in result.message
    assert str(reg_id) in result.message


# --- Property 5 --------------------------------------------------------------

# Feature: multiplantillaje-base, Property 5: Error (plantilla_id=None, estado
# de error, mensaje que identifica al registro) cuando no hay coincidencia, ni
# default, ni plantilla de cola; los datos del registro no se modifican.
# Validates: Requirements 5.8, 8.4.
@settings(max_examples=100)
@given(
    reglas=st.lists(_regla(), min_size=0, max_size=8),
    otras_claves=st.dictionaries(
        keys=st.sampled_from(_DISJOINT_KEYS),
        values=st.sampled_from(_VAL_POOL),
        max_size=3,
    ),
    reg_id=st.integers(min_value=1, max_value=9999),
)
def test_property_5_error_without_default_or_queue(reglas, otras_claves, reg_id):
    datos = dict(otras_claves)
    datos["id"] = reg_id
    datos_original = copy.deepcopy(datos)
    config = ConfigDTO(
        cliente_id=1,
        plantilla_default_id=None,
        reglas=tuple(reglas),
        plantillas_existentes=frozenset({r.plantilla_destino_id for r in reglas}),
    )
    result = resolve_template(datos, config, None)
    assert result.plantilla_id is None
    assert result.status == "error"
    assert result.message is not None
    assert "registro" in result.message
    assert str(reg_id) in result.message
    # Los datos del registro permanecen sin modificación.
    assert datos == datos_original


# --- Property 6 --------------------------------------------------------------

# Feature: multiplantillaje-base, Property 6: Una regla cuyo destino ya no
# existe entre las plantillas vigentes se trata como no aplicable y resuelve al
# default, con advertencia que identifica la regla afectada.
# Validates: Requirements 8.6.
@settings(max_examples=100)
@given(
    atributo=st.sampled_from(_ATTR_POOL),
    valor=st.sampled_from(_VAL_POOL),
    destino_inexistente=st.integers(min_value=50, max_value=60),
    default_id=st.integers(min_value=1, max_value=8),
    orden=st.integers(min_value=0, max_value=40),
)
def test_property_6_missing_destination_falls_to_default(
    atributo, valor, destino_inexistente, default_id, orden
):
    # default vigente; destino de la regla NO vigente.
    existentes = frozenset({default_id})
    assert destino_inexistente not in existentes
    regla = ReglaDTO(
        plantilla_destino_id=destino_inexistente,
        orden=orden,
        condiciones=(_cond(atributo, valor),),
    )
    config = ConfigDTO(
        cliente_id=1,
        plantilla_default_id=default_id,
        reglas=(regla,),
        plantillas_existentes=existentes,
    )
    # El registro coincide con la regla por atributo y valor.
    result = resolve_template({atributo: valor}, config, 100)
    assert result.status == "warning_missing"
    assert result.plantilla_id == default_id
    assert result.rule_index == 0
    assert result.message is not None
    # La advertencia identifica la regla afectada (atributo y valor).
    assert atributo in result.message
    assert valor in result.message


# --- Property 9 --------------------------------------------------------------

# Feature: multiplantillaje-base, Property 9: Configuración parcial — una regla
# sin condiciones nunca coincide para ningún registro; el motor cae al default.
# Validates: Requirements 9.3.
@settings(max_examples=100)
@given(
    datos=st.dictionaries(
        keys=st.sampled_from(_ATTR_POOL + _DISJOINT_KEYS),
        values=st.sampled_from(_VAL_POOL),
        max_size=6,
    ),
    dest=st.integers(min_value=1, max_value=8),
    default_id=st.integers(min_value=10, max_value=18),
    orden=st.integers(min_value=0, max_value=40),
)
def test_property_9_empty_rule_never_matches(datos, dest, default_id, orden):
    # Regla SIN condiciones (configuración parcial): nunca debe coincidir.
    regla_vacia = ReglaDTO(plantilla_destino_id=dest, orden=orden, condiciones=())
    config = ConfigDTO(
        cliente_id=1,
        plantilla_default_id=default_id,
        reglas=(regla_vacia,),
        plantillas_existentes=frozenset({dest, default_id}),
    )
    result = resolve_template(datos, config, None)
    # Nunca "matched" por la regla vacía: cae al default.
    assert result.status == "default"
    assert result.plantilla_id == default_id
