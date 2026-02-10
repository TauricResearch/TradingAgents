"""
CLI wrapper for TradingAgents: programmatic interface used by the Streamlit UI.

This module does NOT duplicate business logic. It calls the same programmatic
runner exposed by the CLI (cli.main.run_analysis_programmatic), which in turn
uses the same graph, config, and save_report_to_disk as the interactive CLI.

How CLI and UI share logic:
- Interactive CLI: cli.main.run_analysis() → get_user_selections() → run_analysis_programmatic
  is NOT used by CLI; CLI uses its own loop with Rich. The shared core is
  run_analysis_programmatic(), which uses TradingAgentsGraph and save_report_to_disk.
- UI: streamlit_app.py builds a selections dict from form inputs and calls
  run_trading_agent() here, which calls run_analysis_programmatic(selections, log_callback).

To add new agents in the future:
- Add the analyst type in tradingagents (and wire into the graph).
- Add the option in cli/models.AnalystType and cli.utils (for CLI prompts).
- Add the option in ui/streamlit_app.py sidebar (analyst checkboxes) and ensure
  the selections["analysts"] list passed to run_trading_agent includes the new key.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, List, Optional, Tuple

# Ensure project root is on path when running as streamlit run ui/streamlit_app.py
import sys
_ui_dir = Path(__file__).resolve().parent
_project_root = _ui_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def run_trading_agent(
    selections: dict,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, Optional[Path], Optional[str], Optional[dict]]:
    """
    Run the TradingAgents pipeline with the given selections (same as CLI options).

    Args:
        selections: Dict with ticker, analysis_date, analysts, research_depth,
            llm_provider, backend_url, shallow_thinker, deep_thinker,
            google_thinking_level (optional), openai_reasoning_effort (optional).
        log_callback: Optional callable(line) for live log streaming.

    Returns:
        (success, report_file_path, error_message, final_state).
        - success: True if the run completed and report was saved.
        - report_file_path: Path to complete_report.md (identical to CLI output).
        - error_message: Non-empty only when success is False.
        - final_state: Last chunk state for preview; None on failure.
    """
    from cli.main import run_analysis_programmatic

    final_state, report_path, err = run_analysis_programmatic(selections, log_callback=log_callback)
    if err:
        return False, None, err, None
    return True, report_path, None, final_state


def build_report_preview_markdown(final_state: dict, ticker: str) -> str:
    """
    Build a single Markdown string for the full report from final_state.

    Matches the structure of complete_report.md produced by save_report_to_disk
    so the UI preview is consistent with the downloaded file.
    """
    if not final_state:
        return ""
    parts = [f"# Trading Analysis Report: {ticker}\n"]
    # Analyst sections
    for key, title in [
        ("market_report", "Market Analysis"),
        ("sentiment_report", "Social Sentiment"),
        ("news_report", "News Analysis"),
        ("fundamentals_report", "Fundamentals Analysis"),
    ]:
        if final_state.get(key):
            parts.append(f"## {title}\n\n{final_state[key]}")
    if final_state.get("investment_debate_state"):
        debate = final_state["investment_debate_state"]
        parts.append("## Research Team Decision\n")
        if debate.get("bull_history"):
            parts.append(f"### Bull Researcher\n{debate['bull_history']}")
        if debate.get("bear_history"):
            parts.append(f"### Bear Researcher\n{debate['bear_history']}")
        if debate.get("judge_decision"):
            parts.append(f"### Research Manager\n{debate['judge_decision']}")
    if final_state.get("trader_investment_plan"):
        parts.append("## Trading Team Plan\n\n" + final_state["trader_investment_plan"])
    if final_state.get("risk_debate_state"):
        risk = final_state["risk_debate_state"]
        parts.append("## Risk Management Team Decision\n")
        for key, label in [
            ("aggressive_history", "Aggressive Analyst"),
            ("conservative_history", "Conservative Analyst"),
            ("neutral_history", "Neutral Analyst"),
        ]:
            if risk.get(key):
                parts.append(f"### {label}\n{risk[key]}")
        if risk.get("judge_decision"):
            parts.append("## Portfolio Manager Decision\n\n" + risk["judge_decision"])
    return "\n\n".join(parts)
