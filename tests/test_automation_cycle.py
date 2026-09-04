import json
import sqlite3
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from tradingagents.automation import AutomationCycleService, AutomationSettings
from tradingagents.automation_state import AutomationState
from tradingagents.execution import (
    LIVE_ACKNOWLEDGMENT,
    LIVE_OPTIONS_ACKNOWLEDGMENT,
    AccountSnapshot,
    AlpacaBroker,
    AssetInfo,
)
from tradingagents.options import (
    EquityPosition,
    OptionContract,
    OptionOpenOrder,
    OptionPosition,
)
from tradingagents.risk import RiskScaleResult, close_returns, forecast_volatility

NOW = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)
RATINGS = {
    "AAPL": "Buy",
    "MSFT": "Overweight",
    "NVDA": "Hold",
    "AMZN": "Buy",
    "META": "Sell",
    "GOOG": "Underweight",
    "TSLA": "Sell",
    "BTC-USD": "Buy",
    "ETH-USD": "Overweight",
}


class FakeGraph:
    def __init__(self, ratings, failures, calls):
        self.ratings = ratings
        self.failures = failures
        self.calls = calls

    def propagate(self, symbol, trade_date, asset_type="stock"):
        self.calls.append((symbol, trade_date, asset_type))
        if symbol in self.failures:
            raise RuntimeError(f"analysis failed for {symbol}")
        return {"final_trade_decision": self.ratings[symbol]}, self.ratings[symbol]

    def save_reports(self, final_state, symbol, save_path=None):
        return Path(f"/reports/{symbol}.md")


class FakeBroker:
    def __init__(self):
        self.cash = Decimal("10000")
        self.buying_power = Decimal("200000")
        self.market_open = True
        self.now = NOW
        self.clock_times = []
        self.trading_blocked = False
        self.status = "ACTIVE"
        self.position_values = {}
        self.open_exposure = {}
        self.shortable = {}
        self.read_failure = None
        self.submit_failures = set()
        self.submitted = []
        self.submit_attempts = []
        self.order_lookups = {}
        self.lookup_calls = []
        self.lookup_failure = False
        self.reads = []
        self.equity = Decimal("100000")
        self.options_buying_power = Decimal("100000")
        self.equity_lots = ()
        self.option_positions = ()
        self.option_orders = ()
        self.option_contract_values = {}
        self.close_history = _aligned_history(Decimal("0.005"))
        self.daily_close_calls = []
        self.submitted_options = []
        self.cancelled_options = []
        self.cancel_failure = False
        self.option_prepare_failures = set()
        self.option_failure = None
        self.entry_chain_failure = False
        self.latest_prices = {}
        self.exact_option_contract_values = {}

    def broker_time(self):
        self.reads.append("broker_time")
        if self.clock_times:
            self.now = self.clock_times.pop(0)
        return self.now

    def equity_market_is_open(self):
        self.reads.append("market")
        return self.market_open

    def account(self):
        self.reads.append("account")
        if self.read_failure == "account":
            raise RuntimeError("account unavailable")
        return AccountSnapshot(
            self.cash,
            self.buying_power,
            self.trading_blocked,
            self.status,
            self.equity,
            self.options_buying_power,
        )

    def positions(self):
        self.reads.append("positions")
        if self.read_failure == "positions":
            raise RuntimeError("positions unavailable")
        return dict(self.position_values)

    def open_order_exposure(self, prices):
        self.reads.append("open_orders")
        if self.read_failure == "open_orders":
            raise RuntimeError("open orders unavailable")
        return dict(self.open_exposure)

    def latest_price(self, symbol):
        self.reads.append(f"price:{symbol}")
        if self.read_failure == f"price:{symbol}":
            raise RuntimeError(f"price unavailable for {symbol}")
        equity = next((lot for lot in self.equity_lots if lot.symbol == symbol), None)
        if equity is not None:
            return equity.current_price
        return self.latest_prices.get(symbol, Decimal("100"))

    def asset(self, symbol):
        self.reads.append(f"asset:{symbol}")
        asset_class = "crypto" if symbol.endswith("-USD") else "us_equity"
        sdk_symbol = f"{symbol[:-4]}/USD" if asset_class == "crypto" else symbol
        return AssetInfo(
            sdk_symbol,
            asset_class,
            True,
            self.shortable.get(symbol, asset_class != "crypto"),
            True,
            Decimal("0.001"),
            Decimal("0.001"),
        )

    def prepare_order(self, intent, asset, price, cycle_id):
        return AlpacaBroker.prepare_order(self, intent, asset, price, cycle_id)

    def submit_idempotent(self, spec):
        self.submit_attempts.append(spec.symbol)
        if spec.symbol in self.submit_failures:
            raise TimeoutError(f"submission uncertain for {spec.symbol}")
        self.submitted.append(spec)
        return f"order-{spec.symbol}"

    def find_order_by_client_id(self, client_order_id):
        self.lookup_calls.append(client_order_id)
        if self.lookup_failure:
            raise RuntimeError("order lookup unavailable")
        return self.order_lookups.get(client_order_id)

    def wheel_positions_and_orders(self):
        if self.option_failure in {"option_positions", "option_orders", "option_delta"}:
            raise RuntimeError(f"{self.option_failure} unavailable")
        return self.equity_lots, self.option_positions, self.option_orders

    def option_contracts(self, underlying, kind, now):
        if self.option_failure == "option_quote" or self.entry_chain_failure:
            raise RuntimeError(f"{self.option_failure} unavailable")
        return self.option_contract_values.get(underlying, ())

    def option_contract(self, symbol, now):
        if self.option_failure == "option_quote":
            raise RuntimeError("option_quote unavailable")
        return self.exact_option_contract_values[symbol]

    def daily_closes(self, symbols, limit=61):
        self.daily_close_calls.append(tuple(symbols))
        if self.option_failure == "daily_closes":
            raise RuntimeError("daily closes unavailable")
        return self.close_history

    def prepare_option_order(self, intent, cycle_id):
        if intent.underlying in self.option_prepare_failures:
            raise ValueError(f"cannot prepare {intent.underlying}")
        return AlpacaBroker.prepare_option_order(self, intent, cycle_id)

    def submit_option_idempotent(self, spec):
        self.submitted_options.append(spec)
        return f"option-{spec.symbol}"

    def cancel_stale_option_order(self, order_id, client_order_id):
        self.cancelled_options.append((order_id, client_order_id))
        if self.cancel_failure:
            raise RuntimeError("cancellation failed")


def _eligible_put(symbol, now):
    return OptionContract(
        symbol=f"{symbol}260904P00300000",
        underlying=symbol,
        kind="put",
        strike=Decimal("300"),
        expiration=date(2026, 9, 4),
        delta=Decimal("-0.20"),
        bid=Decimal("3.00"),
        ask=Decimal("3.20"),
        open_interest=Decimal("500"),
        quote_time=now,
    )


def _opening_put(symbol="AAPL"):
    option_symbol = f"{symbol}260904P00010000"
    order = OptionOpenOrder(
        option_symbol,
        symbol,
        "put",
        "sell_to_open",
        Decimal("1"),
        Decimal("0"),
        Decimal("10"),
    )
    contract = OptionContract(
        option_symbol,
        symbol,
        "put",
        Decimal("10"),
        date(2026, 9, 4),
        Decimal("-1"),
        Decimal("1"),
        Decimal("1.10"),
        Decimal("500"),
        NOW,
    )
    return order, contract


def _quote_for_order(order, delta=Decimal("0.20")):
    return OptionContract(
        order.symbol,
        order.underlying,
        order.kind,
        order.strike,
        date(2026, 10, 2),
        delta,
        Decimal("3"),
        Decimal("3.20"),
        Decimal("500"),
        NOW,
    )


def _offsetting_opening_puts():
    buy_order, buy_contract = _opening_put()
    buy_order = replace(
        buy_order,
        symbol="AAPL260904P00020000",
        position_intent="buy_to_open",
        strike=Decimal("20"),
    )
    buy_contract = replace(
        buy_contract,
        symbol=buy_order.symbol,
        strike=Decimal("20"),
        delta=Decimal("-0.50"),
    )
    sell_order, sell_contract = _opening_put()
    sell_contract = replace(sell_contract, delta=Decimal("-0.50"))
    return (buy_order, sell_order), (buy_contract, sell_contract)


def _offsetting_held_options():
    positions = (
        OptionPosition(
            "AAPL260904C00100000",
            "AAPL",
            "call",
            Decimal("1"),
            Decimal("3"),
            Decimal("0.50"),
        ),
        OptionPosition(
            "AAPL260904P00100000",
            "AAPL",
            "put",
            Decimal("1"),
            Decimal("3"),
            Decimal("-0.50"),
        ),
    )
    contracts = tuple(
        OptionContract(
            position.symbol,
            position.underlying,
            position.kind,
            Decimal("100"),
            date(2026, 9, 4),
            position.delta,
            Decimal("2"),
            Decimal("2.20"),
            Decimal("500"),
            NOW,
        )
        for position in positions
    )
    return positions, contracts


def _aligned_history(change):
    start = date(2026, 7, 1)
    result = {}
    for symbol in ("AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOG", "TSLA"):
        magnitude = Decimal(
            str(("AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOG", "TSLA").index(symbol) + 1)
        )
        price = Decimal("100")
        rows = [(start, price)]
        for index in range(40):
            signed = change * magnitude if index % 2 == 0 else -change * magnitude
            price *= Decimal("1") + signed
            rows.append((start + timedelta(days=index + 1), price))
        result[symbol] = tuple(rows)
    return result


