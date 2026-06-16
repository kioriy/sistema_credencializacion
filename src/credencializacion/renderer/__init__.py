"""
Módulo de renderizado y generación de PDFs.

Exporta las clases principales para generación e impresión de credenciales.
"""
from credencializacion.renderer.coordinates import (
    cm_to_points,
    mm_to_points,
    calculate_card_positions,
    calculate_card_positions_from_config,
    final_coordinate,
)
from credencializacion.renderer.pdf_engine import PDFEngine
from credencializacion.renderer.print_manager import PrintManager
from credencializacion.renderer.rotation import (
    apply_rotation,
    restore_rotation,
    should_rotate,
    get_rotated_dimensions,
)

__all__ = [
    "PDFEngine",
    "PrintManager",
    "cm_to_points",
    "mm_to_points",
    "calculate_card_positions",
    "calculate_card_positions_from_config",
    "final_coordinate",
    "apply_rotation",
    "restore_rotation",
    "should_rotate",
    "get_rotated_dimensions",
]
