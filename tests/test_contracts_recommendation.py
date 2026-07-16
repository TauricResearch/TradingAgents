"""Contract tests: TradeRecommendation geometry and computed risk/reward."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from tradingagents.contracts import (
    AgentEvidence,
    AgentTeam,
    AgentVote,
    AssetClass,
    DataRef,
    Direction,
    HistoricalAnalog,
    MarketRegime,
    PositionSize,
    SourceAttribution,
    SourceType,
    TakeProfitLevel,
    Timeframe,
    TradeAction,
    TradeRecommendation,
    VoteBreakdown,
)


def make_evidence() -> AgentEvidence:
    return AgentEvidence(
        agent_id="trend_agent",
        team=AgentTeam.TECHNICAL,
        claim="Price holds above rising EMA-200 on D1; uptrend intact.",
        direction=Direction.BULLISH,
        confidence=70,
        timeframe=Timeframe.D1,
        data_refs=[DataRef(name="EMA_200", value=2315.0, source="indicator_engine")],
        sources=[
            SourceAttribution(
                id="indicator_engine", type=SourceType.INDICATOR, name="Indicator engine"
            )
        ],
    )


def make_votes() -> VoteBreakdown:
    return VoteBreakdown(
        votes=[
            AgentVote(agent_id="judge", vote=TradeAction.BUY, confidence=72),
            AgentVote(agent_id="risk_lead", vote=TradeAction.BUY, confidence=60),
            AgentVote(agent_id="macro_bear", vote=TradeAction.HOLD, confidence=55),
        ]
    )


def make_buy(**overrides) -> TradeRecommendation:
    fields = {
        "symbol": "XAUUSD",
        "asset": AssetClass.GOLD,
        "action": TradeAction.BUY,
        "confidence": 72,
        "entry_price": 2400.0,
        "stop_loss": 2380.0,
        "take_profits": [
            TakeProfitLevel(price=2420.0, size_fraction=0.5),
            TakeProfitLevel(price=2440.0, size_fraction=0.5),
        ],
        "position_size": PositionSize(quantity=1.0, pct_of_equity=2.0),
        "market_regime": MarketRegime.TRENDING_UP,
        "evidence": [make_evidence()],
        "vote_breakdown": make_votes(),
    }
    fields.update(overrides)
    return TradeRecommendation(**fields)


def test_valid_buy_round_trips_and_computes_risk_reward():
    rec = make_buy()
    # risk = 20; reward = 0.5*20 + 0.5*40 = 30 -> R:R 1.5
    assert rec.risk_reward == 1.5
    restored = TradeRecommendation.model_validate_json(rec.model_dump_json())
    assert restored.risk_reward == 1.5
    assert restored.action is TradeAction.BUY


def test_inconsistent_risk_reward_rejected():
    with pytest.raises(ValidationError, match="derived, not asserted"):
        make_buy(risk_reward=99.0)


def test_matching_risk_reward_accepted_for_round_trip():
    assert make_buy(risk_reward=1.5).risk_reward == 1.5


def test_partial_ladder_normalizes_fractions():
    rec = make_buy(
        take_profits=[
            TakeProfitLevel(price=2420.0, size_fraction=0.5),
            TakeProfitLevel(price=2440.0, size_fraction=0.25),
        ]
    )
    # weights 2/3 and 1/3: reward = 20*2/3 + 40*1/3 = 26.667 -> R:R 1.3333
    assert rec.risk_reward == pytest.approx(1.3333, abs=1e-4)


def test_buy_with_stop_above_entry_rejected():
    with pytest.raises(ValidationError, match="stop_loss < entry_price"):
        make_buy(stop_loss=2410.0)


def test_buy_with_take_profit_below_entry_rejected():
    with pytest.raises(ValidationError, match="above entry_price"):
        make_buy(take_profits=[TakeProfitLevel(price=2390.0, size_fraction=1.0)])


def test_buy_ladder_must_ascend():
    with pytest.raises(ValidationError, match="strictly ascending"):
        make_buy(
            take_profits=[
                TakeProfitLevel(price=2440.0, size_fraction=0.5),
                TakeProfitLevel(price=2420.0, size_fraction=0.5),
            ]
        )


def test_ladder_fractions_must_not_exceed_one():
    with pytest.raises(ValidationError, match="sum"):
        make_buy(
            take_profits=[
                TakeProfitLevel(price=2420.0, size_fraction=0.7),
                TakeProfitLevel(price=2440.0, size_fraction=0.7),
            ]
        )


def test_buy_without_levels_rejected():
    with pytest.raises(ValidationError, match="requires entry, stop"):
        make_buy(entry_price=None, stop_loss=None, take_profits=[])


def test_valid_sell_geometry():
    rec = make_buy(
        symbol="BTC-USD",
        asset=AssetClass.BITCOIN,
        action=TradeAction.SELL,
        entry_price=60000.0,
        stop_loss=61200.0,
        take_profits=[
            TakeProfitLevel(price=58800.0, size_fraction=0.5),
            TakeProfitLevel(price=57600.0, size_fraction=0.5),
        ],
    )
    # risk = 1200; reward = 0.5*1200 + 0.5*2400 = 1800 -> 1.5
    assert rec.risk_reward == 1.5


def test_sell_ladder_must_descend():
    with pytest.raises(ValidationError, match="strictly descending"):
        make_buy(
            action=TradeAction.SELL,
            entry_price=60000.0,
            stop_loss=61200.0,
            take_profits=[
                TakeProfitLevel(price=57600.0, size_fraction=0.5),
                TakeProfitLevel(price=58800.0, size_fraction=0.5),
            ],
        )


def make_sell(**overrides) -> TradeRecommendation:
    fields = {
        "action": TradeAction.SELL,
        "entry_price": 4037.27,
        "stop_loss": 4049.88,
        "take_profits": [
            TakeProfitLevel(price=4011.99, size_fraction=0.5),
            TakeProfitLevel(price=3986.71, size_fraction=0.5),
        ],
    }
    fields.update(overrides)
    return make_buy(**fields)


def test_sell_stop_within_invalidation_buffer_accepted():
    # invalidation 4046.72, stop 3.16 beyond it; distance to entry 9.45 ->
    # allowed overshoot max(0.25*9.45, 0.001*4037.27) = 4.04 >= 3.16
    rec = make_sell(invalidation_price=4046.72)
    assert rec.invalidation_price == 4046.72


def test_sell_stop_beyond_invalidation_rejected():
    # the review's live finding: stop 4062.55 parked 15.83 beyond the
    # stated thesis-death level 4046.72 — the trade outlives its thesis
    with pytest.raises(ValidationError, match="outlive its own thesis"):
        make_sell(stop_loss=4062.55, invalidation_price=4046.72)


def test_sell_invalidation_below_entry_rejected():
    with pytest.raises(ValidationError, match="above entry_price"):
        make_sell(invalidation_price=4020.0)


def test_buy_stop_within_invalidation_buffer_accepted():
    # invalidation 2385, stop 2382.5: overshoot 2.5 <= max(0.25*15, 2.4)
    rec = make_buy(stop_loss=2382.5, invalidation_price=2385.0)
    assert rec.invalidation_price == 2385.0


def test_buy_stop_beyond_invalidation_rejected():
    with pytest.raises(ValidationError, match="outlive its own thesis"):
        make_buy(stop_loss=2380.0, invalidation_price=2395.0)


def test_buy_invalidation_above_entry_rejected():
    with pytest.raises(ValidationError, match="below entry_price"):
        make_buy(invalidation_price=2410.0)


def test_hold_with_invalidation_price_rejected():
    with pytest.raises(ValidationError, match="invalidation_price"):
        make_buy(
            action=TradeAction.HOLD,
            entry_price=None,
            stop_loss=None,
            take_profits=[],
            position_size=PositionSize(quantity=0),
            invalidation_price=2385.0,
        )


def test_hold_carries_no_levels_and_no_risk_reward():
    rec = make_buy(
        action=TradeAction.HOLD,
        entry_price=None,
        stop_loss=None,
        take_profits=[],
        position_size=PositionSize(quantity=0),
    )
    assert rec.risk_reward is None


def test_hold_with_entry_price_rejected():
    with pytest.raises(ValidationError, match="HOLD must not carry"):
        make_buy(
            action=TradeAction.HOLD,
            stop_loss=None,
            take_profits=[],
            position_size=PositionSize(quantity=0),
        )


def test_hold_with_nonzero_quantity_rejected():
    with pytest.raises(ValidationError, match="quantity == 0"):
        make_buy(
            action=TradeAction.HOLD,
            entry_price=None,
            stop_loss=None,
            take_profits=[],
            position_size=PositionSize(quantity=1.0),
        )


def test_recommendation_requires_evidence():
    with pytest.raises(ValidationError):
        make_buy(evidence=[])


def test_vote_tally():
    tally = make_votes().tally()
    assert tally[TradeAction.BUY] == 2
    assert tally[TradeAction.HOLD] == 1
    assert tally[TradeAction.SELL] == 0


def test_historical_analog_period_ordering_enforced():
    with pytest.raises(ValidationError, match="precedes"):
        HistoricalAnalog(
            description="2020 March liquidity crunch",
            period_start=datetime(2020, 3, 20, tzinfo=timezone.utc),
            period_end=datetime(2020, 3, 1, tzinfo=timezone.utc),
            similarity=0.8,
            outcome="V-shaped recovery after Fed intervention",
        )
