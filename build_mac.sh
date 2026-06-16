#!/bin/bash
# ============================================================
#  build_mac.sh
#  Script para generar el ejecutable de macOS (.app)
#
#  USO:
#    chmod +x build_mac.sh
#    ./build_mac.sh
#
#  El resultado queda en: dist/CredencializacionApp.app
# ============================================================

set -e

echo ""
echo "===================================================="
echo "  Sistema de Credencializacion -- Build de macOS"
echo "===================================================="
echo ""

# Verificar Python
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 no encontrado."
    exit 1
fi

echo "[1/4] Activando entorno virtual..."
source .venv/bin/activate 2>/dev/null || {
    echo "  Creando entorno virtual..."
    python3 -m venv .venv
    source .venv/bin/activate
}

echo "[2/4] Instalando dependencias..."
pip install -q -e ".[dev]" 2>/dev/null || pip install -q \
    "PySide6>=6.7" "SQLAlchemy>=2.0" "reportlab>=4.0" "thefuzz[speedup]" \
    "requests>=2.31" "openpyxl>=3.1" "qrcode[pil]>=7.4" "Pillow>=10.0" \
    "gspread>=6.0" "google-auth>=2.0" "qtawesome>=1.4.2"

echo "[3/4] Instalando PyInstaller..."
pip install -q pyinstaller

echo "[4/4] Compilando ejecutable macOS..."
pyinstaller credencializacion.spec \
    --clean \
    --noconfirm \
    --target-arch $(uname -m)

echo ""
echo "===================================================="
echo "  BUILD EXITOSO"
echo "  App: dist/CredencializacionApp/"
echo "===================================================="
echo ""
