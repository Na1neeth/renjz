# Renjz Kitchen

Restaurant order management MVP for four roles:

- `waiter`: table-based free-text ordering
- `kitchen`: live active order dashboard
- `receptionist`: manual billing and payment closure
- `sales`: standalone sales dashboard with trends and item reporting

The app is built with:

- `FastAPI` backend
- `PostgreSQL` database
- `WebSockets` for live updates
- plain `HTML/CSS/JavaScript` frontend served by FastAPI

For Mac setup and local network sharing, see [README_MAC.md](./README_MAC.md).

## What this MVP supports

- Free-text items instead of a fixed menu
- Repeated edits to a running table order
- Preserved cancelled items and full order activity history
- Live kitchen visibility through websocket updates
- Manual billing with editable quantity and price per line
- Payment completion that closes the bill

## Project structure

```text
.
├── backend
│   ├── app
│   │   ├── api
│   │   ├── core
│   │   ├── db
│   │   ├── models
│   │   ├── schemas
│   │   ├── services
│   │   └── websockets
│   ├── .env.example
│   └── requirements.txt
├── frontend
│   ├── index.html
│   ├── js
│   └── styles
├── docker-compose.yml
├── README_MAC.md
└── README.md
```

## Main data model

- `users`
- `tables`
- `orders`
- `order_items`
- `order_activity_logs`
- `billing_items`
- `payments`

`order_items` keep the current order state. `order_activity_logs` keep the immutable action history for adds, edits, cancellations, kitchen changes, billing saves, and payment completion.

## Staff users

- receptionist: `reception1 / 3001`
- kitchen: `kitchen1 / 2001`
- sales: `sales1 / 4001`
- waiter: `waiter1 / 1001`
- waiter: `waiter2 / 1002`
- waiter: `waiter3 / 1003`
- waiter: `waiter4 / 1004`
- waiter: `waiter5 / 1005`

## Upload to GitHub

This project folder is ready to be uploaded as its own GitHub repository.

If you want to publish only this app and not the larger parent folder on your Ubuntu machine, run these commands from inside this folder:

```bash
cd ~/Desktop/'renjis kitchen'
git init
git add .
git commit -m "Initial Renjz Kitchen MVP"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```

After that, on the Mac:

```bash
git clone <your-github-repo-url>
cd 'renjis kitchen'
```

Then continue with the Mac setup in [README_MAC.md](./README_MAC.md).

## Default startup data

- Fresh databases start clean by default.
- The app creates staff users and restaurant tables only.
- No sample orders, billing rows, or payments are inserted unless you explicitly enable demo seeding.
- To enable demo records on a brand new database, set `SEED_DEMO_DATA=true` in `backend/.env` before first startup.

## Local setup

### 1. Install Python dependencies

If you do not already have a virtual environment:

```bash
python3 -m venv venv
```

Install backend packages:

```bash
venv/bin/pip install -r backend/requirements.txt
```

### 2. Start PostgreSQL

```bash
docker compose up -d db
```

This creates a local database at:

- host: `127.0.0.1`
- port: `5432`
- database: `restaurant_app`
- username: `postgres`
- password: `postgres`

### 3. Optional environment config

The defaults already work with the included Docker setup. If you want a custom configuration:

```bash
cp backend/.env.example backend/.env
```

For a clean empty startup, keep `SEED_DEMO_DATA=false`.

### 4. Run the app

```bash
cd backend
../venv/bin/uvicorn app.main:app --reload
```

Open:

- app UI: `http://127.0.0.1:8000`
- health check: `http://127.0.0.1:8000/health`
- API docs: `http://127.0.0.1:8000/docs`

The frontend is static and served directly by FastAPI, so there is no separate Node or frontend build step.

## Role workflows

### Waiter

- view all tables
- open an empty table
- add free-text items with quantity and optional note
- edit active items
- cancel items without removing history
- send the table bill to reception
- mark the table empty when guests physically leave

### Kitchen

- view all active tables live
- see active and cancelled items
- update item status as `new` or `ready`

### Receptionist

- work from the pending bills queue
- inspect the activity log
- manually enter billed quantity and unit price
- apply discount
- record payment and close the bill

### Sales

- sign in separately from reception
- view today, 7 day, and 30 day revenue
- review payment method mix
- review daily sales calendar and trend graph
- inspect top billed items and billed quantity

## Important implementation notes

- There is no fixed menu anywhere in the data model.
- Cancelled items remain visible for kitchen and billing review.
- Pricing is only decided by the receptionist during billing.
- Password hashing uses `pbkdf2_sha256` through `passlib`.
- The database schema is created automatically on startup for this MVP.
- Demo/sample business data is disabled by default and only loads when `SEED_DEMO_DATA=true` on a fresh database.
- PostgreSQL enum values are synced on startup for the current MVP status model.

## Useful API routes

- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/tables`
- `GET /api/tables/{table_id}`
- `POST /api/tables/{table_id}/open`
- `POST /api/tables/{table_id}/mark-empty`
- `GET /api/orders/{order_id}`
- `POST /api/orders/{order_id}/items`
- `PATCH /api/orders/{order_id}/items/{item_id}`
- `POST /api/orders/{order_id}/items/{item_id}/cancel`
- `PATCH /api/orders/{order_id}/status`
- `PATCH /api/kitchen/orders/{order_id}/items/{item_id}/status`
- `GET /api/reception/orders/pending`
- `PUT /api/reception/orders/{order_id}/billing`
- `POST /api/reception/orders/{order_id}/checkout`
- `GET /api/sales/reports/sales?days=30`
- `GET /ws?token=...`

## Verified locally

The following were verified in the local environment during implementation:

- Python dependencies install successfully
- PostgreSQL container starts from `docker compose`
- FastAPI app boots successfully against PostgreSQL
- `GET /health` returns `{"status":"ok"}`
- seeded login works for staff users
- authenticated `GET /api/tables` returns restaurant tables
- websocket connection handshake succeeds
