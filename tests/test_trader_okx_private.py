"""The signed OKX client of the demo account (ADR 0008): it signs as OKX specifies,
only ever reaches simulated trading, keeps the credentials out of everything it
prints, and reads OKX's answers into the account's units. Every answer here is a
recorded shape of the real endpoint; nothing touches the network."""

import json

import pytest
import requests
from typer.testing import CliRunner

from trader import __main__ as cli, okx_private
from trader.okx import OKXError
from trader.okx_private import (
    DUPLICATE_CLIENT_ID,
    Balance,
    ExchangeFill,
    ExchangePosition,
    FundingBill,
    OKXCredentials,
    OKXPrivate,
    OKXPrivateError,
    StopOrder,
    sign,
    timestamp,
)
from trader.settings import Settings

CREDS = OKXCredentials(key="key-123", secret="test-secret", passphrase="pass-word")
NOW = 1_767_225_600.0  # 2026-01-01 00:00:00 UTC
STAMP = "2026-01-01T00:00:00.000Z"
T0 = 1_767_225_600_000


class FakeResponse:
    def __init__(self, body, status_code=200):
        self.body = body
        self.status_code = status_code

    def json(self):
        if isinstance(self.body, str):
            raise ValueError("not JSON")
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


class FakeSession:
    """Answers each (method, path-with-query) once: a list is the ``data`` of a
    successful answer, a dict the whole body, a FakeResponse the answer as is, an
    Exception is raised. ``failures`` go out first whatever is asked. Records calls."""

    def __init__(self, answers=(), failures=()):
        self.answers = list(answers)
        self.failures = list(failures)
        self.calls = []

    def request(self, method, url, data, headers, timeout):
        assert timeout == 10
        path = url.removeprefix(okx_private.BASE_URL)
        self.calls.append((method, path, data, headers))
        if self.failures:
            answer = self.failures.pop(0)
        else:
            key, answer = self.answers.pop(0)
            assert key == (method, path), f"expected {key}, got {(method, path)}"
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, FakeResponse):
            return answer
        body = answer if isinstance(answer, dict) else {"code": "0", "msg": "", "data": answer}
        return FakeResponse(body)


def client(answers=(), failures=()):
    session = FakeSession(answers, failures)
    return OKXPrivate(CREDS, session=session, clock=lambda: NOW), session


@pytest.fixture
def sleeps(monkeypatch):
    pauses = []
    monkeypatch.setattr(okx_private.time, "sleep", pauses.append)
    return pauses


# -- signing and safety ---------------------------------------------------------


def test_the_signature_matches_okx_known_vectors():
    # Base64(HMAC-SHA256(secret, timestamp + method + path + body)), computed independently.
    assert sign("test-secret", STAMP, "GET", "/api/v5/account/balance?ccy=USDT") == (
        "q88nhwRRgbZed82etcHsHMp56hE0ne7uqeezHdX2B0s="
    )
    body = (
        '{"instId":"BTC-USDT-SWAP","tdMode":"cross","side":"buy","ordType":"market",'
        '"sz":"2","clOrdId":"trd1btc","reduceOnly":false}'
    )
    assert sign("test-secret", STAMP, "POST", "/api/v5/trade/order", body) == (
        "mrKZrPsPAocoKe5D+Rscb9d6pDLmWma4u+I2Qdh/Vp4="
    )


def test_the_timestamp_is_iso_8601_utc_with_milliseconds():
    assert timestamp(NOW) == STAMP
    assert timestamp(NOW + 1.2345) == "2026-01-01T00:00:01.234Z"


