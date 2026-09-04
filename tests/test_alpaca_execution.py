import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from tradingagents.allocation import OrderIntent
from tradingagents.execution import (
    LIVE_ACKNOWLEDGMENT,
    LIVE_OPTIONS_ACKNOWLEDGMENT,
    AlpacaBroker,
    AssetInfo,
    OptionOrderRequestSpec,
    OrderRequestSpec,
    alpaca_symbol,
    validate_execution_mode,
)
from tradingagents.options import (
    EquityPosition,
    OptionContract,
    OptionIntent,
    OptionOpenOrder,
    OptionPosition,
)


def _enum(value):
    return SimpleNamespace(value=value)


class _MalformedDateResult(datetime):
    def date(self):
        return "2026-01-02"


class _RaisingDate(datetime):
    def date(self):
        raise ValueError("private malformed timestamp detail")


def test_symbol_conversion_changes_only_supported_crypto_separator():
    assert alpaca_symbol("BTC-USD") == "BTC/USD"
    assert alpaca_symbol("ETH-USD") == "ETH/USD"
    assert alpaca_symbol("AAPL") == "AAPL"
    assert alpaca_symbol("BRK-B") == "BRK-B"


def test_live_submission_requires_exact_acknowledgment():
    with pytest.raises(ValueError, match="live acknowledgment"):
        validate_execution_mode("live", auto_execute=True, live_ack="wrong")
    validate_execution_mode("live", auto_execute=True, live_ack="I_UNDERSTAND_LIVE_ORDERS")


def test_dry_run_still_rejects_invalid_mode_but_does_not_require_live_ack():
    validate_execution_mode("live", auto_execute=False, live_ack="")
    with pytest.raises(ValueError, match="paper or live"):
        validate_execution_mode("staging", auto_execute=False, live_ack="")


def test_paper_is_selected_explicitly_on_sdk_client(monkeypatch):
    calls = []

    class FakeTradingClient:
        def __init__(self, key, secret, paper):
            calls.append((key, secret, paper))

    monkeypatch.setattr("tradingagents.execution._trading_client_class", lambda: FakeTradingClient)
    AlpacaBroker("key", "secret", mode="paper")
    assert calls == [("key", "secret", True)]


@pytest.mark.parametrize("live_ack", ["", "wrong"])
def test_live_idempotent_submit_rejects_bad_ack_before_lookup(live_ack):
    calls = []
    client = SimpleNamespace(
        get_order_by_client_id=lambda client_order_id: calls.append("lookup"),
        submit_order=lambda order_data: calls.append("submit"),
    )
    broker = AlpacaBroker("key", "secret", mode="live", live_ack=live_ack, client=client)
    spec = OrderRequestSpec("AAPL", Decimal("1"), "buy", "day", "stable-client-id")

    with pytest.raises(ValueError, match="live acknowledgment"):
        broker.submit_idempotent(spec)
    assert calls == []


def test_live_direct_submit_rejects_missing_ack_before_sdk_request(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.execution._market_order_request_class",
        lambda: pytest.fail("must not build a live order without acknowledgment"),
    )
    broker = AlpacaBroker("key", "secret", mode="live", live_ack="", client=SimpleNamespace())
    spec = OrderRequestSpec("AAPL", Decimal("1"), "buy", "day", "stable-client-id")

    with pytest.raises(ValueError, match="live acknowledgment"):
        broker.submit(spec)


def test_exact_live_ack_allows_direct_submission(monkeypatch):
    class FakeMarketOrderRequest:
        def __init__(self, **fields):
            self.fields = fields

    monkeypatch.setattr(
        "tradingagents.execution._market_order_request_class",
        lambda: FakeMarketOrderRequest,
    )
    client = SimpleNamespace(submit_order=lambda order_data: SimpleNamespace(id="live-order"))
    broker = AlpacaBroker(
        "key",
        "secret",
        mode="live",
        live_ack="I_UNDERSTAND_LIVE_ORDERS",
        client=client,
    )
    spec = OrderRequestSpec("AAPL", Decimal("1"), "buy", "day", "stable-client-id")

    assert broker.submit(spec) == "live-order"


def test_missing_credentials_fail_without_echoing_values():
    with pytest.raises(RuntimeError) as error:
        AlpacaBroker("", "super-secret-value", mode="paper", client=SimpleNamespace())
    assert "credentials" in str(error.value)
    assert "super-secret-value" not in str(error.value)


def test_clock_and_account_are_mapped_and_blocked_accounts_raise():
    now = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)
    active = SimpleNamespace(
        cash="123.45",
        equity="987.65",
        buying_power="1000.50",
        options_buying_power="750.25",
        trading_blocked=False,
        account_blocked=False,
        trade_suspended_by_user=False,
        status=_enum("ACTIVE"),
    )
    client = SimpleNamespace(
        get_clock=lambda: SimpleNamespace(timestamp=now, is_open=True),
        get_account=lambda: active,
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)

    assert broker.broker_time() == now
    assert broker.equity_market_is_open()
    assert broker.account().cash == Decimal("123.45")
    assert broker.account().equity == Decimal("987.65")
    assert broker.account().buying_power == Decimal("1000.50")
    assert broker.account().status == "ACTIVE"

    active.trading_blocked = True
    with pytest.raises(RuntimeError, match="blocked"):
        broker.account()


def test_account_maps_options_buying_power():
    raw = SimpleNamespace(
        cash="100000",
        equity="120000",
        buying_power="200000",
        options_buying_power="75000",
        trading_blocked=False,
        account_blocked=False,
        trade_suspended_by_user=False,
        status=_enum("ACTIVE"),
    )
    broker = AlpacaBroker("key", "secret", "paper", client=SimpleNamespace(get_account=lambda: raw))

    assert broker.account().options_buying_power == Decimal("75000")


def test_account_maps_finite_negative_cash_for_authorized_margin():
    raw = SimpleNamespace(
        cash="-1250.50",
        equity="120000",
        buying_power="200000",
        options_buying_power="75000",
        trading_blocked=False,
        account_blocked=False,
        trade_suspended_by_user=False,
        status=_enum("ACTIVE"),
    )
    broker = AlpacaBroker(
        "key", "secret", "paper", client=SimpleNamespace(get_account=lambda: raw)
    )

    assert broker.account().cash == Decimal("-1250.50")


@pytest.mark.parametrize(
    "raw",
    [
        SimpleNamespace(
            cash="100000",
            equity="120000",
            buying_power="200000",
            trading_blocked=False,
            account_blocked=False,
            trade_suspended_by_user=False,
            status=_enum("ACTIVE"),
        ),
        SimpleNamespace(
            cash="100000",
            equity="120000",
            buying_power="200000",
            options_buying_power="private-malformed-value",
            trading_blocked=False,
            account_blocked=False,
            trade_suspended_by_user=False,
            status=_enum("ACTIVE"),
        ),
    ],
)
def test_account_rejects_missing_or_malformed_options_buying_power(raw):
    broker = AlpacaBroker(
        "key", "secret", "paper", client=SimpleNamespace(get_account=lambda: raw)
    )

    with pytest.raises(RuntimeError, match="account values") as error:
        broker.account()
    assert "private-malformed-value" not in str(error.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cash", None),
        ("cash", "NaN"),
        ("equity", None),
        ("equity", "0"),
        ("equity", "Infinity"),
        ("buying_power", None),
        ("buying_power", "private-invalid"),
        ("options_buying_power", "-Infinity"),
    ],
)
def test_account_rejects_invalid_required_decimal_fields(field, value):
    values = {
        "cash": "0",
        "equity": "120000",
        "buying_power": "0",
        "options_buying_power": "0",
        "trading_blocked": False,
        "account_blocked": False,
        "trade_suspended_by_user": False,
        "status": _enum("ACTIVE"),
    }
    values[field] = value
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(get_account=lambda: SimpleNamespace(**values)),
    )

    with pytest.raises(RuntimeError, match="Alpaca account values are unavailable") as error:
        broker.account()
    assert "private-invalid" not in str(error.value)