def _settings(tmp_path, **overrides):
    values = {
        "watchlist": ("AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOG", "TSLA"),
        "batch_size": 3,
        "analysis_interval_minutes": 30,
        "position_interval_minutes": 30,
        "max_cash_allocation": 0.30,
        "decision_max_age_minutes": 120,
        "rebalance_threshold_usd": 10.0,
        "state_path": tmp_path / "state.db",
        "auto_execute": False,
        "alpaca_mode": "paper",
        "live_trading_ack": "",
        "options_enabled": False,
        "options_auto_execute": False,
        "options_max_equity_fraction": 0.20,
        "options_entry_time_et": "10:00",
        "options_earnings_path": tmp_path / "earnings.json",
        "live_options_ack": "",
    }
    values.update(overrides)
    return AutomationSettings(**values)


class ServiceHarness:
    def __init__(self, settings, state, broker, ratings=None):
        self.settings = settings
        self.state = state
        self.broker = broker
        self.graph_failures = set()
        self.graph_calls = []
        self.factory_calls = []
        self.factory_failures_remaining = 0
        self.ratings = dict(RATINGS if ratings is None else ratings)

        def graph_factory(analysts):
            self.factory_calls.append(tuple(analysts))
            if self.factory_failures_remaining:
                self.factory_failures_remaining -= 1
                raise RuntimeError("graph construction failed")
            return FakeGraph(self.ratings, self.graph_failures, self.graph_calls)

        self.service = AutomationCycleService(settings, state, broker, graph_factory)

    def run_analysis_cycle(self, due_time):
        return self.service.run_analysis_cycle(due_time)

    def track_positions(self, due_time):
        return self.service.track_positions(due_time)

    def manage_options(self, due_time):
        self.service.settings = self.settings
        return self.service.manage_options(due_time)

    def seed_all_decisions(self, analyzed_at=NOW, omitted=()):
        for symbol in self.settings.watchlist:
            if symbol not in omitted:
                self.state.save_decision(
                    symbol,
                    self.ratings[symbol],
                    analyzed_at,
                    analyzed_at.date().isoformat(),
                    f"/reports/{symbol}.md",
                )


@pytest.fixture
def service(tmp_path):
    state = AutomationState(tmp_path / "state.db")
    settings = _settings(tmp_path)
    settings.options_earnings_path.write_text(
        json.dumps(
            {
                "source": "Wall Street Horizon",
                "retrieved_at": NOW.isoformat(),
                "symbols": dict.fromkeys(settings.watchlist, "2026-12-11"),
            }
        )
    )
    yield ServiceHarness(settings, state, FakeBroker())
    state.close()


@pytest.fixture
def warmed_service(service):
    service.seed_all_decisions()
    return service


def test_reserved_covered_shares_cannot_be_sold(warmed_service):
    warmed_service.settings = replace(warmed_service.settings, options_enabled=True)
    warmed_service.service.settings = warmed_service.settings
    warmed_service.broker.position_values = {"AAPL": Decimal("40000")}
    warmed_service.broker.equity_lots = (
        EquityPosition("AAPL", Decimal("100"), Decimal("300"), Decimal("320")),
    )
    warmed_service.broker.option_orders = (
        OptionOpenOrder(
            "AAPL261002C00350000",
            "AAPL",
            "call",
            "sell_to_open",
            Decimal("1"),
            Decimal("0"),
            Decimal("350"),
        ),
    )
    order = warmed_service.broker.option_orders[0]
    warmed_service.broker.exact_option_contract_values[order.symbol] = _quote_for_order(order)
    warmed_service.ratings["AAPL"] = "Sell"
    result = warmed_service.run_analysis_cycle(NOW)
    aapl = next(intent for intent in result.order_intents if intent.symbol == "AAPL")
    assert aapl.side == "sell"
    assert aapl.target_notional == Decimal("32000")


def test_infeasible_covered_share_floor_suppresses_equity_submission(warmed_service):
    warmed_service.settings = replace(
        warmed_service.settings,
        options_enabled=True,
        auto_execute=True,
    )
    warmed_service.service.settings = warmed_service.settings
    warmed_service.broker.equity = Decimal("10000")
    warmed_service.broker.position_values = {"AAPL": Decimal("32000")}
    warmed_service.broker.equity_lots = (
        EquityPosition("AAPL", Decimal("100"), Decimal("300"), Decimal("320")),
    )
    warmed_service.broker.option_orders = (
        OptionOpenOrder(
            "AAPL261002C00350000",
            "AAPL",
            "call",
            "sell_to_open",
            Decimal("1"),
            Decimal("0"),
            Decimal("350"),
        ),
    )
    order = warmed_service.broker.option_orders[0]
    warmed_service.broker.exact_option_contract_values[order.symbol] = _quote_for_order(order)

    result = warmed_service.run_analysis_cycle(NOW)

    assert result.order_intents == ()
    assert result.trade_suppressed_reason == "combined portfolio risk exceeds limit"
    assert warmed_service.broker.submitted == []


def test_covered_share_floor_at_target_allows_new_option_exposure(warmed_service):
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, options_auto_execute=True
    )
    warmed_service.broker.cash = Decimal("200000")
    warmed_service.broker.equity = Decimal("200000")
    warmed_service.broker.options_buying_power = Decimal("200000")
    warmed_service.broker.equity_lots = (
        EquityPosition("AAPL", Decimal("100"), Decimal("300"), Decimal("320")),
    )
    warmed_service.broker.option_orders = (
        OptionOpenOrder(
            "AAPL261002C00350000",
            "AAPL",
            "call",
            "sell_to_open",
            Decimal("1"),
            Decimal("0"),
            Decimal("350"),
        ),
    )
    order = warmed_service.broker.option_orders[0]
    warmed_service.broker.exact_option_contract_values[order.symbol] = _quote_for_order(
        order, Decimal("0")
    )
    warmed_service.broker.option_contract_values = {
        "MSFT": (
            OptionContract(
                "MSFT260904P00050000",
                "MSFT",
                "put",
                Decimal("50"),
                date(2026, 9, 4),
                Decimal("-0.20"),
                Decimal("3.00"),
                Decimal("3.20"),
                Decimal("500"),
                NOW,
            ),
        ),
    }
    high_risk_aapl = _aligned_history(Decimal("0.08"))["AAPL"]
    warmed_service.broker.close_history = {
        **warmed_service.broker.close_history,
        "AAPL": high_risk_aapl,
    }

    result = warmed_service.manage_options(NOW)

    assert len(result.intents) == 1
    assert result.suppressed_reason is None
    assert len(warmed_service.broker.submitted_options) == 1


def test_option_entry_is_suppressed_when_combined_risk_exceeds_limit(warmed_service):
    warmed_service.settings = replace(warmed_service.settings, options_enabled=True)
    warmed_service.broker.cash = Decimal("200000")
    warmed_service.broker.buying_power = Decimal("200000")
    warmed_service.broker.equity = Decimal("200000")
    warmed_service.broker.options_buying_power = Decimal("200000")
    warmed_service.broker.latest_prices["AAPL"] = Decimal("1000")
    warmed_service.broker.option_contract_values = {
        "AAPL": (_eligible_put("AAPL", NOW),),
    }
    high_risk_history = _aligned_history(Decimal("0.08"))
    aapl_history = high_risk_history["AAPL"]
    warmed_service.broker.close_history = dict.fromkeys(
        warmed_service.settings.watchlist, aapl_history
    )
    result = warmed_service.manage_options(NOW)
    assert result.intents == ()
    assert result.suppressed_reason == "combined portfolio risk exceeds limit"


def test_dry_run_records_ticket_without_submitting(warmed_service):
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, options_auto_execute=False
    )
    warmed_service.broker.cash = Decimal("200000")
    warmed_service.broker.buying_power = Decimal("200000")
    warmed_service.broker.equity = Decimal("200000")
    warmed_service.broker.options_buying_power = Decimal("200000")
    warmed_service.broker.option_contract_values = {
        "AAPL": (_eligible_put("AAPL", NOW),),
    }
    result = warmed_service.manage_options(NOW)
    assert result.intents
    assert warmed_service.broker.submitted_options == []


@pytest.mark.parametrize(
    "failure",
    [
        "options_buying_power",
        "option_positions",
        "option_orders",
        "option_quote",
        "earnings_cache",
        "daily_closes",
    ],
)
def test_option_read_failure_submits_nothing(warmed_service, failure):
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, options_auto_execute=True
    )
    warmed_service.broker.option_contract_values = {
        "AAPL": (_eligible_put("AAPL", NOW),),
    }
    warmed_service.broker.option_failure = failure
    if failure == "options_buying_power":
        warmed_service.broker.options_buying_power = Decimal("-1")
    elif failure == "earnings_cache":
        warmed_service.settings.options_earnings_path.unlink()
    result = warmed_service.manage_options(NOW)
    assert result.submitted_order_ids == ()
    assert result.suppressed_reason
    assert warmed_service.broker.submitted_options == []


def test_option_delta_computation_failure_submits_nothing(warmed_service, monkeypatch):
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, options_auto_execute=True
    )
    monkeypatch.setattr(
        "tradingagents.automation._held_option_exposure",
        lambda positions, prices: (_ for _ in ()).throw(RuntimeError("delta unavailable")),
    )

    result = warmed_service.manage_options(NOW)

    assert result.submitted_order_ids == ()
    assert result.suppressed_reason == "option read failed: delta unavailable"
    assert warmed_service.broker.submitted_options == []


