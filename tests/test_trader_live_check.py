"""python -m trader live check (ADR 0010): it reads the production account with the key
of the live key file and says what does not fit the decision or could not be
established, places nothing, fails alone and with an alert when the key file cannot be
used, and never prints the key or a signature. The answers are the shapes of
tests/test_trader_okx_private.py; those of the fee rates, the IP binding and the
sub-account are from OKX's documentation and have not been recorded from the real
endpoints yet."""

import logging
import os

import pytest
import requests
from typer.testing import CliRunner

from tests.test_trader_jobs import Inbox
from tests.test_trader_live_keys import KEY, PASSPHRASE, SECRET, write_key_file
from tests.test_trader_okx_private import (
    FEE_PATH,
    NOW,
    T0,
    FakeResponse,
    FakeSession,
    as_http_client_sends,
    fee_answer,
    real_session,
)
from trader import __main__ as cli, okx_private
from trader.live import keys
from trader.okx_private import OKXCredentials, OKXPrivate
from trader.settings import TAKER_FEE

LIVE_URL = "https://openapi.okx.com"
PROBE = ("POST", "/api/v5/trade/cancel-order")
NO_SUCH_ORDER = {
    "code": "1", "msg": "All operations failed",
    "data": [{"ordId": "1", "sCode": "51400", "sMsg": "Order cancellation failed as the order does not exist."}],
}
READ_ONLY = {"code": "50120", "msg": "This API key doesn't have permission to use this function", "data": []}


def config_row(**over):
    """A sub-account's key as ADR 0010 wants it once unlocked: trade only, bound to an IP."""
    row = {"posMode": "net_mode", "acctLv": "2", "perm": "read_only,trade", "ip": "117.37.203.58",
           "uid": "698827017768230914", "mainUid": "44705892343619584", "type": "1"}
    row.update(over)
    return row


def fee(taker, maker, group="4"):
    return fee_answer({"rpiMaker": "", "groupId": group, "maker": maker, "taker": taker})


def okx_answers(config=None, balance="500", positions=(), stops=(), fees=None, probe=NO_SUCH_ORDER):
    """What live check asks, in its order: the reads, the fee rates, then the probe."""
    fees = fees or [fee("-0.0005", "-0.0002")] * 3
    return [
        (("GET", "/api/v5/account/config"), [config or config_row()]),
        (("GET", "/api/v5/account/balance?ccy=USDT"), [{"details": [
            {"ccy": "USDT", "eq": balance, "cashBal": balance, "availBal": balance, "upl": "0"}]}]),
        (("GET", "/api/v5/account/positions?instType=SWAP"), list(positions)),
        (("GET", "/api/v5/trade/orders-algo-pending?ordType=conditional&instType=SWAP"), list(stops)),
        *((("GET", FEE_PATH + family), answer)
          for family, answer in zip(("BTC-USDT", "ETH-USDT", "SOL-USDT"), fees, strict=True)),
        (PROBE, probe),
    ]


class LiveCli:
    """The ``live`` commands with the key file, the notifier and OKX's answers faked."""

    def __init__(self, tmp_path, monkeypatch):
        self.monkeypatch = monkeypatch
        self.key_path = write_key_file(tmp_path / "okx-live.env")
        self.inbox = Inbox()
        self.session = None
        monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
        monkeypatch.setenv("TRADER_HOME", str(tmp_path / "home"))
        monkeypatch.setenv(keys.KEY_FILE_ENV, str(self.key_path))
        for part in ("KEY", "SECRET", "PASSPHRASE"):
            monkeypatch.delenv(f"TRADER_OKX_DEMO_{part}", raising=False)
        monkeypatch.setattr(cli, "Notifier", lambda settings: self.inbox)
        monkeypatch.setattr(okx_private.time, "sleep", lambda seconds: None)

    def run(self, *args, answers=(), failures=(), base_url=LIVE_URL):
        self.session = FakeSession(answers, failures, base_url)
        self.monkeypatch.setattr(
            keys, "OKXPrivate",
            lambda creds, **options: OKXPrivate(creds, session=self.session, clock=lambda: NOW, **options),
        )
        result = CliRunner().invoke(cli.app, ["live", *args])
        self.assert_nothing_secret(result.output)
        return result

    def assert_nothing_secret(self, *texts):
        """Neither the key file's values nor a signature sent in a header is in ``texts``
        or in an alert."""
        signatures = [headers["OK-ACCESS-SIGN"] for _, _, _, headers in self.session.calls]
        for text in (*texts, *self.inbox.sent):
            for secret in (KEY, SECRET, PASSPHRASE, "Live#pass", *signatures):
                assert secret not in text


