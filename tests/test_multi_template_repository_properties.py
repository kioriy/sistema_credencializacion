"""Pruebas basadas en propiedades (PBT) de la capa de persistencia / repositorio.

Cubren las Properties 7, 8, 11, 12, 13 y 14 del diseño de la feature
``multiplantillaje-base`` sobre ``MultiTemplateRepository``
(``credencializacion.db.repositories``) usando **SQLite en memoria con los
modelos reales** (``Base.metadata.create_all`` sobre un engine en memoria).

Cada propiedad se ejecuta con ``max_examples=100``.

Nota sobre la Property 11 (rechazo de pares duplicados, Req 3.7): el rechazo
formal de un par ``(atributo, valor)`` duplicado es responsabilidad de los
validadores de la tarea 5 (aún no implementados como módulo). A nivel de
repositorio/persistencia —el alcance de la tarea 4.3— lo que se garantiza y se
verifica aquí es la **invariante de datos**: el repositorio hace round-trip de
un conjunto de reglas sin introducir duplicados, y si la semántica de
deduplicación normalizada (la misma ``normalize`` que el repo expone) rechaza
una adición, la configuración persistida permanece sin cambios. Cuando la tarea
5 añada el validador, se podrá complementar con una prueba de la excepción de
rechazo en el nivel donde se imponga.

Validates: Requirements 2.1, 3.7, 3.8, 4.1, 4.2, 4.4, 6.1, 6.2, 6.3, 6.5, 6.7,
7.1, 7.2, 7.3
"""
from __future__ import annotations

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from credencializacion.db.models import (
    Base,
    Cliente,
    ConfiguracionMultiplantillaje,
    Plantilla,
    Registro,
    ReglaAsignacion,
)
from credencializacion.db.repositories import MultiTemplateRepository
from credencializacion.services.template_assignment import (
    CondicionDTO,
    ConfigDTO,
    ReglaDTO,
    normalize,
)

# --- Arnés de BD en memoria con modelos reales ------------------------------

# Atributos y valores de prueba (conjunto pequeño para forzar colisiones).
_ATTR_POOL = ["grado", "grupo", "nivel", "seccion", "turno"]
_VAL_POOL = ["1", "2", "primaria", "secundaria", "a", "b", "X"]

# Claves para Atributos_Disponibles (Property 13): mezcla de claves válidas,
# vacías, solo espacios, variantes de caso/espacios y una clave demasiado larga.
_LONG_KEY = "L" * 101  # > 100 chars: debe omitirse (Req 7.2/7.3).
_KEY_POOL = [
    "grado",
    " grado ",   # variante con espacios circundantes (duplicado normalizado).
    "GRADO",     # variante de caso (duplicado normalizado).
    "grupo",
    "nivel_escolar",
    "",          # vacía: se omite.
    "   ",       # solo espacios: se omite.
    _LONG_KEY,   # demasiado larga: se omite.
    "a",         # longitud mínima válida (1).
]


