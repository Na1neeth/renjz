#!/usr/bin/env bash

set -u

export PATH="/Users/renjz/Desktop/renjzkitchen/renjz/venv/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="/Users/renjz"

APP_ROOT="/Users/renjz/Desktop/renjzkitchen/renjz"
LOG_FILE="$APP_ROOT/.renjis-uvicorn.log"

cd "$APP_ROOT" || exit 78

echo "==== launchd server start $(date '+%Y-%m-%d %H:%M:%S') ====" >>"$LOG_FILE"
exec "$APP_ROOT/venv/bin/uvicorn" --app-dir "$APP_ROOT/backend" app.main:app --host 0.0.0.0 --port 8000 >>"$LOG_FILE" 2>&1

