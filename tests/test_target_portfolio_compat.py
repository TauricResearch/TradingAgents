"""Parity tests for the target-portfolio strangler seam."""

from dataclasses import asdict
from datetime import date, datetime, timezone

import pandas as pd
import pytest
from pydantic import ValidationError

from tradingagents.adapters.portfolio import LegacyOptimizerForecastWeightPolicy
from tradingagents.compat.portfolio import target_from_legacy_weights, target_to_legacy_weights
from tradingagents.domain.forecasts import ForecastEstimate, ForecastHorizon
from tradingagents.domain.ids import (
    ForecastId,
    ModelId,
    PortfolioId,
    ProtocolId,
    RunId,
    StrategyId,
    TargetPortfolioId,
)
from tradingagents.domain.instruments import provisional_listing
from tradingagents.domain.portfolios import (
    PortfolioConstraints,
    PortfolioMode,
    TargetContext,
)
from tradingagents.domain.time import AsOf
from tradingagents.formal_experiment import (
    FormalDecisionWindowExpiredError,
    _checked_before_open,
    _market_rows,
    _shuffle_forecasts,
    _target as formal_target,
    formal_decision_semantics,
    formal_trial_registration,
)
from tradingagents.portfolio_backtest import optimize_forecast_weights
from tradingagents.ports.portfolio import ForecastWeightPolicy
from tradingagents.research_protocol import GLOBAL_EVENT_V2_PROTOCOL, content_id


def _constraints() -> PortfolioConstraints:
    return PortfolioConstraints(
        mode=PortfolioMode.LONG_ONLY,
        gross_limit=1.0,
        max_weight=0.4,
        max_sector_weight=0.7,
        turnover_hurdle_bps=10.0,
        minimum_trade_weight=0.005,
    )


def _context() -> TargetContext:
    cutoff = datetime(2026, 8, 5, tzinfo=timezone.utc)
    return TargetContext(
        target_portfolio_id=TargetPortfolioId("target_test"),
        portfolio_id=PortfolioId("portfolio_test"),
        run_id=RunId("Run_MixedCase"),
        strategy_id=StrategyId("global_events_champion"),
        protocol_id=ProtocolId("protocol_test"),
        as_of=AsOf(
            decision_cutoff=cutoff,
            calendar="XNYS",
            entry_session=date(2026, 8, 6),
        ),
        effective_at=datetime(2026, 8, 6, 13, 30, tzinfo=timezone.utc),
        created_at=cutoff,
        producer="test-suite",
    )


def _diagnostics(
    weights: dict[str, float],
    *,
    turnover: float = 0.0,
    active_forecasts: list[str] | None = None,
    abstentions: list[str] | None = None,
    binding_constraints: list[str] | None = None,
) -> dict[str, object]:
    return {
        "weights": dict(weights),
        "turnover": turnover,
        "cash_weight": 1.0 - sum(weights.values()),
        "active_forecasts": active_forecasts or [],
        "abstentions": abstentions or [],
        "binding_constraints": binding_constraints or [],
    }


@pytest.mark.unit
def test_legacy_target_round_trip_is_lossless():
    weights = {"AAPL": 0.2, "MSFT": 0.3, "NVDA": 0.0}
    diagnostics = {
        "weights": dict(weights),
        "turnover": 0.4,
        "cash_weight": 0.5,
        "active_forecasts": ["MSFT", "AAPL"],
        "abstentions": ["NVDA"],
        "binding_constraints": ["max_weight"],
    }
    target = target_from_legacy_weights(
        weights=weights,
        diagnostics=diagnostics,
        constraints=_constraints(),
        context=_context(),
    )
    assert target_to_legacy_weights(target) == {
        "weights": weights,
        "diagnostics": diagnostics,
    }
    assert target.gross_exposure == pytest.approx(0.5)
    assert target.net_exposure == pytest.approx(0.5)
    assert target.run_id == "Run_MixedCase"


