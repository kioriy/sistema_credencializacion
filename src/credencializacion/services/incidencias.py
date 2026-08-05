"""
Detección de incidencias de integridad en los registros de alumnos.

Marca los registros que conviene revisar ANTES de imprimir una credencial,
porque la plataforma de origen entregó datos internamente inconsistentes:

- **CURP que no concuerda con el alumno.** La CURP es autoverificable: sus
  cuatro primeras letras derivan de los apellidos y el nombre. Cuando no
  concuerdan, casi siempre es la CURP de un hermano que se filtró al expediente
  al inscribir al segundo hijo.
- **CURP repetida** entre dos alumnos distintos.
- **Más personas autorizadas de las que permite el formulario** (4), casi
  siempre por reenvíos que insertan filas nuevas en vez de actualizar.
- **Personas autorizadas duplicadas** dentro del mismo alumno.

Son avisos para revisión humana, no errores: la comprobación de CURP es
deliberadamente tolerante (apellidos compuestos, partículas, nombres
compuestos, materno ausente) para no marcar registros correctos. Calibrada
contra 702 registros reales con CURP: marca el 1.9%.

## Agregar una regla nueva

El catálogo es abierto. Una regla es una función que recibe los datos del
registro y un `Contexto` con lo que se precalculó del lote completo, y devuelve
las incidencias que encuentre::

    @regla
    def sin_fotografia(datos, contexto):
        if not str(datos.get("photo_url", "") or "").strip():
            return [Incidencia("sin_foto", "Sin fotografía",
                               "El alumno no tiene foto cargada.")]
        return []

Con el decorador basta: `detectar` recorre `REGLAS` en orden de registro. Si la
regla necesita mirar todo el lote (como "CURP repetida", que no se puede saber
mirando un registro solo), se agrega el dato precalculado a `Contexto` y se
llena en `construir_contexto`. Para que aparezca en el resumen del footer con
nombre propio, agregar su `tipo` a `_ORDEN_RESUMEN`.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

# Máximo de personas autorizadas que permite el formulario de la plataforma.
MAX_AUTORIZADOS = 4

# Partículas que la CURP omite al derivar sus letras ("De La Torre" → TORRE).
_PARTICULAS = frozenset({
    "de", "la", "las", "los", "del", "y", "mc", "mac", "van", "von", "der",
    "di", "da",
})

_RE_SLOT_AUTORIZADO = re.compile(r"^autorizado_(\d+)_")


# ── Tipos ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Incidencia:
    """Un hallazgo sobre un registro, listo para mostrarse en la interfaz."""
    tipo: str          # "curp_incoherente" | "curp_duplicada" | …
    titulo: str        # etiqueta corta para agrupar en el resumen
    detalle: str       # frase explicativa para el tooltip / footer


@dataclass(frozen=True)
class Contexto:
    """Lo que se precalcula del lote y una regla individual no podría saber.

    Existe para que una regla que necesita comparar registros entre sí (como
    "CURP repetida") no tenga que recorrer el lote por su cuenta. Agregar aquí
    los índices que necesiten las reglas nuevas, y llenarlos en
    `construir_contexto`.
    """
    curps_repetidas: frozenset[str] = frozenset()
    total_registros: int = 0


# Catálogo abierto de reglas. Cada una recibe ``(datos, contexto)``.
ReglaIncidencia = Callable[[dict, Contexto], list[Incidencia]]
REGLAS: list[ReglaIncidencia] = []


def regla(func: ReglaIncidencia) -> ReglaIncidencia:
    """Registra una función como regla de validación. Ver el módulo."""
    REGLAS.append(func)
    return func


# ── Normalización de nombres ─────────────────────────────────────────────

def _palabras(texto: object) -> list[str]:
    """Mayúsculas sin acentos, con Ñ→X, partida en palabras."""
    crudo = unicodedata.normalize("NFD", str(texto or ""))
    limpio = "".join(c for c in crudo if unicodedata.category(c) != "Mn")
    limpio = limpio.upper().replace("Ñ", "X")
    return [t for t in re.sub(r"[^A-Z ]", " ", limpio).split() if t]


def _raiz(palabras: list[str]) -> str:
    """Primera palabra significativa, ignorando partículas."""
    utiles = [p for p in palabras if p.lower() not in _PARTICULAS]
    if utiles:
        return utiles[0]
    return palabras[0] if palabras else ""


def prefijos_curp_validos(nombre: object, apellidos: object) -> set[str]:
    """Prefijos de CURP compatibles con ese nombre y esos apellidos.

    Devuelve un conjunto porque hay ambigüedad legítima que no se puede
    resolver desde los datos, y marcar un registro correcto es peor que dejar
    pasar uno dudoso:

    - **Dónde parte el apellido paterno del materno.** ``apellido`` llega como
      un solo campo: "De La Torre Marquez" puede partirse en varios puntos, y
      se aceptan todos.
    - **Nombres compuestos.** "Fernanda Mariel" admite F o M como inicial.
    - **Segunda letra.** Es la primera vocal interna del paterno, pero el
      registro civil la sustituye por X en varios casos, así que se acepta.
    - **Materno ausente.** Si solo hay un apellido registrado, la tercera letra
      queda como comodín ``?``.
    """
    apellidos_lst = _palabras(apellidos)
    nombres_lst = [p for p in _palabras(nombre) if p.lower() not in _PARTICULAS]
    if not apellidos_lst or not nombres_lst:
        return set()

    iniciales_nombre = {p[0] for p in nombres_lst}
    salida: set[str] = set()
    divisiones = range(1, len(apellidos_lst) + 1) if len(apellidos_lst) > 1 else [1]

    for corte in divisiones:
        paterno = _raiz(apellidos_lst[:corte])
        materno = _raiz(apellidos_lst[corte:]) if corte < len(apellidos_lst) else ""
        if not paterno:
            continue
        vocales = {next((c for c in paterno[1:] if c in "AEIOU"), "X"), "X"}
        terceras = {materno[0], "X"} if materno else {"?"}
        for vocal in vocales:
            for tercera in terceras:
                for inicial in iniciales_nombre:
                    salida.add(f"{paterno[0]}{vocal}{tercera}{inicial}")
    return salida


def curp_concuerda(curp: object, nombre: object, apellidos: object) -> bool | None:
    """Indica si la CURP concuerda con el nombre.

    ``None`` significa que no se pudo evaluar (falta la CURP o el nombre), que
    es distinto de "no concuerda" y no debe marcarse como incidencia.
    """
    texto = str(curp or "").strip().upper()
    if len(texto) < 4:
        return None
    posibles = prefijos_curp_validos(nombre, apellidos)
    if not posibles:
        return None

    for patron in posibles:
        if patron[2] == "?":
            # Materno desconocido: se comparan las otras tres posiciones.
            if (texto[0], texto[1], texto[3]) == (patron[0], patron[1], patron[3]):
                return True
        elif texto[:4] == patron:
            return True
    return False


# ── Personas autorizadas ─────────────────────────────────────────────────

def _slots_autorizados(datos: dict) -> list[int]:
    numeros: set[int] = set()
    for clave in datos:
        m = _RE_SLOT_AUTORIZADO.match(str(clave))
        if m:
            numeros.add(int(m.group(1)))
    return sorted(numeros)


def _firma_persona(datos: dict, n: int) -> tuple[str, str]:
    """Identidad de una persona autorizada: nombre sin espacios + teléfono."""
    nombre = "".join(_palabras(datos.get(f"autorizado_{n}_nombre", "")))
    telefono = re.sub(r"\D", "", str(datos.get(f"autorizado_{n}_telefono", "") or ""))
    return nombre, telefono[-10:] if len(telefono) >= 10 else telefono


def analizar_autorizados(datos: dict) -> tuple[int, int]:
    """Devuelve ``(personas_devueltas, personas_distintas)``."""
    slots = _slots_autorizados(datos)
    if not slots:
        return 0, 0
    firmas = {_firma_persona(datos, n) for n in slots}
    return len(slots), len(firmas)


# ── Detección ────────────────────────────────────────────────────────────

@regla
def _curp_incoherente(datos: dict, _contexto: Contexto) -> list[Incidencia]:
    """La CURP no deriva del nombre del propio alumno."""
    curp = str(datos.get("curp", "") or "").strip().upper()
    nombre = datos.get("nombre", "")
    apellidos = datos.get("apellido", "") or datos.get("apellidos", "")

    if curp_concuerda(curp, nombre, apellidos) is not False:
        return []
    return [Incidencia(
        tipo="curp_incoherente",
        titulo="CURP no concuerda",
        detalle=(
            f"La CURP «{curp}» no corresponde a «{nombre} {apellidos}». "
            "Suele ser la CURP de un hermano filtrada al expediente."
        ),
    )]


@regla
def _curp_duplicada(datos: dict, contexto: Contexto) -> list[Incidencia]:
    """La misma CURP está en más de un alumno del lote."""
    curp = str(datos.get("curp", "") or "").strip().upper()
    if not curp or curp not in contexto.curps_repetidas:
        return []
    return [Incidencia(
        tipo="curp_duplicada",
        titulo="CURP repetida",
        detalle=f"La CURP «{curp}» está asignada a más de un alumno.",
    )]


@regla
def _autorizados(datos: dict, _contexto: Contexto) -> list[Incidencia]:
    """Más personas autorizadas de las permitidas, o filas repetidas."""
    devueltas, distintas = analizar_autorizados(datos)

    if devueltas > MAX_AUTORIZADOS:
        detalle = (
            f"{devueltas} personas autorizadas; el formulario permite "
            f"{MAX_AUTORIZADOS}."
        )
        if distintas < devueltas:
            detalle += f" Solo {distintas} son distintas: el resto son duplicados."
        return [Incidencia(
            tipo="exceso_autorizados", titulo="Exceso de autorizados",
            detalle=detalle,
        )]

    if distintas and distintas < devueltas:
        return [Incidencia(
            tipo="autorizados_duplicados",
            titulo="Autorizados duplicados",
            detalle=(
                f"{devueltas} personas autorizadas, pero solo {distintas} "
                "distintas."
            ),
        )]
    return []


def detectar(registro: Any, contexto: Contexto | None = None) -> list[Incidencia]:
    """Incidencias de un registro. Lista vacía significa que está limpio.

    Aplica todas las reglas de `REGLAS` en orden de registro. Una regla que
    falle no tumba al resto ni oculta el registro: se ignora su resultado.
    """
    datos = getattr(registro, "datos", None) or {}
    if not isinstance(datos, dict):
        return []

    ctx = contexto if contexto is not None else Contexto()
    hallazgos: list[Incidencia] = []
    for aplicar in REGLAS:
        try:
            hallazgos.extend(aplicar(datos, ctx))
        except Exception:  # noqa: BLE001
            continue
    return hallazgos


def construir_contexto(registros: Iterable[Any]) -> Contexto:
    """Precalcula lo que las reglas necesitan saber del lote completo."""
    lote = list(registros)
    return Contexto(
        curps_repetidas=frozenset(curps_duplicadas(lote)),
        total_registros=len(lote),
    )


def curps_duplicadas(registros: Iterable[Any]) -> set[str]:
    """CURPs que aparecen en más de un registro del lote."""
    vistas: set[str] = set()
    repetidas: set[str] = set()
    for registro in registros:
        datos = getattr(registro, "datos", None) or {}
        if not isinstance(datos, dict):
            continue
        curp = str(datos.get("curp", "") or "").strip().upper()
        if not curp:
            continue
        if curp in vistas:
            repetidas.add(curp)
        vistas.add(curp)
    return repetidas


def analizar_lote(registros: Iterable[Any]) -> dict[int, list[Incidencia]]:
    """Incidencias de una lista de registros, indexadas por ``registro.id``.

    Solo se incluyen los registros con al menos una incidencia.
    """
    lote = list(registros)
    contexto = construir_contexto(lote)
    resultado: dict[int, list[Incidencia]] = {}
    for registro in lote:
        hallazgos = detectar(registro, contexto)
        if hallazgos:
            resultado[getattr(registro, "id", None)] = hallazgos
    resultado.pop(None, None)
    return resultado


# Orden en que se listan los tipos en el resumen del footer, del más grave al
# menos, con su etiqueta en minúscula. Una regla nueva se agrega aquí para
# controlar su posición; si no, aparece al final con su propio título.
_ORDEN_RESUMEN: tuple[tuple[str, str], ...] = (
    ("curp_incoherente", "CURP no concuerda"),
    ("curp_duplicada", "CURP repetida"),
    ("exceso_autorizados", "exceso de autorizados"),
    ("autorizados_duplicados", "autorizados duplicados"),
)


def resumir(incidencias: Iterable[Incidencia]) -> str:
    """Frase compacta para el footer: cuenta por tipo, del más grave al menos.

    Ejemplo: ``"2 CURP no concuerda, 1 exceso de autorizados"``.
    """
    conteo: dict[str, int] = {}
    for inc in incidencias:
        conteo[inc.tipo] = conteo.get(inc.tipo, 0) + 1

    partes = [
        f"{conteo[tipo]} {etiqueta}"
        for tipo, etiqueta in _ORDEN_RESUMEN
        if conteo.get(tipo)
    ]
    # Un tipo no listado igual aparece, al final: una regla nueva nunca queda
    # invisible en el resumen por olvidar registrarla aquí.
    conocidos = {tipo for tipo, _ in _ORDEN_RESUMEN}
    for inc in incidencias:
        if inc.tipo not in conocidos and conteo.get(inc.tipo):
            partes.append(f"{conteo.pop(inc.tipo)} {inc.titulo.lower()}")
    return ", ".join(partes)
