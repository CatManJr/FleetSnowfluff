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
RESOURCES_STAGE_DIR="${BUILD_DIR}/resources_release"

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
# DMG format:
# - UDBZ: highest compression (slower build, smaller file)
# - UDZO: gzip-compressed (faster build)
DMG_FORMAT="${DMG_FORMAT:-UDBZ}"
RESOURCE_COMPRESS="${RESOURCE_COMPRESS:-1}"
JPEG_QUALITY="${JPEG_QUALITY:-82}"
MP3_BITRATE="${MP3_BITRATE:-128k}"
M4A_BITRATE="${M4A_BITRATE:-128k}"
OGG_QUALITY="${OGG_QUALITY:-4}"

ICON_OPT=()
ICON_ICNS_PATH="${PROJECT_ROOT}/resources/icon.icns"
ICON_WEBP_PATH="${PROJECT_ROOT}/resources/icon.webp"
APP_SUPPORT_DIR="${HOME}/Library/Application Support"
PYI_EXCLUDE_MODULES=(
  pytest
  _pytest
  hypothesis
  IPython
  ipykernel
  jupyter
  jupyter_client
  jupyter_core
  notebook
  matplotlib
  pandas
  scipy
)

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

prepare_release_resources() {
  local src_dir="${PROJECT_ROOT}/resources"
  local stage_dir="${RESOURCES_STAGE_DIR}"
  local ffmpeg_bin=""

  rm -rf "${stage_dir}"
  mkdir -p "${stage_dir}"
  cp -R "${src_dir}/." "${stage_dir}/"

  if [[ "${RESOURCE_COMPRESS}" != "1" ]]; then
    echo "==> Resource compression disabled (RESOURCE_COMPRESS=${RESOURCE_COMPRESS})"
    return
  fi

  if command -v ffmpeg >/dev/null 2>&1; then
    ffmpeg_bin="$(command -v ffmpeg)"
  fi
  echo "==> Optimizing release resources (stage only)"
  /usr/bin/python3 - "${stage_dir}" "${ffmpeg_bin}" "${JPEG_QUALITY}" "${MP3_BITRATE}" "${M4A_BITRATE}" "${OGG_QUALITY}" <<'PY'
import shutil
import subprocess
import sys
from pathlib import Path

stage_dir = Path(sys.argv[1])
ffmpeg = sys.argv[2]
jpeg_quality = str(max(20, min(95, int(sys.argv[3]))))
mp3_bitrate = sys.argv[4]
m4a_bitrate = sys.argv[5]
ogg_quality = sys.argv[6]

saved_bytes = 0
optimized_images = 0
optimized_audio = 0

def replace_if_smaller(src: Path, tmp: Path) -> bool:
    global saved_bytes
    if not tmp.exists():
        return False
    try:
        old_size = src.stat().st_size
        new_size = tmp.stat().st_size
    except OSError:
        return False
    if new_size <= 0 or new_size >= old_size:
        return False
    src.unlink(missing_ok=True)
    tmp.replace(src)
    saved_bytes += old_size - new_size
    return True

for path in stage_dir.rglob("*"):
    if not path.is_file():
        continue
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"} and shutil.which("sips"):
        tmp = path.with_suffix(path.suffix + ".tmp")
        cmd = [
            "sips",
            "-s",
            "format",
            "jpeg",
            "-s",
            "formatOptions",
            jpeg_quality,
            str(path),
            "--out",
            str(tmp),
        ]
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if proc.returncode == 0 and replace_if_smaller(path, tmp):
            optimized_images += 1
        if tmp.exists():
            tmp.unlink(missing_ok=True)

if ffmpeg:
    codec_map = {
        ".mp3": ["-c:a", "libmp3lame", "-b:a", mp3_bitrate],
        ".m4a": ["-c:a", "aac", "-b:a", m4a_bitrate],
        ".ogg": ["-c:a", "libvorbis", "-q:a", ogg_quality],
    }
    for path in stage_dir.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        codec_args = codec_map.get(suffix)
        if codec_args is None:
            continue
        # Skip tiny files to avoid needless quality churn.
        try:
            if path.stat().st_size < 512 * 1024:
                continue
        except OSError:
            continue
        tmp = path.with_suffix(path.suffix + ".tmp")
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(path),
            "-map_metadata",
            "-1",
            "-vn",
            *codec_args,
            str(tmp),
        ]
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if proc.returncode == 0 and replace_if_smaller(path, tmp):
            optimized_audio += 1
        if tmp.exists():
            tmp.unlink(missing_ok=True)

print(
    f"   optimized images={optimized_images}, audio={optimized_audio}, "
    f"saved={saved_bytes / (1024 * 1024):.2f}MB"
)
PY
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

prepare_release_resources

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
  --add-data "${RESOURCES_STAGE_DIR}:resources"
  --add-data "${SCRIPT_DIR}/config/FleetSnowfluff.json:resources/config"
)
for mod in "${PYI_EXCLUDE_MODULES[@]}"; do
  PYI_CMD+=(--exclude-module "${mod}")
done
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
DMG_IMAGEKEY_ARGS=()
case "${DMG_FORMAT}" in
  UDBZ)
    # bzip2 level 9 gives smaller DMG, but significantly slower to build.
    DMG_IMAGEKEY_ARGS=(-imagekey bzip2-level=9)
    ;;
  UDZO)
    # zlib level 9 balances compatibility with better compression.
    DMG_IMAGEKEY_ARGS=(-imagekey zlib-level=9)
    ;;
  *)
    echo "Unsupported DMG_FORMAT=${DMG_FORMAT}. Use UDBZ or UDZO."
    exit 1
    ;;
esac
hdiutil create \
  -volname "${APP_NAME}" \
  -srcfolder "${DMG_STAGE_DIR}" \
  -ov \
  -format "${DMG_FORMAT}" \
  "${DMG_IMAGEKEY_ARGS[@]}" \
  "${DMG_PATH}" >/dev/null
rm -rf "${DMG_STAGE_DIR}"

echo
echo "Release build complete:"
echo "  App: ${APP_BUNDLE}"
echo "  DMG: ${DMG_PATH}"
echo "  DMG format: ${DMG_FORMAT}"
