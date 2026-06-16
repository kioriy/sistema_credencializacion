"""
Adaptador para la API de MiEscuela.net.

Se conecta a los endpoints de credencialización del backend Laravel:
- ``GET /api/credentials/schools`` — lista de escuelas
- ``GET /api/credentials/export`` — alumnos por escuela

Header de autenticación: ``X-Credential-Key``.
"""
from __future__ import annotations

import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from credencializacion.adapters.base import DataAdapter

logger = logging.getLogger(__name__)

# ── Configuración de reintentos ──────────────────────────────────────
_DEFAULT_RETRIES = 3
_BACKOFF_FACTOR = 0.5
_RETRY_STATUS_CODES = (429, 500, 502, 503, 504)
_REQUEST_TIMEOUT = 30  # segundos


def _build_session(retries: int = _DEFAULT_RETRIES) -> requests.Session:
    """Crea una sesión HTTP con política de reintentos exponenciales."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=_BACKOFF_FACTOR,
        status_forcelist=list(_RETRY_STATUS_CODES),
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ── Columnas de alumnos que produce este adaptador ───────────────────
_STUDENT_COLUMNS: list[str] = [
    "nombre",
    "apellido",
    "matricula",
    "grado",
    "grupo",
    "turno",
    "nivel_escolar",
    "escuela",
    "logo_escuela",
    "photo_url",
    "estado_credencial",
    "reemplazos",
    "personas_autorizadas",
    "enrollment_code",
]


class MiEscuelaAdapter(DataAdapter):
    """Obtiene datos de escuelas y alumnos desde la API de MiEscuela.

    Args:
        base_url: URL base de la API (ej. ``https://app.miescuela.net``).
        api_key: Clave ``X-Credential-Key``.
    """

    ENDPOINT_SCHOOLS = "/api/credentials/schools"
    ENDPOINT_EXPORT = "/api/credentials/export"

    def __init__(
        self,
        base_url: str,
        api_key: str,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._session: requests.Session = _build_session()

    # ── Headers comunes ──────────────────────────────────────────────

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "X-Credential-Key": self._api_key,
            "Accept": "application/json",
        }

    # ── API: Escuelas ────────────────────────────────────────────────

    def fetch_schools(self) -> list[dict]:
        """Descarga la lista de escuelas asociadas a la API key.

        Returns:
            Lista de dicts con id, name, cct, school_level, status,
            address, logo_url, total_students.

        Raises:
            ConnectionError: Si la API no responde.
        """
        url = f"{self._base_url}{self.ENDPOINT_SCHOOLS}"
        logger.info("Consultando escuelas: %s", url)

        try:
            response = self._session.get(
                url, headers=self._headers, timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Error al obtener escuelas: %s", exc)
            raise ConnectionError(
                f"No se pudo obtener la lista de escuelas: {exc}"
            ) from exc

        payload = response.json()
        # Soportar respuesta directa (lista) o envuelta {"data": [...]}
        if isinstance(payload, list):
            schools = payload
        elif isinstance(payload, dict):
            schools = payload.get("data", payload.get("schools", []))
        else:
            schools = []

        logger.info("Se obtuvieron %d escuelas.", len(schools))
        return schools

    # ── API: Alumnos por escuela ─────────────────────────────────────

    def fetch_records(self, **kwargs) -> list[dict]:
        """Descarga y aplana los registros de alumnos de una escuela.

        Keyword Args:
            school_id: ID de la escuela (obligatorio).
            status: Filtro de estado ('all', 'pending', 'ready', etc.).
            page: Número de página.
            per_page: Registros por página.

        Returns:
            Lista de diccionarios con las columnas estándar.

        Raises:
            ConnectionError: Si la API no responde.
            ValueError: Si no se proporciona school_id.
        """
        school_id = kwargs.get("school_id")
        if not school_id:
            raise ValueError("Se requiere school_id para descargar alumnos.")

        url = f"{self._base_url}{self.ENDPOINT_EXPORT}"
        params: dict[str, Any] = {
            "school_id": str(school_id),
            "status": kwargs.get("status", "all"),
        }
        if "page" in kwargs:
            params["page"] = kwargs["page"]
        if "per_page" in kwargs:
            params["per_page"] = kwargs["per_page"]

        logger.info(
            "Consultando alumnos: %s (school_id=%s)", url, school_id,
        )

        try:
            response = self._session.get(
                url, headers=self._headers, params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.ConnectionError as exc:
            logger.error("Error de conexión con la API: %s", exc)
            raise ConnectionError(
                f"No se pudo conectar a la API de MiEscuela: {exc}"
            ) from exc
        except requests.HTTPError as exc:
            logger.error(
                "Error HTTP %s: %s", response.status_code, response.text[:200],
            )
            raise ConnectionError(
                f"Error HTTP {response.status_code} al consultar la API."
            ) from exc
        except requests.Timeout as exc:
            logger.error("Timeout al conectar con la API: %s", exc)
            raise ConnectionError(
                "La API de MiEscuela no respondió a tiempo."
            ) from exc

        payload = response.json()
        raw_records = self._extract_records(payload)

        logger.info("Se obtuvieron %d registros.", len(raw_records))
        return [self._flatten_record(rec) for rec in raw_records]

    def get_columns(self) -> list[str]:
        """Columnas estandarizadas que produce este adaptador."""
        return list(_STUDENT_COLUMNS)

    def get_source_name(self) -> str:
        return f"MiEscuela API ({self._base_url})"

    # ── Lógica interna ───────────────────────────────────────────────

    @staticmethod
    def _extract_records(payload: Any) -> list[dict]:
        """Extrae la lista de registros del JSON de respuesta."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return payload.get("data", payload.get("records", []))
        return []

    @staticmethod
    def _flatten_record(raw: dict) -> dict:
        """Aplana un registro JSON a columnas estándar."""
        classroom = raw.get("classroom") or {}
        school = raw.get("school") or {}
        authorized = raw.get("authorized_persons") or []

        return {
            "nombre": raw.get("first_name", ""),
            "apellido": raw.get("last_name", ""),
            "matricula": raw.get("enrollment_code", ""),
            "grado": classroom.get("grade", ""),
            "grupo": classroom.get("group_letter", ""),
            "turno": classroom.get("shift", ""),
            "nivel_escolar": classroom.get("school_level", ""),
            "escuela": school.get("name", ""),
            "logo_escuela": school.get("logo_url", ""),
            "photo_url": raw.get("photo_url", ""),
            "estado_credencial": raw.get("credential_status", ""),
            "reemplazos": raw.get("credential_replacement_count", 0),
            "personas_autorizadas": authorized,
            "enrollment_code": raw.get("enrollment_code", ""),
        }
