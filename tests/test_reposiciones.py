"""Pruebas de reposiciones: alumnos y tarjetas de autorizados.

Cubren lo que decide qué se imprime y qué estatus se mueve en la API:

- El adaptador conserva la solicitud de cada autorizado (``credential_request``)
  y descarta ``extra_authorized_persons``.
- Las tarjetas de autorizado se deduplican por ``authorized_code_ids``.
- Una tarjeta de autorizado solo manda ``authorized_person_ids``: nunca el
  ``student_id`` del alumno (podría tener ya su credencial entregada).
- El diseño del autorizado N muestra a la persona correcta aunque ocupe otra
  posición.
"""
from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from credencializacion.adapters.miescuela import MiEscuelaAdapter
from credencializacion.services import reposiciones as rp

_APLANAR = MiEscuelaAdapter._flatten_record


def _persona(pid, request=None, *, codigo=None, status="pending", nombre="", at=None):
    return {
        "authorized_person_id": pid,
        "authorized_code_ids": codigo,
        "full_name": nombre or f"Persona {pid}",
        "phone": "3300000000",
        "relationship": "Madre",
        "is_primary": False,
        "scope": "official",
        "photo_url": f"https://x/{pid}.jpg",
        "credential_status": "replacement_requested" if request == "replacement" else status,
        "in_kit": True,
        "printable": True,
        "credential_request": request,
        "credential_replacement_count": 1 if request == "replacement" else 0,
        "credential_replacement_requested_at": at if request == "replacement" else None,
        "credential_extra_requested_at": at if request == "new" else None,
    }


def _alumno(sid, matricula, personas, *, status="delivered", extras=None):
    return {
        "id": sid,
        "first_name": "Ana",
        "last_name": f"López {sid}",
        "enrollment_code": matricula,
        "credential_status": status,
        "classroom": {"grade": "3", "group_letter": "B"},
        "school": {"name": "Escuela Test"},
        "authorized_persons": personas,
        "extra_authorized_persons": extras or [],
    }


# ── Adaptador ────────────────────────────────────────────────────────


def test_el_aplanado_conserva_la_solicitud_de_cada_autorizado():
    plano = _APLANAR(_alumno(10, "100", [
        _persona(38, "replacement", codigo="A38.40", at="2026-09-21T00:55:59-06:00"),
        _persona(39),
    ]))

    est = plano["autorizados_estatus"]
    assert [e["slot"] for e in est] == [1, 2]
    assert est[0] == {
        "slot": 1, "person_id": 38, "codigo": "A38.40", "request": "replacement",
        "status": "replacement_requested", "printable": True,
        "requested_at": "2026-09-21T00:55:59-06:00",
    }
    assert est[1]["request"] is None
    # Sin código del API se usa "A" + id, igual que el atributo del diseño.
    assert est[1]["codigo"] == "A39" == plano["autorizado_2_id"]


def test_los_autorizados_extra_nunca_entran():
    plano = _APLANAR(_alumno(10, "100", [], extras=[_persona(77, "new")]))

    assert plano["autorizados_estatus"] == []
    assert not any(k.startswith("autorizado_") for k in plano)


def test_el_marcado_manda_solo_las_listas_con_ids():
    adapter = MiEscuelaAdapter("https://api.test", "k")
    enviados = []

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"success": True, "updated": 0, "authorized_updated": 2}

    def _post(url, headers, json, timeout):
        enviados.append((url, json))
        return _Resp()

    adapter._session.post = _post

    adapter.mark_printing(authorized_person_ids=[4029, "4029", None, 5120])
    adapter.mark_ready([101], [4029])

    assert enviados[0] == (
        "https://api.test/api/credentials/bulk-mark-printing",
        {"authorized_person_ids": [4029, 5120]},
    )
    assert enviados[1][1] == {"student_ids": [101], "authorized_person_ids": [4029]}


def test_el_marcado_sin_ids_no_llama_a_la_api():
    adapter = MiEscuelaAdapter("https://api.test", "k")
    try:
        adapter.mark_ready([], [])
    except ValueError:
        return
    raise AssertionError("debió rechazar una llamada sin ids")


# ── Tarjetas ─────────────────────────────────────────────────────────


