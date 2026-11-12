"""Etapas de la credencial y reglas de mezcla de los filtros del padrón.

El punto delicado: en las escuelas que no exigen formulario, el estatus
visible del API (``credential_display_status``) se queda en
``sin_formulario`` aunque la credencial ya se haya impreso o entregado. Por
eso las etapas se leen de ``credential_status``, que no se tapa, y la tabla
muestra el avance real con una nota de lo que falte.
"""
from __future__ import annotations

import pytest

from credencializacion.services.estatus import (
    alternar,
    es_por_imprimir,
    esta_entregada,
    esta_lista_por_entregar,
    estado_visible,
    tiene_formulario,
    tiene_foto,
)


class _Reg:
    """Registro mínimo con la interfaz que usan los filtros."""

    def __init__(self, datos: dict, credential_status: str = "",
                 photo_path: str = "foto.jpg", estado_impresion: str = "pendiente") -> None:
        self._datos = datos
        self.photo_path = photo_path
        self.credential_status = credential_status
        self.estado_impresion = estado_impresion

    def get_dato(self, key, default=""):
        return self._datos.get(key, default)


def _api(display: str, etapa: str, *, foto=True, formulario=True) -> _Reg:
    """Registro como lo deja una sincronización con la API."""
    return _Reg(
        {
            "credential_display_status": display,
            "photo_status": foto,
            "form_status": formulario,
        },
        credential_status=etapa,
        photo_path="https://x/f.jpg" if foto else "",
    )


# ── Etapas en escuelas que SÍ exigen formulario ──────────────────────


def test_la_que_tiene_todo_y_no_se_ha_impreso_esta_por_imprimir():
    reg = _api("pending", "pending")

    assert es_por_imprimir(reg)
    assert not esta_lista_por_entregar(reg) and not esta_entregada(reg)
    assert tiene_foto(reg) and tiene_formulario(reg)


@pytest.mark.parametrize("etapa", ["printing", "ready"])
def test_lo_impreso_y_no_entregado_cuenta_como_lista_por_entregar(etapa):
    reg = _api(etapa, etapa)

    assert esta_lista_por_entregar(reg)
    assert not es_por_imprimir(reg) and not esta_entregada(reg)


def test_lo_entregado_sale_de_las_dos_etapas_de_trabajo():
    reg = _api("delivered", "delivered")

    assert esta_entregada(reg)
    assert not es_por_imprimir(reg) and not esta_lista_por_entregar(reg)


def test_sin_foto_no_hay_nada_que_imprimir():
    assert not es_por_imprimir(_api("sin_fotografia", "pending", foto=False))


def test_una_reposicion_no_entra_en_las_etapas():
    """Las reposiciones se trabajan desde el botón Reposiciones, no aquí."""
    reg = _api("replacement_requested", "replacement_requested")

    assert not es_por_imprimir(reg)
    assert not esta_lista_por_entregar(reg)
    assert not esta_entregada(reg)


# ── Escuelas que NO exigen formulario ────────────────────────────────
#
# El API manda display "sin_formulario" en las tres etapas; solo
# `credential_status` dice en cuál va.


def test_sin_formulario_tambien_se_imprime():
    reg = _api("sin_formulario", "pending", formulario=False)

    assert es_por_imprimir(reg)
    assert not tiene_formulario(reg)


def test_sin_formulario_ya_impresa_es_lista_por_entregar():
    reg = _api("sin_formulario", "ready", formulario=False)

    assert esta_lista_por_entregar(reg)
    assert not es_por_imprimir(reg)


def test_sin_formulario_ya_entregada_no_reaparece_como_pendiente():
    """El caso que hacía imposible repartir: entregada pero se veía igual."""
    reg = _api("sin_formulario", "delivered", formulario=False)

    assert esta_entregada(reg)
    assert not es_por_imprimir(reg) and not esta_lista_por_entregar(reg)


