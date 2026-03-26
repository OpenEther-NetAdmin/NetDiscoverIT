"""WebSocket routes"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/discoveries/{discovery_id}")
async def websocket_discovery_status(websocket: WebSocket, discovery_id: str):
    """
    WebSocket endpoint for real-time discovery status updates.

    Frontend connects to: ws://localhost:8000/api/v1/ws/discoveries/{discovery_id}

    Messages received:
    - {"type": "progress", "progress": 50, "status": "running", "message": "Scanning..."}
    - {"type": "complete", "device_count": 42}
    - {"type": "error", "message": "Scan failed"}
    """
    from app.api.websocket import manager

    await manager.connect(websocket, discovery_id)
    try:
        while True:
            await websocket.receive_text()
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, discovery_id)
