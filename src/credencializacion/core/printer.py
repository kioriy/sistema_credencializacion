"""Módulo de impresión directa — envía PDFs a impresoras del sistema."""
from __future__ import annotations

import logging
import platform
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def get_system_printers() -> list[str]:
    """Obtiene la lista de impresoras del sistema."""
    system = platform.system()
    try:
        if system == "Darwin":  # macOS
            result = subprocess.run(
                ["lpstat", "-a"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return [
                    line.split()[0]
                    for line in result.stdout.strip().split("\n")
                    if line.strip()
                ]
        elif system == "Windows":
            import win32print

            printers = win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )
            return [p[2] for p in printers]
    except Exception as e:
        logger.warning("No se pudieron obtener las impresoras: %s", e)
    return []


def print_pdf(pdf_path: Path, printer_name: str) -> bool:
    """Envía un PDF a la impresora del sistema.

    Args:
        pdf_path: Ruta al archivo PDF.
        printer_name: Nombre de la impresora del sistema.

    Returns:
        True si el envío fue exitoso.
    """
    if not pdf_path.exists():
        logger.error("El archivo PDF no existe: %s", pdf_path)
        return False

    system = platform.system()
    try:
        if system == "Darwin":  # macOS
            result = subprocess.run(
                ["lpr", "-P", printer_name, str(pdf_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info("PDF enviado a '%s': %s", printer_name, pdf_path)
                return True
            else:
                logger.error("Error de impresión: %s", result.stderr)
                return False
        elif system == "Windows":
            import win32api
            import win32print  # noqa: F401

            win32api.ShellExecute(
                0, "print", str(pdf_path), f'/d:"{printer_name}"', ".", 0
            )
            logger.info("PDF enviado a '%s': %s", printer_name, pdf_path)
            return True
        else:
            # Linux fallback
            result = subprocess.run(
                ["lp", "-d", printer_name, str(pdf_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
    except Exception as e:
        logger.error("Error al imprimir: %s", e)
        return False


def get_default_printer() -> str | None:
    """Obtiene la impresora predeterminada del sistema."""
    system = platform.system()
    try:
        if system == "Darwin":
            result = subprocess.run(
                ["lpstat", "-d"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and ":" in result.stdout:
                return result.stdout.split(":")[-1].strip()
        elif system == "Windows":
            import win32print

            return win32print.GetDefaultPrinter()
    except Exception as e:
        logger.debug("No se pudo obtener impresora predeterminada: %s", e)
    return None
