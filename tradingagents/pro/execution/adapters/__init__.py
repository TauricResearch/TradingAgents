"""Live venue transports (go-live Phase 1+).

Each adapter implements the ``VenueAdapter`` v2 protocol from
``execution.interface``. Credentials load from the environment/secrets
layer only — never from code — and are redacted from every log line and
error message (see ``delta_auth.redact``).
"""

from tradingagents.pro.execution.adapters.delta import DeltaAdapter

__all__ = ["DeltaAdapter"]
