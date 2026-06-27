"""Pruebas de integración de render y migración (tarea 9).

Cubren dos comportamientos del flujo de multiplantillaje mediante ejemplos
concretos (no property-based):

1. ``PDFEngine.render_queue`` usa la plantilla de **cada ítem** al renderizar la
   cola (Req 5.6) y **omite** los ítems cuya plantilla asignada no puede
   cargarse — imagen base no disponible — registrando un error que identifica
   el registro y la plantilla, y continuando con el resto (Req 5.9).
2. ``init_database`` (``Base.metadata.create_all``) es **aditivo**: sobre una BD
   con el esquema/datos previos crea las dos tablas nuevas
   (``configuraciones_multiplantillaje``, ``reglas_asignacion``) sin alterar los
   datos existentes (clientes/plantillas/registros/colas/items).

Se usan plantillas/registros mínimos (stubs) para el render y una BD SQLite
**en memoria** (``StaticPool``) para la migración, sin tocar nunca la base real
``data/credencializacion.db``.

Validates: Requirements 5.6, 5.9
"""
from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import credencializacion.db.engine as engine_module
from credencializacion.db.migrations import init_database
from credencializacion.db.models import (
    Base,
    Cliente,
    ColaImpresion,
    ItemCola,
    Plantilla,
    Registro,
)
from credencializacion.renderer.pdf_engine import PDFEngine


# Imágenes base reales del repositorio, usadas como recursos cargables.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_BASE_IMAGES = [
    _REPO_ROOT / "plantilla_base" / "alumnos_frente.jpeg",
    _REPO_ROOT / "plantilla_base" / "alumnos_vuelta2.jpg",
    _REPO_ROOT / "plantilla_base" / "frente_vuelta-02.jpg",
]


class _StubRegistro:
    """Registro mínimo con la interfaz que usa PDFEngine."""

    def __init__(self, datos: dict, id: int = 0, enrollment_code: str = "") -> None:
        self._datos = datos
        self.id = id
        self.enrollment_code = enrollment_code
        self.photo_path = None

    def get_dato(self, key: str, default=""):
        return self._datos.get(key, default)


def _make_plantilla(
    nombre: str,
    campo: str,
    fondo_frente: str = "",
    pid: int = 0,
) -> SimpleNamespace:
    """Plantilla horizontal mínima con un texto único y recurso de fondo dado."""
    elementos_frente = [
        {
            "type": "text",
            "x": 10.0,
            "y": 8.0,
            "width": 50.0,
            "height": 10.0,
            "z_order": 1,
            "campo_dato": campo,
            "properties": {
                "font_family": "Helvetica",
                "font_size": 12,
                "alignment": "center",
                "color": "#000000",
            },
        }
    ]
    return SimpleNamespace(
        id=pid,
        nombre=nombre,
        orientacion="horizontal",
        ancho=8.5,
        alto=5.4,
        elementos_frente=elementos_frente,
        elementos_vuelta=[],
        recursos={"fondo_frente": fondo_frente} if fondo_frente else {},
        posiciones_hoja={},
    )


# ──────────────────────────────────────────────────────────────────────────
# Test 1 — render_queue usa la plantilla de cada ítem (Req 5.6)
# ──────────────────────────────────────────────────────────────────────────
def test_render_queue_uses_each_items_template(tmp_path: Path):
    """Cada ítem se renderiza con los elementos y la imagen base de SU plantilla.

    Se construyen 3 pares ``(registro, plantilla)`` con plantillas DISTINTAS
    (elementos y fondo propios). Se espía ``_render_card`` para capturar qué
    ``elementos`` y qué imagen base (``_current_base_img``) usó el motor en cada
    ítem; deben corresponder, en orden, a la plantilla de cada ítem.
    """
    plantillas = [
        _make_plantilla(f"Diseño {i}", f"campo_{i}", str(_BASE_IMAGES[i]), pid=i + 1)
        for i in range(3)
    ]
    # El motor se construye con una plantilla (dimensiones), pero render_queue
    # debe usar la plantilla de cada ítem, no la del constructor.
    engine = PDFEngine(plantillas[0])

    captured: list[tuple] = []
    original = engine._render_card

    def _spy(canvas, registro, elementos, base_pos):
        captured.append((elementos, engine._current_base_img))
        return original(canvas, registro, elementos, base_pos)

    engine._render_card = _spy  # type: ignore[assignment]

    registros = [_StubRegistro({f"campo_{i}": f"valor_{i}"}, id=i + 1) for i in range(3)]
    items = list(zip(registros, plantillas))

    out = tmp_path / "cola.pdf"
    result = engine.render_queue(items, "frente", out)

    # PDF generado y no vacío.
    assert result.exists()
    assert result.stat().st_size > 0

    # Un _render_card por ítem, en orden, con elementos y fondo de SU plantilla.
    assert len(captured) == 3
    for (elementos, base_img), plantilla in zip(captured, plantillas):
        assert elementos is plantilla.elementos_frente
        assert base_img == plantilla.recursos["fondo_frente"]
    print("OK: render_queue usa la plantilla de cada ítem (Req 5.6)")