@pytest.fixture
def live(tmp_path, monkeypatch):
    return LiveCli(tmp_path, monkeypatch)


def test_live_check_reads_the_production_account_and_places_nothing(live, caplog):
    caplog.set_level(logging.DEBUG)
    result = live.run("check", answers=okx_answers(
        config=config_row(perm="read_only"),
        balance="500.25",
        positions=[{"instId": "BTC-USDT-SWAP", "pos": "3", "posSide": "net", "avgPx": "80000", "upl": "0",
                    "lever": "3", "mgnMode": "cross", "liqPx": "", "uTime": str(T0)}],
        stops=[{"algoId": "a1", "algoClOrdId": "stp1btc", "instId": "BTC-USDT-SWAP", "side": "sell",
                "sz": "3", "slTriggerPx": "76000", "reduceOnly": "true", "cTime": str(T0)}],
        fees=[fee("-0.0005", "-0.0002"), fee("-0.00035", "0.00005"), fee("-0.0006", "0", group="5")],
        probe=READ_ONLY,
    ))
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "正式环境（真钱），域名 https://openapi.okx.com",
        "账户模式 合约模式（单币种保证金），持仓模式 net_mode，子账户",
        "这把 key 的权限 read_only，绑定了 1 个 IP",
        "USDT 权益 500.25，钱包 500.25，可用 500.25，未实现 +0.00",
        "持仓 1 个，挂着的止损单 1 张",
        "  BTC-USDT-SWAP +3 张 @ 80,000.00，cross 3×",
        "  止损 BTC-USDT-SWAP sell 3 张，触发 76,000.00",
        "实际费率（等级 Lv1），模拟盘假设吃单万分之 5：",
        "  BTC-USDT-SWAP 吃单万分之 5（比模拟盘假设 +0），挂单万分之 2",
        "  ETH-USDT-SWAP 吃单万分之 3.5（比模拟盘假设 -1.5），挂单万分之 -0.5",
        "  SOL-USDT-SWAP 吃单万分之 6（比模拟盘假设 +1），挂单万分之 0",
        "注意：这把 key 下不了单（50120 This API key doesn't have permission to use this function）："
        "影子运行可以，解锁前要换成只勾“交易”的 key，交易权限要覆盖加密货币/永续合约。",
    ]
    assert TAKER_FEE == 0.0005  # the paper accounts' assumption the rates are set against
    # Every request went to the production host, unmarked; nothing was posted but the probe
    # that cancels an order that cannot exist, and no account setting was touched.
    assert all(url.startswith("https://openapi.okx.com/api/v5/") for url in live.session.urls)
    assert len(live.session.calls) == 8 and live.session.answers == []
    assert all("x-simulated-trading" not in headers for _, _, _, headers in live.session.calls)
    assert all(headers["OK-ACCESS-KEY"] == KEY for _, _, _, headers in live.session.calls)
    posts = [(path, data) for method, path, data, _ in live.session.calls if method != "GET"]
    assert posts == [("/api/v5/trade/cancel-order", '{"instId":"BTC-USDT-SWAP","ordId":"1"}')]
    assert live.inbox.sent == []
    live.assert_nothing_secret(caplog.text)


def test_a_read_only_key_cannot_trade_whatever_the_probe_answers(live):
    # The gateway's code for a read-only key is not known yet; the key's own permissions tell
    # too, and what the probe did get is said, for it to become known.
    result = live.run("check", answers=okx_answers(config=config_row(perm="read_only")))
    assert result.exit_code == 0, result.output
    assert (
        "注意：这把 key 下不了单（权限里没有 trade；探针得到 51400 Order cancellation failed as the order"
        " does not exist.）：影子运行可以，解锁前要换成只勾“交易”的 key，交易权限要覆盖加密货币/永续合约。"
    ) in result.output
    assert "交易权限正常" not in result.output


