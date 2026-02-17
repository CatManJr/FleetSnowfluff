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
