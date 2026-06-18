"""
Modelos SQLAlchemy para el sistema de credencialización.

Arquitectura multi-tenant con columnas JSON dinámicas:
- Cliente: datos maestros de cada organización
- Registro: credenciales con datos dinámicos en JSON
- Plantilla: configuración visual del diseño
"""
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarativa con soporte para JSON nativo."""
    type_annotation_map = {
        dict[str, Any]: JSON,
        list[dict[str, Any]]: JSON,
        list: JSON,
        dict: JSON,
    }


class Cliente(Base):
    """Datos maestros de cada organización (escuela, empresa, etc.).
    
    Soporta multi-tenancy: múltiples clientes coexisten en la misma BD.
    """
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[str] = mapped_column(
        String(50), nullable=False, default="escuela"
    )  # "escuela", "empresa", "gobierno"
    token: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Token API miescuela.net
    api_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # X-Credential-Key para API export
    api_base_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )  # URL base del backend Laravel
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Campos sincronizados desde la API de escuelas
    school_api_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, unique=True
    )  # ID de la escuela en la API remota
    cct: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # Clave de Centro de Trabajo
    school_level: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # "Primaria", "Secundaria", etc.
    address: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    total_students: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    config: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )  # Config adicional flexible

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relaciones
    registros: Mapped[list["Registro"]] = relationship(
        back_populates="cliente", cascade="all, delete-orphan"
    )
    plantillas: Mapped[list["Plantilla"]] = relationship(
        back_populates="cliente", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Cliente(id={self.id}, nombre='{self.nombre}', tipo='{self.tipo}')>"


class Registro(Base):
    """Registro individual de credencial.
    
    Los datos del sujeto se almacenan como JSON dinámico en `datos`,
    eliminando la necesidad de alterar el esquema en el futuro.
    
    Campos inmutables: id, cliente_id
    Estado de impresión: "pendiente", "en_cola", "impreso", "error"
    """
    __tablename__ = "registros"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False
    )
    estado_impresion: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pendiente"
    )  # "pendiente", "en_cola", "impreso", "error"
    
    # Datos dinámicos del sujeto (flexibilidad total)
    datos: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )  # {"nombre": "Elena", "grado": "3", "curp": "...", ...}

    # Campos de acceso rápido (denormalizados del JSON para consultas)
    enrollment_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    credential_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # "pending", "ready", "delivered", "replacement_requested"
    
    # Recursos procesados
    photo_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )  # Ruta local de foto cacheada
    qr_data: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # URL/string final para el QR

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relación
    cliente: Mapped["Cliente"] = relationship(back_populates="registros")

    @property
    def nombre_completo(self) -> str:
        """Nombre completo extraído del JSON de datos."""
        d = self.datos or {}
        parts = [
            d.get("first_name") or d.get("nombre", ""),
            d.get("last_name") or d.get("apellido_paterno", ""),
            d.get("apellido_materno", ""),
        ]
        return " ".join(p for p in parts if p).strip()

    @property
    def institucion(self) -> str:
        """Nombre de la institución del cliente asociado."""
        return self.cliente.nombre if self.cliente else ""

    def get_dato(self, key: str, default: Any = "") -> Any:
        """Acceso seguro a un atributo dinámico."""
        return (self.datos or {}).get(key, default)

    def __repr__(self) -> str:
        return (
            f"<Registro(id={self.id}, enrollment='{self.enrollment_code}', "
            f"estado='{self.estado_impresion}')>"
        )


class Plantilla(Base):
    """Configuración visual de una plantilla de credencial/certificado.
    
    Almacena la definición completa del diseño: elementos, posiciones,
    fuentes, imágenes de fondo, etc. Todo serializado en JSON.
    
    Soporta múltiples tipos: credencial (8.5x5.4), certificado, gafete, etc.
    """
    __tablename__ = "plantillas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[str] = mapped_column(
        String(50), nullable=False, default="credencial"
    )  # "credencial", "certificado", "gafete"
    orientacion: Mapped[str] = mapped_column(
        String(20), nullable=False, default="horizontal"
    )  # "horizontal" | "vertical"

    # Dimensiones del lienzo en cm
    ancho: Mapped[float] = mapped_column(Float, nullable=False, default=8.5)
    alto: Mapped[float] = mapped_column(Float, nullable=False, default=5.4)

    # Elementos del diseño (JSON arrays)
    elementos_frente: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    """
    Cada elemento es un dict:
    {
        "type": "text" | "image" | "qr" | "barcode" | "shape" | "background",
        "x": float,       # posición x en mm
        "y": float,       # posición y en mm
        "width": float,   # ancho en mm
        "height": float,  # alto en mm
        "z_order": int,   # orden de capa
        "campo_dato": str | None,  # atributo JSON vinculado
        "properties": {   # propiedades específicas del tipo
            "font_family": "Inter",
            "font_size": 14,
            "font_weight": "bold",
            "alignment": "center",
            "color": "#171A2B",
            "src": "path/to/image.png",
            ...
        }
    }
    """
    elementos_vuelta: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )

    # Posiciones base en la hoja física (para 2 credenciales por hoja)
    posiciones_hoja: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=lambda: {
            "page_size": "letter",
            "cards_per_page": 2,
            "positions": [
                {"x_cm": 0, "y_cm": 0},   # Credencial superior
                {"x_cm": 0, "y_cm": 14},   # Credencial inferior
            ],
            "margins": {"top_cm": 1.5, "left_cm": 5.0},
        }
    )

    # Rutas de recursos (fondo, logo, decoraciones)
    recursos: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )  # {"fondo_frente": "path", "fondo_vuelta": "path", "logo": "path"}

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relación
    cliente: Mapped["Cliente"] = relationship(back_populates="plantillas")

    def __repr__(self) -> str:
        return (
            f"<Plantilla(id={self.id}, nombre='{self.nombre}', "
            f"tipo='{self.tipo}', {self.ancho}x{self.alto}cm)>"
        )


class ColaImpresion(Base):
    """Cola de impresión persistente.

    Agrupa un conjunto de registros para imprimir sus frentes y/o vueltas.
    El estado trackea qué caras ya fueron impresas para garantizar
    correspondencia frente↔vuelta al dar vuelta la hoja.

    Estados:
    - pendiente: cola creada, nada impreso
    - frentes_impresos: solo frentes enviados a impresora
    - vueltas_impresas: solo vueltas enviados a impresora
    - completada: ambas caras impresas
    - error: fallo durante impresión
    """
    __tablename__ = "colas_impresion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pendiente"
    )
    impresora: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Nombre de la impresora del sistema asignada
    total_registros: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relaciones
    items: Mapped[list["ItemCola"]] = relationship(
        back_populates="cola", cascade="all, delete-orphan",
        order_by="ItemCola.orden",
    )

    @property
    def estado_label(self) -> str:
        """Etiqueta legible del estado."""
        labels = {
            "pendiente": "⏳ Pendiente",
            "frentes_impresos": "📄 Frentes Impresos",
            "vueltas_impresas": "📄 Vueltas Impresas",
            "completada": "✅ Completada",
            "error": "❌ Error",
        }
        return labels.get(self.estado, self.estado)

    def __repr__(self) -> str:
        return (
            f"<ColaImpresion(id={self.id}, nombre='{self.nombre}', "
            f"estado='{self.estado}', items={self.total_registros})>"
        )


class ItemCola(Base):
    """Ítem individual de una cola de impresión.

    Cada ítem apunta a un registro y a una plantilla específica,
    permitiendo mezclar registros de distintos clientes/plantillas
    en la misma cola.

    El campo `orden` es CRÍTICO: garantiza que al imprimir las vueltas,
    se respete exactamente el mismo orden en que se imprimieron los frentes.
    """
    __tablename__ = "items_cola"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cola_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("colas_impresion.id", ondelete="CASCADE"), nullable=False
    )
    registro_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("registros.id", ondelete="CASCADE"), nullable=False
    )
    plantilla_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plantillas.id", ondelete="CASCADE"), nullable=False
    )
    orden: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # Posición fija en la cola (1, 2, 3, ...)
    estado_item: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pendiente"
    )  # "pendiente", "frente_impreso", "vuelta_impresa", "completado"

    # Relaciones
    cola: Mapped["ColaImpresion"] = relationship(back_populates="items")
    registro: Mapped["Registro"] = relationship()
    plantilla: Mapped["Plantilla"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<ItemCola(id={self.id}, cola={self.cola_id}, "
            f"orden={self.orden}, registro={self.registro_id})>"
        )
