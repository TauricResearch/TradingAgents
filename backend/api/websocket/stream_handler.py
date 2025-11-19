import json
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
from ..models.schemas import StreamUpdate
from ..services.analysis_service import AnalysisService


class ConnectionManager:
    """Manages WebSocket connections for streaming analysis updates."""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, analysis_id: str):
        """Accept a WebSocket connection for a specific analysis."""
        await websocket.accept()
        if analysis_id not in self.active_connections:
            self.active_connections[analysis_id] = set()
        self.active_connections[analysis_id].add(websocket)
    
    def disconnect(self, websocket: WebSocket, analysis_id: str):
        """Remove a WebSocket connection."""
        if analysis_id in self.active_connections:
            self.active_connections[analysis_id].discard(websocket)
            if not self.active_connections[analysis_id]:
                del self.active_connections[analysis_id]
    
    async def send_update(self, analysis_id: str, update: StreamUpdate):
        """Send an update to all connected clients for an analysis."""
        if analysis_id in self.active_connections:
            message = update.model_dump_json()
            disconnected = set()
            for connection in self.active_connections[analysis_id]:
                try:
                    await connection.send_text(message)
                except Exception:
                    disconnected.add(connection)
            
            # Remove disconnected clients
            for conn in disconnected:
                self.disconnect(conn, analysis_id)


class StreamHandler:
    """Handles WebSocket streaming for analysis updates."""
    
    def __init__(self, analysis_service: AnalysisService):
        self.analysis_service = analysis_service
        self.connection_manager = ConnectionManager()
    
    async def handle_stream(
        self,
        websocket: WebSocket,
        analysis_id: str
    ):
        """Handle WebSocket connection for streaming updates."""
        await self.connection_manager.connect(websocket, analysis_id)
        
        try:
            # Send initial connection confirmation
            await websocket.send_json({
                "type": "status",
                "data": {"message": "Connected", "analysis_id": analysis_id},
                "timestamp": ""
            })
            
            # Keep connection alive and forward updates
            while True:
                # Wait for any incoming messages (ping/pong or close)
                try:
                    data = await websocket.receive_text()
                    # Handle ping/pong if needed
                    if data == "ping":
                        await websocket.send_text("pong")
                except WebSocketDisconnect:
                    break
                except Exception:
                    # Connection closed or error
                    break
        
        except WebSocketDisconnect:
            pass
        finally:
            self.connection_manager.disconnect(websocket, analysis_id)
    
    async def send_update(self, analysis_id: str, update: StreamUpdate):
        """Send an update to all connected clients."""
        await self.connection_manager.send_update(analysis_id, update)

