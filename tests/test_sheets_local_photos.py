"""Pruebas de las fotos locales para clientes de Google Sheets.

Cubren los helpers de rutas: carpeta base por escuela, resolución del valor de
la columna de foto (nombre de archivo → ruta local) y el índice de rutas del
sistema que se muestra en Configuración.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from credencializacion.utils import paths as P


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Redirige la carpeta de datos a un temporal."""
    monkeypatch.setattr(P, "_data_dir_cache", tmp_path, raising=False)
    monkeypatch.setattr(P, "get_data_dir", lambda: tmp_path)
    return tmp_path


def test_carpeta_base_por_escuela(data_dir):
    d = P.get_sheets_local_photos_dir("Escuela Primaria X")
    assert d == data_dir / "sheets_local_fotos" / "Escuela Primaria X"
    assert d.is_dir()  # se crea


def test_carpeta_base_sin_cliente(data_dir):
    d = P.get_sheets_local_photos_dir()
    assert d == data_dir / "sheets_local_fotos"
    assert d.is_dir()


def test_nombre_de_carpeta_saneado(data_dir):
    # Caracteres ilegales de sistema de archivos se sustituyen; conserva mayús.
    d = P.get_sheets_local_photos_dir('Colegio A/B: "C"')
    assert d.parent == data_dir / "sheets_local_fotos"
    assert "/" not in d.name and ":" not in d.name and '"' not in d.name
    assert d.name.startswith("Colegio A")


def test_resolver_nombre_de_archivo_relativo(data_dir):
    base = P.get_sheets_local_photos_dir("Esc")
    assert P.resolve_local_photo_path(base, "juan.jpeg") == str(base / "juan.jpeg")


def test_resolver_ruta_absoluta_se_respeta(data_dir, tmp_path):
    base = P.get_sheets_local_photos_dir("Esc")
    abs_path = str(tmp_path / "otra" / "foto.png")
    assert P.resolve_local_photo_path(base, abs_path) == abs_path


def test_resolver_url_se_respeta(data_dir):
    base = P.get_sheets_local_photos_dir("Esc")
    url = "https://cdn/x/juan.jpg"
    assert P.resolve_local_photo_path(base, url) == url


def test_apply_local_photos_muta_columnas_de_imagen(data_dir):
    from credencializacion.utils.images import apply_local_photos, detect_image_attributes

    base = P.get_sheets_local_photos_dir("Escuela Z")
    records = [
        {"matricula": "A1", "nombre": "Juan", "foto": "juan.jpeg"},
        {"matricula": "A2", "nombre": "Ana", "foto": ""},  # sin foto
        {"matricula": "A3", "nombre": "URL", "foto": "https://x/pep.jpg"},
    ]
    cols = detect_image_attributes(records)
    assert cols == ["foto"]
    apply_local_photos(records, cols, base)
    assert records[0]["foto"] == str(base / "juan.jpeg")   # nombre → ruta local
    assert records[1]["foto"] == ""                          # vacío se queda vacío
    assert records[2]["foto"] == "https://x/pep.jpg"         # URL intacta
    # El nombre suelto NO se resuelve (por eso hace falta unir la carpeta):
    from credencializacion.renderer.pdf_engine import PDFEngine
    import types
    ns = types.SimpleNamespace()
    assert PDFEngine._resolve_image_path(ns, "juan.jpeg") is None
    # La ruta local (si el archivo existiera) sí la tomaría; creamos el archivo:
    (base / "juan.jpeg").write_bytes(b"IMG")
    assert PDFEngine._resolve_image_path(ns, str(base / "juan.jpeg")) == str(base / "juan.jpeg")


def test_resolver_vacio(data_dir):
    base = P.get_sheets_local_photos_dir("Esc")
    assert P.resolve_local_photo_path(base, "") == ""
    assert P.resolve_local_photo_path(base, "   ") == ""


def test_indice_de_rutas_incluye_fotos_locales(data_dir):
    rutas = P.app_base_paths()
    etiquetas = [label for label, _ in rutas]
    assert "Fotos locales (Google Sheets)" in etiquetas
    # Todas son Paths existentes (los getters crean la carpeta).
    for _label, ruta in rutas:
        assert isinstance(ruta, Path)