def test_no_entregadas_es_la_suma_de_las_dos_primeras_etapas():
    padron = [
        _api("sin_formulario", "pending", formulario=False),
        _api("sin_formulario", "ready", formulario=False),
        _api("sin_formulario", "delivered", formulario=False),
        _api("delivered", "delivered"),
    ]

    sin_entregar = [
        r for r in padron if es_por_imprimir(r) or esta_lista_por_entregar(r)
    ]

    assert len(sin_entregar) == 2
    assert all(not esta_entregada(r) for r in sin_entregar)


# ── Lo que muestra la columna ESTADO ─────────────────────────────────


def test_la_columna_muestra_el_avance_real_con_la_nota():
    assert estado_visible(_api("sin_formulario", "delivered", formulario=False)) == (
        "delivered", "sin formulario",
    )
    assert estado_visible(_api("sin_formulario", "ready", formulario=False)) == (
        "ready", "sin formulario",
    )
    # Una reposición tampoco debe quedar escondida tras "sin formulario".
    assert estado_visible(
        _api("sin_formulario", "replacement_requested", formulario=False)
    ) == ("replacement_requested", "sin formulario")


def test_antes_de_imprimir_manda_lo_que_falta():
    """Ahí lo accionable es el dato faltante, no la etapa."""
    assert estado_visible(_api("sin_formulario", "pending", formulario=False)) == (
        "sin_formulario", "",
    )
    assert estado_visible(_api("sin_fotografia", "pending", foto=False)) == (
        "sin_fotografia", "",
    )
    assert estado_visible(_api("pending", "pending")) == ("pending", "")


def test_lo_completo_no_lleva_nota():
    assert estado_visible(_api("delivered", "delivered")) == ("delivered", "")


# ── Sin estatus del backend (Google Sheets, importaciones) ───────────


def test_sin_estatus_del_backend_se_usa_el_estado_local():
    por_imprimir = _Reg({"form_status": True}, photo_path="/local/f.jpg")
    impresa = _Reg({"form_status": True}, photo_path="/local/f.jpg", estado_impresion="impreso")
    sin_foto = _Reg({"form_status": True}, photo_path="")

    assert es_por_imprimir(por_imprimir)
    assert esta_lista_por_entregar(impresa)
    assert not es_por_imprimir(sin_foto)


def test_un_registro_viejo_sin_form_status_se_infiere_del_display():
    """Sincronizaciones previas a `form_status`: manda el display del API."""
    assert tiene_formulario(_Reg({"credential_display_status": "pending"}))
    assert not tiene_formulario(_Reg({"credential_display_status": "sin_formulario"}))


# ── Mezcla de filtros ────────────────────────────────────────────────


def test_los_estatus_se_suman_entre_si():
    seleccion = alternar(set(), "por_imprimir")
    assert seleccion == {"por_imprimir"}

    seleccion = alternar(seleccion, "listas")
    assert seleccion == {"por_imprimir", "listas"}

    seleccion = alternar(seleccion, "sin_formulario")
    assert seleccion == {"por_imprimir", "listas", "sin_formulario"}


def test_volver_a_pulsar_una_pill_la_apaga():
    assert alternar({"por_imprimir", "listas"}, "listas") == {"por_imprimir"}
    # Apagar la última deja el padrón completo («Todos»).
    assert alternar({"por_imprimir"}, "por_imprimir") == set()


def test_hermanos_apaga_los_estatus_y_no_se_mezcla():
    assert alternar({"por_imprimir", "listas"}, "hermanos") == {"hermanos"}
    # Y al revés: elegir un estatus suelta hermanos.
    assert alternar({"hermanos"}, "por_imprimir") == {"por_imprimir"}
    # Pulsarla de nuevo la apaga.
    assert alternar({"hermanos"}, "hermanos") == set()


def test_incidencias_tampoco_se_mezcla():
    assert alternar({"por_imprimir"}, "incidencias") == {"incidencias"}
    assert alternar({"incidencias"}, "hermanos") == {"hermanos"}
