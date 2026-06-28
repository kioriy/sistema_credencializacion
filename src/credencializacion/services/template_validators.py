"""
Validadores puros para la configuración de multiplantillaje (Requisitos 3, 7, 8).

Este módulo agrupa funciones puras (sin Qt ni sesiones de BD) que validan las
reglas de asignación y detectan diferencias entre plantillas antes de guardar la
configuración. Operan sobre datos planos / DTOs y son por tanto deterministas y
testeables con property-based testing.

Funciones principales:
- `validate_atributo_length` / `validate_valor_length`: longitud tras recortar
  espacios (Req 3.1, 7.5 / Req 3.4).
- `detect_duplicate_pairs`: detecta pares `(atributo, valor)` duplicados de forma
  normalizada (Req 3.7).
- `validate_single_default`: exactamente una `Plantilla_Por_Defecto` perteneciente
  al cliente (Req 3.8).
- `validate_destino_same_client`: la plantilla destino pertenece al cliente en
  edición (Req 8.5).
- `detect_template_differences`: diferencia de orientación o dimensiones de lienzo
  entre las plantillas mapeadas (Req 8.7).

Se reutiliza `normalize` de `services.template_assignment` para que la
normalización de comparación sea idéntica a la del Motor_Asignacion.
"""
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from credencializacion.services.image_selection import normalize

# Límites de longitud por requisito (tras recortar espacios circundantes).
ATRIBUTO_MIN_LEN = 1
ATRIBUTO_MAX_LEN = 100   # Req 3.1, 7.5
VALOR_MIN_LEN = 1
VALOR_MAX_LEN = 255      # Req 3.4


@dataclass(frozen=True)
class ValidationResult:
    """Resultado de una validación pura.

    `ok` indica si la validación pasó; `errors` enumera los mensajes de error en
    el orden en que se detectaron (vacío cuando `ok` es ``True``).
    """
    ok: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class TemplateDifferenceResult:
    """Resultado de comparar plantillas mapeadas (Req 8.7).

    `has_difference` es ``True`` si al menos un par de plantillas difiere en
    orientación o en alguna dimensión de lienzo (ancho o alto). Las banderas
    `orientacion_difiere`, `ancho_difiere` y `alto_difiere` indican qué tipo de
    diferencia se detectó, y `message` describe la diferencia para mostrarla como
    advertencia previa al guardado.
    """
    has_difference: bool
    orientacion_difiere: bool = False
    ancho_difiere: bool = False
    alto_difiere: bool = False
    message: str | None = None


def _attr(obj: Any, name: str) -> Any:
    """Obtiene `name` de un objeto (atributo) o de un dict (clave) de forma uniforme.

    Permite que las funciones operen indistintamente sobre modelos SQLAlchemy,
    DTOs o diccionarios planos, sin acoplarse a un tipo concreto.
    """
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _trimmed_len(value: object) -> int:
    """Longitud del valor tras convertirlo a texto y recortar espacios.

    Los valores ``None`` se tratan como cadena vacía (longitud 0).
    """
    return len(str(value if value is not None else "").strip())


def validate_atributo_length(atributo: object) -> ValidationResult:
    """Valida que la longitud del atributo (recortado) esté en 1..100 (Req 3.1, 7.5)."""
    longitud = _trimmed_len(atributo)
    if ATRIBUTO_MIN_LEN <= longitud <= ATRIBUTO_MAX_LEN:
        return ValidationResult(ok=True)
    if longitud < ATRIBUTO_MIN_LEN:
        msg = "El nombre del atributo no puede estar vacío."
    else:
        msg = (
            f"El nombre del atributo no puede exceder {ATRIBUTO_MAX_LEN} "
            f"caracteres (tiene {longitud})."
        )
    return ValidationResult(ok=False, errors=(msg,))


def validate_valor_length(valor: object) -> ValidationResult:
    """Valida que la longitud del valor (recortado) esté en 1..255 (Req 3.4)."""
    longitud = _trimmed_len(valor)
    if VALOR_MIN_LEN <= longitud <= VALOR_MAX_LEN:
        return ValidationResult(ok=True)
    if longitud < VALOR_MIN_LEN:
        msg = "El valor de la regla no puede estar vacío."
    else:
        msg = (
            f"El valor de la regla no puede exceder {VALOR_MAX_LEN} "
            f"caracteres (tiene {longitud})."
        )
    return ValidationResult(ok=False, errors=(msg,))


