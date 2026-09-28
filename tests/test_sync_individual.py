"""Sincronización individual: solo la escuela (o pestaña) seleccionada.

La sincronización completa crece con la base, así que la de uso diario es la
de una sola escuela. Lo crítico es que no toque a las demás: ni sus datos ni
su depuración (el padrón de una escuela no dice nada de las otras).
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import credencializacion.db.engine as engine_module
from credencializacion.db.engine import DatabaseSession, get_session
from credencializacion.db.models import Base, Cliente, Registro


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(engine_module, "_engine", engine)
    monkeypatch.setattr(
        engine_module, "_SessionLocal",
        sessionmaker(bind=engine, autocommit=False, autoflush=False),
    )
    with DatabaseSession() as s:
        for api_id, nombre in ((1, "Escuela Uno"), (2, "Escuela Dos")):
            c = Cliente(nombre=nombre, tipo="escuela", school_api_id=api_id, config={})
            s.add(c)
            s.flush()
            # Un alumno que ya no viene en la API: la depuración lo borraría.
            s.add(Registro(cliente_id=c.id, enrollment_code=f"viejo-{api_id}",
                           datos={"nombre": "Viejo"}))
        s.commit()
    return engine


def _alumno(matricula: str) -> dict:
    return {"student_id": int(matricula), "enrollment_code": matricula,
            "nombre": "Ana", "estado_credencial": "pending", "photo_url": ""}


class _FakeAdapter:
    llamadas: list = []
    falla_alumnos = False

    def __init__(self, base_url=None, api_key=None):
        pass

    def fetch_schools(self):
        return [{"id": 1, "name": "Escuela Uno (nuevo nombre)", "total_students": 1},
                {"id": 2, "name": "Escuela Dos", "total_students": 1}]

    def fetch_records(self, school_id, status="all"):
        _FakeAdapter.llamadas.append(school_id)
        if _FakeAdapter.falla_alumnos:
            raise ConnectionError("sin red")
        return [_alumno(f"{school_id}00")]


def _correr(monkeypatch, school_api_id):
    import credencializacion.adapters.miescuela as miescuela
    from credencializacion.ui.pages.control_panel import SyncWorker

    _FakeAdapter.llamadas = []
    monkeypatch.setattr(miescuela, "MiEscuelaAdapter", _FakeAdapter)
    worker = SyncWorker(school_api_id)
    out: dict = {}
    worker.finished_ok.connect(lambda e, a, r: out.update(ok=(e, a, r)))
    worker.failed.connect(lambda m: out.update(error=m))
    worker.run()  # en el hilo actual
    return out


def _matriculas(api_id: int) -> set[str]:
    with get_session() as s:
        c = s.query(Cliente).filter_by(school_api_id=api_id).one()
        return {r.enrollment_code for r in s.query(Registro).filter_by(cliente_id=c.id)}


def test_solo_se_sincroniza_y_depura_la_escuela_seleccionada(db, monkeypatch):
    out = _correr(monkeypatch, 1)

    assert out["ok"][:2] == (1, 1)
    assert out["ok"][2]["escuelas_faltantes"] == []
    assert _FakeAdapter.llamadas == [1]
    assert _matriculas(1) == {"100"}          # descargado y depurado
    assert _matriculas(2) == {"viejo-2"}      # la otra escuela, intacta
    with get_session() as s:
        assert s.query(Cliente).filter_by(school_api_id=1).one().nombre == (
            "Escuela Uno (nuevo nombre)"
        )


def test_la_sincronizacion_completa_sigue_bajando_todas(db, monkeypatch):
    out = _correr(monkeypatch, None)

    assert out["ok"][:2] == (2, 2)
    assert _FakeAdapter.llamadas == [1, 2]
    assert _matriculas(2) == {"200"}


def test_una_escuela_que_ya_no_esta_en_la_plataforma_falla_sin_tocar_nada(db, monkeypatch):
    out = _correr(monkeypatch, 99)

    assert "ya no está" in out["error"]
    assert _FakeAdapter.llamadas == []


def test_si_falla_la_descarga_individual_se_reporta_y_no_se_depura(db, monkeypatch):
    monkeypatch.setattr(_FakeAdapter, "falla_alumnos", True)

    out = _correr(monkeypatch, 1)

    assert "sin red" in out["error"]
    assert "ok" not in out
    assert _matriculas(1) == {"viejo-1"}


def test_sheets_individual_solo_lee_la_pestana_del_cliente(db, monkeypatch):
    import credencializacion.adapters.sheets as sheets
    from credencializacion.ui.sheets_sync_worker import SheetsSyncWorker

    leidas: list[str] = []

    class _Hoja:
        def __init__(self, title):
            self.title = title

        def row_values(self, _n):
            leidas.append(self.title)
            return ["folio", "nombre"]

    class _Doc:
        def worksheets(self):
            return [_Hoja("Negocio A"), _Hoja("Negocio B")]

    monkeypatch.setattr(sheets, "authorize_gspread_client", lambda _p: object())
    monkeypatch.setattr(sheets, "open_spreadsheet_by_name", lambda _c, _n: _Doc())
    monkeypatch.setattr(
        sheets, "read_worksheet_records",
        lambda ws: [{"folio": "1", "nombre": ws.title}],
    )

    out: dict = {}
    worker = SheetsSyncWorker("cred.json", "Doc", solo_cliente="Negocio B")
    worker.finished_ok.connect(lambda c, r, rep: out.update(ok=(c, r)))
    worker.failed.connect(lambda m: out.update(error=m))
    worker.run()

    assert out == {"ok": (1, 1)}
    assert leidas == ["Negocio B"]

    out.clear()
    faltante = SheetsSyncWorker("cred.json", "Doc", solo_cliente="No existe")
    faltante.failed.connect(lambda m: out.update(error=m))
    faltante.run()
    assert "No existe" in out["error"]