@pytest.mark.unit
def test_target_rejects_mismatched_universe_and_constraint_violations():
    context = _context()
    with pytest.raises(ValueError, match="exactly match listing symbols"):
        target_from_legacy_weights(
            weights={"AAPL": 0.2},
            diagnostics=_diagnostics({"AAPL": 0.2}),
            constraints=_constraints(),
            context=context,
            listings=(provisional_listing("MSFT"),),
        )
    with pytest.raises(ValidationError, match="max_weight"):
        target_from_legacy_weights(
            weights={"AAPL": 0.8},
            diagnostics=_diagnostics({"AAPL": 0.8}),
            constraints=_constraints(),
            context=context,
        )


@pytest.mark.unit
def test_legacy_optimizer_adapter_matches_existing_optimizer_exactly():
    listings = tuple(provisional_listing(symbol) for symbol in ("AAPL", "MSFT", "NVDA"))
    forecast_values = {
        "AAPL": (120.0, 0.7, 0.8, False),
        "MSFT": (5.0, 0.51, 0.5, False),
        "NVDA": (0.0, 0.5, 0.0, True),
    }
    forecasts = tuple(
        ForecastEstimate(
            forecast_id=ForecastId(f"forecast_{listing.symbol.lower()}"),
            instrument_id=listing.instrument_id,
            run_id=_context().run_id,
            protocol_id=_context().protocol_id,
            model_id=ModelId("model_fixture"),
            as_of=_context().as_of,
            horizon=ForecastHorizon.NEXT_OPEN_TO_OPEN,
            expected_excess_return_bps=forecast_values[listing.symbol][0],
            probability_positive=forecast_values[listing.symbol][1],
            confidence=forecast_values[listing.symbol][2],
            abstain=forecast_values[listing.symbol][3],
            rationale="fixture",
        )
        for listing in listings
    )
    by_symbol = {listing.symbol: listing.instrument_id for listing in listings}
    current_legacy = {"AAPL": 0.1, "MSFT": 0.1, "NVDA": 0.1}
    sectors_legacy = {"AAPL": "technology", "MSFT": "technology", "NVDA": "semiconductors"}
    rows = [
        {
            "ticker": listing.symbol,
            "expected_excess_return_bps": forecast.expected_excess_return_bps,
            "probability_positive": forecast.probability_positive,
            "confidence": forecast.confidence,
            "abstain": forecast.abstain,
            "event_ids": [],
            "rationale": forecast.rationale,
        }
        for listing, forecast in zip(listings, forecasts, strict=True)
    ]
    constraints = _constraints()
    expected = optimize_forecast_weights(
        rows,
        current_weights=current_legacy,
        sectors=sectors_legacy,
        gross_limit=constraints.gross_limit,
        max_weight=constraints.max_weight,
        max_sector_weight=constraints.max_sector_weight,
        turnover_hurdle_bps=constraints.turnover_hurdle_bps,
        minimum_trade_weight=constraints.minimum_trade_weight,
    )
    policy: ForecastWeightPolicy = LegacyOptimizerForecastWeightPolicy()
    actual = policy.allocate(
        forecasts=forecasts,
        current_weights={by_symbol[symbol]: value for symbol, value in current_legacy.items()},
        listings=listings,
        sectors={by_symbol[symbol]: value for symbol, value in sectors_legacy.items()},
        constraints=constraints,
        context=_context(),
    )
    assert target_to_legacy_weights(actual) == {
        "weights": expected.weights,
        "diagnostics": asdict(expected),
    }
    assert actual.forecast_ids == tuple(forecast.forecast_id for forecast in forecasts)


@pytest.mark.unit
def test_adapter_rejects_incomplete_cross_section():
    listing = provisional_listing("AAPL")
    with pytest.raises(ValueError, match="forecast cross-section"):
        LegacyOptimizerForecastWeightPolicy().allocate(
            forecasts=(),
            current_weights={listing.instrument_id: 0.0},
            listings=(listing,),
            sectors={listing.instrument_id: "technology"},
            constraints=_constraints(),
            context=_context(),
        )


@pytest.mark.unit
@pytest.mark.parametrize("mutation", ["missing", "extra", "mismatched_weights"])
def test_lossless_conversion_rejects_noncanonical_diagnostics(mutation):
    weights = {"AAPL": 0.2}
    diagnostics = _diagnostics(weights)
    if mutation == "missing":
        diagnostics.pop("turnover")
    elif mutation == "extra":
        diagnostics["extension"] = "silently dropping this would be lossy"
    else:
        diagnostics["weights"] = {"AAPL": 0.9}
    with pytest.raises(ValueError, match="shape mismatch|must equal"):
        target_from_legacy_weights(
            weights=weights,
            diagnostics=diagnostics,
            constraints=_constraints(),
            context=_context(),
        )


