"""
Reconciliación de configuraciones contra el diccionario de atributos vigente.

Reescribe las referencias guardadas —``campo_dato`` de los elementos, las
``{claves}`` de los textos compuestos y el atributo de las condiciones de
multiplantillaje— para que apunten al nombre canónico en lugar de a una de sus
definiciones.

**No es una migración de versión.** No existe un mapa fijo "en la versión X
convierte ``address`` en ``domicilio``": el plan se deriva del estado ACTUAL del
diccionario, cada vez que se ejecuta. Por eso sirve igual hoy, en una instalación
que ya lleva meses en producción con sus propias plantillas, y dentro de un año
con definiciones que todavía no existen. Es idempotente: volver a ejecutarla
sobre una base ya reconciliada no produce cambios.

Aplicarla es **opcional**: gracias a que ``clave_real`` resuelve también en
sentido inverso, una plantilla que apunta a ``address`` sigue imprimiendo bien
sin reconciliar. Lo que aporta es higiene —una sola forma de nombrar cada dato—
y que el diseñador muestre esos elementos con su etiqueta correcta.
"""
from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from credencializacion.services.diccionario import (
    Indice,
    es_familia,
    normalizar,
    obtener_indice,
)

logger = logging.getLogger(__name__)

_RE_CLAVE_COMPUESTA = re.compile(r"\{(\w+)\}")
_RE_SLOT_HERMANO = re.compile(r"^(.+)_hermano_(\d+)$")

# Valores de `campo_dato` que no son atributos sino marcas de tipo del propio
# editor. Ni se reescriben ni cuentan como referencias sin clasificar.
_CENTINELAS: frozenset[str] = frozenset({"composite"})


# ── Plan ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CambioElemento:
    """Un ``campo_dato`` (o una clave de texto compuesto) que se reescribirá."""
    plantilla_id: int
    plantilla_nombre: str
    lado: str                 # "frente" | "vuelta"
    indice: int               # posición del elemento en la lista
    etiqueta: str             # nombre legible del elemento
    origen: str               # "campo_dato" | "texto_compuesto"
    actual: str
    nuevo: str


@dataclass(frozen=True)
class CambioCondicion:
    """El atributo de una condición de multiplantillaje que se reescribirá."""
    condicion_id: int
    plantilla_id: int
    plantilla_nombre: str
    lado: str
    actual: str
    nuevo: str
    valor: str


@dataclass(frozen=True)
class Huerfano:
    """Referencia a una clave que el diccionario no reconoce.

    No se toca: solo se reporta. El usuario decide si esa clave pertenece a un
    atributo (la agrega como definición desde Configuración y vuelve a
    ejecutar) o si el elemento quedó apuntando a un dato que ya no existe.
    """
    donde: str                # "plantilla" | "condicion"
    referencia: str           # nombre legible del sitio
    clave: str


@dataclass
class Plan:
    """Resultado de un análisis en seco: qué cambiaría, sin haber cambiado nada."""
    cambios_elemento: list[CambioElemento] = field(default_factory=list)
    cambios_condicion: list[CambioCondicion] = field(default_factory=list)
    huerfanos: list[Huerfano] = field(default_factory=list)
    _huerfanos_vistos: set[tuple[str, str, str]] = field(
        default_factory=set, repr=False,
    )

    def agregar_huerfano(self, huerfano: Huerfano) -> None:
        """Registra un huérfano evitando repetir la misma clave en un sitio."""
        marca = (huerfano.donde, huerfano.referencia, normalizar(huerfano.clave))
        if marca in self._huerfanos_vistos:
            return
        self._huerfanos_vistos.add(marca)
        self.huerfanos.append(huerfano)

    @property
    def total_cambios(self) -> int:
        return len(self.cambios_elemento) + len(self.cambios_condicion)

    @property
    def vacio(self) -> bool:
        return self.total_cambios == 0

    def resumen(self) -> str:
        """Frase corta para el indicador de estado en Configuración."""
        if self.vacio and not self.huerfanos:
            return "Todas las plantillas usan los nombres canónicos."
        partes: list[str] = []
        if self.cambios_elemento:
            plantillas = {c.plantilla_id for c in self.cambios_elemento}
            partes.append(
                f"{len(self.cambios_elemento)} elemento(s) en "
                f"{len(plantillas)} plantilla(s)"
            )
        if self.cambios_condicion:
            partes.append(f"{len(self.cambios_condicion)} condición(es)")
        if self.huerfanos:
            partes.append(f"{len(self.huerfanos)} referencia(s) sin clasificar")
        return "Por reconciliar: " + ", ".join(partes)


# ── Resolución de una referencia ─────────────────────────────────────────

