"""Build the context strings injected into each agent.

Numbers come from the DB (real indicators, portfolio). Data families not yet
ingested (news, financials, social) are passed as explicit placeholders so the
agent knows what is missing rather than inventing it — wiring those vendors to
the DB is a documented follow-up.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..execution import inject_portfolio_state
from ..indicators import indicator_snapshot


def _fmt(d: dict[str, Any]) -> str:
    return "\n".join(f"- {k}: {v}" for k, v in d.items())


def market_context(session: Session, symbol: str) -> str:
    return (
        f"<ticker>{symbol}</ticker>\n"
        "<macro>not yet wired to DB (FRED): treat as neutral unless stated</macro>\n"
        "<news>not yet wired to DB (Finnhub): no catalysts available</news>"
    )


def sentiment_context(session: Session, symbol: str) -> str:
    return (
        f"<ticker>{symbol}</ticker>\n"
        "<news_sentiment>not yet wired</news_sentiment>\n"
        "<social_sentiment>not yet wired (Reddit/StockTwits/X)</social_sentiment>"
    )


def technical_context(session: Session, symbol: str) -> str:
    snap = indicator_snapshot(session, symbol)
    return f"<ticker>{symbol}</ticker>\n<technical_data>\n{_fmt(snap)}\n</technical_data>"


def fundamentals_context(session: Session, symbol: str) -> str:
    return (
        f"<ticker>{symbol}</ticker>\n"
        "<financials>not yet wired to DB (Alpha Vantage): unavailable</financials>"
    )


def pm_context(session: Session, symbol: str, opinions: list[dict[str, Any]]) -> str:
    snap = indicator_snapshot(session, symbol)
    portfolio = inject_portfolio_state(session)
    op_lines = "\n".join(
        f"- {o['agent']}: dir={o['suggested_direction']} conv={o['suggested_conviction']} :: {o['rationale']}"
        for o in opinions
    )
    return (
        f"<ticker>{symbol}</ticker>\n"
        f"<atr_14>{snap.get('atr_14')}</atr_14>\n"
        f"<last_close>{snap.get('last_close')}</last_close>\n"
        f"<portfolio>\n{_fmt(portfolio)}\n</portfolio>\n"
        f"<desk_opinions>\n{op_lines}\n</desk_opinions>"
    )


def risk_context(session: Session, symbol: str, sealed: dict[str, Any], guardrails: dict[str, Any]) -> str:
    return (
        f"<ticker>{symbol}</ticker>\n"
        f"<proposal>{sealed.get('proposal')}</proposal>\n"
        f"<guardrail_checks>{guardrails}</guardrail_checks>"
    )
