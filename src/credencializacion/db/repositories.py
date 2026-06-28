"""
Repositorios de acceso a datos para el multiplantillaje base (por lado).

`LadoConfigRepository` encapsula el CRUD de la `ConfiguracionLado` (única por la
combinación `(plantilla_id, lado)`) para que la UI y el flujo de impresión no
manipulen sesiones ni modelos directamente. Las operaciones reciben la sesión
como parámetro (el llamador controla la transacción vía `DatabaseSession`) y
entregan DTOs inmutables que el Motor_Seleccion_Imagen puede consumir sin estar
acoplado a SQLAlchemy.
"""
from credencializacion.db.models import (
    Cliente,
    CondicionVariante,
    ConfiguracionLado,
    Registro,
    VarianteImagen,
)
from credencializacion.services.image_selection import (
    CondicionDTO,
    ConfigLadoDTO,
    VarianteDTO,
    normalize,
)

# Lados válidos para una configuración.
LADOS_VALIDOS = ("frente", "vuelta")


class LadoConfigRepository:
    """CRUD de la configuración de multiplantillaje por `(plantilla, lado)`.

    Todos los métodos son estáticos y reciben la `session` como primer
    parámetro; no abren ni cierran transacciones por su cuenta.
    """

    @staticmethod
    def get_config_lado(session, plantilla_id: int, lado: str) -> ConfigLadoDTO | None:
        """Carga la configuración de un `(plantilla, lado)` como `ConfigLadoDTO`.

        Devuelve ``None`` si no existe (lo que equivale al comportamiento
        mono-imagen actual). Las variantes se entregan ordenadas por `orden`, y
        cada variante con su tupla de condiciones ordenada por `orden`.
        """
        config = (
            session.query(ConfiguracionLado)
            .filter_by(plantilla_id=plantilla_id, lado=lado)
            .first()
        )
        if config is None:
            return None

        variantes = tuple(
            VarianteDTO(
                imagen_path=variante.imagen_path,
                orden=variante.orden,
                condiciones=tuple(
                    CondicionDTO(
                        atributo=cond.atributo,
                        valor=cond.valor,
                        orden=cond.orden,
                    )
                    for cond in sorted(variante.condiciones, key=lambda c: c.orden)
                ),
            )
            for variante in sorted(config.variantes, key=lambda v: v.orden)
        )

        return ConfigLadoDTO(
            plantilla_id=config.plantilla_id,
            lado=config.lado,
            imagen_default_path=config.imagen_default_path,
            variantes=variantes,
        )

    @staticmethod
    def save_config_lado(
        session,
        plantilla_id: int,
        lado: str,
        variantes: list[VarianteDTO],
        imagen_default_path: str | None,
    ) -> ConfiguracionLado:
        """Upsert in-place de la única configuración de `(plantilla, lado)`.

        Si no existe la fila, la crea; si existe, la actualiza in situ
        (conservando `id`/`created_at`), reemplazando por completo sus variantes
        (y condiciones vía cascade) y la `imagen_default_path`. Respeta
        ``UNIQUE(plantilla_id, lado)``: nunca crea una segunda fila. Acepta 0
        variantes. Idempotente respecto al contenido.
        """
        if lado not in LADOS_VALIDOS:
            raise ValueError(f"Lado inválido: {lado!r}. Use uno de {LADOS_VALIDOS}.")

        config = (
            session.query(ConfiguracionLado)
            .filter_by(plantilla_id=plantilla_id, lado=lado)
            .first()
        )
        if config is None:
            config = ConfiguracionLado(plantilla_id=plantilla_id, lado=lado)
            session.add(config)

        config.imagen_default_path = imagen_default_path

        # Reemplazo total de variantes (y condiciones vía cascade delete-orphan).
        config.variantes.clear()
        session.flush()

        for v_pos, variante in enumerate(variantes):
            nueva = VarianteImagen(
                imagen_path=variante.imagen_path,
                orden=variante.orden if variante.orden is not None else v_pos,
            )
            for c_pos, cond in enumerate(variante.condiciones):
                nueva.condiciones.append(
                    CondicionVariante(
                        atributo=cond.atributo,
                        valor=cond.valor,
                        orden=cond.orden if cond.orden is not None else c_pos,
                    )
                )
            config.variantes.append(nueva)

        session.flush()
        return config

    @staticmethod
    def delete_config_lado(session, plantilla_id: int, lado: str) -> bool:
        """Elimina la configuración de un `(plantilla, lado)`.

        Devuelve ``True`` si existía y se eliminó (con sus variantes/condiciones
        en cascada), ``False`` si no existía.
        """
        config = (
            session.query(ConfiguracionLado)
            .filter_by(plantilla_id=plantilla_id, lado=lado)
            .first()
        )
        if config is None:
            return False
        session.delete(config)
        return True

    @staticmethod
    def available_attributes(session, cliente_id: int) -> list[str]:
        """Construye los Atributos_Disponibles del cliente (Req 8.1-8.3).

        Combina, sin duplicados, las claves de `Cliente.config["known_attributes"]`
        y las claves presentes en `Registro.datos` de los registros del cliente.
        La deduplicación es insensible a mayúsculas/minúsculas y a espacios
        circundantes (`normalize`), conservando la primera clave original vista.
        Solo se incluyen claves con longitud (recortada) en 1..100; se omiten
        las vacías. `known_attributes` tiene precedencia.
        """
        atributos: list[str] = []
        vistos: set[str] = set()

        def _agregar(clave: object) -> None:
            if not isinstance(clave, str):
                return
            if not (1 <= len(clave.strip()) <= 100):
                return
            normalizada = normalize(clave)
            if normalizada in vistos:
                return
            vistos.add(normalizada)
            atributos.append(clave)

        cliente = session.query(Cliente).filter_by(id=cliente_id).first()
        if cliente is not None:
            known = (cliente.config or {}).get("known_attributes")
            if isinstance(known, dict):
                known = list(known.keys())
            if isinstance(known, (list, tuple)):
                for clave in known:
                    _agregar(clave)

        registros = session.query(Registro).filter_by(cliente_id=cliente_id).all()
        for registro in registros:
            datos = registro.datos or {}
            if not isinstance(datos, dict):
                continue
            for clave in datos.keys():
                _agregar(clave)

        return atributos