@pytest.mark.parametrize(
    ("equity_ack", "options_ack"),
    [
        ("", LIVE_OPTIONS_ACKNOWLEDGMENT),
        ("wrong", LIVE_OPTIONS_ACKNOWLEDGMENT),
        (LIVE_ACKNOWLEDGMENT, ""),
        (LIVE_ACKNOWLEDGMENT, "wrong"),
    ],
)
def test_live_acknowledgments_are_required_before_option_cancellation(
    warmed_service, equity_ack, options_ack
):
    warmed_service.settings = replace(
        warmed_service.settings,
        options_enabled=True,
        options_auto_execute=True,
        alpaca_mode="live",
        live_trading_ack=equity_ack,
        live_options_ack=options_ack,
    )
    warmed_service.broker.option_orders = (
        OptionOpenOrder(
            "AAPL260904P00300000",
            "AAPL",
            "put",
            "buy_to_close",
            Decimal("1"),
            Decimal("0"),
            Decimal("300"),
            "old-owned",
            "ta-wheel-old",
            NOW - timedelta(minutes=10),
        ),
    )

    result = warmed_service.manage_options(NOW)

    assert result.suppressed_reason
    assert warmed_service.broker.cancelled_options == []
    assert warmed_service.broker.submitted_options == []


def test_valid_live_acknowledgments_cancel_only_owned_old_option_orders(warmed_service):
    warmed_service.settings = replace(
        warmed_service.settings,
        options_enabled=True,
        options_auto_execute=True,
        alpaca_mode="live",
        live_trading_ack=LIVE_ACKNOWLEDGMENT,
        live_options_ack=LIVE_OPTIONS_ACKNOWLEDGMENT,
    )
    warmed_service.broker.option_orders = (
        OptionOpenOrder(
            "AAPL260904P00300000", "AAPL", "put", "buy_to_close",
            Decimal("1"), Decimal("0"), Decimal("300"), "old-owned",
            "ta-wheel-old", NOW - timedelta(minutes=10),
        ),
        OptionOpenOrder(
            "MSFT260904P00300000", "MSFT", "put", "buy_to_close",
            Decimal("1"), Decimal("0"), Decimal("300"), "young-owned",
            "ta-wheel-young", NOW - timedelta(minutes=9),
        ),
        OptionOpenOrder(
            "NVDA260904P00300000", "NVDA", "put", "buy_to_close",
            Decimal("1"), Decimal("0"), Decimal("300"), "old-manual",
            "manual-old", NOW - timedelta(minutes=20),
        ),
    )

    warmed_service.manage_options(NOW)

    assert warmed_service.broker.cancelled_options == [
        ("old-owned", "ta-wheel-old")
    ]


def test_stale_option_cancellation_failure_blocks_new_entries(warmed_service):
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, options_auto_execute=True
    )
    warmed_service.broker.cancel_failure = True
    warmed_service.broker.option_orders = (
        OptionOpenOrder(
            "MSFT260904P00300000", "MSFT", "put", "buy_to_close",
            Decimal("1"), Decimal("0"), Decimal("300"), "old-owned",
            "ta-wheel-old", NOW - timedelta(minutes=10),
        ),
    )
    warmed_service.broker.cash = Decimal("200000")
    warmed_service.broker.equity = Decimal("200000")
    warmed_service.broker.options_buying_power = Decimal("200000")
    warmed_service.broker.option_contract_values = {
        "AAPL": (_eligible_put("AAPL", NOW),),
    }

    result = warmed_service.manage_options(NOW)

    assert result.suppressed_reason == "stale option cancellation failed"
    assert warmed_service.broker.cancelled_options == [
        ("old-owned", "ta-wheel-old")
    ]
    assert warmed_service.broker.submitted_options == []


def test_profit_exit_uses_exact_contract_quote_below_entry_dte(warmed_service):
    symbol = "AAPL260814P00300000"
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, options_auto_execute=True
    )
    warmed_service.broker.cash = Decimal("100000")
    warmed_service.broker.buying_power = Decimal("100000")
    warmed_service.broker.options_buying_power = Decimal("100000")
    warmed_service.broker.option_positions = (
        OptionPosition(
            symbol, "AAPL", "put", Decimal("-1"), Decimal("4"), Decimal("-0.10")
        ),
    )
    warmed_service.broker.exact_option_contract_values[symbol] = OptionContract(
        symbol,
        "AAPL",
        "put",
        Decimal("300"),
        date(2026, 8, 14),
        Decimal("-0.08"),
        Decimal("1.40"),
        Decimal("1.50"),
        Decimal("20"),
        NOW,
    )

    result = warmed_service.manage_options(NOW)

    assert [intent.position_intent for intent in result.intents] == ["buy_to_close"]
    assert [spec.symbol for spec in warmed_service.broker.submitted_options] == [symbol]


@pytest.mark.parametrize("entry_failure", ["decisions", "earnings", "history", "chain"])
def test_entry_dependency_failure_does_not_block_profit_exit(
    warmed_service, entry_failure
):
    symbol = "AAPL260904P00300000"
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, options_auto_execute=True
    )
    warmed_service.broker.cash = Decimal("100000")
    warmed_service.broker.options_buying_power = Decimal("100000")
    warmed_service.broker.option_positions = (
        OptionPosition(
            symbol, "AAPL", "put", Decimal("-1"), Decimal("4"), Decimal("-0.10")
        ),
    )
    warmed_service.broker.exact_option_contract_values[symbol] = OptionContract(
        symbol,
        "AAPL",
        "put",
        Decimal("300"),
        date(2026, 9, 4),
        Decimal("-0.08"),
        Decimal("1.40"),
        Decimal("1.50"),
        Decimal("20"),
        NOW,
    )
    if entry_failure == "decisions":
        warmed_service.state._connection.execute("DELETE FROM decisions")
        warmed_service.state._connection.commit()
    elif entry_failure == "earnings":
        warmed_service.settings.options_earnings_path.unlink()
    elif entry_failure == "history":
        warmed_service.broker.option_failure = "daily_closes"
    else:
        warmed_service.broker.entry_chain_failure = True

    result = warmed_service.manage_options(NOW)

    assert [intent.position_intent for intent in result.intents] == ["buy_to_close"]
    assert [spec.position_intent for spec in warmed_service.broker.submitted_options] == [
        "buy_to_close"
    ]


def test_all_option_specs_prepare_before_first_submission(warmed_service):
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, options_auto_execute=True
    )
    warmed_service.broker.cash = Decimal("1000000")
    warmed_service.broker.equity = Decimal("1000000")
    warmed_service.broker.options_buying_power = Decimal("1000000")
    warmed_service.broker.option_contract_values = {
        "AAPL": (_eligible_put("AAPL", NOW),),
        "MSFT": (_eligible_put("MSFT", NOW),),
    }
    warmed_service.broker.option_prepare_failures.add("MSFT")

    result = warmed_service.manage_options(NOW)

    assert result.suppressed_reason == "option submission errors: MSFT260904P00300000"
    assert warmed_service.broker.submitted_options == []


def test_all_option_intents_persist_before_first_submission(warmed_service, monkeypatch):
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, options_auto_execute=True
    )
    warmed_service.broker.cash = Decimal("1000000")
    warmed_service.broker.equity = Decimal("1000000")
    warmed_service.broker.options_buying_power = Decimal("1000000")
    warmed_service.broker.option_contract_values = {
        "AAPL": (_eligible_put("AAPL", NOW),),
        "MSFT": (_eligible_put("MSFT", NOW),),
    }
    record = warmed_service.state.record_option_intent
    calls = []

    def fail_second(*args, **kwargs):
        calls.append(args[2])
        if len(calls) == 2:
            raise RuntimeError("persistence unavailable")
        return record(*args, **kwargs)

    monkeypatch.setattr(warmed_service.state, "record_option_intent", fail_second)

    result = warmed_service.manage_options(NOW)

    assert result.suppressed_reason == "option submission errors: MSFT260904P00300000"
    assert warmed_service.broker.submitted_options == []


def test_first_cycle_analyzes_three_but_does_not_trade_before_warmup(service):
    result = service.run_analysis_cycle(NOW)
    assert result.analyzed_symbols == ("AAPL", "MSFT", "NVDA")
    assert result.order_intents == ()
    assert result.trade_suppressed_reason == "waiting for fresh decisions for all 7 symbols"
    assert service.broker.submitted == []
    assert "account" not in service.broker.reads


def test_three_cycles_rotate_3_2_2_then_allocate_all_fresh_decisions(service):
    assert service.run_analysis_cycle(NOW).analyzed_symbols == ("AAPL", "MSFT", "NVDA")
    assert service.run_analysis_cycle(NOW.replace(minute=30)).analyzed_symbols == (
        "AMZN",
        "META",
    )
    third = service.run_analysis_cycle(NOW.replace(hour=15, minute=0))
    assert third.analyzed_symbols == ("GOOG", "TSLA")
    gross = sum(abs(intent.target_notional) for intent in third.order_intents)
    assert Decimal("3000") < gross <= Decimal("200000")
    assert service.broker.submitted == []


def test_stale_or_failed_symbol_suppresses_every_order(service):
    service.state.advance_batch_index(1)
    service.graph_failures.add("META")
    service.seed_all_decisions()
    result = service.run_analysis_cycle(NOW)
    assert result.failed_symbols == ("META",)
    assert result.order_intents == ()
    assert "META" in result.trade_suppressed_reason
    assert service.broker.submitted == []


def test_dry_run_persists_plan_without_submission(warmed_service):
    result = warmed_service.run_analysis_cycle(NOW)
    assert result.order_intents
    assert warmed_service.state.order_intent_count(result.cycle_id) == len(result.order_intents)
    assert set(warmed_service.state.order_intent_statuses(result.cycle_id).values()) == {"planned"}
    assert warmed_service.broker.submitted == []


