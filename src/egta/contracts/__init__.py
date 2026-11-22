"""Shared evidence contracts, re-exported for consumers.

    from egta.contracts import RunSpec, EvidenceItem, EvidencePack

The shared ``ReasonCode`` lives in ``egta.contracts.events`` (owned by the
contracts package's events module); this package does not redefine it.
"""

from __future__ import annotations

from egta.contracts.evidence import (
    Availability,
    EvidenceItem,
    EvidencePack,
    ExcludedItem,
    RunSpec,
)

__all__ = [
    "Availability",
    "EvidenceItem",
    "EvidencePack",
    "ExcludedItem",
    "RunSpec",
]
