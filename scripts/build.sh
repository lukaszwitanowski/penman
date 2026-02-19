#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-0.1.0}"
PLATFORM="$(uname | tr '[:upper:]' '[:lower:]')"
ARTIFACT_NAME="Penman_${VERSION}_${PLATFORM}"

echo "Installing build dependencies..."
python -m pip install --upgrade pip
pip install pyinstaller

echo "Running quality gates..."
python -m compileall .
python -m unittest discover -s tests -v

echo "Building executable..."
pyinstaller \
  --noconfirm \
  --clean \
  --name Penman \
  --windowed \
  main.py

ARTIFACT_DIR="dist/${ARTIFACT_NAME}"
ZIP_PATH="dist/${ARTIFACT_NAME}.zip"

rm -rf "${ARTIFACT_DIR}"
mkdir -p "${ARTIFACT_DIR}"
cp -r dist/Penman/* "${ARTIFACT_DIR}/"

rm -f "${ZIP_PATH}"
(cd dist && zip -r "${ARTIFACT_NAME}.zip" "${ARTIFACT_NAME}")

echo "Build completed: ${ZIP_PATH}"
