"""Portfolio construction port."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from tradingagents.domain.forecasts import ForecastEstimate
from tradingagents.domain.ids import InstrumentId
from tradingagents.domain.instruments import ListingRef
from tradingagents.domain.portfolios import (
    PortfolioConstraints,
    TargetContext,
    TargetPortfolio,
)


@runtime_checkable
class ForecastWeightPolicy(Protocol):
    """V2's synchronous conversion of one forecast cross-section into weights."""

    def allocate(
        self,
        *,
        forecasts: Sequence[ForecastEstimate],
        current_weights: Mapping[InstrumentId, float],
        listings: Sequence[ListingRef],
        sectors: Mapping[InstrumentId, str],
        constraints: PortfolioConstraints,
        context: TargetContext,
    ) -> TargetPortfolio: ...
