"""AgentFeed crypto-derivatives vendor: when it calls and when it does not, the
report it renders, failure handling, key hygiene, routing, and the market
analyst's wiring (a stock run is offered exactly what it was before).

All API access is mocked, so these run without a network connection or a key.
"""
import logging
from unittest import mock

import pytest
import requests
from langchain_core.messages import AIMessage

from tradingagents import __version__
from tradingagents.agents import tools
from tradingagents.agents.analysts import market_analyst
from tradingagents.dataflows import date_window, router
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import VendorNotConfiguredError, VendorUnavailableError
from tradingagents.dataflows.vendors import agentfeed
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS

KEY = "afk_TESTKEY0123456789abcdef"
TODAY = "2026-10-14"

# Shaped like the "data" of a live /api/coin-signal/BTC answer (14 Oct 2026).
SIGNAL = {
    "coin": "BTC",
    "oi_rank": 1,
    "as_of": "2026-10-14T17:30:00.000Z",
    "mark": 112345.0,
    "chg_1h_pct": -0.42,
    "chg_24h_pct": 1.21,
    "funding_1h": 0.0000125,
    "funding_ann_pct": 10.95,
    "oi_usd": 2_134_000_000,
    "oi_chg_1h_pct": 0.31,
    "oi_chg_24h_pct": 4.82,
    "liq_1h_long_usd": 1_204_000,
    "liq_1h_short_usd": 310_000,
    "liq_z": 2.14,
    "whale_net_usd": 45_000_000,
    "whale_tilt": 0.34,
    "flags": ["crowded_long", "liq_spike"],
    "cascade_15m": {"p": 0.0421, "evidence": "measured", "threshold_usd": 5_000_000,
                    "window_end": "2026-10-14T17:30:00.000Z"},
    "liq_cluster_above": {"price_low": 114000, "price_high": 114500, "usd": 8_200_000,
                          "longs_usd": 0, "shorts_usd": 8_200_000, "distance_pct": 1.69},
    "liq_cluster_below": {"price_low": 108000, "price_high": 108500, "usd": 6_100_000,
                          "longs_usd": 6_100_000, "shorts_usd": 0, "distance_pct": -3.65},
    "whale_top": [
        {"side": "long", "size_usd": 120_000_000, "entry_px": 108200, "liquidation_px": 89000},
        {"side": "short", "size_usd": 40_000_000, "entry_px": 115100, "liquidation_px": 131000},
    ],
    "sources": {
        "hl_oi": {"as_of": "2026-10-14T17:30:00.000Z"},
        "liq_tape": {"as_of": "2026-10-14T17:31:02.000Z"},
        "hl_whales": {"as_of": "2026-10-14T17:29:40.000Z"},
        "cascade_forecast": {"as_of": "2026-10-14T17:30:00.000Z"},
        "liq_heatmap": {"as_of": "2026-10-14T17:31:02.000Z"},
    },
}


def _response(status, body):
    response = mock.Mock(status_code=status)
    response.json.return_value = body
    return response


def _ok(data=SIGNAL):
    """A 200 in AgentFeed's envelope: {"tool": ..., "data": {...}, "paid": ...}."""
    return _response(200, {"tool": "get_coin_signal", "data": data, "paid": True})


@pytest.fixture(autouse=True)
def _today_and_key(monkeypatch):
    monkeypatch.setattr(date_window, "get_current_date", lambda: TODAY)
    monkeypatch.setenv("AGENTFEED_API_KEY", KEY)


@pytest.fixture
def get():
    with mock.patch.object(agentfeed.requests, "get", return_value=_ok()) as patched:
        yield patched


# ---- when it calls ------------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("symbol", ["AAPL", "SPY", "GC=F", "EURUSD"])
def test_a_non_crypto_symbol_is_not_applicable_and_sends_nothing(get, symbol):
    out = agentfeed.get_crypto_derivatives(symbol, TODAY)
    assert "does not apply" in out
    get.assert_not_called()


@pytest.mark.unit
def test_without_a_key_nothing_is_sent_and_the_run_goes_on(get, monkeypatch):
    monkeypatch.delenv("AGENTFEED_API_KEY")
    with pytest.raises(VendorNotConfiguredError, match="AGENTFEED_API_KEY is not set"):
        agentfeed.get_crypto_derivatives("BTC-USD", TODAY)
    out = router.route_to_vendor("get_crypto_derivatives", "BTC-USD", TODAY)
    assert out.startswith("DATA_UNAVAILABLE: optional crypto_derivatives")
    assert "AGENTFEED_API_KEY is not set" in out
    assert "http" not in out and "ochinimus" not in out  # no buy link reaches the model
    get.assert_not_called()


@pytest.mark.unit
def test_a_past_dated_run_is_withheld_and_sends_nothing(get):
    out = agentfeed.get_crypto_derivatives("BTC-USD", "2026-10-13")
    assert "withheld for 2026-10-13" in out
    assert "current state" in out
    get.assert_not_called()