def test_every_request_is_signed_over_its_query_and_body_and_marked_simulated():
    okx, session = client([
        (("GET", "/api/v5/account/balance?ccy=USDT"), [{"details": []}]),
        (("POST", "/api/v5/trade/order"), [{"ordId": "1", "clOrdId": "trd1btc", "sCode": "0"}]),
    ])
    okx.balance()
    okx.place_market("BTC-USDT-SWAP", 2, "trd1btc")
    (_, _, get_body, get_headers), (_, _, post_body, post_headers) = session.calls
    assert get_body is None
    assert get_headers["OK-ACCESS-SIGN"] == "q88nhwRRgbZed82etcHsHMp56hE0ne7uqeezHdX2B0s="
    assert post_body == (
        '{"instId":"BTC-USDT-SWAP","tdMode":"cross","side":"buy","ordType":"market",'
        '"sz":"2","clOrdId":"trd1btc","reduceOnly":false}'
    )
    assert post_headers["OK-ACCESS-SIGN"] == "mrKZrPsPAocoKe5D+Rscb9d6pDLmWma4u+I2Qdh/Vp4="
    for headers in (get_headers, post_headers):
        assert headers["OK-ACCESS-KEY"] == "key-123"
        assert headers["OK-ACCESS-PASSPHRASE"] == "pass-word"
        assert headers["OK-ACCESS-TIMESTAMP"] == STAMP
        assert headers["x-simulated-trading"] == "1"
        assert headers["Content-Type"] == "application/json"


def test_the_live_environment_cannot_be_reached():
    with pytest.raises(ValueError, match="only OKX simulated trading"):
        OKXPrivate(CREDS, session=FakeSession(), simulated=False)


def test_credentials_and_client_never_print_the_secret():
    for text in (repr(CREDS), str(CREDS), f"{CREDS}", repr(client()[0])):
        assert "test-secret" not in text and "pass-word" not in text and "key-123" not in text
    assert repr(CREDS) == "OKXCredentials(***)"


def test_an_okx_error_names_the_path_and_code_but_nothing_of_the_request_headers():
    okx, _ = client([
        (("GET", "/api/v5/account/config"), {"code": "50111", "msg": "Invalid OK-ACCESS-KEY", "data": []}),
    ])
    with pytest.raises(OKXPrivateError) as info:
        okx.account_config()
    assert info.value.code == "50111"
    assert str(info.value) == "/api/v5/account/config failed with code 50111: Invalid OK-ACCESS-KEY"
    assert isinstance(info.value, OKXError)


# -- environment -----------------------------------------------------------------


def test_credentials_come_from_the_three_variables_or_not_at_all(monkeypatch):
    for name in ("TRADER_OKX_DEMO_KEY", "TRADER_OKX_DEMO_SECRET", "TRADER_OKX_DEMO_PASSPHRASE"):
        monkeypatch.delenv(name, raising=False)
    assert OKXCredentials.from_env() is None
    monkeypatch.setenv("TRADER_OKX_DEMO_KEY", " key-123 ")
    monkeypatch.setenv("TRADER_OKX_DEMO_SECRET", "test-secret")
    with pytest.raises(ValueError) as info:
        OKXCredentials.from_env()
    assert str(info.value) == (
        "TRADER_OKX_DEMO_PASSPHRASE must be set along with the other OKX variables"
    )
    monkeypatch.setenv("TRADER_OKX_DEMO_PASSPHRASE", "pass-word")
    assert OKXCredentials.from_env() == CREDS