def test_equity_risk_scaling_applies_when_options_are_disabled(warmed_service):
    warmed_service.settings = replace(
        warmed_service.settings, auto_execute=True, max_cash_allocation=0.30
    )
    warmed_service.service.settings = warmed_service.settings
    warmed_service.broker.cash = Decimal("100000")
    warmed_service.broker.buying_power = Decimal("100000")
    warmed_service.broker.close_history = _aligned_history(Decimal("0.02"))
    result = warmed_service.run_analysis_cycle(NOW)
    assert result.order_intents
    assert sum(abs(intent.target_notional) for intent in result.order_intents) < Decimal("30000")
    assert warmed_service.broker.submitted


def test_equity_history_failure_blocks_submission_when_options_are_disabled(warmed_service):
    warmed_service.settings = replace(warmed_service.settings, auto_execute=True)
    warmed_service.service.settings = warmed_service.settings
    warmed_service.broker.option_failure = "daily_closes"
    result = warmed_service.run_analysis_cycle(NOW)
    assert result.order_intents == ()
    assert result.trade_suppressed_reason
    assert warmed_service.broker.submitted == []


def test_negative_cash_does_not_block_equity_controller(warmed_service):
    warmed_service.broker.cash = Decimal("-100")
    result = warmed_service.run_analysis_cycle(NOW)
    assert result.trade_suppressed_reason is None


def test_pending_open_option_delta_blocks_equity_submission(warmed_service):
    order, contract = _opening_put()
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, auto_execute=True
    )
    warmed_service.service.settings = warmed_service.settings
    warmed_service.broker.cash = Decimal("100000")
    warmed_service.broker.equity = Decimal("200000")
    warmed_service.broker.options_buying_power = Decimal("200000")
    warmed_service.broker.latest_prices["AAPL"] = Decimal("5000")
    warmed_service.broker.option_orders = (order,)
    warmed_service.broker.exact_option_contract_values[order.symbol] = contract
    result = warmed_service.run_analysis_cycle(NOW)
    assert result.order_intents == ()
    assert result.trade_suppressed_reason == "combined portfolio risk exceeds limit"
    assert warmed_service.broker.submitted == []


def test_pending_open_option_delta_blocks_new_option_submission(warmed_service):
    order, contract = _opening_put()
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, options_auto_execute=True
    )
    warmed_service.broker.cash = Decimal("100000")
    warmed_service.broker.equity = Decimal("200000")
    warmed_service.broker.options_buying_power = Decimal("200000")
    warmed_service.broker.latest_prices["AAPL"] = Decimal("5000")
    warmed_service.broker.option_orders = (order,)
    warmed_service.broker.exact_option_contract_values[order.symbol] = contract
    warmed_service.broker.option_contract_values = {
        "MSFT": (_eligible_put("MSFT", NOW),),
    }
    result = warmed_service.manage_options(NOW)
    assert result.intents == ()
    assert result.suppressed_reason == "combined portfolio risk exceeds limit"
    assert warmed_service.broker.submitted_options == []


@pytest.mark.parametrize(
    ("contract_changes", "order_changes"),
    [
        ({"quote_time": NOW.replace(tzinfo=None)}, {}),
        ({"quote_time": NOW + timedelta(seconds=1)}, {}),
        ({"quote_time": NOW - timedelta(seconds=301)}, {}),
        ({"bid": Decimal("0")}, {}),
        ({"bid": Decimal("4"), "ask": Decimal("3")}, {}),
        ({"ask": Decimal("NaN")}, {}),
        ({"delta": Decimal("1.01")}, {}),
        ({"strike": Decimal("11")}, {}),
        (
            {"strike": Decimal("Infinity")},
            {"strike": Decimal("Infinity"), "position_intent": "buy_to_open"},
        ),
        (
            {},
            {"filled_qty": Decimal("-1"), "position_intent": "buy_to_open"},
        ),
    ],
    ids=(
        "naive-time",
        "future-time",
        "stale-time",
        "nonpositive-bid",
        "crossed-market",
        "nonfinite-ask",
        "invalid-delta",
        "strike-mismatch",
        "nonfinite-strike",
        "negative-filled-quantity",
    ),
)
def test_invalid_pending_opening_quote_suppresses_equity_submission(
    warmed_service, contract_changes, order_changes
):
    order, contract = _opening_put()
    order = replace(order, **order_changes)
    contract = replace(
        contract, **({"delta": Decimal("-0.20")} | contract_changes)
    )
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, auto_execute=True
    )
    warmed_service.service.settings = warmed_service.settings
    warmed_service.broker.cash = Decimal("100000")
    warmed_service.broker.buying_power = Decimal("100000")
    warmed_service.broker.option_orders = (order,)
    warmed_service.broker.exact_option_contract_values[order.symbol] = contract

    result = warmed_service.run_analysis_cycle(NOW)

    assert result.order_intents == ()
    assert result.trade_suppressed_reason
    assert warmed_service.broker.submitted == []


@pytest.mark.parametrize(
    "spot", [Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity")]
)
def test_invalid_pending_opening_spot_suppresses_equity_submission(
    warmed_service, spot
):
    order, contract = _opening_put()
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, auto_execute=True
    )
    warmed_service.service.settings = warmed_service.settings
    warmed_service.broker.cash = Decimal("100000")
    warmed_service.broker.buying_power = Decimal("100000")
    warmed_service.broker.latest_prices["AAPL"] = spot
    warmed_service.broker.option_orders = (order,)
    warmed_service.broker.exact_option_contract_values[order.symbol] = contract

    result = warmed_service.run_analysis_cycle(NOW)

    assert result.order_intents == ()
    assert result.trade_suppressed_reason
    assert warmed_service.broker.submitted == []


@pytest.mark.parametrize(
    ("qty", "filled_qty"),
    [
        (Decimal("0.5"), Decimal("0")),
        (Decimal("1"), Decimal("0.5")),
    ],
)
def test_fractional_pending_opening_quantity_suppresses_equity_submission(
    warmed_service, qty, filled_qty
):
    order, contract = _opening_put()
    order = replace(
        order,
        position_intent="buy_to_open",
        qty=qty,
        filled_qty=filled_qty,
    )
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, auto_execute=True
    )
    warmed_service.service.settings = warmed_service.settings
    warmed_service.broker.cash = Decimal("100000")
    warmed_service.broker.buying_power = Decimal("100000")
    warmed_service.broker.option_orders = (order,)
    warmed_service.broker.exact_option_contract_values[order.symbol] = contract

    result = warmed_service.run_analysis_cycle(NOW)

    assert result.order_intents == ()
    assert result.trade_suppressed_reason
    assert warmed_service.broker.submitted == []


def test_offsetting_pending_opening_legs_do_not_net_for_gross_limit(warmed_service):
    orders, contracts = _offsetting_opening_puts()
    warmed_service.settings = replace(
        warmed_service.settings,
        options_enabled=True,
        auto_execute=True,
        max_gross_leverage=0.05,
    )
    warmed_service.service.settings = warmed_service.settings
    warmed_service.broker.cash = Decimal("100000")
    warmed_service.broker.buying_power = Decimal("100000")
    warmed_service.broker.option_orders = orders
    warmed_service.broker.exact_option_contract_values = {
        contract.symbol: contract for contract in contracts
    }

    result = warmed_service.run_analysis_cycle(NOW)

    assert result.order_intents == ()
    assert result.trade_suppressed_reason == "combined portfolio risk exceeds limit"
    assert warmed_service.broker.submitted == []


def test_offsetting_pending_opening_legs_block_new_option_gross(warmed_service):
    orders, contracts = _offsetting_opening_puts()
    warmed_service.settings = replace(
        warmed_service.settings,
        options_enabled=True,
        options_auto_execute=True,
        max_gross_leverage=0.05,
        options_max_equity_fraction=1.0,
    )
    warmed_service.broker.cash = Decimal("100000")
    warmed_service.broker.options_buying_power = Decimal("100000")
    warmed_service.broker.option_orders = orders
    warmed_service.broker.exact_option_contract_values = {
        contract.symbol: contract for contract in contracts
    }
    warmed_service.broker.option_contract_values = {
        "MSFT": (_eligible_put("MSFT", NOW),),
    }

    result = warmed_service.manage_options(NOW)

    assert result.intents == ()
    assert result.suppressed_reason == "combined portfolio risk exceeds limit"
    assert warmed_service.broker.submitted_options == []


def test_offsetting_held_option_legs_do_not_net_for_equity_gross(warmed_service):
    positions, _contracts = _offsetting_held_options()
    warmed_service.settings = replace(
        warmed_service.settings,
        options_enabled=True,
        auto_execute=True,
        max_gross_leverage=0.05,
    )
    warmed_service.service.settings = warmed_service.settings
    warmed_service.broker.cash = Decimal("100000")
    warmed_service.broker.buying_power = Decimal("100000")
    warmed_service.broker.option_positions = positions

    result = warmed_service.run_analysis_cycle(NOW)

    assert result.order_intents == ()
    assert result.trade_suppressed_reason == "combined portfolio risk exceeds limit"
    assert warmed_service.broker.submitted == []