def test_asset_mapping_folds_inactive_status_into_tradability():
    client = SimpleNamespace(
        get_asset=lambda symbol: SimpleNamespace(
            symbol=symbol,
            asset_class=_enum("crypto"),
            status=_enum("inactive"),
            tradable=True,
            shortable=False,
            fractionable=True,
            min_order_size="0.0001",
            min_trade_increment="0.0001",
        )
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)

    asset = broker.asset("BTC-USD")

    assert asset.symbol == "BTC/USD"
    assert asset.asset_class == "crypto"
    assert not asset.tradable


def test_positions_preserve_long_and_short_signs():
    client = SimpleNamespace(
        get_all_positions=lambda: [
            SimpleNamespace(symbol="AAPL", side=_enum("long"), market_value="125.50"),
            SimpleNamespace(symbol="TSLA", side=_enum("short"), market_value="42.25"),
        ]
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)

    assert broker.positions() == {
        "AAPL": Decimal("125.50"),
        "TSLA": Decimal("-42.25"),
    }


def test_position_without_market_value_fails_closed():
    client = SimpleNamespace(
        get_all_positions=lambda: [
            SimpleNamespace(symbol="AAPL", side=_enum("long"), market_value=None)
        ]
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)

    with pytest.raises(RuntimeError, match="market value"):
        broker.positions()


def test_latest_price_maps_sdk_trade_price():
    client = SimpleNamespace(
        get_latest_trade=lambda symbol: SimpleNamespace(symbol=symbol, price="101.25")
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)

    assert broker.latest_price("AAPL") == Decimal("101.25")


def test_latest_crypto_price_uses_lazy_data_client(monkeypatch):
    requests = []

    class FakeRequest:
        def __init__(self, symbol_or_symbols):
            self.symbol_or_symbols = symbol_or_symbols

    class FakeCryptoDataClient:
        def __init__(self, key, secret):
            assert (key, secret) == ("key", "secret")

        def get_crypto_latest_trade(self, request):
            requests.append(request.symbol_or_symbols)
            return {"BTC/USD": SimpleNamespace(price="50000.25")}

    client = SimpleNamespace(
        get_asset=lambda symbol: SimpleNamespace(
            symbol=symbol,
            asset_class=_enum("crypto"),
            status=_enum("active"),
            tradable=True,
            shortable=False,
            fractionable=True,
            min_order_size="0.0001",
            min_trade_increment="0.0001",
        )
    )
    monkeypatch.setattr(
        "tradingagents.execution._crypto_data_client_class",
        lambda: FakeCryptoDataClient,
    )
    monkeypatch.setattr(
        "tradingagents.execution._crypto_latest_trade_request_class",
        lambda: FakeRequest,
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)

    assert broker.latest_price("BTC-USD") == Decimal("50000.25")
    assert requests == ["BTC/USD"]


def test_daily_closes_requests_one_iex_batch(monkeypatch):
    captured = []

    class FakeRequest:
        def __init__(self, **fields):
            captured.append(fields)

    bars = {
        "AAPL": [
            SimpleNamespace(
                timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc), close="100"
            )
        ],
        "MSFT": [
            SimpleNamespace(
                timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc), close="200"
            )
        ],
    }
    data_client = SimpleNamespace(get_stock_bars=lambda request: SimpleNamespace(data=bars))
    client = SimpleNamespace(
        get_clock=lambda: SimpleNamespace(
            timestamp=datetime(2026, 1, 9, tzinfo=timezone.utc)
        )
    )
    broker = AlpacaBroker("key", "secret", "paper", client=client)
    broker._stock_data_client = data_client
    monkeypatch.setattr("tradingagents.execution._stock_bars_request_class", lambda: FakeRequest)

    result = broker.daily_closes(("AAPL", "MSFT"), limit=61)

    assert len(captured) == 1
    assert captured[0]["symbol_or_symbols"] == ["AAPL", "MSFT"]
    assert captured[0]["limit"] == 61
    assert str(captured[0]["timeframe"]).lower().endswith("day")
    assert str(captured[0]["feed"]).lower().endswith("iex")
    assert result["AAPL"] == ((datetime(2026, 1, 2).date(), Decimal("100")),)
    assert result["MSFT"] == ((datetime(2026, 1, 2).date(), Decimal("200")),)


def test_daily_closes_fails_when_a_requested_symbol_is_absent(monkeypatch):
    data_client = SimpleNamespace(
        get_stock_bars=lambda request: SimpleNamespace(
            data={
                "AAPL": [
                    SimpleNamespace(
                        timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc), close="100"
                    )
                ]
            }
        )
    )
    client = SimpleNamespace(
        get_clock=lambda: SimpleNamespace(
            timestamp=datetime(2026, 1, 9, tzinfo=timezone.utc)
        )
    )
    broker = AlpacaBroker("key", "secret", "paper", client=client)
    broker._stock_data_client = data_client
    monkeypatch.setattr(
        "tradingagents.execution._stock_bars_request_class", lambda: lambda **fields: fields
    )

    with pytest.raises(RuntimeError, match="MSFT"):
        broker.daily_closes(("AAPL", "MSFT"))


@pytest.mark.parametrize("close", ["0", "-1", "NaN", "Infinity", None])
def test_daily_closes_fails_closed_for_invalid_prices(monkeypatch, close):
    bars = {
        "AAPL": [
            SimpleNamespace(timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc), close=close)
        ]
    }
    data_client = SimpleNamespace(get_stock_bars=lambda request: SimpleNamespace(data=bars))
    client = SimpleNamespace(
        get_clock=lambda: SimpleNamespace(
            timestamp=datetime(2026, 1, 9, tzinfo=timezone.utc)
        )
    )
    broker = AlpacaBroker("key", "secret", "paper", client=client)
    broker._stock_data_client = data_client
    monkeypatch.setattr(
        "tradingagents.execution._stock_bars_request_class", lambda: lambda **fields: fields
    )

    with pytest.raises(RuntimeError, match="AAPL"):
        broker.daily_closes(("AAPL",))


@pytest.mark.parametrize(
    "timestamp",
    [
        datetime(2026, 1, 2),
        _MalformedDateResult(2026, 1, 2, tzinfo=timezone.utc),
    ],
)
def test_daily_closes_fails_closed_for_malformed_timestamps(monkeypatch, timestamp):
    bars = {"AAPL": [SimpleNamespace(timestamp=timestamp, close="100")]}
    data_client = SimpleNamespace(get_stock_bars=lambda request: SimpleNamespace(data=bars))
    client = SimpleNamespace(
        get_clock=lambda: SimpleNamespace(
            timestamp=datetime(2026, 1, 9, tzinfo=timezone.utc)
        )
    )
    broker = AlpacaBroker("key", "secret", "paper", client=client)
    broker._stock_data_client = data_client
    monkeypatch.setattr(
        "tradingagents.execution._stock_bars_request_class", lambda: lambda **fields: fields
    )

    with pytest.raises(RuntimeError, match="AAPL"):
        broker.daily_closes(("AAPL",))


