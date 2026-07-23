"""Strategy SDK core types (roadmap P0.1 / architecture track T1):
order-intent validation, the parameter space (resolve/grid/sample/schema),
and the Strategy protocol's runtime-checkability."""

import random

import pytest

from tradingagents.pro.backtest import (
    BracketIntent,
    OrderIntent,
    Param,
    ParamSpace,
    Strategy,
    StrategyContext,
)
from tradingagents.pro.backtest.strategy import Fill

# --- OrderIntent validation ---------------------------------------------------


class TestOrderIntent:
    def test_market_intent_with_risk_pct(self):
        intent = OrderIntent(kind="market", side="BUY", risk_pct=1.0)
        assert intent.risk_pct == 1.0 and intent.quantity is None

    def test_exactly_one_sizing_method_required(self):
        with pytest.raises(ValueError, match="exactly one"):
            OrderIntent(kind="market", side="BUY")  # neither
        with pytest.raises(ValueError, match="exactly one"):
            OrderIntent(kind="market", side="BUY", quantity=5, risk_pct=1.0)  # both

    def test_bad_kind_and_side_rejected(self):
        with pytest.raises(ValueError, match="kind must be"):
            OrderIntent(kind="teleport", side="BUY", quantity=1)
        with pytest.raises(ValueError, match="side must be"):
            OrderIntent(kind="market", side="LONG", quantity=1)

    def test_limit_and_stop_prices_required_by_kind(self):
        with pytest.raises(ValueError, match="limit_price"):
            OrderIntent(kind="limit", side="BUY", quantity=1)
        with pytest.raises(ValueError, match="stop_price"):
            OrderIntent(kind="stop_entry", side="BUY", quantity=1)
        # stop_limit needs both
        ok = OrderIntent(kind="stop_limit", side="SELL", quantity=1,
                         limit_price=99.0, stop_price=100.0)
        assert ok.limit_price == 99.0 and ok.stop_price == 100.0

    def test_risk_pct_and_quantity_bounds(self):
        with pytest.raises(ValueError, match="risk_pct"):
            OrderIntent(kind="market", side="BUY", risk_pct=0)
        with pytest.raises(ValueError, match="quantity must be positive"):
            OrderIntent(kind="market", side="BUY", quantity=-1)

    def test_bracket_attaches(self):
        intent = OrderIntent(
            kind="market", side="BUY", risk_pct=1.0,
            bracket=BracketIntent(stop_loss=95.0,
                                  take_profits=((102.5, 0.5), (117.5, 0.5))))
        assert intent.bracket.stop_loss == 95.0
        assert len(intent.bracket.take_profits) == 2


# --- Param / ParamSpace -------------------------------------------------------


class TestParam:
    def test_numeric_needs_bounds_categorical_needs_choices(self):
        with pytest.raises(ValueError, match="needs low and high"):
            Param("x", "float")
        with pytest.raises(ValueError, match="needs choices"):
            Param("x", "categorical")

    def test_contains_respects_domain_and_type(self):
        f = Param("nb", "float", 0.2, 0.5, default=0.34)
        assert f.contains(0.34) and not f.contains(0.6)
        i = Param("adx", "int", 12, 25, default=18)
        assert i.contains(18) and not i.contains(18.5) and not i.contains(30)
        c = Param("ladder", "categorical", choices=("a", "b"), default="a")
        assert c.contains("b") and not c.contains("c")

    def test_bool_is_not_a_valid_number(self):
        # guard against True==1 sneaking through numeric domains
        assert not Param("adx", "int", 0, 5).contains(True)

    def test_default_must_be_a_choice(self):
        with pytest.raises(ValueError, match="default"):
            Param("x", "categorical", choices=("a", "b"), default="z")

    def test_grid_values(self):
        assert Param("adx", "int", 12, 14).grid_values() == [12, 13, 14]
        assert Param("m", "float", 1.0, 2.0, step=0.5).grid_values() == [1.0, 1.5, 2.0]
        assert Param("c", "categorical", choices=("x", "y")).grid_values() == ["x", "y"]
        # stepless float collapses to its default (can't enumerate a continuum)
        assert Param("f", "float", 0.0, 1.0, default=0.3).grid_values() == [0.3]


