"""Normalize TradingAgents graph state into UI-safe structured payloads.

Never invent prices, targets, or confidence. Only surface values the engine
already produced (structured trader/PM fields or explicit markdown labels).
"""

from __future__ import annotations

import re
from typing import Any

from tradingagents.agents.utils.rating import parse_rating

AGENT_ORDER = [
    "Market Analyst",
    "Sentiment Analyst",
    "News Analyst",
    "Fundamentals Analyst",
    "Bull Researcher",
    "Bear Researcher",
    "Research Manager",
    "Trader",
    "Aggressive Analyst",
    "Neutral Analyst",
    "Conservative Analyst",
    "Portfolio Manager",
]

ANALYST_KEYS = {
    "market": "Market Analyst",
    "social": "Sentiment Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}

REPORT_TO_AGENT = {
    "market_report": "Market Analyst",
    "sentiment_report": "Sentiment Analyst",
    "news_report": "News Analyst",
    "fundamentals_report": "Fundamentals Analyst",
}

_CONFIDENCE_RE = re.compile(r"\*\*Confidence:\*\*\s*(Low|Medium|High)", re.I)
_ENTRY_RE = re.compile(r"\*\*Entry Price\*\*:\s*([0-9]+(?:\.[0-9]+)?)", re.I)
_STOP_RE = re.compile(r"\*\*Stop Loss\*\*:\s*([0-9]+(?:\.[0-9]+)?)", re.I)
_TARGET_RE = re.compile(r"\*\*Price Target\*\*:\s*([0-9]+(?:\.[0-9]+)?)", re.I)
_HORIZON_RE = re.compile(r"\*\*Time Horizon\*\*:\s*(.+)", re.I)
_SENTIMENT_RE = re.compile(r"Overall Sentiment:\*\*\s*\*\*(.+?)\*\*", re.I)


def first_paragraphs(text: str | None, n: int = 2) -> str | None:
    if not text:
        return None
    chunks = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if not chunks:
        return text.strip()[:600]
    return "\n\n".join(chunks[:n])


def _float_from(pattern: re.Pattern, text: str | None) -> float | None:
    if not text:
        return None
    match = pattern.search(text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def map_action(rating: str) -> str:
    mapping = {
        "Buy": "BUY",
        "Overweight": "BUY",
        "Hold": "HOLD",
        "Underweight": "SELL",
        "Sell": "SELL",
    }
    return mapping.get(rating, rating.upper())


def confidence_from_text(*texts: str | None) -> float | None:
    for text in texts:
        if not text:
            continue
        match = _CONFIDENCE_RE.search(text)
        if match:
            return {"low": 38.0, "medium": 62.0, "high": 82.0}[match.group(1).lower()]
    return None


def risk_from_decision(action: str, debate: dict | None) -> str:
    if not debate:
        return "MEDIUM"
    agg = bool((debate.get("aggressive_history") or "").strip())
    con = bool((debate.get("conservative_history") or "").strip())
    if action == "HOLD":
        return "LOW"
    if con and action == "SELL":
        return "HIGH"
    if agg and action == "BUY":
        return "MEDIUM"
    return "MEDIUM"


def plain_language(action: str, rating: str, reason: str | None, symbol: str) -> str:
    name = symbol.replace(".NS", "").replace(".BO", "")
    if action == "BUY":
        lead = f"The desk leans toward buying {name}."
    elif action == "SELL":
        lead = f"The desk leans toward reducing or exiting {name}."
    else:
        lead = f"The desk prefers to wait on {name} (Hold)."
    extra = first_paragraphs(reason, 1) or f"Final rating from the Portfolio Manager: {rating}."
    return f"{lead} {extra}"


def extract_agents(final_state: dict[str, Any]) -> list[dict[str, Any]]:
    debate = final_state.get("investment_debate_state") or {}
    risk = final_state.get("risk_debate_state") or {}
    mapping = [
        ("Market Analyst", final_state.get("market_report")),
        ("Sentiment Analyst", final_state.get("sentiment_report")),
        ("News Analyst", final_state.get("news_report")),
        ("Fundamentals Analyst", final_state.get("fundamentals_report")),
        ("Bull Researcher", debate.get("bull_history")),
        ("Bear Researcher", debate.get("bear_history")),
        ("Research Manager", debate.get("judge_decision") or final_state.get("investment_plan")),
        ("Trader", final_state.get("trader_investment_plan")),
        ("Aggressive Analyst", risk.get("aggressive_history")),
        ("Neutral Analyst", risk.get("neutral_history")),
        ("Conservative Analyst", risk.get("conservative_history")),
        ("Portfolio Manager", risk.get("judge_decision") or final_state.get("final_trade_decision")),
    ]
    agents = []
    for name, content in mapping:
        if not content:
            continue
        extra: dict[str, Any] = {"full": content}
        if name == "Sentiment Analyst":
            band = _SENTIMENT_RE.search(content)
            if band:
                extra["band"] = band.group(1)
        agents.append(
            {
                "agent_name": name,
                "status": "completed",
                "summary": first_paragraphs(content, 2),
                "structured_output": extra,
            }
        )
    return agents


def normalize_final_state(symbol: str, final_state: dict[str, Any], processed_signal: str | None) -> dict[str, Any]:
    pm_text = (final_state.get("final_trade_decision") or "")
    risk = final_state.get("risk_debate_state") or {}
    if not pm_text and risk.get("judge_decision"):
        pm_text = risk["judge_decision"]
    trader_text = final_state.get("trader_investment_plan") or ""
    rating = processed_signal or parse_rating(pm_text)
    action = map_action(rating)
    reason = first_paragraphs(pm_text, 2)
    confidence = confidence_from_text(final_state.get("sentiment_report"), pm_text, trader_text)
    entry = _float_from(_ENTRY_RE, trader_text)
    stop = _float_from(_STOP_RE, trader_text)
    target = _float_from(_TARGET_RE, pm_text)
    horizon_match = _HORIZON_RE.search(pm_text or "")
    horizon = horizon_match.group(1).strip() if horizon_match else None
    debate = final_state.get("investment_debate_state") or {}
    return {
        "symbol": symbol,
        "rating": rating,
        "action": action,
        "confidence": confidence,
        "risk_level": risk_from_decision(action, risk),
        "reason": reason,
        "in_plain_language": plain_language(action, rating, reason, symbol),
        "entry_price": entry,
        "stop_loss": stop,
        "price_target": target,
        "time_horizon": horizon,
        "reports": {
            "market": final_state.get("market_report"),
            "sentiment": final_state.get("sentiment_report"),
            "news": final_state.get("news_report"),
            "fundamentals": final_state.get("fundamentals_report"),
            "bull": debate.get("bull_history"),
            "bear": debate.get("bear_history"),
            "research_manager": debate.get("judge_decision") or final_state.get("investment_plan"),
            "trader": trader_text,
            "risk_aggressive": risk.get("aggressive_history"),
            "risk_neutral": risk.get("neutral_history"),
            "risk_conservative": risk.get("conservative_history"),
            "portfolio_manager": pm_text,
        },
        "agents": extract_agents(final_state),
    }
