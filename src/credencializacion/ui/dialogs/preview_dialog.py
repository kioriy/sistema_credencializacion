"""Diálogo de vista previa de PDFs con pestañas para Frentes y Vueltas."""
from __future__ import annotations

import logging
from pathlib import Path

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from credencializacion.core.printer import get_default_printer, get_system_printers

logger = logging.getLogger(__name__)

# ── Paleta de colores ──────────────────────────────────────────────────
PRIMARY = "#FB5252"
TEXT_DARK = "#171A2B"
TEXT_LIGHT = "#64748B"
CARD_BG = "#FFFFFF"
BORDER = "#E2E8F0"
MAIN_BG = "#F5F7FA"

# ── Resolución de renderizado ──────────────────────────────────────────
RENDER_DPI = 150

# ── Intento de importar PyMuPDF ────────────────────────────────────────
try:
    import fitz  # PyMuPDF

    _HAS_FITZ = True
except ImportError:
    _HAS_FITZ = False


def _render_pdf_pages(pdf_path: Path, target_width: int) -> list[QPixmap]:
    """Renderiza cada página de un PDF como QPixmap.

    Args:
        pdf_path: Ruta al archivo PDF.
        target_width: Ancho objetivo en píxeles para escalar las imágenes.

    Returns:
        Lista de QPixmap, una por página.
    """
    if not _HAS_FITZ:
        return []

    pixmaps: list[QPixmap] = []
    try:
        doc = fitz.open(str(pdf_path))
        for page in doc:
            zoom = RENDER_DPI / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            fmt = QImage.Format.Format_RGB888
            qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
            pixmap = QPixmap.fromImage(qimg)

            if pixmap.width() > target_width:
                pixmap = pixmap.scaledToWidth(
                    target_width, Qt.TransformationMode.SmoothTransformation
                )
            pixmaps.append(pixmap)
        doc.close()
    except Exception as e:
        logger.error("Error al renderizar PDF '%s': %s", pdf_path, e)
    return pixmaps


class _PageCard(QFrame):
    """Tarjeta individual que muestra una página renderizada con sombra."""

    def __init__(self, pixmap: QPixmap, page_number: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pageCard")
        self.setStyleSheet(
            f"""
            QFrame#pageCard {{
                background: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            """
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 2)
        shadow.setColor(Qt.GlobalColor.gray)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # Etiqueta de número de página
        header = QLabel(f"Página {page_number}")
        header.setStyleSheet(f"color: {TEXT_LIGHT}; font-size: 11px; font-weight: 600;")
        header.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(header)

        # Imagen
        img_label = QLabel()
        img_label.setPixmap(pixmap)
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(img_label)


class _PdfTab(QWidget):
    """Pestaña con scroll area que muestra las páginas de un PDF."""

    def __init__(
        self,
        pdf_path: Path,
        target_width: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.pdf_path = pdf_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {MAIN_BG}; border: none; }}"
        )

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(16, 16, 16, 16)
        container_layout.setSpacing(20)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        if not _HAS_FITZ:
            fallback = QLabel(
                "⚠️ PyMuPDF (fitz) no está instalado.\n"
                "Instálelo con:  pip install PyMuPDF\n\n"
                "No se puede mostrar la vista previa."
            )
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setStyleSheet(
                f"color: {TEXT_LIGHT}; font-size: 13px; padding: 40px;"
            )
            fallback.setWordWrap(True)
            container_layout.addWidget(fallback)
        else:
            pixmaps = _render_pdf_pages(pdf_path, target_width)
            if pixmaps:
                for i, pxm in enumerate(pixmaps, start=1):
                    card = _PageCard(pxm, i)
                    container_layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignHCenter)
            else:
                empty = QLabel("No se pudieron renderizar las páginas del PDF.")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty.setStyleSheet(f"color: {TEXT_LIGHT}; font-size: 13px; padding: 40px;")
                container_layout.addWidget(empty)

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)


