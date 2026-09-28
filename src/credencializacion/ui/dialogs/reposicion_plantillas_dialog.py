"""Diálogo para elegir la plantilla de cada tipo de tarjeta de reposición."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from credencializacion.services.reposiciones import SLOTS_AUTORIZADO, TIPO_ALUMNO


class ReposicionPlantillasDialog(QDialog):
    """Asigna una plantilla a: alumno, autorizado 1, 2, 3 y 4.

    Args:
        plantillas: ``[(id, nombre)]`` de la escuela.
        actuales: mapa vigente ``{"alumno": id, "autorizado_1": id, ...}``.
    """

    def __init__(
        self,
        plantillas: list[tuple[int, str]],
        actuales: dict[str, int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Plantillas de reposición")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        ayuda = QLabel(
            "Elige el diseño con el que se imprime cada tipo de tarjeta. "
            "Si un autorizado no tiene diseño propio, se usa el de otro "
            "autorizado con sus datos."
        )
        ayuda.setWordWrap(True)
        layout.addWidget(ayuda)

        form = QFormLayout()
        self._combos: dict[str, QComboBox] = {}
        claves = [(TIPO_ALUMNO, "Alumno")] + [
            (f"autorizado_{n}", f"Autorizado {n}") for n in SLOTS_AUTORIZADO
        ]
        for clave, etiqueta in claves:
            combo = QComboBox()
            combo.addItem("— Sin asignar —", None)
            for pid, nombre in plantillas:
                combo.addItem(nombre, pid)
            idx = combo.findData(actuales.get(clave))
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            form.addRow(f"{etiqueta}:", combo)
            self._combos[clave] = combo
        layout.addLayout(form)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)

    def result_map(self) -> dict[str, int]:
        """Mapa elegido, solo con las claves asignadas."""
        return {
            clave: combo.currentData()
            for clave, combo in self._combos.items()
            if combo.currentData() is not None
        }
