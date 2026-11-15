"""El lienzo del diseñador queda encuadrado al cambiar de orientación.

Lo que reportó el operador: al abrir la app, entrar al editor y pasar el
lienzo a vertical, se le recortaban los bordes de arriba y abajo; el lienzo
seguía dibujado con la escala del horizontal hasta que la ventana cambiaba de
tamaño (al maximizar) y la vista se reencuadraba.

La vista solo reencuadraba en ``resizeEvent`` y ``showEvent``, y cambiar de
orientación no cambia el tamaño de la vista: cambia el del lienzo. De ahí la
prueba, que comprueba que el lienzo completo cabe en la vista sin que nada
cambie de tamaño.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")

# Sin pantalla: Qt dibuja contra un buffer. Se fija antes de crear la app.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from credencializacion.ui.widgets.canvas import CredentialScene, CredentialView  # noqa: E402

# Tamaños de la credencial, en cm, como los usa el editor.
HORIZONTAL = (8.5, 5.4)
VERTICAL = (5.4, 8.5)

# La vista arranca apaisada, como el contenedor del editor en una ventana sin
# maximizar: es el caso en el que se veía el recorte.
VISTA = (620, 350)


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:  # pragma: no cover - depende del entorno
            pytest.skip(f"No se pudo crear la aplicación Qt: {exc}")
    if not isinstance(app, QApplication):  # pragma: no cover - orden de pruebas
        pytest.skip("Ya existe una app Qt sin widgets en este proceso.")
    return app


@pytest.fixture
def vista(qt_app):
    scene = CredentialScene()
    scene.set_physical_size(*HORIZONTAL)
    view = CredentialView(scene)
    view.resize(*VISTA)
    view.show()
    qt_app.processEvents()
    yield view
    view.hide()
    view.deleteLater()
    qt_app.processEvents()


def _recorte(view: CredentialView) -> tuple[float, float, float, float]:
    """Cuánto se sale el lienzo de la vista por cada lado, en píxeles."""
    caja = view.mapFromScene(view.sceneRect()).boundingRect()
    vp = view.viewport().rect()
    return (
        vp.top() - caja.top(), caja.bottom() - vp.bottom(),
        vp.left() - caja.left(), caja.right() - vp.right(),
    )


def _cabe(view: CredentialView) -> bool:
    return all(lado <= 1 for lado in _recorte(view))


def test_el_lienzo_horizontal_cabe_en_la_vista(vista):
    assert _cabe(vista), _recorte(vista)


def test_al_pasar_a_vertical_el_lienzo_sigue_completo(vista):
    """El bug: la vista no cambia de tamaño, el lienzo sí."""
    vista.scene().set_physical_size(*VERTICAL)

    assert _cabe(vista), _recorte(vista)
    # Y de pie: más alto que ancho en pantalla.
    caja = vista.mapFromScene(vista.sceneRect()).boundingRect()
    assert caja.height() > caja.width()


def test_ir_y_venir_entre_orientaciones_no_descuadra(vista):
    for _ in range(3):
        vista.scene().set_physical_size(*VERTICAL)
        assert _cabe(vista), ("vertical", _recorte(vista))
        vista.scene().set_physical_size(*HORIZONTAL)
        assert _cabe(vista), ("horizontal", _recorte(vista))


def test_el_lienzo_aprovecha_el_alto_disponible(vista):
    """Encuadrado quiere decir pegado al lado corto, no encogido de más."""
    vista.scene().set_physical_size(*VERTICAL)

    caja = vista.mapFromScene(vista.sceneRect()).boundingRect()
    assert caja.height() >= vista.viewport().height() - 6
