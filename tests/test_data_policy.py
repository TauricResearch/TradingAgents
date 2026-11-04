"""A data policy stops a run whose required data is missing, before any model call.

The router turns "no data" into a sentinel so a run survives vendor errors; the
policy is the opt-in way to say some data is required. Unset, nothing is checked.
"""

from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

import cli.main as cli_main
import cli.run as cli_run
from tradingagents.dataflows import data_policy as dp
from tradingagents.dataflows.config import get_config
from tradingagents.default_config import build_default_config
from tradingagents.graph.trading_graph import TradingAgentsGraph

NO_DATA = ("NO_DATA_AVAILABLE: No usable market data for 'DBK' from any configured vendor "
           "(no rows between 2026-01-01 and 2026-10-27). The symbol may be invalid.")
UNAVAILABLE = "DATA_UNAVAILABLE: optional macro_data could not be retrieved (FRED_API_KEY not set). Proceed."


@pytest.fixture
def router(monkeypatch):
    """The router, answering each method from ``answers``; records every call."""
    calls, answers = [], {}

    def route(method, *args):
        calls.append((method, args))
        answer = answers.get(method, "## data")
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(dp, "route_to_vendor", route)
    route.calls, route.answers = calls, answers
    return route


# --- parsing -----------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("value, expected", [
    (None, {}),
    ("", {}),
    ({}, {}),
    ("prices=abort", {"prices": "abort"}),
    (" prices = ABORT , news=warn,", {"prices": "abort", "news": "warn"}),
    ({"Macro": "off", "fundamentals": "warn"}, {"macro": "off", "fundamentals": "warn"}),
])
def test_a_policy_parses_from_a_string_or_a_mapping(value, expected):
    assert dp.parse_data_policy(value) == expected


@pytest.mark.unit
@pytest.mark.parametrize("value, named", [
    ("price=abort", "price"),
    ("prices=stop", "stop"),
    ("prices", "kind=level"),
    ({"prices": "fail"}, "fail"),
])
def test_a_misspelled_policy_is_refused_rather_than_checking_nothing(value, named):
    with pytest.raises(ValueError, match=named):
        dp.parse_data_policy(value)


# --- the check ---------------------------------------------------------------

@pytest.mark.unit
def test_without_a_policy_nothing_is_asked_for(router):
    assert dp.check_data_policy({}, "NVDA", "2026-10-27") == []
    assert dp.check_data_policy({"data_policy": {"prices": "off"}}, "NVDA", "2026-10-27") == []
    assert router.calls == []


@pytest.mark.unit
def test_missing_prices_at_abort_stop_the_run_with_the_routers_reason(router):
    router.answers["get_stock_data"] = NO_DATA

    with pytest.raises(dp.DataPolicyError) as raised:
        dp.check_data_policy({"data_policy": {"prices": "abort"}}, "DBK", "2026-10-27")

    message = str(raised.value)
    assert "DBK on 2026-10-27" in message and "before any model call" in message
    assert "prices: NO_DATA_AVAILABLE: No usable market data for 'DBK'" in message
    assert [gap.kind for gap in raised.value.missing] == ["prices"]
    assert router.calls == [("get_stock_data", ("DBK", "2026-09-27", "2026-10-27"))]


@pytest.mark.unit
def test_missing_data_at_warn_is_returned_and_logged_and_the_run_goes_on(router, caplog):
    router.answers["get_macro_indicators"] = UNAVAILABLE

    missing = dp.check_data_policy({"data_policy": "prices=abort,macro=warn"}, "NVDA", "2026-10-27")

    assert [(gap.kind, gap.level) for gap in missing] == [("macro", "warn")]
    assert missing[0].reason.startswith("DATA_UNAVAILABLE: optional macro_data")
    assert "macro is missing for NVDA" in caplog.text


@pytest.mark.unit
def test_every_gap_is_named_when_the_run_stops(router):
    router.answers.update(get_stock_data=NO_DATA, get_news=UNAVAILABLE)

    with pytest.raises(dp.DataPolicyError) as raised:
        dp.check_data_policy({"data_policy": "prices=abort,news=warn"}, "DBK", "2026-10-27")

    assert [gap.kind for gap in raised.value.missing] == ["prices", "news"]


@pytest.mark.unit
def test_a_vendor_error_counts_as_missing(router):
    router.answers["get_fundamentals"] = ConnectionError("Yahoo unreachable")

    with pytest.raises(dp.DataPolicyError, match="ConnectionError: Yahoo unreachable"):
        dp.check_data_policy({"data_policy": {"fundamentals": "abort"}}, "NVDA", "2026-10-27")


@pytest.mark.unit
def test_served_data_passes_every_kind(router):
    policy = dict.fromkeys(dp.KINDS, "abort")

    assert dp.check_data_policy({"data_policy": policy}, "NVDA", "2026-10-27") == []
    assert [method for method, _ in router.calls] == [
        "get_stock_data", "get_fundamentals", "get_news", "get_macro_indicators"]


@pytest.mark.unit
def test_the_check_reads_the_runs_own_vendors(monkeypatch):
    seen = []
    monkeypatch.setattr(dp, "route_to_vendor",
                        lambda method, *a: seen.append(get_config()["data_vendors"]["core_stock_apis"]) or "ok")

    config = {"data_policy": {"prices": "abort"}, "data_vendors": {"core_stock_apis": "alpha_vantage"}}
    dp.check_data_policy(config, "NVDA", "2026-10-27")

    assert seen == ["alpha_vantage"]