def _condiciones_de_regla(regla: Any) -> list[Any]:
    """Devuelve la lista de condiciones de una regla, de forma flexible.

    Acepta:
    - `ReglaDTO`/objeto con atributo ``condiciones`` (lista de `CondicionDTO`).
    - dict con clave ``condiciones`` (lista de dicts/objetos).
    - Regla "simple" legada (con ``atributo``/``valor`` directos) o tupla/lista
      ``(atributo, valor, ...)``: se trata como una única condición.
    """
    if isinstance(regla, (tuple, list)):
        atributo = regla[0] if len(regla) > 0 else ""
        valor = regla[1] if len(regla) > 1 else ""
        return [{"atributo": atributo, "valor": valor}]

    condiciones = _attr(regla, "condiciones")
    if condiciones is not None:
        return list(condiciones)

    # Regla simple legada: atributo/valor directos como una sola condición.
    return [{"atributo": _attr(regla, "atributo"), "valor": _attr(regla, "valor")}]


def _condition_set(regla: Any) -> frozenset[tuple[str, str]]:
    """Conjunto normalizado de pares ``(atributo, valor)`` de las condiciones.

    Independiente del orden de las condiciones (Req 3.9): dos reglas con las
    mismas condiciones en distinto orden producen el mismo conjunto.
    """
    pares = set()
    for cond in _condiciones_de_regla(regla):
        pares.add((normalize(_attr(cond, "atributo")), normalize(_attr(cond, "valor"))))
    return frozenset(pares)


def validate_condiciones(regla: Any) -> ValidationResult:
    """Valida todas las condiciones de una regla (Req 3.1, 3.4, 3.6, 7.5).

    Rechaza si la regla no tiene condiciones, o si alguna condición tiene
    atributo o valor vacío o con longitud fuera de rango (atributo 1..100,
    valor 1..255). Agrega los mensajes de error de todas las condiciones
    inválidas en el orden detectado.
    """
    condiciones = _condiciones_de_regla(regla)
    if not condiciones:
        return ValidationResult(
            ok=False,
            errors=("La regla debe tener al menos una condición.",),
        )

    errores: list[str] = []
    for idx, cond in enumerate(condiciones, start=1):
        attr_res = validate_atributo_length(_attr(cond, "atributo"))
        if not attr_res.ok:
            errores.extend(f"Condición {idx}: {e}" for e in attr_res.errors)
        valor_res = validate_valor_length(_attr(cond, "valor"))
        if not valor_res.ok:
            errores.extend(f"Condición {idx}: {e}" for e in valor_res.errors)

    if errores:
        return ValidationResult(ok=False, errors=tuple(errores))
    return ValidationResult(ok=True)


def detect_duplicate_pairs(
    reglas: Sequence[Any],
) -> tuple[tuple[int, int], ...]:
    """Detecta reglas con el mismo **conjunto de condiciones** (Req 3.9).

    Compara cada regla con las anteriores por su conjunto normalizado de pares
    ``(atributo, valor)``, independiente del orden de las condiciones. Devuelve
    una tupla con los pares de índices ``(i, j)`` (``i < j``) cuyas reglas tienen
    el mismo conjunto de condiciones. Las reglas sin condiciones (conjunto vacío)
    se ignoran para no marcarlas como duplicadas entre sí (config parcial).
    """
    duplicados: list[tuple[int, int]] = []
    vistos: dict[frozenset[tuple[str, str]], int] = {}
    for idx, regla in enumerate(reglas):
        clave = _condition_set(regla)
        if not clave:
            # Regla sin condiciones (configuración parcial): no participa.
            continue
        if clave in vistos:
            duplicados.append((vistos[clave], idx))
        else:
            vistos[clave] = idx
    return tuple(duplicados)


