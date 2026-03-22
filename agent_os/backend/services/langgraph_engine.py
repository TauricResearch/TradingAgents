import asyncio
import time
from typing import Dict, Any, AsyncGenerator
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.graph.scanner_graph import ScannerGraph
from tradingagents.default_config import DEFAULT_CONFIG

class LangGraphEngine:
    """Orchestrates LangGraph pipeline executions and streams events."""
    
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        # In-memory store to keep track of running tasks if needed
        self.active_runs = {}

    async def run_scan(self, run_id: str, params: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the 3-phase macro scanner and stream events."""
        date = params.get("date", time.strftime("%Y-%m-%d"))
        
        # Initialize ScannerGraph correctly
        scanner = ScannerGraph(config=self.config)
        
        print(f"Engine: Starting SCAN {run_id} for date {date}")
        
        # Initial state for scanner - must match ScannerGraph.scan's initial_state keys
        initial_state = {
            "scan_date": date,
            "messages": [],
            "geopolitical_report": "",
            "market_movers_report": "",
            "sector_performance_report": "",
            "industry_deep_dive_report": "",
            "macro_scan_summary": "",
            "sender": "",
        }

        async for event in scanner.graph.astream_events(initial_state, version="v2"):
            mapped_event = self._map_langgraph_event(event)
            if mapped_event:
                yield mapped_event

    async def run_pipeline(self, run_id: str, params: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """Run per-ticker analysis pipeline and stream events."""
        ticker = params.get("ticker", "AAPL")
        date = params.get("date", time.strftime("%Y-%m-%d"))
        analysts = params.get("analysts", ["market", "news", "fundamentals"])
        
        print(f"Engine: Starting PIPELINE {run_id} for {ticker} on {date}")
        
        # Initialize TradingAgentsGraph
        graph_wrapper = TradingAgentsGraph(
            selected_analysts=analysts,
            config=self.config,
            debug=True
        )
        
        initial_state = graph_wrapper.propagator.create_initial_state(ticker, date)
        # We don't use propagator.get_graph_args() here because we want to stream events directly
        
        async for event in graph_wrapper.graph.astream_events(initial_state, version="v2"):
            mapped_event = self._map_langgraph_event(event)
            if mapped_event:
                yield mapped_event

    def _map_langgraph_event(self, event: Dict[str, Any]) -> Dict[str, Any] | None:
        """Map LangGraph v2 events to AgentOS frontend contract."""
        kind = event["event"]
        name = event["name"]
        tags = event.get("tags", [])
        
        # Try to extract node name from tags or metadata
        node_name = name
        for tag in tags:
            if tag.startswith("graph:node:"):
                node_name = tag.split(":", 2)[-1]
        
        # Filter for relevant events
        if kind == "on_chat_model_start":
            return {
                "id": event["run_id"],
                "node_id": node_name,
                "parent_node_id": "start", # Simplified for now
                "type": "thought",
                "agent": node_name.upper(),
                "message": f"Thinking...",
                "metrics": {
                    "model": event["data"].get("invocation_params", {}).get("model_name", "unknown"),
                }
            }
        
        elif kind == "on_tool_start":
            return {
                "id": event["run_id"],
                "node_id": f"tool_{name}",
                "parent_node_id": node_name,
                "type": "tool",
                "agent": node_name.upper(),
                "message": f"> Tool Call: {name}",
                "metrics": {}
            }
            
        elif kind == "on_chat_model_end":
            output = event["data"].get("output")
            usage = {}
            model = "unknown"
            if hasattr(output, "usage_metadata") and output.usage_metadata:
                usage = output.usage_metadata
            if hasattr(output, "response_metadata") and output.response_metadata:
                model = output.response_metadata.get("model_name", "unknown")
            
            return {
                "id": f"{event['run_id']}_end",
                "node_id": node_name,
                "type": "result",
                "agent": node_name.upper(),
                "message": "Action determined.",
                "metrics": {
                    "model": model,
                    "tokens_in": usage.get("input_tokens", 0),
                    "tokens_out": usage.get("output_tokens", 0),
                    # "latency_ms": ... # calculated in frontend or here if we track start
                }
            }
            
        return None

    # Sync versions for BackgroundTasks (if we still want to use them)
    async def run_scan_background(self, run_id: str, params: Dict[str, Any]):
        async for _ in self.run_scan(run_id, params):
            pass

    async def run_pipeline_background(self, run_id: str, params: Dict[str, Any]):
        async for _ in self.run_pipeline(run_id, params):
            pass
