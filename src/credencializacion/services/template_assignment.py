"""
Motor de asignación de plantillas (multiplantillaje base).

Este módulo define los DTOs inmutables de transporte que el repositorio
entrega al Motor_Asignacion para que la evaluación de reglas sea pura,
determinista y testeable sin necesidad de una sesión de base de datos.

Los DTOs son `@dataclass(frozen=True)`:
- ReglaDTO: una regla "atributo igual a valor → Plantilla_Destino".
- ConfigDTO: configuración completa de un cliente, con reglas ya ordenadas
  por precedencia y el conjunto de plantillas vigentes.
- AssignmentResult: resultado tipado de resolver la plantilla de un registro.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class CondicionDTO:
    """Condición 'atributo igual a valor' de una regla (Req 3.1).

    Una `ReglaDTO` coincide solo si TODAS sus condiciones se cumplen (AND).
    """
    atributo: str
    valor: str
    orden: int = 0


@dataclass(frozen=True)
class ReglaDTO:
    """Regla con destino, compuesta por una o más condiciones en AND (Req 3.1).

    `condiciones` es una tupla de `CondicionDTO` que deben cumplirse todas para
    que la regla coincida. Una tupla vacía `()` modela una plantilla seleccionada
    sin condiciones (configuración parcial, Req 9.3): se persiste y conserva,
    pero nunca coincide.
    """
    plantilla_destino_id: int
    orden: int
    condiciones: tuple[CondicionDTO, ...] = ()


@dataclass(frozen=True)
class ConfigDTO:
    """Configuración de multiplantillaje de un cliente para transporte.

    `reglas` se entrega ya ordenada por `orden` (precedencia, Req 5.4) y
    `plantillas_existentes` contiene los ids de las plantillas vigentes del
    cliente, para detectar destinos inexistentes (Req 8.6).
    """
    cliente_id: int
    plantilla_default_id: int | None
    reglas: tuple[ReglaDTO, ...]           # ya ordenadas por `orden`
    plantillas_existentes: frozenset[int]  # ids de plantillas vigentes del cliente


@dataclass(frozen=True)
class AssignmentResult:
    """Resultado tipado de resolver la plantilla de un registro.

    `status` describe el desenlace de la evaluación:
    "matched" | "default" | "fallback_cola" | "error" | "warning_missing".
    `rule_index` es el índice de la regla coincidente cuando aplica.
    `message` es el texto de error/advertencia para logging (identifica el registro).
    """
    plantilla_id: int | None
    status: str
    rule_index: int | None
    message: str | None


# Claves candidatas para identificar de forma única al registro en los
# mensajes de logging, sin volcar todo el contenido de `datos` (evita ruido y
# posible PII). Se buscan de forma insensible a mayúsculas/espacios.
_IDENTIFIER_KEYS: tuple[str, ...] = ("id", "enrollment_code", "nombre_completo")


def normalize(value: object) -> str:
    """Normaliza un valor para comparación: ``str -> strip -> lower``.

    Convierte a texto, elimina espacios iniciales/finales y pasa a minúsculas,
    de modo que la comparación del Motor_Asignacion sea insensible a
    mayúsculas/minúsculas y a espacios circundantes (Req 5.2, 8.8). Los valores
    ``None`` se tratan como cadena vacía.
    """
    return str(value if value is not None else "").strip().lower()


def _describe_registro(datos: dict[str, object]) -> str:
    """Construye un descriptor breve que identifique al registro para logging.

    Toma únicamente las claves identificadoras conocidas (id, enrollment_code,
    nombre_completo) si están presentes, sin volcar todo `datos` para evitar
    ruido y posible PII en los logs (ver sección 'Logging' del diseño).
    """
    if not isinstance(datos, dict):
        return "registro=<sin datos>"

    # Mapa normalizado clave->clave original para búsqueda insensible.
    normalized = {normalize(k): k for k in datos.keys()}
    partes: list[str] = []
    for ident in _IDENTIFIER_KEYS:
        original_key = normalized.get(ident)
        if original_key is not None:
            valor = datos.get(original_key)
            if valor is not None and str(valor).strip() != "":
                partes.append(f"{ident}={valor}")

    if partes:
        return "registro(" + ", ".join(partes) + ")"
    return "registro=<sin identificador>"


def _condicion_se_cumple(
    condicion: CondicionDTO,
    datos: dict[str, object],
    normalized_keys: dict[str, str],
) -> bool:
    """Indica si una condición se cumple para un registro (Req 5.2, 8.1, 8.8).

    El atributo se busca de forma insensible a mayúsculas/espacios. Si el
    registro no contiene el atributo, la condición no se cumple (Req 8.1). En
    otro caso se compara ``normalize(datos[atributo]) == normalize(valor)``.
    """
    original_key = normalized_keys.get(normalize(condicion.atributo))
    if original_key is None:
        return False
    return normalize(datos.get(original_key)) == normalize(condicion.valor)


def _regla_coincide(
    regla: ReglaDTO,
    datos: dict[str, object],
    normalized_keys: dict[str, str],
) -> bool:
    """Indica si TODAS las condiciones de la regla se cumplen (conjunción AND).

    Una regla sin condiciones nunca coincide (Req 9.3): no puede satisfacer
    "todas sus condiciones" frente a un registro arbitrario.
    """
    if not regla.condiciones:
        return False
    return all(
        _condicion_se_cumple(c, datos, normalized_keys) for c in regla.condiciones
    )


def _describe_regla(idx: int, regla: ReglaDTO) -> str:
    """Descriptor textual de una regla (sus condiciones en AND) para logging."""
    if regla.condiciones:
        partes = " Y ".join(
            f"'{c.atributo}' = '{c.valor}'" for c in regla.condiciones
        )
    else:
        partes = "(sin condiciones)"
    return f"Regla #{idx} ({partes})"


def resolve_template(
    datos: dict[str, object],
    config: ConfigDTO,
    plantilla_cola_id: int | None,
) -> AssignmentResult:
    """Resuelve la plantilla base para un registro evaluando las reglas.

    Orden de evaluación (Req 5.1, 5.5):
      1. Recorre ``config.reglas`` en orden ascendente de ``orden``.
      2. Una regla COINCIDE solo si TODAS sus condiciones se cumplen (AND,
         Req 5.2): para cada condición, si el registro no contiene su atributo
         la condición no se cumple (Req 8.1) y la regla no coincide (Req 5.3);
         en otro caso se compara ``normalize(datos[atributo]) == normalize(valor)``
         (Req 5.2/8.8). Una regla sin condiciones nunca coincide (Req 9.3).
      3. La primera regla coincidente con destino vigente gana
         (``status="matched"``, Req 5.5).
      4. Si la plantilla destino de la regla coincidente no está en
         ``config.plantillas_existentes``, se trata como no coincidente y se
         registra una advertencia que identifica la regla (Req 8.6); se sigue
         buscando y, de no haber otra coincidencia, se cae al default.
      5. Sin coincidencias con destino vigente:
           - default definido y existente -> ``status="default"`` (Req 5.4/8.2),
             o ``status="warning_missing"`` si la caída a default se debió a una
             regla con destino inexistente (Req 8.6).
           - sin default usable y con ``plantilla_cola_id`` -> ``status="fallback_cola"``
             con advertencia que identifica el registro (Req 8.3).
           - sin default usable y sin ``plantilla_cola_id`` -> ``status="error"``,
             ``plantilla_id=None``, con error que identifica el registro
             (Req 5.9/8.4). Los datos del registro no se modifican.
    """
    datos = datos or {}
    registro_desc = _describe_registro(datos)

    # Recorre en orden ascendente de precedencia. El DTO ya entrega las reglas
    # ordenadas, pero se ordena de forma defensiva para garantizar la precedencia.
    reglas_ordenadas = sorted(config.reglas, key=lambda r: r.orden)

    # Búsqueda insensible del atributo en los datos del registro.
    normalized_keys = {normalize(k): k for k in datos.keys()}

    missing_rule_index: int | None = None
    missing_rule: ReglaDTO | None = None

    for idx, regla in enumerate(reglas_ordenadas):
        if not _regla_coincide(regla, datos, normalized_keys):
            continue

        # Todas las condiciones se cumplen (AND).
        if regla.plantilla_destino_id in config.plantillas_existentes:
            return AssignmentResult(
                plantilla_id=regla.plantilla_destino_id,
                status="matched",
                rule_index=idx,
                message=None,
            )

        # Destino inexistente: tratar como no coincidente y registrar advertencia
        # (Req 8.6). Se conserva la primera regla afectada para el mensaje.
        if missing_rule_index is None:
            missing_rule_index = idx
            missing_rule = regla
        # Continúa buscando una regla posterior con destino vigente.

    # Sin coincidencias con destino vigente: resolver el fallback.
    default_usable = (
        config.plantilla_default_id is not None
        and config.plantilla_default_id in config.plantillas_existentes
    )

    if default_usable:
        if missing_rule is not None:
            message = (
                f"{_describe_regla(missing_rule_index, missing_rule)} referencia "
                f"una plantilla destino inexistente "
                f"(plantilla_destino_id={missing_rule.plantilla_destino_id}); "
                f"se asigna la plantilla por defecto al {registro_desc}."
            )
            return AssignmentResult(
                plantilla_id=config.plantilla_default_id,
                status="warning_missing",
                rule_index=missing_rule_index,
                message=message,
            )
        return AssignmentResult(
            plantilla_id=config.plantilla_default_id,
            status="default",
            rule_index=None,
            message=None,
        )

    # Sin default usable: intentar la plantilla seleccionada en la cola (Req 8.3).
    if plantilla_cola_id is not None:
        message = (
            f"Ninguna regla coincide y no hay plantilla por defecto usable para el "
            f"{registro_desc}; se asigna la plantilla de la cola "
            f"(plantilla_cola_id={plantilla_cola_id})."
        )
        return AssignmentResult(
            plantilla_id=plantilla_cola_id,
            status="fallback_cola",
            rule_index=None,
            message=message,
        )

    # Sin default ni plantilla de cola: error, registro sin plantilla (Req 5.8/8.4).
    message = (
        f"No se pudo asignar plantilla al {registro_desc}: ninguna regla coincide, "
        f"sin plantilla por defecto ni plantilla de cola. El registro se omitirá."
    )
    return AssignmentResult(
        plantilla_id=None,
        status="error",
        rule_index=None,
        message=message,
    )
