"""PBT de la persistencia por lado (``LadoConfigRepository``).

Cubren las Properties 4 y 5 del diseño (modelo por lado): upsert único por
``(plantilla, lado)`` con round-trip jerárquico, y que guardar no crea Plantilla.
SQLite en memoria con los modelos reales. ``max_examples=100``.
"""
from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from credencializacion.db.models import (
    Base, Cliente, ConfiguracionLado, Plantilla, VarianteImagen,
)
from credencializacion.db.repositories import LadoConfigRepository
from credencializacion.services.image_selection import CondicionDTO, VarianteDTO

_ATTR_POOL = ["grado", "grupo", "nivel"]
_VAL_POOL = ["1", "2", "a", "b"]


def _factory():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(eng, "connect")
    def _fk(dbapi, _rec):  # pragma: no cover
        cur = dbapi.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, autoflush=False, future=True)


def _client_plantilla(session):
    c = Cliente(nombre="E", config={})
    session.add(c)
    session.flush()
    p = Plantilla(cliente_id=c.id, nombre="alumno")
    session.add(p)
    session.flush()
    return c.id, p.id


@st.composite
def _variantes(draw, n_max=6):
    n = draw(st.integers(min_value=0, max_value=n_max))
    out = []
    for i in range(n):
        nconds = draw(st.integers(min_value=1, max_value=2))
        conds = tuple(
            CondicionDTO(
                draw(st.sampled_from(_ATTR_POOL)),
                draw(st.sampled_from(_VAL_POOL)),
                j,
            )
            for j in range(nconds)
        )
        out.append(VarianteDTO(f"/img/{i}.png", i, conds))
    return out


# Feature: multiplantillaje-base, Property 4: Upsert único por (plantilla, lado)
# y round-trip jerárquico. Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.7
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_property_4_upsert_roundtrip(data):
    factory = _factory()
    with factory() as s:
        _cid, pid = _client_plantilla(s)
        s.commit()

    v1 = data.draw(_variantes())
    v2 = data.draw(_variantes())
    lado = data.draw(st.sampled_from(["frente", "vuelta"]))

    with factory() as s:
        LadoConfigRepository.save_config_lado(s, pid, lado, v1, "/def1.png")
        s.commit()
    with factory() as s:
        dto = LadoConfigRepository.get_config_lado(s, pid, lado)
    assert dto is not None
    assert dto.imagen_default_path == "/def1.png"
    assert [v.imagen_path for v in dto.variantes] == [v.imagen_path for v in v1]
    for got, exp in zip(dto.variantes, v1):
        assert [(c.atributo, c.valor) for c in got.condiciones] == \
               [(c.atributo, c.valor) for c in exp.condiciones]

    # Upsert: segunda vez no crea otra fila y reemplaza por completo.
    with factory() as s:
        LadoConfigRepository.save_config_lado(s, pid, lado, v2, "/def2.png")
        s.commit()
    with factory() as s:
        filas = s.query(ConfiguracionLado).filter_by(
            plantilla_id=pid, lado=lado
        ).count()
        total_variantes = s.query(VarianteImagen).count()
        dto2 = LadoConfigRepository.get_config_lado(s, pid, lado)
    assert filas == 1
    assert dto2.imagen_default_path == "/def2.png"
    assert total_variantes == len(v2)


# Feature: multiplantillaje-base, Property 5: Guardar no crea Plantilla.
# Validates: Requirements 4.5
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_property_5_no_crea_plantilla(data):
    factory = _factory()
    with factory() as s:
        _cid, pid = _client_plantilla(s)
        s.commit()
    with factory() as s:
        antes = s.query(Plantilla).count()
    v = data.draw(_variantes())
    with factory() as s:
        LadoConfigRepository.save_config_lado(s, pid, "frente", v, "/d.png")
        s.commit()
    with factory() as s:
        despues = s.query(Plantilla).count()
    assert despues == antes
