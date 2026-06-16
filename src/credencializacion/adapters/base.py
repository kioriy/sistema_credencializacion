"""
Clase base abstracta para adaptadores de datos.

Define el contrato que cualquier fuente de datos debe implementar
para integrarse al sistema de credencialización.

Patrón Strategy: el sistema solicita registros sin importar si la
fuente es una API, un archivo CSV/Excel, o una hoja de Google Sheets.
"""
from abc import ABC, abstractmethod


class DataAdapter(ABC):
    """Interfaz común para todas las fuentes de datos.

    Cualquier adaptador nuevo debe heredar de esta clase e implementar
    los tres métodos abstractos.

    Ejemplo::

        class MiAdapter(DataAdapter):
            def fetch_records(self, **kwargs):
                return [{"nombre": "Ana", "grado": "3A"}]
            def get_columns(self):
                return ["nombre", "grado"]
            def get_source_name(self):
                return "Mi Fuente"
    """

    @abstractmethod
    def fetch_records(self, **kwargs) -> list[dict]:
        """Obtiene registros de la fuente de datos.

        Args:
            **kwargs: Parámetros específicos de cada adaptador
                      (filtros, rangos, paginación, etc.).

        Returns:
            Lista de diccionarios, cada uno representando un registro.
            Las llaves son los nombres de columna originales de la fuente.

        Raises:
            ConnectionError: Si no se puede conectar a la fuente.
            ValueError: Si los parámetros son inválidos.
        """
        ...

    @abstractmethod
    def get_columns(self) -> list[str]:
        """Retorna las columnas disponibles en la fuente.

        Útil para el mapeo de campos y previsualización antes de importar.

        Returns:
            Lista de nombres de columna como strings.
        """
        ...

    @abstractmethod
    def get_source_name(self) -> str:
        """Nombre legible de la fuente de datos.

        Se muestra en la UI para que el usuario identifique de dónde
        provienen los datos.

        Returns:
            Nombre descriptivo (e.g. "MiEscuela API", "Archivo CSV").
        """
        ...
