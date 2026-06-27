"""Pruebas de la UI del diálogo de multiplantillaje (tarea 6.4).

Verifican el modo edición, la eliminación y la persistencia de
``MultiTemplateDialog`` (``credencializacion.ui.dialogs.multi_template_dialog``)
de forma headless (``QT_QPA_PLATFORM=offscreen``) y con una base SQLite **en
memoria** para no tocar la base real ``data/credencializacion.db``.

Cobertura:
- create → save → get (round-trip de persistencia, Req 4.1, 4.3).
- modo edición: precarga de reglas/default y bloqueo del set (Req 4.4, Dec. 3).
- eliminación de la configuración completa (Decisión 4) con desbloqueo del set.
- fallo de persistencia simulado conservando el estado en pantalla (Req 4.6).

Validates: Requirements 4.1, 4.3, 4.4, 4.6, 6.1, 6.2, 6.3, 6.5, 6.6, 6.7
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import credencializacion.db.engine as engine_module
from credencializacion.db.models import Base, Cliente, Plantilla

from PySide6.QtWidgets import QApplication, QListWidget

# Una única instancia de QApplication para todas las pruebas.
_app = QApplication.instance() or QApplication([])


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


def _seed_cliente_con_plantillas() -> tuple[int, list[int]]:
    """Crea un cliente con tres plantillas y devuelve (cliente_id, [plantilla_ids])."""
    from credencializacion.db.engine import DatabaseSession

    with DatabaseSession() as session:
        cliente = Cliente(
            nombre="Escuela Demo",
            config={"known_attributes": {"grado": "", "grupo": ""}},
        )
        session.add(cliente)
        session.flush()
        ids = []
        for nombre in ("Diseño A", "Diseño B", "Diseño C"):
            p = Plantilla(
                cliente_id=cliente.id,
                nombre=nombre,
                orientacion="horizontal",
                ancho=8.5,
                alto=5.4,
            )
            session.add(p)
            session.flush()
            ids.append(p.id)
        return cliente.id, ids


def _seed_cliente_una_plantilla() -> tuple[int, int]:
    """Crea un cliente con UNA sola plantilla; devuelve (cliente_id, plantilla_id)."""
    from credencializacion.db.engine import DatabaseSession

    with DatabaseSession() as session:
        cliente = Cliente(
            nombre="Escuela Única",
            config={"known_attributes": {"grado": ""}},
        )
        session.add(cliente)
        session.flush()
        p = Plantilla(
            cliente_id=cliente.id,
            nombre="Diseño Único",
            orientacion="horizontal",
            ancho=8.5,
            alto=5.4,
        )
        session.add(p)
        session.flush()
        return cliente.id, p.id


def _make_dialog(cliente_id: int):
    from credencializacion.ui.dialogs.multi_template_dialog import (
        MultiTemplateDialog,
    )

    return MultiTemplateDialog(cliente_id)


def _regla(atributo, valor, dest, orden):
    """ReglaDTO con una sola condición (atributo, valor)."""
    from credencializacion.services.template_assignment import (
        CondicionDTO,
        ReglaDTO,
    )

    return ReglaDTO(
        plantilla_destino_id=dest,
        orden=orden,
        condiciones=(CondicionDTO(atributo=atributo, valor=valor, orden=0),),
    )


def _assign(plantilla_id, nombre, atributo, valor, is_default):
    """Asignación en pantalla con una sola condición."""
    return {
        "plantilla_id": plantilla_id,
        "nombre": nombre,
        "condiciones": [{"atributo": atributo, "valor": valor}],
        "is_default": is_default,
    }


def _pares_de_config(config):
    """Extrae (atributo, valor, destino, orden) de la primera condición de cada regla."""
    return [
        (r.condiciones[0].atributo, r.condiciones[0].valor,
         r.plantilla_destino_id, r.orden)
        for r in config.reglas
    ]


def test_create_save_get_roundtrip():
    """create → save → get devuelve exactamente lo guardado (Req 4.1, 4.3)."""
    _install_memory_db()
    cliente_id, [pa, pb, pc] = _seed_cliente_con_plantillas()

    dlg = _make_dialog(cliente_id)
    # Modo creación: sin configuración previa.
    assert dlg._edit_mode is False
    assert dlg._load_ok is True
    assert len(dlg._templates) == 3

    # Simula la captura de la ventana de asignación (condiciones por plantilla).
    dlg._assignments = [
        _assign(pa, "Diseño A", "grado", "1", True),
        _assign(pb, "Diseño B", "grado", "2", False),
    ]
    dlg._default_template_id = pa

    saved = {"emitted": None}
    dlg.config_saved.connect(lambda cid: saved.__setitem__("emitted", cid))

    dlg._on_save()

    # Señal emitida y diálogo aceptado.
    assert saved["emitted"] == cliente_id

    # Round-trip: lo persistido coincide con lo capturado.
    from credencializacion.db.engine import DatabaseSession
    from credencializacion.db.repositories import MultiTemplateRepository

    with DatabaseSession() as session:
        config = MultiTemplateRepository.get_config(session, cliente_id)
    assert config is not None
    assert config.plantilla_default_id == pa
    assert _pares_de_config(config) == [
        ("grado", "1", pa, 0), ("grado", "2", pb, 1)
    ]
    print("OK: create→save→get round-trip")


def test_edit_mode_preload_without_lock():
    """El modo edición precarga reglas/default y NO bloquea el set (Req 4.4, 9.2)."""
    _install_memory_db()
    cliente_id, [pa, pb, pc] = _seed_cliente_con_plantillas()

    # Persistir una configuración previa con dos reglas.
    from credencializacion.db.engine import DatabaseSession
    from credencializacion.db.repositories import MultiTemplateRepository

    with DatabaseSession() as session:
        MultiTemplateRepository.save_config(
            session, cliente_id,
            [
                _regla("grado", "1", pa, 0),
                _regla("grado", "2", pb, 1),
            ],
            plantilla_default_id=pb,
        )

    dlg = _make_dialog(cliente_id)

    # Entró en modo edición con precarga (Req 4.4).
    assert dlg._edit_mode is True
    # El set ya NO se bloquea (Decisión 3 revisada, Req 9.2).
    assert dlg._set_locked is False
    assert dlg._default_template_id == pb
    assert dlg._locked_template_ids == set()
    pares = sorted(
        (a["condiciones"][0]["atributo"], a["condiciones"][0]["valor"],
         a["plantilla_id"])
        for a in dlg._assignments
    )
    assert pares == [("grado", "1", pa), ("grado", "2", pb)]

    # Botón de eliminar visible y guardar habilitado (hay default y asignaciones).
    assert dlg._delete_btn.isHidden() is False
    assert dlg._save_btn.isEnabled() is True

    # Las casillas marcadas reflejan el set; `_selected_templates` las lee.
    sel_ids = {t["id"] for t in dlg._selected_templates()}
    assert sel_ids == {pa, pb}
    print("OK: edit mode preload sin bloqueo del set")


def test_delete_config_unlocks_set(monkeypatch):
    """Eliminar la configuración borra y desbloquea el set (Decisión 4)."""
    _install_memory_db()
    cliente_id, [pa, pb, pc] = _seed_cliente_con_plantillas()

    from credencializacion.db.engine import DatabaseSession
    from credencializacion.db.repositories import MultiTemplateRepository

    with DatabaseSession() as session:
        MultiTemplateRepository.save_config(
            session, cliente_id,
            [_regla("grado", "1", pa, 0)],
            plantilla_default_id=pa,
        )

    dlg = _make_dialog(cliente_id)
    assert dlg._edit_mode is True

    # Evitar el cuadro de confirmación modal: responder "Yes" automáticamente.
    import credencializacion.ui.dialogs.multi_template_dialog as mod

    monkeypatch.setattr(
        mod.QMessageBox, "question",
        lambda *a, **k: mod.QMessageBox.StandardButton.Yes,
    )

    dlg._on_delete_config()

    # La configuración fue eliminada de la BD.
    with DatabaseSession() as session:
        assert MultiTemplateRepository.get_config(session, cliente_id) is None

    # El set quedó desbloqueado y en modo creación.
    assert dlg._edit_mode is False
    assert dlg._set_locked is False
    assert dlg._locked_template_ids == set()
    assert dlg._assignments == []
    assert (
        dlg._template_list.selectionMode()
        == QListWidget.SelectionMode.NoSelection
    )
    assert dlg._delete_btn.isHidden() is True
    print("OK: delete_config unlocks set")


def test_persistence_failure_preserves_state(monkeypatch):
    """Si la persistencia falla, el estado en pantalla se conserva (Req 4.6)."""
    _install_memory_db()
    cliente_id, [pa, pb, pc] = _seed_cliente_con_plantillas()

    dlg = _make_dialog(cliente_id)
    dlg._assignments = [
        _assign(pa, "Diseño A", "grado", "1", True),
        _assign(pb, "Diseño B", "grado", "2", False),
    ]
    dlg._default_template_id = pa
    snapshot = list(dlg._assignments)
    snapshot_default = dlg._default_template_id

    import credencializacion.ui.dialogs.multi_template_dialog as mod

    def _boom(*_a, **_k):
        raise RuntimeError("fallo simulado de BD")

    monkeypatch.setattr(mod.MultiTemplateRepository, "save_config", _boom)
    # Silenciar el diálogo de error modal.
    monkeypatch.setattr(mod.QMessageBox, "critical", lambda *a, **k: None)

    emitted = {"count": 0}
    dlg.config_saved.connect(lambda *_: emitted.__setitem__("count", 1))

    # No debe lanzar; conserva el estado y no emite la señal ni acepta.
    dlg._on_save()

    assert dlg._assignments == snapshot
    assert dlg._default_template_id == snapshot_default
    assert emitted["count"] == 0
    # La nada se persistió: get_config sigue devolviendo None.
    from credencializacion.db.engine import DatabaseSession
    from credencializacion.db.repositories import MultiTemplateRepository

    with DatabaseSession() as session:
        assert MultiTemplateRepository.get_config(session, cliente_id) is None
    print("OK: persistence failure preserves on-screen state")


def test_single_template_global_config_saves():
    """Cliente con una sola plantilla → config global sin reglas (Req 3.8, 5.7, tarea 6.5).

    Per Decisión 5, no se abre la ventana de reglas: la única plantilla queda
    como Plantilla_Por_Defecto y la configuración se guarda sin reglas. El
    diálogo habilita Guardar directamente y `get_config` devuelve el default
    con `reglas` vacías.
    """
    _install_memory_db()
    cliente_id, plantilla_id = _seed_cliente_una_plantilla()

    dlg = _make_dialog(cliente_id)

    # Modo creación con asignación global de diseño único.
    assert dlg._edit_mode is False
    assert dlg._global_single_mode is True
    assert dlg._default_template_id == plantilla_id
    assert dlg._assignments == []
    # No se requiere la ventana de asignación; Guardar habilitado directamente.
    assert dlg._assign_btn.isHidden() is True
    assert dlg._save_btn.isEnabled() is True

    saved = {"emitted": None}
    dlg.config_saved.connect(lambda cid: saved.__setitem__("emitted", cid))

    dlg._on_save()

    assert saved["emitted"] == cliente_id

    from credencializacion.db.engine import DatabaseSession
    from credencializacion.db.repositories import MultiTemplateRepository

    with DatabaseSession() as session:
        config = MultiTemplateRepository.get_config(session, cliente_id)
    assert config is not None
    assert config.plantilla_default_id == plantilla_id
    assert config.reglas == ()  # configuración global sin reglas
    print("OK: single-template global config saves default-only (0 rules)")


def test_single_template_existing_config_edit_loads():
    """Cliente de una plantilla con config global guardada: carga y reguarda.

    Verifica que el modo edición sigue funcionando en diseño único: se carga la
    config global (default sin reglas) y Guardar permanece habilitado (tarea 6.5).
    """
    _install_memory_db()
    cliente_id, plantilla_id = _seed_cliente_una_plantilla()

    from credencializacion.db.engine import DatabaseSession
    from credencializacion.db.repositories import MultiTemplateRepository

    # Config global previa: default sin reglas.
    with DatabaseSession() as session:
        MultiTemplateRepository.save_config(
            session, cliente_id, [], plantilla_default_id=plantilla_id
        )

    dlg = _make_dialog(cliente_id)

    assert dlg._global_single_mode is True
    assert dlg._edit_mode is True
    assert dlg._default_template_id == plantilla_id
    assert dlg._assignments == []
    assert dlg._delete_btn.isHidden() is False
    assert dlg._save_btn.isEnabled() is True

    dlg._on_save()

    with DatabaseSession() as session:
        config = MultiTemplateRepository.get_config(session, cliente_id)
    assert config is not None
    assert config.plantilla_default_id == plantilla_id
    assert config.reglas == ()
    print("OK: single-template existing global config loads and re-saves")


def test_multi_template_still_requires_assignments():
    """La ruta multi-plantilla sigue exigiendo al menos una asignación (Req 2.6).

    Sin asignaciones y sin diseño único, el guardado se rechaza y la
    configuración no se persiste.
    """
    _install_memory_db()
    cliente_id, [pa, pb, pc] = _seed_cliente_con_plantillas()

    dlg = _make_dialog(cliente_id)

    # Cliente con 3 plantillas: no es diseño único.
    assert dlg._global_single_mode is False
    assert dlg._edit_mode is False
    # Sin asignaciones: Guardar deshabilitado y la validación falla.
    assert dlg._assignments == []
    assert dlg._save_btn.isEnabled() is False
    assert dlg._validate_assignments() is False

    from credencializacion.db.engine import DatabaseSession
    from credencializacion.db.repositories import MultiTemplateRepository

    with DatabaseSession() as session:
        assert MultiTemplateRepository.get_config(session, cliente_id) is None
    print("OK: multi-template path still requires assignments")


if __name__ == "__main__":
    test_create_save_get_roundtrip()
    test_edit_mode_preload_without_lock()
    test_single_template_global_config_saves()
    test_single_template_existing_config_edit_loads()
    test_multi_template_still_requires_assignments()

    class _MP:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    test_delete_config_unlocks_set(_MP())
    test_persistence_failure_preserves_state(_MP())
    print("\nAll dialog checks passed.")