class PreviewDialog(QDialog):
    """Diálogo de vista previa que muestra los PDFs de frentes y vueltas.

    Signals:
        print_requested: Emitido con (pdf_path, printer_name) cuando el
                         usuario solicita imprimir un PDF.
    """

    print_requested = Signal(Path, str)

    def __init__(
        self,
        frentes_pdf: Path | None = None,
        vueltas_pdf: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Vista Previa de Credenciales")
        self.setMinimumSize(840, 620)
        self.resize(860, 700)

        self._frentes_pdf = frentes_pdf
        self._vueltas_pdf = vueltas_pdf

        self._setup_ui()
        self._load_printers()

    # ── UI ─────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        """Construye la interfaz del diálogo."""
        self.setStyleSheet(
            f"""
            QDialog {{
                background: {MAIN_BG};
            }}
            QTabWidget::pane {{
                border: 1px solid {BORDER};
                border-radius: 6px;
                background: {MAIN_BG};
            }}
            QTabBar::tab {{
                padding: 8px 24px;
                font-size: 13px;
                font-weight: 600;
                color: {TEXT_LIGHT};
                border: none;
                border-bottom: 3px solid transparent;
                margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                color: {PRIMARY};
                border-bottom: 3px solid {PRIMARY};
            }}
            QTabBar::tab:hover {{
                color: {TEXT_DARK};
            }}
            """
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(12)

        # ── Encabezado ─────────────────────────────────────────────────
        header = QLabel("Vista Previa de Impresión")
        header.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {TEXT_DARK};"
        )
        main_layout.addWidget(header)

        # ── Pestañas ───────────────────────────────────────────────────
        self._tabs = QTabWidget()
        content_width = 780  # ancho útil para renderizar páginas

        if self._frentes_pdf and self._frentes_pdf.exists():
            tab_frentes = _PdfTab(self._frentes_pdf, content_width)
            self._tabs.addTab(tab_frentes, qta.icon("fa5s.id-card", color=TEXT_DARK), "Frentes")

        if self._vueltas_pdf and self._vueltas_pdf.exists():
            tab_vueltas = _PdfTab(self._vueltas_pdf, content_width)
            self._tabs.addTab(tab_vueltas, qta.icon("fa5s.undo", color=TEXT_DARK), "Vueltas")

        if self._tabs.count() == 0:
            empty = QLabel("No hay archivos PDF para mostrar.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {TEXT_LIGHT}; font-size: 14px; padding: 60px;")
            main_layout.addWidget(empty, 1)
        else:
            main_layout.addWidget(self._tabs, 1)

        # ── Barra de impresión ─────────────────────────────────────────
        print_bar = QHBoxLayout()
        print_bar.setSpacing(10)

        printer_icon = QLabel()
        printer_icon.setPixmap(
            qta.icon("fa5s.print", color=TEXT_DARK).pixmap(18, 18)
        )
        print_bar.addWidget(printer_icon)

        lbl_printer = QLabel("Impresora:")
        lbl_printer.setStyleSheet(f"color: {TEXT_DARK}; font-weight: 600; font-size: 13px;")
        print_bar.addWidget(lbl_printer)

        self._printer_combo = QComboBox()
        self._printer_combo.setMinimumWidth(220)
        self._printer_combo.setStyleSheet(
            f"""
            QComboBox {{
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
                color: {TEXT_DARK};
                background: {CARD_BG};
            }}
            QComboBox:focus {{
                border-color: {PRIMARY};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 28px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid {TEXT_LIGHT};
                width: 0;
                height: 0;
                margin-right: 8px;
            }}
            """
        )
        print_bar.addWidget(self._printer_combo, 1)

        btn_style = f"""
            QPushButton {{
                background: {PRIMARY};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #E04848;
            }}
            QPushButton:pressed {{
                background: #C73E3E;
            }}
            QPushButton:disabled {{
                background: {BORDER};
                color: {TEXT_LIGHT};
            }}
        """

        self._btn_print_frentes = QPushButton(
            qta.icon("fa5s.print", color="#FFFFFF"), "  Imprimir Frentes"
        )
        self._btn_print_frentes.setStyleSheet(btn_style)
        self._btn_print_frentes.setEnabled(
            self._frentes_pdf is not None and self._frentes_pdf.exists()
        )
        self._btn_print_frentes.clicked.connect(self._on_print_frentes)
        print_bar.addWidget(self._btn_print_frentes)

        self._btn_print_vueltas = QPushButton(
            qta.icon("fa5s.print", color="#FFFFFF"), "  Imprimir Vueltas"
        )
        self._btn_print_vueltas.setStyleSheet(btn_style)
        self._btn_print_vueltas.setEnabled(
            self._vueltas_pdf is not None and self._vueltas_pdf.exists()
        )
        self._btn_print_vueltas.clicked.connect(self._on_print_vueltas)
        print_bar.addWidget(self._btn_print_vueltas)

        main_layout.addLayout(print_bar)

        # ── Botón cerrar ───────────────────────────────────────────────
        close_bar = QHBoxLayout()
        close_bar.addStretch()
        btn_close = QPushButton("Cerrar")
        btn_close.setStyleSheet(
            f"""
            QPushButton {{
                background: {CARD_BG};
                color: {TEXT_DARK};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {MAIN_BG};
                border-color: {TEXT_LIGHT};
            }}
            """
        )
        btn_close.clicked.connect(self.close)
        close_bar.addWidget(btn_close)
        main_layout.addLayout(close_bar)

    # ── Impresoras ─────────────────────────────────────────────────────

    def _load_printers(self) -> None:
        """Carga las impresoras del sistema en el combo box."""
        self._printer_combo.clear()
        printers = get_system_printers()

        if not printers:
            self._printer_combo.addItem("— Sin impresoras disponibles —")
            self._btn_print_frentes.setEnabled(False)
            self._btn_print_vueltas.setEnabled(False)
            return

        self._printer_combo.addItems(printers)

        default = get_default_printer()
        if default and default in printers:
            self._printer_combo.setCurrentText(default)

    def _selected_printer(self) -> str | None:
        """Devuelve el nombre de la impresora seleccionada o None."""
        text = self._printer_combo.currentText()
        if text.startswith("—"):
            return None
        return text

    # ── Slots de impresión ─────────────────────────────────────────────

    def _on_print_frentes(self) -> None:
        """Maneja clic en Imprimir Frentes."""
        printer = self._selected_printer()
        if printer and self._frentes_pdf:
            self.print_requested.emit(self._frentes_pdf, printer)

    def _on_print_vueltas(self) -> None:
        """Maneja clic en Imprimir Vueltas."""
        printer = self._selected_printer()
        if printer and self._vueltas_pdf:
            self.print_requested.emit(self._vueltas_pdf, printer)