def test_tarjetas_de_alumno_solo_con_reposicion_solicitada():
    registros = [
        _APLANAR(_alumno(1, "1", [], status="replacement_requested")),
        _APLANAR(_alumno(2, "2", [], status="printing")),
    ]

    tarjetas = rp.tarjetas_de_alumnos(registros)

    assert [(t.tipo, t.student_id, t.enrollment_code) for t in tarjetas] == [
        ("alumno", 1, "1"),
    ]
    assert tarjetas[0].clave_plantilla == "alumno"


def test_un_autorizado_de_dos_hermanos_es_una_sola_tarjeta():
    compartida = dict(codigo="A4029.4030", at="2026-09-20T10:00:00-06:00")
    registros = [
        _APLANAR(_alumno(1, "1", [_persona(4029, "replacement", **compartida)])),
        _APLANAR(_alumno(2, "2", [_persona(4030, "replacement", **compartida)])),
    ]

    tarjetas = rp.tarjetas_de_autorizados(registros)

    assert len(tarjetas) == 1
    t = tarjetas[0]
    assert (t.enrollment_code, t.slot, t.authorized_person_id, t.codigo) == (
        "1", 1, 4029, "A4029.4030",
    )


def test_solo_se_toman_autorizados_con_solicitud_y_por_orden_de_llegada():
    registros = [_APLANAR(_alumno(1, "1", [
        _persona(1),                                                     # nada pendiente
        _persona(2, "new", at="2026-09-21T09:00:00-06:00"),
        _persona(3, "replacement", at="2026-09-19T09:00:00-06:00"),
    ]))]

    tarjetas = rp.tarjetas_de_autorizados(registros)

    assert [(t.slot, t.solicitud) for t in tarjetas] == [(3, "replacement"), (2, "new")]
    assert [t.clave_plantilla for t in tarjetas] == ["autorizado_3", "autorizado_2"]
    assert tarjetas[1].etiqueta == "Autorizado 2 · Nueva"
    assert tarjetas[0].nombre == "Persona 3"


# ── Plantillas ───────────────────────────────────────────────────────


def test_las_plantillas_se_detectan_por_nombre_y_gana_la_configurada():
    plantillas = [(5, "Alumno"), (6, "autorizado  1"), (7, "Autorizado 2"), (8, "Tutor")]

    assert rp.resolver_plantillas(plantillas) == {
        "alumno": 5, "autorizado_1": 6, "autorizado_2": 7,
    }
    # Lo configurado manda; una plantilla que ya no existe se ignora.
    assert rp.resolver_plantillas(
        plantillas, {"autorizado_2": 8, "autorizado_3": 999}
    ) == {"alumno": 5, "autorizado_1": 6, "autorizado_2": 8}


def test_slot_de_plantilla_solo_si_usa_una_posicion():
    assert rp.slot_de_plantilla([
        {"campo_dato": "autorizado_2_nombre"}, {"campo_dato": "autorizado_2_id"},
        {"campo_dato": "nombre_hermano_2"},
    ]) == 2
    # El reverso de una credencial de alumno lista a todos sus autorizados.
    assert rp.slot_de_plantilla([
        {"campo_dato": "autorizado_1_nombre"}, {"campo_dato": "autorizado_2_nombre"},
    ]) is None
    assert rp.slot_de_plantilla([{"campo_dato": "nombre"}]) is None


def test_el_diseno_del_slot_1_muestra_al_autorizado_de_otra_posicion():
    datos = _APLANAR(_alumno(1, "1", [_persona(10), _persona(20, "new", codigo="A20")]))

    extras = rp.extras_remapeo(datos, slot_plantilla=1, person_id=20)

    assert extras["autorizado_1_nombre"] == "Persona 20"
    assert extras["autorizado_1_id"] == "A20"
    assert extras["autorizado_1_foto"] == "https://x/20.jpg"
    # Misma posición o persona que ya no está: nada que remapear.
    assert rp.extras_remapeo(datos, 2, 20) == {}
    assert rp.extras_remapeo(datos, 1, 999) == {}


# ── Estatus ──────────────────────────────────────────────────────────


