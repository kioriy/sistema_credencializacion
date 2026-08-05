"""Pruebas de la detección de incidencias de integridad.

La comprobación de CURP debe ser TOLERANTE: marcar un registro correcto le
cuesta al operador una revisión inútil y erosiona la confianza en la marca, así
que ante ambigüedad legítima (apellidos compuestos, partículas, nombres
compuestos, materno ausente) no se marca.

Los casos "reales" reproducen registros observados en producción.
"""
from __future__ import annotations

import pytest

from credencializacion.services import incidencias as inc


class _Reg:
    """Doble de `Registro` con lo único que el detector consulta."""

    def __init__(self, id: int, **datos) -> None:
        self.id = id
        self.datos = datos


# ── CURP: casos que NO deben marcarse ────────────────────────────────────

@pytest.mark.parametrize("curp, nombre, apellido, motivo", [
    ("LOES170101HJCXXX00", "Santiago", "Lopez Espinoza", "caso simple"),
    ("TOMM170101MJCXXX00", "Madisson Lucia", "De La Torre Marquez",
     "partícula 'De La' — la CURP la omite"),
    ("DECY170101MJCXXX00", "Yaretzi", "De La Cruz Garcia",
     "otra división válida del apellido compuesto"),
    ("GOXS170101MJCXXX00", "Sarah Emilia", "Gómez",
     "sin apellido materno registrado"),
    ("BECM170101MJCXXX00", "Fernanda Mariel", "Bernal Cardenas",
     "nombre compuesto: la CURP usó el segundo"),
    ("BECF170101MJCXXX00", "Fernanda Mariel", "Bernal Cardenas",
     "nombre compuesto: la CURP usó el primero"),
    ("LXES170101HJCXXX00", "Santiago", "Lopez Espinoza",
     "segunda letra sustituida por X"),
    ("PEXA170101HJCXXX00", "Alberto", "Perez Ñoño",
     "Ñ del materno se transcribe como X"),
])
def test_curp_valida_no_se_marca(curp, nombre, apellido, motivo):
    assert inc.curp_concuerda(curp, nombre, apellido) is True, motivo


@pytest.mark.parametrize("curp, nombre, apellido", [
    ("", "Santiago", "Lopez Espinoza"),          # sin CURP
    ("LOES", "", ""),                            # sin nombre
    ("AB", "Santiago", "Lopez Espinoza"),        # CURP truncada
])
def test_sin_datos_suficientes_no_se_evalua(curp, nombre, apellido):
    """`None` ≠ incoherente: no hay base para marcar nada."""
    assert inc.curp_concuerda(curp, nombre, apellido) is None


# ── CURP: casos que SÍ deben marcarse ────────────────────────────────────

def test_curp_de_otra_familia(sub=None):
    """Caso real (student_id 2026): CURP de la familia Morales Quintero."""
    assert inc.curp_concuerda(
        "MOQC170129HJCRNSA0", "Santiago", "Lopez Espinoza",
    ) is False


def test_curp_de_un_hermano():
    """Caso real: la CURP de Dante quedó en el expediente de Camila."""
    assert inc.curp_concuerda(
        "GORD190507HJCNMNA2", "Camila Fernanda", "Gonzalez Romero",
    ) is False


def test_detecta_incidencia_de_curp_en_el_registro():
    reg = _Reg(1, curp="MOQC170129HJCRNSA0", nombre="Santiago",
               apellido="Lopez Espinoza")
    tipos = [i.tipo for i in inc.detectar(reg)]

    assert tipos == ["curp_incoherente"]


# ── Personas autorizadas ─────────────────────────────────────────────────

def _con_autorizados(n: int, nombre_repetido: bool = False) -> dict:
    datos = {}
    for i in range(1, n + 1):
        datos[f"autorizado_{i}_nombre"] = (
            "Citlally Quezada Mora" if nombre_repetido else f"Persona {i}"
        )
        datos[f"autorizado_{i}_telefono"] = (
            "3346295249" if nombre_repetido else f"33100000{i:02d}"
        )
    return datos


def test_cuatro_autorizados_no_es_incidencia():
    assert inc.detectar(_Reg(1, **_con_autorizados(4))) == []


def test_exceso_de_autorizados():
    """Caso real (student_id 3901): 6 filas, 2 personas."""
    reg = _Reg(1, **_con_autorizados(6, nombre_repetido=True))
    hallazgos = inc.detectar(reg)

    assert [h.tipo for h in hallazgos] == ["exceso_autorizados"]
    assert "6 personas autorizadas" in hallazgos[0].detalle
    assert "Solo 1 son distintas" in hallazgos[0].detalle


def test_duplicados_sin_exceder_el_maximo():
    """3 filas para 1 persona: no excede 4, pero sigue siendo un duplicado."""
    reg = _Reg(1, **_con_autorizados(3, nombre_repetido=True))

    assert [h.tipo for h in inc.detectar(reg)] == ["autorizados_duplicados"]


def test_el_telefono_se_normaliza_para_comparar():
    reg = _Reg(1, **{
        "autorizado_1_nombre": "Ana López", "autorizado_1_telefono": "33 1234 5678",
        "autorizado_2_nombre": "ANA  LOPEZ", "autorizado_2_telefono": "+52 3312345678",
    })
    devueltas, distintas = inc.analizar_autorizados(reg.datos)

    assert (devueltas, distintas) == (2, 1)


# ── CURP duplicada y lote ────────────────────────────────────────────────

def test_curp_repetida_entre_dos_alumnos():
    """Caso real: dos hermanos Lira Gutierrez comparten la misma CURP."""
    a = _Reg(1, curp="LIGC170101MJCXXX00", nombre="Chelsea Renata",
             apellido="Lira Gutierrez")
    b = _Reg(2, curp="LIGC170101MJCXXX00", nombre="Christopher",
             apellido="Lira Gutierrez")

    assert inc.curps_duplicadas([a, b]) == {"LIGC170101MJCXXX00"}
    resultado = inc.analizar_lote([a, b])
    assert [i.tipo for i in resultado[1]] == ["curp_duplicada"]
    assert [i.tipo for i in resultado[2]] == ["curp_duplicada"]


def test_el_lote_solo_incluye_registros_con_incidencias():
    limpio = _Reg(1, curp="LOES170101HJCXXX00", nombre="Santiago",
                  apellido="Lopez Espinoza")
    sucio = _Reg(2, curp="MOQC170129HJCRNSA0", nombre="Santiago",
                 apellido="Lopez Espinoza")

    resultado = inc.analizar_lote([limpio, sucio])

    assert set(resultado) == {2}


def test_un_registro_puede_acumular_varias_incidencias():
    reg = _Reg(1, curp="MOQC170129HJCRNSA0", nombre="Santiago",
               apellido="Lopez Espinoza", **_con_autorizados(6, True))

    assert {h.tipo for h in inc.detectar(reg)} == {
        "curp_incoherente", "exceso_autorizados",
    }


def test_registro_sin_datos_no_revienta():
    class Vacio:
        id = 1
        datos = None

    assert inc.detectar(Vacio()) == []


# ── Resumen para el footer ───────────────────────────────────────────────

def test_el_resumen_agrupa_y_ordena_por_gravedad():
    hallazgos = [
        inc.Incidencia("exceso_autorizados", "x", "y"),
        inc.Incidencia("curp_incoherente", "x", "y"),
        inc.Incidencia("curp_incoherente", "x", "y"),
    ]

    assert inc.resumir(hallazgos) == "2 CURP no concuerda, 1 exceso de autorizados"


def test_el_resumen_de_una_lista_vacia_es_vacio():
    assert inc.resumir([]) == ""
