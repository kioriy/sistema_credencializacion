@echo off
REM ============================================================
REM  build_windows.bat
REM  Script para generar el ejecutable de Windows con PyInstaller
REM
REM  REQUISITOS:
REM    - Python 3.12+ instalado (python.org)
REM    - pip actualizado
REM    - Conexión a internet (para instalar dependencias)
REM
REM  USO:
REM    1. Abre una terminal (CMD o PowerShell) en esta carpeta
REM    2. Ejecuta: build_windows.bat
REM    3. El ejecutable quedará en: dist\CredencializacionApp\
REM ============================================================

echo.
echo ====================================================
echo   Sistema de Credencializacion -- Build de Windows
echo ====================================================
echo.

REM Verificar Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python no encontrado. Instala Python 3.12+ desde python.org
    pause
    exit /b 1
)

echo [1/5] Creando entorno virtual...
if not exist ".venv_win" (
    python -m venv .venv_win
)
call .venv_win\Scripts\activate.bat

echo [2/5] Actualizando pip...
python -m pip install --upgrade pip --quiet

echo [3/5] Instalando dependencias del proyecto...
pip install PySide6>=6.7 SQLAlchemy>=2.0 reportlab>=4.0 thefuzz[speedup] ^
    requests>=2.31 openpyxl>=3.1 "qrcode[pil]>=7.4" Pillow>=10.0 ^
    gspread>=6.0 google-auth>=2.0 qtawesome>=1.4.2 PyMuPDF>=1.24 --quiet

echo [4/5] Instalando PyInstaller...
pip install pyinstaller --quiet

echo [5/5] Compilando ejecutable...
pyinstaller credencializacion.spec --clean --noconfirm

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] La compilacion fallo. Revisa los mensajes de arriba.
    pause
    exit /b 1
)

echo.
echo ====================================================
echo   BUILD EXITOSO
echo   Ejecutable: dist\CredencializacionApp\CredencializacionApp.exe
echo ====================================================
echo.
echo Puedes copiar la carpeta dist\CredencializacionApp\ a cualquier PC Windows.
echo.
pause
