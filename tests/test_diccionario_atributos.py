"""Pruebas del diccionario de atributos y de la reconciliación de plantillas.

Cubren las garantías de las que depende el resto del sistema:

- Un dato se encuentra por su nombre canónico sin importar cómo lo nombre el
  origen, y en ambos sentidos (una plantilla vieja que apunta a la clave cruda
  sigue funcionando).
- Editar el diccionario surte efecto sin volver a sincronizar, y quitar una
  definición no destruye el dato.
- Los atributos ancla del sistema no se pueden renombrar ni eliminar.
- Una misma clave nunca puede quedar con dos dueños.
- La reconciliación es idempotente, respeta lo que no reconoce y se puede
  deshacer.

SQLite en memoria con los modelos reales.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from credencializacion.db.models import (
    Base, Cliente, CondicionVariante, ConfiguracionLado, Plantilla, Registro,
    VarianteImagen,
)
from credencializacion.services import diccionario as dic
from credencializacion.services import reconciliacion as rec


@pytest.fixture()
def session():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def _fk(dbapi, _rec):  # pragma: no cover
        cur = dbapi.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(eng)
    factory = sessionmaker(bind=eng, autoflush=False, future=True)
    s = factory()
    dic.invalidar_indice()
    dic.sembrar(s)
    s.commit()
    # El índice se construye contra ESTA sesión: sin esto, `obtener_indice()`
    # abriría la base real de la aplicación.
    dic.obtener_indice(s)
    try:
        yield s
    finally:
        s.close()
        dic.invalidar_indice()


def _registro(session, datos: dict) -> Registro:
    cliente = Cliente(nombre="Escuela", config={})
    session.add(cliente)
    session.flush()
    reg = Registro(cliente_id=cliente.id, datos=datos, enrollment_code="X1")
    session.add(reg)
    session.flush()
    return reg


# ── Resolución ───────────────────────────────────────────────────────────

def test_encuentra_el_dato_pese_a_que_el_origen_lo_nombre_distinto(session):
    ingles = _registro(session, {"address": "Colina Navona 235"})
    espanol = _registro(session, {"direccion": "Av. Santa Rosalía 763"})

    assert ingles.get_dato("domicilio") == "Colina Navona 235"
    assert espanol.get_dato("domicilio") == "Av. Santa Rosalía 763"


def test_una_plantilla_vieja_que_apunta_a_la_clave_cruda_sigue_resolviendo(session):
    """Sin esta propiedad, actualizar rompería el parque ya desplegado."""
    reg = _registro(session, {"address": "Colina Navona 235"})
    assert reg.get_dato("address") == "Colina Navona 235"


def test_clave_desconocida_devuelve_el_default(session):
    reg = _registro(session, {"address": "x"})
    assert reg.get_dato("no_existe") == ""
    assert reg.get_dato("no_existe", "—") == "—"


def test_editar_el_diccionario_surte_efecto_sin_re_sincronizar(session):
    reg = _registro(session, {"telefono_del_hogar": "3339596005"})
    assert reg.get_dato("telefono") == ""

    attr = next(a for a in dic.obtener_indice(session).atributos
                if a.nombre == "telefono")
    dic.agregar_definicion(session, attr.id, "telefono_del_hogar")
    dic.obtener_indice(session)

    assert reg.get_dato("telefono") == "3339596005"


def test_quitar_una_definicion_no_destruye_el_dato(session):
    reg = _registro(session, {"address": "Colina Navona 235"})
    attr = next(a for a in dic.obtener_indice(session).atributos
                if a.nombre == "domicilio")

    dic.quitar_definicion(session, attr.id, "address")
    dic.obtener_indice(session)

    assert reg.get_dato("domicilio") == ""
    assert reg.datos["address"] == "Colina Navona 235"  # el crudo sigue ahí


# ── Vista y bandeja ──────────────────────────────────────────────────────

def test_las_variantes_de_un_dato_colapsan_en_una_sola_entrada(session):
    vista = dic.vista_canonica(
        ["address", "direccion", "calle", "grado"], dic.obtener_indice(session),
    )
    assert vista == ["domicilio", "grado"]


def test_lo_que_el_diccionario_no_conoce_no_desaparece_de_la_vista(session):
    vista = dic.vista_canonica(["address", "peso_kg"], dic.obtener_indice(session))
    assert vista == ["domicilio", "peso_kg"]


def test_la_bandeja_lista_solo_lo_no_clasificado(session):
    idx = dic.obtener_indice(session)
    pendientes = dic.claves_sin_clasificar(
        ["address", "peso_kg", "grado", "autorizado_3_nombre"], idx,
    )
    # Las familias indexadas se reconocen por patrón y no son ruido.
    assert pendientes == ["peso_kg"]


# ── Protecciones ─────────────────────────────────────────────────────────

def test_los_atributos_ancla_no_se_renombran_ni_se_eliminan(session):
    ancla = next(a for a in dic.obtener_indice(session).atributos
                 if a.nombre == "enrollment_code")

    with pytest.raises(dic.ErrorDiccionario):
        dic.renombrar_atributo(session, ancla.id, "otro_nombre")
    with pytest.raises(dic.ErrorDiccionario):
        dic.eliminar_atributo(session, ancla.id)


def test_el_diccionario_de_un_ancla_si_es_editable(session):
    """Es lo que permite adaptar el sistema a otro país sin tocar el código."""
    ancla = next(a for a in dic.obtener_indice(session).atributos
                 if a.nombre == "matricula")
    dic.agregar_definicion(session, ancla.id, "numero_de_legajo")

    assert "numero_de_legajo" in dic.obtener_indice(session).definiciones_de("matricula")


def test_una_clave_no_puede_tener_dos_duenos(session):
    idx = dic.obtener_indice(session)
    domicilio = next(a for a in idx.atributos if a.nombre == "domicilio")
    telefono = next(a for a in idx.atributos if a.nombre == "telefono")

    with pytest.raises(dic.ErrorDiccionario):
        dic.agregar_definicion(session, telefono.id, "address")

    # Con `mover` sí se reasigna, y queda en uno solo.
    dic.agregar_definicion(session, telefono.id, "address", mover=True)
    idx = dic.obtener_indice(session)
    assert "address" not in idx.definiciones_de("domicilio")
    assert "address" in idx.definiciones_de("telefono")
    assert domicilio.id != telefono.id


def test_no_se_puede_usar_el_nombre_de_otro_atributo_como_definicion(session):
    """Ni con `mover`: el nombre seguiría resolviendo por su cuenta."""
    nuevo = dic.crear_atributo(session, "identificacion_oficial")
    for mover in (False, True):
        with pytest.raises(dic.ErrorDiccionario):
            dic.agregar_definicion(session, nuevo.id, "curp", mover=mover)


def test_el_caso_multipais(session):
    """El flujo que motiva todo: una palabra por país, un solo atributo."""
    attr = dic.crear_atributo(session, "identificacion_oficial", "Identificación")
    for palabra in ("ine", "dni", "cedula"):
        dic.agregar_definicion(session, attr.id, palabra)

    mx = _registro(session, {"ine": "AAAA800101HDF"})
    ar = _registro(session, {"dni": "30123456"})
    dic.obtener_indice(session)

    assert mx.get_dato("identificacion_oficial") == "AAAA800101HDF"
    assert ar.get_dato("identificacion_oficial") == "30123456"


# ── Siembra ──────────────────────────────────────────────────────────────

def test_sembrar_dos_veces_no_duplica(session):
    antes = len(dic.obtener_indice(session).atributos)
    assert dic.sembrar(session) == 0
    assert len(dic.obtener_indice(session).atributos) == antes


def test_sembrar_respeta_lo_que_el_usuario_configuro(session):
    attr = next(a for a in dic.obtener_indice(session).atributos
                if a.nombre == "domicilio")
    dic.quitar_definicion(session, attr.id, "calle")
    dic.agregar_definicion(session, attr.id, "domicilio_fiscal")

    dic.sembrar(session)
    definiciones = dic.obtener_indice(session).definiciones_de("domicilio")

    assert "calle" not in definiciones       # no se repone lo que quitó
    assert "domicilio_fiscal" in definiciones  # no se pierde lo que agregó


def test_el_nombre_del_atributo_no_se_siembra_como_definicion(session):
    assert "curp" not in dic.obtener_indice(session).definiciones_de("curp")


@pytest.mark.parametrize("nombre", [
    "estado_credencial", "credential_display_status", "form_status",
    "photo_status", "reemplazos", "qr_data", "domicilio",
])
def test_todos_los_atributos_nacen_visibles(session, nombre):
    """La visibilidad la decide el usuario, no una lista fija en el código."""
    attr = next(a for a in dic.obtener_indice(session).atributos
                if a.nombre == nombre)
    assert attr.visible is True


def test_ocultar_es_solo_de_interfaz_y_no_impide_resolver(session):
    reg = _registro(session, {"estado_credencial": "pending"})
    attr = next(a for a in dic.obtener_indice(session).atributos
                if a.nombre == "estado_credencial")

    dic.fijar_visibilidad(session, attr.id, False)
    dic.obtener_indice(session)

    assert reg.get_dato("estado_credencial") == "pending"


def test_un_atributo_oculto_no_es_una_clave_sin_clasificar(session):
    attr = next(a for a in dic.obtener_indice(session).atributos
                if a.nombre == "qr_data")
    dic.fijar_visibilidad(session, attr.id, False)
    idx = dic.obtener_indice(session)

    assert dic.claves_sin_clasificar(["qr_data"], idx) == []


def test_la_visibilidad_del_usuario_sobrevive_a_la_siembra(session):
    """Reimponer un default en cada arranque desharía su elección."""
    attr = next(a for a in dic.obtener_indice(session).atributos
                if a.nombre == "qr_data")
    dic.fijar_visibilidad(session, attr.id, False)

    dic.sembrar(session)

    vuelto = next(a for a in dic.obtener_indice(session).atributos
                  if a.nombre == "qr_data")
    assert vuelto.visible is False


def test_la_reversion_no_toca_lo_que_el_usuario_oculto_a_mano(session):
    """Solo se restaura lo que ocultó la política retirada, que dejó marca."""
    from credencializacion.db import migrations as mig
    from credencializacion.db.models import AtributoCanonico, MarcaMigracion

    automatico = session.query(AtributoCanonico).filter_by(nombre="qr_data").one()
    a_mano = session.query(AtributoCanonico).filter_by(nombre="domicilio").one()
    automatico.visible = False
    a_mano.visible = False
    mig.marcar_migracion(session, f"{mig._PREFIJO_OCULTO}qr_data")
    session.flush()

    marcas = (
        session.query(MarcaMigracion)
        .filter(MarcaMigracion.clave.like(f"{mig._PREFIJO_OCULTO}%"))
        .all()
    )
    nombres = [m.clave[len(mig._PREFIJO_OCULTO):] for m in marcas]
    for attr in (
        session.query(AtributoCanonico)
        .filter(AtributoCanonico.nombre.in_(nombres))
        .filter(AtributoCanonico.visible.is_(False))
        .all()
    ):
        attr.visible = True
    session.flush()

    assert nombres == ["qr_data"]
    assert automatico.visible is True   # lo ocultó el sistema → se restaura
    assert a_mano.visible is False      # lo ocultó el usuario → se respeta


# ── Reconciliación ───────────────────────────────────────────────────────

def _plantilla_con(session, elementos: list[dict]) -> Plantilla:
    cliente = Cliente(nombre="E", config={})
    session.add(cliente)
    session.flush()
    plantilla = Plantilla(
        cliente_id=cliente.id, nombre="credencial",
        elementos_frente=elementos, elementos_vuelta=[],
    )
    session.add(plantilla)
    session.flush()
    return plantilla


def test_reconciliar_reescribe_campos_y_textos_compuestos(session):
    plantilla = _plantilla_con(session, [
        {"type": "text", "campo_dato": "address", "properties": {}},
        {"type": "text", "campo_dato": "blood_type", "properties": {}},
        {"type": "composite", "campo_dato": "composite",
         "properties": {"composite_template": "{nombre} — {address}"}},
    ])

    plan = rec.planificar(session)
    assert plan.total_cambios == 3
    rec.aplicar(session, plan)

    elementos = session.get(Plantilla, plantilla.id).elementos_frente
    assert elementos[0]["campo_dato"] == "domicilio"
    assert elementos[1]["campo_dato"] == "tipo_sangre"
    assert elementos[2]["properties"]["composite_template"] == "{nombre} — {domicilio}"


def test_reconciliar_es_idempotente(session):
    _plantilla_con(session, [
        {"type": "text", "campo_dato": "address", "properties": {}},
    ])
    rec.aplicar(session, rec.planificar(session))

    assert rec.planificar(session).vacio


def test_reconciliar_respeta_los_slots_de_hermano(session):
    plantilla = _plantilla_con(session, [
        {"type": "text", "campo_dato": "address_hermano_3", "properties": {}},
    ])
    rec.aplicar(session, rec.planificar(session))

    elementos = session.get(Plantilla, plantilla.id).elementos_frente
    assert elementos[0]["campo_dato"] == "domicilio_hermano_3"


def test_reconciliar_no_toca_lo_que_no_reconoce(session):
    plantilla = _plantilla_con(session, [
        {"type": "text", "campo_dato": "campo_inventado", "properties": {}},
    ])
    plan = rec.planificar(session)

    assert plan.vacio
    assert [h.clave for h in plan.huerfanos] == ["campo_inventado"]
    rec.aplicar(session, plan)
    assert session.get(Plantilla, plantilla.id).elementos_frente[0]["campo_dato"] == (
        "campo_inventado"
    )


def test_reconciliar_alcanza_las_condiciones_de_multiplantillaje(session):
    plantilla = _plantilla_con(session, [])
    config = ConfiguracionLado(plantilla_id=plantilla.id, lado="frente")
    session.add(config)
    session.flush()
    variante = VarianteImagen(configuracion_id=config.id, imagen_path="a.png", orden=0)
    session.add(variante)
    session.flush()
    condicion = CondicionVariante(
        variante_id=variante.id, atributo="address", valor="x", orden=0,
    )
    session.add(condicion)
    session.flush()

    plan = rec.planificar(session)
    assert len(plan.cambios_condicion) == 1
    rec.aplicar(session, plan)

    assert session.get(CondicionVariante, condicion.id).atributo == "domicilio"


def test_se_puede_deshacer_una_reconciliacion(session):
    plantilla = _plantilla_con(session, [
        {"type": "text", "campo_dato": "address", "properties": {}},
    ])
    resultado = rec.aplicar(session, rec.planificar(session))
    assert session.get(Plantilla, plantilla.id).elementos_frente[0]["campo_dato"] == (
        "domicilio"
    )

    assert rec.deshacer(session, resultado.respaldo_id) is True
    assert session.get(Plantilla, plantilla.id).elementos_frente[0]["campo_dato"] == (
        "address"
    )


def test_deshacer_dos_veces_no_hace_nada(session):
    _plantilla_con(session, [
        {"type": "text", "campo_dato": "address", "properties": {}},
    ])
    resultado = rec.aplicar(session, rec.planificar(session))

    assert rec.deshacer(session, resultado.respaldo_id) is True
    assert rec.deshacer(session, resultado.respaldo_id) is False
