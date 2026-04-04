# Renjz Kitchen on Mac

This guide is for running `Renjz Kitchen` on a Mac and sharing it with phones, tablets, or other PCs on the same Wi-Fi or hotspot.

If you are bringing the project from GitHub, first clone it:

```bash
git clone <your-github-repo-url>
cd 'renjis kitchen'
```

## What you need

- macOS
- `Python 3`
- `Docker Desktop`

Check them:

```bash
python3 --version
docker --version
docker compose version
```

## First-time setup

From the project root:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
docker compose up -d db
cd backend
../venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If everything starts correctly, open:

```text
http://127.0.0.1:8000
```

## Demo users

- waiter: `waiter / demo123`
- kitchen: `kitchen / demo123`
- receptionist: `reception / demo123`

## Share it on the same Wi-Fi

Keep the backend running with:

```bash
cd backend
../venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Find the Mac IP:

```bash
ipconfig getifaddr en0
```

If that returns nothing, try:

```bash
ipconfig getifaddr en1
```

Example result:

```text
192.168.1.20
```

Then other devices on the same Wi-Fi should open:

```text
http://192.168.1.20:8000
```

## Typical restaurant usage

- receptionist Mac: open the app and sign in as `reception`
- waiter phone: open the same URL and sign in as `waiter`
- kitchen phone/tablet: open the same URL and sign in as `kitchen`

## If macOS asks about connections

Allow incoming connections for Terminal or Python when prompted.

If phones still cannot connect:

- make sure all devices are on the same Wi-Fi or same hotspot
- turn off VPN while testing
- use `http`, not `https`
- close and reopen the browser tab after frontend updates

## Daily start

Start PostgreSQL:

```bash
docker compose up -d db
```

Start the app:

```bash
cd backend
../venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Daily stop

Stop the app with `Ctrl+C` in the terminal where `uvicorn` is running.

Stop PostgreSQL:

```bash
docker compose down
```

## Useful checks

Health check:

```text
http://127.0.0.1:8000/health
```

Find the Mac IP again:

```bash
ipconfig getifaddr en0
```

## Troubleshooting

If port `8000` is already in use:

```bash
lsof -i :8000
```

Then stop the old process or run a different port:

```bash
cd backend
../venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001
```

If Docker is not running, open Docker Desktop first and retry:

```bash
docker compose up -d db
```

If the app works on the Mac but not on the phone:

- verify the backend was started with `--host 0.0.0.0`
- verify the phone is on the same network
- use the Mac IP, not `127.0.0.1`
- reopen the page after code changes so cached JS/CSS is refreshed