def test_daily_closes_wraps_timestamp_date_errors(monkeypatch):
    timestamp = _RaisingDate(2026, 1, 2, tzinfo=timezone.utc)
    bars = {"AAPL": [SimpleNamespace(timestamp=timestamp, close="100")]}
    data_client = SimpleNamespace(get_stock_bars=lambda request: SimpleNamespace(data=bars))
    client = SimpleNamespace(
        get_clock=lambda: SimpleNamespace(
            timestamp=datetime(2026, 1, 9, tzinfo=timezone.utc)
        )
    )
    broker = AlpacaBroker("key", "secret", "paper", client=client)
    broker._stock_data_client = data_client
    monkeypatch.setattr(
        "tradingagents.execution._stock_bars_request_class", lambda: lambda **fields: fields
    )

    with pytest.raises(RuntimeError, match="AAPL") as error:
        broker.daily_closes(("AAPL",))
    assert "private malformed timestamp detail" not in str(error.value)


def test_daily_closes_fails_when_any_symbol_history_is_stale(monkeypatch):
    bars = {
        "AAPL": [
            SimpleNamespace(
                timestamp=datetime(2026, 1, 3, tzinfo=timezone.utc), close="100"
            )
        ],
        "MSFT": [
            SimpleNamespace(
                timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc), close="200"
            )
        ],
    }
    data_client = SimpleNamespace(get_stock_bars=lambda request: SimpleNamespace(data=bars))
    client = SimpleNamespace(
        get_clock=lambda: SimpleNamespace(
            timestamp=datetime(2026, 1, 10, tzinfo=timezone.utc)
        )
    )
    broker = AlpacaBroker("key", "secret", "paper", client=client)
    broker._stock_data_client = data_client
    monkeypatch.setattr(
        "tradingagents.execution._stock_bars_request_class", lambda: lambda **fields: fields
    )

    with pytest.raises(RuntimeError, match="stale.*MSFT"):
        broker.daily_closes(("AAPL", "MSFT"))


def test_open_order_exposure_uses_remaining_qty_and_signed_side():
    client = SimpleNamespace(
        get_orders=lambda: [
            SimpleNamespace(symbol="AAPL", side=_enum("buy"), qty="2", filled_qty="0.5"),
            SimpleNamespace(symbol="AAPL", side=_enum("sell"), qty="1", filled_qty="0"),
            SimpleNamespace(symbol="BTC/USD", side=_enum("sell"), qty="0.001", filled_qty="0"),
        ]
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)

    assert broker.open_order_exposure({"AAPL": Decimal("100"), "BTC-USD": Decimal("50000")}) == {
        "AAPL": Decimal("50.0"),
        "BTC-USD": Decimal("-50.000"),
    }


def test_open_order_exposure_ignores_symbols_outside_priced_universe():
    client = SimpleNamespace(
        get_orders=lambda: [
            SimpleNamespace(symbol="OTHER", side=_enum("buy"), qty="2", filled_qty="0"),
            SimpleNamespace(symbol="AAPL", side=_enum("buy"), qty="1", filled_qty="0"),
        ]
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)

    assert broker.open_order_exposure({"AAPL": Decimal("100")}) == {"AAPL": Decimal("100")}


def test_open_order_exposure_ignores_malformed_order_outside_priced_universe():
    client = SimpleNamespace(
        get_orders=lambda: [
            SimpleNamespace(symbol="OTHER", side=_enum("buy"), qty="bad", filled_qty=None),
            SimpleNamespace(symbol="AAPL", side=_enum("buy"), qty="1", filled_qty="0"),
        ]
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)

    assert broker.open_order_exposure({"AAPL": Decimal("100")}) == {"AAPL": Decimal("100")}


def test_partially_filled_notional_order_uses_remaining_exposure():
    client = SimpleNamespace(
        get_orders=lambda: [
            SimpleNamespace(
                symbol="AAPL",
                side=_enum("buy"),
                notional="200",
                qty=None,
                filled_qty="0.5",
                filled_avg_price="100",
            )
        ]
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)

    assert broker.open_order_exposure({"AAPL": Decimal("100")}) == {"AAPL": Decimal("150.0")}


def test_ambiguous_notional_fill_fails_closed():
    client = SimpleNamespace(
        get_orders=lambda: [
            SimpleNamespace(
                symbol="AAPL",
                side=_enum("buy"),
                notional="200",
                qty=None,
                filled_qty="0.5",
                filled_avg_price=None,
            )
        ]
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)

    with pytest.raises(RuntimeError, match="remaining exposure"):
        broker.open_order_exposure({"AAPL": Decimal("100")})


def test_unshortable_asset_rejects_negative_target_without_submission():
    client = SimpleNamespace(submit_order=lambda **kwargs: pytest.fail("must not submit"))
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)
    asset = AssetInfo(
        "BTC/USD",
        "crypto",
        True,
        False,
        True,
        Decimal("0.0001"),
        Decimal("0.0001"),
    )
    intent = OrderIntent("BTC-USD", "sell", Decimal("500"), Decimal("-500"))
    with pytest.raises(ValueError, match="not shortable"):
        broker.prepare_order(intent, asset, Decimal("50000"), "cycle-1")


def test_crypto_negative_target_is_rejected_even_if_capability_claims_shortable():
    broker = AlpacaBroker("key", "secret", mode="paper", client=SimpleNamespace())
    malformed_crypto = AssetInfo(
        "BTC/USD",
        "crypto",
        True,
        True,
        True,
        Decimal("0.0001"),
        Decimal("0.0001"),
    )
    intent = OrderIntent("BTC-USD", "sell", Decimal("500"), Decimal("-500"))

    with pytest.raises(ValueError, match="crypto.*short"):
        broker.prepare_order(intent, malformed_crypto, Decimal("50000"), "cycle-1")


def test_prepare_order_uses_asset_time_in_force_and_stable_client_id():
    broker = AlpacaBroker("key", "secret", mode="paper", client=SimpleNamespace())
    intent = OrderIntent("AAPL", "buy", Decimal("101"), Decimal("1000"))
    equity = AssetInfo(
        "AAPL",
        "us_equity",
        True,
        True,
        True,
        Decimal("0.001"),
        Decimal("0.001"),
    )
    first = broker.prepare_order(intent, equity, Decimal("100"), "cycle-1")
    second = broker.prepare_order(intent, equity, Decimal("100"), "cycle-1")
    assert first.time_in_force == "day"
    assert first.qty == Decimal("1.01")
    assert first.client_order_id == second.client_order_id


