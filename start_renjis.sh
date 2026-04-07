#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_UVICORN="$ROOT_DIR/venv/bin/uvicorn"
PID_FILE="$ROOT_DIR/.renjis-uvicorn.pid"
LOG_FILE="$ROOT_DIR/.renjis-uvicorn.log"
PORT="${PORT:-8000}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1"
    exit 1
  fi
}

find_lan_ip() {
  local ip
  ip="$(ip route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "src") { print $(i + 1); exit }}')"
  if [[ -n "${ip:-}" ]]; then
    printf '%s\n' "$ip"
    return
  fi

  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  printf '%s\n' "${ip:-}"
}

is_server_up() {
  curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1
}

wait_for_server() {
  local attempts=30
  local delay=1
  local count=0
  while (( count < attempts )); do
    if is_server_up; then
      return 0
    fi
    sleep "$delay"
    ((count += 1))
  done
  return 1
}

print_urls() {
  local lan_ip
  lan_ip="$(find_lan_ip)"

  echo
  echo "Renjz Kitchen is running."
  echo "Laptop: http://127.0.0.1:${PORT}"
  if [[ -n "${lan_ip:-}" ]]; then
    echo "Phone : http://${lan_ip}:${PORT}"
  else
    echo "Phone : Could not detect LAN IP automatically."
  fi
  echo "Health: http://127.0.0.1:${PORT}/health"
  echo "Log   : ${LOG_FILE}"
}

require_command docker
require_command curl
require_command hostname

if [[ ! -x "$VENV_UVICORN" ]]; then
  echo "Missing uvicorn at ${VENV_UVICORN}"
  echo "Create the virtualenv and install dependencies first."
  exit 1
fi

cd "$ROOT_DIR"
docker compose up -d db >/dev/null

if is_server_up; then
  print_urls
  exit 0
fi

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${existing_pid:-}" ]] && kill -0 "$existing_pid" >/dev/null 2>&1; then
    if wait_for_server; then
      print_urls
      exit 0
    fi
  fi
  rm -f "$PID_FILE"
fi

nohup "$VENV_UVICORN" --app-dir "$ROOT_DIR/backend" app.main:app --host 0.0.0.0 --port "$PORT" --reload >"$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

if ! wait_for_server; then
  echo "Server did not start successfully."
  echo "Check log: ${LOG_FILE}"
  exit 1
fi

print_urls
