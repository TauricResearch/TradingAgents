"""Scorecard — aggregate strategy consensus from computed signals."""

from __future__ import annotations

from typing import Literal

from typing_extensions import TypedDict

from .base import StrategySignal


class Scorecard(TypedDict):
    """Aggregated consensus across all strategy signals."""

    ticker: str
    date: str
    bullish: int
    bearish: int
    neutral: int
    total: int
    overall: Literal["bullish", "bearish", "neutral"]
    avg_strength: float  # mean signal_strength across all signals


def build_scorecard(signals: list[StrategySignal]) -> Scorecard | None:
    """Build a consensus scorecard from a list of signals.

    Returns ``None`` when *signals* is empty.
    """
    if not signals:
        return None

    counts = {"bullish": 0, "bearish": 0, "neutral": 0}
    for s in signals:
        counts[s["direction"]] += 1

    total = len(signals)
    avg = sum(s["signal_strength"] for s in signals) / total

    # Overall direction: majority wins; tie-break by avg_strength sign
    if counts["bullish"] > counts["bearish"]:
        overall: Literal["bullish", "bearish", "neutral"] = "bullish"
    elif counts["bearish"] > counts["bullish"]:
        overall = "bearish"
    else:
        overall = "bullish" if avg > 0 else "bearish" if avg < 0 else "neutral"

    return Scorecard(
        ticker=signals[0]["ticker"],
        date=signals[0]["date"],
        bullish=counts["bullish"],
        bearish=counts["bearish"],
        neutral=counts["neutral"],
        total=total,
        overall=overall,
        avg_strength=round(avg, 4),
    )


def format_scorecard(sc: Scorecard | None) -> str:
    """Format a scorecard as a prompt-ready string. Empty string if None."""
    if sc is None:
        return ""
    return (
        f"## Strategy Consensus Scorecard\n"
        f"- Ticker: {sc['ticker']} | Date: {sc['date']}\n"
        f"- Bullish: {sc['bullish']} | Bearish: {sc['bearish']} | Neutral: {sc['neutral']} (total: {sc['total']})\n"
        f"- Avg signal strength: {sc['avg_strength']:+.4f}\n"
        f"- Overall direction: **{sc['overall']}**"
    )