def test_crypto_order_uses_gtc_and_trade_increment():
    broker = AlpacaBroker("key", "secret", mode="paper", client=SimpleNamespace())
    crypto = AssetInfo(
        "BTC/USD",
        "crypto",
        True,
        False,
        True,
        Decimal("0.0001"),
        Decimal("0.0001"),
    )
    spec = broker.prepare_order(
        OrderIntent("BTC-USD", "buy", Decimal("51"), Decimal("51")),
        crypto,
        Decimal("50000"),
        "cycle-1",
    )
    assert spec.symbol == "BTC/USD"
    assert spec.time_in_force == "gtc"
    assert spec.qty == Decimal("0.0010")


def test_non_fractionable_equity_rounds_down_to_whole_shares():
    broker = AlpacaBroker("key", "secret", mode="paper", client=SimpleNamespace())
    equity = AssetInfo(
        "AAPL",
        "us_equity",
        True,
        True,
        False,
        Decimal("0.001"),
        Decimal("0.001"),
    )
    spec = broker.prepare_order(
        OrderIntent("AAPL", "buy", Decimal("150"), Decimal("150")),
        equity,
        Decimal("100"),
        "cycle-1",
    )

    assert spec.qty == Decimal("1")


def test_fractionable_equity_short_rounds_down_to_whole_shares():
    broker = AlpacaBroker("key", "secret", mode="paper", client=SimpleNamespace())
    equity = AssetInfo(
        "AAPL",
        "us_equity",
        True,
        True,
        True,
        Decimal("0.001"),
        Decimal("0.001"),
    )
    spec = broker.prepare_order(
        OrderIntent("AAPL", "sell", Decimal("150"), Decimal("-150")),
        equity,
        Decimal("100"),
        "cycle-1",
    )

    assert spec.qty == Decimal("1")


@pytest.mark.parametrize("price", [Decimal("0"), Decimal("-1")])
def test_prepare_order_rejects_non_positive_prices(price):
    broker = AlpacaBroker("key", "secret", mode="paper", client=SimpleNamespace())
    asset = AssetInfo("AAPL", "us_equity", True, True, True, Decimal("0.001"), Decimal("0.001"))
    with pytest.raises(ValueError, match="positive"):
        broker.prepare_order(
            OrderIntent("AAPL", "buy", Decimal("10"), Decimal("10")),
            asset,
            price,
            "cycle-1",
        )


def test_prepare_order_rejects_untradable_asset_and_too_small_quantity():
    broker = AlpacaBroker("key", "secret", mode="paper", client=SimpleNamespace())
    intent = OrderIntent("AAPL", "buy", Decimal("0.01"), Decimal("0.01"))
    unavailable = AssetInfo(
        "AAPL", "us_equity", False, True, True, Decimal("0.001"), Decimal("0.001")
    )
    with pytest.raises(ValueError, match="not tradable"):
        broker.prepare_order(intent, unavailable, Decimal("100"), "cycle-1")

    available = AssetInfo("AAPL", "us_equity", True, True, True, Decimal("1"), Decimal("1"))
    with pytest.raises(ValueError, match="minimum order size"):
        broker.prepare_order(intent, available, Decimal("100"), "cycle-1")


def test_idempotent_submit_returns_existing_order_before_submit():
    client = SimpleNamespace(
        get_order_by_client_id=lambda client_order_id: SimpleNamespace(id="existing"),
        submit_order=lambda **kwargs: pytest.fail("must not submit a duplicate"),
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)
    spec = SimpleNamespace(client_order_id="stable-id")
    assert broker.submit_idempotent(spec) == "existing"


def test_idempotent_submit_submits_once_only_after_confirmed_absence(monkeypatch):
    submitted = []

    class NotFoundError(Exception):
        status_code = 404

    class FakeMarketOrderRequest:
        def __init__(self, **fields):
            self.fields = fields

    def missing_order(client_order_id):
        raise NotFoundError(client_order_id)

    client = SimpleNamespace(
        get_order_by_client_id=missing_order,
        submit_order=lambda order_data: (
            submitted.append(order_data) or SimpleNamespace(id="new-order")
        ),
    )
    monkeypatch.setattr(
        "tradingagents.execution._market_order_request_class",
        lambda: FakeMarketOrderRequest,
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)
    spec = OrderRequestSpec("AAPL", Decimal("1.5"), "buy", "day", "stable-client-id")

    assert broker.submit_idempotent(spec) == "new-order"
    assert submitted[0].fields == {
        "symbol": "AAPL",
        "qty": 1.5,
        "side": "buy",
        "time_in_force": "day",
        "client_order_id": "stable-client-id",
    }


def test_uncertain_lookup_failure_is_never_followed_by_submission():
    def fail_lookup(client_order_id):
        raise TimeoutError("lookup uncertain")

    client = SimpleNamespace(
        get_order_by_client_id=fail_lookup,
        submit_order=lambda order_data: pytest.fail("must not submit after uncertain lookup"),
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)
    spec = OrderRequestSpec("AAPL", Decimal("1"), "buy", "day", "stable-client-id")

    with pytest.raises(TimeoutError, match="uncertain"):
        broker.submit_idempotent(spec)


def test_timeout_after_accept_is_resolved_by_second_client_id_lookup(monkeypatch):
    lookups = iter((None, SimpleNamespace(id="accepted-order")))

    class FakeMarketOrderRequest:
        def __init__(self, **fields):
            self.fields = fields

    client = SimpleNamespace(
        get_order_by_client_id=lambda client_order_id: next(lookups),
        submit_order=lambda order_data: (_ for _ in ()).throw(TimeoutError("timed out")),
    )
    monkeypatch.setattr(
        "tradingagents.execution._market_order_request_class", lambda: FakeMarketOrderRequest
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)
    spec = OrderRequestSpec("AAPL", Decimal("1"), "buy", "day", "stable-client-id")

    assert broker.submit_idempotent(spec) == "accepted-order"


def test_submit_timeout_with_confirmed_second_lookup_absence_is_not_resubmitted(monkeypatch):
    lookups = []

    class FakeMarketOrderRequest:
        def __init__(self, **fields):
            self.fields = fields

    client = SimpleNamespace(
        get_order_by_client_id=lambda client_order_id: lookups.append(client_order_id),
        submit_order=lambda order_data: (_ for _ in ()).throw(TimeoutError("timed out")),
    )
    monkeypatch.setattr(
        "tradingagents.execution._market_order_request_class", lambda: FakeMarketOrderRequest
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)
    spec = OrderRequestSpec("AAPL", Decimal("1"), "buy", "day", "stable-client-id")

    with pytest.raises(TimeoutError, match="timed out"):
        broker.submit_idempotent(spec)
    assert lookups == ["stable-client-id", "stable-client-id"]


