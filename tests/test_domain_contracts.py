"""Unit tests for the first architecture contract slice."""

from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from tradingagents.domain.contracts import canonical_json
from tradingagents.domain.ids import (
    InstrumentId,
    PortfolioId,
    ProtocolId,
    RunId,
    StrategyId,
    TargetPortfolioId,
)
from tradingagents.domain.instruments import ListingRef, provisional_listing
from tradingagents.domain.portfolios import (
    PortfolioConstraints,
    PortfolioMode,
    TargetAllocation,
    TargetContext,
)
from tradingagents.domain.time import AsOf, TimeRange


@pytest.mark.unit
def test_asof_requires_aware_time_and_normalizes_to_utc():
    with pytest.raises(ValidationError, match="timezone info"):
        AsOf(decision_cutoff=datetime(2026, 8, 5), calendar="XNYS")

    as_of = AsOf(
        decision_cutoff=datetime(2026, 8, 5, 2, tzinfo=timezone(timedelta(hours=2))),
        calendar=" xnys ",
        entry_session=date(2026, 8, 5),
    )
    assert as_of.decision_cutoff == datetime(2026, 8, 5, tzinfo=timezone.utc)
    assert as_of.calendar == "XNYS"
    assert as_of.admits_observed_at(as_of.decision_cutoff - timedelta(microseconds=1))
    assert not as_of.admits_observed_at(as_of.decision_cutoff)
    assert not as_of.admits_observed_at(as_of.decision_cutoff + timedelta(microseconds=1))


@pytest.mark.unit
def test_time_range_is_half_open_and_rejects_invalid_intervals():
    start = datetime(2026, 8, 5, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    interval = TimeRange(start=start, end=end)
    assert interval.contains(start)
    assert interval.contains(end - timedelta(microseconds=1))
    assert not interval.contains(end)
    with pytest.raises(ValidationError, match="start < end"):
        TimeRange(start=end, end=start)


@pytest.mark.unit
def test_provisional_listing_is_explicit_stable_and_symbol_canonical():
    left = provisional_listing(" aapl ")
    right = provisional_listing("AAPL")
    assert left == right
    assert left.symbol == "AAPL"
    assert left.instrument_id.startswith("instrument_")
    assert left.id_scheme == "provisional-v2-listing"

    with pytest.raises(ValidationError, match="valid_from < valid_to"):
        ListingRef(
            instrument_id=InstrumentId("instrument_example"),
            symbol="AAPL",
            id_scheme="test",
            valid_from=datetime(2026, 8, 6, tzinfo=timezone.utc),
            valid_to=datetime(2026, 8, 5, tzinfo=timezone.utc),
        )


@pytest.mark.unit
def test_contracts_are_frozen_strict_and_deterministically_serialized():
    allocation = TargetAllocation(
        instrument_id=InstrumentId("Instrument_MixedCase"), target_weight=0.125
    )
    assert allocation.instrument_id == "Instrument_MixedCase"
    assert '"target_weight":0.125' in allocation.canonical_json()
    with pytest.raises(ValidationError, match="Extra inputs"):
        TargetAllocation(
            instrument_id="instrument_example", target_weight=0.1, unexpected=True
        )
    with pytest.raises(ValidationError, match="valid number"):
        TargetAllocation(instrument_id="instrument_example", target_weight=True)
    with pytest.raises(ValidationError, match="valid number"):
        TargetAllocation(instrument_id="instrument_example", target_weight="0.1")
    with pytest.raises(ValidationError, match="finite"):
        TargetAllocation(instrument_id="instrument_example", target_weight=float("nan"))
    spaced = TargetAllocation(instrument_id=" instrument_example ", target_weight=0.1)
    assert spaced.instrument_id == " instrument_example "
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})
    with pytest.raises(TypeError, match="unordered container"):
        canonical_json({"values": {"a", "b"}})


@pytest.mark.unit
def test_portfolio_contract_rejects_numeric_coercion_and_invalid_time_order():
    with pytest.raises(ValidationError, match="valid number"):
        PortfolioConstraints(
            mode=PortfolioMode.LONG_ONLY,
            gross_limit=True,
            max_weight=0.1,
            max_sector_weight=0.3,
            turnover_hurdle_bps=10.0,
            minimum_trade_weight=0.005,
        )
    cutoff = datetime(2026, 8, 5, tzinfo=timezone.utc)
    with pytest.raises(ValidationError, match="creation cannot precede"):
        TargetContext(
            target_portfolio_id=TargetPortfolioId("Target_MixedCase"),
            portfolio_id=PortfolioId("Portfolio_MixedCase"),
            run_id=RunId("Run_MixedCase"),
            strategy_id=StrategyId("Strategy_MixedCase"),
            protocol_id=ProtocolId("Protocol_MixedCase"),
            as_of=AsOf(
                decision_cutoff=cutoff,
                calendar="XNYS",
                entry_session=date(2026, 8, 6),
            ),
            created_at=cutoff - timedelta(microseconds=1),
            effective_at=cutoff + timedelta(hours=1),
            producer="test",
        )
    with pytest.raises(ValidationError, match="does not match its entry session"):
        TargetContext(
            target_portfolio_id=TargetPortfolioId("Target_MixedCase"),
            portfolio_id=PortfolioId("Portfolio_MixedCase"),
            run_id=RunId("Run_MixedCase"),
            strategy_id=StrategyId("Strategy_MixedCase"),
            protocol_id=ProtocolId("Protocol_MixedCase"),
            as_of=AsOf(
                decision_cutoff=cutoff,
                calendar="XNYS",
                entry_session=date(2026, 8, 7),
            ),
            created_at=cutoff,
            effective_at=cutoff + timedelta(days=1, hours=13),
            producer="test",
        )
