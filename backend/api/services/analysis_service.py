import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Callable, AsyncGenerator
from pathlib import Path

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from ..models.schemas import AnalysisRequest, AnalysisStatus, StreamUpdate


class AnalysisService:
    """Service that wraps TradingAgentsGraph and handles analysis execution."""
    
    def __init__(self):
        self.active_analyses: Dict[str, Dict[str, Any]] = {}
        self.completed_analyses: Dict[str, Dict[str, Any]] = {}
        # Track agent statuses for each analysis
        self.agent_statuses: Dict[str, Dict[str, str]] = {}
    
    def extract_content_string(self, content):
        """Extract string content from various message formats."""
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # Handle Anthropic's list format
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get('type') == 'text':
                        text_parts.append(item.get('text', ''))
                    elif item.get('type') == 'tool_use':
                        text_parts.append(f"[Tool: {item.get('name', 'unknown')}]")
                else:
                    text_parts.append(str(item))
            return ' '.join(text_parts)
        else:
            return str(content)
    
    def start_analysis(
        self,
        request: AnalysisRequest,
        update_callback: Optional[Callable[[StreamUpdate], None]] = None
    ) -> str:
        """Start a new analysis and return analysis_id."""
        analysis_id = str(uuid.uuid4())
        
        # Create config from request
        config = DEFAULT_CONFIG.copy()
        config["max_debate_rounds"] = request.research_depth
        config["max_risk_discuss_rounds"] = request.research_depth
        config["quick_think_llm"] = request.quick_think_llm
        config["deep_think_llm"] = request.deep_think_llm
        config["backend_url"] = request.backend_url
        config["llm_provider"] = request.llm_provider.value
        
        if request.data_vendors:
            config["data_vendors"].update(request.data_vendors)
        
        # Initialize agent statuses
        self.agent_statuses[analysis_id] = {
            "Market Analyst": "pending",
            "Social Analyst": "pending",
            "News Analyst": "pending",
            "Fundamentals Analyst": "pending",
            "Bull Researcher": "pending",
            "Bear Researcher": "pending",
            "Research Manager": "pending",
            "Trader": "pending",
            "Risky Analyst": "pending",
            "Neutral Analyst": "pending",
            "Safe Analyst": "pending",
            "Portfolio Manager": "pending",
        }
        
        # Initialize analysis status
        self.active_analyses[analysis_id] = {
            "status": "running",
            "ticker": request.ticker,
            "analysis_date": request.analysis_date,
            "started_at": datetime.now().isoformat(),
            "config": config,
            "request": request,
            "final_state": None,
            "processed_signal": None,
            "update_callback": update_callback,
        }
        
        # Set first analyst to in_progress (will be sent when analysis starts)
        first_analyst = request.analysts[0].value.capitalize() + " Analyst"
        if first_analyst in self.agent_statuses[analysis_id]:
            self.agent_statuses[analysis_id][first_analyst] = "in_progress"
        
        # Run analysis in background task
        asyncio.create_task(
            self._run_analysis(analysis_id, request, config, update_callback)
        )
        
        return analysis_id
    
    async def _run_analysis(
        self,
        analysis_id: str,
        request: AnalysisRequest,
        config: Dict[str, Any],
        update_callback: Optional[Callable] = None
    ):
        """Run the analysis and stream updates."""
        try:
            # Get update callback from stored analysis if not provided
            if update_callback is None and analysis_id in self.active_analyses:
                stored_callback = self.active_analyses[analysis_id].get("update_callback")
                if stored_callback:
                    update_callback = stored_callback
            # Initialize the graph
            graph = TradingAgentsGraph(
                selected_analysts=[analyst.value for analyst in request.analysts],
                config=config,
                debug=True
            )
            
            # Create result directory
            results_dir = Path(config["results_dir"]) / request.ticker / request.analysis_date
            results_dir.mkdir(parents=True, exist_ok=True)
            report_dir = results_dir / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            
            # Initialize state
            init_agent_state = graph.propagator.create_initial_state(
                request.ticker, request.analysis_date
            )
            args = graph.propagator.get_graph_args()
            
            # Send initial agent status for first analyst
            if update_callback and analysis_id in self.agent_statuses:
                first_analyst = request.analysts[0].value.capitalize() + " Analyst"
                if first_analyst in self.agent_statuses[analysis_id]:
                    await update_callback(StreamUpdate(
                        type="agent_status",
                        data={"agent": first_analyst, "status": "in_progress"},
                        timestamp=datetime.now().isoformat()
                    ))
            
            # Stream the analysis
            trace = []
            async for chunk in graph.graph.astream(init_agent_state, **args):
                if update_callback:
                    await self._process_chunk(chunk, update_callback, analysis_id, request.analysts)
                trace.append(chunk)
            
            # Get final state
            final_state = trace[-1] if trace else None
            processed_signal = None
            
            if final_state:
                processed_signal = graph.process_signal(final_state.get("final_trade_decision", ""))
                
                # Save reports
                self._save_reports(final_state, report_dir)
                
                # Update analysis status
                self.active_analyses[analysis_id]["final_state"] = final_state
                self.active_analyses[analysis_id]["processed_signal"] = processed_signal
                self.active_analyses[analysis_id]["status"] = "completed"
                self.active_analyses[analysis_id]["completed_at"] = datetime.now().isoformat()
                
                # Move to completed
                self.completed_analyses[analysis_id] = self.active_analyses.pop(analysis_id)
                
                # Send final update
                if update_callback:
                    try:
                        await update_callback(StreamUpdate(
                            type="final_decision",
                            data={
                                "final_trade_decision": final_state.get("final_trade_decision", ""),
                                "processed_signal": processed_signal,
                            },
                            timestamp=datetime.now().isoformat()
                        ))
                    except Exception as e:
                        print(f"Error sending final update: {e}")
        
        except Exception as e:
            error_msg = str(e)
            self.active_analyses[analysis_id]["status"] = "error"
            self.active_analyses[analysis_id]["error"] = error_msg
            self.active_analyses[analysis_id]["completed_at"] = datetime.now().isoformat()
            
            if update_callback:
                try:
                    await update_callback(StreamUpdate(
                        type="status",
                        data={"error": error_msg},
                        timestamp=datetime.now().isoformat()
                    ))
                except Exception as e:
                    print(f"Error sending error update: {e}")
    
    async def _process_chunk(
        self,
        chunk: Dict[str, Any],
        update_callback: Optional[Callable] = None,
        analysis_id: Optional[str] = None,
        selected_analysts: Optional[list] = None
    ):
        """Process a chunk from the graph stream and send updates."""
        if not update_callback:
            return
        
        timestamp = datetime.now().isoformat()
        
        # Process messages
        if "messages" in chunk and len(chunk["messages"]) > 0:
            last_message = chunk["messages"][-1]
            
            if hasattr(last_message, "content"):
                content = self.extract_content_string(last_message.content)
                msg_type = "Reasoning"
            else:
                content = str(last_message)
                msg_type = "System"
            
            await update_callback(StreamUpdate(
                type="message",
                data={
                    "type": msg_type,
                    "content": content,
                },
                timestamp=timestamp
            ))
            
            # Process tool calls
            if hasattr(last_message, "tool_calls"):
                for tool_call in last_message.tool_calls:
                    if isinstance(tool_call, dict):
                        tool_name = tool_call.get("name", "unknown")
                        tool_args = tool_call.get("args", {})
                    else:
                        tool_name = tool_call.name
                        tool_args = tool_call.args
                    
                    await update_callback(StreamUpdate(
                        type="tool_call",
                        data={
                            "tool_name": tool_name,
                            "args": tool_args,
                        },
                        timestamp=timestamp
                    ))
        
        # Process reports and update agent statuses
        report_sections = [
            ("market_report", "Market Analyst"),
            ("sentiment_report", "Social Analyst"),
            ("news_report", "News Analyst"),
            ("fundamentals_report", "Fundamentals Analyst"),
        ]
        
        for section, agent_name in report_sections:
            if section in chunk and chunk[section]:
                # Mark current analyst as completed
                if analysis_id and agent_name in self.agent_statuses.get(analysis_id, {}):
                    self.agent_statuses[analysis_id][agent_name] = "completed"
                    await update_callback(StreamUpdate(
                        type="agent_status",
                        data={"agent": agent_name, "status": "completed"},
                        timestamp=timestamp
                    ))
                
                # Set next analyst to in_progress
                if analysis_id and selected_analysts:
                    analyst_map = {
                        "market": "Market Analyst",
                        "social": "Social Analyst",
                        "news": "News Analyst",
                        "fundamentals": "Fundamentals Analyst",
                    }
                    
                    # Find next analyst
                    current_idx = None
                    for i, analyst_type in enumerate(selected_analysts):
                        if analyst_map.get(analyst_type.value) == agent_name:
                            current_idx = i
                            break
                    
                    if current_idx is not None and current_idx + 1 < len(selected_analysts):
                        next_analyst_type = selected_analysts[current_idx + 1]
                        next_agent = analyst_map.get(next_analyst_type.value)
                        if next_agent and next_agent in self.agent_statuses.get(analysis_id, {}):
                            self.agent_statuses[analysis_id][next_agent] = "in_progress"
                            await update_callback(StreamUpdate(
                                type="agent_status",
                                data={"agent": next_agent, "status": "in_progress"},
                                timestamp=timestamp
                            ))
                    elif current_idx is not None and current_idx + 1 == len(selected_analysts):
                        # All analysts done, start research team
                        research_team = ["Bull Researcher", "Bear Researcher", "Research Manager"]
                        for research_agent in research_team:
                            if research_agent in self.agent_statuses.get(analysis_id, {}):
                                self.agent_statuses[analysis_id][research_agent] = "in_progress"
                                await update_callback(StreamUpdate(
                                    type="agent_status",
                                    data={"agent": research_agent, "status": "in_progress"},
                                    timestamp=timestamp
                                ))
                
                await update_callback(StreamUpdate(
                    type="report",
                    data={
                        "section_name": section,
                        "content": chunk[section],
                    },
                    timestamp=timestamp
                ))
        
        # Process trader investment plan
        if "trader_investment_plan" in chunk and chunk["trader_investment_plan"]:
            # Mark trader as completed and start risk team
            if analysis_id:
                if "Trader" in self.agent_statuses.get(analysis_id, {}):
                    self.agent_statuses[analysis_id]["Trader"] = "completed"
                    await update_callback(StreamUpdate(
                        type="agent_status",
                        data={"agent": "Trader", "status": "completed"},
                        timestamp=timestamp
                    ))
                
                # Start risk team
                risk_team = ["Risky Analyst", "Safe Analyst", "Neutral Analyst"]
                for agent in risk_team:
                    if agent in self.agent_statuses.get(analysis_id, {}):
                        self.agent_statuses[analysis_id][agent] = "in_progress"
                        await update_callback(StreamUpdate(
                            type="agent_status",
                            data={"agent": agent, "status": "in_progress"},
                            timestamp=timestamp
                        ))
            
            await update_callback(StreamUpdate(
                type="report",
                data={
                    "section_name": "trader_investment_plan",
                    "content": chunk["trader_investment_plan"],
                },
                timestamp=timestamp
            ))
        
        # Process investment debate state
        if "investment_debate_state" in chunk and chunk["investment_debate_state"]:
            debate_state = chunk["investment_debate_state"]
            
            # Update research team statuses based on debate state
            if analysis_id:
                if getattr(debate_state, "bull_history", None) or (isinstance(debate_state, dict) and debate_state.get("bull_history")):
                    if "Bull Researcher" in self.agent_statuses.get(analysis_id, {}):
                        self.agent_statuses[analysis_id]["Bull Researcher"] = "in_progress"
                        await update_callback(StreamUpdate(
                            type="agent_status",
                            data={"agent": "Bull Researcher", "status": "in_progress"},
                            timestamp=timestamp
                        ))
                
                if getattr(debate_state, "bear_history", None) or (isinstance(debate_state, dict) and debate_state.get("bear_history")):
                    if "Bear Researcher" in self.agent_statuses.get(analysis_id, {}):
                        self.agent_statuses[analysis_id]["Bear Researcher"] = "in_progress"
                        await update_callback(StreamUpdate(
                            type="agent_status",
                            data={"agent": "Bear Researcher", "status": "in_progress"},
                            timestamp=timestamp
                        ))
                
                if getattr(debate_state, "judge_decision", None) or (isinstance(debate_state, dict) and debate_state.get("judge_decision")):
                    research_team = ["Bull Researcher", "Bear Researcher", "Research Manager"]
                    for agent in research_team:
                        if agent in self.agent_statuses.get(analysis_id, {}):
                            self.agent_statuses[analysis_id][agent] = "completed"
                            await update_callback(StreamUpdate(
                                type="agent_status",
                                data={"agent": agent, "status": "completed"},
                                timestamp=timestamp
                            ))
            
            await update_callback(StreamUpdate(
                type="debate_update",
                data={
                    "bull_history": getattr(debate_state, "bull_history", None) or debate_state.get("bull_history") if isinstance(debate_state, dict) else None,
                    "bear_history": getattr(debate_state, "bear_history", None) or debate_state.get("bear_history") if isinstance(debate_state, dict) else None,
                    "judge_decision": getattr(debate_state, "judge_decision", None) or debate_state.get("judge_decision") if isinstance(debate_state, dict) else None,
                },
                timestamp=timestamp
            ))
        
        # Process risk debate state
        if "risk_debate_state" in chunk and chunk["risk_debate_state"]:
            risk_state = chunk["risk_debate_state"]
            
            # Update risk team statuses
            if analysis_id:
                if getattr(risk_state, "current_risky_response", None) or (isinstance(risk_state, dict) and risk_state.get("current_risky_response")):
                    if "Risky Analyst" in self.agent_statuses.get(analysis_id, {}):
                        self.agent_statuses[analysis_id]["Risky Analyst"] = "in_progress"
                        await update_callback(StreamUpdate(
                            type="agent_status",
                            data={"agent": "Risky Analyst", "status": "in_progress"},
                            timestamp=timestamp
                        ))
                
                if getattr(risk_state, "current_safe_response", None) or (isinstance(risk_state, dict) and risk_state.get("current_safe_response")):
                    if "Safe Analyst" in self.agent_statuses.get(analysis_id, {}):
                        self.agent_statuses[analysis_id]["Safe Analyst"] = "in_progress"
                        await update_callback(StreamUpdate(
                            type="agent_status",
                            data={"agent": "Safe Analyst", "status": "in_progress"},
                            timestamp=timestamp
                        ))
                
                if getattr(risk_state, "current_neutral_response", None) or (isinstance(risk_state, dict) and risk_state.get("current_neutral_response")):
                    if "Neutral Analyst" in self.agent_statuses.get(analysis_id, {}):
                        self.agent_statuses[analysis_id]["Neutral Analyst"] = "in_progress"
                        await update_callback(StreamUpdate(
                            type="agent_status",
                            data={"agent": "Neutral Analyst", "status": "in_progress"},
                            timestamp=timestamp
                        ))
                
                if getattr(risk_state, "judge_decision", None) or (isinstance(risk_state, dict) and risk_state.get("judge_decision")):
                    risk_team = ["Risky Analyst", "Safe Analyst", "Neutral Analyst", "Portfolio Manager"]
                    for agent in risk_team:
                        if agent in self.agent_statuses.get(analysis_id, {}):
                            self.agent_statuses[analysis_id][agent] = "completed"
                            await update_callback(StreamUpdate(
                                type="agent_status",
                                data={"agent": agent, "status": "completed"},
                                timestamp=timestamp
                            ))
            
            await update_callback(StreamUpdate(
                type="risk_debate_update",
                data={
                    "current_risky_response": getattr(risk_state, "current_risky_response", None) or risk_state.get("current_risky_response") if isinstance(risk_state, dict) else None,
                    "current_safe_response": getattr(risk_state, "current_safe_response", None) or risk_state.get("current_safe_response") if isinstance(risk_state, dict) else None,
                    "current_neutral_response": getattr(risk_state, "current_neutral_response", None) or risk_state.get("current_neutral_response") if isinstance(risk_state, dict) else None,
                    "judge_decision": getattr(risk_state, "judge_decision", None) or risk_state.get("judge_decision") if isinstance(risk_state, dict) else None,
                },
                timestamp=timestamp
            ))
    
    def _save_reports(self, final_state: Dict[str, Any], report_dir: Path):
        """Save reports to files."""
        report_sections = [
            "market_report", "sentiment_report", "news_report",
            "fundamentals_report", "trader_investment_plan", "final_trade_decision"
        ]
        
        for section in report_sections:
            if section in final_state and final_state[section]:
                file_path = report_dir / f"{section}.md"
                with open(file_path, "w") as f:
                    f.write(final_state[section])
    
    def get_analysis_status(self, analysis_id: str) -> Optional[AnalysisStatus]:
        """Get the status of an analysis."""
        analysis = self.active_analyses.get(analysis_id) or self.completed_analyses.get(analysis_id)
        if not analysis:
            return None
        
        return AnalysisStatus(
            analysis_id=analysis_id,
            status=analysis["status"],
            ticker=analysis["ticker"],
            analysis_date=analysis["analysis_date"],
            started_at=analysis.get("started_at"),
            completed_at=analysis.get("completed_at"),
            error=analysis.get("error"),
        )
    
    def get_analysis_results(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        """Get the results of a completed analysis."""
        analysis = self.completed_analyses.get(analysis_id)
        if not analysis or analysis["status"] != "completed":
            return None
        
        return {
            "analysis_id": analysis_id,
            "ticker": analysis["ticker"],
            "analysis_date": analysis["analysis_date"],
            "final_state": analysis.get("final_state", {}),
            "processed_signal": analysis.get("processed_signal"),
            "completed_at": analysis.get("completed_at"),
        }

