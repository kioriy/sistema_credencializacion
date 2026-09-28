"""
Reposiciones: qué tarjetas hay que reimprimir y con qué diseño.

La API de MiEscuela entrega dos clases de pendientes por escuela:

- **Alumno**: su credencial se repone (``credential_status ==
  "replacement_requested"``). Se imprime con la plantilla de alumno y su
  estatus se mueve con ``student_ids``.
- **Autorizado**: una tarjeta de autorizado oficial por imprimir, sea
  reposición (``request == "replacement"``) o credencial nueva fuera del kit
  (``request == "new"``). Se imprime con la plantilla del autorizado N (la N de
  ``autorizado_N_*``) y su estatus se mueve con ``authorized_person_ids``,
  NUNCA con el ``student_id``: el alumno puede tener ya su credencial entregada.

Una tarjeta de autorizado es de una persona dentro de una familia y cubre a
todos los hermanos que puede recoger, así que se deduplica por su código
(``authorized_code_ids``, p. ej. ``"A4029.4030"``).

Todo aquí es puro (sin BD ni UI) para poder probarlo aislado.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

TIPO_ALUMNO = "alumno"
TIPO_AUTORIZADO = "autorizado"

# Posiciones de autorizado con plantilla propia (Autorizado 1…4).
SLOTS_AUTORIZADO: tuple[int, ...] = (1, 2, 3, 4)

# Clave en ``Cliente.config`` con la plantilla elegida para cada tipo de
# tarjeta: {"alumno": id, "autorizado_1": id, ...}.
CONFIG_PLANTILLAS = "plantillas_reposicion"

SOLICITUD_LABEL = {
    "replacement": "Reposición",
    "new": "Nueva",
}

_RE_SLOT_CAMPO = re.compile(r"^autorizado_(\d+)_(\w+)$")


@dataclass(frozen=True)
class Tarjeta:
    """Una credencial por imprimir en una cola de reposiciones.

    ``enrollment_code`` identifica el registro local del alumno (el de la
    tarjeta de alumno, o el alumno por el que llegó el autorizado).
    """

    tipo: str
    enrollment_code: str
    student_id: int | None
    alumno_nombre: str
    slot: int | None = None
    authorized_person_id: int | None = None
    codigo: str = ""
    solicitud: str = "replacement"
    solicitada_en: str | None = None
    nombre: str = ""

    @property
    def clave_plantilla(self) -> str:
        """Clave del tipo de tarjeta en el mapa de plantillas."""
        if self.tipo == TIPO_ALUMNO:
            return TIPO_ALUMNO
        return f"autorizado_{self.slot}"

    @property
    def etiqueta(self) -> str:
        """Texto corto para la cola: ``Alumno`` / ``Autorizado 2 · Nueva``."""
        if self.tipo == TIPO_ALUMNO:
            return "Alumno · Reposición"
        return (
            f"Autorizado {self.slot} · "
            f"{SOLICITUD_LABEL.get(self.solicitud, self.solicitud)}"
        )


def _int(valor: Any) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def tarjetas_de_alumnos(registros: Iterable[dict]) -> list[Tarjeta]:
    """Tarjetas de alumno a partir del export ``replacement_requested``.

    Se vuelve a comprobar el estatus por si la API devolviera algo más.
    """
    tarjetas: list[Tarjeta] = []
    for rec in registros:
        if rec.get("estado_credencial") != "replacement_requested":
            continue
        tarjetas.append(Tarjeta(
            tipo=TIPO_ALUMNO,
            enrollment_code=str(rec.get("enrollment_code", "") or ""),
            student_id=_int(rec.get("student_id")),
            alumno_nombre=str(rec.get("nombre_completo", "") or ""),
            nombre=str(rec.get("nombre_completo", "") or ""),
        ))
    return tarjetas


def tarjetas_de_autorizados(registros: Iterable[dict]) -> list[Tarjeta]:
    """Tarjetas de autorizado a partir del export ``authorized_requests``.

    Toma solo los autorizados con ``request`` y los deduplica por código: si
    la persona aparece en dos hermanos, sale una sola tarjeta (la del primer
    alumno en que aparece). Ordena por fecha de solicitud (las más antiguas
    primero; sin fecha al final) para que la cola siga el orden de llegada.
    """
    vistas: set[str] = set()
    tarjetas: list[Tarjeta] = []
    for rec in registros:
        for est in rec.get("autorizados_estatus") or []:
            if not isinstance(est, dict) or not est.get("request"):
                continue
            slot = _int(est.get("slot"))
            person_id = _int(est.get("person_id"))
            if slot is None or person_id is None:
                continue
            codigo = str(est.get("codigo") or f"A{person_id}")
            if codigo in vistas:
                continue
            vistas.add(codigo)
            tarjetas.append(Tarjeta(
                tipo=TIPO_AUTORIZADO,
                enrollment_code=str(rec.get("enrollment_code", "") or ""),
                student_id=_int(rec.get("student_id")),
                alumno_nombre=str(rec.get("nombre_completo", "") or ""),
                slot=slot,
                authorized_person_id=person_id,
                codigo=codigo,
                solicitud=str(est.get("request")),
                solicitada_en=est.get("requested_at"),
                nombre=str(rec.get(f"autorizado_{slot}_nombre", "") or ""),
            ))
    tarjetas.sort(key=lambda t: (t.solicitada_en is None, t.solicitada_en or ""))
    return tarjetas


def resolver_plantillas(
    plantillas: Iterable[tuple[int, str]],
    configuradas: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Plantilla para cada tipo de tarjeta de una escuela.

    Gana lo configurado en el cliente (si la plantilla aún existe). Lo que
    falte se detecta por nombre: ``Alumno`` y ``Autorizado N`` (sin distinguir
    mayúsculas ni espacios de más).

    Returns:
        ``{"alumno": id, "autorizado_1": id, ...}`` solo con lo encontrado.
    """
    lista = list(plantillas)
    existentes = {pid for pid, _ in lista}
    resultado: dict[str, int] = {}

    for clave, pid in (configuradas or {}).items():
        pid = _int(pid)
        if pid in existentes:
            resultado[clave] = pid

    por_nombre = {" ".join(nombre.lower().split()): pid for pid, nombre in lista}
    candidatos = {TIPO_ALUMNO: "alumno"}
    for n in SLOTS_AUTORIZADO:
        candidatos[f"autorizado_{n}"] = f"autorizado {n}"
    for clave, nombre in candidatos.items():
        if clave not in resultado and nombre in por_nombre:
            resultado[clave] = por_nombre[nombre]
    return resultado