def test_offsetting_held_option_legs_block_new_option_gross(warmed_service):
    positions, contracts = _offsetting_held_options()
    warmed_service.settings = replace(
        warmed_service.settings,
        options_enabled=True,
        options_auto_execute=True,
        max_gross_leverage=0.05,
        options_max_equity_fraction=1.0,
    )
    warmed_service.broker.cash = Decimal("100000")
    warmed_service.broker.options_buying_power = Decimal("100000")
    warmed_service.broker.option_positions = positions
    warmed_service.broker.exact_option_contract_values = {
        contract.symbol: contract for contract in contracts
    }
    warmed_service.broker.option_contract_values = {
        "MSFT": (_eligible_put("MSFT", NOW),),
    }

    result = warmed_service.manage_options(NOW)

    assert result.intents == ()
    assert result.suppressed_reason == "combined portfolio risk exceeds limit"
    assert warmed_service.broker.submitted_options == []


def test_equity_risk_scaling_can_increase_targets_to_gross_cap(warmed_service):
    warmed_service.settings = replace(
        warmed_service.settings, auto_execute=True, max_cash_allocation=0.30
    )
    warmed_service.service.settings = warmed_service.settings
    warmed_service.broker.cash = Decimal("10000")
    warmed_service.broker.buying_power = Decimal("200000")
    warmed_service.broker.equity = Decimal("100000")
    warmed_service.broker.close_history = _aligned_history(Decimal("0.002"))

    result = warmed_service.run_analysis_cycle(NOW)

    gross = sum(abs(intent.target_notional) for intent in result.order_intents)
    buy_notional = sum(
        intent.notional for intent in result.order_intents if intent.side == "buy"
    )
    assert gross == Decimal("200000")
    assert warmed_service.broker.cash - buy_notional < 0
    assert gross <= warmed_service.broker.buying_power
    targets = {intent.symbol: intent.target_notional for intent in result.order_intents}
    assert (
        forecast_volatility(
            targets,
            warmed_service.broker.equity,
            close_returns(warmed_service.broker.close_history),
        )
        <= Decimal("0.15")
    )
    assert warmed_service.broker.submitted


def test_equity_risk_validation_tolerates_decimal_noise_at_target(
    warmed_service, monkeypatch
):
    target = Decimal("100")
    results = iter(
        (
            RiskScaleResult(
                {"AAPL": target},
                Decimal("0.15"),
                Decimal("0.15"),
                Decimal("1"),
                Decimal("0.1"),
            ),
            RiskScaleResult(
                {"AAPL": target},
                Decimal("0.1500000000000000000000000004"),
                Decimal("0.15"),
                Decimal("1"),
                Decimal("0.1"),
            ),
        )
    )
    monkeypatch.setattr(
        "tradingagents.automation.scale_equity_targets",
        lambda *args: next(results),
    )

    adjusted = warmed_service.service._risk_adjusted_targets(
        {"AAPL": target},
        {},
        {},
        Decimal("1000"),
        {},
    )

    assert adjusted == {"AAPL": target}


def test_equity_risk_validation_keeps_maximum_volatility_hard(
    warmed_service, monkeypatch
):
    warmed_service.settings = replace(
        warmed_service.settings,
        target_volatility=0.20,
        max_volatility=0.20,
    )
    warmed_service.service.settings = warmed_service.settings
    target = Decimal("100")
    results = iter(
        (
            RiskScaleResult(
                {"AAPL": target},
                Decimal("0.20"),
                Decimal("0.20"),
                Decimal("1"),
                Decimal("0.1"),
            ),
            RiskScaleResult(
                {"AAPL": target},
                Decimal("0.2000000000005"),
                Decimal("0.20"),
                Decimal("1"),
                Decimal("0.1"),
            ),
        )
    )
    monkeypatch.setattr(
        "tradingagents.automation.scale_equity_targets",
        lambda *args: next(results),
    )

    with pytest.raises(ValueError, match="combined portfolio risk exceeds limit"):
        warmed_service.service._risk_adjusted_targets(
            {"AAPL": target},
            {},
            {},
            Decimal("1000"),
            {},
        )


def test_options_cycle_persists_broker_reservations_for_reopen(warmed_service):
    order, contract = _opening_put()
    warmed_service.settings = replace(warmed_service.settings, options_enabled=True)
    warmed_service.broker.option_orders = (order,)
    warmed_service.broker.exact_option_contract_values[order.symbol] = contract
    result = warmed_service.manage_options(NOW)
    with AutomationState(warmed_service.state.path) as reopened:
        snapshot = reopened.latest_wheel_reservations()
    assert snapshot.cycle_id == result.cycle_id
    assert snapshot.put_collateral == {"AAPL": Decimal("1000")}
    assert snapshot.covered_shares == {}


def test_reservation_persistence_failure_blocks_new_exposure(warmed_service, monkeypatch):
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, options_auto_execute=True
    )
    warmed_service.broker.cash = Decimal("200000")
    warmed_service.broker.options_buying_power = Decimal("200000")
    warmed_service.broker.equity = Decimal("200000")
    warmed_service.broker.option_contract_values = {
        "AAPL": (_eligible_put("AAPL", NOW),),
    }
    monkeypatch.setattr(
        warmed_service.state,
        "record_wheel_reservations",
        lambda *args: (_ for _ in ()).throw(RuntimeError("reservation store unavailable")),
    )
    result = warmed_service.manage_options(NOW)
    assert result.intents == ()
    assert result.suppressed_reason
    assert warmed_service.broker.submitted_options == []


def test_position_tracking_persists_cash_and_positions(service):
    service.broker.position_values = {"AAPL": Decimal("500")}
    service.track_positions(NOW)
    snapshot = service.state.latest_position_snapshot()
    assert snapshot.cash == Decimal("10000")
    assert snapshot.positions == {"AAPL": Decimal("500")}


def test_position_tracking_waits_when_only_equity_market_is_closed(service):
    service.broker.market_open = False
    service.track_positions(NOW)
    assert service.state.latest_position_snapshot() is None


def test_equity_closed_partition_is_deferred_without_cursor_advance(service):
    service.broker.market_open = False
    result = service.run_analysis_cycle(NOW)
    assert result.analyzed_symbols == ()
    assert result.trade_suppressed_reason == "fewer than 2 eligible symbols in current partition"
    assert service.state.get_batch_index() == 0
    assert service.broker.submitted == []


def test_crypto_remains_eligible_while_equity_market_is_closed(tmp_path):
    symbols = ("BTC-USD", "ETH-USD", "AAPL", "MSFT", "NVDA", "AMZN", "META")
    ratings = {symbol: RATINGS[symbol] for symbol in symbols}
    state = AutomationState(tmp_path / "crypto.db")
    broker = FakeBroker()
    broker.market_open = False
    harness = ServiceHarness(
        _settings(tmp_path, watchlist=symbols, state_path=tmp_path / "crypto.db"),
        state,
        broker,
        ratings,
    )
    try:
        result = harness.run_analysis_cycle(NOW)
        assert result.analyzed_symbols == ("BTC-USD", "ETH-USD")
        assert result.trade_suppressed_reason == "waiting for fresh decisions for all 7 symbols"
        assert state.get_batch_index() == 1
        assert broker.submitted == []
    finally:
        state.close()


def test_warmed_mixed_watchlist_suppresses_crypto_when_history_is_unavailable(tmp_path):
    symbols = ("BTC-USD", "ETH-USD", "AAPL", "MSFT", "NVDA", "AMZN", "META")
    ratings = dict.fromkeys(symbols, "Hold")
    ratings.update({"BTC-USD": "Buy", "ETH-USD": "Overweight"})
    state = AutomationState(tmp_path / "mixed-closed.db")
    broker = FakeBroker()
    broker.market_open = False
    broker.cash = Decimal("1000000")
    broker.equity = Decimal("100000")
    broker.buying_power = Decimal("200000")
    harness = ServiceHarness(
        _settings(
            tmp_path,
            watchlist=symbols,
            auto_execute=True,
            max_cash_allocation=0.90,
            max_cash_reserve_usd=70000,
            state_path=tmp_path / "mixed-closed.db",
        ),
        state,
        broker,
        ratings,
    )
    harness.seed_all_decisions()
    try:
        result = harness.run_analysis_cycle(NOW)
        assert result.order_intents == ()
        assert result.trade_suppressed_reason == "combined portfolio risk exceeds limit"
        assert broker.daily_close_calls == [("BTC-USD", "ETH-USD")]
        assert broker.submitted == []
        assert not any(
            read.startswith("price:") and not read.endswith("-USD") for read in broker.reads
        )
    finally:
        state.close()


def test_supported_crypto_history_constrains_supra_gross_reserve_targets(tmp_path):
    symbols = ("BTC-USD", "ETH-USD", "AAPL", "MSFT", "NVDA", "AMZN", "META")
    ratings = dict.fromkeys(symbols, "Hold")
    ratings.update({"BTC-USD": "Buy", "ETH-USD": "Overweight"})
    state = AutomationState(tmp_path / "mixed-supported.db")
    broker = FakeBroker()
    broker.market_open = False
    broker.cash = Decimal("1000000")
    broker.equity = Decimal("100000")
    broker.buying_power = Decimal("200000")
    stock_history = _aligned_history(Decimal("0.002"))
    broker.close_history = {
        "BTC-USD": stock_history["AAPL"],
        "ETH-USD": stock_history["MSFT"],
    }
    harness = ServiceHarness(
        _settings(
            tmp_path,
            watchlist=symbols,
            auto_execute=True,
            max_cash_allocation=0.90,
            max_cash_reserve_usd=70000,
            state_path=tmp_path / "mixed-supported.db",
        ),
        state,
        broker,
        ratings,
    )
    harness.seed_all_decisions()
    try:
        result = harness.run_analysis_cycle(NOW)
        targets = {intent.symbol: intent.target_notional for intent in result.order_intents}
        gross = sum(abs(target) for target in targets.values())
        buy_notional = sum(
            intent.notional for intent in result.order_intents if intent.side == "buy"
        )

        assert result.trade_suppressed_reason is None
        assert broker.daily_close_calls == [("BTC-USD", "ETH-USD")]
        assert set(targets) == {"BTC-USD", "ETH-USD"}
        assert gross < broker.cash * Decimal("0.90")
        assert gross <= Decimal("200000")
        assert buy_notional <= broker.buying_power
        assert forecast_volatility(
            targets,
            broker.equity,
            close_returns(broker.close_history),
        ) <= Decimal("0.1500000001")
        assert broker.submitted
    finally:
        state.close()


