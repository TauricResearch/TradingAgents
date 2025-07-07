from typing import Dict, Set
from fastapi import WebSocket
import json
from datetime import datetime


class WebSocketManager:
    def __init__(self):
        # Store active connections by member_id
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Store analysis_id to member_id mapping
        self.analysis_member_map: Dict[str, str] = {}

    async def connect(self, websocket: WebSocket, member_id: str):
        await websocket.accept()
        if member_id not in self.active_connections:
            self.active_connections[member_id] = set()
        self.active_connections[member_id].add(websocket)

    def disconnect(self, websocket: WebSocket, member_id: str):
        if member_id in self.active_connections:
            self.active_connections[member_id].discard(websocket)
            if not self.active_connections[member_id]:
                del self.active_connections[member_id]

    def register_analysis(self, analysis_id: str, member_id: str):
        """Register which member owns which analysis"""
        self.analysis_member_map[analysis_id] = member_id

    async def send_analysis_update(self, analysis_id: str, update_type: str, data: dict):
        """Send analysis update to the member who owns the analysis"""
        member_id = self.analysis_member_map.get(analysis_id)
        if not member_id:
            return
        
        message = {
            "type": "analysis_update",
            "analysis_id": analysis_id,
            "update_type": update_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        
        await self.send_to_member(member_id, message)



    async def send_to_member(self, member_id: str, message: dict|str):
        """Send message to all connections of a specific member"""
        if member_id not in self.active_connections:
            return
        
        dead_connections = set()
        for connection in self.active_connections[member_id]:
            try:
                if isinstance(message, dict):
                    await connection.send_json(message)
                else:
                    await connection.send_text(message)
            except Exception:
                dead_connections.add(connection)
        
        # Clean up dead connections
        for connection in dead_connections:
            self.disconnect(connection, member_id)