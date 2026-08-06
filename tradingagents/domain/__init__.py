"""Framework-independent trading domain contracts.

The domain package is intentionally free of environment, storage, network,
or orchestration concerns.  New contracts are introduced here only when an
existing workflow exercises them.
"""

from tradingagents.domain.forecasts import ForecastEstimate, ForecastHorizon
from tradingagents.domain.ids import (
    ArtifactId,
    EventId,
    ForecastId,
    InstrumentId,
    ModelId,
    PortfolioId,
    ProtocolId,
    RunId,
    StrategyId,
    TargetPortfolioId,
)
from tradingagents.domain.instruments import AssetClass, ListingRef, provisional_listing
from tradingagents.domain.portfolios import (
    AllocationDiagnostics,
    PortfolioConstraints,
    PortfolioMode,
    TargetAllocation,
    TargetContext,
    TargetPortfolio,
)
from tradingagents.domain.time import AsOf, TimeRange, VintagePolicy

__all__ = [
    "AllocationDiagnostics",
    "ArtifactId",
    "AsOf",
    "AssetClass",
    "EventId",
    "ForecastEstimate",
    "ForecastHorizon",
    "ForecastId",
    "InstrumentId",
    "ListingRef",
    "ModelId",
    "PortfolioConstraints",
    "PortfolioId",
    "PortfolioMode",
    "ProtocolId",
    "RunId",
    "StrategyId",
    "TargetAllocation",
    "TargetContext",
    "TargetPortfolio",
    "TargetPortfolioId",
    "TimeRange",
    "VintagePolicy",
    "provisional_listing",
]