def test_cash_reserve_cycle_creates_risk_constrained_intents_within_buying_power(
    warmed_service,
):
    warmed_service.settings = replace(
        warmed_service.settings,
        auto_execute=True,
        max_cash_allocation=0.90,
        max_cash_reserve_usd=70000,
    )
    warmed_service.service.settings = warmed_service.settings
    warmed_service.broker.cash = Decimal("10000")
    warmed_service.broker.equity = Decimal("100000")
    warmed_service.broker.buying_power = Decimal("200000")
    warmed_service.broker.close_history = _aligned_history(Decimal("0.002"))

    result = warmed_service.run_analysis_cycle(NOW)
    targets = {intent.symbol: intent.target_notional for intent in result.order_intents}
    projected_cash = warmed_service.broker.equity - sum(targets.values())
    gross = sum(abs(target) for target in targets.values())
    buy_notional = sum(
        intent.notional for intent in result.order_intents if intent.side == "buy"
    )

    assert result.trade_suppressed_reason is None
    assert result.order_intents
    assert projected_cash < Decimal("0")
    assert gross <= Decimal("200000")
    assert buy_notional <= warmed_service.broker.buying_power
    assert forecast_volatility(
        targets,
        warmed_service.broker.equity,
        close_returns(warmed_service.broker.close_history),
    ) <= Decimal("0.1500000001")
    assert len(result.submitted_order_ids) == len(result.order_intents)
    assert len(warmed_service.broker.submitted) == len(result.order_intents)


def test_cash_reserve_cycle_suppresses_same_intents_beyond_buying_power(
    warmed_service,
):
    warmed_service.settings = replace(
        warmed_service.settings,
        auto_execute=True,
        max_cash_allocation=0.90,
        max_cash_reserve_usd=70000,
    )
    warmed_service.service.settings = warmed_service.settings
    warmed_service.broker.cash = Decimal("10000")
    warmed_service.broker.equity = Decimal("100000")
    warmed_service.broker.buying_power = Decimal("150000")
    warmed_service.broker.close_history = _aligned_history(Decimal("0.002"))

    result = warmed_service.run_analysis_cycle(NOW)
    targets = {intent.symbol: intent.target_notional for intent in result.order_intents}
    projected_cash = warmed_service.broker.equity - sum(targets.values())
    gross = sum(abs(target) for target in targets.values())
    buy_notional = sum(
        intent.notional for intent in result.order_intents if intent.side == "buy"
    )

    assert result.trade_suppressed_reason == "insufficient buying power"
    assert result.order_intents
    assert projected_cash < Decimal("0")
    assert gross <= Decimal("200000")
    assert buy_notional > warmed_service.broker.buying_power
    assert forecast_volatility(
        targets,
        warmed_service.broker.equity,
        close_returns(warmed_service.broker.close_history),
    ) <= Decimal("0.1500000001")
    assert result.submitted_order_ids == ()
    assert warmed_service.broker.submitted == []


