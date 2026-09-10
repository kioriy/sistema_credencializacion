"""El motor resuelve `campo_dato` por el diccionario (columnas de Sheets).

Confirma el arreglo: un elemento enlazado al nombre canónico (p. ej. «matricula»,
«nombre», «grado») encuentra la columna cruda del cliente de Google Sheets aunque
se llame distinto (sinónimo, acento o mayúsculas), y sigue funcionando con datos
ya canónicos (flujo API).
"""
from __future__ import annotations

import types

import pytest

from credencializacion.db.engine import get_engine
from credencializacion.db.models import Base, Registro
from credencializacion.renderer.pdf_engine import PDFEngine


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    # El diccionario se construye desde la BD (obtener_indice); apuntarla a temp.
    import credencializacion.utils.paths as P
    monkeypatch.setattr(P, "get_db_path", lambda: str(tmp_path / "t.db"))
    import credencializacion.db.engine as E
    for attr in ("_engine", "_SessionLocal"):
        if hasattr(E, attr):
            setattr(E, attr, None)
    Base.metadata.create_all(get_engine())
    # Reset del índice cacheado del diccionario para que lea esta BD.
    import credencializacion.services.diccionario as D
    if hasattr(D, "_indice_cache"):
        D._indice_cache = None


def _engine():
    # PDFEngine solo necesita 'plantilla' para _dato si usamos el método directo;
    # basta un objeto mínimo para poblar el índice cacheado por instancia.
    eng = PDFEngine.__new__(PDFEngine)
    eng._current_extra = {}
    return eng


def _reg(datos):
    r = Registro(cliente_id=1, datos=datos, enrollment_code="X")
    return r


def test_sinonimo_de_matricula_resuelve():
    eng = _engine()
    # Columna cruda 'folio' (sinónimo de matricula en el diccionario).
    assert eng._dato(_reg({"folio": "12345"}), "matricula") == "12345"


def test_acento_y_mayusculas_resuelven():
    eng = _engine()
    assert eng._dato(_reg({"Matrícula": "A-9"}), "matricula") == "A-9"
    assert eng._dato(_reg({"GRADO": "3"}), "grado") == "3"


def test_coincidencia_exacta_sigue_funcionando():
    eng = _engine()
    # Datos ya canónicos (flujo API): no debe romperse.
    assert eng._dato(_reg({"matricula": "777", "nombre": "Ana"}), "matricula") == "777"
    assert eng._dato(_reg({"nombre": "Ana"}), "nombre") == "Ana"


def test_columna_no_reconocida_se_usa_cruda():
    eng = _engine()
    # Un atributo personalizado sin canónico se enlaza por su nombre exacto.
    assert eng._dato(_reg({"club": "Ajedrez"}), "club") == "Ajedrez"


def test_campo_ausente_devuelve_vacio():
    eng = _engine()
    assert eng._dato(_reg({"nombre": "Ana"}), "matricula") == ""


def test_extra_tiene_prioridad():
    eng = _engine()
    eng._current_extra = {"nombre_hermano_2": "Luis"}
    assert eng._dato(_reg({"nombre": "Ana"}), "nombre_hermano_2") == "Luis"
