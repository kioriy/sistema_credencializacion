#!/bin/bash
# ============================================================
#  release.sh — Publica una nueva versión del sistema
#
#  USO:
#    ./release.sh 1.0.1          → publica la versión 1.0.1
#    ./release.sh                → pregunta la versión
#
#  Lo que hace automáticamente:
#    1. Actualiza la versión en pyproject.toml
#    2. Actualiza APP_VERSION en updater.py
#    3. Hace commit con el cambio
#    4. Crea el tag v1.0.1
#    5. Hace push del commit y del tag a GitHub
#    6. GitHub Actions compila el .exe automáticamente (~5 min)
# ============================================================

set -e

# ── Colores para la terminal ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

print_step() { echo -e "\n${BLUE}[${1}/${TOTAL_STEPS}]${NC} ${BOLD}${2}${NC}"; }
print_ok()   { echo -e "  ${GREEN}✓${NC} ${1}"; }
print_warn() { echo -e "  ${YELLOW}⚠${NC}  ${1}"; }
print_err()  { echo -e "  ${RED}✗${NC}  ${1}"; }

TOTAL_STEPS=5

echo ""
echo -e "${BOLD}=====================================================${NC}"
echo -e "${BOLD}   Sistema de Credencialización — Publicar versión   ${NC}"
echo -e "${BOLD}=====================================================${NC}"

# ── Obtener la versión nueva ──────────────────────────────────────────────────
NEW_VERSION="${1}"

if [ -z "$NEW_VERSION" ]; then
    # Leer la versión actual del pyproject.toml
    CURRENT=$(grep '^version' pyproject.toml | head -1 | sed 's/version = "//;s/"//')
    echo ""
    echo -e "  Versión actual: ${YELLOW}${CURRENT}${NC}"
    echo -n "  Nueva versión (ej: 1.0.1): "
    read NEW_VERSION
fi

# Validar formato x.y.z
if ! echo "$NEW_VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    print_err "Formato de versión inválido. Usa: X.Y.Z (ej: 1.0.1)"
    exit 1
fi

TAG="v${NEW_VERSION}"

echo ""
echo -e "  Publicando versión: ${GREEN}${TAG}${NC}"
echo ""
read -p "  ¿Confirmas? (s/N): " CONFIRM
if [[ ! "$CONFIRM" =~ ^[sS]$ ]]; then
    echo "  Cancelado."
    exit 0
fi

# ── Verificar que estamos en main y no hay cambios sin commit ─────────────────
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
    print_warn "Estás en la rama '${BRANCH}', no en 'main'."
    read -p "  ¿Continuar de todas formas? (s/N): " C
    [[ ! "$C" =~ ^[sS]$ ]] && exit 0
fi

if ! git diff-index --quiet HEAD --; then
    print_err "Tienes cambios sin commit. Haz commit primero."
    exit 1
fi

# ── Verificar que el tag no existe ya ────────────────────────────────────────
if git rev-parse "$TAG" >/dev/null 2>&1; then
    print_err "El tag ${TAG} ya existe. Elige otra versión."
    exit 1
fi

# ── PASO 1: Actualizar pyproject.toml ────────────────────────────────────────
print_step 1 "Actualizando pyproject.toml → version = \"${NEW_VERSION}\""

sed -i '' "s/^version = \".*\"/version = \"${NEW_VERSION}\"/" pyproject.toml
print_ok "pyproject.toml actualizado"

# ── PASO 2: Actualizar updater.py ────────────────────────────────────────────
print_step 2 "Actualizando updater.py → APP_VERSION = \"${NEW_VERSION}\""

sed -i '' "s/^APP_VERSION = \".*\"/APP_VERSION = \"${NEW_VERSION}\"/" \
    src/credencializacion/core/updater.py
print_ok "updater.py actualizado"

# ── PASO 3: Commit ───────────────────────────────────────────────────────────
print_step 3 "Haciendo commit del bump de versión"

git add pyproject.toml src/credencializacion/core/updater.py
git commit -m "🔖 bump version to ${NEW_VERSION}"
print_ok "Commit creado"

# ── PASO 4: Crear tag ────────────────────────────────────────────────────────
print_step 4 "Creando tag ${TAG}"

git tag -a "$TAG" -m "Versión ${NEW_VERSION}"
print_ok "Tag ${TAG} creado"

# ── PASO 5: Push ──────────────────────────────────────────────────────────────
print_step 5 "Subiendo a GitHub (commit + tag)"

git push origin main
git push origin "$TAG"
print_ok "Push completado"

# ── Resultado ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}=====================================================${NC}"
echo -e "${GREEN}${BOLD}   ✅ Versión ${TAG} publicada exitosamente          ${NC}"
echo -e "${GREEN}${BOLD}=====================================================${NC}"
echo ""
echo -e "  GitHub Actions está compilando el .exe ahora mismo."
echo -e "  Revisa el progreso en:"
echo -e "  ${BLUE}https://github.com/kioriy/sistema_credencializacion/actions${NC}"
echo ""
echo -e "  En ~5 minutos el Release estará disponible en:"
echo -e "  ${BLUE}https://github.com/kioriy/sistema_credencializacion/releases${NC}"
echo ""
echo -e "  Los usuarios verán la alerta de actualización"
echo -e "  la próxima vez que abran la app. 🚀"
echo ""
