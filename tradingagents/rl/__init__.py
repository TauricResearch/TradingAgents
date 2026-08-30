"""FinRL-X weight-centric RL allocator.

Architecture: w = R(T(A(S(market)))) where S=selection, A=allocation,
T=timing, R=risk overlay. Sole contract is target weight vector.
Paper: FinRL-X arXiv:2603.21330
"""

from tradingagents.rl.weight_allocator import (
    DRLAllocator,
    EqualWeightAllocator,
    MeanVarianceAllocator,
    WeightAllocator,
    apply_risk_overlay,
)

__all__ = [
    "WeightAllocator",
    "EqualWeightAllocator",
    "MeanVarianceAllocator",
    "DRLAllocator",
    "apply_risk_overlay",
]
