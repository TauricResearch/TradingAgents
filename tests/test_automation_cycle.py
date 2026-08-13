import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from tradingagents.automation import AutomationCycleService, AutomationSettings
from tradingagents.automation_state import AutomationState
from tradingagents.execution import (
    LIVE_ACKNOWLEDGMENT,
    AccountSnapshot,
    AlpacaBroker,
    AssetInfo,
)

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
        self.buying_power = Decimal("10000")
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
        self.reads = []

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
        return Decimal("100")

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
    yield ServiceHarness(_settings(tmp_path), state, FakeBroker())
    state.close()


@pytest.fixture
def warmed_service(service):
    service.seed_all_decisions()
    return service


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
    assert sum(abs(intent.target_notional) for intent in third.order_intents) <= Decimal("3000")
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


def test_warmed_mixed_watchlist_only_executes_crypto_while_equity_market_is_closed(tmp_path):
    symbols = ("BTC-USD", "ETH-USD", "AAPL", "MSFT", "NVDA", "AMZN", "META")
    ratings = {symbol: RATINGS[symbol] for symbol in symbols}
    state = AutomationState(tmp_path / "mixed-closed.db")
    broker = FakeBroker()
    broker.market_open = False
    harness = ServiceHarness(
        _settings(
            tmp_path,
            watchlist=symbols,
            auto_execute=True,
            state_path=tmp_path / "mixed-closed.db",
        ),
        state,
        broker,
        ratings,
    )
    harness.seed_all_decisions()
    try:
        result = harness.run_analysis_cycle(NOW)
        assert {intent.symbol for intent in result.order_intents} == {"BTC-USD", "ETH-USD"}
        assert {spec.symbol for spec in broker.submitted} == {"BTC/USD", "ETH/USD"}
        assert not any(
            read.startswith("price:") and not read.endswith("-USD") for read in broker.reads
        )
        assert sum(abs(intent.target_notional) for intent in result.order_intents) < Decimal("3000")
    finally:
        state.close()


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
        assert targets["AAPL"] == Decimal("600")
        assert targets["TSLA"] == Decimal("-600")
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


def test_next_cycle_reuses_persisted_unresolved_client_order_id(tmp_path):
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
        restarted.run_analysis_cycle(NOW.replace(minute=30))

    second = [spec for spec in broker.submitted if spec.symbol == "AAPL"][-1]
    assert second.client_order_id == first_id


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

    broker.submit_failures.clear()
    with AutomationState(path) as state:
        restarted = ServiceHarness(
            _settings(tmp_path, auto_execute=True, state_path=path), state, broker
        )
        restarted.run_analysis_cycle(NOW.replace(minute=30))
        historical_status = state._connection.execute(
            "SELECT status FROM order_intents WHERE cycle_id = ? AND symbol = 'AAPL'",
            (first_result.cycle_id,),
        ).fetchone()[0]

    assert historical_status == "retired"


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