def is_duplicate_condition_set(
    reglas: Sequence[Any],
    condiciones: Sequence[Any],
) -> bool:
    """Indica si el conjunto de condiciones candidato ya existe en `reglas`.

    Comparación normalizada e independiente del orden (Req 3.9). Útil al añadir
    una nueva regla en el diálogo: rechaza el conjunto antes de insertarlo.
    """
    candidato = _condition_set({"condiciones": list(condiciones)})
    if not candidato:
        return False
    return any(_condition_set(regla) == candidato for regla in reglas)


def validate_single_default(
    plantilla_default_id: int | None,
    plantilla_ids_cliente: Sequence[int] | frozenset[int] | set[int],
) -> ValidationResult:
    """Valida que exista exactamente una `Plantilla_Por_Defecto` válida (Req 3.8).

    Comprueba que `plantilla_default_id` esté definido (no ``None``) y que
    pertenezca al conjunto de plantillas del cliente. Devuelve un resultado con
    el mensaje correspondiente cuando falta el default o cuando referencia una
    plantilla ajena al cliente.
    """
    if plantilla_default_id is None:
        return ValidationResult(
            ok=False,
            errors=("Debe designar exactamente una plantilla por defecto.",),
        )
    if plantilla_default_id not in set(plantilla_ids_cliente):
        return ValidationResult(
            ok=False,
            errors=(
                "La plantilla por defecto debe pertenecer a las plantillas "
                "del cliente.",
            ),
        )
    return ValidationResult(ok=True)


def validate_destino_same_client(
    plantilla: Any,
    cliente_id: int,
) -> ValidationResult:
    """Valida que la plantilla destino pertenezca al cliente en edición (Req 8.5).

    `plantilla` puede ser un modelo `Plantilla`, un DTO o un dict con la clave
    ``cliente_id``. Si la plantilla no existe (``None``) o pertenece a otro
    cliente, la validación falla conservando un mensaje explicativo.
    """
    if plantilla is None:
        return ValidationResult(
            ok=False,
            errors=("La plantilla destino no existe.",),
        )
    plantilla_cliente_id = _attr(plantilla, "cliente_id")
    if plantilla_cliente_id != cliente_id:
        return ValidationResult(
            ok=False,
            errors=(
                "Solo se permiten plantillas del mismo cliente como destino.",
            ),
        )
    return ValidationResult(ok=True)


def detect_template_differences(
    plantillas: Sequence[Any],
) -> TemplateDifferenceResult:
    """Detecta diferencia de orientación o dimensiones entre plantillas (Req 8.7).

    Recorre las plantillas mapeadas y marca una diferencia si alguna difiere de
    la primera en `orientacion`, `ancho` o `alto`. La orientación se compara de
    forma normalizada (insensible a mayúsculas/espacios); el ancho y el alto se
    comparan como números. Con menos de dos plantillas no hay diferencia posible.

    Cada plantilla puede ser un modelo `Plantilla`, un DTO o un dict con las
    claves ``orientacion``, ``ancho`` y ``alto``.
    """
    if len(plantillas) < 2:
        return TemplateDifferenceResult(has_difference=False)

    primera = plantillas[0]
    orient_ref = normalize(_attr(primera, "orientacion"))
    ancho_ref = _attr(primera, "ancho")
    alto_ref = _attr(primera, "alto")

    orientacion_difiere = False
    ancho_difiere = False
    alto_difiere = False

    for plantilla in plantillas[1:]:
        if normalize(_attr(plantilla, "orientacion")) != orient_ref:
            orientacion_difiere = True
        if _attr(plantilla, "ancho") != ancho_ref:
            ancho_difiere = True
        if _attr(plantilla, "alto") != alto_ref:
            alto_difiere = True

    has_difference = orientacion_difiere or ancho_difiere or alto_difiere
    if not has_difference:
        return TemplateDifferenceResult(has_difference=False)

    partes: list[str] = []
    if orientacion_difiere:
        partes.append("orientación")
    if ancho_difiere:
        partes.append("ancho")
    if alto_difiere:
        partes.append("alto")
    message = (
        "Las plantillas seleccionadas difieren en " + ", ".join(partes) + "."
    )
    return TemplateDifferenceResult(
        has_difference=True,
        orientacion_difiere=orientacion_difiere,
        ancho_difiere=ancho_difiere,
        alto_difiere=alto_difiere,
        message=message,
    )
