"""The signed OKX client of the demo and the live account (ADR 0008, ADR 0010): it
signs as OKX specifies, marks its requests as simulated trading unless it was built
for production, keeps the credentials out of everything it prints and raises, takes
them to no host a redirect points at, and reads OKX's answers into the account's
units. Every answer here is a recorded shape of the real endpoint, except those of
the fee rates and of the key's IP binding and sub-account, which are the shapes OKX's
documentation gives; nothing touches the network."""

import http.client
import json
import logging
import traceback

import pytest
import requests
from requests.adapters import BaseAdapter
from typer.testing import CliRunner

from trader import __main__ as cli, okx_private
from trader.okx import OKXError
from trader.okx_private import (
    DUPLICATE_CLIENT_ID,
    Balance,
    ExchangeFill,
    ExchangePosition,
    FeeRate,
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
    def __init__(self, body, status_code=200, headers=None):
        self.body = body
        self.status_code = status_code
        self.headers = headers or {}

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
    Exception is raised. ``failures`` go out first whatever is asked. Records calls,
    and in ``urls`` where each went: it must be ``base_url``. Every request must
    forbid redirects, which would take its signed headers along."""

    def __init__(self, answers=(), failures=(), base_url=okx_private.BASE_URL):
        self.answers = list(answers)
        self.failures = list(failures)
        self.base_url = base_url
        self.calls = []
        self.urls = []

    def request(self, method, url, data, headers, timeout, allow_redirects=True):
        assert timeout == 10
        assert allow_redirects is False, "a signed request must not follow redirects"
        assert url.startswith(self.base_url + "/"), f"expected a request to {self.base_url}, got {url}"
        self.urls.append(url)
        path = url.removeprefix(self.base_url)
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


def client(answers=(), failures=(), **options):
    """A client on a FakeSession; ``options`` (simulated, base_url) go to OKXPrivate."""
    session = FakeSession(answers, failures, options.get("base_url", okx_private.BASE_URL))
    return OKXPrivate(CREDS, session=session, clock=lambda: NOW, **options), session


class Adapter(BaseAdapter):
    """Stands where requests would open a connection: ``answer(request, count)`` gives
    the status, headers and body of the count-th request, and ``sent`` keeps them."""

    def __init__(self, answer):
        super().__init__()
        self.answer = answer
        self.sent = []

    def send(self, request, **kwargs):
        self.sent.append(request)
        status, headers, body = self.answer(request, len(self.sent))
        response = requests.Response()
        response.status_code, response.url, response.request = status, request.url, request
        response.headers.update(headers)
        response._content, response._content_consumed = body, True
        return response

    def close(self):
        pass


def real_session(answer):
    """A session of requests itself, so that what the client asks of requests is what
    requests does; its requests end in an Adapter rather than on the network."""
    session, adapter = requests.Session(), Adapter(answer)
    session.trust_env = False  # not the proxies of the machine that runs the tests
    session.mount("https://", adapter)
    return session, adapter


CONFIG_BODY = b'{"code":"0","msg":"","data":[{"posMode":"net_mode","acctLv":"2","perm":"read_only,trade"}]}'


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


def test_a_production_client_signs_the_same_and_sends_no_simulated_header():
    okx, session = client([
        (("GET", "/api/v5/account/balance?ccy=USDT"), [{"details": []}]),
        (("POST", "/api/v5/trade/order"), [{"ordId": "1", "clOrdId": "trd1btc", "sCode": "0"}]),
    ], simulated=False)
    okx.balance()
    okx.place_market("BTC-USDT-SWAP", 2, "trd1btc")
    (_, _, _, get_headers), (_, _, _, post_headers) = session.calls
    assert get_headers["OK-ACCESS-SIGN"] == "q88nhwRRgbZed82etcHsHMp56hE0ne7uqeezHdX2B0s="
    assert post_headers["OK-ACCESS-SIGN"] == "mrKZrPsPAocoKe5D+Rscb9d6pDLmWma4u+I2Qdh/Vp4="
    for headers in (get_headers, post_headers):
        assert set(headers) == {
            "Content-Type", "OK-ACCESS-KEY", "OK-ACCESS-SIGN", "OK-ACCESS-TIMESTAMP", "OK-ACCESS-PASSPHRASE",
        }
        assert headers["OK-ACCESS-KEY"] == "key-123"
        assert headers["OK-ACCESS-PASSPHRASE"] == "pass-word"
        assert headers["OK-ACCESS-TIMESTAMP"] == STAMP


def test_a_client_is_simulated_unless_it_is_built_for_production():
    simulated, live = client()[0], client(simulated=False)[0]
    assert (simulated.simulated, repr(simulated)) == (True, "OKXPrivate(simulated)")
    assert (live.simulated, repr(live)) == (False, "OKXPrivate(live)")


def test_the_environment_and_the_host_of_a_client_are_fixed_when_it_is_built():
    okx, _ = client(simulated=False, base_url="https://openapi.okx.com")
    with pytest.raises(AttributeError):
        okx.simulated = True
    with pytest.raises(AttributeError):
        okx.base_url = "https://elsewhere.example"
    assert (okx.simulated, okx.base_url) == (False, "https://openapi.okx.com")
    with pytest.raises(TypeError):  # the environment is named where a client is built
        OKXPrivate(CREDS, FakeSession(), False)


def test_requests_go_to_the_public_clients_host_unless_the_client_is_given_another():
    row = {"posMode": "net_mode", "acctLv": "2", "perm": "read_only,trade"}
    okx, session = client([(("GET", "/api/v5/account/config"), [row])])
    okx.account_config()
    assert okx.base_url == "https://www.okx.com"
    assert session.urls == ["https://www.okx.com/api/v5/account/config"]
    other, other_session = client(
        [(("GET", "/api/v5/account/config"), [row]),
         (("POST", "/api/v5/account/set-position-mode"), [{"posMode": "net_mode"}])],
        base_url="https://openapi.okx.com",
    )
    other.account_config()
    other.set_position_mode()
    assert other_session.urls == [
        "https://openapi.okx.com/api/v5/account/config",
        "https://openapi.okx.com/api/v5/account/set-position-mode",
    ]
    # The host is no part of what is signed: the same request signs the same on either.
    assert other_session.calls[0][3] == session.calls[0][3]


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


def as_http_client_sends(request, count):
    """What the standard library does with a request before it sends it, by its own
    code: the request line and each header are put on a connection that is never
    opened, where a value it will not send raises."""
    connection = http.client.HTTPConnection("okx.invalid")
    connection.putrequest(request.method, request.path_url)
    for name, value in request.headers.items():
        connection.putheader(name, value)
    return 200, {}, CONFIG_BODY


@pytest.mark.parametrize("creds", [
    OKXCredentials("key-123", "test-secret", "Ab\ncd1!"),       # requests refuses a line break in a header...
    OKXCredentials("key\r\n-123", "test-secret", "pass-word"),  # ...of either credential it carries...
    OKXCredentials("key-123", "test-secret", " pass-word"),     # ...and a leading blank
    # A line break at the very end: requests refuses it from 2.33.1 on; before, it goes on
    # to the standard library, which refuses it with a bare ValueError.
    OKXCredentials("key-123", "test-secret", "pass-word\n"),
    OKXCredentials("key-123", "test-secret", "Pass口令1!"),      # not Latin-1: the standard library cannot send it
    OKXCredentials("kéy-口令", "test-secret", "pass-word"),
    OKXCredentials("key-123", "test-\udcffsecret", "pass-word"),  # cannot be encoded to sign with
])
def test_a_credential_that_cannot_be_sent_fails_without_being_quoted(creds):
    """requests and the standard library say which value they choke on (requests in
    full); with a session of requests itself, nothing of it leaves the client."""
    session, adapter = real_session(as_http_client_sends)
    okx = OKXPrivate(creds, session=session, clock=lambda: NOW)
    with pytest.raises(OKXError) as info:
        okx.account_config()
    assert str(info.value) == (
        "the API key, its secret or its passphrase holds a character that cannot be"
        " signed with or sent in a request header; nothing was sent"
    )
    assert not isinstance(info.value, OKXPrivateError)
    # Nor does the error it replaces come along, as its cause or its context.
    assert info.value.__cause__ is None and info.value.__context__ is None
    shown = "".join(traceback.format_exception(info.value))
    for value in (creds.key, creds.secret, creds.passphrase, "pass-word", "cd1!", "口令", "\\u53e3", "\\udcff"):
        assert value not in shown
    assert "InvalidHeader" not in shown and "codec can't encode" not in shown


def test_what_the_standard_library_says_of_a_header_it_will_not_send_is_dropped_too():
    """Whatever the version of requests: before 2.33.1 it lets a line break at the end
    of a value through, and the standard library then refuses the value with a bare
    ValueError that quotes it."""
    okx, _ = client(failures=[ValueError("Invalid header value b'pass-word\\n'")])
    with pytest.raises(OKXError) as info:
        okx.account_config()
    assert str(info.value).startswith("the API key, its secret or its passphrase holds a character")
    assert info.value.__cause__ is None and info.value.__context__ is None
    assert "pass-word" not in "".join(traceback.format_exception(info.value))
    # A ValueError of requests' own, about a URL or a proxy, holds no header: it leaves as it is.
    okx, _ = client(failures=[requests.exceptions.InvalidURL("Invalid URL 'https://www.okx.com:x': bad port")])
    with pytest.raises(requests.exceptions.InvalidURL, match="bad port"):
        okx.account_config()


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


@pytest.mark.parametrize("status, location, target", [
    (302, "https://elsewhere.example/api/v5/account/config?x=1", "elsewhere.example"),
    (301, "http://ELSEWHERE.example:8080/", "elsewhere.example"),
    (307, "/api/v5/account/config/", "an unnamed host"),            # the same host: none is named
    (308, None, "an unnamed host"),
    (303, "https://[not-a-host/", "an unnamed host"),               # not a URL
    (302, "https://else\x1bwhere.example/", "an unnamed host"),     # not what a host name is made of
])
def test_a_redirect_is_an_error_that_is_neither_followed_nor_retried(sleeps, status, location, target):
    headers = {"Location": location} if location else {}
    okx, session = client([(("GET", "/api/v5/account/config"), FakeResponse("", status, headers))])
    with pytest.raises(OKXError) as info:
        okx.account_config()
    assert str(info.value) == f"/api/v5/account/config answered {status}, a redirect to {target}: not followed"
    assert not isinstance(info.value, OKXPrivateError)
    assert len(session.calls) == 1 and sleeps == []
    sent = session.calls[0][3]
    for value in ("key-123", "test-secret", "pass-word", sent["OK-ACCESS-SIGN"]):
        assert value not in str(info.value)


def test_requests_itself_is_told_not_to_follow_a_redirect():
    """With a session of requests itself: left to its default, requests sends the
    request again to where the redirect points, with every OK-ACCESS header on it."""
    def redirecting(request, count):
        if count == 1:
            return 302, {"Location": "https://elsewhere.example/api/v5/trade/order"}, b""
        return 200, {}, b'{"code":"0","msg":"","data":[{"ordId":"9001","clOrdId":"trd1btc","sCode":"0"}]}'

    session, adapter = real_session(redirecting)
    okx = OKXPrivate(CREDS, session=session, clock=lambda: NOW)
    with pytest.raises(OKXError) as info:
        okx.place_market("BTC-USDT-SWAP", 2, "trd1btc")
    assert str(info.value) == "/api/v5/trade/order answered 302, a redirect to elsewhere.example: not followed"
    assert [(request.method, request.url) for request in adapter.sent] == [
        ("POST", "https://www.okx.com/api/v5/trade/order"),
    ]
    assert adapter.sent[0].headers["OK-ACCESS-KEY"] == "key-123"  # the request that did go out was the signed one


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


def test_the_trade_permission_probe_passes_when_only_the_order_is_missing():
    okx, session = client([(("POST", "/api/v5/trade/cancel-order"), {
        "code": "1", "msg": "All operations failed",
        "data": [{"ordId": "1", "sCode": "51400", "sMsg": "Order cancellation failed as the order does not exist."}],
    })])
    assert okx.check_trade_permission("BTC-USDT-SWAP") is None
    method, path, data, _ = session.calls[0]
    assert (method, path, data) == ("POST", "/api/v5/trade/cancel-order", '{"instId":"BTC-USDT-SWAP","ordId":"1"}')


def test_the_trade_permission_probe_raises_the_gateway_refusal():
    okx, _ = client([(("POST", "/api/v5/trade/cancel-order"), {
        "code": "50123", "msg": "This API Key does not have trading permission for the Crypto", "data": [],
    })])
    with pytest.raises(OKXPrivateError) as info:
        okx.check_trade_permission("BTC-USDT-SWAP")
    assert info.value.code == "50123"
    assert info.value.message == "This API Key does not have trading permission for the Crypto"


def test_the_probe_hands_back_what_okx_answered_for_a_caller_that_must_tell_more():
    cancel = ("POST", "/api/v5/trade/cancel-order")
    okx, session = client([
        (cancel, {"code": "1", "msg": "All operations failed", "data": [
            {"ordId": "1", "sCode": "51400", "sMsg": "Order cancellation failed as the order does not exist."}]}),
        (cancel, {"code": "50120", "msg": "This API key doesn't have permission to use this function", "data": []}),
        (cancel, {"code": "51000", "msg": "Parameter ordId error", "data": []}),
        (cancel, [{"ordId": "1", "clOrdId": "", "sCode": "0", "sMsg": ""}]),
        (cancel, {"code": "51000", "msg": "Parameter ordId error", "data": []}),
    ])
    missing = okx.probe_trade_permission("BTC-USDT-SWAP")
    assert (missing.code, okx_private.PROBE_ORDER_MISSING) == ("51400", "51400")
    refused = okx.probe_trade_permission("BTC-USDT-SWAP")
    assert (refused.code, refused.message) == ("50120", "This API key doesn't have permission to use this function")
    unseen = okx.probe_trade_permission("BTC-USDT-SWAP")
    assert (unseen.code, unseen.message) == ("51000", "Parameter ordId error")
    assert okx.probe_trade_permission("BTC-USDT-SWAP") is None  # OKX took the cancel
    # check_trade_permission reads the same answers as it always did: only a 50xxx one raises.
    assert okx.check_trade_permission("BTC-USDT-SWAP") is None
    assert {call[2] for call in session.calls} == {'{"instId":"BTC-USDT-SWAP","ordId":"1"}'}


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


def test_the_account_config_tells_the_keys_ip_binding_and_whether_it_is_a_sub_account():
    """The fields are those of OKX's documentation: a sub-account's uid differs from its
    mainUid, ip is "" for a key bound to none. Not recorded from the real endpoint yet."""
    okx, _ = client([
        (("GET", "/api/v5/account/config"), [{
            "posMode": "net_mode", "acctLv": "2", "perm": "read_only", "ip": "117.37.203.58,117.37.203.57",
            "uid": "698827017768230914", "mainUid": "44705892343619584", "type": "1",
        }]),
        (("GET", "/api/v5/account/config"), [{
            "posMode": "long_short_mode", "acctLv": "2", "perm": "read_only,withdraw,trade", "ip": "",
            "uid": "44705892343619584", "mainUid": "44705892343619584", "type": "0",
        }]),
        # What the recorded answers of this file hold: the new fields are then empty.
        (("GET", "/api/v5/account/config"), [{"posMode": "net_mode", "acctLv": "2", "perm": "read_only,trade"}]),
    ])
    sub = okx.account_config()
    assert (sub.ip, sub.uid, sub.main_uid) == (
        "117.37.203.58,117.37.203.57", "698827017768230914", "44705892343619584"
    )
    main = okx.account_config()
    assert (main.ip, main.uid, main.main_uid) == ("", "44705892343619584", "44705892343619584")
    bare = okx.account_config()
    assert (bare.ip, bare.uid, bare.main_uid) == ("", "", "")


def fee_answer(*groups, level="Lv1"):
    """OKX's documented answer of /api/v5/account/trade-fee (its response example, with
    the instrument type a swap's) around ``groups``. The top-level rates are the
    deprecated ones, for crypto-margined contracts: the client must not read them."""
    return [{
        "category": "1", "delivery": "", "exercise": "", "feeGroup": list(groups), "fiat": [],
        "instType": "SWAP", "level": level, "maker": "-0.0008", "makerU": "", "makerUSDC": "",
        "ruleType": "normal", "taker": "-0.001", "takerU": "", "takerUSDC": "", "ts": "1763979985847",
    }]


FEE_PATH = "/api/v5/account/trade-fee?instType=SWAP&instFamily="


def test_a_fee_rate_is_what_the_account_pays_on_the_swaps_family():
    """The shapes here are those of OKX's documentation; none has been recorded from the
    real endpoint yet. OKX writes a rate it charges as a negative number."""
    okx, session = client([
        (("GET", FEE_PATH + "BTC-USDT"), fee_answer(
            {"rpiMaker": "", "groupId": "4", "maker": "-0.0002", "taker": "-0.0005"})),
        (("GET", FEE_PATH + "ETH-USDT"), fee_answer(
            {"rpiMaker": "", "groupId": "4", "maker": "0.00005", "taker": "-0.00035"}, level="Lv5")),
        (("GET", FEE_PATH + "SOL-USDT"), fee_answer(
            {"rpiMaker": "", "groupId": "5", "maker": "0", "taker": "-0.0004"})),
    ])
    assert okx.fee_rate("BTC-USDT-SWAP") == FeeRate("BTC-USDT-SWAP", "Lv1", 0.0005, 0.0002)
    rebated = okx.fee_rate("ETH-USDT-SWAP")  # a positive rate is a rebate: the account is paid
    assert (rebated.level, rebated.taker, rebated.maker) == ("Lv5", 0.00035, -0.00005)
    free = okx.fee_rate("SOL-USDT-SWAP")
    assert (free.taker, str(free.maker)) == (0.0004, "0.0")  # zero, not -0.0
    assert [method for method, _, _, _ in session.calls] == ["GET"] * 3


def test_a_fee_rate_among_several_groups_is_the_one_the_instrument_trades_in():
    """As documented: instType and groupId together name a fee group, and the
    instruments endpoint maps an instrument to its group. Not recorded yet."""
    groups = (
        {"rpiMaker": "", "groupId": "4", "maker": "-0.0002", "taker": "-0.0005"},
        {"rpiMaker": "", "groupId": "5", "maker": "-0.0003", "taker": "-0.0006"},
    )
    okx, session = client([
        (("GET", FEE_PATH + "SOL-USDT"), fee_answer(*groups)),
        (("GET", "/api/v5/account/instruments?instType=SWAP&instId=SOL-USDT-SWAP"),
         [{"instId": "SOL-USDT-SWAP", "instType": "SWAP", "instFamily": "SOL-USDT", "groupId": "5"}]),
    ])
    assert okx.fee_rate("SOL-USDT-SWAP") == FeeRate("SOL-USDT-SWAP", "Lv1", 0.0006, 0.0003)
    assert len(session.calls) == 2


@pytest.mark.parametrize("answers", [
    [(("GET", FEE_PATH + "BTC-USDT"), fee_answer())],  # no group at all
    [(("GET", FEE_PATH + "BTC-USDT"), [])],            # no row at all
    [(("GET", FEE_PATH + "BTC-USDT"), fee_answer({"groupId": "4", "maker": "", "taker": ""}))],
    [(("GET", FEE_PATH + "BTC-USDT"), fee_answer(
        {"groupId": "4", "maker": "-0.0002", "taker": "-0.0005"},
        {"groupId": "5", "maker": "-0.0003", "taker": "-0.0006"})),
     (("GET", "/api/v5/account/instruments?instType=SWAP&instId=BTC-USDT-SWAP"),
      [{"instId": "BTC-USDT-SWAP", "groupId": "7"}])],  # the instrument's group is not among them
    [(("GET", FEE_PATH + "BTC-USDT"), fee_answer(
        {"groupId": "4", "maker": "-0.0002", "taker": "-0.0005"},
        {"groupId": "5", "maker": "-0.0003", "taker": "-0.0006"})),
     (("GET", "/api/v5/account/instruments?instType=SWAP&instId=BTC-USDT-SWAP"), [])],
])
def test_a_fee_answer_without_one_group_of_rates_raises_instead_of_guessing(answers):
    okx, _ = client(answers)
    with pytest.raises(OKXError, match="no single fee group with rates for BTC-USDT-SWAP"):
        okx.fee_rate("BTC-USDT-SWAP")


@pytest.mark.parametrize("taker, maker", [
    ("abc", "-0.0002"), ("-0.0005", "n/a"), ("nan", "-0.0002"), ("-0.0005", "-inf"), (["-0.0005"], "-0.0002"),
])
def test_a_fee_rate_that_is_not_a_number_raises_the_error_of_a_fee_not_read(taker, maker):
    okx, _ = client([(("GET", FEE_PATH + "BTC-USDT"), fee_answer({"groupId": "4", "maker": maker, "taker": taker}))])
    with pytest.raises(OKXError) as info:
        okx.fee_rate("BTC-USDT-SWAP")
    assert str(info.value) == "/api/v5/account/trade-fee gave rates for BTC-USDT-SWAP that are not numbers"


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


def fills_path(limit, after=None, begin=T0, end=T0 + 1000, endpoint="fills"):
    path = f"/api/v5/trade/{endpoint}?instType=SWAP&begin={begin}&end={end}&limit={limit}"
    return path if after is None else f"{path}&after={after}"


DAY = 86_400_000
RECENT_FROM = T0 - okx_private.RECENT_FILLS_MS  # the clock is T0: the live endpoint covers from here


def test_fills_within_three_days_come_from_the_live_endpoint_only():
    okx, session = client([(("GET", fills_path(100)), [fill_row(5, T0 + 900)])])
    assert [f.bill_id for f in okx.fills(T0, T0 + 1000)] == ["5"]
    assert [c[1].split("?")[0] for c in session.calls] == ["/api/v5/trade/fills"]


def test_fills_older_than_three_days_come_from_the_history_merged_with_the_live_ones():
    okx, session = client([
        (("GET", fills_path(100, begin=T0 - 4 * DAY, end=RECENT_FROM, endpoint="fills-history")),
         [fill_row(2, T0 - 4 * DAY + 500), fill_row(1, T0 - 4 * DAY + 100)]),
        (("GET", fills_path(100, begin=RECENT_FROM, end=T0 + 1000)),
         [fill_row(3, T0 + 900), fill_row(2, T0 - 4 * DAY + 500)]),  # bill 2 in both: once
    ])
    fills = okx.fills(T0 - 4 * DAY, T0 + 1000)
    assert [f.bill_id for f in fills] == ["1", "2", "3"]
    assert [c[1].split("?")[0] for c in session.calls] == [
        "/api/v5/trade/fills-history", "/api/v5/trade/fills"
    ]


def test_a_window_entirely_older_than_three_days_reads_the_history_only():
    okx, session = client([
        (("GET", fills_path(100, begin=T0 - 5 * DAY, end=T0 - 4 * DAY, endpoint="fills-history")),
         [fill_row(1, T0 - 5 * DAY + 100)]),
    ])
    assert [f.bill_id for f in okx.fills(T0 - 5 * DAY, T0 - 4 * DAY)] == ["1"]
    assert len(session.calls) == 1


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
        (("POST", "/api/v5/trade/cancel-order"), {
            "code": "1", "msg": "All operations failed",
            "data": [{"ordId": "1", "sCode": "51400", "sMsg": "Order cancellation failed as the order does not exist."}],
        }),
    ])
    monkeypatch.setattr(cli, "OKXPrivate", lambda creds: OKXPrivate(creds, session=session, clock=lambda: NOW))
    result = CliRunner().invoke(cli.app, ["demo", "check"])
    assert result.exit_code == 0, result.output
    assert "long_short_mode" in result.output and "合约模式（单币种保证金）" in result.output
    assert "USDT 权益 10,012.50" in result.output
    assert "BTC-USDT-SWAP +3 张 @ 80,000.00" in result.output
    assert "首次运行会切换" in result.output
    assert "交易权限正常" in result.output
    # Nothing is placed: the reads, then one cancel of an order that cannot exist.
    posts = [(path, data) for method, path, data, _ in session.calls if method == "POST"]
    assert posts == [("/api/v5/trade/cancel-order", '{"instId":"BTC-USDT-SWAP","ordId":"1"}')]
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


def test_demo_check_points_at_a_key_that_cannot_trade(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADER_HOME", str(tmp_path))
    monkeypatch.setenv("TRADER_OKX_DEMO_KEY", "key-123")
    monkeypatch.setenv("TRADER_OKX_DEMO_SECRET", "test-secret")
    monkeypatch.setenv("TRADER_OKX_DEMO_PASSPHRASE", "pass-word")
    session = FakeSession([
        (("GET", "/api/v5/account/config"), [{"posMode": "net_mode", "acctLv": "3", "perm": "read_only,trade"}]),
        (("GET", "/api/v5/account/balance?ccy=USDT"), [{"details": [
            {"ccy": "USDT", "eq": "5000", "cashBal": "5000", "availBal": "5000", "upl": "0"}]}]),
        (("GET", "/api/v5/account/positions?instType=SWAP"), []),
        (("GET", "/api/v5/trade/orders-algo-pending?ordType=conditional&instType=SWAP"), []),
        (("POST", "/api/v5/trade/cancel-order"), {
            "code": "50123", "msg": "This API Key does not have trading permission for the Crypto", "data": [],
        }),
    ])
    monkeypatch.setattr(cli, "OKXPrivate", lambda creds: OKXPrivate(creds, session=session, clock=lambda: NOW))
    result = CliRunner().invoke(cli.app, ["demo", "check"])
    assert result.exit_code == 0, result.output
    assert "跨币种保证金" in result.output and "权限 read_only,trade" in result.output
    assert "注意：这把 key 下不了单：50123 This API Key does not have trading permission for the Crypto；" in result.output
    assert "勾上加密货币/永续合约" in result.output
    assert "交易权限正常" not in result.output


@pytest.mark.parametrize("passphrase, fragments", [
    ("Ab\ncd1!", ("Ab\ncd1!", "cd1!", "Ab\\n")),
    ("Pass口令1!", ("Pass口令1!", "口令", "Pass")),
])
def test_demo_check_does_not_print_a_passphrase_that_cannot_be_a_header(
    monkeypatch, tmp_path, caplog, passphrase, fragments
):
    """The demo key is taken from the environment as it is. One that cannot be sent
    still fails at its first request, with a session of requests itself, but the
    failure no longer quotes it."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("TRADER_HOME", str(tmp_path))
    monkeypatch.setenv("TRADER_OKX_DEMO_KEY", "key-123")
    monkeypatch.setenv("TRADER_OKX_DEMO_SECRET", "test-secret")
    monkeypatch.setenv("TRADER_OKX_DEMO_PASSPHRASE", passphrase)
    session, adapter = real_session(as_http_client_sends)
    monkeypatch.setattr(cli, "OKXPrivate", lambda creds: OKXPrivate(creds, session=session, clock=lambda: NOW))
    result = CliRunner().invoke(cli.app, ["demo", "check"])
    assert result.exit_code == 1
    assert result.output.strip() == (
        "OKX 模拟盘没有应答：OKXError: the API key, its secret or its passphrase holds a character that"
        " cannot be signed with or sent in a request header; nothing was sent"
    )
    for text in (result.output, caplog.text):
        assert not any(fragment in text for fragment in fragments)

