"""Lectura tolerante de pestañas de Google Sheets con encabezados duplicados."""
from __future__ import annotations

from credencializacion.adapters.sheets import read_worksheet_records


class _FakeWorksheet:
    """Doble de gspread: solo implementa get_all_values()."""

    def __init__(self, values):
        self._values = values

    def get_all_values(self):
        return self._values


def test_duplicados_gana_la_primera_columna():
    ws = _FakeWorksheet([
        ["matricula", "nombre", "grado", "grado"],   # 'grado' repetido
        ["A1", "Juan", "3", "OTRO"],
        ["A2", "Ana", "4", "X"],
    ])
    recs = read_worksheet_records(ws)
    assert recs == [
        {"matricula": "A1", "nombre": "Juan", "grado": "3"},   # gana la 1ª 'grado'
        {"matricula": "A2", "nombre": "Ana", "grado": "4"},
    ]


def test_encabezados_vacios_se_ignoran():
    ws = _FakeWorksheet([
        ["matricula", "", "nombre", ""],
        ["A1", "basura", "Juan", "mas basura"],
    ])
    recs = read_worksheet_records(ws)
    assert recs == [{"matricula": "A1", "nombre": "Juan"}]


def test_celdas_faltantes_quedan_vacias():
    ws = _FakeWorksheet([
        ["matricula", "nombre", "grado"],
        ["A1", "Juan"],   # fila más corta que el encabezado
    ])
    recs = read_worksheet_records(ws)
    assert recs == [{"matricula": "A1", "nombre": "Juan"}]  # 'grado' ausente → sin clave


def test_hoja_vacia():
    assert read_worksheet_records(_FakeWorksheet([])) == []


def test_solo_encabezado_sin_filas():
    assert read_worksheet_records(_FakeWorksheet([["matricula", "nombre"]])) == []