@pytest.mark.parametrize("answer, got", [
    ({"code": "51000", "msg": "Parameter ordId error", "data": []}, "探针得到 51000 Parameter ordId error"),
    ({"code": "1", "msg": "All operations failed", "data": [{"ordId": "1", "sCode": "51603", "sMsg": "Order does not exist"}]},
     "探针得到 51603 Order does not exist"),
    ([{"ordId": "1", "clOrdId": "", "sCode": "0", "sMsg": ""}], "探针的撤单被接受了"),
])
def test_an_answer_to_the_probe_that_has_not_been_seen_does_not_pass_for_permission(live, answer, got):
    result = live.run("check", answers=okx_answers(probe=answer))
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-1] == (
        f"注意：交易权限{got}，不是“订单不存在”（51400）：这个应答没见过，不能确认这把 key 能下单。"
    )
    assert "交易权限正常" not in result.output


@pytest.mark.parametrize("failures, error", [
    ([requests.ConnectionError("down")] * 3, "ConnectionError: down"),
    ([FakeResponse("<html>forbidden</html>", 403)], "HTTPError: 403 error"),
    ([FakeResponse("", 302, {"Location": "https://elsewhere.example/login"})],
     "OKXError: /api/v5/trade/cancel-order answered 302, a redirect to elsewhere.example: not followed"),
])
def test_a_probe_without_an_answer_is_noted_and_the_rest_is_still_printed(live, failures, error):
    answers = okx_answers(balance="500.25")[:-1] + [(PROBE, failure) for failure in failures]
    result = live.run("check", answers=answers)
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[:5] == [
        "正式环境（真钱），域名 https://openapi.okx.com",
        "账户模式 合约模式（单币种保证金），持仓模式 net_mode，子账户",
        "这把 key 的权限 read_only,trade，绑定了 1 个 IP",
        "USDT 权益 500.25，钱包 500.25，可用 500.25，未实现 +0.00",
        "持仓 0 个，挂着的止损单 0 张",
    ]
    assert "  SOL-USDT-SWAP 吃单万分之 5（比模拟盘假设 +0），挂单万分之 2" in lines
    assert lines[-1] == f"注意：交易权限探针没有得到应答：{error}；不能确认这把 key 能下单。"
    assert "交易权限正常" not in result.output and live.session.answers == []


def test_a_read_only_key_whose_probe_got_no_answer_still_cannot_trade(live):
    answers = okx_answers(config=config_row(perm="read_only"))[:-1] + [(PROBE, requests.ConnectionError("down"))] * 3
    result = live.run("check", answers=answers)
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-1] == (
        "注意：这把 key 下不了单（权限里没有 trade；探针没有得到应答：ConnectionError: down）："
        "影子运行可以，解锁前要换成只勾“交易”的 key，交易权限要覆盖加密货币/永续合约。"
    )


def test_a_trade_key_the_gateway_refuses_cannot_trade_either(live):
    result = live.run("check", answers=okx_answers(probe={
        "code": "50123", "msg": "This API Key does not have trading permission for the Crypto.", "data": [],
    }))
    assert result.exit_code == 0, result.output
    assert (
        "注意：这把 key 下不了单（50123 This API Key does not have trading permission for the Crypto.）："
        "影子运行可以，解锁前要换成只勾“交易”的 key，交易权限要覆盖加密货币/永续合约。"
    ) in result.output
    assert "交易权限正常" not in result.output


def test_live_check_passes_a_key_made_as_the_decision_wants_it(live):
    result = live.run("check", answers=okx_answers())
    assert result.exit_code == 0, result.output
    assert "这把 key 的权限 read_only,trade，绑定了 1 个 IP" in result.output
    assert "交易权限正常（试了一次不存在订单的撤单，没有下单）。" in result.output
    assert "注意" not in result.output


