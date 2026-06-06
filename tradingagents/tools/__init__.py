"""Agent tool layer (the wiki tool inventory as real callables).

These are the concrete tools the desks/PM use. The defining rule (wiki): for
decision-critical live data the tool tries the real-time source first and writes
a copy through to the DB (so the DB stays the single information center); for
immutable/historical data it reads the DB. Each tool takes a session so it can
write-through, and an optional ``live_fn`` injected for the real-time path
(kept injectable so everything is testable offline).
"""

from .market import get_realtime_quote, volume_spike
from .portfolio import get_open_positions_risk

__all__ = ["get_realtime_quote", "volume_spike", "get_open_positions_risk"]