@pytest.mark.unit
def test_target_canonical_serialization_is_independent_of_weight_input_order():
    left_weights = {"MSFT": 0.3, "AAPL": 0.2}
    right_weights = {"AAPL": 0.2, "MSFT": 0.3}
    left = target_from_legacy_weights(
        weights=left_weights,
        diagnostics=_diagnostics(left_weights),
        constraints=_constraints(),
        context=_context(),
    )
    right = target_from_legacy_weights(
        weights=right_weights,
        diagnostics=_diagnostics(right_weights),
        constraints=_constraints(),
        context=_context(),
    )
    assert left.canonical_json() == right.canonical_json()


@pytest.mark.unit
@pytest.mark.parametrize("strategy", GLOBAL_EVENT_V2_PROTOCOL["strategies"])
def test_actual_formal_target_seam_preserves_every_strategy_payload(strategy):
    universe = ["AAPL", "MSFT"]
    current = dict.fromkeys(universe, 0.0)

    class Store:
        def latest_strategy_weights(self, run_id, requested_strategy, requested_universe):
            assert run_id == "Run_MixedCase"
            assert requested_strategy == strategy
            assert requested_universe == universe
            return dict(current)

    rows = [
        {
            "ticker": "AAPL",
            "expected_excess_return_bps": 100.0,
            "probability_positive": 0.7,
            "confidence": 0.8,
            "abstain": False,
            "event_ids": ["event_01"],
            "rationale": "positive fixture",
        },
        {
            "ticker": "MSFT",
            "expected_excess_return_bps": 0.0,
            "probability_positive": 0.5,
            "confidence": 0.0,
            "abstain": True,
            "event_ids": [],
            "rationale": "abstention fixture",
        },
    ]
    protocol = GLOBAL_EVENT_V2_PROTOCOL["portfolio"]
    expected_result = optimize_forecast_weights(
        rows,
        current_weights=current,
        sectors={
            ticker: GLOBAL_EVENT_V2_PROTOCOL["universe"]["sectors"][ticker]
            for ticker in universe
        },
        gross_limit=protocol["gross_limit"],
        max_weight=protocol["max_weight"],
        max_sector_weight=protocol["max_sector_weight"],
        turnover_hurdle_bps=protocol["turnover_hurdle_bps"],
        minimum_trade_weight=protocol["minimum_trade_weight"],
    )
    expected = {"weights": expected_result.weights, "diagnostics": asdict(expected_result)}
    cutoff = datetime(2026, 8, 5, tzinfo=timezone.utc)
    actual = formal_target(
        Store(),
        "Run_MixedCase",
        strategy,
        rows,
        universe,
        cutoff=cutoff,
        next_open=datetime(2026, 8, 6, 13, 30, tzinfo=timezone.utc),
        entry_date="2026-08-06",
        created_at=datetime(2026, 8, 5, 1, tzinfo=timezone.utc),
        model_id="Model_MixedCase",
    )
    assert actual == expected
    assert content_id(actual) == content_id(expected)


@pytest.mark.unit
def test_live_clock_fails_closed_when_work_crosses_the_next_open():
    next_open = datetime(2026, 8, 6, 13, 30, tzinfo=timezone.utc)
    readings = iter([
        next_open.replace(minute=29, second=59),
        next_open,
    ])
    def clock():
        return next(readings)

    assert _checked_before_open(clock, next_open, stage="target") < next_open
    with pytest.raises(FormalDecisionWindowExpiredError, match="retroactive"):
        _checked_before_open(clock, next_open, stage="persistence")


