from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from tradingagents.allocation import OrderIntent
from tradingagents.execution import (
    AlpacaBroker,
    AssetInfo,
    OrderRequestSpec,
    alpaca_symbol,
    validate_execution_mode,
)


def _enum(value):
    return SimpleNamespace(value=value)


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
        buying_power="1000.50",
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
    assert broker.account().buying_power == Decimal("1000.50")
    assert broker.account().status == "ACTIVE"

    active.trading_blocked = True
    with pytest.raises(RuntimeError, match="blocked"):
        broker.account()


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

    assert broker.open_order_exposure({}) == {"AAPL": Decimal("150.0")}


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
        broker.open_order_exposure({})


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
