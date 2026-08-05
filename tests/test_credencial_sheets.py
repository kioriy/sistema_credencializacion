"""Pruebas del resguardo del JSON de service account de Google Sheets.

La app guarda en sus ajustes la RUTA del archivo, no una copia, así que dejarlo
en Descargas la rompe en cuanto el sistema limpia esa carpeta. Estas pruebas
fijan que el archivo se valide antes de tocarse, que termine en la carpeta
estable del sistema operativo y que nada se pierda por el camino.
"""
from __future__ import annotations

import json

import pytest

from credencializacion.adapters import sheets


@pytest.fixture()
def carpeta_credenciales(tmp_path, monkeypatch):
    """Redirige la carpeta de credenciales a una temporal."""
    destino = tmp_path / "app" / "credenciales"

    def _fake():
        destino.mkdir(parents=True, exist_ok=True)
        return destino

    monkeypatch.setattr(
        "credencializacion.utils.paths.get_credentials_dir", _fake,
    )
    return destino


@pytest.fixture()
def json_valido(tmp_path, monkeypatch):
    """Un JSON que el cargador de credenciales acepta.

    Se sustituye la validación de Google: construir una llave RSA real solo
    para probar el movimiento de un archivo sería lento y no aporta.
    """
    archivo = tmp_path / "descargas" / "miescuela-ad498-abc123.json"
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps({
        "type": "service_account",
        "project_id": "miescuela-ad498",
        "client_email": "miescuelanet@miescuela-ad498.iam.gserviceaccount.com",
    }))
    monkeypatch.setattr(
        sheets, "load_service_account_credentials", lambda ruta: object(),
    )
    return archivo


# ── Camino feliz ─────────────────────────────────────────────────────────

def test_la_credencial_termina_en_la_carpeta_de_la_app(
    carpeta_credenciales, json_valido,
):
    destino = sheets.instalar_credencial_sheets(json_valido)

    assert destino == carpeta_credenciales / sheets.CREDENCIAL_SHEETS_NOMBRE
    assert destino.exists()
    assert json.loads(destino.read_text())["project_id"] == "miescuela-ad498"


def test_el_nombre_se_normaliza(carpeta_credenciales, json_valido):
    """La ruta guardada no debe depender del nombre aleatorio de Google."""
    destino = sheets.instalar_credencial_sheets(json_valido)

    assert destino.name == "google-sheets.json"


def test_el_original_se_retira(carpeta_credenciales, json_valido):
    sheets.instalar_credencial_sheets(json_valido)

    assert not json_valido.exists()


def test_permisos_de_solo_el_dueno(carpeta_credenciales, json_valido):
    destino = sheets.instalar_credencial_sheets(json_valido)

    assert destino.stat().st_mode & 0o777 == 0o600


# ── Que nada se pierda ───────────────────────────────────────────────────

def test_la_credencial_previa_se_conserva(carpeta_credenciales, json_valido):
    """Cambiar de clave no debe destruir la anterior sin dejar rastro."""
    previa = carpeta_credenciales / sheets.CREDENCIAL_SHEETS_NOMBRE
    previa.parent.mkdir(parents=True, exist_ok=True)
    previa.write_text('{"project_id": "la-vieja"}')

    sheets.instalar_credencial_sheets(json_valido)

    respaldo = previa.with_suffix(previa.suffix + ".anterior")
    assert json.loads(respaldo.read_text())["project_id"] == "la-vieja"
    assert json.loads(previa.read_text())["project_id"] == "miescuela-ad498"


def test_reinstalar_la_misma_credencial_no_la_borra(
    carpeta_credenciales, json_valido,
):
    """Volver a elegir el archivo ya resguardado no debe dejarlo sin contenido."""
    destino = sheets.instalar_credencial_sheets(json_valido)

    otra_vez = sheets.instalar_credencial_sheets(destino)

    assert otra_vez == destino
    assert destino.exists()
    assert json.loads(destino.read_text())["project_id"] == "miescuela-ad498"


# ── Validación antes de tocar nada ───────────────────────────────────────

def test_un_json_invalido_no_mueve_nada(carpeta_credenciales, tmp_path, monkeypatch):
    malo = tmp_path / "descargas" / "cualquier-cosa.json"
    malo.parent.mkdir(parents=True, exist_ok=True)
    malo.write_text('{"algo": 1}')

    def _falla(_ruta):
        raise ValueError("no es un JSON de service account")

    monkeypatch.setattr(sheets, "load_service_account_credentials", _falla)

    with pytest.raises(ValueError):
        sheets.instalar_credencial_sheets(malo)

    assert malo.exists()  # el original sigue intacto
    assert not (carpeta_credenciales / sheets.CREDENCIAL_SHEETS_NOMBRE).exists()


def test_un_archivo_inexistente_falla_claro(carpeta_credenciales, tmp_path, monkeypatch):
    def _falla(ruta):
        raise FileNotFoundError(f"No se encontró: {ruta}")

    monkeypatch.setattr(sheets, "load_service_account_credentials", _falla)

    with pytest.raises(FileNotFoundError):
        sheets.instalar_credencial_sheets(tmp_path / "no-existe.json")


# ── Carpeta por sistema operativo ────────────────────────────────────────

@pytest.mark.parametrize("sistema, esperado", [
    ("Darwin", ("Library", "Application Support", "Credencializacion", "credenciales")),
    ("Linux", ("Credencializacion", "credenciales")),
])
def test_la_carpeta_depende_del_sistema(monkeypatch, tmp_path, sistema, esperado):
    from credencializacion.utils import paths

    monkeypatch.setattr(paths.platform, "system", lambda: sistema)
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))

    carpeta = paths.get_credentials_dir()

    assert carpeta.parts[-len(esperado):] == esperado
    assert carpeta.is_dir()


def test_la_carpeta_es_privada(monkeypatch, tmp_path):
    from credencializacion.utils import paths

    monkeypatch.setattr(paths.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))

    carpeta = paths.get_credentials_dir()

    assert carpeta.stat().st_mode & 0o777 == 0o700
