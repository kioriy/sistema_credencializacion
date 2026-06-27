"""
Repositorios de acceso a datos para el multiplantillaje base.

`MultiTemplateRepository` encapsula el CRUD de la `ConfiguracionMultiplantillaje`
para que la UI y el flujo de impresión no manipulen sesiones ni modelos
directamente. Las operaciones reciben la sesión como parámetro (el llamador
controla la transacción vía `DatabaseSession`) y entregan DTOs inmutables que el
Motor_Asignacion puede consumir sin estar acoplado a SQLAlchemy.
"""
from credencializacion.db.models import (
    Cliente,
    CondicionAsignacion,
    ConfiguracionMultiplantillaje,
    Plantilla,
    Registro,
    ReglaAsignacion,
)
from credencializacion.services.template_assignment import (
    CondicionDTO,
    ConfigDTO,
    ReglaDTO,
    normalize,
)


class MultiTemplateRepository:
    """CRUD de la configuración de multiplantillaje por cliente.

    Todos los métodos son estáticos y reciben la `session` como primer
    parámetro; no abren ni cierran transacciones por su cuenta, de modo que el
    llamador (típicamente `with DatabaseSession() as session:`) decida cuándo
    confirmar o revertir.
    """

    @staticmethod
    def get_config(session, cliente_id: int) -> ConfigDTO | None:
        """Carga la configuración completa de un cliente como `ConfigDTO`.

        Devuelve ``None`` si el cliente no tiene configuración (lo que equivale
        al comportamiento mono-plantilla actual, Req 5.7). Las reglas se entregan
        ordenadas por `orden` (precedencia, Req 5.4) como tupla inmutable y
        `plantillas_existentes` contiene los ids de las plantillas vigentes del
        cliente para detectar destinos inexistentes (Req 8.6).
        """
        config = (
            session.query(ConfiguracionMultiplantillaje)
            .filter_by(cliente_id=cliente_id)
            .first()
        )
        if config is None:
            return None

        reglas = tuple(
            ReglaDTO(
                plantilla_destino_id=regla.plantilla_destino_id,
                orden=regla.orden,
                condiciones=tuple(
                    CondicionDTO(
                        atributo=cond.atributo,
                        valor=cond.valor,
                        orden=cond.orden,
                    )
                    for cond in sorted(regla.condiciones, key=lambda c: c.orden)
                ),
            )
            for regla in sorted(config.reglas, key=lambda r: r.orden)
        )

        plantillas_existentes = frozenset(
            pid
            for (pid,) in session.query(Plantilla.id)
            .filter_by(cliente_id=cliente_id)
            .all()
        )

        return ConfigDTO(
            cliente_id=config.cliente_id,
            plantilla_default_id=config.plantilla_default_id,
            reglas=reglas,
            plantillas_existentes=plantillas_existentes,
        )

    @staticmethod
    def save_config(
        session,
        cliente_id: int,
        reglas: list[ReglaDTO],
        plantilla_default_id: int | None,
    ) -> ConfiguracionMultiplantillaje:
        """Upsert de la única configuración del cliente (Req 4.1, 4.2, 4.3).

        Si el cliente NO tiene configuración, crea una nueva; si ya tiene,
        actualiza la existente **in situ** (conservando su `id`/`created_at`)
        reemplazando por completo sus reglas y condiciones. Respeta el
        ``UNIQUE(cliente_id)``: nunca genera una segunda fila para el mismo
        cliente, por lo que tener varias plantillas no produce varias
        configuraciones.

        Es idempotente respecto al contenido: guardar dos veces el mismo
        conjunto de reglas/condiciones y el mismo default deja el mismo estado
        lógico, sin residuales (Req 4.4, 6.5, 6.7). Acepta reglas con
        ``condiciones == ()`` para soportar configuración parcial (Req 9.3): la
        plantilla queda registrada sin condiciones, lista para completarse luego.
        """
        config = (
            session.query(ConfiguracionMultiplantillaje)
            .filter_by(cliente_id=cliente_id)
            .first()
        )
        if config is None:
            config = ConfiguracionMultiplantillaje(cliente_id=cliente_id)
            session.add(config)

        config.plantilla_default_id = plantilla_default_id

        # Reemplazo total de las reglas (y sus condiciones vía cascade
        # delete-orphan). Se vacía la colección y se fuerza el flush para aplicar
        # el borrado antes de insertar las nuevas, evitando colisiones.
        config.reglas.clear()
        session.flush()

        for posicion, regla in enumerate(reglas):
            nueva = ReglaAsignacion(
                plantilla_destino_id=regla.plantilla_destino_id,
                orden=regla.orden if regla.orden is not None else posicion,
            )
            for c_pos, cond in enumerate(regla.condiciones):
                nueva.condiciones.append(
                    CondicionAsignacion(
                        atributo=cond.atributo,
                        valor=cond.valor,
                        orden=cond.orden if cond.orden is not None else c_pos,
                    )
                )
            config.reglas.append(nueva)

        session.flush()
        return config

    @staticmethod
    def delete_config(session, cliente_id: int) -> bool:
        """Elimina la configuración de un cliente (Decisión 4).

        Devuelve ``True`` si existía una configuración y se eliminó, ``False`` si
        el cliente no tenía configuración. El borrado arrastra las reglas
        asociadas vía `cascade="all, delete-orphan"`.
        """
        config = (
            session.query(ConfiguracionMultiplantillaje)
            .filter_by(cliente_id=cliente_id)
            .first()
        )
        if config is None:
            return False

        session.delete(config)
        return True

    @staticmethod
    def list_templates(session, cliente_id: int) -> list[Plantilla]:
        """Lista las plantillas del cliente para poblar el diálogo (Req 2.1).

        Devuelve exactamente las plantillas que pertenecen al cliente indicado,
        ordenadas por nombre para una presentación estable.
        """
        return (
            session.query(Plantilla)
            .filter_by(cliente_id=cliente_id)
            .order_by(Plantilla.nombre)
            .all()
        )

    @staticmethod
    def available_attributes(session, cliente_id: int) -> list[str]:
        """Construye los Atributos_Disponibles del cliente (Req 7.1, 7.2, 7.3).

        Combina en una única lista, sin duplicados, las claves de
        `Cliente.config["known_attributes"]` y las claves presentes en
        `Registro.datos` de los registros del cliente. La deduplicación es
        insensible a mayúsculas/minúsculas y a espacios circundantes (se usa
        `normalize` para comparar), conservando la primera clave original vista
        para mostrarla tal cual al usuario (Req 7.1).

        Solo se incluyen claves cuya longitud, tras recortar espacios
        circundantes, sea de 1 a 100 caracteres; se omiten las vacías (Req 7.2,
        7.3). Las claves de `known_attributes` tienen precedencia: las claves de
        `Registro.datos` ya presentes (comparadas de forma normalizada) se
        omiten (Req 7.3).
        """
        atributos: list[str] = []
        vistos: set[str] = set()

        def _agregar(clave: object) -> None:
            # Solo claves de texto; otras se ignoran de forma defensiva.
            if not isinstance(clave, str):
                return
            # Filtro de longitud sobre la clave recortada (Req 7.2, 7.3).
            if not (1 <= len(clave.strip()) <= 100):
                return
            normalizada = normalize(clave)
            if normalizada in vistos:
                return
            vistos.add(normalizada)
            # Se conserva la clave original (primera vista) para mostrar (Req 7.1).
            atributos.append(clave)

        # 1) Claves de `known_attributes` (precedencia, Req 7.2).
        cliente = (
            session.query(Cliente).filter_by(id=cliente_id).first()
        )
        if cliente is not None:
            known = (cliente.config or {}).get("known_attributes")
            if isinstance(known, dict):
                known = list(known.keys())
            if isinstance(known, (list, tuple)):
                for clave in known:
                    _agregar(clave)

        # 2) Claves presentes en `Registro.datos` no añadidas aún (Req 7.3).
        registros = (
            session.query(Registro).filter_by(cliente_id=cliente_id).all()
        )
        for registro in registros:
            datos = registro.datos or {}
            if not isinstance(datos, dict):
                continue
            for clave in datos.keys():
                _agregar(clave)

        return atributos