def test_submit_timeout_with_ambiguous_second_lookup_stays_unresolved(monkeypatch):
    calls = 0

    class FakeMarketOrderRequest:
        def __init__(self, **fields):
            self.fields = fields

    def lookup(client_order_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        raise ConnectionError("lookup ambiguous")

    client = SimpleNamespace(
        get_order_by_client_id=lookup,
        submit_order=lambda order_data: (_ for _ in ()).throw(TimeoutError("timed out")),
    )
    monkeypatch.setattr(
        "tradingagents.execution._market_order_request_class", lambda: FakeMarketOrderRequest
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)
    spec = OrderRequestSpec("AAPL", Decimal("1"), "buy", "day", "stable-client-id")

    with pytest.raises(ConnectionError, match="lookup ambiguous"):
        broker.submit_idempotent(spec)
    assert calls == 2


def test_option_order_is_limit_day_with_position_intent(monkeypatch):
    captured = []

    class FakeLimitOrderRequest:
        def __init__(self, **fields):
            captured.append(fields)

    monkeypatch.setattr(
        "tradingagents.execution._limit_order_request_class",
        lambda: FakeLimitOrderRequest,
    )
    client = SimpleNamespace(
        _base_url="https://paper-api.alpaca.markets",
        get_order_by_client_id=lambda value: None,
        submit_order=lambda order_data: SimpleNamespace(id="option-order"),
    )
    broker = AlpacaBroker("key", "secret", "paper", client=client)
    spec = OptionOrderRequestSpec(
        "AAPL261002P00300000",
        Decimal("1"),
        "sell",
        "sell_to_open",
        Decimal("3.10"),
        "day",
        "wheel-stable-id",
    )

    assert broker.submit_option_idempotent(spec) == "option-order"
    assert captured[0]["limit_price"] == 3.1
    assert str(captured[0]["position_intent"]).lower().endswith("sell_to_open")


def test_option_missing_submission_id_is_resolved_by_client_id_lookup(monkeypatch):
    lookups = iter((None, SimpleNamespace(id="resolved-order")))
    monkeypatch.setattr(
        "tradingagents.execution._limit_order_request_class",
        lambda: lambda **fields: fields,
    )
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(
            _base_url="https://paper-api.alpaca.markets",
            get_order_by_client_id=lambda value: next(lookups),
            submit_order=lambda order_data: SimpleNamespace(id=None),
        ),
    )
    spec = OptionOrderRequestSpec(
        "AAPL261002P00300000",
        Decimal("1"),
        "sell",
        "sell_to_open",
        Decimal("3.10"),
        "day",
        "ta-wheel-stable",
    )

    assert broker.submit_option_idempotent(spec) == "resolved-order"


def test_option_missing_submission_id_and_lookup_absence_raise_sanitized(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "tradingagents.execution._limit_order_request_class",
        lambda: lambda **fields: fields,
    )
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(
            _base_url="https://paper-api.alpaca.markets",
            get_order_by_client_id=lambda value: calls.append(value),
            submit_order=lambda order_data: SimpleNamespace(
                id=None, private_detail="broker-secret"
            ),
        ),
    )
    spec = OptionOrderRequestSpec(
        "AAPL261002P00300000",
        Decimal("1"),
        "sell",
        "sell_to_open",
        Decimal("3.10"),
        "day",
        "ta-wheel-stable",
    )

    with pytest.raises(RuntimeError, match="option submission.*ambiguous") as error:
        broker.submit_option_idempotent(spec)
    assert "broker-secret" not in str(error.value)
    assert calls == ["ta-wheel-stable", "ta-wheel-stable"]


def test_option_contracts_request_scope_and_normalize_snapshots(monkeypatch):
    now = datetime(2026, 9, 4, 15, 30, tzinfo=timezone.utc)
    captured_contract_requests = []
    captured_snapshot_requests = []

    class FakeContractsRequest:
        def __init__(self, **fields):
            captured_contract_requests.append(fields)

    class FakeSnapshotRequest:
        def __init__(self, **fields):
            captured_snapshot_requests.append(fields)

    raw_contract = SimpleNamespace(
        symbol="AAPL260925P00300000",
        underlying_symbol="AAPL",
        type=_enum("put"),
        status=_enum("active"),
        strike_price="300",
        expiration_date=(now + timedelta(days=21)).date(),
        open_interest="250",
    )
    raw_snapshot = SimpleNamespace(
        greeks=SimpleNamespace(delta="-0.22"),
        latest_quote=SimpleNamespace(bid_price="3.05", ask_price="3.15", timestamp=now),
    )
    client = SimpleNamespace(
        get_option_contracts=lambda request: SimpleNamespace(option_contracts=[raw_contract])
    )
    data_client = SimpleNamespace(
        get_option_snapshot=lambda request: {"AAPL260925P00300000": raw_snapshot}
    )
    monkeypatch.setattr(
        "tradingagents.execution._get_option_contracts_request_class",
        lambda: FakeContractsRequest,
    )
    monkeypatch.setattr(
        "tradingagents.execution._option_snapshot_request_class",
        lambda: FakeSnapshotRequest,
    )
    broker = AlpacaBroker("key", "secret", "paper", client=client)
    broker._option_data_client = data_client

    contracts = broker.option_contracts("AAPL", "put", now)

    assert contracts == (
        OptionContract(
            symbol="AAPL260925P00300000",
            underlying="AAPL",
            kind="put",
            strike=Decimal("300"),
            expiration=(now + timedelta(days=21)).date(),
            delta=Decimal("-0.22"),
            bid=Decimal("3.05"),
            ask=Decimal("3.15"),
            open_interest=Decimal("250"),
            quote_time=now,
        ),
    )
    request = captured_contract_requests[0]
    assert request["underlying_symbols"] == ["AAPL"]
    assert request["expiration_date_gte"] == (now + timedelta(days=14)).date()
    assert request["expiration_date_lte"] == (now + timedelta(days=28)).date()
    assert str(request["status"]).lower().endswith("active")
    assert str(request["type"]).lower().endswith("put")
    assert captured_snapshot_requests == [{"symbol_or_symbols": ["AAPL260925P00300000"]}]


def test_exact_option_contract_quote_is_not_limited_by_entry_dte(monkeypatch):
    now = datetime(2026, 9, 4, 15, 30, tzinfo=timezone.utc)
    symbol = "AAPL260911P00300000"
    monkeypatch.setattr(
        "tradingagents.execution._option_snapshot_request_class",
        lambda: lambda **fields: fields,
    )
    broker = AlpacaBroker("key", "secret", "paper", client=SimpleNamespace())
    broker._option_data_client = SimpleNamespace(
        get_option_snapshot=lambda request: {
            symbol: SimpleNamespace(
                greeks=SimpleNamespace(delta="-0.08"),
                latest_quote=SimpleNamespace(
                    bid_price="1.40", ask_price="1.50", timestamp=now
                ),
            )
        }
    )

    contract = broker.option_contract(symbol, now)

    assert contract == OptionContract(
        symbol,
        "AAPL",
        "put",
        Decimal("300"),
        (now + timedelta(days=7)).date(),
        Decimal("-0.08"),
        Decimal("1.40"),
        Decimal("1.50"),
        Decimal("0"),
        now,
    )


