"""
Módulo de auto-actualización.

Comprueba si existe una versión más reciente publicada en GitHub Releases
y ofrece al usuario descargarla e instalar la actualización sin salir de la app.

Uso:
    from credencializacion.core.updater import init_updater, check_for_updates
    init_updater(window)          # una vez, en el hilo principal (al iniciar)
    check_for_updates(window)     # verificación silenciosa al inicio
    check_for_updates(window, manual=True)  # verificación manual (botón)
"""
from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from threading import Thread
from typing import Optional

import requests

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

# ── Configuración ─────────────────────────────────────────────────────────────
# Reemplaza con tu usuario y nombre del repositorio de GitHub
GITHUB_REPO = "kioriy/sistema_credencializacion"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ASSET_NAME = "CredencializacionApp-Windows.zip"

# Versión actual de la app (sincronizada con pyproject.toml por release.sh)
APP_VERSION = "0.1.4"


# ── Marca de intento de actualización (rompe el bucle de re-prompt) ───────────
def _attempt_marker_path() -> Path:
    """Ruta del archivo que registra la última versión que se intentó instalar.

    Vive en el directorio de datos del usuario (estable, fuera de la app), de
    modo que persiste entre reinicios y no se ve afectado por la actualización.
    """
    from credencializacion.utils.paths import get_data_dir

    return get_data_dir() / "update_attempt.json"


def _read_attempted_version() -> Optional[str]:
    """Devuelve la última versión cuya instalación se intentó, o None."""
    try:
        import json

        path = _attempt_marker_path()
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("attempted_version")
    except Exception:  # noqa: BLE001
        return None


def _write_attempted_version(tag: str) -> None:
    """Registra la versión cuya instalación se está intentando."""
    try:
        import json
        import time

        _attempt_marker_path().write_text(
            json.dumps({"attempted_version": tag, "ts": time.time()}),
            encoding="utf-8",
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("No se pudo escribir la marca de actualización: %s", e)


# ── Consulta a GitHub ─────────────────────────────────────────────────────────
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


# ── Descarga e instalación ────────────────────────────────────────────────────
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


def can_self_update() -> bool:
    """Indica si la app puede auto-instalar la actualización.

    Solo es posible cuando corre como ejecutable compilado en Windows
    (el mecanismo usa un script .bat con xcopy).
    """
    return getattr(sys, "frozen", False) and platform.system() == "Windows"


def apply_update(zip_path: Path) -> bool:
    """Extrae el zip en el directorio del ejecutable actual (Windows).

    El propio .exe se reemplaza tras cerrar la app mediante un script batch
    auxiliar. La carpeta de datos del usuario vive fuera del directorio de la
    app (ver ``utils.paths.get_data_dir``), por lo que la actualización **no
    toca la base de datos**; aun así se excluye cualquier carpeta ``data`` del
    copiado como defensa en profundidad.

    Returns:
        True si la extracción y el lanzamiento del script fueron exitosos.
    """
    exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()

    try:
        tmp_dir = exe_dir.parent / "_update_tmp"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)

        # Detectar dinámicamente la carpeta raíz extraída (no asumir un nombre
        # fijo): si el zip contiene una única carpeta de nivel superior, esa es
        # el origen; si no, se usa la carpeta temporal completa. Evita el fallo
        # silencioso de xcopy cuando el nombre de la carpeta no coincide.
        entries = [p for p in tmp_dir.iterdir()]
        subdirs = [p for p in entries if p.is_dir()]
        if len(subdirs) == 1 and len(entries) == 1:
            source_dir = subdirs[0]
        else:
            source_dir = tmp_dir

        # Archivo de exclusión para xcopy: no copiar la carpeta de datos.
        exclude_file = exe_dir.parent / "_update_exclude.txt"
        exclude_file.write_text("\\data\\\n", encoding="utf-8")

        # Script .bat que reemplaza los archivos de la app y la relanza.
        bat = exe_dir.parent / "_apply_update.bat"
        bat.write_text(
            "@echo off\r\n"
            "timeout /t 3 /nobreak >nul\r\n"
            f'xcopy /E /Y /I /EXCLUDE:"{exclude_file}" "{source_dir}\\*" "{exe_dir}"\r\n'
            f'rmdir /S /Q "{tmp_dir}"\r\n'
            f'del /Q "{exclude_file}"\r\n'
            f'start "" "{exe_dir}\\CredencializacionApp.exe"\r\n'
            'del "%~f0"\r\n',
            encoding="utf-8",
        )

        subprocess.Popen(["cmd", "/c", str(bat)], shell=False)
        return True
    except Exception as e:
        logger.error("Error al aplicar actualización: %s", e)
        return False


