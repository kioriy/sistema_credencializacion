# -*- mode: python ; coding: utf-8 -*-
#
# credencializacion.spec
# Archivo de especificación para PyInstaller
#
# Uso en Windows:
#   pip install pyinstaller
#   pyinstaller credencializacion.spec
#
# Esto genera:
#   dist/CredencializacionApp/  — carpeta con el ejecutable y sus dependencias
#   dist/CredencializacionApp/CredencializacionApp.exe

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH)

# ── Binarios y datos extra que PyInstaller no detecta automáticamente ────────
datas = [
    # Recursos del proyecto (fuentes, iconos, plantillas)
    (str(ROOT / "resources"),  "resources"),
    # Carpeta de plantilla base (puede estar vacía al compilar)
    (str(ROOT / "plantilla_base"), "plantilla_base"),
    # ReportLab necesita sus datos internos
    *collect_data_files("reportlab"),
    # QR code
    *collect_data_files("qrcode"),
    # PySide6 — plugins Qt necesarios (impresión, imagen, plataforma)
    *collect_data_files("PySide6"),
]

# ── Imports ocultos que PyInstaller no detecta por ser dinámicos ─────────────
hiddenimports = [
    # SQLAlchemy dialects
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.orm",
    "sqlalchemy.ext.declarative",
    # ReportLab internals
    "reportlab.graphics.barcode.common",
    "reportlab.graphics.barcode.code128",
    "reportlab.graphics.barcode.code39",
    "reportlab.graphics.barcode.code93",
    "reportlab.graphics.barcode.qr",
    "reportlab.graphics.barcode.eanbc",
    "reportlab.graphics.barcode.ecc200datamatrix",
    "reportlab.graphics.barcode.usps",
    "reportlab.graphics.barcode.usps4s",
    "reportlab.graphics.barcode.widgets",
    "reportlab.pdfbase.pdfmetrics",
    "reportlab.pdfbase.ttfonts",
    "reportlab.platypus",
    # Pillow
    "PIL._tkinter_finder",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    # QR code
    "qrcode",
    "qrcode.image.pil",
    # Fuzzy matching
    "thefuzz",
    "thefuzz.fuzz",
    "thefuzz.process",
    "Levenshtein",
    # PySide6
    "PySide6.QtPrintSupport",
    "PySide6.QtSvg",
    "PySide6.QtXml",
    # PyMuPDF (vista previa de PDFs)
    "fitz",
    "pymupdf",
    # Requests / urllib3
    "requests",
    "urllib3",
    "certifi",
    "charset_normalizer",
    # Google auth (gspread)
    "google.auth",
    "google.auth.transport.requests",
    "gspread",
    # Módulos internos del proyecto
    "credencializacion",
    "credencializacion.main",
    "credencializacion.db",
    "credencializacion.db.engine",
    "credencializacion.db.models",
    "credencializacion.db.migrations",
    "credencializacion.adapters",
    "credencializacion.adapters.miescuela",
    "credencializacion.adapters.base",
    "credencializacion.adapters.normalizer",
    "credencializacion.adapters.image_cache",
    "credencializacion.renderer",
    "credencializacion.renderer.pdf_engine",
    "credencializacion.renderer.coordinates",
    "credencializacion.renderer.rotation",
    "credencializacion.ui",
    "credencializacion.ui.app",
    "credencializacion.ui.main_window",
    "credencializacion.ui.styles",
    "credencializacion.ui.pages.control_panel",
    "credencializacion.ui.pages.template_editor",
    "credencializacion.ui.widgets.canvas",
    "credencializacion.ui.widgets.record_table",
    "credencializacion.ui.widgets.print_queue",
    "credencializacion.ui.widgets.sidebar",
    "credencializacion.core.settings",
    "credencializacion.utils.qr",
    "credencializacion.utils.fonts",
] + collect_submodules("credencializacion") + collect_submodules("reportlab")

# ── Análisis ─────────────────────────────────────────────────────────────────
a = Analysis(
    # Punto de entrada: main.py en la raíz del proyecto
    [str(ROOT / "main.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Excluir lo que no necesitamos para reducir tamaño
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "jupyter",
        "IPython",
        "test",
        "tests",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CredencializacionApp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,               # Compresión UPX (instala UPX para activarla)
    console=False,          # Sin ventana de consola (app gráfica)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="resources/icons/app.ico",  # Descomenta y pon tu ícono .ico
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CredencializacionApp",
)
