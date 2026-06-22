"""Host glue between the native macOS app (TradingDesk) and the TradingAgents engine.

This package is intentionally thin. Two modules are dependency-free and import
nothing from ``tradingagents`` so they can be unit-tested on any interpreter:

- ``desk_adapter.protocol`` — the NDJSON event channel (envelope + fd-1 discipline).
- ``desk_adapter.diff`` — turns consecutive ``stream_mode="values"`` whole-state
  snapshots into the typed event stream the app consumes.

The remaining modules (``run``, ``introspect``, ``env``, ``__main__``) drive the
engine and therefore require the full ``tradingagents`` dependency tree (Python
>=3.10). Keep this ``__init__`` import-light so importing the pure modules never
pulls the engine in.
"""

from desk_adapter.protocol import SCHEMA_VERSION

__all__ = ["SCHEMA_VERSION"]