def test_live_check_notes_what_the_decision_does_not_allow(live):
    result = live.run("check", answers=okx_answers(config=config_row(
        acctLv="1", posMode="long_short_mode", perm="read_only,withdraw,trade", ip="",
        uid="44705892343619584", type="0",
    )))
    assert result.exit_code == 0, result.output
    assert "账户模式 现货，持仓模式 long_short_mode，主账户" in result.output
    assert "这把 key 的权限 read_only,withdraw,trade，没有绑定 IP" in result.output
    assert [line for line in result.output.splitlines() if line.startswith("注意：")] == [
        "注意：这把 key 带提币权限（withdraw）；ADR 0010 要求只勾交易、不勾提币。",
        "注意：这把 key 没有绑定 IP；ADR 0010 要求绑定 mini 的固定出口 IP。",
        "注意：这把 key 建在主账户下；ADR 0010 要求建在只给这套系统用的子账户下。",
        "注意：现货模式不能交易合约，请在 OKX 把账户模式改成合约模式（以前叫单币种保证金）或跨币种保证金。",
    ]
    assert "交易权限正常" in result.output


@pytest.mark.parametrize("ids", [
    {"uid": "698827017768230914", "mainUid": ""},  # one without the other would read as a sub-account
    {"uid": "", "mainUid": "44705892343619584"},
    {"uid": "", "mainUid": ""},
])
def test_live_check_does_not_guess_whether_the_account_is_a_sub_account(live, ids):
    result = live.run("check", answers=okx_answers(config=config_row(**ids)))
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[1] == "账户模式 合约模式（单币种保证金），持仓模式 net_mode，不确定是不是子账户"
    assert [line for line in result.output.splitlines() if line.startswith("注意：")] == [
        "注意：应答里没有 uid 或 mainUid，看不出这把 key 是不是建在子账户下；ADR 0010 要求建在只给这套系统用的子账户下。",
    ]


def test_live_check_counts_the_bound_ips_without_printing_them(live):
    result = live.run("check", answers=okx_answers(config=config_row(ip="117.37.203.58,117.37.203.57")))
    assert "绑定了 2 个 IP" in result.output
    assert "117.37" not in result.output and "698827017768230914" not in result.output


def test_live_check_goes_on_without_a_fee_rate_it_cannot_read(live):
    result = live.run("check", answers=okx_answers(fees=[
        fee("-0.0005", "-0.0002"),
        fee_answer(),  # no fee group in the answer
        {"code": "51000", "msg": "Parameter instFamily error", "data": []},
    ]))
    assert result.exit_code == 0, result.output
    assert "  BTC-USDT-SWAP 吃单万分之 5（比模拟盘假设 +0），挂单万分之 2" in result.output
    assert "ETH-USDT-SWAP 吃单" not in result.output and "SOL-USDT-SWAP 吃单" not in result.output
    assert result.output.splitlines()[-2:] == [
        "注意：ETH-USDT-SWAP 的实际费率没有读到：OKXError: /api/v5/account/trade-fee names no single fee group"
        " with rates for ETH-USDT-SWAP",
        "注意：SOL-USDT-SWAP 的实际费率没有读到：OKXPrivateError: /api/v5/account/trade-fee failed with code"
        " 51000: Parameter instFamily error",
    ]
    assert "交易权限正常" in result.output


def test_live_check_notes_a_fee_rate_that_is_not_a_number_and_goes_on(live):
    result = live.run("check", answers=okx_answers(fees=[
        fee("-0.0005", "-0.0002"), fee("abc", "-0.0002"), fee("-0.0005", "nan"),
    ]))
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-2:] == [
        "注意：ETH-USDT-SWAP 的实际费率没有读到：OKXError: /api/v5/account/trade-fee gave rates for"
        " ETH-USDT-SWAP that are not numbers",
        "注意：SOL-USDT-SWAP 的实际费率没有读到：OKXError: /api/v5/account/trade-fee gave rates for"
        " SOL-USDT-SWAP that are not numbers",
    ]
    assert "万分之 nan" not in result.output and "交易权限正常" in result.output


