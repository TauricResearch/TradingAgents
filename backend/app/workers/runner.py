import json
import logging
import os
import re
import sys
import threading
import time
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tradingagents.agents.utils.rating import extract_rating  # noqa: E402
from tradingagents.dataflows.utils import safe_ticker_component  # noqa: E402
from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402
from tradingagents.reporting import write_report_tree  # noqa: E402

logger = logging.getLogger(__name__)

def extract_price_level(text: str, label_keywords: list[str]) -> float | None:
    """Robustly extract the first monetary price level associated with given label keywords."""
    if not text:
        return None
    for line in text.splitlines():
        if any(kw.lower() in line.lower() for kw in label_keywords):
            search_part = line.split(":", 1)[-1] if ":" in line else line
            m = re.search(r'\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)', search_part)
            if m:
                clean_num = m.group(1).replace(",", "")
                try:
                    return float(clean_num)
                except ValueError:
                    pass
    return None

def run_analysis_task(
    job_dict: dict[str, Any],
    event_callback: Callable[[str, dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None
) -> dict[str, Any]:
    """Worker function to execute a single analysis pipeline with isolated context.

    Can be run in a separate process/thread. Reports progress and events through event_callback.
    Supports graceful cancellation via cancel_event.
    """
    job_id = job_dict["id"]
    ticker = job_dict["ticker"]
    trade_date = job_dict["trade_date"]
    asset_type = job_dict.get("asset_type", "stock")
    analysts = job_dict.get("analysts", ["market", "social", "news", "fundamentals"])
    if isinstance(analysts, str):
        try:
            analysts = json.loads(analysts)
        except Exception:
            analysts = [a.strip() for a in analysts.split(",") if a.strip()]
    if not isinstance(analysts, list):
        analysts = ["market", "social", "news", "fundamentals"]

    start_time = time.time()

    def emit(event_type: str, data: dict[str, Any]):
        if event_callback:
            try:
                event_callback(event_type, data)
            except Exception as e:
                logger.warning(f"Error in event_callback for job {job_id}: {e}")

    try:
        emit("stage_change", {
            "stage": "Initializing",
            "progress": 5,
            "message": f"Initializing multi-agent graph for {ticker} on {trade_date}"
        })

        # Build isolated config for this specific run
        cfg = DEFAULT_CONFIG.copy()
        cfg["llm_provider"] = job_dict.get("llm_provider", cfg.get("llm_provider", "openai"))
        cfg["deep_think_llm"] = job_dict.get("deep_think_llm", cfg.get("deep_think_llm", "gpt-5.6"))
        cfg["quick_think_llm"] = job_dict.get("quick_think_llm", cfg.get("quick_think_llm", "gpt-5.6-luna"))
        cfg["backend_url"] = job_dict.get("backend_url") or cfg.get("backend_url") or os.getenv("TRADINGAGENTS_LLM_BACKEND_URL")
        cfg["max_debate_rounds"] = int(job_dict.get("max_debate_rounds", 1))
        cfg["max_risk_discuss_rounds"] = int(job_dict.get("max_risk_discuss_rounds", 1))
        cfg["output_language"] = job_dict.get("output_language", "English")
        cfg["checkpoint_enabled"] = False # Scoped per-job to avoid lock conflicts

        # Ensure results_dir is writable; fall back to local results dir if running outside container
        results_dir = cfg.get("results_dir")
        try:
            if results_dir:
                os.makedirs(results_dir, exist_ok=True)
            else:
                raise OSError("results_dir not specified")
        except (PermissionError, OSError):
            fallback_dir = PROJECT_ROOT / "results"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            cfg["results_dir"] = str(fallback_dir)

        # Initialize graph
        graph = TradingAgentsGraph(
            selected_analysts=analysts,
            debug=False,
            config=cfg
        )


        # Deterministically resolve instrument identity
        emit("stage_change", {
            "stage": "Identity Resolution",
            "progress": 10,
            "message": f"Resolving asset profile and instrument identity for {ticker}"
        })
        instrument_context = graph.resolve_instrument_context(ticker, asset_type)

        # Create initial state
        init_agent_state = graph.propagator.create_initial_state(
            ticker,
            trade_date,
            asset_type=asset_type,
            past_context=graph.memory_log.get_past_context(ticker, as_of=graph._memory_as_of(trade_date)),
            instrument_context=instrument_context,
        )
        args = graph.propagator.get_graph_args()

        emit("stage_change", {
            "stage": "Analyst Team Execution",
            "progress": 15,
            "message": "Dispatching Analyst Team (Market, Sentiment, News, Fundamentals)"
        })

        trace = []
        processed_speakers = set()
        analysts_completed = set()

        # Stream the graph step by step
        for chunk in graph.graph.stream(init_agent_state, **args):
            if cancel_event and cancel_event.is_set():
                logger.info(f"Job {job_id} cancelled by user. Halting pipeline execution.")
                emit("stage_change", {
                    "stage": "Cancelled",
                    "progress": 100,
                    "message": "Analysis cancelled by user"
                })
                return {
                    "status": "cancelled",
                    "job_id": job_id,
                    "duration_seconds": round(time.time() - start_time, 2),
                    "error_message": "Analysis cancelled by user"
                }
            trace.append(chunk)

            # 1. Analyst Reports
            if chunk.get("market_report") and "market" not in analysts_completed:
                analysts_completed.add("market")
                emit("agent_completed", {
                    "agent": "Market Analyst",
                    "progress": 25,
                    "preview": chunk["market_report"][:300] + "..." if len(chunk["market_report"]) > 300 else chunk["market_report"]
                })
            if chunk.get("sentiment_report") and "sentiment" not in analysts_completed:
                analysts_completed.add("sentiment")
                emit("agent_completed", {
                    "agent": "Sentiment Analyst",
                    "progress": 35,
                    "preview": chunk["sentiment_report"][:300] + "..." if len(chunk["sentiment_report"]) > 300 else chunk["sentiment_report"]
                })
            if chunk.get("news_report") and "news" not in analysts_completed:
                analysts_completed.add("news")
                emit("agent_completed", {
                    "agent": "News Analyst",
                    "progress": 45,
                    "preview": chunk["news_report"][:300] + "..." if len(chunk["news_report"]) > 300 else chunk["news_report"]
                })
            if chunk.get("fundamentals_report") and "fundamentals" not in analysts_completed:
                analysts_completed.add("fundamentals")
                emit("agent_completed", {
                    "agent": "Fundamentals Analyst",
                    "progress": 55,
                    "preview": chunk["fundamentals_report"][:300] + "..." if len(chunk["fundamentals_report"]) > 300 else chunk["fundamentals_report"]
                })

            # 2. Bull vs Bear Debate
            if chunk.get("investment_debate_state"):
                debate = chunk["investment_debate_state"]
                current_response = debate.get("current_response", "").strip()
                count = debate.get("count", 0)

                if current_response and current_response not in processed_speakers:
                    processed_speakers.add(current_response)
                    speaker = "Bull Researcher" if current_response.startswith("Bull Analyst") else "Bear Researcher"
                    emit("debate_speech", {
                        "speaker": speaker,
                        "round": count,
                        "content": current_response,
                        "progress": min(55 + count * 5, 70)
                    })

                if debate.get("judge_decision"):
                    emit("research_plan", {
                        "plan": debate["judge_decision"],
                        "progress": 72,
                        "message": "Research Manager synthesized investment thesis"
                    })

            # 3. Trader Proposal
            if chunk.get("trader_investment_plan"):
                emit("trader_proposal", {
                    "proposal": chunk["trader_investment_plan"],
                    "progress": 78,
                    "message": "Trader formulated transaction proposal with Entry/Stop-Loss"
                })

            # 4. Risk Debate
            if chunk.get("risk_debate_state"):
                risk = chunk["risk_debate_state"]
                speaker = risk.get("latest_speaker", "")
                count = risk.get("count", 0)

                speech = ""
                if speaker == "Aggressive":
                    speech = risk.get("current_aggressive_response", "")
                elif speaker == "Conservative":
                    speech = risk.get("current_conservative_response", "")
                elif speaker == "Neutral":
                    speech = risk.get("current_neutral_response", "")

                if speech and speech not in processed_speakers:
                    processed_speakers.add(speech)
                    emit("risk_speech", {
                        "speaker": f"{speaker} Analyst",
                        "round": count,
                        "content": speech,
                        "progress": min(80 + count * 3, 90)
                    })

            # 5. Final Decision
            if chunk.get("final_trade_decision"):
                decision = chunk["final_trade_decision"]
                rating = extract_rating(decision) or "Hold"
                emit("final_decision", {
                    "rating": rating,
                    "decision": decision,
                    "progress": 98,
                    "message": "Portfolio Manager rendered final investment decision"
                })

        # Merge streamed chunks to form final state
        final_state = {}
        for chunk in trace:
            final_state.update(chunk)

        final_decision_text = final_state.get("final_trade_decision", "")
        rating_signal = extract_rating(final_decision_text) or "Hold"

        # Save to memory log
        try:
            graph.memory_log.store_decision(
                ticker=ticker,
                trade_date=trade_date,
                final_trade_decision=final_decision_text
            )
        except Exception as e:
            logger.warning(f"Failed to append to memory log for {ticker}: {e}")

        # Write report tree
        duration = round(time.time() - start_time, 2)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_ticker = safe_ticker_component(ticker)
        reports_dir = Path(cfg["results_dir"]) / "reports" / f"{safe_ticker}_{stamp}"
        complete_report_path = write_report_tree(final_state, ticker, reports_dir)
        complete_report_md = complete_report_path.read_text(encoding="utf-8") if complete_report_path.exists() else ""

        # Extract fields for database
        exec_summary = ""
        entry_price = None
        stop_loss = None
        target_price = None

        # Parse price levels using robust regex
        for line in final_decision_text.splitlines():
            if "Executive Summary" in line or "**Summary**" in line:
                exec_summary = line.split(":", 1)[-1].strip()

        target_price = extract_price_level(final_decision_text, ["Price Target", "Target Price", "Target"])
        trader_plan = final_state.get("trader_investment_plan", "")
        entry_price = extract_price_level(trader_plan, ["Entry Price", "Entry Target", "Entry"])
        stop_loss = extract_price_level(trader_plan, ["Stop Loss", "Stop-Loss", "Stop"])

        result = {
            "status": "completed",
            "progress": 100,
            "decision_signal": rating_signal,
            "duration_seconds": duration,
            "final_state": final_state,
            "complete_report_md": complete_report_md,
            "executive_summary": exec_summary or final_decision_text[:400],
            "recommendation": rating_signal,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "target_price": target_price,
            "market_report_md": final_state.get("market_report", ""),
            "sentiment_report_md": final_state.get("sentiment_report", ""),
            "news_report_md": final_state.get("news_report", ""),
            "fundamentals_report_md": final_state.get("fundamentals_report", ""),
            "trader_investment_plan": trader_plan,
            "investment_debate": final_state.get("investment_debate_state", {}),
            "risk_debate": final_state.get("risk_debate_state", {})
        }

        emit("job_completed", {
            "job_id": job_id,
            "decision_signal": rating_signal,
            "duration_seconds": duration,
            "progress": 100
        })

        return result

    except Exception as exc:
        duration = round(time.time() - start_time, 2)
        err_msg = f"{type(exc).__name__}: {str(exc)}"
        tb = traceback.format_exc()
        logger.error(f"Job {job_id} failed with error: {tb}")

        emit("job_failed", {
            "job_id": job_id,
            "error_message": err_msg,
            "traceback": tb
        })

        return {
            "status": "failed",
            "progress": 0,
            "error_message": err_msg,
            "duration_seconds": duration
        }
