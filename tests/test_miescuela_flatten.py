"""Pruebas del aplanado de registros del adaptador de MiEscuela.

El foco está en las colisiones entre la ficha configurable de cada escuela
(``student_record``) y los atributos fijos que el adaptador escribe siempre.
Antes, la clave de la escuela se descartaba sin dejar rastro: no llegaba a la
base ni al catálogo del cliente, así que nada delataba la pérdida.
"""
from __future__ import annotations

from credencializacion.adapters.miescuela import MiEscuelaAdapter

_APLANAR = MiEscuelaAdapter._flatten_record


def _alumno(student_record: dict) -> dict:
    return {
        "id": 4021,
        "first_name": "Ana",
        "last_name": "López",
        "enrollment_code": "1500",
        "classroom": {"grade": "3", "group_letter": "B"},
        "school": {"name": "Ernesto Corona Amador"},
        "student_record": student_record,
    }


def test_un_campo_de_ficha_sin_colision_se_aplana_tal_cual():
    plano = _APLANAR(_alumno({"curp": "AULG170508MJCGZNA1", "alergias": "No"}))

    assert plano["curp"] == "AULG170508MJCGZNA1"
    assert plano["alergias"] == "No"


def test_una_matricula_propia_de_la_escuela_no_se_pierde():
    """El caso de Ernesto Corona Amador: la escuela define su propia matrícula."""
    plano = _APLANAR(_alumno({"matricula": "ECA-2024-0087"}))

    # Gana el adaptador: es lo que las plantillas ya imprimen.
    assert plano["matricula"] == "1500"
    assert plano["enrollment_code"] == "1500"
    # Pero el dato de la escuela sigue disponible.
    assert plano["student_record_matricula"] == "ECA-2024-0087"


def test_si_el_valor_es_el_mismo_no_se_duplica():
    """Conservar una copia idéntica solo ensuciaría la bandeja."""
    plano = _APLANAR(_alumno({"matricula": "1500"}))

    assert plano["matricula"] == "1500"
    assert "student_record_matricula" not in plano


def test_la_proteccion_cubre_a_todos_los_atributos_fijos():
    plano = _APLANAR(_alumno({
        "nombre": "Otro Nombre",
        "grado": "9",
        "escuela": "Otra Escuela",
    }))

    assert plano["nombre"] == "Ana"
    assert plano["grado"] == "3"
    assert plano["escuela"] == "Ernesto Corona Amador"
    assert plano["student_record_nombre"] == "Otro Nombre"
    assert plano["student_record_grado"] == "9"
    assert plano["student_record_escuela"] == "Otra Escuela"


def test_una_ficha_que_ya_use_el_prefijo_no_se_sobrescribe():
    plano = _APLANAR(_alumno({
        "matricula": "ECA-2024-0087",
        "student_record_matricula": "ya_existia",
    }))

    assert plano["student_record_matricula"] == "ya_existia"


def test_los_valores_no_escalares_se_siguen_ignorando():
    plano = _APLANAR(_alumno({"historial": [1, 2, 3], "meta": {"a": 1}}))

    assert "historial" not in plano
    assert "meta" not in plano


def test_un_nulo_se_aplana_como_cadena_vacia():
    plano = _APLANAR(_alumno({"religion": None}))

    assert plano["religion"] == ""
