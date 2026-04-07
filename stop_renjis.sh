#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/.renjis-uvicorn.pid"

stop_server() {
  local stopped=0

  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
      stopped=1
    fi
    rm -f "$PID_FILE"
  fi

  pkill -f "uvicorn .*app.main:app" >/dev/null 2>&1 && stopped=1 || true

  if [[ "$stopped" -eq 1 ]]; then
    echo "Renjz Kitchen app server stopped."
  else
    echo "Renjz Kitchen app server was not running."
  fi
}

stop_database() {
  cd "$ROOT_DIR"
  docker compose down >/dev/null
  echo "Renjz Kitchen database stopped."
}

stop_server
stop_database
