import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from utils.logger import logger
router = APIRouter()
connected_websockets = set()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

# WebSocket route to handle WebSocket connections
@router.websocket("/logs")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await asyncio.sleep(0.01)
            text = await websocket.receive_text()
            await manager.broadcast(text)
    except WebSocketDisconnect:
        pass