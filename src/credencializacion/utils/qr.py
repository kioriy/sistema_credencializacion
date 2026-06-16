"""
Generación de códigos QR para credenciales.

Produce QR codes como:
- ``QPixmap`` para uso directo en el canvas Qt (QGraphicsScene).
- Archivo PNG temporal para inclusión en PDFs con ReportLab.

Usa la librería ``qrcode`` con backend Pillow y nivel de corrección M.
"""
from __future__ import annotations

import io
import logging
import tempfile
from pathlib import Path

import qrcode
from qrcode.constants import ERROR_CORRECT_M
from PIL import Image as PILImage

logger = logging.getLogger(__name__)


def generate_qr_image(
    data: str,
    size: int = 200,
    border: int = 2,
) -> Path:
    """Genera un QR y lo guarda como archivo PNG temporal.

    Útil para incluir el QR en PDFs generados con ReportLab.

    Args:
        data: Contenido a codificar en el QR (URL, texto, etc.).
        size: Tamaño del lado en píxeles de la imagen final.
        border: Número de celdas de margen alrededor del QR.

    Returns:
        ``Path`` al archivo PNG temporal generado.

    Raises:
        ValueError: Si ``data`` está vacío.
    """
    if not data:
        raise ValueError("El contenido del QR no puede estar vacío.")

    qr = qrcode.QRCode(
        version=None,  # Auto-detect
        error_correction=ERROR_CORRECT_M,
        box_size=10,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)

    pil_img = qr.make_image(fill_color="black", back_color="white")

    # Redimensionar al tamaño solicitado
    pil_img = pil_img.resize(
        (size, size),
        PILImage.Resampling.NEAREST,
    )

    # Guardar en archivo temporal (no se borra automáticamente para
    # que ReportLab pueda leerlo después)
    temp_file = tempfile.NamedTemporaryFile(
        suffix=".png",
        prefix="qr_",
        delete=False,
    )
    pil_img.save(temp_file, format="PNG")
    temp_file.close()

    temp_path = Path(temp_file.name)
    logger.debug("QR generado en: %s (%dpx, datos: %.30s…)", temp_path, size, data)
    return temp_path


def generate_qr_pixmap(
    data: str,
    size: int = 200,
    border: int = 2,
):
    """Genera un QR como ``QPixmap`` para el canvas Qt.

    Args:
        data: Contenido a codificar en el QR.
        size: Tamaño del lado en píxeles.
        border: Número de celdas de margen alrededor del QR.

    Returns:
        ``QPixmap`` listo para usarse en QGraphicsPixmapItem.

    Raises:
        ValueError: Si ``data`` está vacío.
        ImportError: Si PySide6 no está disponible.
    """
    # Import diferido para que el módulo sea importable en entornos
    # sin display (tests, CLI, servidor de render)
    from PySide6.QtGui import QImage, QPixmap
    from PySide6.QtCore import Qt

    if not data:
        raise ValueError("El contenido del QR no puede estar vacío.")

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=10,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)

    pil_img = qr.make_image(fill_color="black", back_color="white")

    # Redimensionar
    pil_img = pil_img.resize(
        (size, size),
        PILImage.Resampling.NEAREST,
    )

    # Convertir PIL → bytes → QImage → QPixmap
    buffer = io.BytesIO()
    pil_img.save(buffer, format="PNG")
    buffer.seek(0)

    qimage = QImage()
    qimage.loadFromData(buffer.read(), "PNG")

    pixmap = QPixmap.fromImage(qimage)
    logger.debug("QR QPixmap generado (%dpx, datos: %.30s…)", size, data)
    return pixmap


def cleanup_temp_qr(qr_path: Path) -> None:
    """Elimina un archivo QR temporal.

    Args:
        qr_path: Ruta al archivo PNG temporal generado por
                  ``generate_qr_image``.
    """
    try:
        if qr_path.exists():
            qr_path.unlink()
            logger.debug("QR temporal eliminado: %s", qr_path)
    except OSError as exc:
        logger.warning("No se pudo eliminar QR temporal %s: %s", qr_path, exc)