def test_live_check_can_be_pointed_at_another_okx_host_for_one_run(live):
    result = live.run("check", "--base-url", "https://www.okx.com/", answers=okx_answers(), base_url="https://www.okx.com")
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[0] == "正式环境（真钱），域名 https://www.okx.com"
    assert live.session.urls[0] == "https://www.okx.com/api/v5/account/config"
    assert all("x-simulated-trading" not in headers for _, _, _, headers in live.session.calls)


@pytest.mark.parametrize("url", [
    "http://openapi.okx.com", "openapi.okx.com", "https://okx.com.example.org", "https://example.org/okx.com",
    "https://notokx.com", "https://openapi.okx.com@example.org", "https://example.org#.okx.com",
    "https://openapi.okx.com/api", "https://openapi.okx.com:8443", "https://us.okx.com", "https://okx.com",
])
def test_live_check_sends_the_key_to_no_other_host(live, url):
    live.monkeypatch.setattr(keys, "load", lambda *args: pytest.fail("the key file was read"))
    result = live.run("check", "--base-url", url)
    assert result.exit_code == 1
    assert result.output.strip() == (
        "--base-url 只接受 https://openapi.okx.com 或 https://www.okx.com，live 的密钥不发往别处"
    )
    assert live.session.calls == [] and live.inbox.sent == []


def test_live_check_stops_at_a_redirect_and_does_not_follow_it(live):
    result = live.run("check", answers=[
        (("GET", "/api/v5/account/config"), FakeResponse("", 302, {"Location": "https://elsewhere.example/login"})),
    ])
    assert result.exit_code == 1
    assert result.output.strip() == (
        "OKX 正式环境没有应答：OKXError: /api/v5/account/config answered 302, a redirect to elsewhere.example:"
        " not followed"
    )
    assert len(live.session.calls) == 1 and live.inbox.sent == []


UNFIT = "{path} 里 TRADER_OKX_LIVE_PASSPHRASE 的值含空白、控制字符或非 ASCII 字符"


@pytest.mark.parametrize("damage, reason", [
    (lambda path: path.unlink(), "{path} 不存在"),
    (lambda path: path.chmod(0o644), "{path} 的权限是 644，比 600 宽：先 chmod 600 再运行"),
    (lambda path: write_key_file(path, TRADER_OKX_LIVE_SECRET=None), "{path} 里缺 TRADER_OKX_LIVE_SECRET"),
    (lambda path: path.chmod(0o000), "{path} 读不了：Permission denied"),
    (lambda path: path.write_bytes(b"TRADER_OKX_LIVE_KEY=\xff\xfel\x00i\x00v\x00e\x00\n"), "{path} 不是 UTF-8 文本"),
    # A passphrase requests would quote in full in the error it raises on sending it: in
    # double quotes dotenv reads \n as a line break.
    (lambda path: write_key_file(path, TRADER_OKX_LIVE_PASSPHRASE='TRADER_OKX_LIVE_PASSPHRASE="Ab\\ncd1!"'), UNFIT),
    (lambda path: write_key_file(path, TRADER_OKX_LIVE_PASSPHRASE="TRADER_OKX_LIVE_PASSPHRASE='Pass口令1!'"), UNFIT),
])
def test_a_key_file_that_cannot_be_used_fails_the_command_with_an_alert(live, caplog, damage, reason):
    caplog.set_level(logging.DEBUG)
    damage(live.key_path)
    if reason.endswith("Permission denied") and os.access(live.key_path, os.R_OK):
        pytest.skip("this user reads a file whatever its mode")
    reason = reason.format(path=live.key_path)
    result = live.run("check", answers=okx_answers())
    assert result.exit_code == 1
    assert result.output.strip() == f"live 的密钥文件有问题：{reason}"
    assert live.inbox.sent == [f"live 的密钥文件有问题，这次没有运行：{reason}"]
    assert live.session.calls == []  # nothing was asked of OKX
    live.assert_nothing_secret(caplog.text)
    for text in (result.output, *live.inbox.sent, caplog.text):
        assert "cd1!" not in text and "口令" not in text


