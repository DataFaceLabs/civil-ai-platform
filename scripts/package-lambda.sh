#!/usr/bin/env bash
# Build the platform Lambda deployment zip for OpenTofu (linux/arm64 or x86_64).
# Run from civil-ai-platform repo root before `tofu apply` when create_http_api=true.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/infra/dist/platform-lambda.zip"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

cd "$ROOT"
uv export --frozen --no-dev --extra api -o "$BUILD_DIR/requirements.txt"
uv pip install --target "$BUILD_DIR" -r "$BUILD_DIR/requirements.txt" --python-platform aarch64-manylinux2014 --python-version 3.12

cp -R src/civilai_platform "$BUILD_DIR/"
# Vendor civilai-agent (editable dep) — minimal copy for Lambda
if [ -d "../civil-ai-agent/src/civilai_agent" ]; then
  cp -R ../civil-ai-agent/src/civilai_agent "$BUILD_DIR/"
fi

mkdir -p "$(dirname "$OUT")"
(cd "$BUILD_DIR" && zip -qr9 "$OUT" .)

echo "Wrote $OUT ($(du -h "$OUT" | cut -f1))"
