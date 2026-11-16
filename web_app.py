"""Minimal non-interactive Gradio UI for TradingAgents."""

from __future__ import annotations

import os
from datetime import date

import gradio as gr

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


ANALYST_LABELS = {
    "Market": "market",
    "Social": "social",
    "News": "news",
    "Fundamentals": "fundamentals",
}

REPORTS = (
    ("Market report", "market_report"),
    ("Sentiment report", "sentiment_report"),
    ("News report", "news_report"),
    ("Fundamentals report", "fundamentals_report"),
    ("Research manager plan", "investment_plan"),
    ("Trader plan", "trader_investment_plan"),
)


def _web_config() -> dict:
    """Keep environment-selected models while applying conservative web defaults."""
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = int(os.getenv("WEB_MAX_DEBATE_ROUNDS", "1"))
    config["max_risk_discuss_rounds"] = int(os.getenv("WEB_MAX_RISK_ROUNDS", "1"))
    config["max_tool_rounds"] = int(os.getenv("WEB_MAX_TOOL_ROUNDS", "3"))
    if not os.getenv("TRADINGAGENTS_MAX_TOKENS"):
        config["max_tokens"] = int(os.getenv("WEB_MAX_TOKENS", "2048"))
    return config


def _format_reports(state: dict) -> str:
    sections = []
    for title, key in REPORTS:
        if text := state.get(key):
            sections.append(f"## {title}\n\n{text}")

    risk = state.get("risk_debate_state") or {}
    for title, key in (
        ("Aggressive risk view", "aggressive_history"),
        ("Conservative risk view", "conservative_history"),
        ("Neutral risk view", "neutral_history"),
    ):
        if text := risk.get(key):
            sections.append(f"## {title}\n\n{text}")
    return "\n\n---\n\n".join(sections) or "No reports were returned."


def analyze(ticker: str, trade_date: str, analysts: list[str]):
    ticker = (ticker or "").strip().upper()
    if not ticker:
        raise gr.Error("Enter a ticker symbol.")
    if not analysts:
        raise gr.Error("Select at least one analyst.")

    selected = [ANALYST_LABELS[label] for label in analysts]
    try:
        graph = TradingAgentsGraph(
            selected_analysts=selected,
            debug=False,
            config=_web_config(),
        )
        final_state, rating = graph.propagate(ticker, trade_date)
    except Exception as exc:
        raise gr.Error(f"Analysis failed: {exc}") from exc

    decision = final_state.get("final_trade_decision") or "No final decision was returned."
    return f"# {rating}\n\n{decision}", _format_reports(final_state)


def build_app() -> gr.Blocks:
    with gr.Blocks(title="TradingAgents") as app:
        gr.Markdown("# TradingAgents\nRun a non-interactive multi-agent market analysis.")
        with gr.Row():
            ticker = gr.Textbox(label="Ticker", value="NVDA", placeholder="e.g. AAPL")
            trade_date = gr.Textbox(label="Analysis date", value=date.today().isoformat())
        analysts = gr.CheckboxGroup(
            choices=list(ANALYST_LABELS),
            value=["Market"],
            label="Analysts (fewer analysts use fewer tokens)",
        )
        run = gr.Button("Run analysis", variant="primary")
        with gr.Tab("Decision"):
            decision = gr.Markdown()
        with gr.Tab("Reports"):
            reports = gr.Markdown()
        run.click(analyze, [ticker, trade_date, analysts], [decision, reports])
    return app


app = build_app()


if __name__ == "__main__":
    app.queue(default_concurrency_limit=1).launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
        show_error=True,
    )