def test_one_symbol_eligibility_defers_whole_partition(tmp_path):
    symbols = ("BTC-USD", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOG")
    ratings = {symbol: RATINGS[symbol] for symbol in symbols}
    state = AutomationState(tmp_path / "one-eligible.db")
    broker = FakeBroker()
    broker.market_open = False
    harness = ServiceHarness(
        _settings(tmp_path, watchlist=symbols, state_path=tmp_path / "one-eligible.db"),
        state,
        broker,
        ratings,
    )
    try:
        result = harness.run_analysis_cycle(NOW)
        assert result.analyzed_symbols == ()
        assert result.trade_suppressed_reason == (
            "fewer than 2 eligible symbols in current partition"
        )
        assert state.get_batch_index() == 0
        assert broker.submitted == []
    finally:
        state.close()


def test_blocked_account_suppresses_every_order(warmed_service):
    warmed_service.broker.trading_blocked = True
    result = warmed_service.run_analysis_cycle(NOW)
    assert result.order_intents == ()
    assert result.trade_suppressed_reason == "account is blocked from trading"
    assert warmed_service.broker.submitted == []


def test_insufficient_buying_power_suppresses_all_submission(tmp_path):
    state = AutomationState(tmp_path / "buying-power.db")
    broker = FakeBroker()
    broker.buying_power = Decimal("100")
    harness = ServiceHarness(
        _settings(
            tmp_path,
            auto_execute=True,
            state_path=tmp_path / "buying-power.db",
        ),
        state,
        broker,
    )
    harness.seed_all_decisions()
    try:
        result = harness.run_analysis_cycle(NOW)
        assert result.order_intents
        assert result.submitted_order_ids == ()
        assert result.trade_suppressed_reason == "insufficient buying power"
        assert broker.submitted == []
    finally:
        state.close()


def test_insufficient_buying_power_suppresses_all_short_openings(tmp_path):
    state = AutomationState(tmp_path / "short-buying-power.db")
    broker = FakeBroker()
    broker.buying_power = Decimal("100")
    ratings = dict.fromkeys(RATINGS, "Sell")
    harness = ServiceHarness(
        _settings(
            tmp_path,
            auto_execute=True,
            state_path=tmp_path / "short-buying-power.db",
        ),
        state,
        broker,
        ratings,
    )
    harness.seed_all_decisions()
    try:
        result = harness.run_analysis_cycle(NOW)

        assert result.order_intents
        assert all(intent.side == "sell" for intent in result.order_intents)
        assert result.submitted_order_ids == ()
        assert result.trade_suppressed_reason == "insufficient buying power"
        assert broker.submitted == []
    finally:
        state.close()


def test_short_openings_within_buying_power_submit(tmp_path):
    state = AutomationState(tmp_path / "funded-shorts.db")
    broker = FakeBroker()
    broker.buying_power = Decimal("200000")
    broker.close_history = _aligned_history(Decimal("0.002"))
    ratings = dict.fromkeys(RATINGS, "Sell")
    harness = ServiceHarness(
        _settings(
            tmp_path,
            auto_execute=True,
            state_path=tmp_path / "funded-shorts.db",
        ),
        state,
        broker,
        ratings,
    )
    harness.seed_all_decisions()
    try:
        result = harness.run_analysis_cycle(NOW)

        assert result.trade_suppressed_reason is None
        assert result.order_intents
        assert all(intent.side == "sell" for intent in result.order_intents)
        short_notional = sum(intent.notional for intent in result.order_intents)
        assert broker.equity < short_notional <= broker.buying_power
        assert len(result.submitted_order_ids) == len(result.order_intents)
        assert len(broker.submitted) == len(result.order_intents)
    finally:
        state.close()


def test_exposure_reducing_buys_do_not_consume_buying_power(tmp_path):
    state = AutomationState(tmp_path / "reducing-shorts.db")
    broker = FakeBroker()
    broker.buying_power = Decimal("0")
    broker.position_values = dict.fromkeys(RATINGS, Decimal("-100000"))
    ratings = dict.fromkeys(RATINGS, "Sell")
    harness = ServiceHarness(
        _settings(
            tmp_path,
            auto_execute=True,
            state_path=tmp_path / "reducing-shorts.db",
        ),
        state,
        broker,
        ratings,
    )
    harness.seed_all_decisions()
    try:
        result = harness.run_analysis_cycle(NOW)

        assert result.trade_suppressed_reason is None
        assert result.order_intents
        assert all(intent.side == "buy" for intent in result.order_intents)
        assert len(result.submitted_order_ids) == len(result.order_intents)
    finally:
        state.close()


def test_open_orders_count_toward_effective_exposure_in_preflight(tmp_path):
    state = AutomationState(tmp_path / "reducing-open-shorts.db")
    broker = FakeBroker()
    broker.buying_power = Decimal("0")
    broker.open_exposure = dict.fromkeys(RATINGS, Decimal("-100000"))
    ratings = dict.fromkeys(RATINGS, "Sell")
    harness = ServiceHarness(
        _settings(
            tmp_path,
            auto_execute=True,
            state_path=tmp_path / "reducing-open-shorts.db",
        ),
        state,
        broker,
        ratings,
    )
    harness.seed_all_decisions()
    try:
        result = harness.run_analysis_cycle(NOW)

        assert result.trade_suppressed_reason is None
        assert result.order_intents
        assert all(intent.side == "buy" for intent in result.order_intents)
        assert len(result.submitted_order_ids) == len(result.order_intents)
    finally:
        state.close()


@pytest.mark.parametrize(
    ("rating", "current_exposure", "side", "suppressed"),
    (
        ("Sell", Decimal("100000"), "sell", False),
        ("Buy", Decimal("-100000"), "buy", False),
        ("Sell", Decimal("100"), "sell", True),
        ("Buy", Decimal("-100"), "buy", True),
    ),
)
def test_sign_crossing_charges_only_net_incremental_absolute_exposure(
    tmp_path, rating, current_exposure, side, suppressed
):
    state = AutomationState(tmp_path / f"crossing-{side}.db")
    broker = FakeBroker()
    broker.buying_power = Decimal("0")
    broker.position_values = dict.fromkeys(RATINGS, current_exposure)
    ratings = dict.fromkeys(RATINGS, rating)
    harness = ServiceHarness(
        _settings(
            tmp_path,
            auto_execute=True,
            state_path=tmp_path / f"crossing-{side}.db",
        ),
        state,
        broker,
        ratings,
    )
    harness.seed_all_decisions()
    try:
        result = harness.run_analysis_cycle(NOW)

        assert result.order_intents
        assert all(intent.side == side for intent in result.order_intents)
        if suppressed:
            assert result.trade_suppressed_reason == "insufficient buying power"
            assert result.submitted_order_ids == ()
            assert broker.submitted == []
        else:
            assert result.trade_suppressed_reason is None
            assert len(result.submitted_order_ids) == len(result.order_intents)
            assert len(broker.submitted) == len(result.order_intents)
    finally:
        state.close()


def test_unsupported_short_is_skipped_without_redistribution(tmp_path):
    state = AutomationState(tmp_path / "unsupported-short.db")
    broker = FakeBroker()
    broker.shortable["TSLA"] = False
    harness = ServiceHarness(
        _settings(
            tmp_path,
            auto_execute=True,
            state_path=tmp_path / "unsupported-short.db",
        ),
        state,
        broker,
    )
    harness.seed_all_decisions()
    try:
        result = harness.run_analysis_cycle(NOW)
        targets = {intent.symbol: intent.target_notional for intent in result.order_intents}
        assert targets["AAPL"] > 0
        assert targets["AAPL"] == -targets["TSLA"]
        assert result.trade_suppressed_reason == "skipped unsupported symbols: TSLA"
        assert result.submitted_order_ids == (
            "order-AAPL",
            "order-MSFT",
            "order-AMZN",
            "order-META",
            "order-GOOG",
        )
        assert [spec.symbol for spec in broker.submitted] == [
            "AAPL",
            "MSFT",
            "AMZN",
            "META",
            "GOOG",
        ]
        assert state.order_intent_statuses(result.cycle_id)["TSLA"] == "skipped"
    finally:
        state.close()


def test_auto_execute_paper_submits_each_planned_order(tmp_path):
    state = AutomationState(tmp_path / "paper.db")
    broker = FakeBroker()
    harness = ServiceHarness(
        _settings(tmp_path, auto_execute=True, state_path=tmp_path / "paper.db"),
        state,
        broker,
    )
    harness.seed_all_decisions()
    try:
        result = harness.run_analysis_cycle(NOW)
        assert len(result.submitted_order_ids) == len(result.order_intents) == 6
        assert result.trade_suppressed_reason is None
        assert len(broker.submitted) == 6
        assert set(state.order_intent_statuses(result.cycle_id).values()) == {"submitted"}
    finally:
        state.close()


@pytest.mark.parametrize("ack", ["", "I_UNDERSTAND_LIVE_ORDER"])
def test_live_auto_execute_requires_exact_acknowledgment(tmp_path, ack):
    state = AutomationState(tmp_path / f"live-{len(ack)}.db")
    broker = FakeBroker()
    harness = ServiceHarness(
        _settings(
            tmp_path,
            auto_execute=True,
            alpaca_mode="live",
            live_trading_ack=ack,
            state_path=tmp_path / f"live-{len(ack)}.db",
        ),
        state,
        broker,
    )
    harness.seed_all_decisions()
    try:
        result = harness.run_analysis_cycle(NOW)
        assert result.order_intents
        assert result.submitted_order_ids == ()
        assert result.trade_suppressed_reason == (
            "live acknowledgment is required for automatic live orders"
        )
        assert broker.submitted == []
    finally:
        state.close()


def test_exact_live_acknowledgment_allows_submission(tmp_path):
    state = AutomationState(tmp_path / "live-exact.db")
    broker = FakeBroker()
    harness = ServiceHarness(
        _settings(
            tmp_path,
            auto_execute=True,
            alpaca_mode="live",
            live_trading_ack=LIVE_ACKNOWLEDGMENT,
            state_path=tmp_path / "live-exact.db",
        ),
        state,
        broker,
    )
    harness.seed_all_decisions()
    try:
        result = harness.run_analysis_cycle(NOW)
        assert len(result.submitted_order_ids) == 6
        assert result.trade_suppressed_reason is None
        assert len(broker.submitted) == 6
    finally:
        state.close()


def test_graphs_are_cached_by_analyst_tuple_and_symbols_run_sequentially(tmp_path):
    symbols = ("BTC-USD", "ETH-USD", "AAPL", "MSFT", "NVDA", "AMZN", "META")
    ratings = {symbol: RATINGS[symbol] for symbol in symbols}
    state = AutomationState(tmp_path / "graphs.db")
    broker = FakeBroker()
    harness = ServiceHarness(
        _settings(tmp_path, watchlist=symbols, state_path=tmp_path / "graphs.db"),
        state,
        broker,
        ratings,
    )
    try:
        result = harness.run_analysis_cycle(NOW)
        assert result.analyzed_symbols == ("BTC-USD", "ETH-USD", "AAPL")
        assert harness.factory_calls == [
            ("market", "social", "news"),
            ("market", "social", "news", "fundamentals"),
        ]
        assert harness.graph_calls == [
            ("BTC-USD", "2026-08-11", "crypto"),
            ("ETH-USD", "2026-08-11", "crypto"),
            ("AAPL", "2026-08-11", "stock"),
        ]
        assert broker.submitted == []
    finally:
        state.close()


def test_broker_clock_drives_decision_and_position_timestamps(service):
    broker_now = NOW + timedelta(days=1, hours=3)
    service.broker.now = broker_now
    result = service.run_analysis_cycle(NOW)
    decisions = service.state.fresh_decisions(
        result.analyzed_symbols,
        broker_now,
        service.settings.decision_max_age_minutes,
    )
    service.track_positions(NOW)
    assert {record.analyzed_at for record in decisions.values()} == {broker_now}
    assert {record.trade_date for record in decisions.values()} == {"2026-08-12"}
    assert service.state.latest_position_snapshot().captured_at == broker_now
    assert service.broker.submitted == []


def test_advancing_clock_uses_post_analysis_time_for_freshness(service):
    service.seed_all_decisions(NOW)
    service.broker.clock_times = [
        NOW,
        NOW,
        NOW + timedelta(minutes=5),
        NOW + timedelta(minutes=10),
        NOW + timedelta(minutes=15),
        NOW + timedelta(minutes=20),
        NOW + timedelta(minutes=25),
        NOW + timedelta(minutes=121),
    ]

    result = service.run_analysis_cycle(NOW)
    records = service.state.fresh_decisions(
        ("AAPL", "MSFT", "NVDA"),
        NOW + timedelta(minutes=121),
        500,
    )

    assert result.order_intents == ()
    assert result.trade_suppressed_reason == "waiting for fresh decisions for all 7 symbols"
    assert {symbol: record.analyzed_at for symbol, record in records.items()} == {
        "AAPL": NOW + timedelta(minutes=5),
        "MSFT": NOW + timedelta(minutes=15),
        "NVDA": NOW + timedelta(minutes=25),
    }
    assert "account" not in service.broker.reads
    assert service.broker.submitted == []


def test_snapshot_and_intents_use_capture_boundary_broker_times(warmed_service):
    snapshot_time = NOW + timedelta(minutes=10)
    intent_time = NOW + timedelta(minutes=11)
    warmed_service.broker.clock_times = [
        NOW,
        NOW,
        NOW + timedelta(minutes=1),
        NOW + timedelta(minutes=2),
        NOW + timedelta(minutes=3),
        NOW + timedelta(minutes=4),
        NOW + timedelta(minutes=5),
        NOW + timedelta(minutes=6),
        snapshot_time,
        intent_time,
    ]

    result = warmed_service.run_analysis_cycle(NOW)

    assert result.order_intents
    assert warmed_service.state.latest_position_snapshot().captured_at == snapshot_time
    with sqlite3.connect(warmed_service.state.path) as connection:
        created_at = connection.execute(
            "SELECT DISTINCT created_at FROM order_intents WHERE cycle_id = ?",
            (result.cycle_id,),
        ).fetchall()
    assert created_at == [(intent_time.isoformat(),)]
    assert warmed_service.broker.submitted == []


def test_graph_factory_failure_records_symbol_and_continues_partition(service):
    service.factory_failures_remaining = 1

    result = service.run_analysis_cycle(NOW)

    assert result.analyzed_symbols == ("MSFT", "NVDA")
    assert result.failed_symbols == ("AAPL",)
    assert result.order_intents == ()
    assert result.trade_suppressed_reason == "analysis failed for: AAPL"
    assert service.factory_calls == [
        ("market", "social", "news", "fundamentals"),
        ("market", "social", "news", "fundamentals"),
    ]
    assert service.graph_calls == [
        ("MSFT", "2026-08-11", "stock"),
        ("NVDA", "2026-08-11", "stock"),
    ]
    assert service.state.get_batch_index() == 1
    assert service.broker.submitted == []


def test_broker_read_failure_suppresses_all_submission(tmp_path):
    state = AutomationState(tmp_path / "read-failure.db")
    broker = FakeBroker()
    broker.read_failure = "price:META"
    harness = ServiceHarness(
        _settings(
            tmp_path,
            auto_execute=True,
            state_path=tmp_path / "read-failure.db",
        ),
        state,
        broker,
    )
    harness.seed_all_decisions()
    try:
        result = harness.run_analysis_cycle(NOW)
        assert result.order_intents == ()
        assert result.trade_suppressed_reason == "broker read failed: price unavailable for META"
        assert broker.submitted == []
    finally:
        state.close()


def test_ambiguous_submit_is_recorded_without_direct_retry(tmp_path):
    state = AutomationState(tmp_path / "submit-failure.db")
    broker = FakeBroker()
    broker.submit_failures.add("AAPL")
    harness = ServiceHarness(
        _settings(
            tmp_path,
            auto_execute=True,
            state_path=tmp_path / "submit-failure.db",
        ),
        state,
        broker,
    )
    harness.seed_all_decisions()
    try:
        result = harness.run_analysis_cycle(NOW)
        assert result.trade_suppressed_reason == "submission errors: AAPL"
        assert broker.submit_attempts.count("AAPL") == 1
        assert all(spec.symbol != "AAPL" for spec in broker.submitted)
        assert state.order_intent_statuses(result.cycle_id)["AAPL"] == "error"
        row = state._connection.execute(
            "SELECT client_order_id FROM order_intents WHERE cycle_id = ? AND symbol = 'AAPL'",
            (result.cycle_id,),
        ).fetchone()
        assert row[0].startswith("ta-")
    finally:
        state.close()


@pytest.mark.parametrize("broker_lookup", [None, "accepted-order", "error"])
def test_unresolved_equity_intent_never_duplicates_after_restart(
    warmed_service, broker_lookup
):
    first = warmed_service.run_analysis_cycle(NOW)
    intent = next(item for item in first.order_intents if item.symbol == "AAPL")
    warmed_service.state.record_order_intents(
        "crashed-equity", NOW + timedelta(seconds=1), (intent,)
    )
    warmed_service.state.update_order_intent(
        "crashed-equity", "AAPL", "pending", "ta-original-equity"
    )
    warmed_service.settings = replace(warmed_service.settings, auto_execute=True)
    warmed_service.service.settings = warmed_service.settings
    if broker_lookup == "error":
        warmed_service.broker.lookup_failure = True
    elif broker_lookup is not None:
        warmed_service.broker.order_lookups["ta-original-equity"] = broker_lookup

    result = warmed_service.run_analysis_cycle(NOW + timedelta(minutes=30))

    assert warmed_service.broker.lookup_calls == ["ta-original-equity"]
    assert all(spec.symbol != "AAPL" for spec in warmed_service.broker.submitted)
    if broker_lookup == "accepted-order":
        assert "accepted-order" in result.submitted_order_ids
    else:
        assert result.trade_suppressed_reason
        assert warmed_service.broker.submit_attempts == []


def test_ambiguous_unresolved_equity_intent_suppresses_before_lookup(warmed_service):
    first = warmed_service.run_analysis_cycle(NOW)
    intent = next(item for item in first.order_intents if item.symbol == "AAPL")
    for cycle, client_id in (("crash-1", "ta-one"), ("crash-2", "ta-two")):
        warmed_service.state.record_order_intents(cycle, NOW, (intent,))
        warmed_service.state.update_order_intent(
            cycle, "AAPL", "pending", client_id
        )
    warmed_service.settings = replace(warmed_service.settings, auto_execute=True)
    warmed_service.service.settings = warmed_service.settings

    result = warmed_service.run_analysis_cycle(NOW + timedelta(minutes=30))

    assert result.trade_suppressed_reason
    assert warmed_service.broker.lookup_calls == []
    assert warmed_service.broker.submitted == []


@pytest.mark.parametrize("broker_lookup", [None, "accepted-option", "error"])
def test_unresolved_option_intent_never_duplicates_after_restart(
    warmed_service, broker_lookup
):
    symbol = "AAPL260904P00300000"
    warmed_service.state.record_option_intent(
        "crashed-option",
        NOW,
        symbol,
        "AAPL",
        "sell_to_open",
        Decimal("1"),
        Decimal("3.10"),
        "ta-original-option",
    )
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, options_auto_execute=True
    )
    warmed_service.broker.cash = Decimal("200000")
    warmed_service.broker.options_buying_power = Decimal("200000")
    warmed_service.broker.equity = Decimal("200000")
    warmed_service.broker.option_contract_values = {
        "AAPL": (_eligible_put("AAPL", NOW),),
    }
    if broker_lookup == "error":
        warmed_service.broker.lookup_failure = True
    elif broker_lookup is not None:
        warmed_service.broker.order_lookups["ta-original-option"] = broker_lookup

    result = warmed_service.manage_options(NOW)

    assert warmed_service.broker.lookup_calls == ["ta-original-option"]
    assert warmed_service.broker.submitted_options == []
    if broker_lookup == "accepted-option":
        assert result.submitted_order_ids == ("accepted-option",)
    else:
        assert result.suppressed_reason


