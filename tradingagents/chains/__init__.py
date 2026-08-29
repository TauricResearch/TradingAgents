"""
Chained Investment Strategies.

Provides multi-market chained investment strategies with
correlation-based execution.
"""

from .models import ChainStrategy, ChainStep, ChainStepStatus, ChainExecutionResult
from .executor import ChainExecutor
from .prototypes import create_geopolitical_tension_chain, create_crypto_correlation_chain
from .carry_trade_prototypes import GlobalCarryStrategies

__all__ = [
    "ChainStrategy",
    "ChainStep",
    "ChainStepStatus",
    "ChainExecutionResult",
    "ChainExecutor",
    "create_geopolitical_tension_chain",
    "create_crypto_correlation_chain",
    "GlobalCarryStrategies",
]
