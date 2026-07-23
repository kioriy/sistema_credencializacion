#!/bin/bash
# ============================================================
#  build_raspberry.sh
#  Script para generar el ejecutable de Raspberry Pi (Linux ARM64)
#
#  REQUISITOS:
#    - Raspberry Pi 4 o 5 con Raspberry Pi OS de 64 bits (aarch64).
#      No compatible con Raspberry Pi OS de 32 bits (armhf/armv7l):
#      PySide6 no publica ruedas para esa arquitectura.
#    - Python 3.12+ (Raspberry Pi OS Bookworm trae 3.11 por defecto;
#      instala 3.12 si tu versión de OS no lo trae de fábrica).
#    - Debe ejecutarse EN la propia Raspberry Pi: PyInstaller no compila
#      cruzado, el binario resultante solo corre en la arquitectura donde
#      se compiló.
#
#  USO (en la Raspberry Pi):
#    chmod +x build_raspberry.sh
#    ./build_raspberry.sh
#
#  El resultado queda en: dist/CredencializacionApp/
#  y empaquetado en:      dist/CredencializacionApp-RaspberryPi-arm64.tar.gz
# ============================================================

set -e

echo ""
echo "===================================================="
echo "  Sistema de Credencializacion -- Build Raspberry Pi"
echo "===================================================="
echo ""

# ── Verificar arquitectura ────────────────────────────────────────────────
ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ] && [ "$ARCH" != "arm64" ]; then
    echo "[ERROR] Arquitectura detectada: ${ARCH}."
    echo "  Este script debe correr en una Raspberry Pi con Raspberry Pi OS"
    echo "  de 64 bits (aarch64). PyInstaller no compila cruzado: el"
    echo "  ejecutable solo funciona en la arquitectura donde se compila."
    exit 1
fi

# ── Verificar Python 3.12+ ────────────────────────────────────────────────
PYTHON_BIN=""
for candidate in python3.12 python3.13 python3; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -eq 3 ] && [ "$minor" -ge 12 ]; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "[ERROR] No se encontró Python 3.12+."
    echo "  Raspberry Pi OS Bookworm trae Python 3.11 por defecto."
    echo "  Instala 3.12 (por ejemplo, compilándolo con pyenv) y reintenta."
    exit 1
fi

echo "[1/6] Usando $($PYTHON_BIN --version) (${PYTHON_BIN})"

# ── Librerías del sistema para el runtime de Qt/PySide6 ───────────────────
# Best-effort: en Raspberry Pi OS con escritorio ya suelen estar presentes
# (el propio escritorio corre sobre ellas). No se aborta el build si falla
# esta instalación (por ejemplo, sin sudo disponible).
echo "[2/6] Verificando librerías del sistema para Qt (best-effort)..."
if command -v apt-get &>/dev/null && [ "$(id -u)" -eq 0 -o -n "$(command -v sudo)" ]; then
    SUDO=""
    # sudo -n: no interactivo. Si hace falta contraseña y no está cacheada,
    # falla al instante en vez de colgarse esperando un prompt (p. ej. por SSH).
    [ "$(id -u)" -ne 0 ] && SUDO="sudo -n"
    $SUDO apt-get install -y --no-install-recommends \
        libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
        libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 \
        libxkbcommon-x11-0 libegl1 libopengl0 libfontconfig1 libdbus-1-3 \
        >/dev/null 2>&1 \
        && echo "  Librerías de Qt verificadas/instaladas." \
        || echo "  [warn] No se pudieron instalar automáticamente; si la app" \
                "no abre en el escritorio, instálalas manualmente."
else
    echo "  [warn] apt-get o sudo no disponibles; omitiendo (asume que ya están)."
fi

echo "[3/6] Activando entorno virtual (.venv_pi)..."
"$PYTHON_BIN" -m venv .venv_pi 2>/dev/null || true
source .venv_pi/bin/activate

echo "[4/6] Instalando dependencias..."
pip install -q --upgrade pip
pip install -q -e ".[dev]" 2>/dev/null || pip install -q \
    "PySide6>=6.7" "SQLAlchemy>=2.0" "reportlab>=4.0" "thefuzz[speedup]" \
    "requests>=2.31" "openpyxl>=3.1" "qrcode[pil]>=7.4" "Pillow>=10.0" \
    "gspread>=6.0" "google-auth>=2.0" "qtawesome>=1.4.2" "PyMuPDF>=1.24"

echo "[5/6] Instalando PyInstaller y compilando..."
pip install -q pyinstaller
pyinstaller credencializacion.spec --clean --noconfirm

echo "[6/6] Empaquetando ejecutable..."
(cd dist && tar -czf CredencializacionApp-RaspberryPi-arm64.tar.gz CredencializacionApp)

echo ""
echo "===================================================="
echo "  BUILD EXITOSO"
echo "  App:     dist/CredencializacionApp/"
echo "  Paquete: dist/CredencializacionApp-RaspberryPi-arm64.tar.gz"
echo "===================================================="
echo ""
echo "Para instalarla en esta u otra Raspberry Pi (misma arquitectura):"
echo "  1. Copia/extrae la carpeta CredencializacionApp/ donde prefieras"
echo "     (ej: ~/Apps/CredencializacionApp)."
echo "  2. Ejecuta ./CredencializacionApp/CredencializacionApp"
echo ""
echo "Acceso directo desde el menú de escritorio (opcional):"
echo "  Crea ~/.local/share/applications/credencializacion.desktop con:"
echo "    [Desktop Entry]"
echo "    Type=Application"
echo "    Name=Sistema de Credencialización"
echo "    Exec=/ruta/a/CredencializacionApp/CredencializacionApp"
echo "    Icon=/ruta/a/CredencializacionApp/_internal/resources/icons/app.png"
echo "    Terminal=false"
echo "    Categories=Office;"
echo ""
