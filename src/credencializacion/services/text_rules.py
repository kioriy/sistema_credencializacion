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
    {"id": "mayusculas", "label": "MAYÚSCULAS"},
    {"id": "capitalizar", "label": "Capitalizar"},
]


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
        if rule_id == "mayusculas":
            return value.upper()
        if rule_id == "capitalizar":
            return " ".join(t.capitalize() for t in value.split())
    except Exception:
        return value
    return value
