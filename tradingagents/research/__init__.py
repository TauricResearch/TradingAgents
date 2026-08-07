"""Leakage-bounded offline research pipeline.

The package deliberately exposes four separate phases: evidence snapshots,
decisions, outcome labels, and evaluation.  Only immutable artifact identifiers
cross phase boundaries.
"""

from tradingagents.research.artifacts import ArtifactRef, FilesystemArtifactStore
from tradingagents.research.contracts import ModelCheckpointSpec

__all__ = [
    "ArtifactRef",
    "FilesystemArtifactStore",
    "ModelCheckpointSpec",
]