def _canonizar(clave: object, indice: Indice) -> tuple[str | None, bool]:
    """Nombre canónico de una referencia guardada, respetando los slots.

    Devuelve ``(nuevo_nombre_o_None, es_conocida)``. ``None`` significa que no
    hay nada que reescribir (ya es canónica o no se reconoce).

    Los atributos de hermano (``photo_url_hermano_2``) se descomponen: se
    canoniza la base y se vuelve a colgar el sufijo del slot. El sufijo se
    reconoce por forma, no contra la lista de bases válidas del editor: así un
    slot cuya base quedó escrita con una definición vieja también se corrige.
    """
    texto = str(clave or "").strip()
    if not texto:
        return None, True
    if normalizar(texto) in _CENTINELAS or es_familia(texto):
        return None, True

    slot = _RE_SLOT_HERMANO.match(texto)
    base = slot.group(1) if slot else texto

    canonico = indice.canonico_de(base)
    if canonico is None:
        return None, False
    if normalizar(canonico) == normalizar(base):
        return None, True

    nuevo = f"{canonico}_hermano_{slot.group(2)}" if slot else canonico
    return nuevo, True


def _etiqueta_elemento(elem: dict) -> str:
    props = elem.get("properties", {}) or {}
    etiqueta = str(props.get("label", "") or "").strip()
    if etiqueta:
        return etiqueta
    campo = str(elem.get("campo_dato", "") or "").strip()
    return campo or str(elem.get("type", "elemento"))


# ── Análisis en seco ─────────────────────────────────────────────────────

def planificar(session, indice: Indice | None = None) -> Plan:
    """Analiza la base y devuelve qué se reescribiría. No modifica nada."""
    from credencializacion.db.models import (
        CondicionVariante,
        ConfiguracionLado,
        Plantilla,
        VarianteImagen,
    )

    idx = indice if indice is not None else obtener_indice(session)
    plan = Plan()

    for plantilla in session.query(Plantilla).order_by(Plantilla.id).all():
        for lado, elementos in (
            ("frente", plantilla.elementos_frente or []),
            ("vuelta", plantilla.elementos_vuelta or []),
        ):
            for i, elem in enumerate(elementos):
                if not isinstance(elem, dict):
                    continue
                etiqueta = _etiqueta_elemento(elem)

                campo = str(elem.get("campo_dato", "") or "").strip()
                if campo:
                    nuevo, conocida = _canonizar(campo, idx)
                    if nuevo:
                        plan.cambios_elemento.append(
                            CambioElemento(
                                plantilla_id=plantilla.id,
                                plantilla_nombre=plantilla.nombre,
                                lado=lado, indice=i, etiqueta=etiqueta,
                                origen="campo_dato", actual=campo, nuevo=nuevo,
                            )
                        )
                    elif not conocida:
                        plan.agregar_huerfano(
                            Huerfano(
                                donde="plantilla",
                                referencia=f"{plantilla.nombre} · {lado} · {etiqueta}",
                                clave=campo,
                            )
                        )

                props = elem.get("properties", {}) or {}
                plantilla_txt = str(props.get("composite_template", "") or "")
                for clave in _RE_CLAVE_COMPUESTA.findall(plantilla_txt):
                    nuevo, conocida = _canonizar(clave, idx)
                    if nuevo:
                        plan.cambios_elemento.append(
                            CambioElemento(
                                plantilla_id=plantilla.id,
                                plantilla_nombre=plantilla.nombre,
                                lado=lado, indice=i, etiqueta=etiqueta,
                                origen="texto_compuesto",
                                actual=clave, nuevo=nuevo,
                            )
                        )
                    elif not conocida:
                        plan.agregar_huerfano(
                            Huerfano(
                                donde="plantilla",
                                referencia=f"{plantilla.nombre} · {lado} · {etiqueta}",
                                clave=clave,
                            )
                        )

    condiciones = (
        session.query(
            CondicionVariante, ConfiguracionLado.plantilla_id,
            ConfiguracionLado.lado, Plantilla.nombre,
        )
        .join(VarianteImagen, CondicionVariante.variante_id == VarianteImagen.id)
        .join(
            ConfiguracionLado,
            VarianteImagen.configuracion_id == ConfiguracionLado.id,
        )
        .join(Plantilla, ConfiguracionLado.plantilla_id == Plantilla.id)
        .order_by(CondicionVariante.id)
        .all()
    )
    for condicion, plantilla_id, lado, plantilla_nombre in condiciones:
        nuevo, conocida = _canonizar(condicion.atributo, idx)
        if nuevo:
            plan.cambios_condicion.append(
                CambioCondicion(
                    condicion_id=condicion.id,
                    plantilla_id=plantilla_id,
                    plantilla_nombre=plantilla_nombre,
                    lado=lado,
                    actual=condicion.atributo,
                    nuevo=nuevo,
                    valor=condicion.valor,
                )
            )
        elif not conocida:
            plan.agregar_huerfano(
                Huerfano(
                    donde="condicion",
                    referencia=f"{plantilla_nombre} · {lado} · fondo condicional",
                    clave=condicion.atributo,
                )
            )

    return plan


# ── Aplicación ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Resultado:
    """Qué se aplicó y con qué respaldo puede revertirse."""
    respaldo_id: int | None
    elementos: int
    condiciones: int


