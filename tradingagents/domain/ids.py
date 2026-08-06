"""Opaque identifiers used by domain contracts.

The aliases are statically distinct while remaining strings on the wire.  The
underlying value deliberately carries no ticker, account, or broker semantics.
"""

from __future__ import annotations

from typing import NewType

# Compatibility IDs preserve the exact strings accepted by existing V2 DTOs
# and CLI/store boundaries.  Safety-sensitive path/object-key encodings must
# use a separate adapter-level encoding rather than narrowing identity here.
OpaqueIdString = str

ArtifactId = NewType("ArtifactId", OpaqueIdString)
EventId = NewType("EventId", OpaqueIdString)
ForecastId = NewType("ForecastId", OpaqueIdString)
InstrumentId = NewType("InstrumentId", OpaqueIdString)
ModelId = NewType("ModelId", OpaqueIdString)
PortfolioId = NewType("PortfolioId", OpaqueIdString)
ProtocolId = NewType("ProtocolId", OpaqueIdString)
RunId = NewType("RunId", OpaqueIdString)
StrategyId = NewType("StrategyId", OpaqueIdString)
TargetPortfolioId = NewType("TargetPortfolioId", OpaqueIdString)
