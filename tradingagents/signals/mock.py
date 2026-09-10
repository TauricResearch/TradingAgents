from .models import NormalizedSignal


class MockSignalProvider:
    """Simple in-memory signal provider for examples and tests."""

    def __init__(self, signals: list[NormalizedSignal]) -> None:
        self._signals = signals

    def get_signals(self, symbol: str) -> list[NormalizedSignal]:
        """Return signals matching the requested symbol."""
        return [
            signal
            for signal in self._signals
            if signal.symbol == symbol
        ]