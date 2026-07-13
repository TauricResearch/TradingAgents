"""Shared, typed contracts for TradingAgents Pro (Phase 0).

Every later phase (asset ingestion, agent hierarchy, debate pipeline,
backtesting, execution) exchanges data through the models defined here.
Ground rules encoded in these contracts:

- LLM agents never compute numbers. Deterministic code produces a
  ``MarketSnapshot``; agents read it and answer with ``AgentEvidence``.
- Every agent claim carries direction, confidence, timeframe, data
  references, and source attribution. Evidence-free prose does not parse.
- ``TradeRecommendation.risk_reward`` is a computed field derived from the
  entry / stop / take-profit ladder — it cannot be supplied by a model.
- ``ProConfig`` defaults to paper trading; a live-mode config cannot be
  constructed without both the explicit enable flag and human approval.

All models are immutable (``frozen=True``) and reject unknown fields
(``extra="forbid"``) so a malformed agent output fails loudly at the
boundary instead of drifting through the graph.
"""

from tradingagents.contracts.base import SCHEMA_VERSION, ContractModel, utc_now
from tradingagents.contracts.config import (
    LiveRiskLimits,
    ModelRouting,
    ProConfig,
    RiskLimits,
)
from tradingagents.contracts.enums import (
    AgentTeam,
    AssetClass,
    Direction,
    MarketRegime,
    SourceType,
    Timeframe,
    TradeAction,
    TradingMode,
    TradingSession,
)
from tradingagents.contracts.evidence import AgentEvidence, DataRef, SourceAttribution
from tradingagents.contracts.recommendation import (
    AgentVote,
    HistoricalAnalog,
    PositionSize,
    TakeProfitLevel,
    TradeRecommendation,
    VoteBreakdown,
)
from tradingagents.contracts.snapshot import (
    IndicatorReading,
    MarketSnapshot,
    MetricReading,
    NewsItem,
    OHLCVBar,
    SpotQuote,
)

__all__ = [
    "SCHEMA_VERSION",
    "ContractModel",
    "utc_now",
    "AgentTeam",
    "AssetClass",
    "Direction",
    "MarketRegime",
    "SourceType",
    "Timeframe",
    "TradeAction",
    "TradingMode",
    "TradingSession",
    "AgentEvidence",
    "DataRef",
    "SourceAttribution",
    "AgentVote",
    "HistoricalAnalog",
    "PositionSize",
    "TakeProfitLevel",
    "TradeRecommendation",
    "VoteBreakdown",
    "IndicatorReading",
    "MarketSnapshot",
    "MetricReading",
    "NewsItem",
    "OHLCVBar",
    "SpotQuote",
    "ModelRouting",
    "ProConfig",
    "LiveRiskLimits",
    "RiskLimits",
]
