"""
Creación inicial de tablas y datos semilla.
Ejecuta create_all para generar el esquema SQLite.
"""
from sqlalchemy import inspect, text

from credencializacion.db.engine import get_engine
from credencializacion.db.models import (
    Base,
    Cliente,
    Plantilla,
    ColaImpresion,
    ItemCola,
    ConfiguracionLado,
    VarianteImagen,
    CondicionVariante,
)
from credencializacion.db.engine import DatabaseSession


def init_database() -> None:
    """Crea las tablas si no existen y migra el esquema/datos si hace falta."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    _drop_legacy_multiplantillaje(engine)
    _migrate_plantilla_base()


def _drop_legacy_multiplantillaje(engine) -> None:
    """Retira las tablas obsoletas del modelo viejo de multiplantillaje.

    El modelo previo (configuración por cliente con reglas que apuntaban a un
    diseño destino) fue reemplazado por el modelo por `(plantilla, lado)` con
    variantes de imagen. Estas tablas quedan sin uso. Como no hay datos
    productivos que preservar (se eliminó la única configuración de prueba), se
    eliminan de forma idempotente. No afecta a clientes/plantillas/registros/colas.
    """
    legacy = (
        "condiciones_asignacion",
        "reglas_asignacion",
        "configuraciones_multiplantillaje",
    )
    inspector = inspect(engine)
    existentes = set(inspector.get_table_names())
    a_borrar = [t for t in legacy if t in existentes]
    if not a_borrar:
        return

    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("PRAGMA foreign_keys=OFF")
        cur.execute("BEGIN")
        try:
            # Orden hijo→padre para respetar dependencias.
            for tabla in a_borrar:
                cur.execute(f"DROP TABLE IF EXISTS {tabla}")
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    finally:
        raw.close()


def _migrate_plantilla_base() -> None:
    """Reubica las imágenes base a la carpeta estable y remapea las rutas en la BD.

    Garantiza que las imágenes base (`Plantilla.recursos['fondo_frente'/'fondo_vuelta']`)
    sobrevivan a las actualizaciones:

    1. Crea la carpeta destino estable si no existe (primera ejecución/actualización).
    2. Siembra en ella las imágenes presentes en ubicaciones empaquetadas/legadas
       (sin sobrescribir las ya migradas).
    3. Por cada plantilla, si la ruta guardada apunta fuera de la carpeta estable
       o ya no existe, copia/ubica la imagen por nombre en la carpeta estable y
       actualiza la ruta en la BD. Es idempotente y no rompe rutas válidas.

    Si una imagen referenciada no puede recuperarse, se deja la ruta tal cual
    (no se pierde información en la BD).
    """
    import shutil
    from pathlib import Path

    from sqlalchemy.orm.attributes import flag_modified

    from credencializacion.db.models import Plantilla
    from credencializacion.utils.paths import (
        get_bundled_plantilla_base,
        get_plantilla_base_dir,
    )

    dest = get_plantilla_base_dir()  # crea el directorio si no existe

    # 1-2) Sembrar imágenes desde la carpeta empaquetada/legada (sin sobrescribir).
    bundled = get_bundled_plantilla_base()
    if bundled is not None:
        try:
            if bundled.resolve() != dest.resolve():
                for f in bundled.iterdir():
                    if f.is_file() and not (dest / f.name).exists():
                        try:
                            shutil.copy2(f, dest / f.name)
                        except Exception:  # noqa: BLE001
                            pass
        except Exception:  # noqa: BLE001
            pass

    # 3) Remapear rutas en Plantilla.recursos.
    try:
        with DatabaseSession() as session:
            for plantilla in session.query(Plantilla).all():
                recursos = dict(plantilla.recursos or {})
                changed = False
                for key in ("fondo_frente", "fondo_vuelta"):
                    old = recursos.get(key)
                    if not old:
                        continue
                    op = Path(old)
                    # Ya apunta a la carpeta estable y existe: nada que hacer.
                    if op.exists() and op.parent.resolve() == dest.resolve():
                        continue
                    target = dest / op.name
                    # Si la imagen original aún existe fuera de dest, copiarla.
                    if op.exists() and not target.exists():
                        try:
                            shutil.copy2(op, target)
                        except Exception:  # noqa: BLE001
                            pass
                    # Si la imagen está disponible en dest (recién copiada o
                    # sembrada en el paso 2), apuntar la ruta ahí.
                    if target.exists() and str(target) != old:
                        recursos[key] = str(target)
                        changed = True
                if changed:
                    plantilla.recursos = recursos
                    flag_modified(plantilla, "recursos")
    except Exception:  # noqa: BLE001
        # La migración de rutas es best-effort; no debe impedir el arranque.
        pass


def seed_default_data() -> None:
    """Inserta datos semilla si la BD está vacía."""
    with DatabaseSession() as session:
        # Solo insertar si no hay clientes
        if session.query(Cliente).count() > 0:
            return

        # Cliente demo
        demo_client = Cliente(
            nombre="Escuela Demo",
            tipo="escuela",
            token="demo-token",
            config={
                "qr_url_template": "https://app.miescuela.net/q/{access_token}",
                "photo_base_url": "https://app.miescuela.net/storage/photos/",
            },
        )
        session.add(demo_client)
        session.flush()  # Para obtener el ID

        # Plantilla default de credencial
        default_template = Plantilla(
            cliente_id=demo_client.id,
            nombre="Credencial Estándar",
            tipo="credencial",
            orientacion="horizontal",
            ancho=8.5,
            alto=5.4,
            elementos_frente=[
                {
                    "type": "background",
                    "x": 0, "y": 0,
                    "width": 85.0, "height": 54.0,
                    "z_order": 0,
                    "campo_dato": None,
                    "properties": {"color": "#FFFFFF"},
                },
                {
                    "type": "image",
                    "x": 5.0, "y": 8.0,
                    "width": 22.0, "height": 28.0,
                    "z_order": 1,
                    "campo_dato": "photo",
                    "properties": {"placeholder": "Foto"},
                },
                {
                    "type": "text",
                    "x": 30.0, "y": 10.0,
                    "width": 50.0, "height": 8.0,
                    "z_order": 2,
                    "campo_dato": "nombre_completo",
                    "properties": {
                        "font_family": "Inter",
                        "font_size": 14,
                        "font_weight": "bold",
                        "alignment": "center",
                        "color": "#171A2B",
                    },
                },
                {
                    "type": "text",
                    "x": 30.0, "y": 20.0,
                    "width": 50.0, "height": 6.0,
                    "z_order": 3,
                    "campo_dato": "enrollment_code",
                    "properties": {
                        "font_family": "Inter",
                        "font_size": 10,
                        "font_weight": "normal",
                        "alignment": "center",
                        "color": "#64748B",
                    },
                },
                {
                    "type": "qr",
                    "x": 62.0, "y": 28.0,
                    "width": 18.0, "height": 18.0,
                    "z_order": 4,
                    "campo_dato": "qr_data",
                    "properties": {},
                },
            ],
            elementos_vuelta=[
                {
                    "type": "background",
                    "x": 0, "y": 0,
                    "width": 85.0, "height": 54.0,
                    "z_order": 0,
                    "campo_dato": None,
                    "properties": {"color": "#F5F7FA"},
                },
                {
                    "type": "barcode",
                    "x": 15.0, "y": 15.0,
                    "width": 55.0, "height": 15.0,
                    "z_order": 1,
                    "campo_dato": "enrollment_code",
                    "properties": {},
                },
                {
                    "type": "text",
                    "x": 5.0, "y": 38.0,
                    "width": 75.0, "height": 10.0,
                    "z_order": 2,
                    "campo_dato": None,
                    "properties": {
                        "font_family": "Inter",
                        "font_size": 7,
                        "font_weight": "normal",
                        "alignment": "center",
                        "color": "#64748B",
                        "static_text": (
                            "Esta credencial es personal e intransferible. "
                            "En caso de pérdida, favor de reportarlo "
                            "inmediatamente a la administración escolar."
                        ),
                    },
                },
            ],
            posiciones_hoja={
                "page_size": "letter",
                "cards_per_page": 2,
                "positions": [
                    {"x_cm": 5.0, "y_cm": 2.0},
                    {"x_cm": 5.0, "y_cm": 15.0},
                ],
                "margins": {"top_cm": 1.5, "left_cm": 5.0},
            },
            recursos={},
        )
        session.add(default_template)
