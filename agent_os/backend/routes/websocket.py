from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
import asyncio
import time
import uuid
from typing import Dict, Any
from agent_os.backend.dependencies import get_current_user

router = APIRouter(prefix="/ws", tags=["websocket"])

@router.websocket("/stream/{run_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    run_id: str,
    # user: dict = Depends(get_current_user) # In V2, validate token from query string
):
    await websocket.accept()
    print(f"WebSocket client connected to run: {run_id}")
    
    try:
        # For now, we use a mock stream.
        # In a real implementation, this would subscribe to an event queue or a database stream
        # that's being populated by the BackgroundTask running the LangGraph.
        
        mock_events = [
            {
                "id": "node_1",
                "node_id": "analyst_node",
                "parent_node_id": "start",
                "type": "thought", 
                "agent": "ANALYST", 
                "message": "Evaluating market data...",
                "metrics": {
                    "model": "gpt-4-turbo",
                    "tokens_in": 120,
                    "tokens_out": 45,
                    "latency_ms": 450
                }
            },
            {
                "id": "node_2",
                "node_id": "tool_node",
                "parent_node_id": "analyst_node",
                "type": "tool", 
                "agent": "ANALYST", 
                "message": "> Tool Call: get_news_sentiment",
                "metrics": {
                    "latency_ms": 800
                }
            },
            {
                "id": "node_3",
                "node_id": "research_node",
                "parent_node_id": "analyst_node",
                "type": "thought", 
                "agent": "RESEARCHER", 
                "message": "Synthesizing industry trends...",
                "metrics": {
                    "model": "claude-3-opus",
                    "tokens_in": 800,
                    "tokens_out": 300,
                    "latency_ms": 2200
                }
            },
            {
                "id": "node_4",
                "node_id": "trader_node",
                "parent_node_id": "research_node",
                "type": "result", 
                "agent": "TRADER", 
                "message": "Action determined: BUY VLO", 
                "details": {
                    "model_used": "gpt-4-turbo",
                    "latency_ms": 1200,
                    "input_tokens": 450,
                    "output_tokens": 120,
                    "raw_json_response": '{"action": "buy", "ticker": "VLO"}'
                },
                "metrics": {
                    "model": "gpt-4-turbo",
                    "tokens_in": 450,
                    "tokens_out": 120,
                    "latency_ms": 1200
                }
            }
        ]
        
        for evt in mock_events:
            payload = {
                "id": evt["id"],
                "node_id": evt["node_id"],
                "parent_node_id": evt["parent_node_id"],
                "timestamp": time.strftime("%H:%M:%S"),
                "agent": evt["agent"],
                "tier": "mid" if evt["agent"] == "ANALYST" else "deep",
                "type": evt["type"],
                "message": evt["message"],
                "details": evt.get("details"),
                "metrics": evt.get("metrics")
            }
            await websocket.send_json(payload)
            await asyncio.sleep(2) # Simulating execution delay
            
        await websocket.send_json({"type": "system", "message": "Run completed."})
        
    except WebSocketDisconnect:
        print(f"WebSocket client disconnected from run {run_id}")
    except Exception as e:
        await websocket.send_json({"type": "system", "message": f"Error: {str(e)}"})
        await websocket.close()