@pytest.mark.unit
def test_todays_run_sends_one_identified_request_with_the_key_in_a_header(get):
    agentfeed.get_crypto_derivatives("BTC-USD", TODAY)
    get.assert_called_once()
    url = get.call_args.args[0]
    kwargs = get.call_args.kwargs
    assert url == "https://x402.ochinimus.app/api/coin-signal/BTC"
    assert KEY not in url
    assert kwargs["headers"]["X-AgentFeed-Key"] == KEY
    assert kwargs["headers"]["User-Agent"].startswith(f"TradingAgents/{__version__}")
    assert kwargs["timeout"] == agentfeed.REQUEST_TIMEOUT


@pytest.mark.unit
@pytest.mark.parametrize("symbol", ["BTC-USD", "BTCUSD", "BTC-USDT", "btc-usdc", "BTCUSD+"])
def test_every_symbol_form_asks_for_the_base_coin(get, symbol):
    agentfeed.get_crypto_derivatives(symbol, TODAY)
    assert get.call_args.args[0].endswith("/api/coin-signal/BTC")


# ---- what it renders ----------------------------------------------------------------------------


@pytest.mark.unit
def test_the_report_carries_the_key_fields(get):
    out = agentfeed.get_crypto_derivatives("BTC-USD", TODAY)
    for expected in (
        "BTC perpetual, as of 2026-10-14T17:30:00.000Z",
        "Mark 112,345", "1h -0.42%", "24h +1.21%",
        "Funding +10.95% annualized",
        "Open interest $2.13B", "24h +4.82%",
        "longs $1.20M", "shorts $310.00K", "z-score 2.14",
        "Flags: crowded_long, liq_spike",
        "+0.34 (net $45.00M)",
        "above: 114,000-114,500, $8.20M, +1.69% from mark",
        "below: 108,000-108,500, $6.10M, -3.65% from mark",
        "long $120.00M entry 108,200 liq 89,000",
        "cascade probability: 4.2%",
        "Source: AgentFeed (x402.ochinimus.app): Hyperliquid perps for price, funding, open "
        "interest and positions; AgentFeed's cross-venue liquidation tape for liquidations, "
        "clusters and the cascade model.",
        "liq_tape 2026-10-14T17:31:02.000Z",
    ):
        assert expected in out, expected
    assert len(out) < 1500


@pytest.mark.unit
def test_missing_values_render_as_unavailable_not_as_numbers(get):
    sparse = {**SIGNAL, "liq_1h_long_usd": None, "liq_1h_short_usd": None, "liq_z": None,
              "whale_tilt": None, "whale_net_usd": None, "flags": [], "whale_top": [],
              "liq_cluster_above": None, "cascade_15m": {"p": None, "reason": "model not loaded"}}
    get.return_value = _ok(sparse)
    out = agentfeed.get_crypto_derivatives("ETH-USD", TODAY)
    assert "longs n/a, shorts n/a; z-score n/a" in out
    assert "None" not in out
    assert "tilt (top 250 Hyperliquid accounts, -1 all short to +1 all long): n/a" in out
    assert "Flags: none" in out
    assert "Largest positions: none" in out
    assert "cluster above: none" in out
    assert "unavailable (model not loaded)" in out


# ---- failures -----------------------------------------------------------------------------------


FAILURES = {
    "400": lambda: _response(400, {"error": 'unknown Hyperliquid perp "BTC"'}),
    "401": lambda: _response(401, {"error": f"unknown key {KEY}"}),
    "402": lambda: _response(402, {"error": "balance is empty"}),
    "503": lambda: _response(503, {"error": "signals: the tape is stale"}),
    "not json": lambda: mock.Mock(status_code=200, json=mock.Mock(
        side_effect=requests.exceptions.JSONDecodeError("x", "doc", 0))),
    "not an object": lambda: _response(200, ["BTC"]),
    "no data": lambda: _response(200, {"tool": "get_coin_signal", "paid": True}),
    "bare signal": lambda: _response(200, SIGNAL),   # unwrapped: not AgentFeed's shape
    "timeout": requests.Timeout(f"read timed out, headers {KEY}"),
    "network": requests.ConnectionError(f"connection refused, headers {KEY}"),
}


def _patch(failure):
    if isinstance(failure, Exception):
        return mock.patch.object(agentfeed.requests, "get", side_effect=failure)
    return mock.patch.object(agentfeed.requests, "get", return_value=failure())


@pytest.mark.unit
@pytest.mark.parametrize("name", FAILURES)
def test_a_failed_request_is_unavailable_and_the_run_goes_on(name):
    with _patch(FAILURES[name]):
        with pytest.raises(VendorUnavailableError):
            agentfeed.get_crypto_derivatives("BTC-USD", TODAY)
        out = router.route_to_vendor("get_crypto_derivatives", "BTC-USD", TODAY)
    assert out.startswith("DATA_UNAVAILABLE")


