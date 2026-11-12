"""
Estatus de los registros y reglas de los filtros del padrón.

El backend manda el estatus ya resuelto en ``credential_display_status`` y esa
es la fuente de verdad:

- ``pending``: foto y formulario listos, pero la credencial todavía no se
  manda a imprimir. Son las que faltan por imprimir — lo que aquí llamamos
  **pendiente**. No incluye ``printing``/``ready``/``delivered``, que ya
  pasaron por la impresora.
- ``sin_formulario`` / ``sin_fotografia``: falta ese dato del alumno.

Sobre la mezcla de filtros: los de estatus se **suman** (marcar «Pendientes» y
«Sin formulario» muestra los dos grupos). Es el caso de uso real: imprimir de
una vez las rezagadas —las que ya tienen formulario— junto con las que se
imprimirán solo con el QR, para que los datos aparezcan cuando el papá llene
el formulario y lo escanee. En cambio «Hermanos» e «Incidencias» no se
mezclan: son otra manera de mirar el padrón, así que al marcarlas se apaga lo
demás.
"""
from __future__ import annotations

from typing import Any, Iterable

# Valor de `credential_display_status` que el API usa para "lista para
# imprimir, aún no impresa".
DISPLAY_PENDIENTE = "pending"
DISPLAY_SIN_FORMULARIO = "sin_formulario"

# Filtros que se pueden marcar a la vez (se suman entre ellos).
FILTROS_ESTATUS: tuple[str, ...] = (
    "pendiente",
    "con_foto",
    "sin_foto",
    "con_formulario",
    "sin_formulario",
)

# Filtros que van solos: miran el padrón de otra forma, no por estatus.
FILTROS_EXCLUSIVOS: tuple[str, ...] = ("hermanos", "incidencias")


def _display(reg: Any) -> str:
    """``credential_display_status`` del registro, normalizado."""
    return str(reg.get_dato("credential_display_status", "") or "").strip()


def tiene_foto(reg: Any) -> bool:
    """Indica si el registro tiene fotografía."""
    return bool(getattr(reg, "photo_path", ""))


def tiene_formulario(reg: Any) -> bool:
    """Indica si el alumno completó su formulario (``form_status`` del API).

    Si el registro no trae el campo (sincronizaciones viejas), se infiere del
    ``credential_display_status``: el backend reporta "sin_formulario" con
    prioridad sobre cualquier otro estado.
    """
    val = reg.get_dato("form_status", None)
    if val is not None:
        return bool(val)
    return _display(reg) != DISPLAY_SIN_FORMULARIO


def es_pendiente(reg: Any) -> bool:
    """Indica si la credencial está lista para imprimir y aún no se imprime.

    Se cree lo que diga el backend. Si el registro no trae el estatus resuelto
    (clientes de Google Sheets, importaciones), se deduce: tiene foto y
    formulario, y no ha pasado por la impresora.
    """
    display = _display(reg)
    if display:
        return display == DISPLAY_PENDIENTE

    if not (tiene_foto(reg) and tiene_formulario(reg)):
        return False
    credencial = str(getattr(reg, "credential_status", "") or "").strip()
    if credencial and credencial != DISPLAY_PENDIENTE:
        return False  # printing, ready, delivered, replacement_requested…
    impresion = str(getattr(reg, "estado_impresion", "") or "").strip()
    return impresion in ("", "pendiente")


def alternar(seleccion: Iterable[str], clave: str) -> set[str]:
    """Nueva selección de filtros tras pulsar la pill ``clave``.

    - Un filtro de estatus se agrega o se quita, conservando los demás de
      estatus y apagando los exclusivos.
    - Un filtro exclusivo deja solo a ese (o limpia todo si ya estaba solo).

    Returns:
        El conjunto de filtros activos. Vacío significa «Todos».
    """
    actual = set(seleccion)

    if clave in FILTROS_EXCLUSIVOS:
        return set() if actual == {clave} else {clave}

    if clave not in FILTROS_ESTATUS:
        return set()  # clave desconocida (o «Todos»): sin filtro

    nueva = {c for c in actual if c in FILTROS_ESTATUS}
    if clave in nueva:
        nueva.discard(clave)
    else:
        nueva.add(clave)
    return nueva
