"""
Módulo de auto-actualización.

Comprueba si existe una versión más reciente publicada en GitHub Releases
y ofrece al usuario descargarlo e instalar la actualización sin salir de la app.

Uso:
    from credencializacion.core.updater import check_for_updates
    check_for_updates(parent_window)
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from threading import Thread
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── Configuración ─────────────────────────────────────────────────────────────
# Reemplaza con tu usuario y nombre del repositorio de GitHub
GITHUB_REPO = "kioriy/sistema_credencializacion"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ASSET_NAME = "CredencializacionApp-Windows.zip"

# Versión actual de la app (sincronizada con pyproject.toml)
APP_VERSION = "0.1.0"


def get_latest_release() -> Optional[dict]:
    """Consulta GitHub API y retorna la info del último release.

    Returns:
        Dict con 'tag_name', 'html_url', 'assets' o None si falla.
    """
    try:
        resp = requests.get(
            GITHUB_API_URL,
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("No se pudo verificar actualizaciones: %s", e)
        return None


def _version_tuple(v: str) -> tuple[int, ...]:
    """Convierte '1.2.3' a (1, 2, 3) para comparación numérica."""
    return tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())


def is_newer(remote_tag: str) -> bool:
    """Retorna True si el tag remoto es mayor que APP_VERSION."""
    try:
        return _version_tuple(remote_tag) > _version_tuple(APP_VERSION)
    except Exception:
        return False


def download_update(asset_url: str, dest: Path, progress_cb=None) -> bool:
    """Descarga el zip de actualización con progreso.

    Args:
        asset_url: URL de descarga del asset de GitHub.
        dest: Ruta donde guardar el zip.
        progress_cb: Callback(bytes_descargados, total_bytes) opcional.

    Returns:
        True si la descarga fue exitosa.
    """
    try:
        with requests.get(asset_url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)
        return True
    except Exception as e:
        logger.error("Error al descargar actualización: %s", e)
        return False


def apply_update(zip_path: Path) -> bool:
    """Extrae el zip en el directorio del ejecutable actual.

    En Windows extrae y reemplaza archivos. El propio .exe se reemplaza
    en el siguiente reinicio con un script batch auxiliar.

    Returns:
        True si la extracción fue exitosa.
    """
    exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Extraer a una carpeta temporal contigua
            tmp_dir = exe_dir.parent / "_update_tmp"
            tmp_dir.mkdir(exist_ok=True)
            zf.extractall(tmp_dir)

        # Crear script .bat que reemplaza la carpeta y relanza la app
        bat = exe_dir.parent / "_apply_update.bat"
        bat.write_text(
            f"@echo off\n"
            f"timeout /t 2 /nobreak >nul\n"
            f'xcopy /E /Y /I "{tmp_dir}\\CredencializacionApp" "{exe_dir}"\n'
            f'rmdir /S /Q "{tmp_dir}"\n'
            f'start "" "{exe_dir}\\CredencializacionApp.exe"\n'
            f"del \"%~f0\"\n",
            encoding="utf-8",
        )

        # Ejecutar el bat y cerrar la app actual
        subprocess.Popen(["cmd", "/c", str(bat)], shell=False)
        return True
    except Exception as e:
        logger.error("Error al aplicar actualización: %s", e)
        return False


def check_for_updates(parent=None) -> None:
    """Verifica actualizaciones y muestra diálogo al usuario si hay una nueva.

    Se ejecuta en un hilo separado para no bloquear la UI.

    Args:
        parent: Ventana padre para el diálogo (QWidget o None).
    """
    # Solo verificar si se ejecuta como ejecutable compilado
    # (en desarrollo no queremos actualizar automáticamente)
    if not getattr(sys, "frozen", False):
        logger.debug("Modo desarrollo — verificación de actualizaciones omitida.")
        return

    def _check():
        release = get_latest_release()
        if not release:
            return

        tag = release.get("tag_name", "")
        if not is_newer(tag):
            logger.info("La app está actualizada (v%s).", APP_VERSION)
            return

        # Buscar el asset descargable
        assets = release.get("assets", [])
        asset = next((a for a in assets if a["name"] == ASSET_NAME), None)
        if not asset:
            return

        asset_url = asset["browser_download_url"]
        release_url = release.get("html_url", "")

        # Mostrar diálogo en el hilo principal (PySide6 requiere GUI en main thread)
        from PySide6.QtCore import QMetaObject, Qt
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app:
            app.postEvent(
                app,
                _UpdateEvent(tag, asset_url, release_url, parent),
            )

    Thread(target=_check, daemon=True).start()


# ── Evento interno para comunicar con el hilo principal ──────────────────────
from PySide6.QtCore import QEvent

_UPDATE_EVENT_TYPE = QEvent.Type(QEvent.registerEventType())


class _UpdateEvent(QEvent):
    def __init__(self, version: str, asset_url: str, release_url: str, parent):
        super().__init__(_UPDATE_EVENT_TYPE)
        self.version = version
        self.asset_url = asset_url
        self.release_url = release_url
        self.parent_widget = parent


class UpdateEventFilter:
    """Instala en QApplication para recibir eventos de actualización."""

    def __init__(self, app):
        from PySide6.QtCore import QObject

        class _Filter(QObject):
            def eventFilter(self_, obj, event):
                if event.type() == _UPDATE_EVENT_TYPE:
                    _show_update_dialog(event.version, event.asset_url, event.release_url, event.parent_widget)
                    return True
                return False

        self._filter = _Filter()
        app.installEventFilter(self._filter)


def _show_update_dialog(version: str, asset_url: str, release_url: str, parent) -> None:
    """Muestra el diálogo de actualización disponible."""
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QProgressBar, QMessageBox,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    import tempfile

    dialog = QDialog(parent)
    dialog.setWindowTitle("Actualización disponible")
    dialog.setFixedWidth(420)
    dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(16)
    layout.setContentsMargins(24, 24, 24, 20)

    # Encabezado
    lbl_title = QLabel(f"🚀 Nueva versión disponible: <b>{version}</b>")
    lbl_title.setFont(QFont("Inter", 12))
    lbl_title.setWordWrap(True)

    lbl_sub = QLabel(
        f"Tu versión actual es <b>v{APP_VERSION}</b>.\n"
        "¿Deseas descargar e instalar la actualización ahora?"
    )
    lbl_sub.setWordWrap(True)
    lbl_sub.setFont(QFont("Inter", 10))

    progress = QProgressBar()
    progress.setRange(0, 100)
    progress.setVisible(False)
    progress.setTextVisible(True)

    lbl_status = QLabel("")
    lbl_status.setVisible(False)
    lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # Botones
    btn_update = QPushButton("⬇  Descargar e instalar")
    btn_update.setObjectName("primaryButton")
    btn_cancel = QPushButton("Ahora no")
    btn_cancel.setObjectName("outlineButton")

    btn_row = QHBoxLayout()
    btn_row.addWidget(btn_cancel)
    btn_row.addWidget(btn_update)

    layout.addWidget(lbl_title)
    layout.addWidget(lbl_sub)
    layout.addWidget(progress)
    layout.addWidget(lbl_status)
    layout.addLayout(btn_row)

    def on_update():
        btn_update.setEnabled(False)
        btn_cancel.setEnabled(False)
        progress.setVisible(True)
        lbl_status.setVisible(True)
        lbl_status.setText("Descargando actualización…")

        tmp = Path(tempfile.mkdtemp()) / ASSET_NAME

        def _progress(done, total):
            if total:
                pct = int(done * 100 / total)
                progress.setValue(pct)
                mb_done = done / 1_048_576
                mb_total = total / 1_048_576
                lbl_status.setText(f"Descargando… {mb_done:.1f} / {mb_total:.1f} MB")

        def _download():
            ok = download_update(asset_url, tmp, _progress)
            if ok:
                lbl_status.setText("Aplicando actualización…")
                apply_update(tmp)
                QApplication.quit()
            else:
                lbl_status.setText("❌ Error al descargar. Intenta de nuevo más tarde.")
                btn_cancel.setEnabled(True)

        Thread(target=_download, daemon=True).start()

    btn_update.clicked.connect(on_update)
    btn_cancel.clicked.connect(dialog.reject)

    dialog.exec()