@pytest.mark.unit
@pytest.mark.parametrize("name", FAILURES)
def test_the_key_never_reaches_an_error_a_log_or_a_report(name, caplog):
    caplog.set_level(logging.DEBUG)
    with _patch(FAILURES[name]):
        with pytest.raises(VendorUnavailableError) as caught:
            agentfeed.get_crypto_derivatives("BTC-USD", TODAY)
        out = router.route_to_vendor("get_crypto_derivatives", "BTC-USD", TODAY)
    error = caught.value
    assert error.__cause__ is None and error.__context__ is None
    for text in (str(error), repr(error), out, caplog.text):
        assert KEY not in text


@pytest.mark.unit
def test_the_key_is_not_in_a_successful_report(get):
    assert KEY not in agentfeed.get_crypto_derivatives("BTC-USD", TODAY)


# ---- routing and tool -----------------------------------------------------------------------------


@pytest.mark.unit
def test_the_category_is_optional_and_routes_to_agentfeed(get):
    assert router.get_category_for_method("get_crypto_derivatives") == "crypto_derivatives"
    assert "crypto_derivatives" in router.OPTIONAL_CATEGORIES
    assert DEFAULT_CONFIG["data_vendors"]["crypto_derivatives"] == "agentfeed"
    set_config({"data_vendors": {"crypto_derivatives": "agentfeed"}})
    assert "BTC perpetual" in router.route_to_vendor("get_crypto_derivatives", "BTC-USD", TODAY)


@pytest.mark.unit
def test_the_model_sees_only_the_date():
    properties = tools.get_crypto_derivatives.tool_call_schema.model_json_schema()["properties"]
    assert set(properties) == {"curr_date"}


@pytest.mark.unit
def test_the_tool_clamps_a_later_date_to_the_run_date(get):
    with mock.patch.object(tools, "route_to_vendor", return_value="ok") as routed:
        tools.get_crypto_derivatives.func("BTC-USD", "2026-10-20", trade_date="2026-10-13")
    assert routed.call_args.args == ("get_crypto_derivatives", "BTC-USD", "2026-10-13")


# ---- market analyst wiring ------------------------------------------------------------------------


def _offered(asset_type):
    """The tools the market analyst binds, and its rendered system prompt."""
    seen = {}

    def take_turn(prompt, llm, offered, messages):
        seen["tools"] = offered
        seen["prompt"] = prompt.format_messages(messages=messages)[0].content
        return AIMessage("report"), "report"

    state = {"trade_date": TODAY, "messages": [], "asset_type": asset_type,
             "company_of_interest": "BTC-USD" if asset_type == "crypto" else "NVDA",
             "instrument_context": "The instrument is under analysis."}
    with mock.patch.object(market_analyst, "take_turn", take_turn):
        market_analyst.create_market_analyst(object())(state)
    return seen["tools"], seen["prompt"]


@pytest.mark.unit
def test_a_stock_run_is_offered_the_market_tools_alone():
    offered, prompt = _offered("stock")
    assert offered == market_analyst.TOOLS
    assert "get_crypto_derivatives" not in prompt
    assert market_analyst.CRYPTO_BRIEF.strip() not in prompt


@pytest.mark.unit
def test_a_crypto_run_with_the_key_is_offered_the_derivatives_tool_and_told_of_it():
    offered, prompt = _offered("crypto")
    assert offered == market_analyst.TOOLS + (tools.get_crypto_derivatives,)
    assert "get_crypto_derivatives" in prompt
    assert market_analyst.CRYPTO_BRIEF.strip() in prompt


@pytest.mark.unit
def test_a_crypto_run_without_the_key_is_offered_what_it_was_before(monkeypatch):
    """Opt-in: no key means no tool, no brief and no mention of the vendor, so
    the model has nothing to call and nothing to report about it."""
    monkeypatch.delenv("AGENTFEED_API_KEY")
    offered, prompt = _offered("crypto")
    assert offered == market_analyst.TOOLS
    for absent in ("get_crypto_derivatives", "perpetual", "AgentFeed", "ochinimus"):
        assert absent not in prompt


@pytest.mark.unit
@pytest.mark.parametrize("chain, key, expected", [
    ("agentfeed", True, True),
    ("default", True, True),
    ("some_other_vendor", True, False),   # AgentFeed not chosen: never offered
    ("agentfeed", False, False),          # chosen but no key: never offered
])
def test_the_tool_is_offered_only_when_the_chain_can_serve_it(monkeypatch, chain, key, expected):
    if not key:
        monkeypatch.delenv("AGENTFEED_API_KEY")
    set_config({"data_vendors": {"crypto_derivatives": chain}})
    assert router.crypto_derivatives_available() is expected
    assert (market_analyst.tools_for("crypto") == market_analyst.ALL_TOOLS) is expected
    assert market_analyst.tools_for("stock") == market_analyst.TOOLS


@pytest.mark.unit
def test_the_market_tool_node_can_run_the_derivatives_tool():
    assert tools.get_crypto_derivatives in ANALYST_NODE_SPECS["market"].tools
