"""
Estatus de los registros y reglas de los filtros del padrón.

El backend manda el estatus ya resuelto en ``credential_display_status`` y esa
es la fuente de verdad:

- ``pending``: foto y formulario listos, pero la credencial todavía no se
  manda a imprimir.
- ``sin_formulario`` / ``sin_fotografia``: falta ese dato del alumno.

Pero ese campo **tapa el avance real**: una credencial entregada en una
escuela que no exige formulario sigue llegando como ``sin_formulario``, así
que por ahí es imposible saber si ya se imprimió o se entregó. El ciclo de
vida va en ``credential_status`` (``pending`` → ``printing`` → ``ready`` →
``delivered``), que nunca se tapa, y es el que usan los filtros de etapa:

- **Por imprimir**: ``pending`` y con foto, tenga formulario o no. En las
  escuelas que no lo exigen, esas credenciales se imprimen solo con el QR.
- **Listas por entregar**: ``printing`` o ``ready``. Ya se imprimieron y
  todavía no se entregan.
- **Entregadas**: ``delivered``.

Las no entregadas son, entonces, las dos primeras juntas.

Sobre la mezcla de filtros: los de estatus se **suman**, así que «Por
imprimir» + «Listas por entregar» da todo lo que no se ha entregado, y «Por
imprimir» + «Sin formulario» arma la tanda donde conviven las rezagadas y las
que salen solo con el QR. En cambio «Hermanos» e «Incidencias» no se mezclan:
son otra manera de mirar el padrón, así que al marcarlas se apaga lo demás.
"""
from __future__ import annotations

from typing import Any, Iterable

# Valor de `credential_display_status` que el API usa para "lista para
# imprimir, aún no impresa".
DISPLAY_PENDIENTE = "pending"
DISPLAY_SIN_FORMULARIO = "sin_formulario"
DISPLAY_SIN_FOTOGRAFIA = "sin_fotografia"

# Etapas de `credential_status`.
ESTADO_PENDIENTE = "pending"
ESTADO_PRINTING = "printing"
ESTADO_READY = "ready"
ESTADO_ENTREGADA = "delivered"
ESTADO_REPOSICION = "replacement_requested"

# Etapas en las que el avance real manda sobre el estatus visible.
ETAPAS_AVANZADAS = (
    ESTADO_PRINTING, ESTADO_READY, ESTADO_ENTREGADA, ESTADO_REPOSICION,
)

# Filtros que se pueden marcar a la vez (se suman entre ellos).
FILTROS_ESTATUS: tuple[str, ...] = (
    "por_imprimir",
    "listas",
    "entregadas",
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


def etapa(reg: Any) -> str:
    """Etapa del ciclo de vida: ``credential_status`` normalizado.

    Si el registro no lo trae (clientes de Google Sheets, importaciones), se
    cae al estado de impresión local: lo ya impreso cuenta como ``ready``.
    """
    credencial = str(getattr(reg, "credential_status", "") or "").strip()
    if credencial:
        return credencial
    impresion = str(getattr(reg, "estado_impresion", "") or "").strip()
    return ESTADO_READY if impresion == "impreso" else ESTADO_PENDIENTE


def es_por_imprimir(reg: Any) -> bool:
    """Indica si falta imprimir la credencial y ya se puede.

    Pide foto —sin ella no hay credencial que imprimir— pero NO formulario:
    hay escuelas que no lo exigen y esas salen solo con el QR. Las
    reposiciones quedan fuera: tienen su propio flujo (botón Reposiciones).
    """
    return etapa(reg) == ESTADO_PENDIENTE and tiene_foto(reg)


def esta_lista_por_entregar(reg: Any) -> bool:
    """Indica si la credencial ya se imprimió y todavía no se entrega."""
    return etapa(reg) in (ESTADO_PRINTING, ESTADO_READY)


def esta_entregada(reg: Any) -> bool:
    """Indica si la credencial ya se entregó."""
    return etapa(reg) == ESTADO_ENTREGADA


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


def estado_visible(reg: Any) -> tuple[str, str]:
    """Estado a mostrar en la tabla: ``(etapa, nota)``.

    El ``credential_display_status`` sirve mientras la credencial no se ha
    impreso: ahí lo accionable es justo lo que falta (foto o formulario). En
    cuanto avanza, ese campo miente —sigue diciendo "sin_formulario" aunque ya
    esté entregada—, así que manda la etapa real y lo que falta pasa a ser una
    nota al lado.

    Returns:
        ``(etapa, nota)``; ``nota`` es ``""`` cuando no hay nada que aclarar.
    """
    display = _display(reg)
    actual = etapa(reg)

    if actual in ETAPAS_AVANZADAS:
        nota = ""
        if display == DISPLAY_SIN_FORMULARIO or not tiene_formulario(reg):
            nota = "sin formulario"
        elif display == DISPLAY_SIN_FOTOGRAFIA or not tiene_foto(reg):
            nota = "sin foto"
        return actual, nota

    return (display or actual), ""