def test_settings_carry_the_demo_credentials_masked(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADER_HOME", str(tmp_path))
    for name in ("TRADER_OKX_DEMO_KEY", "TRADER_OKX_DEMO_SECRET", "TRADER_OKX_DEMO_PASSPHRASE"):
        monkeypatch.delenv(name, raising=False)
    assert Settings.from_env().okx_demo is None
    monkeypatch.setenv("TRADER_OKX_DEMO_KEY", "key-123")
    monkeypatch.setenv("TRADER_OKX_DEMO_SECRET", "test-secret")
    monkeypatch.setenv("TRADER_OKX_DEMO_PASSPHRASE", "pass-word")
    settings = Settings.from_env()
    assert settings.okx_demo == CREDS
    assert "test-secret" not in repr(settings)


# -- transport -------------------------------------------------------------------


def test_transient_failures_are_retried_with_the_public_clients_pauses(sleeps):
    okx, session = client(
        [(("GET", "/api/v5/account/config"),
          [{"posMode": "net_mode", "acctLv": "2", "perm": "read_only,trade"}])],
        failures=[requests.ConnectionError("reset"), FakeResponse({"code": "50011"}, 429)],
    )
    config = okx.account_config()
    assert (config.position_mode, config.account_level, config.permissions) == (
        "net_mode", "2", "read_only,trade"
    )
    assert sleeps == [1, 2]
    assert len(session.calls) == 3


def test_the_last_transient_failure_is_raised_as_is(sleeps):
    okx, _ = client(failures=[requests.Timeout("slow")] * 3)
    with pytest.raises(requests.Timeout):
        okx.account_config()
    assert sleeps == [1, 2]


def test_a_non_json_answer_raises_through_its_status():
    okx, _ = client([(("GET", "/api/v5/account/config"), FakeResponse("<html>forbidden</html>", 403))])
    with pytest.raises(requests.HTTPError, match="403"):
        okx.account_config()


def test_an_order_that_okx_rejects_raises_its_item_code():
    okx, _ = client([(("POST", "/api/v5/trade/order"), {
        "code": "1", "msg": "All operations failed",
        "data": [{"clOrdId": "trd1btc", "ordId": "", "sCode": "51016",
                  "sMsg": "Client order ID already exists"}],
    })])
    with pytest.raises(OKXPrivateError) as info:
        okx.place_market("BTC-USDT-SWAP", 2, "trd1btc")
    assert info.value.code == DUPLICATE_CLIENT_ID
    assert "Client order ID already exists" in str(info.value)


# -- account ---------------------------------------------------------------------


def test_balance_reads_the_usdt_row_and_is_zero_without_one():
    okx, _ = client([
        (("GET", "/api/v5/account/balance?ccy=USDT"), [{"totalEq": "10012.5", "details": [
            {"ccy": "USDT", "eq": "10012.5", "cashBal": "10000", "availBal": "9700.25", "upl": "12.5"},
        ]}]),
        (("GET", "/api/v5/account/balance?ccy=USDT"), [{"totalEq": "0", "details": []}]),
    ])
    assert okx.balance() == Balance("USDT", 10012.5, 10000.0, 9700.25, 12.5)
    assert okx.balance() == Balance("USDT", 0.0, 0.0, 0.0, 0.0)


def test_positions_are_signed_by_side_and_skip_the_closed_ones():
    okx, session = client([(("GET", "/api/v5/account/positions?instType=SWAP"), [
        {"instId": "BTC-USDT-SWAP", "pos": "3", "posSide": "net", "avgPx": "80000", "upl": "1.5",
         "lever": "3", "mgnMode": "cross", "liqPx": "54000.5", "uTime": str(T0)},
        {"instId": "ETH-USDT-SWAP", "pos": "-10", "posSide": "net", "avgPx": "3000", "upl": "",
         "lever": "3", "mgnMode": "cross", "liqPx": "", "uTime": str(T0 + 1)},
        {"instId": "SOL-USDT-SWAP", "pos": "0", "posSide": "net", "avgPx": "", "upl": "",
         "lever": "3", "mgnMode": "cross", "liqPx": "", "uTime": str(T0 + 2)},
        {"instId": "SOL-USDT-SWAP", "pos": "4", "posSide": "short", "avgPx": "150", "upl": "0",
         "lever": "2", "mgnMode": "isolated", "liqPx": "", "uTime": str(T0 + 3)},
    ])])
    assert okx.positions() == [
        ExchangePosition("BTC-USDT-SWAP", 3.0, 80000.0, 1.5, 3.0, "cross", 54000.5, T0),
        ExchangePosition("ETH-USDT-SWAP", -10.0, 3000.0, 0.0, 3.0, "cross", None, T0 + 1),
        ExchangePosition("SOL-USDT-SWAP", -4.0, 150.0, 0.0, 2.0, "isolated", None, T0 + 3),
    ]
    assert session.calls[0][1] == "/api/v5/account/positions?instType=SWAP"


def test_account_setup_posts_net_mode_and_leverage():
    okx, session = client([
        (("POST", "/api/v5/account/set-position-mode"), [{"posMode": "net_mode"}]),
        (("POST", "/api/v5/account/set-leverage"),
         [{"instId": "BTC-USDT-SWAP", "lever": "3", "mgnMode": "cross"}]),
    ])
    okx.set_position_mode()
    okx.set_leverage("BTC-USDT-SWAP", 3)
    assert json.loads(session.calls[0][2]) == {"posMode": "net_mode"}
    assert json.loads(session.calls[1][2]) == {"instId": "BTC-USDT-SWAP", "lever": "3", "mgnMode": "cross"}


# -- orders ----------------------------------------------------------------------


def test_a_market_order_sells_negative_counts_reduce_only_and_returns_the_order_id():
    okx, session = client([
        (("POST", "/api/v5/trade/order"), [{"ordId": "9001", "clOrdId": "trd1eth", "sCode": "0"}]),
    ])
    assert okx.place_market("ETH-USDT-SWAP", -0.5, "trd1eth", reduce_only=True) == "9001"
    assert json.loads(session.calls[0][2]) == {
        "instId": "ETH-USDT-SWAP", "tdMode": "cross", "side": "sell", "ordType": "market",
        "sz": "0.5", "clOrdId": "trd1eth", "reduceOnly": True,
    }
    with pytest.raises(ValueError):
        okx.place_market("ETH-USDT-SWAP", 0, "trd2eth")


def test_an_order_is_read_by_client_or_exchange_id():
    row = {"ordId": "9001", "clOrdId": "trd1eth", "instId": "ETH-USDT-SWAP", "state": "filled",
           "side": "sell", "sz": "0.5", "accFillSz": "0.5", "avgPx": "3001.5", "fee": "-0.75",
           "algoClOrdId": "", "uTime": str(T0 + 500)}
    okx, session = client([
        (("GET", "/api/v5/trade/order?instId=ETH-USDT-SWAP&clOrdId=trd1eth"), [row]),
        (("GET", "/api/v5/trade/order?instId=ETH-USDT-SWAP&ordId=9001"),
         [{**row, "state": "live", "accFillSz": "0", "avgPx": "", "fee": "", "algoClOrdId": "stp1eth"}]),
    ])
    order = okx.order("ETH-USDT-SWAP", client_id="trd1eth")
    assert (order.order_id, order.state, order.filled, order.avg_price, order.fee, order.updated) == (
        "9001", "filled", 0.5, 3001.5, -0.75, T0 + 500
    )
    pending = okx.order("ETH-USDT-SWAP", order_id="9001")
    assert (pending.state, pending.filled, pending.avg_price, pending.fee, pending.algo_client_id) == (
        "live", 0.0, None, 0.0, "stp1eth"
    )
    with pytest.raises(ValueError):
        okx.order("ETH-USDT-SWAP")


def fill_row(bill_id, ts, **over):
    row = {"billId": str(bill_id), "tradeId": f"t{bill_id}", "ordId": "9001", "clOrdId": "trd1btc",
           "instId": "BTC-USDT-SWAP", "side": "buy", "fillSz": "1", "fillPx": "80000", "fee": "-0.4",
           "ts": str(ts)}
    row.update(over)
    return row


def fills_path(limit, after=None):
    path = f"/api/v5/trade/fills-history?instType=SWAP&begin={T0}&end={T0 + 1000}&limit={limit}"
    return path if after is None else f"{path}&after={after}"


def test_fills_page_by_bill_id_and_come_back_oldest_first_within_the_window(monkeypatch):
    monkeypatch.setattr(okx_private, "_PAGE", 2)  # two rows per page so that paging is exercised
    okx, session = client([
        (("GET", fills_path(2)), [fill_row(5, T0 + 900), fill_row(4, T0 + 800)]),
        (("GET", fills_path(2, after=4)), [fill_row(3, T0 + 700, clOrdId=""), fill_row(2, T0 - 1)]),
    ])
    fills = okx.fills(T0, T0 + 1000)
    assert [f.bill_id for f in fills] == ["3", "4", "5"]
    assert fills[0] == ExchangeFill("3", "t3", "9001", "", "BTC-USDT-SWAP", "buy", 1.0, 80000.0, -0.4, T0 + 700)
    assert len(session.calls) == 2


def test_a_short_page_ends_the_paging():
    okx, session = client([(("GET", fills_path(100)), [fill_row(5, T0 + 900)])])
    assert [f.bill_id for f in okx.fills(T0, T0 + 1000)] == ["5"]
    assert len(session.calls) == 1


def test_fill_paging_that_does_not_advance_raises_instead_of_looping(monkeypatch):
    monkeypatch.setattr(okx_private, "_PAGE", 1)
    okx, _ = client([
        (("GET", fills_path(1)), [fill_row(5, T0 + 900)]),
        (("GET", fills_path(1, after=5)), [fill_row(5, T0 + 900)]),
    ])
    with pytest.raises(OKXError, match="did not advance"):
        okx.fills(T0, T0 + 1000)


def test_close_position_cancels_its_closing_orders_and_ignores_no_position():
    okx, session = client([
        (("POST", "/api/v5/trade/close-position"), [{"instId": "BTC-USDT-SWAP", "posSide": "net"}]),
        (("POST", "/api/v5/trade/close-position"),
         {"code": "51023", "msg": "Position does not exist", "data": []}),
        (("POST", "/api/v5/trade/close-position"),
         {"code": "50113", "msg": "Invalid signature", "data": []}),
    ])
    okx.close_position("BTC-USDT-SWAP", client_id="kil1btc")
    okx.close_position("BTC-USDT-SWAP")
    assert json.loads(session.calls[0][2]) == {
        "instId": "BTC-USDT-SWAP", "mgnMode": "cross", "autoCxl": True, "clOrdId": "kil1btc",
    }
    assert "clOrdId" not in json.loads(session.calls[1][2])
    with pytest.raises(OKXPrivateError):
        okx.close_position("BTC-USDT-SWAP")


# -- stops -----------------------------------------------------------------------


def test_a_stop_is_a_reduce_only_conditional_market_order_on_the_other_side():
    okx, session = client([
        (("POST", "/api/v5/trade/order-algo"), [{"algoId": "a1", "algoClOrdId": "stp1btc", "sCode": "0"}]),
        (("POST", "/api/v5/trade/order-algo"), [{"algoId": "a2", "algoClOrdId": "stp1eth", "sCode": "0"}]),
    ])
    assert okx.place_stop("BTC-USDT-SWAP", 3, 76_123.456789, "stp1btc") == "a1"
    assert okx.place_stop("ETH-USDT-SWAP", -10, 3200.0, "stp1eth") == "a2"
    assert json.loads(session.calls[0][2]) == {
        "instId": "BTC-USDT-SWAP", "tdMode": "cross", "side": "sell", "ordType": "conditional",
        "sz": "3", "slTriggerPx": "76123.456789", "slOrdPx": "-1", "slTriggerPxType": "last",
        "reduceOnly": True, "algoClOrdId": "stp1btc",
    }
    short = json.loads(session.calls[1][2])
    assert (short["side"], short["sz"], short["slTriggerPx"]) == ("buy", "10", "3200")
    with pytest.raises(ValueError):
        okx.place_stop("BTC-USDT-SWAP", 0, 1.0, "stp2btc")


def test_pending_stops_are_read_and_cancelled_in_one_request():
    okx, session = client([
        (("GET", "/api/v5/trade/orders-algo-pending?ordType=conditional&instType=SWAP"), [
            {"algoId": "a1", "algoClOrdId": "stp1btc", "instId": "BTC-USDT-SWAP", "side": "sell",
             "sz": "3", "slTriggerPx": "76000", "reduceOnly": "true", "cTime": str(T0)},
            {"algoId": "a2", "algoClOrdId": "", "instId": "ETH-USDT-SWAP", "side": "buy",
             "sz": "10", "slTriggerPx": "3200", "reduceOnly": "false", "cTime": str(T0 + 1)},
        ]),
        (("POST", "/api/v5/trade/cancel-algos"), [{"algoId": "a1", "sCode": "0"}, {"algoId": "a2", "sCode": "0"}]),
        (("POST", "/api/v5/trade/cancel-algos"),
         {"code": "2", "msg": "Partial failure", "data": [
             {"algoId": "a2", "sCode": "0", "sMsg": ""},
             {"algoId": "a1", "sCode": "51400", "sMsg": "Cancellation failed as the order does not exist"},
         ]}),
    ])
    stops = okx.pending_stops()
    assert stops == [
        StopOrder("a1", "stp1btc", "BTC-USDT-SWAP", "sell", 3.0, 76000.0, True, T0),
        StopOrder("a2", "", "ETH-USDT-SWAP", "buy", 10.0, 3200.0, False, T0 + 1),
    ]
    okx.cancel_stops(stops)
    assert json.loads(session.calls[1][2]) == [
        {"algoId": "a1", "instId": "BTC-USDT-SWAP"}, {"algoId": "a2", "instId": "ETH-USDT-SWAP"},
    ]
    okx.cancel_stops(stops[:1])  # already gone: not an error
    okx.cancel_stops([])         # nothing to do: no request
    assert len(session.calls) == 3


# -- funding ---------------------------------------------------------------------


def test_funding_bills_are_the_type_8_swap_bills_in_the_window():
    path = f"/api/v5/account/bills-archive?instType=SWAP&type=8&begin={T0}&end={T0 + 10}&limit=100"
    okx, _ = client([(("GET", path), [
        {"billId": "12", "instId": "ETH-USDT-SWAP", "type": "8", "balChg": "0.31", "ts": str(T0 + 5)},
        {"billId": "11", "instId": "BTC-USDT-SWAP", "type": "8", "balChg": "-1.25", "ts": str(T0 + 5)},
        {"billId": "10", "instId": "BTC-USDT-SWAP", "type": "8", "balChg": "-9", "ts": str(T0 + 10)},
    ])])
    assert okx.funding_bills(T0, T0 + 10) == [
        FundingBill("11", "BTC-USDT-SWAP", -1.25, T0 + 5),
        FundingBill("12", "ETH-USDT-SWAP", 0.31, T0 + 5),
    ]


# -- the check command -----------------------------------------------------------


def test_demo_check_explains_the_missing_variables(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADER_HOME", str(tmp_path))
    for name in ("TRADER_OKX_DEMO_KEY", "TRADER_OKX_DEMO_SECRET", "TRADER_OKX_DEMO_PASSPHRASE"):
        monkeypatch.delenv(name, raising=False)
    result = CliRunner().invoke(cli.app, ["demo", "check"])
    assert result.exit_code == 1
    assert "TRADER_OKX_DEMO_KEY" in result.output


def test_demo_check_reads_the_account_and_places_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADER_HOME", str(tmp_path))
    monkeypatch.setenv("TRADER_OKX_DEMO_KEY", "key-123")
    monkeypatch.setenv("TRADER_OKX_DEMO_SECRET", "test-secret")
    monkeypatch.setenv("TRADER_OKX_DEMO_PASSPHRASE", "pass-word")
    session = FakeSession([
        (("GET", "/api/v5/account/config"), [{"posMode": "long_short_mode", "acctLv": "2", "perm": "read_only,trade"}]),
        (("GET", "/api/v5/account/balance?ccy=USDT"), [{"details": [
            {"ccy": "USDT", "eq": "10012.5", "cashBal": "10000", "availBal": "9700.25", "upl": "12.5"}]}]),
        (("GET", "/api/v5/account/positions?instType=SWAP"), [
            {"instId": "BTC-USDT-SWAP", "pos": "3", "posSide": "net", "avgPx": "80000", "upl": "12.5",
             "lever": "3", "mgnMode": "cross", "liqPx": "", "uTime": str(T0)}]),
        (("GET", "/api/v5/trade/orders-algo-pending?ordType=conditional&instType=SWAP"), []),
    ])
    monkeypatch.setattr(cli, "OKXPrivate", lambda creds: OKXPrivate(creds, session=session, clock=lambda: NOW))
    result = CliRunner().invoke(cli.app, ["demo", "check"])
    assert result.exit_code == 0, result.output
    assert "long_short_mode" in result.output and "单币种保证金" in result.output
    assert "USDT 权益 10,012.50" in result.output
    assert "BTC-USDT-SWAP +3 张 @ 80,000.00" in result.output
    assert "首次运行会切换" in result.output
    assert all(method == "GET" for method, *_ in session.calls)
    assert "test-secret" not in result.output and "pass-word" not in result.output


def test_demo_check_reports_an_unreachable_exchange(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADER_HOME", str(tmp_path))
    monkeypatch.setenv("TRADER_OKX_DEMO_KEY", "key-123")
    monkeypatch.setenv("TRADER_OKX_DEMO_SECRET", "test-secret")
    monkeypatch.setenv("TRADER_OKX_DEMO_PASSPHRASE", "pass-word")
    monkeypatch.setattr(okx_private.time, "sleep", lambda _: None)
    session = FakeSession(failures=[requests.ConnectionError("down")] * 3)
    monkeypatch.setattr(cli, "OKXPrivate", lambda creds: OKXPrivate(creds, session=session, clock=lambda: NOW))
    result = CliRunner().invoke(cli.app, ["demo", "check"])
    assert result.exit_code == 1
    assert "OKX 模拟盘没有应答" in result.output and "ConnectionError" in result.output
