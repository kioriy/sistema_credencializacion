import re
import sys
from pathlib import Path

content = Path('src/credencializacion/ui/pages/control_panel.py').read_text()

worker_code = """
class SyncWorker(QThread):
    progress = Signal(str, str, bool)
    finished_ok = Signal(int, int)
    failed = Signal(str)

    def run(self) -> None:
        from credencializacion.adapters.miescuela import MiEscuelaAdapter
        from credencializacion.db.engine import DatabaseSession
        from credencializacion.db.models import Cliente, Registro
        from datetime import datetime

        BASE_URL = "https://app.miescuela.net"
        API_KEY = "7c9e6679-7425-40de-944b-e07fc1f90ae7"

        self.progress.emit("⏳ Sincronizando escuelas con MiEscuela.net...", "info", False)

        try:
            adapter = MiEscuelaAdapter(base_url=BASE_URL, api_key=API_KEY)

            # ── 1. Obtener lista de escuelas ───────────────────────────
            try:
                schools = adapter.fetch_schools()
            except ConnectionError:
                self.progress.emit("⚠ Endpoint /schools no disponible, usando fallback...", "warning", False)
                records = adapter.fetch_records(school_id=1, status="all")
                if records:
                    school_name = records[0].get("escuela", "Escuela 1")
                    schools = [{
                        "id": 1,
                        "name": school_name,
                        "cct": "",
                        "school_level": records[0].get("nivel_escolar", ""),
                        "status": "active",
                        "address": "",
                        "logo_url": records[0].get("logo_escuela", ""),
                        "total_students": len(records),
                    }]
                else:
                    schools = []

            if not schools:
                self.progress.emit("⚠ No se encontraron escuelas asociadas a esta clave API.", "warning", True)
                return

            self.progress.emit(f"💾 Guardando {len(schools)} escuelas...", "info", False)

            # ── 2. Upsert de escuelas en `clientes` ────────────────────
            cliente_map: dict[int, int] = {}
            with DatabaseSession() as session:
                for school_data in schools:
                    api_id = school_data.get("id")
                    existing = session.query(Cliente).filter_by(
                        school_api_id=api_id
                    ).first()

                    if existing:
                        existing.nombre = school_data.get("name", existing.nombre)
                        existing.cct = school_data.get("cct")
                        existing.school_level = school_data.get("school_level")
                        existing.address = school_data.get("address")
                        existing.logo_path = school_data.get("logo_url")
                        existing.total_students = school_data.get("total_students")
                        session.flush()
                        cliente_map[api_id] = existing.id
                    else:
                        nuevo = Cliente(
                            nombre=school_data.get("name", "Sin nombre"),
                            tipo="escuela",
                            api_key=API_KEY,
                            api_base_url=BASE_URL,
                            school_api_id=api_id,
                            cct=school_data.get("cct"),
                            school_level=school_data.get("school_level"),
                            address=school_data.get("address"),
                            logo_path=school_data.get("logo_url"),
                            total_students=school_data.get("total_students"),
                        )
                        session.add(nuevo)
                        session.flush()
                        cliente_map[api_id] = nuevo.id

            # ── 3. Para cada escuela: fetch alumnos y hacer upsert ─────
            total_alumnos = 0
            for school_data in schools:
                api_id = school_data.get("id")
                local_cliente_id = cliente_map.get(api_id)
                if not local_cliente_id:
                    continue

                self.progress.emit(
                    f"⬇ Descargando alumnos de {school_data.get('name', '')}...", "info", False
                )
                try:
                    raw_records = adapter.fetch_records(school_id=api_id, status="all")
                except Exception:
                    continue

                if not raw_records:
                    continue

                from credencializacion.utils.images import detect_image_attributes
                known_attrs: list[str] = []
                _seen_attr: set[str] = set()
                for _rec in raw_records:
                    if not isinstance(_rec, dict):
                        continue
                    for _k, _v in _rec.items():
                        if _k in _seen_attr or isinstance(_v, (list, dict)):
                            continue
                        _seen_attr.add(_k)
                        known_attrs.append(_k)
                        
                image_attrs = detect_image_attributes(raw_records)

                with DatabaseSession() as session:
                    for rec_data in raw_records:
                        enrollment = rec_data.get("enrollment_code") or rec_data.get("matricula", "")
                        existing_reg = session.query(Registro).filter_by(
                            cliente_id=local_cliente_id,
                            enrollment_code=enrollment,
                        ).first()

                        if existing_reg:
                            existing_reg.datos = rec_data
                            existing_reg.credential_status = rec_data.get("estado_credencial")
                            existing_reg.qr_data = rec_data.get("qr_data") or rec_data.get("photo_url", "")
                            existing_reg.photo_path = rec_data.get("photo_url", "")
                        else:
                            nuevo_reg = Registro(
                                cliente_id=local_cliente_id,
                                datos=rec_data,
                                enrollment_code=enrollment,
                                credential_status=rec_data.get("estado_credencial"),
                                qr_data=rec_data.get("qr_data") or rec_data.get("photo_url", ""),
                                photo_path=rec_data.get("photo_url", ""),
                                estado_impresion="pendiente",
                            )
                            session.add(nuevo_reg)

                    cliente_obj = session.query(Cliente).get(local_cliente_id)
                    if cliente_obj:
                        cfg = dict(cliente_obj.config or {})
                        cfg["known_attributes"] = known_attrs
                        cfg["image_attributes"] = image_attrs
                        cfg["last_sync"] = datetime.now().isoformat()
                        cliente_obj.config = cfg

                total_alumnos += len(raw_records)

            self.finished_ok.emit(len(schools), total_alumnos)

        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Error en sincronización API: %s", e)
            self.failed.emit(str(e))


class ControlPanel"""

content = content.replace("class ControlPanel", worker_code)


new_on_sync_api = """    def _on_sync_api(self) -> None:
        \"\"\"Sincroniza escuelas y alumnos desde la API de MiEscuela (asíncrono).\"\"\"
        self.btn_sync_api.setEnabled(False)
        self.set_status("Iniciando sincronización...", "info", toast=False)
        
        self._sync_worker = SyncWorker()
        self._sync_worker.progress.connect(self.set_status)
        self._sync_worker.finished_ok.connect(self._on_sync_finished)
        self._sync_worker.failed.connect(self._on_sync_failed)
        self._sync_worker.start()

    def _on_sync_finished(self, count_schools: int, count_students: int) -> None:
        self.btn_sync_api.setEnabled(True)
        self._load_clients_combo()
        self.set_status(f"✅ Sincronización completada — {count_schools} escuelas, {count_students} alumnos guardados.", "success", toast=True)
        self._sync_worker = None

    def _on_sync_failed(self, error_msg: str) -> None:
        self.btn_sync_api.setEnabled(True)
        self.set_status(f"❌ Error de sincronización: {error_msg}", "error", toast=True)
        self._sync_worker = None"""

# Find the old _on_sync_api method and replace it
import re

pattern = re.compile(r"    def _on_sync_api\(self\) -> None:.*?        except Exception as e:\n            self.set_status\(f\"❌ Error de sincronización: \{str\(e\)\}\", \"error\"\)\n", re.DOTALL)
content = pattern.sub(new_on_sync_api + "\n\n", content)


Path('src/credencializacion/ui/pages/control_panel.py').write_text(content)
