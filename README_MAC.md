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

Fresh databases start empty by default. If you ever want demo/sample orders on a brand new database, copy `backend/.env.example` to `backend/.env` and set `SEED_DEMO_DATA=true` before the first app startup.

If everything starts correctly, open:

```text
http://127.0.0.1:8000
```

## Receipt printer on Mac

This app can print a receipt automatically after checkout to an `ESC/POS` network printer.

Copy the env file if you have not already:

```bash
cp backend/.env.example backend/.env
```

Then set these values in `backend/.env`:

```env
RECEIPT_PRINTER_ENABLED=true
RECEIPT_PRINTER_HOST=192.168.0.57
RECEIPT_PRINTER_PORT=9100
RECEIPT_SHOP_NAME=RENJZ KITCHEN
RECEIPT_ADDRESS_LINES=Bhuvanappa layout, 30, 31, 32|2nd cross road, Tavarekere Main Rd,|DRC Post, Bengaluru, Karnataka 560029
RECEIPT_PHONE=9400204473
```

Notes:

- The printer self-test should show `Protocol: ESC/POS`.
- The printer host should match the printer IP from the self-test page.
- `9100` is the common raw network printing port for thermal printers.
- `Print bill` now prints a sample-style bill before payment completion.
- Payment is still saved even if printing fails, and the reception screen will show the print result.

## Staff users

- receptionist: `reception1 / 3001`
- kitchen: `kitchen1 / 2001`
- sales: `sales1 / 4001`
- waiter: `waiter1 / 1001`
- waiter: `waiter2 / 1002`
- waiter: `waiter3 / 1003`
- waiter: `waiter4 / 1004`
- waiter: `waiter5 / 1005`

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
