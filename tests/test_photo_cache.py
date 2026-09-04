"""Pruebas de la caché de fotos por URL compartida entre panel y motor de PDF.

Cubren el arreglo del bug de fotos que salían en blanco de forma aleatoria al
imprimir: el motor de PDF ahora reutiliza la caché persistente por URL (la misma
que llena el panel de control) en vez de re-descargar en cada render.
"""
from __future__ import annotations

import hashlib
import types

import pytest

from credencializacion.adapters import image_cache
from credencializacion.renderer.pdf_engine import PDFEngine


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """Apunta la caché de imágenes a un directorio temporal."""
    monkeypatch.setattr(image_cache, "get_image_cache_dir", lambda *a, **k: tmp_path)
    return tmp_path


def test_clave_por_url_es_sha1_img(cache_dir):
    url = "https://x/storage/photos/42.jpg"
    esperado = cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".img")
    assert image_cache.photo_url_cache_path(url) == esperado


def test_cache_hit_no_toca_la_red(cache_dir, monkeypatch):
    url = "https://x/foto.jpg"
    dest = image_cache.photo_url_cache_path(url)
    dest.write_bytes(b"DATOSJPEG")

    def _boom(*a, **k):  # requests.get no debe llamarse en un hit
        raise AssertionError("no debe descargar cuando ya está en caché")

    monkeypatch.setattr(image_cache.requests, "get", _boom)
    assert image_cache.fetch_photo_to_cache(url) == dest


def test_reintenta_y_persiste(cache_dir, monkeypatch):
    url = "https://x/lenta.jpg"
    monkeypatch.setattr(image_cache.time, "sleep", lambda *_: None)

    llamadas = {"n": 0}

    class _Resp:
        content = b"IMG"
        def raise_for_status(self):  # noqa: D401
            return None

    def _flaky(*a, **k):
        llamadas["n"] += 1
        if llamadas["n"] < 3:
            raise image_cache.requests.RequestException("timeout")
        return _Resp()

    monkeypatch.setattr(image_cache.requests, "get", _flaky)
    dest = image_cache.fetch_photo_to_cache(url, retries=3)
    assert dest is not None and dest.exists() and dest.read_bytes() == b"IMG"
    assert llamadas["n"] == 3
    # Sin temporales .part huérfanos tras la escritura atómica.
    assert not list(cache_dir.glob("*.part"))


def test_todos_los_intentos_fallan_devuelve_none(cache_dir, monkeypatch):
    url = "https://x/rota.jpg"
    monkeypatch.setattr(image_cache.time, "sleep", lambda *_: None)

    def _fail(*a, **k):
        raise image_cache.requests.RequestException("caída")

    monkeypatch.setattr(image_cache.requests, "get", _fail)
    assert image_cache.fetch_photo_to_cache(url, retries=2) is None


def test_respuesta_vacia_no_crea_archivo(cache_dir, monkeypatch):
    url = "https://x/vacia.jpg"
    monkeypatch.setattr(image_cache.time, "sleep", lambda *_: None)

    class _Empty:
        content = b""
        def raise_for_status(self):
            return None

    monkeypatch.setattr(image_cache.requests, "get", lambda *a, **k: _Empty())
    assert image_cache.fetch_photo_to_cache(url, retries=2) is None
    assert not image_cache.photo_url_cache_path(url).exists()


def test_engine_download_image_usa_la_cache(cache_dir, monkeypatch):
    """El wrapper del motor delega en la caché y memoiza en memoria."""
    url = "https://x/foto.jpg"
    dest = cache_dir / "resuelta.img"
    dest.write_bytes(b"X")

    llamadas = {"n": 0}

    def _fake_fetch(u, **k):
        llamadas["n"] += 1
        return dest

    monkeypatch.setattr(image_cache, "fetch_photo_to_cache", _fake_fetch)

    ns = types.SimpleNamespace()
    r1 = PDFEngine._download_image(ns, url)
    r2 = PDFEngine._download_image(ns, url)  # segunda vez: memoria, sin re-fetch
    assert r1 == str(dest) and r2 == str(dest)
    assert llamadas["n"] == 1  # solo una resolución; la 2ª vino del atajo memoria


def test_clear_url_cache_borra_solo_las_dadas(cache_dir):
    a = "https://x/a.jpg"
    b = "https://x/b.jpg"
    c = "https://x/c.jpg"
    for u in (a, b, c):
        image_cache.photo_url_cache_path(u).write_bytes(b"IMG")

    borradas = image_cache.clear_url_cache({a, b})
    assert borradas == 2
    assert not image_cache.photo_url_cache_path(a).exists()
    assert not image_cache.photo_url_cache_path(b).exists()
    assert image_cache.photo_url_cache_path(c).exists()  # la no incluida queda


def test_clear_url_cache_ignora_urls_vacias_o_faltantes(cache_dir):
    # URL vacía y una que no existe en disco no cuentan ni fallan.
    assert image_cache.clear_url_cache(["", None, "https://x/no-existe.jpg"]) == 0


def test_paridad_de_clave_con_panel_de_control(cache_dir):
    """El panel de control y el motor deben resolver a la MISMA ruta."""
    from credencializacion.ui.pages.control_panel import ControlPanel
    url = "https://x/foto-paridad.jpg"
    assert ControlPanel._photo_disk_path(url) == image_cache.photo_url_cache_path(url)
