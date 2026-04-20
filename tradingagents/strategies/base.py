"""Base interface for quantitative strategy signals.

Every strategy subclasses BaseStrategy and implements compute().
Signals are typed dicts with a common shape for analyst prompt injection.

Reference:
    Zura Kakushadze and Juan Andrés Serur,
    "151 Trading Strategies",
    Palgrave Macmillan, 2018.
    SSRN: https://ssrn.com/abstract=3247865
    DOI: 10.1007/978-3-030-02792-6

    Section numbers (§) in each strategy module refer to this text.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypedDict


class StrategySignal(TypedDict, total=False):
    """Common signal shape returned by all strategies.

    Required keys: name, ticker, date, signal, value, direction.
    Optional keys are strategy-specific (e.g. rank, z_score, etc.).
    """
    name: str           # Strategy name (e.g. "momentum", "mean_reversion")
    ticker: str
    date: str           # YYYY-MM-DD
    signal: str         # STRONG | MODERATE | WEAK | NEGATIVE | NEUTRAL
    value: float        # Primary numeric value (strategy-specific meaning)
    value_label: str    # Human-readable value (e.g. "+42.3% (rank 2/27)")
    direction: str      # SUPPORTS | CONTRADICTS | NEUTRAL
    detail: dict        # Strategy-specific extra data


class BaseStrategy(ABC):
    """Abstract base for all strategy signal generators."""

    # Subclasses set these
    name: str = ""
    description: str = ""
    # Which analyst role(s) receive this signal
    target_analysts: list[str] = []

    @abstractmethod
    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        """Compute signal for a single ticker on a given date.

        Implementations must handle missing data gracefully — return a
        signal with signal="NEUTRAL" and value=0 rather than raising.

        kwargs may include:
            hist: pd.DataFrame — pre-fetched OHLCV history
            info: dict — pre-fetched yfinance .info
            portfolio_tickers: list[str] — for ranking within portfolio
        """
        ...

    def format_for_prompt(self, signal: StrategySignal) -> str:
        """Format signal with interpretation guidance for LLM prompt injection."""
        value_str = signal.get('value_label', str(signal.get('value', '')))
        direction = signal.get('direction', 'NEUTRAL')
        guidance = self.interpretation_guide
        if guidance:
            return f"- **{self.name}**: {value_str} [{direction}]. {guidance}"
        return f"- **{self.name}**: {value_str} [{direction}]"

    @property
    def interpretation_guide(self) -> str:
        """LLM guidance on how to interpret this signal.

        Override in subclasses to provide strategy-specific context:
        what the signal means, when it's reliable, what to combine it with,
        and common pitfalls.
        """
        return ""
