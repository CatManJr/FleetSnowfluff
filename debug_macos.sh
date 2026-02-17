#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script only supports macOS."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEBUG_RELEASE_DIR="${PROJECT_ROOT}/release-debug"
BUILD_DIR="${SCRIPT_DIR}/build-debug"

APP_NAME="Fleet Snowfluff Debug"
RUN_AFTER_BUILD="${RUN_AFTER_BUILD:-0}"
ICON_ICNS_PATH="${PROJECT_ROOT}/resources/icon.icns"
ICON_OPT=()

if [[ -f "${ICON_ICNS_PATH}" ]]; then
  ICON_OPT=(--icon "${ICON_ICNS_PATH}")
fi

echo "==> Sync dependencies"
cd "${SCRIPT_DIR}"
uv sync

echo "==> Cleaning debug artifacts"
mkdir -p "${DEBUG_RELEASE_DIR}"
rm -rf "${BUILD_DIR}" "${SCRIPT_DIR}/__pycache__" "${SCRIPT_DIR}"/*.spec "${DEBUG_RELEASE_DIR}/${APP_NAME}.app"

echo "==> Building debug .app with PyInstaller"
PYI_CMD=(
  uv run pyinstaller
  --noconfirm
  --clean
  --console
  --log-level DEBUG
  --debug all
  --distpath "${DEBUG_RELEASE_DIR}"
  --workpath "${BUILD_DIR}"
  --specpath "${SCRIPT_DIR}"
  --name "${APP_NAME}"
  --add-data "${PROJECT_ROOT}/resources:resources"
  --add-data "${SCRIPT_DIR}/config/FleetSnowfluff.json:resources/config"
)
if [[ ${#ICON_OPT[@]} -gt 0 ]]; then
  PYI_CMD+=("${ICON_OPT[@]}")
fi
PYI_CMD+=("${SCRIPT_DIR}/main.py")
"${PYI_CMD[@]}"

APP_BUNDLE="${DEBUG_RELEASE_DIR}/${APP_NAME}.app"
if [[ ! -d "${APP_BUNDLE}" ]]; then
  echo "Build failed: app bundle not found at ${APP_BUNDLE}"
  exit 1
fi

echo
echo "Debug build complete:"
echo "  App: ${APP_BUNDLE}"
echo
echo "To run with terminal logs:"
echo "  \"${APP_BUNDLE}/Contents/MacOS/${APP_NAME}\""

if [[ "${RUN_AFTER_BUILD}" == "1" ]]; then
  echo "==> Launching debug app in foreground"
  "${APP_BUNDLE}/Contents/MacOS/${APP_NAME}"
fi
