"""
Diálogo para crear una cola de impresión a partir de una CARPETA de diseños.

Para clientes que entregan sus credenciales ya diseñadas como imágenes. El
usuario elige la carpeta (con subcarpetas ``frente/`` y opcional ``vuelta/``),
el tamaño de la credencial y si debe rotarse, y el sistema arma los PDFs de
frentes y vueltas listos para imprimir con la calibración de la charola.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from credencializacion.renderer.folder_compose import (
    DEFAULT_CARD_H_CM,
    DEFAULT_CARD_W_CM,
    FolderSides,
    resolve_folder_sides,
)

TEXT_DARK = "#171A2B"
TEXT_LIGHT = "#64748B"
CARD_BG = "#FFFFFF"
BORDER = "#E2E8F0"
WARNING = "#B45309"
SUCCESS = "#15803D"


class FolderComposeDialog(QDialog):
    """Configura la composición de PDFs desde una carpeta de diseños."""

    def __init__(
        self,
        profile_names: list[str],
        current_profile: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._root: Path | None = None
        self._sides: FolderSides | None = None

        self.setWindowTitle("Componer impresión desde carpeta")
        self.setMinimumWidth(520)
        self.setStyleSheet(f"background-color: {CARD_BG}; color: {TEXT_DARK};")

        input_style = f"""
            background-color: {CARD_BG};
            border: 1px solid {BORDER};
            border-radius: 6px;
            padding: 8px;
            font-size: 13px;
            color: {TEXT_DARK};
        """

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        intro = QLabel(
            "Elige una carpeta con los diseños ya terminados. Debe tener una "
            "subcarpeta «frente» y, opcionalmente, «vuelta». Las imágenes se "
            "emparejan por orden de nombre."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {TEXT_LIGHT}; font-size: 12px;")
        layout.addWidget(intro)

        # ── Carpeta ──
        lbl_folder = QLabel("Carpeta de diseños:")
        lbl_folder.setFont(QFont("Inter", 12, QFont.Weight.DemiBold))
        layout.addWidget(lbl_folder)

        folder_row = QHBoxLayout()
        self._edit_folder = QLineEdit()
        self._edit_folder.setReadOnly(True)
        self._edit_folder.setPlaceholderText("Ninguna carpeta seleccionada")
        self._edit_folder.setStyleSheet(input_style)
        folder_row.addWidget(self._edit_folder, stretch=1)
        btn_browse = QPushButton("Examinar…")
        btn_browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(btn_browse)
        layout.addLayout(folder_row)

        # Info de conteo/emparejado (se llena al elegir carpeta).
        self._lbl_info = QLabel("")
        self._lbl_info.setWordWrap(True)
        self._lbl_info.setStyleSheet(f"color: {TEXT_LIGHT}; font-size: 12px;")
        layout.addWidget(self._lbl_info)

        # ── Nombre ──
        lbl_nombre = QLabel("Nombre de la cola:")
        lbl_nombre.setFont(QFont("Inter", 12, QFont.Weight.DemiBold))
        layout.addWidget(lbl_nombre)
        self._edit_nombre = QLineEdit()
        self._edit_nombre.setStyleSheet(input_style)
        layout.addWidget(self._edit_nombre)

        # ── Perfil de posición ──
        lbl_perfil = QLabel("Perfil de posición (calibración de charola):")
        lbl_perfil.setFont(QFont("Inter", 12, QFont.Weight.DemiBold))
        layout.addWidget(lbl_perfil)
        self._combo_perfil = QComboBox()
        self._combo_perfil.setStyleSheet(input_style)
        for name in profile_names:
            self._combo_perfil.addItem(name, name)
        if current_profile:
            idx = self._combo_perfil.findData(current_profile)
            if idx >= 0:
                self._combo_perfil.setCurrentIndex(idx)
        if not profile_names:
            self._combo_perfil.addItem("(configuración global)", "")
        layout.addWidget(self._combo_perfil)

        # ── Tamaño / rotación ──
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Ancho (cm):"))
        self._sp_w = QDoubleSpinBox()
        self._sp_w.setRange(1.0, 100.0)
        self._sp_w.setDecimals(2)
        self._sp_w.setSingleStep(0.1)
        self._sp_w.setValue(DEFAULT_CARD_W_CM)
        size_row.addWidget(self._sp_w)
        size_row.addSpacing(12)
        size_row.addWidget(QLabel("Alto (cm):"))
        self._sp_h = QDoubleSpinBox()
        self._sp_h.setRange(1.0, 100.0)
        self._sp_h.setDecimals(2)
        self._sp_h.setSingleStep(0.1)
        self._sp_h.setValue(DEFAULT_CARD_H_CM)
        size_row.addWidget(self._sp_h)
        size_row.addSpacing(12)
        self._chk_rotate = QCheckBox("Rotar 90°")
        self._chk_rotate.setToolTip(
            "Marca esto si los diseños son verticales y deben acostarse en la "
            "charola (ej. credencial 5.4 × 8.5)."
        )
        size_row.addWidget(self._chk_rotate)
        size_row.addStretch()
        layout.addLayout(size_row)

        # ── Botones ──
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Componer")
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        layout.addWidget(self._buttons)

    # ── Carpeta ──
    def _browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Selecciona la carpeta de diseños", str(Path.home())
        )
        if not path:
            return
        self._root = Path(path)
        self._edit_folder.setText(path)
        if not self._edit_nombre.text().strip():
            self._edit_nombre.setText(self._root.name)
        self._analyze()

    def _analyze(self) -> None:
        """Analiza la carpeta y actualiza el resumen de emparejado."""
        assert self._root is not None
        self._sides = resolve_folder_sides(self._root)
        sides = self._sides

        ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if sides.mode == "empty":
            self._lbl_info.setText(f"⚠ {sides.warning}")
            self._lbl_info.setStyleSheet(f"color: {WARNING}; font-size: 12px;")
            ok_btn.setEnabled(False)
            return

        resumen = {
            "only_front": f"✓ {sides.n_front} frente(s), sin vueltas — se generará solo el PDF de frentes.",
            "single_back": f"✓ {sides.n_front} frente(s) y 1 vuelta — esa vuelta se repite en todas.",
            "paired": f"✓ {sides.n_front} frente(s) y {sides.n_back} vuelta(s), emparejados por nombre.",
            "mismatch": f"⚠ {sides.warning}",
        }.get(sides.mode, "")
        color = WARNING if sides.mode == "mismatch" else SUCCESS
        self._lbl_info.setText(resumen)
        self._lbl_info.setStyleSheet(f"color: {color}; font-size: 12px;")
        ok_btn.setEnabled(True)

    # ── Resultado ──
    def result_values(self) -> dict:
        """Devuelve la configuración elegida (llamar tras ``exec()`` == Accepted)."""
        return {
            "root": self._root,
            "sides": self._sides,
            "nombre": self._edit_nombre.text().strip() or (
                self._root.name if self._root else "Cola desde carpeta"
            ),
            "perfil_name": self._combo_perfil.currentData() or "",
            "card_w_cm": self._sp_w.value(),
            "card_h_cm": self._sp_h.value(),
            "rotate": self._chk_rotate.isChecked(),
        }
