#!/usr/bin/env bash
set -euo pipefail

# One-command macOS release build for Fleet Snowfluff.
# - Builds .app with PyInstaller
# - Packages .dmg for distribution
#
# Usage:
#   ./release_macos.sh
#   ./release_macos.sh v1.2.0beta

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script only supports macOS."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RELEASE_DIR="${PROJECT_ROOT}/release"

APP_NAME="Fleet Snowfluff"
DIST_DIR="${RELEASE_DIR}"
BUILD_DIR="${SCRIPT_DIR}/build"
DMG_STAGE_DIR="${SCRIPT_DIR}/dmg_stage"

VERSION="${1:-}"
if [[ -z "${VERSION}" ]]; then
  VERSION="$(python3 - <<'PY'
from pathlib import Path
import tomllib

pyproject = Path("pyproject.toml")
if not pyproject.exists():
      print("v1.2.0beta")
else:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    print(data.get("project", {}).get("version", "v1.2.0beta"))
PY
)"
fi

DMG_NAME="FleetSnowfluff-${VERSION}-macOS.dmg"
DMG_PATH="${RELEASE_DIR}/${DMG_NAME}"

ICON_OPT=()
ICON_ICNS_PATH="${PROJECT_ROOT}/resources/icon.icns"
ICON_WEBP_PATH="${PROJECT_ROOT}/resources/icon.webp"
APP_SUPPORT_DIR="${HOME}/Library/Application Support"

build_icns_from_source() {
  local source_image="$1"
  local output_icns="$2"
  local temp_dir
  local iconset_dir
  temp_dir="$(mktemp -d)"
  iconset_dir="${temp_dir}/icon.iconset"
  mkdir -p "${iconset_dir}"

  uv run python - "${source_image}" "${iconset_dir}" <<'PY'
import sys
from pathlib import Path
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt

source = Path(sys.argv[1])
iconset = Path(sys.argv[2])
img = QImage(str(source))
if img.isNull():
    raise SystemExit(f"Failed to load icon source: {source}")

targets = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]

for filename, size in targets:
    scaled = img.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    out_path = iconset / filename
    if not scaled.save(str(out_path), "PNG"):
        raise SystemExit(f"Failed to save icon: {out_path}")
PY

  iconutil -c icns "${iconset_dir}" -o "${output_icns}"
  rm -rf "${temp_dir}"
}

clean_developer_chat_history() {
  # Intentionally no-op:
  # keep developer's local usage traces and settings untouched.
  # Packaging sanitization is handled on build artifacts only.
  echo "   skip local data cleanup (keep developer history/settings)"
}

audit_release_bundle() {
  local app_bundle="$1"
  local canary="${RELEASE_CANARY:-}"
  local leaked=0

  for name in "settings.json" "chat_history.jsonl"; do
    if [[ -n "$(find "${app_bundle}" -type f -name "${name}" -print -quit)" ]]; then
      echo "ERROR: found forbidden runtime data file in bundle: ${name}"
      leaked=1
    fi
  done

  if [[ -n "${canary}" ]]; then
    if ! /usr/bin/python3 - "${app_bundle}" "${canary}" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
needle = sys.argv[2]
for p in root.rglob("*"):
    if not p.is_file():
        continue
    try:
        if p.stat().st_size > 8 * 1024 * 1024:
            continue
        data = p.read_bytes()
    except OSError:
        continue
    if needle.encode("utf-8") in data:
        print(p)
        raise SystemExit(2)
raise SystemExit(0)
PY
    then
      echo "ERROR: found RELEASE_CANARY in bundle files."
      leaked=1
    fi
  fi

  if [[ $leaked -ne 0 ]]; then
    exit 1
  fi
}

echo "==> Sync dependencies"
cd "${SCRIPT_DIR}"
uv sync

echo "==> Cleaning old artifacts"
mkdir -p "${RELEASE_DIR}"
rm -rf "${BUILD_DIR}" "${DMG_STAGE_DIR}" "${SCRIPT_DIR}/__pycache__" "${SCRIPT_DIR}"/*.spec "${DMG_PATH}" "${DIST_DIR}/${APP_NAME}.app"

echo "==> Removing developer chat history"
clean_developer_chat_history

if [[ ! -f "${ICON_ICNS_PATH}" && -f "${ICON_WEBP_PATH}" ]]; then
  echo "==> Generating icon.icns from icon.webp"
  build_icns_from_source "${ICON_WEBP_PATH}" "${ICON_ICNS_PATH}"
fi

if [[ -f "${ICON_ICNS_PATH}" ]]; then
  ICON_OPT=(--icon "${ICON_ICNS_PATH}")
fi

echo "==> Building .app with PyInstaller"
PYI_CMD=(
  uv run pyinstaller
  --noconfirm
  --clean
  --windowed
  --distpath "${DIST_DIR}"
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

APP_BUNDLE="${DIST_DIR}/${APP_NAME}.app"
if [[ ! -d "${APP_BUNDLE}" ]]; then
  echo "Build failed: app bundle not found at ${APP_BUNDLE}"
  exit 1
fi

echo "==> Sanitizing bundle (remove developer local data artifacts)"
find "${APP_BUNDLE}" -type f \( -name "chat_history.jsonl" -o -name "settings.json" \) -delete || true
echo "==> Auditing bundle for sensitive data leakage"
audit_release_bundle "${APP_BUNDLE}"

echo "==> Packaging DMG"
mkdir -p "${DMG_STAGE_DIR}"
cp -R "${APP_BUNDLE}" "${DMG_STAGE_DIR}/"
ln -s /Applications "${DMG_STAGE_DIR}/Applications"
cat > "${DMG_STAGE_DIR}/Uninstall and Cleanup.command" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APP_NAME="Fleet Snowfluff"
APP_PATH="/Applications/${APP_NAME}.app"
APP_SUPPORT_DIR="${HOME}/Library/Application Support"

echo "This will remove app and local sensitive data:"
echo "  - ${APP_PATH}"
echo "  - ${APP_SUPPORT_DIR}/FleetSnowfluff"
echo "  - ${APP_SUPPORT_DIR}/Aemeath"
read -r -p "Continue? [y/N] " ans
if [[ ! "${ans}" =~ ^[Yy]$ ]]; then
  echo "Cancelled."
  exit 0
fi

rm -rf "${APP_PATH}"
rm -rf "${APP_SUPPORT_DIR}/FleetSnowfluff" "${APP_SUPPORT_DIR}/Aemeath"
echo "Done."
EOF
chmod +x "${DMG_STAGE_DIR}/Uninstall and Cleanup.command"
hdiutil create \
  -volname "${APP_NAME}" \
  -srcfolder "${DMG_STAGE_DIR}" \
  -ov \
  -format UDZO \
  "${DMG_PATH}" >/dev/null
rm -rf "${DMG_STAGE_DIR}"

echo
echo "Release build complete:"
echo "  App: ${APP_BUNDLE}"
echo "  DMG: ${DMG_PATH}"
