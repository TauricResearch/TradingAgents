"""Reusable report writing.

Turns a finished run's ``final_state`` into an organized markdown report tree on
disk. Previously this logic lived inside ``cli/main.py`` and was reachable only
through the interactive CLI; programmatic callers (``TradingAgentsGraph``) got a
single JSON blob instead. This module is the single source of truth so both
paths produce identical artifacts.
"""

from __future__ import annotations

import datetime
from pathlib import Path


def write_reports(final_state: dict, ticker: str, out_dir: str | Path) -> Path:
    """Write the full analysis as an organized markdown tree under ``out_dir``.

    Layout::

        out_dir/
        ├── 1_analysts/      market.md, sentiment.md, news.md, fundamentals.md
        ├── 2_research/      bull.md, bear.md, manager.md
        ├── 3_trading/       trader.md
        ├── 4_risk/          aggressive.md, conservative.md, neutral.md
        ├── 5_portfolio/     decision.md
        └── complete_report.md   (consolidated)

    Each subfolder/section is written only when its content is present, so a run
    with fewer analysts produces a smaller tree rather than empty files.

    Returns:
        Path to the consolidated ``complete_report.md``.
    """
    save_path = Path(out_dir)
    save_path.mkdir(parents=True, exist_ok=True)
    sections: list[str] = []

    # 1. Analysts
    analysts_dir = save_path / "1_analysts"
    analyst_specs = [
        ("market_report", "market.md", "Market Analyst"),
        ("sentiment_report", "sentiment.md", "Sentiment Analyst"),
        ("news_report", "news.md", "News Analyst"),
        ("fundamentals_report", "fundamentals.md", "Fundamentals Analyst"),
    ]
    analyst_parts = []
    for key, filename, label in analyst_specs:
        text = final_state.get(key)
        if text:
            analysts_dir.mkdir(exist_ok=True)
            (analysts_dir / filename).write_text(text, encoding="utf-8")
            analyst_parts.append((label, text))
    if analyst_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. Analyst Team Reports\n\n{content}")

    # 2. Research
    debate = final_state.get("investment_debate_state") or {}
    if debate:
        research_dir = save_path / "2_research"
        research_specs = [
            ("bull_history", "bull.md", "Bull Researcher"),
            ("bear_history", "bear.md", "Bear Researcher"),
            ("judge_decision", "manager.md", "Research Manager"),
        ]
        research_parts = []
        for key, filename, label in research_specs:
            text = debate.get(key)
            if text:
                research_dir.mkdir(exist_ok=True)
                (research_dir / filename).write_text(text, encoding="utf-8")
                research_parts.append((label, text))
        if research_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in research_parts)
            sections.append(f"## II. Research Team Decision\n\n{content}")

    # 3. Trading
    trader_plan = final_state.get("trader_investment_plan")
    if trader_plan:
        trading_dir = save_path / "3_trading"
        trading_dir.mkdir(exist_ok=True)
        (trading_dir / "trader.md").write_text(trader_plan, encoding="utf-8")
        sections.append(f"## III. Trading Team Plan\n\n### Trader\n{trader_plan}")

    # 4. Risk Management + 5. Portfolio Manager
    risk = final_state.get("risk_debate_state") or {}
    if risk:
        risk_dir = save_path / "4_risk"
        risk_specs = [
            ("aggressive_history", "aggressive.md", "Aggressive Analyst"),
            ("conservative_history", "conservative.md", "Conservative Analyst"),
            ("neutral_history", "neutral.md", "Neutral Analyst"),
        ]
        risk_parts = []
        for key, filename, label in risk_specs:
            text = risk.get(key)
            if text:
                risk_dir.mkdir(exist_ok=True)
                (risk_dir / filename).write_text(text, encoding="utf-8")
                risk_parts.append((label, text))
        if risk_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in risk_parts)
            sections.append(f"## IV. Risk Management Team Decision\n\n{content}")

        if risk.get("judge_decision"):
            portfolio_dir = save_path / "5_portfolio"
            portfolio_dir.mkdir(exist_ok=True)
            (portfolio_dir / "decision.md").write_text(risk["judge_decision"], encoding="utf-8")
            sections.append(
                f"## V. Portfolio Manager Decision\n\n### Portfolio Manager\n{risk['judge_decision']}"
            )

    # Consolidated report
    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = f"# Trading Analysis Report: {ticker}\n\nGenerated: {generated}\n\n"
    report_path = save_path / "complete_report.md"
    report_path.write_text(header + "\n\n".join(sections), encoding="utf-8")
    return report_path
