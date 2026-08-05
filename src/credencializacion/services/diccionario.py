"""
Diccionario de atributos: resolución de claves de origen a atributos canónicos.

Cada origen nombra los datos a su manera (``address``, ``direccion``, ``calle``)
y cada país usa su propia palabra para el mismo concepto (``ine``, ``dni``,
``cedula``). En vez de tocar las cabeceras del origen, el sistema mantiene un
**diccionario editable**: un atributo canónico y las definiciones que apuntan a
él.

Dos decisiones de diseño sostienen todo lo demás:

**La resolución ocurre al LEER, no al escribir.** ``Registro.datos`` conserva
las claves crudas tal como llegaron del origen; el diccionario se aplica en el
momento de la consulta. Por eso editar una definición surte efecto de inmediato
—sin volver a sincronizar— y quitarla nunca destruye el dato: la clave original
sigue ahí.

**La resolución es bidireccional.** ``resolver(datos, "domicilio")`` encuentra
``address``, y ``resolver(datos, "address")`` también funciona porque la clave
cruda sigue presente. Esa segunda dirección es lo que permite que una plantilla
configurada antes del diccionario siga imprimiendo igual, aunque nunca se
reconcilie.
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# Familias de claves generadas con índice, que el origen produce en cantidad
# variable (un alumno puede traer 2 personas autorizadas y otro 9). No son
# atributos del diccionario —no tendría sentido definirlas una por una— pero sí
# son claves legítimas: se reconocen por patrón para que no aparezcan como
# "sin clasificar" ni se reescriban.
PATRONES_FAMILIA: tuple[re.Pattern[str], ...] = (
    re.compile(r"^autorizado_\d+_\w+$"),
)


def es_familia(clave: object) -> bool:
    """True si la clave pertenece a una familia indexada conocida."""
    texto = normalizar(clave)
    return any(p.match(texto) for p in PATRONES_FAMILIA)


# ── Normalización ────────────────────────────────────────────────────────

def normalizar(valor: object) -> str:
    """Forma canónica de una clave para comparar: texto, sin bordes, minúsculas.

    Los acentos se conservan (``direccion`` y ``dirección`` son claves
    distintas): plegarlos colapsaría pares legítimos como ``ano``/``año``. Las
    dos formas se siembran por separado en el diccionario.
    """
    return str(valor if valor is not None else "").strip().lower()


# ── Semilla del diccionario ──────────────────────────────────────────────
# (nombre, etiqueta, icono, tipo, es_sistema, [definiciones])
#
# `es_sistema` = el código referencia ese nombre como literal (90 apariciones
# en el árbol: `enrollment_code` identifica el registro en el upsert del sync,
# `student_id` viaja a la API para marcar impresión, `tutor_email` agrupa
# hermanos). Su nombre queda bloqueado; su diccionario NO.
#
# Nota sobre dos definiciones que se retiraron a propósito del catálogo previo
# (`adapters/normalizer.py`): allí `matricula` listaba `enrollment_code` y
# `student_id` como sinónimos suyos. `student_id` es el id interno del alumno
# en la API, un número distinto de la matrícula; aceptarlo como definición de
# `matricula` haría que un registro sin matrícula imprimiera el id interno como
# si fuera el número de control. Ambos quedan como canónicos propios.

# Todos los atributos nacen visibles. Qué se ofrece como arrastrable en el
# diseñador es una decisión del usuario, no del código: se administra atributo
# por atributo con la casilla "Mostrar en el diseñador" de Configuración, y esa
# elección persiste. Ocultar es solo cuestión de interfaz — el atributo se
# sigue reconociendo, resolviendo y no aparece como clave sin clasificar.
SEMILLA: tuple[tuple[str, str, str, str, bool, tuple[str, ...]], ...] = (
    # ── Identidad del alumno ──
    ("nombre", "Nombre", "👤", "text", True,
     ("nombre", "first_name", "nombres", "name", "primer_nombre",
      "nombre_alumno", "student_name")),
    ("apellido", "Apellidos", "👤", "text", True,
     ("apellido", "last_name", "apellidos", "surname")),
    ("apellido_paterno", "Apellido Paterno", "👤", "text", False,
     ("apellido_paterno", "paterno", "primer_apellido", "fathers_last_name")),
    ("apellido_materno", "Apellido Materno", "👤", "text", False,
     ("apellido_materno", "materno", "segundo_apellido", "mothers_last_name")),
    ("nombre_completo", "Nombre Completo", "👤", "text", True,
     ("nombre_completo", "full_name", "nombre_alumno_completo")),
    ("curp", "CURP", "🔢", "text", False,
     ("curp", "clave_unica", "clave_curp")),
    ("fecha_nacimiento", "Fecha Nacimiento", "📅", "text", False,
     ("fecha_nacimiento", "date_of_birth", "birthdate", "nacimiento",
      "fecha_nac", "dob", "fdn")),
    ("sexo", "Sexo", "⚧", "text", False, ("sexo", "genero", "género", "gender")),

    # ── Datos escolares ──
    ("matricula", "Matrícula", "🔢", "text", True,
     ("matricula", "matrícula", "clave_alumno", "numero_control", "folio")),
    ("enrollment_code", "Código de Inscripción", "🔢", "text", True,
     ("enrollment_code", "enrollment")),
    ("student_id", "ID de Alumno (API)", "🆔", "text", True, ("student_id",)),
    ("access_token", "Token de Acceso", "🔑", "text", True,
     ("access_token", "token")),
    ("grado", "Grado", "📚", "text", True,
     ("grado", "grade", "año_escolar", "school_grade")),
    ("grupo", "Grupo", "📚", "text", True,
     ("grupo", "group", "group_letter", "seccion", "sección", "section")),
    ("turno", "Turno", "⏰", "text", True,
     ("turno", "shift", "jornada", "horario")),
    ("nivel_escolar", "Nivel Escolar", "🏫", "text", True,
     ("nivel_escolar", "school_level", "nivel")),
    ("escuela", "Escuela", "🏢", "text", True,
     ("escuela", "school", "institucion", "institución", "plantel")),
    ("logo_escuela", "Logo de Escuela", "🏢", "image", True,
     ("logo_escuela", "logo_url", "school_logo")),

    # ── Contacto y ubicación ──
    ("domicilio", "Domicilio", "📍", "text", False,
     ("domicilio", "address", "direccion", "dirección", "calle",
      "domicilio_alumno")),
    ("colonia", "Colonia", "📍", "text", False,
     ("colonia", "neighborhood", "barrio", "fraccionamiento")),
    ("codigo_postal", "Código Postal", "📍", "text", False,
     ("codigo_postal", "código_postal", "cp", "zip", "postal_code")),
    ("estado", "Estado / Provincia", "📍", "text", False,
     ("estado_domicilio", "provincia", "departamento")),
    ("telefono", "Teléfono", "📞", "text", False,
     ("telefono", "teléfono", "phone", "celular", "tel", "movil",
      "phone_number", "telefono_casa")),
    ("email_tutor", "Email del Tutor", "✉", "text", False,
     ("email_tutor", "guardian_email", "correo_tutor", "email_padre",
      "correo_padre", "parent_email", "email_madre")),
    ("tutor_email", "Email del Tutor (API)", "✉", "text", True,
     ("tutor_email",)),
    ("tutor_phone", "Teléfono del Tutor (API)", "📞", "text", True,
     ("tutor_phone",)),

    # ── Salud ──
    ("tipo_sangre", "Tipo de Sangre", "🩸", "text", False,
     ("tipo_sangre", "blood_type", "sangre", "grupo_sanguineo",
      "tipo_sanguineo")),
    ("alergias", "Alergias", "🩺", "text", False,
     ("alergias", "allergies", "alergia")),

    # ── Credencial ──
    ("photo_url", "Foto", "🖼", "image", True,
     ("photo_url", "foto", "photo", "imagen", "image", "foto_url",
      "url_foto", "photo_path")),
    ("qr_data", "Código QR", "🔳", "text", True,
     ("qr_data", "qr", "qr_url", "codigo_qr", "qr_code", "qr_string")),
    ("estado_credencial", "Estado de Credencial", "🏷", "text", True,
     ("estado_credencial", "credential_status")),
    ("credential_display_status", "Estatus Visible", "🏷", "text", True,
     ("credential_display_status",)),
    ("form_status", "Estatus de Formulario", "🏷", "text", True,
     ("form_status",)),
    ("photo_status", "Estatus de Foto", "🏷", "text", True, ("photo_status",)),
    ("reemplazos", "Reemplazos", "🔁", "text", True,
     ("reemplazos", "credential_replacement_count")),
)


# ── Índice en memoria ────────────────────────────────────────────────────

@dataclass(frozen=True)
class AtributoDTO:
    """Vista inmutable de un atributo canónico y su diccionario."""
    id: int
    nombre: str
    etiqueta: str
    tipo: str
    icono: str
    orden: int
    es_sistema: bool
    visible: bool
    definiciones: tuple[str, ...] = ()


@dataclass(frozen=True)
class Indice:
    """Índice de resolución, cacheado en memoria y reconstruido al editar."""
    atributos: tuple[AtributoDTO, ...] = ()
    # alias normalizado → nombre canónico
    _por_alias: dict[str, str] = field(default_factory=dict)
    # nombre canónico normalizado → DTO
    _por_nombre: dict[str, AtributoDTO] = field(default_factory=dict)

    def canonico_de(self, clave: object) -> str | None:
        """Nombre canónico al que apunta una clave, o ``None`` si no está.

        Acepta tanto una definición (``address``) como el propio nombre
        canónico (``domicilio``).
        """
        n = normalizar(clave)
        if not n:
            return None
        if n in self._por_nombre:
            return self._por_nombre[n].nombre
        return self._por_alias.get(n)

    def atributo(self, nombre: object) -> AtributoDTO | None:
        """DTO del canónico indicado (acepta también una de sus definiciones)."""
        canonico = self.canonico_de(nombre)
        if canonico is None:
            return None
        return self._por_nombre.get(normalizar(canonico))

    def definiciones_de(self, nombre: object) -> tuple[str, ...]:
        """Definiciones del canónico, en orden de preferencia de resolución."""
        attr = self.atributo(nombre)
        return attr.definiciones if attr else ()

    def es_conocida(self, clave: object) -> bool:
        """True si la clave es un canónico, una definición o una familia."""
        return self.canonico_de(clave) is not None or es_familia(clave)


_indice: Indice | None = None
_lock = threading.Lock()


def _construir_indice(session) -> Indice:
    from credencializacion.db.models import AliasAtributo, AtributoCanonico

    filas = (
        session.query(AtributoCanonico)
        .order_by(AtributoCanonico.orden, AtributoCanonico.id)
        .all()
    )

    # Las definiciones se consultan directo en vez de por la relación: si el
    # atributo ya estaba cargado en la sesión, su colección `alias` puede venir
    # cacheada y no incluir las filas recién agregadas — el índice nacería
    # incompleto justo después de editar el diccionario. De paso evita una
    # consulta por atributo.
    por_atributo: dict[int, list[str]] = {}
    for fila_alias in (
        session.query(AliasAtributo).order_by(AliasAtributo.id).all()
    ):
        por_atributo.setdefault(fila_alias.atributo_id, []).append(fila_alias.alias)

    atributos: list[AtributoDTO] = []
    por_alias: dict[str, str] = {}
    por_nombre: dict[str, AtributoDTO] = {}

    for fila in filas:
        definiciones = tuple(por_atributo.get(fila.id, ()))
        dto = AtributoDTO(
            id=fila.id,
            nombre=fila.nombre,
            etiqueta=fila.etiqueta or fila.nombre,
            tipo=fila.tipo,
            icono=fila.icono,
            orden=fila.orden,
            es_sistema=fila.es_sistema,
            visible=fila.visible,
            definiciones=definiciones,
        )
        atributos.append(dto)
        por_nombre[normalizar(fila.nombre)] = dto
        for alias in definiciones:
            por_alias[normalizar(alias)] = fila.nombre

    return Indice(
        atributos=tuple(atributos),
        _por_alias=por_alias,
        _por_nombre=por_nombre,
    )


def obtener_indice(session=None) -> Indice:
    """Índice vigente, construido una vez y cacheado hasta que se invalide."""
    global _indice
    with _lock:
        if _indice is not None:
            return _indice
        if session is not None:
            _indice = _construir_indice(session)
            return _indice

    from credencializacion.db.engine import DatabaseSession

    with DatabaseSession() as s:
        construido = _construir_indice(s)
    with _lock:
        _indice = construido
    return construido


def invalidar_indice() -> None:
    """Descarta el índice cacheado; la próxima lectura lo reconstruye.

    Se llama tras cualquier cambio en el diccionario, de modo que una edición
    en Configuración surta efecto sin reiniciar ni volver a sincronizar.
    """
    global _indice
    with _lock:
        _indice = None


# ── Resolución sobre un registro ─────────────────────────────────────────

def clave_real(
    datos: dict[str, Any],
    campo: object,
    indice: Indice | None = None,
) -> str | None:
    """Clave de ``datos`` que corresponde a ``campo``, o ``None``.

    Orden de resolución:

    1. Coincidencia directa (exacta, y luego insensible a mayúsculas).
    2. Si ``campo`` es canónico —o una definición de uno—, se prueban las
       definiciones de ese canónico en orden hasta encontrar una presente.

    El paso 1 es lo que mantiene vivas las plantillas configuradas antes del
    diccionario: apuntan a ``address``, y ``address`` sigue en los datos.
    """
    if not datos:
        return None
    campo_txt = str(campo or "")
    if not campo_txt:
        return None

    if campo_txt in datos:
        return campo_txt

    normalizadas = {normalizar(k): k for k in datos}
    directa = normalizadas.get(normalizar(campo_txt))
    if directa is not None:
        return directa

    idx = indice if indice is not None else obtener_indice()
    canonico = idx.canonico_de(campo_txt)
    if canonico is None:
        return None

    real = normalizadas.get(normalizar(canonico))
    if real is not None:
        return real

    for definicion in idx.definiciones_de(canonico):
        real = normalizadas.get(normalizar(definicion))
        if real is not None:
            return real
    return None


def resolver(
    datos: dict[str, Any],
    campo: object,
    default: Any = "",
    indice: Indice | None = None,
) -> Any:
    """Valor de ``campo`` en ``datos`` aplicando el diccionario."""
    real = clave_real(datos, campo, indice)
    if real is None:
        return default
    return datos.get(real, default)


def vista_canonica(
    claves: Iterable[str],
    indice: Indice | None = None,
) -> list[str]:
    """Traduce una lista de claves crudas a la lista de atributos a mostrar.

    Cada clave reconocida se sustituye por su canónico (deduplicando: seis
    variantes de domicilio colapsan en una entrada). Las claves que el
    diccionario no conoce se conservan tal cual, para que ningún dato
    desaparezca de la vista por no estar clasificado todavía.
    """
    idx = indice if indice is not None else obtener_indice()
    salida: list[str] = []
    vistos: set[str] = set()
    for clave in claves:
        if not isinstance(clave, str) or not clave.strip():
            continue
        canonico = idx.canonico_de(clave)
        final = canonico if canonico else clave
        marca = normalizar(final)
        if marca in vistos:
            continue
        vistos.add(marca)
        salida.append(final)
    return salida


def claves_sin_clasificar(
    claves: Iterable[str],
    indice: Indice | None = None,
) -> list[str]:
    """Claves que no pertenecen a ningún atributo del diccionario.

    Alimenta la bandeja de Configuración: es la lista de datos que el sistema
    está recibiendo y todavía nadie definió a qué atributo pertenecen.
    """
    idx = indice if indice is not None else obtener_indice()
    salida: list[str] = []
    vistos: set[str] = set()
    for clave in claves:
        if not isinstance(clave, str) or not clave.strip():
            continue
        if idx.es_conocida(clave):
            continue
        marca = normalizar(clave)
        if marca in vistos:
            continue
        vistos.add(marca)
        salida.append(clave)
    return salida


# ── Siembra ──────────────────────────────────────────────────────────────

def sembrar(session) -> int:
    """Crea los atributos y definiciones que falten. Idempotente.

    Pensada para correr en cada arranque desde ``init_database()``: una
    instalación nueva queda con el catálogo completo, y una que ya venía en
    producción recibe solo lo que le falte, **sin tocar lo que el usuario haya
    configurado** — ni sus definiciones propias ni las que haya eliminado a
    propósito de un atributo que ya existía.

    Returns:
        Cuántas filas se crearon (atributos + definiciones).
    """
    from credencializacion.db.models import AliasAtributo, AtributoCanonico

    existentes = {
        normalizar(a.nombre): a
        for a in session.query(AtributoCanonico).all()
    }
    alias_tomados = {
        normalizar(a.alias) for a in session.query(AliasAtributo).all()
    }

    creados = 0
    for orden, (nombre, etiqueta, icono, tipo, es_sistema, definiciones) in enumerate(
        SEMILLA
    ):
        attr = existentes.get(normalizar(nombre))
        if attr is None:
            attr = AtributoCanonico(
                nombre=nombre,
                etiqueta=etiqueta,
                icono=icono,
                tipo=tipo,
                orden=orden,
                es_sistema=es_sistema,
                visible=True,
            )
            session.add(attr)
            session.flush()
            existentes[normalizar(nombre)] = attr
            creados += 1
            nuevas = definiciones
        else:
            # Atributo preexistente: se respeta lo que el usuario haya hecho con
            # su diccionario. Solo se siembran definiciones en un atributo que
            # se acaba de crear.
            nuevas = ()
            # El flag de sistema sí se reafirma: es una propiedad del código,
            # no una preferencia del usuario.
            if attr.es_sistema != es_sistema:
                attr.es_sistema = es_sistema

        for alias in nuevas:
            clave = normalizar(alias)
            # El nombre del atributo ya resuelve por sí mismo: sembrarlo además
            # como definición crearía una fila redundante que luego permitiría
            # "moverla" a otro atributo y dejar la clave con dos dueños.
            if not clave or clave == normalizar(nombre) or clave in alias_tomados:
                continue
            session.add(
                AliasAtributo(
                    atributo_id=attr.id, alias=clave, origen="semilla",
                )
            )
            alias_tomados.add(clave)
            creados += 1

    if creados:
        logger.info("Diccionario de atributos: %d filas sembradas.", creados)
        invalidar_indice()
    return creados


# ── CRUD ─────────────────────────────────────────────────────────────────

class ErrorDiccionario(Exception):
    """Operación inválida sobre el diccionario (mensaje apto para la UI)."""


def crear_atributo(
    session,
    nombre: str,
    etiqueta: str = "",
    tipo: str = "text",
    icono: str = "",
) -> Any:
    """Crea un atributo canónico de usuario."""
    from credencializacion.db.models import AtributoCanonico

    limpio = normalizar(nombre).replace(" ", "_")
    if not limpio:
        raise ErrorDiccionario("El nombre del atributo no puede estar vacío.")
    if obtener_indice(session).canonico_de(limpio) is not None:
        raise ErrorDiccionario(
            f"'{limpio}' ya existe como atributo o como definición de otro."
        )

    maximo = session.query(AtributoCanonico).count()
    attr = AtributoCanonico(
        nombre=limpio,
        etiqueta=etiqueta.strip() or limpio,
        tipo=tipo if tipo in ("text", "image") else "text",
        icono=icono,
        orden=maximo,
        es_sistema=False,
        visible=True,
    )
    session.add(attr)
    session.flush()
    invalidar_indice()
    return attr


def renombrar_atributo(session, atributo_id: int, nuevo_nombre: str) -> str:
    """Renombra un canónico de usuario y devuelve el nombre aplicado.

    No propaga el cambio a plantillas ni condiciones: de eso se encarga la
    reconciliación, que muestra antes qué va a tocar y permite deshacerlo.
    """
    from credencializacion.db.models import AtributoCanonico

    attr = session.get(AtributoCanonico, atributo_id)
    if attr is None:
        raise ErrorDiccionario("El atributo ya no existe.")
    if attr.es_sistema:
        raise ErrorDiccionario(
            f"'{attr.nombre}' es un atributo ancla del sistema: el motor lo "
            "referencia por nombre. Puedes cambiar sus definiciones, no su "
            "nombre."
        )

    limpio = normalizar(nuevo_nombre).replace(" ", "_")
    if not limpio:
        raise ErrorDiccionario("El nombre del atributo no puede estar vacío.")
    if limpio == normalizar(attr.nombre):
        return attr.nombre

    conflicto = obtener_indice(session).canonico_de(limpio)
    if conflicto is not None:
        raise ErrorDiccionario(
            f"'{limpio}' ya existe como atributo o como definición de "
            f"'{conflicto}'."
        )

    attr.nombre = limpio
    session.flush()
    invalidar_indice()
    return limpio


def eliminar_atributo(session, atributo_id: int) -> None:
    """Elimina un canónico de usuario; sus definiciones quedan sin clasificar."""
    from credencializacion.db.models import AtributoCanonico

    attr = session.get(AtributoCanonico, atributo_id)
    if attr is None:
        return
    if attr.es_sistema:
        raise ErrorDiccionario(
            f"'{attr.nombre}' es un atributo ancla del sistema y no puede "
            "eliminarse."
        )
    session.delete(attr)
    session.flush()
    invalidar_indice()


def agregar_definicion(
    session,
    atributo_id: int,
    alias: str,
    mover: bool = False,
) -> None:
    """Agrega una definición a un atributo.

    Args:
        mover: Si la definición ya pertenece a otro atributo, ``True`` la
               reasigna; ``False`` (por defecto) falla con un mensaje que
               indica el dueño actual. La unicidad es lo que impide que una
               misma clave se resuelva de dos formas según el orden.
    """
    from credencializacion.db.models import AliasAtributo, AtributoCanonico

    clave = normalizar(alias)
    if not clave:
        raise ErrorDiccionario("La definición no puede estar vacía.")

    attr = session.get(AtributoCanonico, atributo_id)
    if attr is None:
        raise ErrorDiccionario("El atributo ya no existe.")

    if normalizar(attr.nombre) == clave:
        raise ErrorDiccionario(
            "El nombre del atributo ya se resuelve solo; no hace falta "
            "agregarlo como definición."
        )

    # Choque contra el NOMBRE de otro atributo: no se puede resolver moviendo
    # una fila, porque el nombre es la identidad de ese atributo y seguiría
    # resolviéndose por su cuenta. Quedarían dos caminos para la misma clave —
    # justo la ambigüedad que el diccionario existe para eliminar.
    otro = (
        session.query(AtributoCanonico)
        .filter(AtributoCanonico.id != attr.id)
        .all()
    )
    for candidato in otro:
        if normalizar(candidato.nombre) == clave:
            raise ErrorDiccionario(
                f"'{clave}' es el nombre del atributo '{candidato.nombre}'. "
                "Renómbralo o elimínalo antes de usar esa palabra como "
                "definición de otro atributo."
            )

    otro_canonico = obtener_indice(session).canonico_de(clave)
    if otro_canonico is not None and normalizar(otro_canonico) != normalizar(attr.nombre):
        if not mover:
            raise ErrorDiccionario(
                f"'{clave}' ya está definida en '{otro_canonico}'. "
                "Muévela si es ahí donde no corresponde."
            )
        existente = (
            session.query(AliasAtributo).filter_by(alias=clave).first()
        )
        if existente is not None:
            existente.atributo_id = attr.id
            existente.origen = "usuario"
            session.flush()
            invalidar_indice()
            return

    ya = session.query(AliasAtributo).filter_by(alias=clave).first()
    if ya is not None:
        return  # ya pertenece a este mismo atributo

    session.add(
        AliasAtributo(atributo_id=attr.id, alias=clave, origen="usuario")
    )
    session.flush()
    invalidar_indice()


def quitar_definicion(session, atributo_id: int, alias: str) -> None:
    """Quita una definición. El dato crudo no se toca: es reversible."""
    from credencializacion.db.models import AliasAtributo

    clave = normalizar(alias)
    fila = (
        session.query(AliasAtributo)
        .filter_by(atributo_id=atributo_id, alias=clave)
        .first()
    )
    if fila is None:
        return
    session.delete(fila)
    session.flush()
    invalidar_indice()


def fijar_visibilidad(session, atributo_id: int, visible: bool) -> None:
    """Define si el atributo se ofrece como arrastrable en el diseñador."""
    from credencializacion.db.models import AtributoCanonico

    attr = session.get(AtributoCanonico, atributo_id)
    if attr is None:
        return
    attr.visible = bool(visible)
    session.flush()
    invalidar_indice()
