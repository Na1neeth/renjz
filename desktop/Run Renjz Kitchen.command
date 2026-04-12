#!/usr/bin/env bash

set -u

export PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin:/usr/sbin:/sbin"

APP_ROOT="/Users/renjz/Desktop/renjzkitchen/renjz"
LOG_FILE="$APP_ROOT/.renjis-uvicorn.log"
PORT="${PORT:-8000}"
URL="http://127.0.0.1:${PORT}"
LAN_IP=""

find_lan_ip() {
  local ip

  ip="$(ipconfig getifaddr en0 2>/dev/null || true)"
  if [[ -n "${ip:-}" ]]; then
    printf '%s\n' "$ip"
    return
  fi

  ip="$(ipconfig getifaddr en1 2>/dev/null || true)"
  if [[ -n "${ip:-}" ]]; then
    printf '%s\n' "$ip"
    return
  fi

  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [[ -n "${ip:-}" ]]; then
    printf '%s\n' "$ip"
    return
  fi
}

print_header() {
  clear
  echo "Renjz Kitchen"
  echo "-------------"
  echo
}

print_links() {
  echo "Open on this Mac:"
  echo "  $URL"
  echo

  LAN_IP="$(find_lan_ip)"
  if [[ -n "${LAN_IP:-}" ]]; then
    echo "Open on phone or another device on the same Wi-Fi:"
    echo "  http://${LAN_IP}:${PORT}"
  else
    echo "Phone link:"
    echo "  Could not detect Wi-Fi IP. Make sure Wi-Fi is connected."
  fi

  echo
  echo "Keep this Terminal window open while using the app."
  echo "Press Control-C here to stop the app server."
  echo
  echo "Server log:"
  echo "  $LOG_FILE"
  echo
  echo "Status: running"
}

is_server_up() {
  curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1
}

wait_for_server() {
  local attempts=60
  local count=0

  while (( count < attempts )); do
    if is_server_up; then
      return 0
    fi
    sleep 1
    ((count += 1))
  done

  return 1
}

wait_for_docker() {
  local attempts=90
  local count=0

  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker command not found. Install Docker Desktop first."
    return 1
  fi

  if docker info >/dev/null 2>&1; then
    return 0
  fi

  echo "Opening Docker Desktop..."
  open -a Docker >/dev/null 2>&1 || true

  while (( count < attempts )); do
    if docker info >/dev/null 2>&1; then
      echo "Docker is ready."
      return 0
    fi
    sleep 2
    ((count += 1))
  done

  echo "Docker Desktop did not become ready in time."
  return 1
}

start_database() {
  local running_container
  local existing_container

  running_container="$(docker ps --filter "name=^/restaurant_app_db$" --filter "status=running" -q 2>/dev/null || true)"
  if [[ -n "${running_container:-}" ]]; then
    echo "Database is already running."
    return 0
  fi

  existing_container="$(docker ps -a --filter "name=^/restaurant_app_db$" -q 2>/dev/null || true)"
  if [[ -n "${existing_container:-}" ]]; then
    echo "Starting database..."
    docker start restaurant_app_db >/dev/null
    return 0
  fi

  echo "Creating database..."
  docker run -d \
    --name restaurant_app_db \
    --restart unless-stopped \
    -e POSTGRES_DB=restaurant_app \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=postgres \
    -p 5432:5432 \
    -v renjz_postgres_data:/var/lib/postgresql/data \
    postgres:16-alpine >/dev/null
}

main() {
  cd "$APP_ROOT" || exit 1

  print_header
  echo "Starting Renjz Kitchen..."
  wait_for_docker || exit 1
  start_database || exit 1

  if is_server_up; then
    print_header
    print_links
    echo
    echo "Renjz Kitchen was already running."
    open "$URL"
    echo
    echo "You can close this Terminal window."
    read -r -p "Press Enter to close... "
    return 0
  fi

  if [[ ! -x "$APP_ROOT/venv/bin/uvicorn" ]]; then
    echo "Missing server dependency: $APP_ROOT/venv/bin/uvicorn"
    echo "Install dependencies with: venv/bin/pip install -r backend/requirements.txt"
    exit 1
  fi

  echo "Starting app server..."
  (
    if wait_for_server; then
      open "$URL"
      print_header
      print_links
    else
      print_header
      echo "Renjz Kitchen server did not become ready."
      echo "Log: $LOG_FILE"
    fi
  ) &

  print_header
  echo "Renjz Kitchen server is starting..."
  echo

  "$APP_ROOT/venv/bin/uvicorn" --app-dir "$APP_ROOT/backend" app.main:app --host 0.0.0.0 --port "$PORT" >>"$LOG_FILE" 2>&1
}

main