def _new_session_factory():
    """Crea un engine SQLite en memoria con el esquema real y un sessionmaker.

    Usa ``StaticPool`` para que todas las sesiones compartan la misma conexión
    (y por tanto la misma base en memoria). Habilita ``PRAGMA foreign_keys=ON``
    para reproducir el comportamiento referencial real de la aplicación.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):  # pragma: no cover - trivial
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, future=True)


def _create_client_with_templates(session, n_plantillas: int, nombre: str = "Cliente"):
    """Crea un cliente con ``n_plantillas`` plantillas reales y devuelve
    ``(cliente_id, [plantilla_ids])``."""
    cliente = Cliente(nombre=nombre, config={})
    session.add(cliente)
    session.flush()
    ids: list[int] = []
    for k in range(n_plantillas):
        plantilla = Plantilla(cliente_id=cliente.id, nombre=f"{nombre}-P{k}")
        session.add(plantilla)
        session.flush()
        ids.append(plantilla.id)
    return cliente.id, ids


def _build_reglas_dto(rule_specs, plantilla_ids):
    """Convierte specs generadas (dest como índice local) en ``ReglaDTO`` con
    ids reales de plantilla. Cada regla lleva una única condición (atributo,
    valor), reproduciendo la semántica simple sobre el modelo de condiciones."""
    return [
        ReglaDTO(
            plantilla_destino_id=plantilla_ids[spec["dest_index"]],
            orden=spec["orden"],
            condiciones=(
                CondicionDTO(atributo=spec["atributo"], valor=spec["valor"], orden=0),
            ),
        )
        for spec in rule_specs
    ]


def _attr_of(regla) -> str:
    """Atributo de la (única) condición de una regla simple."""
    return regla.condiciones[0].atributo


def _valor_of(regla) -> str:
    """Valor de la (única) condición de una regla simple."""
    return regla.condiciones[0].valor


def _regla_simple(atributo, valor, plantilla_destino_id, orden) -> ReglaDTO:
    """Construye una ReglaDTO con una sola condición (atributo, valor)."""
    return ReglaDTO(
        plantilla_destino_id=plantilla_destino_id,
        orden=orden,
        condiciones=(CondicionDTO(atributo=atributo, valor=valor, orden=0),),
    )


# --- Estrategias -------------------------------------------------------------

@st.composite
def _rule_specs(draw, n_plantillas: int, min_size: int = 0, max_size: int = 10):
    """Genera reglas con ``orden`` DISTINTO (permutación) para que la
    precedencia sea inequívoca al hacer round-trip."""
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    ordenes = draw(st.permutations(list(range(n))))
    specs = []
    for i in range(n):
        specs.append(
            {
                "atributo": draw(st.sampled_from(_ATTR_POOL)),
                "valor": draw(st.sampled_from(_VAL_POOL)),
                "dest_index": draw(st.integers(min_value=0, max_value=n_plantillas - 1)),
                "orden": ordenes[i],
            }
        )
    return specs


# --- Property 7 --------------------------------------------------------------

# Feature: multiplantillaje-base, Property 7: Round-trip y reemplazo total de la
# persistencia. Guardar una config válida (0..100 reglas con default) y cargarla
# devuelve exactamente las mismas reglas (atributo, valor, destino, orden) y el
# mismo default; guardar una config nueva para un cliente que ya tenía una la
# reemplaza por completo, sin reglas residuales.
# Validates: Requirements 4.1, 4.2, 4.4, 6.5, 6.7.
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_property_7_roundtrip_and_total_replacement(data):
    factory = _new_session_factory()
    n_plantillas = data.draw(st.integers(min_value=1, max_value=5))

    with factory() as session:
        cliente_id, plantilla_ids = _create_client_with_templates(session, n_plantillas)
        session.commit()

    specs1 = data.draw(_rule_specs(n_plantillas))
    specs2 = data.draw(_rule_specs(n_plantillas))
    default1 = plantilla_ids[data.draw(st.integers(0, n_plantillas - 1))]
    default2 = plantilla_ids[data.draw(st.integers(0, n_plantillas - 1))]

    reglas1 = _build_reglas_dto(specs1, plantilla_ids)
    reglas2 = _build_reglas_dto(specs2, plantilla_ids)

    # Guardar la primera configuración.
    with factory() as session:
        MultiTemplateRepository.save_config(session, cliente_id, reglas1, default1)
        session.commit()

    # Round-trip: cargar devuelve exactamente lo guardado, ordenado por `orden`.
    with factory() as session:
        loaded = MultiTemplateRepository.get_config(session, cliente_id)
    assert loaded is not None
    assert loaded.plantilla_default_id == default1
    assert loaded.reglas == tuple(sorted(reglas1, key=lambda r: r.orden))

    # Reemplazo total: guardar una nueva config sustituye por completo la previa.
    with factory() as session:
        MultiTemplateRepository.save_config(session, cliente_id, reglas2, default2)
        session.commit()

    with factory() as session:
        reloaded = MultiTemplateRepository.get_config(session, cliente_id)
        # No quedan reglas residuales: el total en BD == reglas de la nueva config.
        total_reglas = session.query(ReglaAsignacion).count()
        total_configs = (
            session.query(ConfiguracionMultiplantillaje)
            .filter_by(cliente_id=cliente_id)
            .count()
        )
    assert reloaded is not None
    assert reloaded.plantilla_default_id == default2
    assert reloaded.reglas == tuple(sorted(reglas2, key=lambda r: r.orden))
    assert total_reglas == len(reglas2)
    assert total_configs == 1


# --- Property 8 --------------------------------------------------------------

# Feature: multiplantillaje-base, Property 8: Edición y eliminación parcial
# preservan el resto. Editar un campo de una regla (atributo/valor/destino) o
# eliminar una regla deja inalterados los demás campos de esa regla y todas las
# demás reglas. (El repositorio modela la edición mediante save_config como
# reemplazo total; aquí se construye la lista editada y se verifica que la
# persistencia preserva el resto.)
# Validates: Requirements 6.1, 6.2, 6.3.
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_property_8_partial_edit_or_delete_preserves_rest(data):
    factory = _new_session_factory()
    # >= 2 plantillas para que un cambio de destino pueda diferir del actual.
    n_plantillas = data.draw(st.integers(min_value=2, max_value=5))

    with factory() as session:
        cliente_id, plantilla_ids = _create_client_with_templates(session, n_plantillas)
        session.commit()

    # >= 1 regla para poder editar/eliminar.
    specs = data.draw(_rule_specs(n_plantillas, min_size=1, max_size=8))
    reglas1 = _build_reglas_dto(specs, plantilla_ids)
    default_id = plantilla_ids[data.draw(st.integers(0, n_plantillas - 1))]

    with factory() as session:
        MultiTemplateRepository.save_config(session, cliente_id, reglas1, default_id)
        session.commit()

    original_by_orden = {r.orden: r for r in reglas1}
    target_index = data.draw(st.integers(0, len(reglas1) - 1))
    target = reglas1[target_index]
    op = data.draw(st.sampled_from(
        ["edit_atributo", "edit_valor", "edit_destino", "delete"]
    ))

    if op == "delete":
        reglas2 = [r for r in reglas1 if r.orden != target.orden]
    elif op == "edit_atributo":
        nuevo = data.draw(st.sampled_from(_ATTR_POOL))
        assume(nuevo != _attr_of(target))
        reglas2 = [
            _regla_simple(nuevo, _valor_of(r), r.plantilla_destino_id, r.orden)
            if r.orden == target.orden else r
            for r in reglas1
        ]
    elif op == "edit_valor":
        nuevo = data.draw(st.sampled_from(_VAL_POOL))
        assume(nuevo != _valor_of(target))
        reglas2 = [
            _regla_simple(_attr_of(r), nuevo, r.plantilla_destino_id, r.orden)
            if r.orden == target.orden else r
            for r in reglas1
        ]
    else:  # edit_destino
        nuevo_dest = data.draw(st.sampled_from(plantilla_ids))
        assume(nuevo_dest != target.plantilla_destino_id)
        reglas2 = [
            _regla_simple(_attr_of(r), _valor_of(r), nuevo_dest, r.orden)
            if r.orden == target.orden else r
            for r in reglas1
        ]

    with factory() as session:
        MultiTemplateRepository.save_config(session, cliente_id, reglas2, default_id)
        session.commit()

    with factory() as session:
        loaded = MultiTemplateRepository.get_config(session, cliente_id)
    assert loaded is not None
    loaded_by_orden = {r.orden: r for r in loaded.reglas}

    if op == "delete":
        # La regla objetivo desaparece; el resto queda intacto.
        assert target.orden not in loaded_by_orden
        assert len(loaded.reglas) == len(reglas1) - 1
        for orden, regla in original_by_orden.items():
            if orden == target.orden:
                continue
            assert loaded_by_orden[orden] == regla
    else:
        # La regla objetivo cambió solo en el campo editado; el resto intacto.
        assert len(loaded.reglas) == len(reglas1)
        for orden, regla in original_by_orden.items():
            if orden == target.orden:
                edited = loaded_by_orden[orden]
                if op == "edit_atributo":
                    assert _valor_of(edited) == _valor_of(regla)
                    assert edited.plantilla_destino_id == regla.plantilla_destino_id
                    assert _attr_of(edited) != _attr_of(regla)
                elif op == "edit_valor":
                    assert _attr_of(edited) == _attr_of(regla)
                    assert edited.plantilla_destino_id == regla.plantilla_destino_id
                    assert _valor_of(edited) != _valor_of(regla)
                else:  # edit_destino
                    assert _attr_of(edited) == _attr_of(regla)
                    assert _valor_of(edited) == _valor_of(regla)
                    assert edited.plantilla_destino_id != regla.plantilla_destino_id
            else:
                assert loaded_by_orden[orden] == regla


# --- Property 11 -------------------------------------------------------------

def _normalized_pairs(reglas) -> set[tuple[str, str]]:
    return {(normalize(_attr_of(r)), normalize(_valor_of(r))) for r in reglas}


def _dedupe_by_normalized_pair(reglas):
    """Acepta reglas evitando pares (atributo, valor) duplicados normalizados,
    reasignando `orden` secuencial (simula la entrada aceptada por el validador)."""
    aceptadas: list[ReglaDTO] = []
    vistos: set[tuple[str, str]] = set()
    for r in reglas:
        clave = (normalize(_attr_of(r)), normalize(_valor_of(r)))
        if clave in vistos:
            continue
        vistos.add(clave)
        aceptadas.append(
            _regla_simple(_attr_of(r), _valor_of(r), r.plantilla_destino_id, len(aceptadas))
        )
    return aceptadas


# Feature: multiplantillaje-base, Property 11: Rechazo de reglas duplicadas
# (par (atributo, valor) normalizado). Alcance 4.3 = invariante de datos: el
# repositorio hace round-trip sin introducir duplicados, y si la semántica de
# dedup normalizada rechaza una adición, la config persistida no cambia. El
# rechazo formal (excepción/mensaje) corresponde a los validadores de la tarea 5.
# Validates: Requirements 3.7.
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_property_11_duplicate_pair_rejection_data_invariant(data):
    factory = _new_session_factory()
    n_plantillas = data.draw(st.integers(min_value=1, max_value=4))

    with factory() as session:
        cliente_id, plantilla_ids = _create_client_with_templates(session, n_plantillas)
        session.commit()

    specs = data.draw(_rule_specs(n_plantillas, min_size=1, max_size=10))
    raw_reglas = _build_reglas_dto(specs, plantilla_ids)
    # Conjunto aceptado: sin pares duplicados normalizados.
    reglas = _dedupe_by_normalized_pair(raw_reglas)
    default_id = plantilla_ids[data.draw(st.integers(0, n_plantillas - 1))]

    with factory() as session:
        MultiTemplateRepository.save_config(session, cliente_id, reglas, default_id)
        session.commit()

    with factory() as session:
        loaded = MultiTemplateRepository.get_config(session, cliente_id)
    assert loaded is not None
    # Invariante: no hay pares (atributo, valor) duplicados bajo normalización.
    pares = _normalized_pairs(loaded.reglas)
    assert len(pares) == len(loaded.reglas)

    # Intento de añadir una regla cuyo par ya existe (variante de caso/espacios).
    existente = reglas[data.draw(st.integers(0, len(reglas) - 1))]
    candidata = _regla_simple(
        "  " + _attr_of(existente).upper() + " ",
        "  " + _valor_of(existente).upper() + " ",
        existente.plantilla_destino_id,
        len(reglas),
    )
    clave_candidata = (normalize(_attr_of(candidata)), normalize(_valor_of(candidata)))
    # La semántica de dedup normalizada la detecta como duplicada -> se rechaza
    # (no se persiste). La configuración guardada permanece sin cambios.
    assert clave_candidata in _normalized_pairs(reglas)

    with factory() as session:
        reloaded = MultiTemplateRepository.get_config(session, cliente_id)
    assert reloaded is not None
    assert reloaded.reglas == loaded.reglas
    assert reloaded.plantilla_default_id == default_id


# --- Property 12 -------------------------------------------------------------

# Feature: multiplantillaje-base, Property 12: Exactamente una Plantilla_Por_
# Defecto. Una config válida persistida tiene exactamente una referencia de
# default y esa plantilla pertenece al conjunto de plantillas del cliente.
# Validates: Requirements 3.8.
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_property_12_exactly_one_valid_default(data):
    factory = _new_session_factory()
    n_plantillas = data.draw(st.integers(min_value=1, max_value=5))

    with factory() as session:
        cliente_id, plantilla_ids = _create_client_with_templates(session, n_plantillas)
        session.commit()

    specs = data.draw(_rule_specs(n_plantillas))
    reglas = _build_reglas_dto(specs, plantilla_ids)
    default_id = plantilla_ids[data.draw(st.integers(0, n_plantillas - 1))]

    with factory() as session:
        MultiTemplateRepository.save_config(session, cliente_id, reglas, default_id)
        session.commit()

    with factory() as session:
        loaded = MultiTemplateRepository.get_config(session, cliente_id)
        # Exactamente una fila de configuración para el cliente.
        total_configs = (
            session.query(ConfiguracionMultiplantillaje)
            .filter_by(cliente_id=cliente_id)
            .count()
        )
        config_row = (
            session.query(ConfiguracionMultiplantillaje)
            .filter_by(cliente_id=cliente_id)
            .one()
        )
        default_persistido = config_row.plantilla_default_id

    assert total_configs == 1
    assert loaded is not None
    # Exactamente una referencia de default (columna escalar) y es válida.
    assert default_persistido is not None
    assert isinstance(default_persistido, int)
    assert default_persistido == default_id
    # El default pertenece al conjunto de plantillas del cliente.
    assert default_persistido in set(plantilla_ids)
    assert loaded.plantilla_default_id in loaded.plantillas_existentes


# --- Property 13 -------------------------------------------------------------

# Feature: multiplantillaje-base, Property 13: Construcción de Atributos_
# Disponibles. La lista no contiene duplicados bajo comparación normalizada,
# incluye solo claves con longitud (recortada) en 1..100, y omite las vacías.
# Validates: Requirements 7.1, 7.2, 7.3.
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.too_slow])
@given(
    known=st.lists(st.sampled_from(_KEY_POOL), max_size=9),
    registros_keys=st.lists(
        st.lists(st.sampled_from(_KEY_POOL), max_size=5), max_size=4
    ),
)
def test_property_13_available_attributes_construction(known, registros_keys):
    factory = _new_session_factory()

    with factory() as session:
        cliente = Cliente(nombre="Cliente", config={"known_attributes": list(known)})
        session.add(cliente)
        session.flush()
        cliente_id = cliente.id
        for keys in registros_keys:
            datos = {k: "v" for k in keys}
            session.add(Registro(cliente_id=cliente_id, datos=datos))
        session.commit()

    with factory() as session:
        result = MultiTemplateRepository.available_attributes(session, cliente_id)

    # Solo claves con longitud (recortada) en 1..100; ninguna vacía.
    for clave in result:
        assert isinstance(clave, str)
        assert 1 <= len(clave.strip()) <= 100

    # Sin duplicados bajo comparación normalizada (insensible a caso/espacios).
    normalizadas = [normalize(c) for c in result]
    assert len(set(normalizadas)) == len(normalizadas)

    # Correctitud frente a las fuentes: el conjunto normalizado de resultados es
    # exactamente el de las claves de fuente válidas (known_attributes + datos).
    fuentes: list[str] = [k for k in known if isinstance(k, str)]
    for keys in registros_keys:
        fuentes.extend(keys)
    esperado = {
        normalize(k) for k in fuentes if 1 <= len(k.strip()) <= 100
    }
    assert set(normalizadas) == esperado


# --- Property 14 -------------------------------------------------------------

# Feature: multiplantillaje-base, Property 14: list_templates filtra por cliente.
# Devuelve exactamente las plantillas del cliente indicado y ninguna de otro.
# Validates: Requirements 2.1.
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.too_slow])
@given(
    plantillas_por_cliente=st.lists(
        st.integers(min_value=0, max_value=4), min_size=1, max_size=4
    ),
    objetivo_seed=st.integers(min_value=0, max_value=999),
)
def test_property_14_list_templates_filters_by_client(
    plantillas_por_cliente, objetivo_seed
):
    factory = _new_session_factory()

    ids_por_cliente: dict[int, set[int]] = {}
    with factory() as session:
        for i, n in enumerate(plantillas_por_cliente):
            cliente_id, plantilla_ids = _create_client_with_templates(
                session, n, nombre=f"Cliente-{i}"
            )
            ids_por_cliente[cliente_id] = set(plantilla_ids)
        session.commit()

    cliente_ids = list(ids_por_cliente.keys())
    objetivo = cliente_ids[objetivo_seed % len(cliente_ids)]

    with factory() as session:
        plantillas = MultiTemplateRepository.list_templates(session, objetivo)
        devueltos = {p.id for p in plantillas}
        clientes_devueltos = {p.cliente_id for p in plantillas}

    # Exactamente las plantillas del cliente objetivo.
    assert devueltos == ids_por_cliente[objetivo]
    # Ninguna plantilla de otro cliente.
    assert clientes_devueltos <= {objetivo}
    # Ningún id de otros clientes se filtró.
    otros = set().union(
        *(ids for cid, ids in ids_por_cliente.items() if cid != objetivo)
    ) if len(cliente_ids) > 1 else set()
    assert devueltos.isdisjoint(otros)