class TestParamSpace:
    def _space(self):
        return ParamSpace(
            Param("neutral_band", "float", 0.2, 0.5, step=0.1, default=0.34),
            Param("chop_adx", "int", 12, 14, default=18),
            Param("ladder", "categorical",
                  choices=("0.5/3.5", "1.0/3.0"), default="0.5/3.5"),
        )

    def test_rejects_duplicate_names(self):
        with pytest.raises(ValueError, match="duplicate"):
            ParamSpace(Param("a", "int", 0, 1), Param("a", "int", 0, 1))

    def test_defaults(self):
        assert self._space().defaults() == {
            "neutral_band": 0.34, "chop_adx": 18, "ladder": "0.5/3.5"}

    def test_resolve_merges_and_validates(self):
        space = self._space()
        resolved = space.resolve({"chop_adx": 13})
        assert resolved["chop_adx"] == 13 and resolved["neutral_band"] == 0.34
        with pytest.raises(ValueError, match="unknown parameter"):
            space.resolve({"nope": 1})
        with pytest.raises(ValueError, match="outside declared domain"):
            space.resolve({"chop_adx": 99})

    def test_grid_is_full_cartesian_product(self):
        # neutral_band: [0.2,0.3,0.4,0.5] × chop_adx: [12,13,14] × ladder: [2]
        grid = list(self._space().grid())
        assert len(grid) == 4 * 3 * 2
        assert all(g.keys() == {"neutral_band", "chop_adx", "ladder"} for g in grid)
        assert all(self._space().resolve(g) == g for g in grid)  # every point valid

    def test_sample_is_in_domain_and_seeded_deterministic(self):
        space = self._space()
        a = space.sample(random.Random(7))
        b = space.sample(random.Random(7))
        assert a == b  # deterministic given a seed (replay requirement)
        assert space.resolve(a) == a  # a draw is always in-domain

    def test_schema_serializes_every_param(self):
        schema = self._space().schema()
        assert [s["name"] for s in schema] == ["neutral_band", "chop_adx", "ladder"]
        assert schema[2]["choices"] == ["0.5/3.5", "1.0/3.0"]


# --- Strategy protocol --------------------------------------------------------


class _MinimalStrategy:
    id = "test_v1"
    params = ParamSpace(Param("k", "int", 1, 10, default=3))

    def __init__(self):
        self.fills = []

    def on_start(self, ctx): ...
    def on_bar(self, ctx):
        return [OrderIntent(kind="market", side="BUY", risk_pct=ctx.params["k"] / 10)]
    def on_fill(self, fill):
        self.fills.append(fill)
    def on_stop(self, ctx): ...


class TestStrategyProtocol:
    def test_minimal_strategy_satisfies_protocol(self):
        assert isinstance(_MinimalStrategy(), Strategy)

    def test_on_bar_emits_valid_intents_from_params(self):
        strat = _MinimalStrategy()
        ctx = StrategyContext(snapshot=None, equity=100_000.0,
                              params=strat.params.defaults())
        intents = strat.on_bar(ctx)
        assert len(intents) == 1 and intents[0].risk_pct == pytest.approx(0.3)

    def test_on_fill_receives_fills(self):
        from datetime import datetime, timezone
        strat = _MinimalStrategy()
        strat.on_fill(Fill(order_tag="t", symbol="BTC-USD", side="BUY",
                           quantity=1.0, price=100.0,
                           at=datetime.now(timezone.utc), is_entry=True))
        assert len(strat.fills) == 1 and strat.fills[0].is_entry

    def test_incomplete_object_is_not_a_strategy(self):
        class NotAStrategy:
            id = "x"
        assert not isinstance(NotAStrategy(), Strategy)