def test_unresolved_error_without_broker_order_blocks_retry(tmp_path):
    path = tmp_path / "restart-submit.db"
    broker = FakeBroker()
    broker.submit_failures.add("AAPL")
    with AutomationState(path) as state:
        first = ServiceHarness(
            _settings(tmp_path, auto_execute=True, state_path=path), state, broker
        )
        first.seed_all_decisions()
        first_result = first.run_analysis_cycle(NOW)
        first_id = state._connection.execute(
            "SELECT client_order_id FROM order_intents WHERE cycle_id = ? AND symbol = 'AAPL'",
            (first_result.cycle_id,),
        ).fetchone()[0]

    broker.submit_failures.clear()
    with AutomationState(path) as restarted_state:
        restarted = ServiceHarness(
            _settings(tmp_path, auto_execute=True, state_path=path), restarted_state, broker
        )
        result = restarted.run_analysis_cycle(NOW.replace(minute=30))

    assert result.trade_suppressed_reason == (
        "unresolved equity intent not found at broker: AAPL"
    )
    assert first_id in broker.lookup_calls
    assert all(spec.symbol != "AAPL" for spec in broker.submitted)


def test_resolved_reused_id_retires_historical_error(tmp_path):
    path = tmp_path / "resolved-restart.db"
    broker = FakeBroker()
    broker.submit_failures.add("AAPL")
    with AutomationState(path) as state:
        first = ServiceHarness(
            _settings(tmp_path, auto_execute=True, state_path=path), state, broker
        )
        first.seed_all_decisions()
        first_result = first.run_analysis_cycle(NOW)
        first_id = state._connection.execute(
            "SELECT client_order_id FROM order_intents WHERE cycle_id = ? AND symbol = 'AAPL'",
            (first_result.cycle_id,),
        ).fetchone()[0]

    broker.submit_failures.clear()
    broker.order_lookups[first_id] = "accepted-aapl"
    with AutomationState(path) as state:
        restarted = ServiceHarness(
            _settings(tmp_path, auto_execute=True, state_path=path), state, broker
        )
        result = restarted.run_analysis_cycle(NOW.replace(minute=30))
        historical_status = state._connection.execute(
            "SELECT status FROM order_intents WHERE cycle_id = ? AND symbol = 'AAPL'",
            (first_result.cycle_id,),
        ).fetchone()[0]

    assert historical_status == "retired"
    assert "accepted-aapl" in result.submitted_order_ids
    assert all(spec.symbol != "AAPL" for spec in broker.submitted)


def test_ambiguous_reused_id_remains_reusable(tmp_path):
    path = tmp_path / "ambiguous-restart.db"
    broker = FakeBroker()
    broker.submit_failures.add("AAPL")
    with AutomationState(path) as state:
        first = ServiceHarness(
            _settings(tmp_path, auto_execute=True, state_path=path), state, broker
        )
        first.seed_all_decisions()
        first_result = first.run_analysis_cycle(NOW)
        first_id = state._connection.execute(
            "SELECT client_order_id FROM order_intents WHERE cycle_id = ? AND symbol = 'AAPL'",
            (first_result.cycle_id,),
        ).fetchone()[0]

    with AutomationState(path) as state:
        restarted = ServiceHarness(
            _settings(tmp_path, auto_execute=True, state_path=path), state, broker
        )
        second_result = restarted.run_analysis_cycle(NOW.replace(minute=30))
        aapl_intent = next(
            intent for intent in second_result.order_intents if intent.symbol == "AAPL"
        )
        historical_status = state._connection.execute(
            "SELECT status FROM order_intents WHERE cycle_id = ? AND symbol = 'AAPL'",
            (first_result.cycle_id,),
        ).fetchone()[0]

        assert historical_status == "error"
        assert state.unresolved_client_order_id(aapl_intent) == first_id


def test_later_rebalance_with_different_delta_gets_fresh_id(tmp_path):
    path = tmp_path / "later-rebalance.db"
    broker = FakeBroker()
    broker.submit_failures.add("AAPL")
    with AutomationState(path) as state:
        first = ServiceHarness(
            _settings(tmp_path, auto_execute=True, state_path=path), state, broker
        )
        first.seed_all_decisions()
        first_result = first.run_analysis_cycle(NOW)
        first_id = state._connection.execute(
            "SELECT client_order_id FROM order_intents WHERE cycle_id = ? AND symbol = 'AAPL'",
            (first_result.cycle_id,),
        ).fetchone()[0]

    broker.submit_failures.clear()
    broker.position_values["AAPL"] = Decimal("100")
    with AutomationState(path) as state:
        restarted = ServiceHarness(
            _settings(tmp_path, auto_execute=True, state_path=path), state, broker
        )
        result = restarted.run_analysis_cycle(NOW.replace(minute=30))

    submitted = [spec for spec in broker.submitted if spec.symbol == "AAPL"][-1]
    assert submitted.client_order_id != first_id
    assert "order-AAPL" in result.submitted_order_ids
