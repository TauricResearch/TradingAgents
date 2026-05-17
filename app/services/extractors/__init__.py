"""
TT-295: structured-data extraction for agent reports.

After each TradingAgents agent completes, run a small follow-up LLM call
that extracts the analyst's quantitative findings (RSI value, P/E ratio,
sentiment score, etc.) into a stable Pydantic schema. The dashboard then
renders these as gauges, sparklines, and metric cards.

Best-effort: extraction failures null the metadata field but never break
the underlying agent_reports row write (see callbacks.py).
"""

from .extractor import extract_metadata

__all__ = ["extract_metadata"]
