"""Prueba basada en propiedades (PBT) del armado de la cola de impresión.

Cubre la **Property 17** del diseño de la feature ``multiplantillaje-base``
sobre la integración del Motor_Asignacion en el flujo de armado de cola
(``ControlPanel._save_queue_and_emit`` + el helper ``_resolve_plantilla_id``,
en ``credencializacion.ui.pages.control_panel``).

Enfoque elegido (faithful a producción):
- Se redirige el engine de la app a una BD **SQLite en memoria** con los modelos
  reales (``StaticPool`` + ``PRAGMA foreign_keys=ON``), igual que
  ``tests/test_multi_template_dialog.py``. NO se toca ``data/credencializacion.db``.
- Qt se ejecuta headless (``QT_QPA_PLATFORM=offscreen``). Se instancia un
  ``ControlPanel`` real y se ejercita su método de producción
  ``_save_queue_and_emit``, sustituyendo únicamente las dos fuentes de entrada
  de UI que el método lee: ``self._queue_panel.get_queue()`` (cola de registros)
  y ``self._combo_templates.currentData()/currentText()`` (plantilla de la cola).
  El resto del camino (carga de config vía ``MultiTemplateRepository``,
  resolución por registro con ``resolve_template`` y creación de ``ItemCola`` en
  una ``DatabaseSession``) es exactamente el código de producción.

Property 17: Para todo conjunto de registros — cuando existe configuración, cada
``ItemCola`` creado recibe el ``plantilla_id`` que ``resolve_template`` resuelve
para su registro (y los registros que resuelven a error/``None`` no producen
``ItemCola``); cuando no existe configuración, todos los ``ItemCola`` reciben la
plantilla seleccionada en la cola (comportamiento actual preservado).

Validates: Requirements 5.5, 5.7
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import credencializacion.db.engine as engine_module
from credencializacion.db.models import Base, Cliente, ItemCola, Plantilla, Registro
from credencializacion.db.repositories import MultiTemplateRepository
from credencializacion.services.template_assignment import (
    CondicionDTO,
    ReglaDTO,
    resolve_template,
)

from PySide6.QtWidgets import QApplication

# Una única instancia de QApplication + un único ControlPanel reutilizado entre
# ejemplos para evitar crear cientos de árboles de widgets.
_app = QApplication.instance() or QApplication([])
_PANEL = None

# Conjuntos pequeños para forzar coincidencias y no-coincidencias.
_ATTR_POOL = ["grado", "grupo"]
_VAL_POOL = ["1", "2", "3", "a", "b", "X"]


def _get_panel():
    """Crea (una vez) y devuelve el ControlPanel real headless."""
    global _PANEL
    if _PANEL is None:
        from credencializacion.ui.pages.control_panel import ControlPanel

        _PANEL = ControlPanel()
    return _PANEL


def _install_memory_db():
    """Redirige el engine de la app a una BD SQLite en memoria con StaticPool."""
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
    engine_module._engine = engine
    engine_module._SessionLocal = sessionmaker(
        bind=engine, autocommit=False, autoflush=False
    )
    return engine


def _seed(cliente_id_holder, n_plantillas, records_datos):
    """Crea cliente + plantillas + registros reales en la BD en memoria.

    Devuelve ``(cliente_id, [plantilla_ids], [registros_detached])``. Los
    registros se desvinculan (``expunge_all``) tras precargar los atributos que
    el código de producción lee (id, cliente_id, datos, photo_path), de modo que
    ``get_queue()`` pueda devolverlos como objetos detached válidos.
    """
    from credencializacion.db.engine import DatabaseSession

    with DatabaseSession() as session:
        cliente = Cliente(nombre="Escuela PBT", config={})
        session.add(cliente)
        session.flush()
        cliente_id = cliente.id

        plantilla_ids = []
        for k in range(n_plantillas):
            p = Plantilla(cliente_id=cliente_id, nombre=f"Diseño {k}")
            session.add(p)
            session.flush()
            plantilla_ids.append(p.id)

        registros = []
        for datos in records_datos:
            reg = Registro(cliente_id=cliente_id, datos=dict(datos))
            session.add(reg)
            session.flush()
            # Precarga de atributos antes de desvincular.
            _ = (reg.id, reg.cliente_id, reg.datos, reg.photo_path)
            registros.append(reg)

        session.commit()
        # Desvincular para usarlos fuera de la sesión (como hace la cola visual).
        for reg in registros:
            _ = (reg.id, reg.cliente_id, reg.datos, reg.photo_path)
        session.expunge_all()

    return cliente_id, plantilla_ids, registros


# Feature: multiplantillaje-base, Property 17: El armado de cola asigna la
# plantilla resuelta por ítem. Con configuración, cada ItemCola recibe el
# plantilla_id que resolve_template resuelve para su registro (los registros que
# resuelven a error/None no generan ItemCola); sin configuración, todos los
# ItemCola reciben la plantilla seleccionada en la cola (Req 5.7 preservado).
# Validates: Requirements 5.5, 5.7.
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
@given(data=st.data())
def test_property_17_queue_assembly_assigns_resolved_template(data):
    with_config = data.draw(st.booleans(), label="with_config")
    n_plantillas = data.draw(st.integers(min_value=2, max_value=4), label="n_plantillas")
    n_records = data.draw(st.integers(min_value=1, max_value=6), label="n_records")

    # Datos de cada registro: siempre con 'grado' y 'grupo' para poder coincidir
    # o no con las reglas según los valores generados.
    records_datos = [
        {
            "grado": data.draw(st.sampled_from(_VAL_POOL)),
            "grupo": data.draw(st.sampled_from(_VAL_POOL)),
        }
        for _ in range(n_records)
    ]

    _install_memory_db()
    cliente_id, plantilla_ids, registros = _seed(None, n_plantillas, records_datos)

    # La plantilla seleccionada en la cola (combo). Siempre una plantilla real
    # del cliente (FK de ItemCola.plantilla_id).
    queue_template_id = data.draw(st.sampled_from(plantilla_ids), label="queue_template_id")
    queue_template_name = "Plantilla de Cola"

    if with_config:
        # Generar reglas con orden distinto (permutación) -> precedencia clara.
        n_rules = data.draw(st.integers(min_value=0, max_value=5), label="n_rules")
        ordenes = data.draw(st.permutations(list(range(n_rules))))
        reglas = [
            ReglaDTO(
                plantilla_destino_id=plantilla_ids[
                    data.draw(st.integers(0, n_plantillas - 1))
                ],
                orden=ordenes[i],
                condiciones=(
                    CondicionDTO(
                        atributo=data.draw(st.sampled_from(_ATTR_POOL)),
                        valor=data.draw(st.sampled_from(_VAL_POOL)),
                        orden=0,
                    ),
                ),
            )
            for i in range(n_rules)
        ]
        # Default: una plantilla del cliente o None (para ejercitar fallback_cola).
        default_choice = data.draw(
            st.one_of(st.none(), st.sampled_from(plantilla_ids)), label="default"
        )
        from credencializacion.db.engine import DatabaseSession

        with DatabaseSession() as session:
            MultiTemplateRepository.save_config(
                session, cliente_id, reglas, default_choice
            )

    # --- Calcular lo esperado, espejando el código de producción --------------
    from credencializacion.db.engine import DatabaseSession

    with DatabaseSession() as session:
        config_dto = MultiTemplateRepository.get_config(session, cliente_id)

    if not with_config:
        assert config_dto is None  # sin guardar config, no hay DTO (Req 5.7).

    expected_plantilla_ids: list[int] = []
    for reg in registros:
        if config_dto is None:
            expected_plantilla_ids.append(queue_template_id)
        else:
            result = resolve_template(reg.datos or {}, config_dto, queue_template_id)
            if result.status == "error":
                # Registro omitido: no genera ItemCola (Req 5.8/8.4).
                continue
            expected_plantilla_ids.append(result.plantilla_id)

    # --- Ejercitar el código de producción ------------------------------------
    panel = _get_panel()
    panel._queue_panel.get_queue = lambda: list(registros)  # type: ignore[assignment]
    panel._combo_templates.clear()
    panel._combo_templates.addItem(queue_template_name, userData=queue_template_id)
    panel._combo_templates.setCurrentIndex(0)

    panel._save_queue_and_emit("front")

    # --- Verificar los ItemCola persistidos -----------------------------------
    from credencializacion.db.engine import DatabaseSession

    with DatabaseSession() as session:
        items = (
            session.query(ItemCola)
            .order_by(ItemCola.orden)
            .all()
        )
        actual_plantilla_ids = [it.plantilla_id for it in items]
        actual_registro_ids = [it.registro_id for it in items]

    # La secuencia de plantillas asignadas coincide exactamente con lo resuelto.
    assert actual_plantilla_ids == expected_plantilla_ids

    if not with_config:
        # Comportamiento actual preservado: todos reciben la plantilla de la cola
        # y no se omite ningún registro (Req 5.7).
        assert len(actual_plantilla_ids) == len(registros)
        assert all(pid == queue_template_id for pid in actual_plantilla_ids)

    # Los ItemCola corresponden a registros reales de la cola (no inventados).
    assert set(actual_registro_ids) <= {r.id for r in registros}


if __name__ == "__main__":
    test_property_17_queue_assembly_assigns_resolved_template()
    print("Property 17 OK")
