"""Pruebas basadas en propiedades (PBT) del Motor de Selección de Imagen.

Cubren las Properties 1-3 del diseño de la feature ``multiplantillaje-base``
(modelo por lado) sobre la función pura ``select_imagen`` y ``normalize`` de
``credencializacion.services.image_selection``.

Cada propiedad se ejecuta con ``max_examples=100``.
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from credencializacion.services.image_selection import (
    CondicionDTO,
    ConfigLadoDTO,
    VarianteDTO,
    normalize,
    select_imagen,
)

_ATTR_POOL = ["grado", "grupo", "nivel", "seccion", "turno"]
_DISJOINT_KEYS = ["x", "y", "z", "campo_extra"]
_VAL_POOL = ["1", "2", "primaria", "secundaria", "a", "b", "X"]


def _cond(a: str, v: str, o: int = 0) -> CondicionDTO:
    return CondicionDTO(atributo=a, valor=v, orden=o)


@st.composite
def _variante(draw, idx: int):
    conds = draw(st.lists(
        st.builds(_cond, st.sampled_from(_ATTR_POOL), st.sampled_from(_VAL_POOL)),
        min_size=1, max_size=2,
    ))
    conds = tuple(CondicionDTO(c.atributo, c.valor, i) for i, c in enumerate(conds))
    return VarianteDTO(imagen_path=f"/img/{idx}.png", orden=idx, condiciones=conds)


def _variante_coincide_ref(v: VarianteDTO, datos: dict, keys: dict) -> bool:
    if not v.condiciones:
        return False
    for c in v.condiciones:
        ok = keys.get(normalize(c.atributo))
        if ok is None or normalize(datos[ok]) != normalize(c.valor):
            return False
    return True


# Feature: multiplantillaje-base, Property 1: Conjunción (AND), primera
# coincidencia, orden y determinismo.
# Validates: Requirements 5.1, 5.2, 5.3, 5.5, 5.8, 9.1
@settings(max_examples=100)
@given(
    n=st.integers(min_value=0, max_value=6),
    datos=st.dictionaries(
        keys=st.sampled_from(_ATTR_POOL + _DISJOINT_KEYS),
        values=st.sampled_from(_VAL_POOL), max_size=6,
    ),
    data=st.data(),
)
def test_property_1_and_first_match_deterministic(n, datos, data):
    variantes = tuple(data.draw(_variante(i)) for i in range(n))
    cfg = ConfigLadoDTO(1, "frente", "/default.png", variantes)

    r1 = select_imagen(datos, cfg)
    r2 = select_imagen(dict(datos), cfg)
    assert r1 == r2  # determinismo

    keys = {normalize(k): k for k in datos}
    esperado = None
    for v in sorted(variantes, key=lambda v: v.orden):
        if _variante_coincide_ref(v, datos, keys):
            esperado = v.imagen_path
            break
    if esperado is not None:
        assert r1 == esperado


# Feature: multiplantillaje-base, Property 2: Idempotencia e insensibilidad de
# la normalización. Validates: Requirements 5.2, 9.1
@settings(max_examples=100)
@given(
    base=st.text(alphabet="abcdefghijABCDEFGHIJ0123456789 ", max_size=12),
    pad=st.text(alphabet=" \t", max_size=3),
)
def test_property_2_normalize(base, pad):
    assert normalize(normalize(base)) == normalize(base)
    variante = pad + base.upper() + pad
    assert normalize(variante) == normalize(base.lower())
    # El motor las considera coincidentes.
    cfg = ConfigLadoDTO(1, "frente", "/d.png",
                        (VarianteDTO("/v.png", 0, (_cond("grado", variante),)),))
    assert select_imagen({"grado": base}, cfg) == "/v.png"


# Feature: multiplantillaje-base, Property 3: Fallback a la Imagen_Base_Por_Defecto.
# Validates: Requirements 5.4
@settings(max_examples=100)
@given(
    n=st.integers(min_value=0, max_value=6),
    datos=st.dictionaries(
        keys=st.sampled_from(_DISJOINT_KEYS), values=st.sampled_from(_VAL_POOL),
        max_size=4,
    ),
    default=st.sampled_from(["/default.png", None]),
    data=st.data(),
)
def test_property_3_fallback_default(n, datos, default, data):
    # Variantes con atributos de _ATTR_POOL; datos solo con claves disjuntas →
    # ninguna variante coincide.
    variantes = tuple(data.draw(_variante(i)) for i in range(n))
    cfg = ConfigLadoDTO(1, "frente", default, variantes)
    assert select_imagen(datos, cfg) == default
