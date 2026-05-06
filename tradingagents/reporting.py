"""Shared report writer.

Produces the canonical structured-folder layout under `<save_path>`:

    1_analysts/{market,sentiment,news,fundamentals}.md
    2_research/{bull,bear,manager}.md
    3_trading/trader.md
    4_risk/{aggressive,conservative,neutral}.md
    5_portfolio/decision.md
    complete_report.md

Both `cli/main.py` and `TradingAgentsGraph._run_graph` call this so every
analysis — whether interactive or programmatic — emits the same layout.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Mapping


def save_report_to_disk(final_state: Mapping[str, Any], ticker: str, save_path: Path) -> Path:
    """Save complete analysis report to disk with organized subfolders."""
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)
    sections: list[str] = []

    # 1. Analysts
    analysts_dir = save_path / "1_analysts"
    analyst_parts: list[tuple[str, str]] = []
    if final_state.get("market_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "market.md").write_text(final_state["market_report"], encoding="utf-8")
        analyst_parts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "sentiment.md").write_text(final_state["sentiment_report"], encoding="utf-8")
        analyst_parts.append(("Social Analyst", final_state["sentiment_report"]))
    if final_state.get("news_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "news.md").write_text(final_state["news_report"], encoding="utf-8")
        analyst_parts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("fundamentals_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "fundamentals.md").write_text(final_state["fundamentals_report"], encoding="utf-8")
        analyst_parts.append(("Fundamentals Analyst", final_state["fundamentals_report"]))
    if analyst_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. Analyst Team Reports\n\n{content}")

    # 2. Research
    if final_state.get("investment_debate_state"):
        research_dir = save_path / "2_research"
        debate = final_state["investment_debate_state"]
        research_parts: list[tuple[str, str]] = []
        if debate.get("bull_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bull.md").write_text(debate["bull_history"], encoding="utf-8")
            research_parts.append(("Bull Researcher", debate["bull_history"]))
        if debate.get("bear_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bear.md").write_text(debate["bear_history"], encoding="utf-8")
            research_parts.append(("Bear Researcher", debate["bear_history"]))
        if debate.get("judge_decision"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "manager.md").write_text(debate["judge_decision"], encoding="utf-8")
            research_parts.append(("Research Manager", debate["judge_decision"]))
        if research_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in research_parts)
            sections.append(f"## II. Research Team Decision\n\n{content}")

    # 3. Trading — accept either the live state key (`trader_investment_plan`)
    # or the JSON-dump alias (`trader_investment_decision`) so this works when
    # called from a re-loaded JSON, not just live state.
    trader_text = final_state.get("trader_investment_plan") or final_state.get("trader_investment_decision")
    if trader_text:
        trading_dir = save_path / "3_trading"
        trading_dir.mkdir(exist_ok=True)
        (trading_dir / "trader.md").write_text(trader_text, encoding="utf-8")
        sections.append(f"## III. Trading Team Plan\n\n### Trader\n{trader_text}")

    # 4. Risk Management
    if final_state.get("risk_debate_state"):
        risk_dir = save_path / "4_risk"
        risk = final_state["risk_debate_state"]
        risk_parts: list[tuple[str, str]] = []
        if risk.get("aggressive_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "aggressive.md").write_text(risk["aggressive_history"], encoding="utf-8")
            risk_parts.append(("Aggressive Analyst", risk["aggressive_history"]))
        if risk.get("conservative_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "conservative.md").write_text(risk["conservative_history"], encoding="utf-8")
            risk_parts.append(("Conservative Analyst", risk["conservative_history"]))
        if risk.get("neutral_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "neutral.md").write_text(risk["neutral_history"], encoding="utf-8")
            risk_parts.append(("Neutral Analyst", risk["neutral_history"]))
        if risk_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in risk_parts)
            sections.append(f"## IV. Risk Management Team Decision\n\n{content}")

        # 5. Portfolio Manager
        if risk.get("judge_decision"):
            portfolio_dir = save_path / "5_portfolio"
            portfolio_dir.mkdir(exist_ok=True)
            (portfolio_dir / "decision.md").write_text(risk["judge_decision"], encoding="utf-8")
            sections.append(f"## V. Portfolio Manager Decision\n\n### Portfolio Manager\n{risk['judge_decision']}")

    header = f"# Trading Analysis Report: {ticker}\n\nGenerated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    (save_path / "complete_report.md").write_text(header + "\n\n".join(sections), encoding="utf-8")
    return save_path / "complete_report.md"


def default_save_path(results_dir: str | Path, ticker: str, trade_date: str | None = None) -> Path:
    """Compute the canonical save path: `<results_dir>/<TICKER>_<DATE>_<TIMESTAMP>/`.

    Ticker is sanitized via `safe_ticker_component` to prevent path escape.
    """
    from tradingagents.dataflows.utils import safe_ticker_component

    safe_ticker = safe_ticker_component(ticker)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if trade_date:
        date_token = str(trade_date).replace("-", "")
        folder = f"{safe_ticker}_{date_token}_{timestamp}"
    else:
        folder = f"{safe_ticker}_{timestamp}"
    return Path(results_dir) / folder