@pytest.mark.parametrize(
    ("open_interest", "greeks", "quote"),
    [
        (None, SimpleNamespace(delta="0.22"), SimpleNamespace(bid_price="3", ask_price="3.2", timestamp=datetime(2026, 9, 4, tzinfo=timezone.utc))),
        ("250", None, SimpleNamespace(bid_price="3", ask_price="3.2", timestamp=datetime(2026, 9, 4, tzinfo=timezone.utc))),
        ("250", SimpleNamespace(delta=None), SimpleNamespace(bid_price="3", ask_price="3.2", timestamp=datetime(2026, 9, 4, tzinfo=timezone.utc))),
        ("250", SimpleNamespace(delta="0.22"), None),
        ("250", SimpleNamespace(delta="0.22"), SimpleNamespace(bid_price=None, ask_price="3.2", timestamp=datetime(2026, 9, 4, tzinfo=timezone.utc))),
        ("250", SimpleNamespace(delta="0.22"), SimpleNamespace(bid_price="3", ask_price=None, timestamp=datetime(2026, 9, 4, tzinfo=timezone.utc))),
        ("250", SimpleNamespace(delta="0.22"), SimpleNamespace(bid_price="3", ask_price="3.2", timestamp=None)),
    ],
)
def test_option_contracts_reject_missing_required_market_data(
    monkeypatch, open_interest, greeks, quote
):
    now = datetime(2026, 9, 4, 15, 30, tzinfo=timezone.utc)
    contract = SimpleNamespace(
        symbol="AAPL260925C00300000",
        underlying_symbol="AAPL",
        type=_enum("call"),
        status=_enum("active"),
        strike_price="300",
        expiration_date=(now + timedelta(days=21)).date(),
        open_interest=open_interest,
    )
    client = SimpleNamespace(
        get_option_contracts=lambda request: SimpleNamespace(option_contracts=[contract])
    )
    broker = AlpacaBroker("key", "secret", "paper", client=client)
    broker._option_data_client = SimpleNamespace(
        get_option_snapshot=lambda request: {
            contract.symbol: SimpleNamespace(greeks=greeks, latest_quote=quote)
        }
    )
    monkeypatch.setattr(
        "tradingagents.execution._get_option_contracts_request_class",
        lambda: lambda **fields: fields,
    )
    monkeypatch.setattr(
        "tradingagents.execution._option_snapshot_request_class",
        lambda: lambda **fields: fields,
    )

    with pytest.raises(RuntimeError, match="option (contract|snapshot)"):
        broker.option_contracts("AAPL", "call", now)


@pytest.mark.parametrize(
    "changes",
    [
        {"underlying_symbol": "MSFT"},
        {"type": _enum("call")},
        {"status": _enum("inactive")},
        {"expiration_date": datetime(2026, 9, 10).date()},
        {"expiration_date": datetime(2026, 10, 10).date()},
        {"symbol": "MSFT260925P00300000"},
        {"symbol": "AAPL260925C00300000"},
        {"symbol": "AAPL260925P00301000"},
    ],
)
def test_option_contracts_reject_inconsistent_broker_items(monkeypatch, changes):
    now = datetime(2026, 9, 4, 15, 30, tzinfo=timezone.utc)
    fields = {
        "symbol": "AAPL260925P00300000",
        "underlying_symbol": "AAPL",
        "type": _enum("put"),
        "status": _enum("active"),
        "strike_price": "300",
        "expiration_date": (now + timedelta(days=21)).date(),
        "open_interest": "250",
    }
    fields.update(changes)
    contract = SimpleNamespace(**fields)
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(
            get_option_contracts=lambda request: SimpleNamespace(option_contracts=[contract])
        ),
    )
    broker._option_data_client = SimpleNamespace(
        get_option_snapshot=lambda request: {
            contract.symbol: SimpleNamespace(
                greeks=SimpleNamespace(delta="-0.22"),
                latest_quote=SimpleNamespace(
                    bid_price="3", ask_price="3.2", timestamp=now
                ),
            )
        }
    )
    monkeypatch.setattr(
        "tradingagents.execution._get_option_contracts_request_class",
        lambda: lambda **values: values,
    )
    monkeypatch.setattr(
        "tradingagents.execution._option_snapshot_request_class",
        lambda: lambda **values: values,
    )

    with pytest.raises(RuntimeError, match="inconsistent option contract"):
        broker.option_contracts("AAPL", "put", now)


def test_wheel_positions_and_orders_map_equities_options_and_open_orders(monkeypatch):
    submitted_at = datetime(2026, 9, 4, 14, 0, tzinfo=timezone.utc)
    positions = [
        SimpleNamespace(
            symbol="AAPL",
            asset_class=_enum("us_equity"),
            side=_enum("long"),
            qty="125",
            avg_entry_price="190",
            current_price="205",
        ),
        SimpleNamespace(
            symbol="AAPL260925C00300000",
            asset_class=_enum("us_option"),
            side=_enum("short"),
            qty="1",
            avg_entry_price="4.20",
            current_price="3.10",
        ),
    ]
    orders = [
        SimpleNamespace(
            id="order-id",
            client_order_id="ta-wheel-owned",
            symbol="AAPL260925P00195000",
            asset_class=_enum("us_option"),
            position_intent=_enum("sell_to_open"),
            qty="3",
            filled_qty="1",
            submitted_at=submitted_at,
        )
    ]
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(
            get_all_positions=lambda: positions,
            get_orders=lambda: orders,
        ),
    )
    monkeypatch.setattr(
        broker,
        "option_snapshot",
        lambda symbols: {
            "AAPL260925C00300000": (
                Decimal("0.21"),
                Decimal("3"),
                Decimal("3.2"),
                submitted_at,
            )
        },
    )

    equities, option_positions, option_orders = broker.wheel_positions_and_orders()

    assert equities == (EquityPosition("AAPL", Decimal("125"), Decimal("190"), Decimal("205")),)
    assert option_positions == (
        OptionPosition(
            "AAPL260925C00300000",
            "AAPL",
            "call",
            Decimal("-1"),
            Decimal("4.20"),
            Decimal("0.21"),
        ),
    )
    assert option_orders == (
        OptionOpenOrder(
            "AAPL260925P00195000",
            "AAPL",
            "put",
            "sell_to_open",
            Decimal("3"),
            Decimal("1"),
            Decimal("195"),
            "order-id",
            "ta-wheel-owned",
            submitted_at,
        ),
    )


@pytest.mark.parametrize("asset_class", [None, _enum("unknown")])
def test_wheel_positions_reject_unclassifiable_records(asset_class):
    raw = SimpleNamespace(
        symbol="private-position-symbol",
        asset_class=asset_class,
        side=_enum("long"),
        qty="1",
        avg_entry_price="1",
        current_price="1",
    )
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(get_all_positions=lambda: [raw], get_orders=lambda: []),
    )

    with pytest.raises(RuntimeError, match="position record") as error:
        broker.wheel_positions_and_orders()
    assert "private-position-symbol" not in str(error.value)


def test_wheel_positions_reject_missing_quantity():
    raw = SimpleNamespace(
        symbol="private-position-symbol",
        asset_class=_enum("us_equity"),
        side=_enum("long"),
        qty=None,
        avg_entry_price="1",
        current_price="1",
    )
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(get_all_positions=lambda: [raw], get_orders=lambda: []),
    )

    with pytest.raises(RuntimeError, match="position record") as error:
        broker.wheel_positions_and_orders()
    assert "private-position-symbol" not in str(error.value)


def test_wheel_option_positions_reject_fractional_contract_quantity(monkeypatch):
    raw = SimpleNamespace(
        symbol="AAPL260925C00300000",
        asset_class=_enum("us_option"),
        side=_enum("short"),
        qty="1.5",
        avg_entry_price="4.20",
        current_price="3.10",
    )
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(get_all_positions=lambda: [raw], get_orders=lambda: []),
    )
    monkeypatch.setattr(
        broker,
        "option_snapshot",
        lambda symbols: {
            raw.symbol: (
                Decimal("0.21"),
                Decimal("3"),
                Decimal("3.2"),
                datetime(2026, 9, 4, tzinfo=timezone.utc),
            )
        },
    )

    with pytest.raises(RuntimeError, match="option position"):
        broker.wheel_positions_and_orders()