@pytest.mark.parametrize("passphrase, fragments", [
    ("Ab\ncd1!", ("Ab\ncd1!", "cd1!", "Ab\\n")),
    ("Pass口令1!", ("Pass口令1!", "口令", "Pass")),
])
def test_live_check_does_not_print_a_passphrase_that_cannot_be_a_header(live, caplog, passphrase, fragments):
    """Should such a value get past the key file's own check: with a session of
    requests itself, the client's error does not quote it either."""
    caplog.set_level(logging.DEBUG)
    live.monkeypatch.setattr(keys, "load", lambda *args: OKXCredentials(KEY, SECRET, passphrase))
    session, adapter = real_session(as_http_client_sends)
    live.monkeypatch.setattr(
        keys, "OKXPrivate",
        lambda creds, **options: OKXPrivate(creds, session=session, clock=lambda: NOW, **options),
    )
    result = CliRunner().invoke(cli.app, ["live", "check"])
    assert result.exit_code == 1
    assert result.output.strip() == (
        "OKX 正式环境没有应答：OKXError: the API key, its secret or its passphrase holds a character that"
        " cannot be signed with or sent in a request header; nothing was sent"
    )
    assert live.inbox.sent == []
    for text in (result.output, caplog.text):
        assert not any(fragment in text for fragment in (*fragments, KEY, SECRET))


def test_live_check_reports_an_unreachable_exchange(live):
    result = live.run("check", failures=[requests.ConnectionError("down")] * 3)
    assert result.exit_code == 1
    assert "OKX 正式环境没有应答" in result.output and "ConnectionError" in result.output
    assert live.inbox.sent == []


def test_live_check_reports_a_key_okx_refuses(live):
    result = live.run("check", answers=[
        (("GET", "/api/v5/account/config"),
         {"code": "50101", "msg": "APIKey does not match current environment.", "data": []}),
    ])
    assert result.exit_code == 1
    assert result.output.strip() == (
        "OKX 正式环境拒绝了请求：OKXPrivateError: /api/v5/account/config failed with code 50101:"
        " APIKey does not match current environment."
    )
    assert len(live.session.calls) == 1  # it stops at the refusal: no probe is posted


def test_the_other_commands_run_without_the_live_key_file(live):
    live.key_path.unlink()
    live.monkeypatch.setattr(keys, "load", lambda *args: pytest.fail("the live key file was read"))
    live.monkeypatch.setenv("TRADER_CAPITAL", "10000")
    runner = CliRunner()
    assert "模拟账户已建立" in runner.invoke(cli.app, ["init"]).output
    assert "日内模拟账户已建立" in runner.invoke(cli.app, ["intraday", "init"]).output
    for part in ("KEY", "SECRET", "PASSPHRASE"):
        live.monkeypatch.setenv(f"TRADER_OKX_DEMO_{part}", f"demo-{part.lower()}")
    session = FakeSession([
        (("GET", "/api/v5/account/config"), [config_row()]),
        (("GET", "/api/v5/account/balance?ccy=USDT"), [{"details": []}]),
        (("GET", "/api/v5/account/positions?instType=SWAP"), []),
        (("GET", "/api/v5/trade/orders-algo-pending?ordType=conditional&instType=SWAP"), []),
        (PROBE, NO_SUCH_ORDER),
    ])
    live.monkeypatch.setattr(cli, "OKXPrivate", lambda creds: OKXPrivate(creds, session=session, clock=lambda: NOW))
    result = runner.invoke(cli.app, ["demo", "check"])
    assert result.exit_code == 0, result.output
    # The demo account's requests are as before: to its own host, marked as simulated trading.
    assert all(url.startswith("https://www.okx.com/") for url in session.urls)
    assert all(headers["x-simulated-trading"] == "1" for _, _, _, headers in session.calls)
    assert live.inbox.sent == []


def test_an_uncaught_errors_traceback_shows_no_local_variables():
    # The locals of a request's frames hold its headers: the key, the passphrase, the signature.
    assert cli.app.pretty_exceptions_show_locals is False
