"""
Worker de sincronización con Google Sheets ("clientes negocios").

Modelo de datos: un documento de Google Sheets con una pestaña por cliente
(negocio). La primera fila de cada pestaña son los nombres de atributo
(columnas); cada fila siguiente es un registro, identificado de forma única
por el valor de su primera columna (equivalente al ``enrollment_code`` del
flujo de la API miescuela.net).

Un cliente puede tener una pestaña sin columnas (registrada mientras solo
necesita la plantilla base, sin atributos dinámicos aún). Ese estado se
guarda explícitamente como ``known_attributes: []`` — distinto de "nunca
sincronizado" — para que el editor de plantillas pueda mostrarlo con una
etiqueta propia en vez de pedir sincronizar.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class SheetsSyncWorker(QThread):
    """Sincroniza el documento de Google Sheets configurado en segundo plano.

    Emite ``progress`` con mensajes de estado para el footer, ``finished_ok``
    con (clientes, registros, reporte) al terminar y ``failed`` ante un error
    que impide continuar (credenciales inválidas, documento no encontrado).
    Errores acotados a una sola pestaña no abortan el resto de la
    sincronización — se acumulan en el reporte.
    """

    progress = Signal(str)
    finished_ok = Signal(int, int, dict)  # clientes, registros, reporte
    failed = Signal(str)

    def __init__(self, credentials_path: str, document_name: str) -> None:
        super().__init__()
        self._credentials_path = credentials_path
        self._document_name = document_name

    def run(self) -> None:  # noqa: D401
        from credencializacion.adapters.sheets import (
            authorize_gspread_client,
            open_spreadsheet_by_name,
        )
        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import Cliente, Registro
        from credencializacion.services.sync_registros import purge_stale_records

        if not self._credentials_path:
            self.failed.emit(
                "No hay credenciales de Google configuradas. Ve a "
                "Configuración → Sincronización con Google Sheets."
            )
            return

        self.progress.emit("⏳ Conectando con Google Sheets...")
        try:
            client = authorize_gspread_client(Path(self._credentials_path))
            spreadsheet = open_spreadsheet_by_name(client, self._document_name)
        except Exception as e:  # noqa: BLE001
            logger.error("Error al conectar con Google Sheets: %s", e)
            self.failed.emit(str(e))
            return

        try:
            worksheets = spreadsheet.worksheets()
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"No se pudieron listar las pestañas: {e}")
            return

        if not worksheets:
            self.failed.emit(
                f"El documento '{self._document_name}' no tiene pestañas."
            )
            return

        total_registros = 0
        total_depurados = 0
        colas_afectadas: list[str] = []
        sin_atributos: list[str] = []
        errores_pestanas: list[str] = []

        for worksheet in worksheets:
            nombre_cliente = worksheet.title
            self.progress.emit(f"⬇ Descargando pestaña '{nombre_cliente}'...")

            try:
                header_row = worksheet.row_values(1)
            except Exception as e:  # noqa: BLE001
                errores_pestanas.append(f"{nombre_cliente} ({e})")
                continue

            known_attrs = [h.strip() for h in header_row if h and h.strip()]

            # Encabezado leído con éxito: siempre se puede identificar y
            # registrar al cliente, aunque falle la descarga de sus filas.
            rows: list[dict] = []
            rows_error: str | None = None
            if known_attrs:
                try:
                    rows = worksheet.get_all_records(default_blank="")
                except Exception as e:  # noqa: BLE001
                    # Encabezados duplicados/ambiguos u otro problema puntual
                    # de esta pestaña: se reporta pero NO se oculta al
                    # cliente — solo se deja su padrón sin tocar este ciclo.
                    rows_error = str(e)
                    errores_pestanas.append(f"{nombre_cliente} ({e})")

            with DatabaseSession() as session:
                # Identidad: (nombre, tipo="empresa"). No hay un id numérico
                # estable como school_api_id — la pestaña ES la identidad.
                cliente_obj = (
                    session.query(Cliente)
                    .filter_by(nombre=nombre_cliente, tipo="empresa")
                    .first()
                )
                if cliente_obj is None:
                    cliente_obj = Cliente(nombre=nombre_cliente, tipo="empresa")
                    session.add(cliente_obj)
                    session.flush()

                cfg = dict(cliente_obj.config or {})
                cfg["known_attributes"] = known_attrs
                cfg["sheets_managed"] = True
                cfg["last_sync"] = datetime.now().isoformat()
                cliente_obj.config = cfg
                cliente_id = cliente_obj.id

                if not known_attrs:
                    # Pestaña "sin atributos": solo se registra el cliente
                    # (plantilla base). No hay columnas con que identificar
                    # filas, así que no se depura nada este ciclo — evita
                    # que un encabezado vacío por accidente borre registros
                    # previos que sí tenían datos reales.
                    sin_atributos.append(nombre_cliente)
                    continue

                if rows_error is not None:
                    # El encabezado es válido pero no se pudieron leer las
                    # filas: por seguridad no se toca ningún registro
                    # existente de este cliente este ciclo (ya se reportó
                    # el error arriba).
                    continue

                primera_col = known_attrs[0]
                raw_records: list[dict] = []
                for row in rows:
                    key = str(row.get(primera_col, "") or "").strip()
                    if not key:
                        continue
                    datos = {k: str(v) if v is not None else "" for k, v in row.items()}
                    datos["enrollment_code"] = key
                    raw_records.append(datos)

                for rec_data in raw_records:
                    key = rec_data["enrollment_code"]
                    existing_reg = session.query(Registro).filter_by(
                        cliente_id=cliente_id, enrollment_code=key,
                    ).first()
                    if existing_reg:
                        existing_reg.datos = rec_data
                    else:
                        session.add(
                            Registro(
                                cliente_id=cliente_id,
                                datos=rec_data,
                                enrollment_code=key,
                                estado_impresion="pendiente",
                            )
                        )

                depurados, colas = purge_stale_records(
                    session, cliente_id, raw_records
                )
                total_depurados += depurados
                for nombre_cola in colas:
                    if nombre_cola not in colas_afectadas:
                        colas_afectadas.append(nombre_cola)

                total_registros += len(raw_records)

        reporte = {
            "depurados": total_depurados,
            "colas_afectadas": colas_afectadas,
            "sin_atributos": sin_atributos,
            "errores_pestanas": errores_pestanas,
        }
        self.finished_ok.emit(len(worksheets), total_registros, reporte)