@pytest.mark.parametrize("side", [_enum("long"), _enum("short")])
def test_wheel_option_positions_reject_negative_raw_quantity(monkeypatch, side):
    raw = SimpleNamespace(
        symbol="AAPL260925C00300000",
        asset_class=_enum("us_option"),
        side=side,
        qty="-1",
        avg_entry_price="4.20",
        current_price="3.10",
    )
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(get_all_positions=lambda: [raw], get_orders=lambda: []),
    )
    monkeypatch.setattr(
        broker,
        "option_snapshot",
        lambda symbols: {
            raw.symbol: (
                Decimal("0.21"),
                Decimal("3"),
                Decimal("3.2"),
                datetime(2026, 9, 4, tzinfo=timezone.utc),
            )
        },
    )

    with pytest.raises(RuntimeError, match="option position"):
        broker.wheel_positions_and_orders()


@pytest.mark.parametrize(
    ("asset_class", "symbol"),
    [
        (_enum("us_equity"), None),
        (_enum("us_equity"), "   "),
        (_enum("us_option"), None),
        (_enum("us_option"), ""),
    ],
)
def test_wheel_positions_reject_missing_or_blank_symbols(asset_class, symbol):
    raw = SimpleNamespace(
        symbol=symbol,
        asset_class=asset_class,
        side=_enum("long"),
        qty="1",
        avg_entry_price="1",
        current_price="1",
    )
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(get_all_positions=lambda: [raw], get_orders=lambda: []),
    )

    with pytest.raises(RuntimeError, match="position record"):
        broker.wheel_positions_and_orders()


@pytest.mark.parametrize("asset_class", [None, _enum("unknown")])
def test_wheel_orders_reject_unclassifiable_records(asset_class):
    raw = SimpleNamespace(
        id="private-order-id",
        client_order_id="ta-wheel-owned",
        symbol="AAPL260925P00195000",
        asset_class=asset_class,
        position_intent=_enum("sell_to_open"),
        qty="1",
        filled_qty="0",
        submitted_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
    )
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(get_all_positions=lambda: [], get_orders=lambda: [raw]),
    )

    with pytest.raises(RuntimeError, match="order record") as error:
        broker.wheel_positions_and_orders()
    assert "private-order-id" not in str(error.value)


def test_wheel_orders_reject_missing_quantity():
    raw = SimpleNamespace(
        id="private-order-id",
        client_order_id="ta-wheel-owned",
        symbol="AAPL260925P00195000",
        asset_class=_enum("us_option"),
        position_intent=_enum("sell_to_open"),
        qty=None,
        filled_qty="0",
        submitted_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
    )
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(get_all_positions=lambda: [], get_orders=lambda: [raw]),
    )

    with pytest.raises(RuntimeError, match="order record") as error:
        broker.wheel_positions_and_orders()
    assert "private-order-id" not in str(error.value)


@pytest.mark.parametrize(
    ("qty", "filled_qty"),
    [
        ("NaN", "0"),
        ("1", "Infinity"),
        ("0", "0"),
        ("-1", "0"),
        ("1", "-1"),
        ("1.5", "0"),
        ("2", "0.5"),
        ("1", "2"),
    ],
)
def test_wheel_option_orders_reject_invalid_contract_quantities(qty, filled_qty):
    raw = SimpleNamespace(
        id="private-order-id",
        client_order_id="ta-wheel-owned",
        symbol="AAPL260925P00195000",
        asset_class=_enum("us_option"),
        position_intent=_enum("sell_to_open"),
        qty=qty,
        filled_qty=filled_qty,
        submitted_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
    )
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(get_all_positions=lambda: [], get_orders=lambda: [raw]),
    )

    with pytest.raises(RuntimeError, match="option order record"):
        broker.wheel_positions_and_orders()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("symbol", None),
        ("symbol", "  "),
        ("position_intent", None),
        ("position_intent", ""),
        ("position_intent", _enum("unknown")),
        ("id", None),
        ("id", ""),
        ("client_order_id", None),
        ("client_order_id", "   "),
        ("submitted_at", None),
    ],
)
def test_wheel_orders_reject_missing_required_stale_order_fields(field, value):
    fields = {
        "id": "order-id",
        "client_order_id": "ta-wheel-owned",
        "symbol": "AAPL260925P00195000",
        "asset_class": _enum("us_option"),
        "position_intent": _enum("sell_to_open"),
        "qty": "1",
        "filled_qty": "0",
        "submitted_at": datetime(2026, 9, 4, tzinfo=timezone.utc),
    }
    fields[field] = value
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(
            get_all_positions=lambda: [],
            get_orders=lambda: [SimpleNamespace(**fields)],
        ),
    )

    with pytest.raises(RuntimeError, match="option order record"):
        broker.wheel_positions_and_orders()


def test_absent_option_order_intent_cannot_disappear_from_reservations():
    raw = SimpleNamespace(
        id="order-id",
        client_order_id="ta-wheel-owned",
        symbol="AAPL260925P00195000",
        asset_class=_enum("us_option"),
        position_intent=None,
        qty="1",
        filled_qty="0",
        submitted_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
    )
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(get_all_positions=lambda: [], get_orders=lambda: [raw]),
    )

    with pytest.raises(RuntimeError, match="option order record"):
        broker.wheel_positions_and_orders()


def test_wheel_option_position_rejects_missing_delta(monkeypatch):
    raw = SimpleNamespace(
        symbol="AAPL260925C00300000",
        asset_class=_enum("us_option"),
        side=_enum("short"),
        qty="1",
        avg_entry_price="4.20",
        current_price="3.10",
    )
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(get_all_positions=lambda: [raw], get_orders=lambda: []),
    )
    monkeypatch.setattr(
        broker,
        "option_snapshot",
        lambda symbols: {
            raw.symbol: (
                None,
                Decimal("3"),
                Decimal("3.2"),
                datetime(2026, 9, 4, tzinfo=timezone.utc),
            )
        },
    )

    with pytest.raises(RuntimeError, match="option position") as error:
        broker.wheel_positions_and_orders()
    assert raw.symbol not in str(error.value)


def test_prepare_option_order_is_day_only_and_has_deterministic_wheel_id():
    broker = AlpacaBroker("key", "secret", "paper", client=SimpleNamespace())
    intent = OptionIntent(
        "AAPL260925P00195000",
        "AAPL",
        "put",
        "sell",
        "sell_to_open",
        Decimal("1"),
        Decimal("3.10"),
        Decimal("-0.22"),
    )

    spec = broker.prepare_option_order(intent, "cycle-1")

    identity = "cycle-1|AAPL260925P00195000|sell|sell_to_open|1|3.10"
    expected_id = "ta-wheel-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
    assert spec == OptionOrderRequestSpec(
        "AAPL260925P00195000",
        Decimal("1"),
        "sell",
        "sell_to_open",
        Decimal("3.10"),
        "day",
        expected_id,
    )