# ──────────────────────────────────────────────────────────────────────────
# Test 1b — render_queue omite ítems con recursos faltantes (Req 5.9)
# ──────────────────────────────────────────────────────────────────────────
def test_render_queue_skips_items_with_missing_resources(tmp_path: Path, caplog):
    """El ítem cuya plantilla referencia una imagen base inexistente se omite.

    Se arman 3 ítems; el del medio referencia un fondo que NO existe. El motor
    debe omitir ese ítem (no llamar a ``_render_card`` para él), continuar con
    los otros dos y registrar un error que identifique el registro y la
    plantilla afectados (Req 5.9).
    """
    missing = str(tmp_path / "no_existe.png")
    assert not Path(missing).exists()

    plantillas = [
        _make_plantilla("OK A", "campo_0", str(_BASE_IMAGES[0]), pid=1),
        _make_plantilla("FALTANTE", "campo_1", missing, pid=2),
        _make_plantilla("OK B", "campo_2", str(_BASE_IMAGES[1]), pid=3),
    ]
    engine = PDFEngine(plantillas[0])

    rendered_elementos: list = []
    original = engine._render_card

    def _spy(canvas, registro, elementos, base_pos):
        rendered_elementos.append(elementos)
        return original(canvas, registro, elementos, base_pos)

    engine._render_card = _spy  # type: ignore[assignment]

    registros = [
        _StubRegistro({"campo_0": "a"}, id=11, enrollment_code="REG-A"),
        _StubRegistro({"campo_1": "b"}, id=22, enrollment_code="REG-B"),
        _StubRegistro({"campo_2": "c"}, id=33, enrollment_code="REG-C"),
    ]
    items = list(zip(registros, plantillas))

    with caplog.at_level(logging.ERROR, logger="credencializacion.renderer.pdf_engine"):
        result = engine.render_queue(items, "frente", tmp_path / "cola_skip.pdf")

    assert result.exists()

    # Solo se renderizaron los dos ítems válidos (A y B), no el faltante.
    assert len(rendered_elementos) == 2
    assert rendered_elementos[0] is plantillas[0].elementos_frente
    assert rendered_elementos[1] is plantillas[2].elementos_frente

    # Se registró un error que identifica el registro y la plantilla omitidos.
    error_text = "\n".join(
        r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR
    )
    assert "22" in error_text  # id del registro omitido
    assert "FALTANTE" in error_text  # nombre de la plantilla omitida
    print("OK: render_queue omite ítems con recursos faltantes (Req 5.9)")


def test_render_queue_keeps_template_without_base_image(tmp_path: Path):
    """Una plantilla SIN imagen base configurada se renderiza (no se omite).

    Comportamiento actual preservado: la ausencia de ``fondo_frente`` no es un
    fallo de carga; el ítem se dibuja solo con sus elementos.
    """
    plantilla = _make_plantilla("Sin fondo", "campo_0", fondo_frente="", pid=1)
    engine = PDFEngine(plantilla)

    rendered = []
    original = engine._render_card
    engine._render_card = lambda c, r, e, b: (rendered.append(e), original(c, r, e, b))[1]  # type: ignore

    items = [(_StubRegistro({"campo_0": "x"}, id=1), plantilla)]
    result = engine.render_queue(items, "frente", tmp_path / "cola_nofondo.pdf")

    assert result.exists()
    assert len(rendered) == 1
    print("OK: plantilla sin imagen base no se omite")


# ──────────────────────────────────────────────────────────────────────────
# Test 2 — init_database / create_all es aditivo (Req 5.9 migración)
# ──────────────────────────────────────────────────────────────────────────
_OLD_TABLES = [
    Cliente.__table__,
    Plantilla.__table__,
    Registro.__table__,
    ColaImpresion.__table__,
    ItemCola.__table__,
]
_NEW_TABLES = {
    "configuraciones_multiplantillaje",
    "reglas_asignacion",
    "condiciones_asignacion",
}


