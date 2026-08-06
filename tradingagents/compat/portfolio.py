"""Lossless compatibility for the current paper-target JSON shape."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from tradingagents.domain.ids import ForecastId, InstrumentId
from tradingagents.domain.instruments import ListingRef, provisional_listing
from tradingagents.domain.portfolios import (
    AllocationDiagnostics,
    PortfolioConstraints,
    TargetAllocation,
    TargetContext,
    TargetPortfolio,
)

_DIAGNOSTIC_KEYS = {
    "weights",
    "turnover",
    "cash_weight",
    "active_forecasts",
    "abstentions",
    "binding_constraints",
}


def _legacy_symbol(value: object) -> str:
    if not isinstance(value, str) or value != value.strip().upper() or not value:
        raise ValueError(f"legacy symbols must already be canonical uppercase strings: {value!r}")
    return value


def _legacy_float(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, float):
        raise ValueError(f"legacy {field} must be a float")
    return value


def _listing_index(listings: Sequence[ListingRef]) -> dict[str, ListingRef]:
    index = {listing.symbol: listing for listing in listings}
    if len(index) != len(listings):
        raise ValueError("legacy conversion requires unique listing symbols")
    return index


def target_from_legacy_weights(
    *,
    weights: Mapping[str, float],
    diagnostics: Mapping[str, object],
    constraints: PortfolioConstraints,
    context: TargetContext,
    listings: Sequence[ListingRef] | None = None,
    forecast_ids: Sequence[ForecastId] = (),
) -> TargetPortfolio:
    """Create a canonical target while preserving the existing JSON semantics."""
    normalized_weights = {
        _legacy_symbol(symbol): _legacy_float(value, field=f"weight for {symbol!r}")
        for symbol, value in weights.items()
    }
    if set(diagnostics) != _DIAGNOSTIC_KEYS:
        missing = sorted(_DIAGNOSTIC_KEYS - set(diagnostics))
        extra = sorted(set(diagnostics) - _DIAGNOSTIC_KEYS)
        raise ValueError(f"legacy diagnostics shape mismatch; missing={missing}, extra={extra}")
    diagnostic_weights = diagnostics["weights"]
    if not isinstance(diagnostic_weights, Mapping):
        raise ValueError("legacy diagnostic weights must be a mapping")
    checked_diagnostic_weights = {
        _legacy_symbol(symbol): _legacy_float(value, field=f"diagnostic weight for {symbol!r}")
        for symbol, value in diagnostic_weights.items()
    }
    if checked_diagnostic_weights != normalized_weights:
        raise ValueError("legacy diagnostic weights must equal top-level weights")
    normalized_weights = dict(sorted(normalized_weights.items()))
    if listings is None:
        listings = tuple(provisional_listing(symbol) for symbol in normalized_weights)
    else:
        listings = tuple(sorted(listings, key=lambda listing: listing.symbol))
    by_symbol = _listing_index(listings)
    if set(by_symbol) != set(normalized_weights):
        raise ValueError("legacy weights must exactly match listing symbols")

    def instrument_ids(key: str) -> tuple[InstrumentId, ...]:
        values = diagnostics[key]
        if not isinstance(values, list):
            raise ValueError(f"legacy diagnostic {key} must be a list")
        normalized = [_legacy_symbol(symbol) for symbol in values]
        unknown = set(normalized) - set(by_symbol)
        if unknown:
            raise ValueError(f"legacy diagnostic {key} contains unknown symbols: {sorted(unknown)}")
        return tuple(by_symbol[symbol].instrument_id for symbol in normalized)

    turnover = _legacy_float(diagnostics["turnover"], field="turnover")
    cash_weight = _legacy_float(diagnostics["cash_weight"], field="cash_weight")
    binding_constraints = diagnostics["binding_constraints"]
    if not isinstance(binding_constraints, list) or not all(
        isinstance(value, str) for value in binding_constraints
    ):
        raise ValueError("legacy diagnostic binding_constraints must be a list of strings")
    canonical_diagnostics = AllocationDiagnostics(
        turnover=turnover,
        cash_weight=cash_weight,
        active_forecasts=instrument_ids("active_forecasts"),
        abstentions=instrument_ids("abstentions"),
        binding_constraints=tuple(binding_constraints),
    )
    return TargetPortfolio(
        target_portfolio_id=context.target_portfolio_id,
        portfolio_id=context.portfolio_id,
        run_id=context.run_id,
        strategy_id=context.strategy_id,
        protocol_id=context.protocol_id,
        as_of=context.as_of,
        effective_at=context.effective_at,
        created_at=context.created_at,
        producer=context.producer,
        listings=tuple(listings),
        allocations=tuple(
            TargetAllocation(
                instrument_id=by_symbol[symbol].instrument_id,
                target_weight=weight,
            )
            for symbol, weight in normalized_weights.items()
        ),
        cash_weight=cash_weight,
        constraints=constraints,
        diagnostics=canonical_diagnostics,
        forecast_ids=tuple(sorted(forecast_ids)),
        provenance=context.provenance,
    )


def target_to_legacy_weights(target: TargetPortfolio) -> dict[str, object]:
    """Return the exact dictionary shape expected by ``PaperStore`` today."""
    by_id = {listing.instrument_id: listing.symbol for listing in target.listings}
    weights = {
        by_id[allocation.instrument_id]: allocation.target_weight
        for allocation in target.allocations
    }
    diagnostics = {
        "weights": dict(weights),
        "turnover": target.diagnostics.turnover,
        "cash_weight": target.diagnostics.cash_weight,
        "active_forecasts": [
            by_id[instrument_id] for instrument_id in target.diagnostics.active_forecasts
        ],
        "abstentions": [
            by_id[instrument_id] for instrument_id in target.diagnostics.abstentions
        ],
        "binding_constraints": list(target.diagnostics.binding_constraints),
    }
    return {"weights": weights, "diagnostics": diagnostics}