def test_una_tarjeta_de_autorizado_nunca_manda_el_student_id():
    alumno = SimpleNamespace(tipo_item="alumno", authorized_person_id=None,
                             registro=SimpleNamespace(datos={"student_id": 101}))
    autorizado = SimpleNamespace(tipo_item="autorizado", authorized_person_id=4029,
                                 registro=SimpleNamespace(datos={"student_id": 202}))
    cola_vieja = SimpleNamespace(tipo_item=None, authorized_person_id=None,
                                 datos={"student_id": "303"})

    assert rp.separar_ids([alumno, autorizado, autorizado, cola_vieja]) == (
        [101, 303], [4029],
    )


# ── Migración ────────────────────────────────────────────────────────


def test_la_migracion_agrega_las_columnas_a_items_cola_existentes():
    from credencializacion.db.migrations import _add_item_cola_reposicion_columns

    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE items_cola (id INTEGER PRIMARY KEY, cola_id INTEGER, "
            "registro_id INTEGER, plantilla_id INTEGER, orden INTEGER, "
            "estado_item VARCHAR(50))"
        ))
        conn.execute(text("INSERT INTO items_cola VALUES (1, 1, 1, 1, 1, 'pendiente')"))

    _add_item_cola_reposicion_columns(engine)
    _add_item_cola_reposicion_columns(engine)  # idempotente

    columnas = {c["name"] for c in inspect(engine).get_columns("items_cola")}
    assert {"tipo_item", "autorizado_slot", "authorized_person_id",
            "credential_request"} <= columnas
    with engine.connect() as conn:
        assert conn.execute(text("SELECT tipo_item FROM items_cola")).scalar() == "alumno"


# ── Render ───────────────────────────────────────────────────────────


def test_render_de_autorizados_imprime_a_cada_persona_sin_colapsar(tmp_path, monkeypatch):
    """Dos tarjetas del mismo alumno con el diseño de «Autorizado 1».

    La segunda persona está en la posición 2; el render debe copiar sus datos
    a la posición 1. El diseño usa slots de hermano, que en colas normales
    colapsan familias: aquí no debe descartarse ninguna tarjeta.
    """
    import fitz
    from sqlalchemy import event
    from sqlalchemy.orm import sessionmaker

    import credencializacion.db.engine as engine_module
    from credencializacion.db.engine import DatabaseSession
    from credencializacion.db.models import Base, Cliente, Plantilla, Registro
    from credencializacion.ui.render_worker import QueueRenderWorker

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(engine_module, "_engine", engine)
    monkeypatch.setattr(
        engine_module, "_SessionLocal",
        sessionmaker(bind=engine, autocommit=False, autoflush=False),
    )

    def _texto(campo, y):
        return {
            "type": "text", "x": 5.0, "y": y, "width": 70.0, "height": 8.0,
            "z_order": 1, "campo_dato": campo,
            "properties": {"font_size": 10, "color": "#000000"},
        }

    datos = _APLANAR(_alumno(1, "1", [
        _persona(10, "replacement", codigo="A10", nombre="Rosa Uno"),
        _persona(20, "new", codigo="A20", nombre="Pedro Dos"),
    ]))
    datos["tutor_email"] = "familia@test"
    with DatabaseSession() as s:
        cliente = Cliente(nombre="Escuela Test", config={})
        s.add(cliente)
        s.flush()
        plantilla = Plantilla(
            cliente_id=cliente.id, nombre="Autorizado 1", orientacion="horizontal",
            ancho=8.5, alto=5.4,
            elementos_frente=[_texto("autorizado_1_nombre", 5.0), _texto("nombre_hermano_2", 20.0)],
            elementos_vuelta=[], recursos={},
        )
        reg = Registro(cliente_id=cliente.id, datos=datos, enrollment_code="1")
        s.add_all([plantilla, reg])
        s.commit()
        pid, rid = plantilla.id, reg.id

    worker = QueueRenderWorker([rid, rid], pid, str(tmp_path), autorizados=[10, 20])
    resultado = {}
    worker.finished_ok.connect(lambda f, v: resultado.update(frentes=f))
    worker.failed.connect(lambda m: resultado.update(error=m))
    worker.run()  # en el hilo actual

    assert "error" not in resultado, resultado
    with fitz.open(resultado["frentes"]) as doc:
        texto = "".join(page.get_text() for page in doc)
    assert "Rosa Uno" in texto
    assert "Pedro Dos" in texto
