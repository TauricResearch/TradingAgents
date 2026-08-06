"""Adapter for the existing deterministic V2 optimizer."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict

from tradingagents.compat.portfolio import target_from_legacy_weights
from tradingagents.domain.forecasts import ForecastEstimate
from tradingagents.domain.ids import InstrumentId
from tradingagents.domain.instruments import ListingRef
from tradingagents.domain.portfolios import (
    PortfolioConstraints,
    PortfolioMode,
    TargetContext,
    TargetPortfolio,
)
from tradingagents.portfolio_backtest import optimize_forecast_weights


class LegacyOptimizerForecastWeightPolicy:
    """Expose the proven optimizer through the new canonical portfolio port."""

    def allocate(
        self,
        *,
        forecasts: Sequence[ForecastEstimate],
        current_weights: Mapping[InstrumentId, float],
        listings: Sequence[ListingRef],
        sectors: Mapping[InstrumentId, str],
        constraints: PortfolioConstraints,
        context: TargetContext,
    ) -> TargetPortfolio:
        listings = tuple(listings)
        by_id = {listing.instrument_id: listing for listing in listings}
        if len(by_id) != len(listings):
            raise ValueError("portfolio policy requires unique instrument listings")
        forecast_ids = {forecast.instrument_id for forecast in forecasts}
        if forecast_ids != set(by_id) or len(forecasts) != len(listings):
            raise ValueError("forecast cross-section must exactly match the listing universe")
        if set(current_weights) != set(by_id):
            raise ValueError("current weights must exactly match the listing universe")
        if set(sectors) != set(by_id):
            raise ValueError("sector map must exactly match the listing universe")
        if constraints.mode != PortfolioMode.LONG_ONLY:
            raise ValueError("the legacy optimizer adapter supports long-only targets only")
        if any(not math.isfinite(value) for value in current_weights.values()):
            raise ValueError("current portfolio weights must be finite")
        horizons = {forecast.horizon for forecast in forecasts}
        if len(horizons) != 1:
            raise ValueError("forecast cross-section must use exactly one horizon")
        for forecast in forecasts:
            if forecast.run_id != context.run_id:
                raise ValueError("forecast run ID does not match target context")
            if forecast.protocol_id != context.protocol_id:
                raise ValueError("forecast protocol ID does not match target context")
            if forecast.as_of != context.as_of:
                raise ValueError("forecast AsOf boundary does not match target context")

        rows = [
            {
                "ticker": by_id[forecast.instrument_id].symbol,
                "expected_excess_return_bps": forecast.expected_excess_return_bps,
                "probability_positive": forecast.probability_positive,
                "confidence": forecast.confidence,
                "abstain": forecast.abstain,
                "event_ids": list(forecast.event_ids),
                "rationale": forecast.rationale,
            }
            for forecast in forecasts
        ]
        result = optimize_forecast_weights(
            rows,
            current_weights={by_id[key].symbol: value for key, value in current_weights.items()},
            sectors={by_id[key].symbol: value for key, value in sectors.items()},
            gross_limit=constraints.gross_limit,
            max_weight=constraints.max_weight,
            max_sector_weight=constraints.max_sector_weight,
            turnover_hurdle_bps=constraints.turnover_hurdle_bps,
            minimum_trade_weight=constraints.minimum_trade_weight,
        )
        target = target_from_legacy_weights(
            weights=result.weights,
            diagnostics=asdict(result),
            constraints=constraints,
            context=context,
            listings=listings,
            forecast_ids=tuple(forecast.forecast_id for forecast in forecasts),
        )
        return target