def slot_de_plantilla(elementos: Iterable[dict]) -> int | None:
    """La N de autorizado que usa un diseño, si usa exactamente una.

    Un diseño de "Autorizado 2" liga sus campos a ``autorizado_2_*``. Si usa
    varias N (p. ej. el reverso de una credencial de alumno que lista a todos
    sus autorizados) o ninguna, devuelve ``None``.
    """
    slots: set[int] = set()
    for elem in elementos:
        if not isinstance(elem, dict):
            continue
        m = _RE_SLOT_CAMPO.match(str(elem.get("campo_dato", "") or ""))
        if m:
            slots.add(int(m.group(1)))
    return slots.pop() if len(slots) == 1 else None


def slot_actual(datos: dict, person_id: int) -> int | None:
    """Posición que hoy ocupa el autorizado ``person_id`` en el registro."""
    for est in (datos or {}).get("autorizados_estatus") or []:
        if isinstance(est, dict) and _int(est.get("person_id")) == person_id:
            return _int(est.get("slot"))
    return None


def extras_remapeo(datos: dict, slot_plantilla: int | None, person_id: int | None) -> dict:
    """Atributos para que el diseño del slot N muestre a la persona correcta.

    El diseño está ligado a ``autorizado_N_*``, pero la persona puede ocupar
    otra posición: porque la API reordenó a los autorizados desde que se creó
    la cola, o porque su posición no tiene diseño propio y se usa el de otra.
    Copia los ``autorizado_K_*`` de la persona sobre los ``autorizado_N_*``
    (los extras tienen prioridad sobre los datos al renderizar).

    Devuelve ``{}`` si no hace falta o no se puede (persona ya no está).
    """
    if slot_plantilla is None or person_id is None:
        return {}
    actual = slot_actual(datos, person_id)
    if actual is None or actual == slot_plantilla:
        return {}
    prefijo = f"autorizado_{actual}_"
    destino = f"autorizado_{slot_plantilla}_"
    return {
        destino + clave[len(prefijo):]: "" if valor is None else str(valor)
        for clave, valor in (datos or {}).items()
        if isinstance(clave, str) and clave.startswith(prefijo)
    }


def separar_ids(items: Iterable[Any]) -> tuple[list[int], list[int]]:
    """Separa los ids a mandar a ``bulk-mark-*`` según el tipo de tarjeta.

    Cada ítem expone ``tipo_item``, ``authorized_person_id`` y ``datos`` (o
    un ``registro`` con ``datos``). Las tarjetas de alumno aportan su
    ``student_id``; las de autorizado solo su ``authorized_person_id``.

    Returns:
        ``(student_ids, authorized_person_ids)`` sin duplicados.
    """
    alumnos: list[int] = []
    autorizados: list[int] = []
    for it in items:
        tipo = getattr(it, "tipo_item", None) or TIPO_ALUMNO
        if tipo == TIPO_AUTORIZADO:
            pid = _int(getattr(it, "authorized_person_id", None))
            if pid is not None and pid not in autorizados:
                autorizados.append(pid)
            continue
        datos = getattr(it, "datos", None)
        if datos is None:
            reg = getattr(it, "registro", None)
            datos = getattr(reg, "datos", None) if reg is not None else None
        sid = _int((datos or {}).get("student_id"))
        if sid is not None and sid not in alumnos:
            alumnos.append(sid)
    return alumnos, autorizados
