#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

stop_pid_file() {
  local label="$1"
  local pid_file="$2"

  if [ ! -f "$pid_file" ]; then
    echo "[stop] $label not running"
    return
  fi

  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "[stop] stopped $label: $pid"
  else
    echo "[stop] stale $label pid: $pid"
  fi
  rm -f "$pid_file"
}

stop_pid_file "frontend" "$ROOT_DIR/output/pids/frontend.pid"
stop_pid_file "backend" "$ROOT_DIR/output/pids/backend.pid"
