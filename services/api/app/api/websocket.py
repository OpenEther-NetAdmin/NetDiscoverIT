"""
WebSocket manager for real-time updates
"""

from fastapi import WebSocket
from typing import Dict, List
import json
import redis
from app.core.config import settings


class ConnectionManager:
    """Manages WebSocket connections"""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, discovery_id: str):
        """Connect a WebSocket to a discovery room"""
        await websocket.accept()
        if discovery_id not in self.active_connections:
            self.active_connections[discovery_id] = []
        self.active_connections[discovery_id].append(websocket)

    def disconnect(self, websocket: WebSocket, discovery_id: str):
        """Disconnect a WebSocket from a discovery room"""
        if discovery_id in self.active_connections:
            if websocket in self.active_connections[discovery_id]:
                self.active_connections[discovery_id].remove(websocket)
            if not self.active_connections[discovery_id]:
                del self.active_connections[discovery_id]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific WebSocket"""
        await websocket.send_json(message)

    async def broadcast_to_discovery(self, discovery_id: str, message: dict):
        """Broadcast a message to all WebSockets subscribed to a discovery"""
        if discovery_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[discovery_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.append(connection)
            for conn in disconnected:
                self.disconnect(conn, discovery_id)


manager = ConnectionManager()


async def publish_discovery_update(discovery_id: str, update: dict):
    """Publish a discovery update to Redis pub/sub"""
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        channel = f"discovery:{discovery_id}:updates"
        redis_client.publish(channel, json.dumps(update))
        redis_client.close()
    except Exception as e:
        import logging

        logging.warning(f"Failed to publish discovery update: {e}")
