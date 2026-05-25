"""Audit subsystem for TradingAgents.

This package collects the infrastructure SR 11-7 model risk management
expects from any production LLM system: full prompt + response capture
(T1.2), hash-chained immutable storage (T1.3, planned), pinned prompt
versioning (T1.4, planned), and deterministic replay (T1.7, planned).

The Phase 0 work (deterministic LLM kwargs, news snapshots, checkpoint
archival, per-call JSONL) lives in its original locations because it
slots into existing callbacks and dataflows; this package contains the
new instrumentation that needed a fresh home rather than retrofits.
"""

from tradingagents.audit.ledger import (
    GENESIS_HASH,
    HashChainLedger,
    VerifyResult,
    verify_ledger,
)
from tradingagents.audit.prompt_registry import (
    DEFAULT_PROMPTS_DIR,
    PromptNotFoundError,
    PromptRegistry,
    default_registry,
    reset_default_registry,
)
from tradingagents.audit.replay import (
    PromptVerification,
    Replayer,
    ReplaySummary,
)
from tradingagents.audit.schemas import (
    NODE_ENTER,
    NODE_EXIT,
    LLM_END,
    LLM_START,
    TOOL_END,
    TOOL_START,
    TraceRecord,
)
from tradingagents.audit.trace_callback import TraceCallback

__all__ = [
    "TraceCallback",
    "TraceRecord",
    "HashChainLedger",
    "VerifyResult",
    "verify_ledger",
    "GENESIS_HASH",
    "PromptRegistry",
    "PromptNotFoundError",
    "DEFAULT_PROMPTS_DIR",
    "default_registry",
    "reset_default_registry",
    "Replayer",
    "ReplaySummary",
    "PromptVerification",
    "LLM_START",
    "LLM_END",
    "TOOL_START",
    "TOOL_END",
    "NODE_ENTER",
    "NODE_EXIT",
]