# ── Puente de señales (hilo de trabajo → hilo principal de la UI) ─────────────
class _UpdaterBridge(QObject):
    """Puente que traslada los resultados del hilo de verificación a la UI.

    Las señales se emiten desde un hilo de trabajo y, como el puente vive en el
    hilo principal, Qt entrega los slots de forma segura en dicho hilo (conexión
    en cola automática). Esto evita el frágil mecanismo de postEvent + filtro de
    eventos, que se perdía si el filtro era recolectado por el garbage collector.
    """

    update_available = Signal(str, str, str)  # version, asset_url, release_url
    feedback = Signal(str, str)               # message, level

    def __init__(self) -> None:
        super().__init__()
        self._parent_widget = None
        self.update_available.connect(self._on_update_available)
        self.feedback.connect(self._on_feedback)

    def set_parent_widget(self, widget) -> None:
        self._parent_widget = widget

    def _on_update_available(self, version: str, asset_url: str, release_url: str) -> None:
        global _dialog_open
        if _dialog_open:
            # Ya hay un diálogo de actualización abierto: no abrir otro.
            return
        _dialog_open = True
        try:
            _show_update_dialog(version, asset_url, release_url, self._parent_widget)
        finally:
            _dialog_open = False

    def _on_feedback(self, message: str, level: str) -> None:
        from credencializacion.ui.widgets.toast import ToastManager
        ToastManager.instance().show_toast(message, level)


# Referencia global para mantener vivo el puente durante toda la sesión.
_bridge: Optional[_UpdaterBridge] = None
# Evita abrir múltiples diálogos de actualización simultáneos (bucle dentro de
# una misma sesión).
_dialog_open: bool = False


def init_updater(parent=None) -> _UpdaterBridge:
    """Crea (una sola vez) el puente de actualización en el hilo principal.

    Debe llamarse desde el hilo principal de la UI (al iniciar la app o al
    pulsar el botón de actualización).

    Args:
        parent: Ventana padre para el diálogo de actualización.

    Returns:
        La instancia única de _UpdaterBridge.
    """
    global _bridge
    if _bridge is None:
        _bridge = _UpdaterBridge()
    if parent is not None:
        _bridge.set_parent_widget(parent)
    return _bridge


def check_for_updates(parent=None, manual: bool = False) -> None:
    """Verifica actualizaciones y, si hay una nueva, ofrece instalarla.

    La consulta de red se ejecuta en un hilo separado para no bloquear la UI;
    los resultados se comunican a la UI mediante señales (hilo principal).

    Args:
        parent: Ventana padre para el diálogo (QWidget o None).
        manual: True cuando lo dispara el usuario (botón). En ese caso siempre
                se consulta GitHub y se da feedback. False es la verificación
                silenciosa de arranque, que se omite en modo desarrollo.
    """
    bridge = init_updater(parent)

    # La verificación automática de arranque se omite en desarrollo para no
    # molestar; la verificación manual siempre se ejecuta para poder probarla.
    if not manual and not getattr(sys, "frozen", False):
        logger.debug("Modo desarrollo — verificación automática de actualizaciones omitida.")
        return

    def _check() -> None:
        if manual:
            bridge.feedback.emit("🔎 Buscando actualizaciones…", "info")

        release = get_latest_release()
        if not release:
            if manual:
                bridge.feedback.emit(
                    "No se pudo conectar con el servidor de actualizaciones.", "error"
                )
            return

        tag = release.get("tag_name", "")
        if not is_newer(tag):
            logger.info("La app está actualizada (v%s).", APP_VERSION)
            if manual:
                bridge.feedback.emit(
                    f"Ya tienes la última versión (v{APP_VERSION}).", "success"
                )
            return

        # Rompe el bucle de re-prompt entre reinicios: si ya se intentó instalar
        # esta misma versión y la app sigue ejecutando una anterior (la
        # actualización no completó), NO se vuelve a abrir automáticamente el
        # diálogo. El usuario puede reintentar manualmente. (Solo aplica a la
        # verificación automática de arranque.)
        if not manual and _read_attempted_version() == tag:
            logger.warning(
                "Ya se intentó actualizar a %s y la app sigue en v%s; se omite "
                "el aviso automático para evitar un bucle. Usa el botón de "
                "actualización para reintentar.",
                tag, APP_VERSION,
            )
            return

        # Hay una versión más reciente — buscar el asset descargable
        assets = release.get("assets", [])
        asset = next((a for a in assets if a["name"] == ASSET_NAME), None)
        release_url = release.get("html_url", "")

        if not asset:
            logger.warning("Release %s sin asset '%s'.", tag, ASSET_NAME)
            if manual:
                bridge.feedback.emit(
                    f"Versión {tag} disponible, pero aún no hay instalador para descargar.",
                    "warning",
                )
            return

        asset_url = asset["browser_download_url"]
        bridge.update_available.emit(tag, asset_url, release_url)

    Thread(target=_check, daemon=True).start()


