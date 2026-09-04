"""Pruebas de composición de PDFs desde una carpeta de diseños (folder_compose)."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from credencializacion.renderer.folder_compose import (
    compose_from_folder,
    resolve_folder_sides,
)


def _mkimg(path: Path, color=(120, 120, 120)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (340, 216), color).save(path)


def _pdf_pages(path: str | Path) -> int:
    data = Path(path).read_bytes()
    # Conteo aproximado suficiente para el test: páginas menos el nodo /Pages.
    return data.count(b"/Type /Page") - data.count(b"/Type /Pages")


def test_paired_por_orden(tmp_path: Path) -> None:
    for i in range(1, 4):
        _mkimg(tmp_path / "frente" / f"c{i}.png")
        _mkimg(tmp_path / "vuelta" / f"c{i}.png")
    sides = resolve_folder_sides(tmp_path)
    assert sides.mode == "paired"
    assert sides.n_front == 3 and sides.n_back == 3
    f, v = compose_from_folder(sides, tmp_path / "out")
    assert Path(f).exists() and v and Path(v).exists()
    assert _pdf_pages(f) == 2 and _pdf_pages(v) == 2  # 3 credenciales, 2 por hoja


def test_single_back_para_todos(tmp_path: Path) -> None:
    for i in range(1, 5):
        _mkimg(tmp_path / "frente" / f"c{i}.png")
    _mkimg(tmp_path / "vuelta" / "comun.png")
    sides = resolve_folder_sides(tmp_path)
    assert sides.mode == "single_back"
    assert sides.backs is not None and len(sides.backs) == 4
    assert len({str(b) for b in sides.backs}) == 1  # misma vuelta repetida
    _, v = compose_from_folder(sides, tmp_path / "out")
    assert _pdf_pages(v) == 2


def test_only_front_no_genera_vueltas(tmp_path: Path) -> None:
    for i in range(1, 3):
        _mkimg(tmp_path / "frente" / f"c{i}.png")
    sides = resolve_folder_sides(tmp_path)
    assert sides.mode == "only_front" and sides.backs is None
    f, v = compose_from_folder(sides, tmp_path / "out")
    assert v is None
    assert not (tmp_path / "out" / "vueltas.pdf").exists()


def test_mismatch_deja_huecos_y_avisa(tmp_path: Path) -> None:
    for i in range(1, 4):
        _mkimg(tmp_path / "frente" / f"c{i}.png")
    for i in range(1, 3):
        _mkimg(tmp_path / "vuelta" / f"c{i}.png")
    sides = resolve_folder_sides(tmp_path)
    assert sides.mode == "mismatch"
    assert sides.backs is not None
    assert sides.backs[-1] is None  # hueco en blanco para conservar el emparejado
    assert sides.warning and "no coinciden" in sides.warning
    _, v = compose_from_folder(sides, tmp_path / "out")
    assert _pdf_pages(v) == 2


def test_orden_natural_de_nombres(tmp_path: Path) -> None:
    for i in (1, 2, 10):
        _mkimg(tmp_path / "frente" / f"img{i}.png")
    sides = resolve_folder_sides(tmp_path)
    assert [p.name for p in sides.fronts] == ["img1.png", "img2.png", "img10.png"]


def test_carpeta_vacia(tmp_path: Path) -> None:
    sides = resolve_folder_sides(tmp_path)
    assert sides.mode == "empty" and not sides.fronts and sides.warning


def test_imagenes_en_raiz_sin_subcarpetas(tmp_path: Path) -> None:
    # Sin subcarpetas frente/vuelta: la raíz se toma como frentes, sin vueltas.
    for i in range(1, 3):
        _mkimg(tmp_path / f"c{i}.png")
    sides = resolve_folder_sides(tmp_path)
    assert sides.mode == "only_front" and sides.n_front == 2
