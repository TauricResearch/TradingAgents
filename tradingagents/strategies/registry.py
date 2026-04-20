"""Strategy registry — discover, run, and cache all enabled strategies per ticker."""

from __future__ import annotations

import importlib
import pkgutil
import sys
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tradingagents.portfolio.cache import AnalysisCache

from tradingagents.strategies.base import BaseStrategy, StrategySignal


def _discover_strategies() -> list[BaseStrategy]:
    """Import all modules in tradingagents.strategies and collect BaseStrategy subclasses."""
    import tradingagents.strategies as pkg

    for finder, name, _ in pkgutil.iter_modules(pkg.__path__):
        if name in ("base", "registry"):
            continue
        try:
            importlib.import_module(f"tradingagents.strategies.{name}")
        except Exception as e:
            print(f"  ⚠️ Strategy module {name} failed to import: {e}", file=sys.stderr)

    instances: list[BaseStrategy] = []
    for cls in BaseStrategy.__subclasses__():
        try:
            instances.append(cls())
        except Exception as e:
            print(f"  ⚠️ Strategy {cls.__name__} failed to instantiate: {e}", file=sys.stderr)
    return instances


# Module-level singleton (populated on first call)
_strategies: list[BaseStrategy] | None = None


def get_strategies() -> list[BaseStrategy]:
    """Return all discovered strategy instances (cached after first call)."""
    global _strategies
    if _strategies is None:
        _strategies = _discover_strategies()
    return _strategies


def compute_signals(
    ticker: str,
    date: str,
    cache: "AnalysisCache | None" = None,
    **kwargs,
) -> list[StrategySignal]:
    """Compute all strategy signals for a ticker. Returns list of signals.

    Checks Redis cache first (key: strategy:{name}:{ticker}:{date}).
    Failed strategies are skipped gracefully.

    Meta-strategies (alpha_combo) run in a second pass with Tier 1 signals
    injected as tier1_signals kwarg.
    """
    strategies = get_strategies()
    signals: list[StrategySignal] = []
    deferred: list[BaseStrategy] = []  # meta-strategies that need tier1 signals

    # Names of meta-strategies that depend on other signals
    META_STRATEGIES = {"alpha_combo"}

    for strat in strategies:
        if strat.name in META_STRATEGIES:
            deferred.append(strat)
            continue

        # Check cache
        if cache and cache.available:
            try:
                cached = cache.get_strategy(strat.name, ticker, date)
                if cached:
                    signals.append(cached)
                    continue
            except Exception:
                pass

        # Compute
        try:
            sig = strat.compute(ticker, date, **kwargs)
            signals.append(sig)
            # Cache result
            if cache and cache.available:
                try:
                    cache.set_strategy(strat.name, ticker, date, sig)
                except Exception:
                    pass
        except Exception as e:
            print(f"  ⚠️ Strategy {strat.name} failed for {ticker}: {e}", file=sys.stderr)

    # Second pass: meta-strategies with tier1 signals
    for strat in deferred:
        if cache and cache.available:
            try:
                cached = cache.get_strategy(strat.name, ticker, date)
                if cached:
                    signals.append(cached)
                    continue
            except Exception:
                pass
        try:
            sig = strat.compute(ticker, date, tier1_signals=signals, **kwargs)
            signals.append(sig)
            if cache and cache.available:
                try:
                    cache.set_strategy(strat.name, ticker, date, sig)
                except Exception:
                    pass
        except Exception as e:
            print(f"  ⚠️ Strategy {strat.name} failed for {ticker}: {e}", file=sys.stderr)

    return signals


def signals_by_analyst(signals: list[StrategySignal]) -> dict[str, list[StrategySignal]]:
    """Group signals by target analyst role.

    Returns e.g. {"technical": [...], "fundamentals": [...], "risk": [...], "portfolio": [...]}.
    """
    strategies = get_strategies()
    name_to_strat = {s.name: s for s in strategies}
    grouped: dict[str, list[StrategySignal]] = defaultdict(list)

    for sig in signals:
        strat = name_to_strat.get(sig.get("name", ""))
        if strat:
            for role in strat.target_analysts:
                grouped[role].append(sig)
        else:
            grouped["portfolio"].append(sig)

    return dict(grouped)


