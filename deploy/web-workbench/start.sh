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

export PIPELINE_WORKER_MODE="${PIPELINE_WORKER_MODE:-codex}"
export CODEX_BIN="${CODEX_BIN:-codex}"
export HERMES_BIN="${HERMES_BIN:-hermes}"
export HERMES_MODEL="${HERMES_MODEL:-}"
export HERMES_PROVIDER="${HERMES_PROVIDER:-}"
export HERMES_TOOLSETS="${HERMES_TOOLSETS:-}"
export PIPELINE_WORKER_TIMEOUT_SECONDS="${PIPELINE_WORKER_TIMEOUT_SECONDS:-1200}"
export MAX_UPLOAD_MB="${MAX_UPLOAD_MB:-200}"
export BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
export BACKEND_PORT="${BACKEND_PORT:-8000}"
export FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
export FRONTEND_PORT="${FRONTEND_PORT:-3000}"
export API_BASE="${API_BASE:-http://127.0.0.1:${BACKEND_PORT}}"
export NEXT_PUBLIC_API_BASE="${NEXT_PUBLIC_API_BASE:-$API_BASE}"
export PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-http://127.0.0.1:${FRONTEND_PORT}}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://127.0.0.1:${FRONTEND_PORT},http://localhost:${FRONTEND_PORT}}"

mkdir -p "$ROOT_DIR/output/logs" "$ROOT_DIR/output/pids" "$ROOT_DIR/storage/jobs" "$ROOT_DIR/storage/workspaces" "$ROOT_DIR/storage/knowledge_base" "$ROOT_DIR/storage/presets"

if [ -f "$ROOT_DIR/output/pids/backend.pid" ] && kill -0 "$(cat "$ROOT_DIR/output/pids/backend.pid")" 2>/dev/null; then
  echo "[start] backend already running: $(cat "$ROOT_DIR/output/pids/backend.pid")"
else
  cd "$ROOT_DIR/backend"
  nohup "$ROOT_DIR/backend/.venv/bin/uvicorn" app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
    > "$ROOT_DIR/output/logs/backend.log" 2>&1 &
  echo $! > "$ROOT_DIR/output/pids/backend.pid"
  echo "[start] backend pid: $(cat "$ROOT_DIR/output/pids/backend.pid")"
fi

if [ -f "$ROOT_DIR/output/pids/frontend.pid" ] && kill -0 "$(cat "$ROOT_DIR/output/pids/frontend.pid")" 2>/dev/null; then
  echo "[start] frontend already running: $(cat "$ROOT_DIR/output/pids/frontend.pid")"
else
  cd "$ROOT_DIR/frontend"
  if [ -f "$ROOT_DIR/frontend/.next/standalone/server.js" ]; then
    nohup env HOSTNAME="$FRONTEND_HOST" PORT="$FRONTEND_PORT" API_BASE="$API_BASE" NEXT_PUBLIC_API_BASE="$NEXT_PUBLIC_API_BASE" \
      node "$ROOT_DIR/frontend/.next/standalone/server.js" \
      > "$ROOT_DIR/output/logs/frontend.log" 2>&1 &
  else
    nohup env API_BASE="$API_BASE" NEXT_PUBLIC_API_BASE="$NEXT_PUBLIC_API_BASE" \
      npm run dev -- --hostname "$FRONTEND_HOST" --port "$FRONTEND_PORT" \
      > "$ROOT_DIR/output/logs/frontend.log" 2>&1 &
  fi
  echo $! > "$ROOT_DIR/output/pids/frontend.pid"
  echo "[start] frontend pid: $(cat "$ROOT_DIR/output/pids/frontend.pid")"
fi

echo "[start] frontend: http://127.0.0.1:${FRONTEND_PORT}/create"
echo "[start] backend health: http://127.0.0.1:${BACKEND_PORT}/api/health"
