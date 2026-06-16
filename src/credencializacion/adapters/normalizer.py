"""
Normalización y mapeo inteligente de columnas.

Usa fuzzy-matching (thefuzz) para auto-mapear encabezados de columna
provenientes de cualquier fuente a los atributos estándar del sistema.

Tres niveles de confianza:
- **auto** (≥85): mapeo automático sin intervención del usuario.
- **ambiguous** (60-84): requiere confirmación manual.
- **unmapped** (<60): no se encontró correspondencia.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from thefuzz import process as fuzz_process

logger = logging.getLogger(__name__)

# ── Atributos estándar del sistema ───────────────────────────────────
# Cada clave es el nombre canónico; los valores son alias conocidos
# (en español e inglés) que las fuentes podrían usar.

STANDARD_ATTRIBUTES: dict[str, list[str]] = {
    "nombre": [
        "nombre", "first_name", "nombres", "name", "primer_nombre",
        "nombre_alumno", "student_name",
    ],
    "apellido_paterno": [
        "apellido_paterno", "last_name", "apellido", "paterno",
        "primer_apellido", "fathers_last_name",
    ],
    "apellido_materno": [
        "apellido_materno", "mothers_last_name", "segundo_apellido",
        "materno", "apellido_2",
    ],
    "matricula": [
        "matricula", "matrícula", "enrollment_code", "enrollment",
        "clave_alumno", "student_id", "numero_control", "folio",
    ],
    "curp": [
        "curp", "clave_unica", "clave_curp",
    ],
    "grado": [
        "grado", "grade", "nivel", "año", "anio", "school_grade",
    ],
    "grupo": [
        "grupo", "group", "seccion", "sección", "section",
    ],
    "turno": [
        "turno", "shift", "jornada", "horario",
    ],
    "domicilio": [
        "domicilio", "address", "direccion", "dirección", "calle",
        "domicilio_alumno",
    ],
    "telefono": [
        "telefono", "teléfono", "phone", "celular", "tel", "movil",
        "phone_number",
    ],
    "email_tutor": [
        "email_tutor", "guardian_email", "correo_tutor", "email_padre",
        "correo_padre", "parent_email", "email_madre",
    ],
    "fecha_nacimiento": [
        "fecha_nacimiento", "date_of_birth", "birthdate", "nacimiento",
        "fecha_nac", "dob", "fdn",
    ],
    "tipo_sangre": [
        "tipo_sangre", "blood_type", "sangre", "grupo_sanguineo",
        "tipo_sanguineo",
    ],
    "photo_url": [
        "photo_url", "foto", "photo", "imagen", "image", "foto_url",
        "url_foto", "photo_path",
    ],
    "qr_data": [
        "qr_data", "qr", "qr_url", "codigo_qr", "qr_code", "qr_string",
    ],
}

# ── Umbrales de confianza ────────────────────────────────────────────
_THRESHOLD_AUTO = 85       # Mapeo automático
_THRESHOLD_AMBIGUOUS = 60  # Requiere confirmación


@dataclass
class MappingResult:
    """Resultado del mapeo de columnas.

    Attributes:
        auto_mapped: Mapeos automáticos seguros.
                     ``{columna_origen: atributo_estándar}``
        ambiguous: Mapeos inciertos que requieren confirmación.
                   ``{columna_origen: (atributo_sugerido, score)}``
        unmapped: Columnas sin correspondencia.
                  ``{columna_origen: mejor_candidato_o_None}``
    """
    auto_mapped: dict[str, str] = field(default_factory=dict)
    ambiguous: dict[str, tuple[str, int]] = field(default_factory=dict)
    unmapped: dict[str, str | None] = field(default_factory=dict)

    @property
    def all_mapped(self) -> dict[str, str]:
        """Combinación de auto + ambiguos (para previsualización)."""
        result = dict(self.auto_mapped)
        for col, (attr, _score) in self.ambiguous.items():
            result[col] = attr
        return result

    @property
    def is_complete(self) -> bool:
        """True si no hay columnas ambiguas ni sin mapear."""
        return not self.ambiguous and not self.unmapped


class DataNormalizer:
    """Mapea columnas de entrada a los atributos estándar del sistema.

    Usa fuzzy-matching para encontrar la mejor correspondencia entre
    los encabezados de la fuente y los alias de cada atributo estándar.

    Ejemplo::

        normalizer = DataNormalizer()
        result = normalizer.map_columns(["Nombre Alumno", "CURP", "Grd"])
        # result.auto_mapped == {"Nombre Alumno": "nombre", "CURP": "curp"}
        # result.ambiguous == {"Grd": ("grado", 72)}
    """

    def __init__(
        self,
        custom_attributes: dict[str, list[str]] | None = None,
    ) -> None:
        """
        Args:
            custom_attributes: Atributos extra o overrides. Se fusionan
                               con ``STANDARD_ATTRIBUTES``.
        """
        self._attributes = dict(STANDARD_ATTRIBUTES)
        if custom_attributes:
            for key, aliases in custom_attributes.items():
                existing = self._attributes.get(key, [])
                self._attributes[key] = list(set(existing + aliases))

        # Construir índice invertido: alias → atributo estándar
        self._alias_index: dict[str, str] = {}
        for attr, aliases in self._attributes.items():
            for alias in aliases:
                self._alias_index[alias.lower()] = attr

    # ── Mapeo de columnas ────────────────────────────────────────────

    def map_columns(self, incoming_columns: list[str]) -> MappingResult:
        """Mapea una lista de encabezados a atributos estándar.

        Args:
            incoming_columns: Nombres de columna tal como vienen de la
                              fuente de datos.

        Returns:
            ``MappingResult`` con los tres niveles de confianza.
        """
        result = MappingResult()
        all_aliases = list(self._alias_index.keys())

        # Atributos estándar ya asignados (evitar duplicados)
        assigned: set[str] = set()

        for col in incoming_columns:
            col_lower = col.strip().lower()

            # 1) Coincidencia exacta con un alias
            if col_lower in self._alias_index:
                standard = self._alias_index[col_lower]
                if standard not in assigned:
                    result.auto_mapped[col] = standard
                    assigned.add(standard)
                    continue

            # 2) Fuzzy match contra todos los alias
            if not all_aliases:
                result.unmapped[col] = None
                continue

            match = fuzz_process.extractOne(col_lower, all_aliases)
            if match is None:
                result.unmapped[col] = None
                continue

            best_alias, score, *_ = match
            standard = self._alias_index[best_alias]

            if score >= _THRESHOLD_AUTO and standard not in assigned:
                result.auto_mapped[col] = standard
                assigned.add(standard)
                logger.debug(
                    "Auto-mapeado: '%s' → '%s' (score=%d)",
                    col, standard, score,
                )
            elif score >= _THRESHOLD_AMBIGUOUS and standard not in assigned:
                result.ambiguous[col] = (standard, score)
                logger.debug(
                    "Ambiguo: '%s' → '%s' (score=%d)",
                    col, standard, score,
                )
            else:
                result.unmapped[col] = standard if score >= 40 else None
                logger.debug(
                    "Sin mapear: '%s' (mejor: '%s', score=%d)",
                    col, standard, score,
                )

        logger.info(
            "Mapeo: %d auto, %d ambiguos, %d sin mapear de %d columnas.",
            len(result.auto_mapped),
            len(result.ambiguous),
            len(result.unmapped),
            len(incoming_columns),
        )
        return result

    # ── Normalización de registros ───────────────────────────────────

    @staticmethod
    def normalize_record(
        raw_record: dict[str, Any],
        mapping: dict[str, str],
    ) -> dict[str, Any]:
        """Aplica un mapeo de columnas a un registro individual.

        Args:
            raw_record: Diccionario con claves originales de la fuente.
            mapping: ``{columna_original: atributo_estándar}``

        Returns:
            Nuevo diccionario con claves estándar.
        """
        normalized: dict[str, Any] = {}
        for original_col, standard_attr in mapping.items():
            value = raw_record.get(original_col, "")
            # Limpiar strings: quitar espacios extra
            if isinstance(value, str):
                value = value.strip()
            normalized[standard_attr] = value
        return normalized

    # ── Campos compuestos ────────────────────────────────────────────

    @staticmethod
    def build_composite_fields(
        record: dict[str, Any],
        template_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Construye campos derivados o compuestos.

        Genera campos como ``nombre_completo`` o ``qr_url`` a partir
        de los datos normalizados y la configuración de la plantilla.

        Args:
            record: Registro ya normalizado con claves estándar.
            template_config: Configuración de la plantilla, puede
                             contener ``qr_base_url``, ``qr_format``, etc.

        Returns:
            Diccionario con los campos compuestos generados.
        """
        config = template_config or {}
        composites: dict[str, Any] = {}

        # Nombre completo
        name_parts = [
            record.get("nombre", ""),
            record.get("apellido_paterno", ""),
            record.get("apellido_materno", ""),
        ]
        composites["nombre_completo"] = " ".join(
            p for p in name_parts if p
        ).strip()

        # QR URL: construir si hay template de QR y matrícula
        qr_base = config.get("qr_base_url", "")
        qr_format = config.get("qr_format", "{base}/{matricula}")
        if qr_base and record.get("matricula"):
            composites["qr_url"] = qr_format.format(
                base=qr_base.rstrip("/"),
                matricula=record.get("matricula", ""),
                curp=record.get("curp", ""),
                **{k: v for k, v in record.items() if isinstance(v, str)},
            )
        elif record.get("qr_data"):
            # Si ya viene un qr_data del adaptador, usarlo directamente
            composites["qr_url"] = record["qr_data"]

        # Grado + Grupo concatenado
        grado = record.get("grado", "")
        grupo = record.get("grupo", "")
        if grado or grupo:
            composites["grado_grupo"] = f"{grado}{grupo}".strip()

        return composites
