"""Módulo de impresión directa — envía PDFs a impresoras del sistema."""
from __future__ import annotations

import logging
import platform
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _printers_via_qt() -> list[str]:
    """Impresoras vía Qt (QPrinterInfo), sin depender de subprocess ni PATH."""
    try:
        from PySide6.QtPrintSupport import QPrinterInfo

        return [
            p.printerName()
            for p in QPrinterInfo.availablePrinters()
            if p.printerName()
        ]
    except Exception as e:  # noqa: BLE001
        logger.debug("QPrinterInfo no disponible: %s", e)
        return []


def _printers_via_lpstat() -> list[str]:
    """Impresoras vía CUPS (`lpstat`) en macOS/Linux, usando ruta absoluta.

    Las apps lanzadas desde Finder/escritorio pueden tener un PATH reducido, por
    lo que se invoca el binario por su ruta absoluta habitual. Se prueban varias
    banderas (`-e`, `-p`, `-a`) porque su disponibilidad varía entre sistemas.
    """
    lpstat = None
    for candidate in ("/usr/bin/lpstat", "/bin/lpstat", "lpstat"):
        if candidate == "lpstat" or Path(candidate).exists():
            lpstat = candidate
            break
    if lpstat is None:
        return []

    # `-e`: enumera todos los destinos (una por línea, nombre tal cual).
    # `-p`/`-a`: "printer NAME ..." / "NAME accepting ...".
    for args, name_index in ((["-e"], None), (["-p"], 1), (["-a"], 0)):
        try:
            result = subprocess.run(
                [lpstat, *args], capture_output=True, text=True, timeout=5
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("lpstat %s falló: %s", args, e)
            continue
        if result.returncode != 0:
            continue
        nombres: list[str] = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if name_index is None:
                nombres.append(parts[0])
            elif len(parts) > name_index:
                nombres.append(parts[name_index])
        if nombres:
            return nombres
    return []


def get_system_printers() -> list[str]:
    """Obtiene la lista de impresoras del sistema (robusta y multiplataforma).

    Combina varias fuentes y elimina duplicados conservando el orden:
    - Qt (`QPrinterInfo`), que funciona en proceso sin depender del PATH.
    - En macOS/Linux, `lpstat` (CUPS) por ruta absoluta como complemento.
    - En Windows, `win32print` si está disponible.

    Esto maximiza la probabilidad de detectar impresoras tanto en desarrollo
    como en la app empaquetada (donde el PATH puede estar reducido).
    """
    system = platform.system()
    nombres: list[str] = []

    # 1) Qt en proceso (todas las plataformas).
    nombres.extend(_printers_via_qt())

    # 2) Backends nativos por plataforma.
    if system in ("Darwin", "Linux"):
        nombres.extend(_printers_via_lpstat())
    elif system == "Windows":
        try:
            import win32print

            printers = win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )
            nombres.extend(p[2] for p in printers)
        except Exception as e:  # noqa: BLE001
            logger.debug("win32print no disponible: %s", e)

    # Deduplicar conservando el orden de aparición.
    vistos: set[str] = set()
    unicas: list[str] = []
    for n in nombres:
        if n and n not in vistos:
            vistos.add(n)
            unicas.append(n)

    logger.info("Impresoras detectadas (%s): %s", system, unicas)
    return unicas


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
                ["/usr/bin/lpstat", "-d"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and ":" in result.stdout:
                return result.stdout.split(":")[-1].strip()
        elif system == "Windows":
            import win32print

            return win32print.GetDefaultPrinter()
    except Exception as e:
        logger.debug("No se pudo obtener impresora predeterminada: %s", e)

    # Fallback multiplataforma vía Qt.
    try:
        from PySide6.QtPrintSupport import QPrinterInfo

        name = QPrinterInfo.defaultPrinterName()
        return name or None
    except Exception:  # noqa: BLE001
        return None