@pytest.mark.unit
def test_the_policy_can_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_DATA_POLICY", "prices=abort")
    assert dp.parse_data_policy(build_default_config()["data_policy"]) == {"prices": "abort"}


@pytest.mark.unit
def test_by_default_no_policy_is_set():
    assert build_default_config()["data_policy"] == {}


# --- the graph ---------------------------------------------------------------

def _bare_graph(config):
    graph = object.__new__(TradingAgentsGraph)
    graph.config = config
    graph.selected_analysts = ("market",)
    return graph


@pytest.mark.unit
def test_propagate_stops_before_the_graph_runs(router, monkeypatch):
    router.answers["get_stock_data"] = NO_DATA
    graph = _bare_graph({**build_default_config(), "data_policy": {"prices": "abort"}})
    monkeypatch.setattr(graph, "_run_graph", lambda *a, **k: pytest.fail("the graph ran"), raising=False)

    with pytest.raises(dp.DataPolicyError):
        graph.propagate("DBK", "2026-10-27")


@pytest.mark.unit
def test_the_policy_does_not_change_a_checkpoint(monkeypatch):
    plain = _bare_graph(build_default_config())
    checked = _bare_graph({**build_default_config(), "data_policy": {"prices": "abort"}})

    assert plain._run_signature("stock") == checked._run_signature("stock")


# --- the CLI -----------------------------------------------------------------

@pytest.mark.unit
def test_the_flag_reaches_the_analysis_parsed(monkeypatch):
    calls = []
    monkeypatch.setattr(cli_main, "run_analysis", lambda **kw: calls.append(kw))

    result = CliRunner().invoke(cli_main.app, ["--data-policy", "prices=abort,news=warn"])

    assert result.exit_code == 0, result.output
    assert calls[0]["data_policy"] == {"prices": "abort", "news": "warn"}


@pytest.mark.unit
def test_a_bad_flag_stops_before_anything_runs(monkeypatch):
    monkeypatch.setattr(cli_main, "run_analysis", lambda **kw: pytest.fail("the analysis ran"))

    result = CliRunner().invoke(cli_main.app, ["--data-policy", "prices=maybe"])

    assert result.exit_code == 1
    assert "unknown level 'maybe'" in result.output


@pytest.mark.unit
def test_the_backtest_runs_under_the_policy(monkeypatch):
    configs = []

    def sweep(tickers, dates, config, **kw):
        configs.append(config)
        raise RuntimeError("stop here")

    monkeypatch.setattr(cli_main, "run_backtest", sweep)

    CliRunner().invoke(cli_main.app, ["backtest", "DBK", "--start", "2026-06-01", "--end", "2026-06-01",
                                      "--data-policy", "prices=abort"])

    assert configs[0]["data_policy"] == {"prices": "abort"}


@pytest.mark.unit
def test_the_help_names_the_kinds_and_levels():
    output = CliRunner().invoke(cli_main.app, ["--help"], terminal_width=200).output
    assert "--data-policy" in output and "fundamentals" in output and "abort" in output


@pytest.mark.unit
def test_the_cli_ends_an_aborted_run_with_the_reason(router, capsys):
    router.answers["get_stock_data"] = NO_DATA

    with pytest.raises(typer.Exit) as stopped:
        cli_run._check_required_data({"data_policy": {"prices": "abort"}}, "DBK", "2026-10-27")

    assert stopped.value.exit_code == 1
    assert "NO_DATA_AVAILABLE" in capsys.readouterr().out


@pytest.mark.unit
def test_the_cli_names_a_gap_at_warn_and_goes_on(router, capsys):
    router.answers["get_news"] = UNAVAILABLE

    cli_run._check_required_data({"data_policy": {"news": "warn"}}, "NVDA", "2026-10-27")

    assert "Missing news, continuing" in capsys.readouterr().out


@pytest.mark.unit
def test_the_cli_checks_nothing_without_a_policy(router):
    cli_run._check_required_data({"data_policy": {}}, "NVDA", "2026-10-27")
    assert router.calls == []


@pytest.mark.unit
def test_an_aborted_cli_run_never_builds_a_model(router, monkeypatch):
    from cli.models import AnalystType

    router.answers["get_stock_data"] = NO_DATA
    monkeypatch.setattr(cli_run, "unattended_gaps", lambda flags: [])
    monkeypatch.setattr(cli_run, "get_user_selections", lambda flags=None: {
        "ticker": "DBK", "analysis_date": "2026-10-27",
        "analysts": [AnalystType.MARKET], "asset_type": "stock",
    })
    monkeypatch.setattr(cli_run, "_build_run_config", lambda selections, checkpoint: {})
    monkeypatch.setattr(cli_run, "TradingAgentsGraph", lambda *a, **k: pytest.fail("a model was built"))

    with pytest.raises(typer.Exit):
        cli_run.run_analysis(data_policy={"prices": "abort"})


@pytest.mark.unit
def test_a_cause_with_sentences_of_its_own_is_kept_whole(router):
    router.answers["get_macro_indicators"] = (
        "DATA_UNAVAILABLE: optional macro_data could not be retrieved (FRED_API_KEY is not set. "
        "Get a free key at https://fred.example/key.html.). Proceed without it; do not fabricate values.")

    (gap,) = dp.check_data_policy({"data_policy": {"macro": "warn"}}, "NVDA", "2026-10-27")

    assert gap.reason.endswith("(FRED_API_KEY is not set. Get a free key at https://fred.example/key.html.)")