@pytest.mark.unit
def test_shuffled_control_rotates_the_complete_actionable_signal():
    rows = [
        {
            "ticker": "AAPL", "expected_excess_return_bps": 0.0,
            "probability_positive": 0.5, "confidence": 0.0,
            "abstain": True, "event_ids": [], "rationale": "neutral",
        },
        {
            "ticker": "MSFT", "expected_excess_return_bps": 200.0,
            "probability_positive": 0.7, "confidence": 0.8,
            "abstain": False, "event_ids": ["event_1"], "rationale": "active",
        },
    ]

    shuffled = {row["ticker"]: row for row in _shuffle_forecasts(rows)}

    assert shuffled["AAPL"]["expected_excess_return_bps"] == 200.0
    assert shuffled["AAPL"]["abstain"] is False
    assert shuffled["AAPL"]["event_ids"] == ["event_1"]
    assert shuffled["MSFT"]["expected_excess_return_bps"] == 0.0
    assert shuffled["MSFT"]["abstain"] is True
    assert shuffled["MSFT"]["event_ids"] == []


@pytest.mark.unit
def test_formal_decision_implementation_is_content_addressed():
    manifest = formal_decision_semantics()
    payload = {key: value for key, value in manifest.items() if key != "semantic_id"}

    assert manifest["semantic_id"] == content_id(payload, prefix="semantics_")
    assert manifest["semantic_id"] == GLOBAL_EVENT_V2_PROTOCOL["forecast"][
        "expected_decision_semantics_id"
    ]
    assert len(manifest["components"]) >= 10
    assert all(len(digest) == 64 for digest in manifest["components"].values())


@pytest.mark.unit
def test_formal_trial_registration_is_outcome_blind_and_content_addressed():
    outcome_semantics_id = "outcome_semantics_" + "5" * 64
    configuration_binding = {
        "configuration_manifest_id": "config_" + "1" * 24,
        "collector_configuration_id": "config_" + "2" * 24,
        "paper_decision_configuration_id": "config_" + "3" * 24,
        "paper_marker_configuration_id": "config_" + "4" * 24,
    }
    registration = formal_trial_registration(
        "confirmatory-1",
        formal_decision_semantics(),
        outcome_semantics_id=outcome_semantics_id,
        configuration_binding=configuration_binding,
    )
    payload = {
        key: value for key, value in registration.items() if key != "registration_id"
    }

    assert registration["registration_id"] == content_id(
        payload, prefix="registration_"
    )
    assert registration["registration_type"] == "confirmatory"
    assert registration["outcome_semantics_id"] == outcome_semantics_id
    assert registration["configuration_binding"] == configuration_binding
    assert registration["outcomes_accessed_before_registration"] is False
    assert registration["parent_run_id"] is None
    assert registration["registered_strategies"] == GLOBAL_EVENT_V2_PROTOCOL[
        "strategies"
    ]


@pytest.mark.unit
@pytest.mark.parametrize("timezone_name", [None, "America/New_York"])
def test_market_rows_compare_exchange_session_dates(monkeypatch, timezone_name):
    index = pd.DatetimeIndex(["2026-08-04", "2026-08-05", "2026-08-06"])
    if timezone_name:
        index = index.tz_localize(timezone_name)
    frame = pd.DataFrame(
        {"Open": [100.0, 101.0, 999.0], "Close": [100.0, 102.0, 999.0]},
        index=index,
    )
    monkeypatch.setattr(
        "tradingagents.formal_experiment.backtest._load_prices",
        lambda *_args, **_kwargs: frame,
    )

    inverse_vol, momentum, snapshots = _market_rows(["AAPL"], "2026-08-05")

    assert len(inverse_vol) == len(momentum) == 1
    assert snapshots["AAPL"] == [
        {"date": "2026-08-04", "open": 100.0, "close": 100.0},
        {"date": "2026-08-05", "open": 101.0, "close": 102.0},
    ]


@pytest.mark.unit
def test_target_rejects_listing_that_expires_before_effective_open():
    base = provisional_listing("AAPL")
    expired = type(base)(
        instrument_id=base.instrument_id,
        symbol=base.symbol,
        asset_class=base.asset_class,
        venue=base.venue,
        quote_currency=base.quote_currency,
        valid_to=datetime(2026, 8, 6, 13, 0, tzinfo=timezone.utc),
        id_scheme=base.id_scheme,
    )
    weights = {"AAPL": 0.2}
    with pytest.raises(ValidationError, match="expired when effective"):
        target_from_legacy_weights(
            weights=weights,
            diagnostics=_diagnostics(weights),
            constraints=_constraints(),
            context=_context(),
            listings=(expired,),
        )
