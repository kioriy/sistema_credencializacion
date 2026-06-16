"""
Vista previa de credencial antes de impresión.
Muestra el PDF renderizado en un diálogo con controles de zoom y navegación.
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QSizePolicy,
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap, QImage, QPainter


class PreviewDialog(QDialog):
    """Diálogo de vista previa de la salida de impresión."""

    print_requested = Signal(str)  # "frente" o "vuelta"

    def __init__(self, pdf_path: Path | None = None, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.current_page = 0
        self.total_pages = 1
        self.zoom_level = 100
        self._setup_ui()
        if pdf_path:
            self.load_preview(pdf_path)

    def _setup_ui(self):
        self.setWindowTitle("Vista Previa de Impresión")
        self.setMinimumSize(700, 800)
        self.setStyleSheet("QDialog { background-color: #F5F7FA; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()

        # Navegación de páginas
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedSize(36, 36)
        self.prev_btn.clicked.connect(self._prev_page)
        toolbar.addWidget(self.prev_btn)

        self.page_label = QLabel("Página 1 de 1")
        self.page_label.setStyleSheet(
            "color: #171A2B; font-size: 13px; font-weight: bold;"
        )
        toolbar.addWidget(self.page_label)

        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedSize(36, 36)
        self.next_btn.clicked.connect(self._next_page)
        toolbar.addWidget(self.next_btn)

        toolbar.addStretch()

        # Zoom
        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFixedSize(36, 36)
        zoom_out_btn.clicked.connect(lambda: self._set_zoom(self.zoom_level - 25))
        toolbar.addWidget(zoom_out_btn)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet("color: #64748B; font-size: 13px;")
        toolbar.addWidget(self.zoom_label)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedSize(36, 36)
        zoom_in_btn.clicked.connect(lambda: self._set_zoom(self.zoom_level + 25))
        toolbar.addWidget(zoom_in_btn)

        layout.addLayout(toolbar)

        # Área de preview
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                background-color: #E2E8F0;
            }
        """)

        self.preview_container = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: white;
                border: 1px solid #CBD5E1;
            }
        """)
        # Placeholder
        self.preview_label.setText("Vista previa no disponible.\nGenera un PDF primero.")
        self.preview_label.setMinimumSize(400, 550)
        self.preview_layout.addWidget(self.preview_label)

        self.scroll_area.setWidget(self.preview_container)
        layout.addWidget(self.scroll_area)

        # Botones de acción
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton("Cerrar")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #F5F7FA; color: #171A2B;
                border: 1px solid #E2E8F0; border-radius: 8px;
                padding: 10px 24px; font-size: 14px;
            }
            QPushButton:hover { background-color: #E2E8F0; }
        """)
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)

        print_front_btn = QPushButton("🖨 Imprimir Frente")
        print_front_btn.setStyleSheet("""
            QPushButton {
                background-color: #FB5252; color: white; border: none;
                border-radius: 8px; padding: 10px 24px;
                font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #E04848; }
        """)
        print_front_btn.clicked.connect(lambda: self.print_requested.emit("frente"))
        btn_layout.addWidget(print_front_btn)

        print_back_btn = QPushButton("🖨 Imprimir Vuelta")
        print_back_btn.setStyleSheet("""
            QPushButton {
                background-color: #FB5252; color: white; border: none;
                border-radius: 8px; padding: 10px 24px;
                font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #E04848; }
        """)
        print_back_btn.clicked.connect(lambda: self.print_requested.emit("vuelta"))
        btn_layout.addWidget(print_back_btn)

        layout.addLayout(btn_layout)

    def load_preview(self, pdf_path: Path):
        """Carga un PDF para vista previa (usando QImage para renderizar)."""
        self.pdf_path = pdf_path
        # Nota: PySide6 no tiene renderizador PDF nativo.
        # En producción se usaría poppler-qt o similar.
        # Por ahora mostramos info del archivo.
        if pdf_path.exists():
            size = pdf_path.stat().st_size / 1024
            self.preview_label.setText(
                f"📄 PDF generado exitosamente\n\n"
                f"Archivo: {pdf_path.name}\n"
                f"Tamaño: {size:.1f} KB\n\n"
                f"Usa los botones de abajo para imprimir."
            )

    def set_preview_image(self, image: QImage | QPixmap):
        """Establece una imagen como vista previa (para renderizado directo)."""
        if isinstance(image, QImage):
            pixmap = QPixmap.fromImage(image)
        else:
            pixmap = image

        scaled = pixmap.scaled(
            int(pixmap.width() * self.zoom_level / 100),
            int(pixmap.height() * self.zoom_level / 100),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)

    def _set_zoom(self, level: int):
        self.zoom_level = max(25, min(400, level))
        self.zoom_label.setText(f"{self.zoom_level}%")

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._update_page_label()

    def _next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._update_page_label()

    def _update_page_label(self):
        self.page_label.setText(
            f"Página {self.current_page + 1} de {self.total_pages}"
        )