def _install_memory_db_with_old_schema():
    """Crea una BD en memoria SOLO con el esquema previo y redirige el engine.

    Mirror de instalaciones existentes: las tablas nuevas aún no existen.
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

    # Crear únicamente las tablas del esquema previo (no las nuevas).
    Base.metadata.create_all(engine, tables=_OLD_TABLES)
    engine_module._engine = engine
    engine_module._SessionLocal = sessionmaker(
        bind=engine, autocommit=False, autoflush=False
    )
    return engine


def _seed_old_data():
    """Inserta un conjunto representativo de datos previos y devuelve un snapshot."""
    from credencializacion.db.engine import DatabaseSession

    with DatabaseSession() as session:
        cliente = Cliente(nombre="Escuela Previa", config={"known_attributes": {"grado": ""}})
        session.add(cliente)
        session.flush()

        plantilla = Plantilla(
            cliente_id=cliente.id,
            nombre="Diseño Previo",
            orientacion="horizontal",
            ancho=8.5,
            alto=5.4,
        )
        session.add(plantilla)
        session.flush()

        registro = Registro(
            cliente_id=cliente.id,
            datos={"nombre": "Elena", "grado": "3"},
            enrollment_code="ENR-001",
        )
        session.add(registro)
        session.flush()

        cola = ColaImpresion(nombre="Cola Previa", estado="pendiente", total_registros=1)
        session.add(cola)
        session.flush()

        item = ItemCola(
            cola_id=cola.id,
            registro_id=registro.id,
            plantilla_id=plantilla.id,
            orden=1,
        )
        session.add(item)
        session.flush()

        snapshot = {
            "cliente": (cliente.id, cliente.nombre, dict(cliente.config)),
            "plantilla": (plantilla.id, plantilla.nombre, plantilla.ancho, plantilla.alto),
            "registro": (registro.id, dict(registro.datos), registro.enrollment_code),
            "cola": (cola.id, cola.nombre, cola.estado, cola.total_registros),
            "item": (item.id, item.cola_id, item.registro_id, item.plantilla_id, item.orden),
        }
    return snapshot


def test_init_database_is_additive_over_existing_schema():
    """``init_database`` añade las tablas nuevas sin tocar los datos previos."""
    engine = _install_memory_db_with_old_schema()
    snapshot = _seed_old_data()

    # Precondición: las tablas nuevas NO existen todavía.
    tables_before = set(inspect(engine).get_table_names())
    assert _NEW_TABLES.isdisjoint(tables_before)

    # Ejecutar la migración real (usa get_engine() -> engine redirigido).
    init_database()

    # Las dos tablas nuevas ahora existen.
    tables_after = set(inspect(engine).get_table_names())
    assert _NEW_TABLES.issubset(tables_after)
    # Y todas las tablas previas siguen presentes.
    assert tables_before.issubset(tables_after)

    # Los datos previos permanecen exactamente iguales.
    from credencializacion.db.engine import DatabaseSession

    with DatabaseSession() as session:
        cliente = session.get(Cliente, snapshot["cliente"][0])
        plantilla = session.get(Plantilla, snapshot["plantilla"][0])
        registro = session.get(Registro, snapshot["registro"][0])
        cola = session.get(ColaImpresion, snapshot["cola"][0])
        item = session.get(ItemCola, snapshot["item"][0])

        assert (cliente.id, cliente.nombre, dict(cliente.config)) == snapshot["cliente"]
        assert (
            plantilla.id, plantilla.nombre, plantilla.ancho, plantilla.alto
        ) == snapshot["plantilla"]
        assert (
            registro.id, dict(registro.datos), registro.enrollment_code
        ) == snapshot["registro"]
        assert (cola.id, cola.nombre, cola.estado, cola.total_registros) == snapshot["cola"]
        assert (
            item.id, item.cola_id, item.registro_id, item.plantilla_id, item.orden
        ) == snapshot["item"]

        # Conteos inalterados (no se duplicó ni borró nada).
        assert session.query(Cliente).count() == 1
        assert session.query(Plantilla).count() == 1
        assert session.query(Registro).count() == 1
        assert session.query(ColaImpresion).count() == 1
        assert session.query(ItemCola).count() == 1

    print("OK: init_database es aditivo y preserva los datos existentes")


def test_init_database_is_idempotent_on_full_schema():
    """Re-ejecutar la migración sobre un esquema ya completo no altera datos."""
    engine = _install_memory_db_with_old_schema()
    snapshot = _seed_old_data()

    init_database()  # crea las tablas nuevas
    init_database()  # segunda ejecución: no debe fallar ni alterar datos

    tables = set(inspect(engine).get_table_names())
    assert _NEW_TABLES.issubset(tables)

    from credencializacion.db.engine import DatabaseSession

    with DatabaseSession() as session:
        assert session.query(Cliente).count() == 1
        assert session.query(ItemCola).count() == 1
        registro = session.get(Registro, snapshot["registro"][0])
        assert dict(registro.datos) == snapshot["registro"][1]
    print("OK: init_database es idempotente sobre el esquema completo")


if __name__ == "__main__":
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    test_render_queue_uses_each_items_template(tmp)

    class _CapLog:
        records: list = []

        def at_level(self, *a, **k):
            import contextlib

            return contextlib.nullcontext()

    test_render_queue_skips_items_with_missing_resources(tmp, _CapLog())
    test_render_queue_keeps_template_without_base_image(tmp)
    test_init_database_is_additive_over_existing_schema()
    test_init_database_is_idempotent_on_full_schema()
    print("\nAll render + migration integration checks passed.")
