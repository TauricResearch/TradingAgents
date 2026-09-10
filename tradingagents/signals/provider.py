from typing import Protocol

from .models import NormalizedSignal


class SignalProvider(Protocol):
    """Protocol for external signal providers."""

    def get_signals(self, symbol: str) -> list[NormalizedSignal]:
        """Return normalized signals for a symbol."""
        ...