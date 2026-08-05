"""Reglas de transformación de texto para atributos.

Sistema extensible de reglas aplicables a elementos de texto (p.ej. nombres,
apellidos, autorizados). Cada regla tiene un id estable y una etiqueta legible.
Para añadir una regla nueva: agregar una entrada a ``TEXT_RULES`` y su lógica
en ``apply_text_rule``.
"""
from __future__ import annotations

# Lista de reglas disponibles. El primer elemento ("") es "sin transformación".
TEXT_RULES = [
    {"id": "", "label": "Ninguna"},
    {"id": "abreviar_iniciales", "label": "Abreviar a iniciales (H. C.)"},
    {"id": "nombre_apellido", "label": "Primer nombre + primer apellido"},
    {"id": "primer_nombre", "label": "Solo el primer nombre"},
    {"id": "segundo_nombre", "label": "Solo el segundo nombre"},
    {"id": "tercer_nombre", "label": "Solo el tercer nombre"},
    {"id": "apellido_paterno", "label": "Solo el apellido paterno"},
    {"id": "apellido_materno", "label": "Solo el apellido materno"},
    {"id": "mayusculas", "label": "MAYÚSCULAS"},
    {"id": "capitalizar", "label": "Capitalizar"},
]

# Partículas que forman parte del apellido o nombre siguiente y no cuentan como
# palabra aparte: "De La Torre Marquez" son DOS apellidos, no cuatro. Aparecen
# en 142 registros del padrón, así que ignorarlas no era opción.
_PARTICULAS = frozenset({
    "de", "del", "la", "las", "los", "y", "van", "von", "der", "da", "di",
    "mc", "mac", "san", "santa",
})


def _unidades(value: str) -> list[str]:
    """Parte el texto en unidades, uniendo cada partícula a lo que le sigue.

    ``"De La Torre Marquez"`` → ``["De La Torre", "Marquez"]``
    ``"Delgadillo de la Cruz"`` → ``["Delgadillo", "de la Cruz"]``

    Una partícula al final, sin palabra que la siga, se queda pegada a la
    unidad anterior en vez de perderse.
    """
    unidades: list[str] = []
    pendiente: list[str] = []
    for token in value.split():
        pendiente.append(token)
        if token.lower() not in _PARTICULAS:
            unidades.append(" ".join(pendiente))
            pendiente = []
    if pendiente:
        if unidades:
            unidades[-1] = f"{unidades[-1]} {' '.join(pendiente)}"
        else:
            unidades.append(" ".join(pendiente))
    return unidades


def _abreviar_iniciales(value: str) -> str:
    """'Hernandez Carranza' -> 'H. C.' (cada palabra a inicial mayúscula)."""
    tokens = value.split()
    if not tokens:
        return value
    return " ".join(f"{t[0].upper()}." for t in tokens if t)


def _nombre_apellido(value: str) -> str:
    """'Hugo Rafael Hernandez Llamas' -> 'Hugo Hernandez'.

    Heurística: nombre = primer token; apellido = penúltimo token (se asume
    que los dos últimos tokens son los apellidos). Con <= 2 tokens se devuelve
    el valor tal cual.
    """
    tokens = value.split()
    if len(tokens) <= 2:
        return value
    nombre = tokens[0]
    apellido = tokens[-2]
    return f"{nombre} {apellido}"


def _primer_nombre(value: str) -> str:
    """'Hugo Rafael Hernandez' -> 'Hugo'."""
    tokens = value.split()
    if not tokens:
        return value
    return tokens[0]


def _nombre_en_posicion(value: str, posicion: int) -> str:
    """Nombre de pila en la posición dada (1 = primero), o "" si no existe.

    Cuenta **desde el principio**, sin intentar adivinar dónde terminan los
    nombres y empiezan los apellidos: la intención es usarla sobre el atributo
    ``nombre``, que el origen entrega ya separado de ``apellido``. Sobre
    ``nombre_completo`` la posición 2 puede caer en un apellido cuando la
    persona tiene un solo nombre de pila.
    """
    unidades = _unidades(value)
    if len(unidades) < posicion:
        return ""
    return unidades[posicion - 1]


def _apellido_paterno(value: str) -> str:
    """Apellido paterno, contando **desde el final**.

    Se asume que las dos últimas unidades son los apellidos, que es lo que
    hace funcionar la regla tanto sobre ``apellido`` ("Aceves Barrón") como
    sobre ``nombre_completo`` ("Carlos Daniel Aceves Barrón"). Con una sola
    unidad se devuelve esa: es el único apellido registrado.
    """
    unidades = _unidades(value)
    if not unidades:
        return ""
    if len(unidades) == 1:
        return unidades[0]
    return unidades[-2]


def _apellido_materno(value: str) -> str:
    """Apellido materno: la última unidad. Vacío si solo hay un apellido."""
    unidades = _unidades(value)
    if len(unidades) < 2:
        return ""
    return unidades[-1]


def apply_text_rule(value: str, rule_id: str) -> str:
    """Aplica la regla ``rule_id`` al ``value``.

    Si la regla es desconocida o vacía, devuelve el valor sin cambios.
    Nunca lanza excepción: ante cualquier error devuelve el valor original.
    """
    if not value or not rule_id:
        return value
    try:
        if rule_id == "abreviar_iniciales":
            return _abreviar_iniciales(value)
        if rule_id == "nombre_apellido":
            return _nombre_apellido(value)
        if rule_id == "primer_nombre":
            return _primer_nombre(value)
        if rule_id == "segundo_nombre":
            return _nombre_en_posicion(value, 2)
        if rule_id == "tercer_nombre":
            return _nombre_en_posicion(value, 3)
        if rule_id == "apellido_paterno":
            return _apellido_paterno(value)
        if rule_id == "apellido_materno":
            return _apellido_materno(value)
        if rule_id == "mayusculas":
            return value.upper()
        if rule_id == "capitalizar":
            return " ".join(t.capitalize() for t in value.split())
    except Exception:
        return value
    return value
