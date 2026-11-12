"""Estatus «pendiente» y reglas de mezcla de los filtros del padrón.

Pendiente es lo que falta por imprimir: foto y formulario listos y la
credencial todavía sin mandar a impresión. Lo que ya pasó por la impresora
(``printing``, ``ready``, ``delivered``) no cuenta.

Los filtros de estatus se suman entre sí —la combinación de trabajo es
«Pendientes» + «Sin formulario»— y «Hermanos»/«Incidencias» van solas.
"""
from __future__ import annotations

import pytest

from credencializacion.services.estatus import (
    alternar,
    es_pendiente,
    tiene_formulario,
    tiene_foto,
)


class _Reg:
    """Registro mínimo con la interfaz que usan los filtros."""

    def __init__(self, datos: dict, photo_path: str = "foto.jpg",
                 credential_status: str = "", estado_impresion: str = "pendiente") -> None:
        self._datos = datos
        self.photo_path = photo_path
        self.credential_status = credential_status
        self.estado_impresion = estado_impresion

    def get_dato(self, key, default=""):
        return self._datos.get(key, default)


def _api(display: str, *, foto=True, formulario=True, credencial="") -> _Reg:
    """Registro como lo deja una sincronización con la API."""
    return _Reg(
        {
            "credential_display_status": display,
            "photo_status": foto,
            "form_status": formulario,
        },
        photo_path="https://x/f.jpg" if foto else "",
        credential_status=credencial or display,
    )


# ── Qué cuenta como pendiente ────────────────────────────────────────


def test_pendiente_es_el_que_tiene_foto_y_formulario_y_no_se_ha_impreso():
    reg = _api("pending")

    assert es_pendiente(reg)
    assert tiene_foto(reg) and tiene_formulario(reg)


@pytest.mark.parametrize("display", ["printing", "ready", "delivered"])
def test_lo_que_ya_paso_por_la_impresora_no_es_pendiente(display):
    """Tienen foto y formulario, pero ya no faltan por imprimir."""
    reg = _api(display)

    assert tiene_foto(reg) and tiene_formulario(reg)
    assert not es_pendiente(reg)


@pytest.mark.parametrize("display,foto,formulario", [
    ("sin_formulario", True, False),
    ("sin_fotografia", False, True),
    ("sin_formulario", False, False),
])
def test_al_que_le_falta_un_dato_no_es_pendiente(display, foto, formulario):
    assert not es_pendiente(_api(display, foto=foto, formulario=formulario))


def test_replacement_requested_no_es_pendiente():
    """Las reposiciones tienen su propio flujo (botón Reposiciones)."""
    assert not es_pendiente(_api("replacement_requested"))


# ── Sin estatus del backend (Google Sheets, importaciones) ───────────


def test_sin_estatus_del_backend_se_deduce_de_la_foto_y_el_formulario():
    completo = _Reg({"form_status": True}, photo_path="/local/foto.jpg")
    sin_foto = _Reg({"form_status": True}, photo_path="")
    sin_formulario = _Reg({"form_status": False}, photo_path="/local/foto.jpg")

    assert es_pendiente(completo)
    assert not es_pendiente(sin_foto)
    assert not es_pendiente(sin_formulario)


def test_sin_estatus_del_backend_lo_ya_impreso_no_cuenta():
    impreso = _Reg(
        {"form_status": True}, photo_path="/local/foto.jpg",
        credential_status="ready",
    )
    en_cola = _Reg(
        {"form_status": True}, photo_path="/local/foto.jpg",
        estado_impresion="impreso",
    )

    assert not es_pendiente(impreso)
    assert not es_pendiente(en_cola)


def test_un_registro_viejo_sin_form_status_se_infiere_del_display():
    """Sincronizaciones previas a `form_status`: manda el display del API."""
    assert tiene_formulario(_Reg({"credential_display_status": "pending"}))
    assert not tiene_formulario(_Reg({"credential_display_status": "sin_formulario"}))


# ── Mezcla de filtros ────────────────────────────────────────────────


def test_los_estatus_se_suman_entre_si():
    seleccion = alternar(set(), "pendiente")
    assert seleccion == {"pendiente"}

    seleccion = alternar(seleccion, "sin_formulario")
    assert seleccion == {"pendiente", "sin_formulario"}

    seleccion = alternar(seleccion, "sin_foto")
    assert seleccion == {"pendiente", "sin_formulario", "sin_foto"}


def test_volver_a_pulsar_una_pill_la_apaga():
    seleccion = {"pendiente", "sin_formulario"}

    assert alternar(seleccion, "pendiente") == {"sin_formulario"}
    # Apagar la última deja el padrón completo («Todos»).
    assert alternar({"pendiente"}, "pendiente") == set()


def test_hermanos_apaga_los_estatus_y_no_se_mezcla():
    assert alternar({"pendiente", "sin_formulario"}, "hermanos") == {"hermanos"}
    # Y al revés: elegir un estatus suelta hermanos.
    assert alternar({"hermanos"}, "pendiente") == {"pendiente"}
    # Pulsarla de nuevo la apaga.
    assert alternar({"hermanos"}, "hermanos") == set()


def test_incidencias_tampoco_se_mezcla():
    assert alternar({"pendiente"}, "incidencias") == {"incidencias"}
    assert alternar({"incidencias"}, "hermanos") == {"hermanos"}
