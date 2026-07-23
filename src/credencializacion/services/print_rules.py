"""
Reglas que deciden qué registros se imprimen y con qué datos.

Agrupa tres reglas que se aplican antes de renderizar una cola:

- **Atributos requeridos**: un elemento del diseño puede marcarse como
  ``required_for_print``; si el registro no aporta ese dato, la credencial
  no se genera para ese registro.
- **Hermanos**: los alumnos que comparten ``tutor_email`` son hermanos.
  Sus fotos alimentan los slots ``photo_url_hermano_2/3/4`` de la plantilla
  (pensados para credenciales de autorizados, que muestran a todos los
  alumnos que esa persona puede recoger).
- **Colapsado por familia**: cuando la plantilla usa slots de hermanos,
  varios hermanos en la misma cola producirían credenciales redundantes,
  así que se conserva solo la primera del grupo familiar.

Todas las reglas son puras (no tocan la base de datos ni la UI) para que el
worker de render las aplique una sola vez y use el mismo resultado en el PDF
de frentes y en el de vueltas — si cada cara filtrara por su cuenta, al
voltear la hoja las credenciales quedarían cruzadas.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# Slots de foto de hermanos. El slot 1 es el ``photo_url`` que ya existe: el
# alumno de la credencial. Estos son los hermanos 2, 3 y 4.
SIBLING_PHOTO_ATTRS: tuple[str, ...] = (
    "photo_url_hermano_2",
    "photo_url_hermano_3",
    "photo_url_hermano_4",
)

# Etiquetas legibles para la UI (panel de atributos y combo de imagen).
SIBLING_PHOTO_LABELS: dict[str, str] = {
    "photo_url_hermano_2": "Foto Hermano 2",
    "photo_url_hermano_3": "Foto Hermano 3",
    "photo_url_hermano_4": "Foto Hermano 4",
}


# ── Hermanos ──────────────────────────────────────────────────────────────

# Mínimo de dígitos para aceptar un teléfono como identificador de familia.
# Evita agrupar por extensiones o capturas incompletas ("123", "0000").
_MIN_DIGITOS_TEL = 10


def _solo_digitos(valor: Any) -> str:
    """Deja únicamente los dígitos de un teléfono, quitando formato.

    Se conservan los últimos 10 dígitos para que ``+52 55 1234 5678``,
    ``(55) 1234-5678`` y ``5512345678`` produzcan la misma clave.
    """
    digitos = re.sub(r"\D", "", str(valor or ""))
    return digitos[-10:] if len(digitos) >= _MIN_DIGITOS_TEL else ""


def _telefono_principal(registro: Any) -> str:
    """Teléfono del tutor principal a partir de los autorizados del registro.

    Respaldo para los registros ya sincronizados, que no traen ``tutor_phone``
    (se agregó después). Recorre ``autorizado_N_telefono`` prefiriendo al que
    esté marcado como principal, igual que hace el adaptador.
    """
    primero = ""
    for i in range(1, 11):
        tel = _solo_digitos(registro.get_dato(f"autorizado_{i}_telefono", ""))
        if not tel:
            continue
        principal = str(registro.get_dato(f"autorizado_{i}_principal", "") or "").strip().lower()
        if principal in ("sí", "si", "true", "1", "yes"):
            return tel
        if not primero:
            primero = tel
    return primero


def tutor_key(registro: Any) -> str:
    """Clave de familia de un registro (identidad del tutor principal).

    Se resuelve en tres niveles, del más fiable al más disponible:

    1. ``tutor_email`` — lo más confiable, pero el endpoint de la plataforma
       aún no expone correos en ``authorized_persons``.
    2. ``tutor_phone`` — teléfono del tutor principal, que el adaptador sí
       obtiene hoy.
    3. ``autorizado_N_telefono`` del principal — permite agrupar los
       registros ya sincronizados sin obligar a re-sincronizar.

    Las claves llevan prefijo (``email:`` / ``tel:``) para que un correo y un
    teléfono nunca puedan colisionar entre sí.

    Devuelve cadena vacía cuando no hay tutor identificable. Un registro sin
    clave NUNCA se considera hermano de otro: agrupar por cadena vacía
    convertiría a todos los alumnos sin tutor en una sola familia.
    """
    if not hasattr(registro, "get_dato"):
        return ""

    correo = str(registro.get_dato("tutor_email", "") or "").strip().lower()
    if correo:
        return f"email:{correo}"

    telefono = _solo_digitos(registro.get_dato("tutor_phone", ""))
    if not telefono:
        telefono = _telefono_principal(registro)
    if telefono:
        return f"tel:{telefono}"

    return ""


def _grado_num(registro: Any) -> float:
    """Grado como número para ordenar; -1 si no se puede interpretar.

    Acepta valores como ``"3"``, ``"3°"`` o ``"3ro"`` quedándose con los
    dígitos iniciales.
    """
    crudo = str(registro.get_dato("grado", "") or "").strip()
    match = re.match(r"\d+", crudo)
    if not match:
        return -1.0
    try:
        return float(match.group(0))
    except ValueError:
        return -1.0


def _nombre_orden(registro: Any) -> str:
    """Nombre completo en minúsculas, para desempatar ordenamientos."""
    nombre = getattr(registro, "nombre_completo", "") or ""
    return str(nombre).strip().lower()


def sort_siblings(registros: Iterable[Any]) -> list[Any]:
    """Ordena hermanos por grado descendente, desempatando por nombre."""
    return sorted(registros, key=lambda r: (-_grado_num(r), _nombre_orden(r)))


def family_key(registro: Any) -> str:
    """Clave de familia anclada a la escuela: ``<cliente_id>|<tutor_key>``.

    Los hermanos son alumnos de LA MISMA escuela que comparten tutor. Un
    hermano matriculado en otra escuela (p. ej. una filial) comparte el
    correo del tutor pero NO debe ocupar un slot en la credencial: cada
    credencial se imprime para una escuela concreta. Anclar la agrupación al
    ``cliente_id`` lo impide de raíz, sin depender de qué escuelas contenga
    la cola.

    Devuelve cadena vacía cuando no hay tutor identificable (sin familia).
    """
    tk = tutor_key(registro)
    if not tk:
        return ""
    cliente_id = getattr(registro, "cliente_id", None)
    return f"{cliente_id}|{tk}"


def group_by_tutor(registros: Iterable[Any]) -> dict[str, list[Any]]:
    """Agrupa registros en familias (misma escuela + mismo tutor).

    Los registros sin tutor quedan fuera del resultado: no forman familia.
    Cada grupo viene ordenado por grado descendente. La clave del dict es la
    ``family_key`` (incluye la escuela), así que dos hermanos en escuelas
    distintas caen en grupos distintos aunque compartan tutor.
    """
    grupos: dict[str, list[Any]] = {}
    for registro in registros:
        clave = family_key(registro)
        if not clave:
            continue
        grupos.setdefault(clave, []).append(registro)
    return {clave: sort_siblings(miembros) for clave, miembros in grupos.items()}


def has_siblings(registro: Any, grupos: dict[str, list[Any]]) -> bool:
    """Indica si el registro tiene al menos un hermano en la misma escuela."""
    clave = family_key(registro)
    if not clave:
        return False
    return len(grupos.get(clave, ())) > 1


def sibling_photo_extras(
    registro: Any,
    grupos: dict[str, list[Any]],
    slot_order: list[str] | None = None,
) -> dict[str, str]:
    """Fotos de los hermanos del registro, asignadas a los slots 2/3/4.

    Solo se consideran hermanos de la MISMA escuela (la agrupación está
    anclada al ``cliente_id``): un hermano de una filial no reserva slot. El
    propio alumno se excluye (ocupa el slot 1 vía ``photo_url``). Los
    hermanos van ordenados por grado descendente.

    ``slot_order`` define en qué orden se rellenan los slots. Cuando la
    plantilla coloca los slots en un orden visual distinto al numérico
    (p. ej. ``hermano_3`` a la izquierda de ``hermano_2``), pasar el orden
    visual evita dejar un hueco entre el alumno y su primer hermano: los
    hermanos llenan los slots de izquierda a derecha, no por número. Si no
    se indica, se usa el orden numérico por defecto (``hermano_2/3/4``).

    Los slots sin hermano quedan en cadena vacía, que el motor de render
    dibuja como espacio en blanco.
    """
    extras = {attr: "" for attr in SIBLING_PHOTO_ATTRS}

    clave = family_key(registro)
    if not clave:
        return extras

    orden = slot_order or list(SIBLING_PHOTO_ATTRS)

    familia = grupos.get(clave, [])
    propio_id = getattr(registro, "id", None)
    hermanos = [h for h in familia if getattr(h, "id", None) != propio_id]

    for slot, hermano in zip(orden, hermanos):
        foto = str(hermano.get_dato("photo_url", "") or "").strip()
        if not foto:
            foto = str(getattr(hermano, "photo_path", "") or "").strip()
        extras[slot] = foto

    return extras


# ── Uso de slots de hermanos en una plantilla ─────────────────────────────

def _iter_elementos(plantilla: Any) -> Iterable[dict]:
    """Recorre los elementos de ambas caras de una plantilla."""
    for atributo in ("elementos_frente", "elementos_vuelta"):
        for elem in (getattr(plantilla, atributo, None) or []):
            if isinstance(elem, dict):
                yield elem


def template_uses_sibling_slots(plantilla: Any) -> bool:
    """Indica si algún elemento del diseño está ligado a una foto de hermano.

    Determina si procede colapsar familias: sin esta comprobación, cualquier
    cola normal de credenciales de alumno empezaría a descartar hermanos
    silenciosamente.
    """
    for elem in _iter_elementos(plantilla):
        if elem.get("campo_dato", "") in SIBLING_PHOTO_ATTRS:
            return True
    return False


# Banda vertical (mm) para agrupar slots en la misma "fila" pese a pequeñas
# diferencias de altura al colocarlos a mano.
_FILA_BANDA_MM = 10.0


def template_sibling_slots_in_order(plantilla: Any) -> list[str]:
    """Slots de foto de hermano de la plantilla, en orden visual de lectura.

    Ordena por filas (de arriba a abajo) y, dentro de cada fila, de izquierda
    a derecha. Así los hermanos se asignan siguiendo la disposición real del
    diseño y no por el número del atributo: si el usuario colocó
    ``hermano_3`` a la izquierda de ``hermano_2``, el primer hermano ocupa el
    slot de la izquierda y no queda un hueco intermedio.

    Devuelve cada ``campo_dato`` una sola vez, conservando el orden.
    """
    posiciones: list[tuple[float, float, str]] = []
    for elem in _iter_elementos(plantilla):
        campo = elem.get("campo_dato", "")
        if campo not in SIBLING_PHOTO_ATTRS:
            continue
        try:
            y = float(elem.get("y", 0) or 0)
            x = float(elem.get("x", 0) or 0)
        except (TypeError, ValueError):
            y, x = 0.0, 0.0
        # Banda de fila para que jitter vertical no rompa el orden horizontal.
        fila = round(y / _FILA_BANDA_MM)
        posiciones.append((fila, x, campo))

    posiciones.sort(key=lambda t: (t[0], t[1]))

    orden: list[str] = []
    for _, _, campo in posiciones:
        if campo not in orden:
            orden.append(campo)
    return orden


def collapse_families(
    items: list[tuple[Any, Any]]
) -> tuple[list[int], list[tuple[Any, Any]]]:
    """Conserva un solo registro por familia, respetando el orden de la cola.

    El representante de cada familia es el primero que aparece en la cola: el
    orden de la cola es la garantía sobre la que se apoya la correspondencia
    frente/vuelta, así que no se reordena.

    Args:
        items: Lista de tuplas ``(registro, plantilla)`` en el orden de la cola.

    Returns:
        ``(indices_conservados, descartados)`` donde ``descartados`` son las
        tuplas omitidas por pertenecer a una familia ya representada.
    """
    conservados: list[int] = []
    descartados: list[tuple[Any, Any]] = []
    familias_vistas: set[str] = set()

    for idx, (registro, plantilla) in enumerate(items):
        # `family_key` incluye la escuela: dos hermanos de escuelas distintas
        # nunca se colapsan entre sí (cada uno es su propia credencial).
        clave = family_key(registro)
        if clave and clave in familias_vistas:
            descartados.append((registro, plantilla))
            continue
        if clave:
            familias_vistas.add(clave)
        conservados.append(idx)

    return conservados, descartados


# ── Atributos requeridos para impresión ───────────────────────────────────

def _valor_atributo(registro: Any, campo: str, extras: dict[str, str]) -> str:
    """Valor de un atributo, consultando primero los extras calculados."""
    if campo in extras:
        return str(extras.get(campo, "") or "").strip()
    return str(registro.get_dato(campo, "") or "").strip()


def _etiqueta_elemento(elem: dict, props: dict) -> str:
    """Nombre legible de un elemento para los mensajes de omisión."""
    etiqueta = str(props.get("label", "") or "").strip()
    if etiqueta:
        return etiqueta
    campo = str(elem.get("campo_dato", "") or "").strip()
    if campo:
        return SIBLING_PHOTO_LABELS.get(campo, campo)
    if elem.get("type") == "composite":
        return "texto compuesto"
    return elem.get("type", "elemento")


def missing_required_attributes(
    elementos: Iterable[dict],
    registro: Any,
    extras: dict[str, str] | None = None,
) -> list[str]:
    """Devuelve las etiquetas de los requeridos que el registro no cumple.

    Un elemento marcado ``required_for_print`` no se cumple cuando el dato del
    que depende viene vacío:

    - texto / QR / código de barras → su ``campo_dato`` está vacío.
    - texto compuesto → alguno de los ``{campos}`` de su plantilla está vacío.
    - imagen ligada a atributo → ese atributo está vacío.
    - imagen con archivo fijo → nunca bloquea (no depende del registro).

    Lista vacía significa que el registro cumple con todos los requeridos.
    """
    extras = extras or {}
    faltantes: list[str] = []

    for elem in elementos:
        if not isinstance(elem, dict):
            continue
        props = elem.get("properties", {}) or {}
        if not props.get("required_for_print", False):
            continue

        tipo = elem.get("type", "")
        campo = str(elem.get("campo_dato", "") or "").strip()
        cumple = True

        if tipo == "composite":
            plantilla_txt = str(props.get("composite_template", "") or "")
            claves = re.findall(r"\{(\w+)\}", plantilla_txt)
            if not claves:
                # Texto compuesto sin campos: es literal, no depende del registro.
                cumple = True
            else:
                cumple = all(
                    _valor_atributo(registro, clave, extras) for clave in claves
                )
        elif tipo in ("image", "photo_path"):
            if campo:
                cumple = bool(_valor_atributo(registro, campo, extras))
            elif str(props.get("src", "") or "").strip():
                cumple = True  # archivo fijo del diseño
            else:
                # Imagen sin origen: usa la foto cacheada del registro.
                cumple = bool(str(getattr(registro, "photo_path", "") or "").strip())
        else:
            # text, qr, barcode y cualquier otro tipo ligado a un atributo.
            cumple = bool(_valor_atributo(registro, campo, extras)) if campo else True

        if not cumple:
            faltantes.append(_etiqueta_elemento(elem, props))

    return faltantes
