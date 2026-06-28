"""
Motor de selección de imagen base para multiplantillaje por lado.

Dado un registro y la configuración de un (diseño, lado), elige qué imagen de
fondo usar según las condiciones de cada variante. Es una función PURA: no abre
sesiones de BD ni depende de Qt, por lo que es determinista y testeable con
property-based testing.

Modelo:
- Una `ConfigLadoDTO` tiene una `imagen_default_path` y N `VarianteDTO`.
- Cada `VarianteDTO` tiene una `imagen_path` y 1..N `CondicionDTO` en conjunción
  lógica (AND): la variante coincide solo si TODAS sus condiciones se cumplen.
- Gana la PRIMERA variante coincidente por orden; si ninguna coincide, se usa la
  imagen por defecto.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CondicionDTO:
    """Condición 'atributo igual a valor' de una variante (AND)."""
    atributo: str
    valor: str
    orden: int = 0


@dataclass(frozen=True)
class VarianteDTO:
    """Imagen de fondo candidata con sus condiciones en conjunción (AND).

    `condiciones` vacío `()` representa una variante sin condiciones, que nunca
    coincide (no puede satisfacer "todas sus condiciones" frente a un registro).
    """
    imagen_path: str
    orden: int
    condiciones: tuple[CondicionDTO, ...] = ()


@dataclass(frozen=True)
class ConfigLadoDTO:
    """Configuración de imágenes de fondo de un (diseño, lado)."""
    plantilla_id: int
    lado: str
    imagen_default_path: str | None
    variantes: tuple[VarianteDTO, ...]  # ya ordenadas por `orden`


def normalize(value: object) -> str:
    """Normaliza para comparación: ``str -> strip -> lower``.

    Convierte a texto, elimina espacios iniciales/finales y pasa a minúsculas,
    de modo que la comparación sea insensible a mayúsculas/minúsculas y a
    espacios circundantes. ``None`` se trata como cadena vacía.
    """
    return str(value if value is not None else "").strip().lower()


def _condicion_se_cumple(
    condicion: CondicionDTO,
    datos: dict[str, object],
    normalized_keys: dict[str, str],
) -> bool:
    """Indica si una condición se cumple para un registro.

    Si el registro no contiene el atributo, la condición no se cumple. En otro
    caso compara ``normalize(datos[atributo]) == normalize(valor)``.
    """
    original_key = normalized_keys.get(normalize(condicion.atributo))
    if original_key is None:
        return False
    return normalize(datos.get(original_key)) == normalize(condicion.valor)


def _variante_coincide(
    variante: VarianteDTO,
    datos: dict[str, object],
    normalized_keys: dict[str, str],
) -> bool:
    """Indica si TODAS las condiciones de la variante se cumplen (AND).

    Una variante sin condiciones nunca coincide.
    """
    if not variante.condiciones:
        return False
    return all(
        _condicion_se_cumple(c, datos, normalized_keys) for c in variante.condiciones
    )


def select_imagen(datos: dict[str, object], config: ConfigLadoDTO) -> str | None:
    """Elige la ruta de imagen de fondo para un registro y lado.

    Evalúa ``config.variantes`` en orden ascendente de ``orden``; gana la primera
    variante cuyas condiciones se cumplen todas (AND). Si ninguna coincide,
    devuelve ``config.imagen_default_path`` (que puede ser ``None``). Determinista.
    """
    datos = datos or {}
    normalized_keys = {normalize(k): k for k in datos.keys()}

    for variante in sorted(config.variantes, key=lambda v: v.orden):
        if _variante_coincide(variante, datos, normalized_keys):
            return variante.imagen_path

    return config.imagen_default_path
