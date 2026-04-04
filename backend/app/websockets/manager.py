from collections.abc import Iterable

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[dict] = []

    async def connect(self, websocket: WebSocket, user: dict) -> None:
        await websocket.accept()
        self._connections.append({"websocket": websocket, "user": user})
        await websocket.send_json({"type": "connected", "payload": user})

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections = [
            connection
            for connection in self._connections
            if connection["websocket"] is not websocket
        ]

    async def broadcast(self, event_type: str, payload: dict, roles: Iterable[str] | None = None) -> None:
        allowed_roles = set(roles or [])
        message = jsonable_encoder({"type": event_type, "payload": payload})
        stale_connections = []

        for connection in self._connections:
            if allowed_roles and connection["user"]["role"] not in allowed_roles:
                continue
            websocket = connection["websocket"]
            try:
                await websocket.send_json(message)
            except Exception:
                stale_connections.append(websocket)

        for websocket in stale_connections:
            self.disconnect(websocket)


manager = ConnectionManager()