def format_signals_for_prompt(signals: list[StrategySignal]) -> str:
    """Format a list of signals as text block for LLM prompt injection."""
    if not signals:
        return ""
    strategies = get_strategies()
    name_to_strat = {s.name: s for s in strategies}
    lines = ["Quantitative Strategy Signals:"]
    for sig in signals:
        strat = name_to_strat.get(sig.get("name", ""))
        if strat:
            lines.append(strat.format_for_prompt(sig))
        else:
            lines.append(f"- {sig.get('name', '?')}: {sig.get('value_label', '')} [{sig.get('direction', '')}]")
    return "\n".join(lines)


_ROLE_CITATIONS: dict[str, str] = {
    "technical": (
        "\n\nWhen making your recommendation, explicitly reference the quantitative strategy signals above. "
        "For each signal that supports or contradicts your thesis, state:\n"
        "- The signal name and value\n"
        "- Whether it SUPPORTS or CONTRADICTS your recommendation\n"
        "- How it influenced your confidence level\n\n"
        "Example: \"The momentum score of +42.3% (rank 2/27) SUPPORTS the bullish thesis, "
        "but the mean reversion Z-score of 1.8 CONTRADICTS — the stock is extended 1.8σ "
        "above its 60-day mean, suggesting a pullback is likely before further upside.\""
    ),
    "fundamentals": (
        "\n\nWhen making your recommendation, explicitly reference the quantitative strategy signals above. "
        "For each signal that supports or contradicts your thesis, state:\n"
        "- The signal name and value\n"
        "- Whether it SUPPORTS or CONTRADICTS your recommendation\n"
        "- How it influenced your confidence level\n\n"
        "Example: \"The value composite score of 0.72 (deep value) SUPPORTS the undervaluation thesis, "
        "and the earnings momentum SUE of +2.1σ SUPPORTS — post-earnings drift suggests continued upside.\""
    ),
    "risk": (
        "\n\nWhen making your recommendation, explicitly reference the quantitative strategy signals above. "
        "For each signal that supports or contradicts your thesis, state:\n"
        "- The signal name and value\n"
        "- Whether it SUPPORTS or CONTRADICTS your recommendation\n"
        "- How it influenced your risk assessment\n\n"
        "Example: \"Realized volatility at 45% (high-vol quintile) CONTRADICTS an overweight position — "
        "the IV premium of +8.2% suggests the market is pricing in elevated risk.\""
    ),
    "portfolio": (
        "\n\nWhen making your recommendation, explicitly reference the quantitative strategy signals above. "
        "For each signal that supports or contradicts your thesis, state:\n"
        "- The signal name and value\n"
        "- Whether it SUPPORTS or CONTRADICTS your recommendation\n"
        "- How it influenced your position sizing or allocation decision\n\n"
        "Example: \"The multifactor composite of 0.64 (moderate) suggests a neutral weight, "
        "while sector rotation shows Technology in the top quintile, SUPPORTING an overweight tilt.\""
    ),
    "research": (
        "\n\nWhen making your recommendation, explicitly reference the quantitative strategy signals above. "
        "For each signal, state the name, value, and whether it SUPPORTS or CONTRADICTS your thesis.\n\n"
        "Pay special attention to:\n"
        "- Pairs trading signals: if the stock is cheap/expensive vs its most correlated peer, "
        "use this as evidence for relative value arguments.\n"
        "- Event-driven M&A signals: if volume spikes, price gaps, or volatility compression "
        "suggest corporate activity, factor this into your bull/bear case."
    ),
}

_DEFAULT_CITATION = (
    "\n\nWhen making your recommendation, explicitly reference the quantitative strategy signals above. "
    "For each signal that supports or contradicts your thesis, state the signal name, value, "
    "and whether it SUPPORTS or CONTRADICTS your recommendation."
)


def format_signals_for_role(strategy_signals: str | list, role: str) -> str:
    """Extract signals for a specific analyst role and format for prompt.

    Args:
        strategy_signals: JSON string or list of StrategySignal dicts
        role: Analyst role key (e.g. "technical", "fundamentals", "risk")

    Returns formatted text block with role-specific citation instruction, or "" if no signals.
    """
    if not strategy_signals:
        return ""
    if isinstance(strategy_signals, str):
        try:
            import json
            all_signals = json.loads(strategy_signals)
        except Exception:
            return ""
    else:
        all_signals = strategy_signals
    if not all_signals:
        return ""

    grouped = signals_by_analyst(all_signals)
    role_signals = grouped.get(role, [])
    if not role_signals:
        return ""

    text = format_signals_for_prompt(role_signals)
    citation = _ROLE_CITATIONS.get(role, _DEFAULT_CITATION)
    return text + citation
