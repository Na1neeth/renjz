from pathlib import Path

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.api.router import api_router
from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.user import User
from app.websockets.manager import manager


settings = get_settings()
app = FastAPI(title=settings.app_name)
frontend_dir = Path(__file__).resolve().parents[2] / "frontend"

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def healthcheck():
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = Query(default=None)):
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    token_payload = decode_access_token(token)
    if not token_payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == token_payload["sub"], User.is_active.is_(True)))
    finally:
        db.close()

    if not user or user.active_session_key != token_payload["sid"]:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(
        websocket,
        {"id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role.value},
    )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
