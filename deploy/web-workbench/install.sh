#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

echo "[install] backend dependencies"
cd "$ROOT_DIR/backend"
python3 -m venv .venv
"$ROOT_DIR/backend/.venv/bin/pip" install --upgrade pip
"$ROOT_DIR/backend/.venv/bin/pip" install -r requirements.txt

echo "[install] frontend dependencies"
cd "$ROOT_DIR/frontend"
npm ci

echo "[install] frontend production build"
API_BASE="${API_BASE:-http://127.0.0.1:8000}" NEXT_PUBLIC_API_BASE="${NEXT_PUBLIC_API_BASE:-http://127.0.0.1:8000}" npm run build

if [ -f "$ROOT_DIR/frontend/.next/standalone/server.js" ]; then
  echo "[install] copy frontend static assets for standalone runtime"
  rm -rf "$ROOT_DIR/frontend/.next/standalone/.next/static"
  mkdir -p "$ROOT_DIR/frontend/.next/standalone/.next"
  cp -R "$ROOT_DIR/frontend/.next/static" "$ROOT_DIR/frontend/.next/standalone/.next/static"

  if [ -d "$ROOT_DIR/frontend/public" ]; then
    rm -rf "$ROOT_DIR/frontend/.next/standalone/public"
    cp -R "$ROOT_DIR/frontend/public" "$ROOT_DIR/frontend/.next/standalone/public"
  fi
fi

echo "[install] done"
