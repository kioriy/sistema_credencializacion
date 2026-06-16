"""
Creación inicial de tablas y datos semilla.
Ejecuta create_all para generar el esquema SQLite.
"""
from credencializacion.db.engine import get_engine
from credencializacion.db.models import Base, Cliente, Plantilla
from credencializacion.db.engine import DatabaseSession


def init_database() -> None:
    """Crea todas las tablas si no existen."""
    engine = get_engine()
    Base.metadata.create_all(engine)


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