def test_prepare_option_order_rejects_fractional_contract_quantity():
    broker = AlpacaBroker("key", "secret", "paper", client=SimpleNamespace())
    intent = OptionIntent(
        "AAPL260925P00195000",
        "AAPL",
        "put",
        "sell",
        "sell_to_open",
        Decimal("1.5"),
        Decimal("3.10"),
        Decimal("-0.22"),
    )

    with pytest.raises(ValueError, match="positive whole number"):
        broker.prepare_option_order(intent, "cycle-1")


@pytest.mark.parametrize("price", [Decimal("0"), Decimal("-1")])
def test_option_submission_rejects_non_positive_limit(price):
    broker = AlpacaBroker("key", "secret", "paper", client=SimpleNamespace())
    spec = OptionOrderRequestSpec(
        "AAPL261002P00300000",
        Decimal("1"),
        "sell",
        "sell_to_open",
        price,
        "day",
        "id",
    )
    with pytest.raises(ValueError, match="limit price"):
        broker.submit_option_idempotent(spec)


def test_live_options_require_separate_ack_before_lookup():
    calls = []
    broker = AlpacaBroker(
        "key",
        "secret",
        "live",
        client=SimpleNamespace(get_order_by_client_id=lambda value: calls.append("lookup")),
        live_ack="I_UNDERSTAND_LIVE_ORDERS",
        live_options_ack="",
    )
    spec = OptionOrderRequestSpec(
        "AAPL261002P00300000",
        Decimal("1"),
        "sell",
        "sell_to_open",
        Decimal("3.10"),
        "day",
        "wheel-live-id",
    )
    with pytest.raises(ValueError, match="live options acknowledgment"):
        broker.submit_option_idempotent(spec)
    assert calls == []


def test_option_submission_rejects_non_day_or_fractional_contract_before_lookup():
    calls = []
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(get_order_by_client_id=lambda value: calls.append(value)),
    )
    invalid_specs = (
        OptionOrderRequestSpec(
            "AAPL261002P00300000", Decimal("1"), "sell", "sell_to_open", Decimal("3"), "gtc", "id"
        ),
        OptionOrderRequestSpec(
            "AAPL261002P00300000", Decimal("0.5"), "sell", "sell_to_open", Decimal("3"), "day", "id"
        ),
    )

    for spec in invalid_specs:
        with pytest.raises(ValueError):
            broker.submit_option_idempotent(spec)
    assert calls == []


def test_option_submission_rejects_side_intent_mismatch_before_lookup():
    calls = []
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(get_order_by_client_id=lambda value: calls.append(value)),
    )
    spec = OptionOrderRequestSpec(
        "AAPL261002P00300000",
        Decimal("1"),
        "buy",
        "sell_to_open",
        Decimal("3"),
        "day",
        "id",
    )

    with pytest.raises(ValueError, match="position intent"):
        broker.submit_option_idempotent(spec)
    assert calls == []


@pytest.mark.parametrize(
    ("mode", "endpoint", "live_ack", "live_options_ack"),
    [
        ("paper", "https://paper-api.alpaca.markets", "", ""),
        (
            "live",
            "https://api.alpaca.markets",
            LIVE_ACKNOWLEDGMENT,
            LIVE_OPTIONS_ACKNOWLEDGMENT,
        ),
    ],
)
def test_option_submit_allows_only_matching_authoritative_endpoint(
    monkeypatch, mode, endpoint, live_ack, live_options_ack
):
    calls = []
    monkeypatch.setattr(
        "tradingagents.execution._limit_order_request_class",
        lambda: lambda **fields: fields,
    )
    broker = AlpacaBroker(
        "key",
        "secret",
        mode,
        client=SimpleNamespace(
            _base_url=endpoint,
            get_order_by_client_id=lambda value: None,
            submit_order=lambda order_data: calls.append(order_data)
            or SimpleNamespace(id="option-order"),
        ),
        live_ack=live_ack,
        live_options_ack=live_options_ack,
    )
    spec = OptionOrderRequestSpec(
        "AAPL261002P00300000",
        Decimal("1"),
        "sell",
        "sell_to_open",
        Decimal("3.10"),
        "day",
        "ta-wheel-stable",
    )

    assert broker.submit_option_idempotent(spec) == "option-order"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "endpoint",
    ["https://api.alpaca.markets", None],
    ids=["mismatch", "unknown"],
)
def test_option_submit_rejects_unverified_endpoint_without_mutation(monkeypatch, endpoint):
    calls = []
    monkeypatch.setattr(
        "tradingagents.execution._limit_order_request_class",
        lambda: lambda **fields: fields,
    )
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(
            _base_url=endpoint,
            get_order_by_client_id=lambda value: None,
            submit_order=lambda order_data: calls.append(order_data),
        ),
    )
    spec = OptionOrderRequestSpec(
        "AAPL261002P00300000",
        Decimal("1"),
        "sell",
        "sell_to_open",
        Decimal("3.10"),
        "day",
        "ta-wheel-stable",
    )

    with pytest.raises(RuntimeError, match="trading endpoint"):
        broker.submit_option_idempotent(spec)
    assert calls == []


def test_cancel_rejects_orders_not_owned_by_the_wheel():
    calls = []
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(cancel_order_by_id=lambda value: calls.append(value)),
    )
    with pytest.raises(ValueError, match="not owned"):
        broker.cancel_stale_option_order("order-id", "manual-order")
    assert calls == []


def test_cancel_allows_only_wheel_owned_order():
    calls = []
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(
            _base_url="https://paper-api.alpaca.markets",
            cancel_order_by_id=lambda value: calls.append(value),
        ),
    )

    broker.cancel_stale_option_order("order-id", "ta-wheel-owned")

    assert calls == ["order-id"]


@pytest.mark.parametrize("options_ack", ["", "wrong"])
def test_live_cancel_requires_exact_options_acknowledgment(options_ack):
    calls = []
    broker = AlpacaBroker(
        "key",
        "secret",
        "live",
        client=SimpleNamespace(cancel_order_by_id=lambda value: calls.append(value)),
        live_ack=LIVE_ACKNOWLEDGMENT,
        live_options_ack=options_ack,
    )

    with pytest.raises(ValueError, match="live options acknowledgment"):
        broker.cancel_stale_option_order("order-id", "ta-wheel-owned")

    assert calls == []


def test_live_cancel_with_both_acknowledgments_reaches_broker():
    calls = []
    broker = AlpacaBroker(
        "key",
        "secret",
        "live",
        client=SimpleNamespace(
            _base_url="https://api.alpaca.markets",
            cancel_order_by_id=lambda value: calls.append(value),
        ),
        live_ack=LIVE_ACKNOWLEDGMENT,
        live_options_ack=LIVE_OPTIONS_ACKNOWLEDGMENT,
    )

    broker.cancel_stale_option_order("order-id", "ta-wheel-owned")

    assert calls == ["order-id"]


@pytest.mark.parametrize(
    "endpoint",
    ["https://api.alpaca.markets", None],
    ids=["mismatch", "unknown"],
)
def test_option_cancel_rejects_unverified_endpoint_without_mutation(endpoint):
    calls = []
    broker = AlpacaBroker(
        "key",
        "secret",
        "paper",
        client=SimpleNamespace(
            _base_url=endpoint,
            cancel_order_by_id=lambda value: calls.append(value),
        ),
    )

    with pytest.raises(RuntimeError, match="trading endpoint"):
        broker.cancel_stale_option_order("order-id", "ta-wheel-owned")
    assert calls == []