def aplicar(session, plan: Plan, descripcion: str = "") -> Resultado:
    """Aplica el plan en una sola transacción, dejando respaldo para deshacer.

    El respaldo guarda el estado ANTERIOR completo de cada plantilla y condición
    tocada, de modo que revertir no dependa de poder invertir el plan.
    """
    from credencializacion.db.models import (
        CondicionVariante,
        Plantilla,
        RespaldoReconciliacion,
    )

    if plan.vacio:
        return Resultado(respaldo_id=None, elementos=0, condiciones=0)

    ids_plantilla = {c.plantilla_id for c in plan.cambios_elemento}
    ids_condicion = {c.condicion_id for c in plan.cambios_condicion}

    plantillas = {
        p.id: p
        for p in session.query(Plantilla).filter(Plantilla.id.in_(ids_plantilla)).all()
    } if ids_plantilla else {}
    condiciones = {
        c.id: c
        for c in session.query(CondicionVariante)
        .filter(CondicionVariante.id.in_(ids_condicion))
        .all()
    } if ids_condicion else {}

    payload: dict[str, Any] = {
        "plantillas": [
            {
                "id": p.id,
                "elementos_frente": copy.deepcopy(p.elementos_frente or []),
                "elementos_vuelta": copy.deepcopy(p.elementos_vuelta or []),
            }
            for p in plantillas.values()
        ],
        "condiciones": [
            {"id": c.id, "atributo": c.atributo}
            for c in condiciones.values()
        ],
    }

    # Copias de trabajo: las columnas JSON solo se marcan como modificadas si se
    # les reasigna una lista nueva, no si se mutan en el sitio.
    trabajo: dict[int, dict[str, list]] = {
        pid: {
            "frente": copy.deepcopy(p.elementos_frente or []),
            "vuelta": copy.deepcopy(p.elementos_vuelta or []),
        }
        for pid, p in plantillas.items()
    }

    aplicados_elemento = 0
    for cambio in plan.cambios_elemento:
        elementos = trabajo.get(cambio.plantilla_id, {}).get(cambio.lado)
        if not elementos or cambio.indice >= len(elementos):
            continue
        elem = elementos[cambio.indice]
        if not isinstance(elem, dict):
            continue

        if cambio.origen == "campo_dato":
            if str(elem.get("campo_dato", "") or "").strip() != cambio.actual:
                continue
            elem["campo_dato"] = cambio.nuevo
            aplicados_elemento += 1
        else:
            props = elem.get("properties")
            if not isinstance(props, dict):
                continue
            texto = str(props.get("composite_template", "") or "")
            nuevo_texto = re.sub(
                r"\{" + re.escape(cambio.actual) + r"\}",
                "{" + cambio.nuevo + "}",
                texto,
            )
            if nuevo_texto == texto:
                continue
            props["composite_template"] = nuevo_texto
            aplicados_elemento += 1

    for pid, caras in trabajo.items():
        plantillas[pid].elementos_frente = caras["frente"]
        plantillas[pid].elementos_vuelta = caras["vuelta"]

    aplicados_condicion = 0
    for cambio in plan.cambios_condicion:
        condicion = condiciones.get(cambio.condicion_id)
        if condicion is None or condicion.atributo != cambio.actual:
            continue
        condicion.atributo = cambio.nuevo
        aplicados_condicion += 1

    respaldo = RespaldoReconciliacion(
        descripcion=descripcion or (
            f"{aplicados_elemento} elemento(s), "
            f"{aplicados_condicion} condición(es)"
        ),
        payload=payload,
    )
    session.add(respaldo)
    session.flush()

    logger.info(
        "Reconciliación aplicada: %d elementos, %d condiciones (respaldo %s).",
        aplicados_elemento, aplicados_condicion, respaldo.id,
    )
    return Resultado(
        respaldo_id=respaldo.id,
        elementos=aplicados_elemento,
        condiciones=aplicados_condicion,
    )


def deshacer(session, respaldo_id: int) -> bool:
    """Restaura el estado guardado en un respaldo. Devuelve si hubo cambios."""
    from credencializacion.db.models import (
        CondicionVariante,
        Plantilla,
        RespaldoReconciliacion,
    )

    respaldo = session.get(RespaldoReconciliacion, respaldo_id)
    if respaldo is None or respaldo.revertido:
        return False

    payload = respaldo.payload or {}
    for fila in payload.get("plantillas", []):
        plantilla = session.get(Plantilla, fila.get("id"))
        if plantilla is None:
            continue
        plantilla.elementos_frente = copy.deepcopy(fila.get("elementos_frente", []))
        plantilla.elementos_vuelta = copy.deepcopy(fila.get("elementos_vuelta", []))

    for fila in payload.get("condiciones", []):
        condicion = session.get(CondicionVariante, fila.get("id"))
        if condicion is None:
            continue
        condicion.atributo = fila.get("atributo", condicion.atributo)

    respaldo.revertido = True
    session.flush()
    logger.info("Reconciliación %s revertida.", respaldo_id)
    return True