# ── Diálogo de actualización disponible ───────────────────────────────────────
def _show_update_dialog(version: str, asset_url: str, release_url: str, parent) -> None:
    """Muestra el diálogo de actualización disponible (en el hilo principal)."""
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QProgressBar, QApplication,
    )
    from PySide6.QtCore import Qt, QUrl
    from PySide6.QtGui import QFont, QDesktopServices
    import tempfile

    dialog = QDialog(parent)
    dialog.setWindowTitle("Actualización disponible")
    dialog.setFixedWidth(420)
    dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(16)
    layout.setContentsMargins(24, 24, 24, 20)

    # Encabezado
    lbl_title = QLabel(f"🚀 Nueva versión disponible: <b>{version}</b>")
    lbl_title.setFont(QFont("Inter", 12))
    lbl_title.setWordWrap(True)

    self_update = can_self_update()
    if self_update:
        sub_text = (
            f"Tu versión actual es <b>v{APP_VERSION}</b>.<br>"
            "¿Deseas descargar e instalar la actualización ahora?"
        )
    else:
        sub_text = (
            f"Tu versión actual es <b>v{APP_VERSION}</b>.<br>"
            "La instalación automática solo está disponible en la versión "
            "instalada para Windows. Puedes abrir la página de descargas."
        )
    lbl_sub = QLabel(sub_text)
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
    if self_update:
        btn_primary = QPushButton("⬇  Descargar e instalar")
    else:
        btn_primary = QPushButton("🌐  Abrir página de descargas")
    btn_primary.setObjectName("primaryButton")
    btn_cancel = QPushButton("Ahora no")
    btn_cancel.setObjectName("outlineButton")

    btn_row = QHBoxLayout()
    btn_row.addWidget(btn_cancel)
    btn_row.addWidget(btn_primary)

    layout.addWidget(lbl_title)
    layout.addWidget(lbl_sub)
    layout.addWidget(progress)
    layout.addWidget(lbl_status)
    layout.addLayout(btn_row)

    def on_open_page():
        QDesktopServices.openUrl(QUrl(release_url or asset_url))
        dialog.accept()

    def on_update():
        btn_primary.setEnabled(False)
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
                # Registrar el intento ANTES de aplicar: si el relanzamiento no
                # completa la actualización, el arranque siguiente no volverá a
                # abrir el diálogo automáticamente (evita el bucle).
                _write_attempted_version(version)
                if apply_update(tmp):
                    QApplication.quit()
                else:
                    lbl_status.setText("❌ No se pudo aplicar la actualización.")
                    btn_cancel.setEnabled(True)
            else:
                lbl_status.setText("❌ Error al descargar. Intenta de nuevo más tarde.")
                btn_cancel.setEnabled(True)

        Thread(target=_download, daemon=True).start()

    btn_primary.clicked.connect(on_update if self_update else on_open_page)
    btn_cancel.clicked.connect(dialog.reject)

    dialog.exec()
