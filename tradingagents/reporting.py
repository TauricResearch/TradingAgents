from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Mapping


def save_report_bundle(
    final_state: Mapping[str, Any],
    ticker: str,
    save_path: Path,
    *,
    generated_at: dt.datetime | None = None,
) -> Path:
    """Persist a complete TradingAgents report bundle to disk."""

    generated_at = generated_at or dt.datetime.now()
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)

    sections: list[str] = []

    analysts_dir = save_path / "1_analysts"
    analyst_parts: list[tuple[str, str]] = []
    for file_name, title, key in (
        ("market.md", "Market Analyst", "market_report"),
        ("sentiment.md", "Social Analyst", "sentiment_report"),
        ("news.md", "News Analyst", "news_report"),
        ("fundamentals.md", "Fundamentals Analyst", "fundamentals_report"),
    ):
        content = _coerce_text(final_state.get(key))
        if not content:
            continue
        analysts_dir.mkdir(exist_ok=True)
        _write_text(analysts_dir / file_name, content)
        analyst_parts.append((title, content))

    if analyst_parts:
        sections.append(
            "## I. Analyst Team Reports\n\n"
            + "\n\n".join(f"### {title}\n{content}" for title, content in analyst_parts)
        )

    debate = final_state.get("investment_debate_state") or {}
    research_dir = save_path / "2_research"
    research_parts: list[tuple[str, str]] = []
    for file_name, title, key in (
        ("bull.md", "Bull Researcher", "bull_history"),
        ("bear.md", "Bear Researcher", "bear_history"),
        ("manager.md", "Research Manager", "judge_decision"),
    ):
        content = _coerce_text(debate.get(key))
        if not content:
            continue
        research_dir.mkdir(exist_ok=True)
        _write_text(research_dir / file_name, content)
        research_parts.append((title, content))

    if research_parts:
        sections.append(
            "## II. Research Team Decision\n\n"
            + "\n\n".join(f"### {title}\n{content}" for title, content in research_parts)
        )

    trader_plan = _coerce_text(final_state.get("trader_investment_plan"))
    if trader_plan:
        trading_dir = save_path / "3_trading"
        trading_dir.mkdir(exist_ok=True)
        _write_text(trading_dir / "trader.md", trader_plan)
        sections.append(f"## III. Trading Team Plan\n\n### Trader\n{trader_plan}")

    risk = final_state.get("risk_debate_state") or {}
    risk_dir = save_path / "4_risk"
    risk_parts: list[tuple[str, str]] = []
    for file_name, title, key in (
        ("aggressive.md", "Aggressive Analyst", "aggressive_history"),
        ("conservative.md", "Conservative Analyst", "conservative_history"),
        ("neutral.md", "Neutral Analyst", "neutral_history"),
    ):
        content = _coerce_text(risk.get(key))
        if not content:
            continue
        risk_dir.mkdir(exist_ok=True)
        _write_text(risk_dir / file_name, content)
        risk_parts.append((title, content))

    if risk_parts:
        sections.append(
            "## IV. Risk Management Team Decision\n\n"
            + "\n\n".join(f"### {title}\n{content}" for title, content in risk_parts)
        )

    portfolio_decision = _coerce_text(risk.get("judge_decision"))
    if portfolio_decision:
        portfolio_dir = save_path / "5_portfolio"
        portfolio_dir.mkdir(exist_ok=True)
        _write_text(portfolio_dir / "decision.md", portfolio_decision)
        sections.append(
            "## V. Portfolio Manager Decision\n\n"
            f"### Portfolio Manager\n{portfolio_decision}"
        )

    header = (
        f"# Trading Analysis Report: {ticker}\n\n"
        f"Generated: {generated_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    complete_report = save_path / "complete_report.md"
    _write_text(complete_report, header + "\n\n".join(sections))
    return complete_report


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
