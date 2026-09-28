"""Headless CLI defaults, validation, config precedence and automatic exports.

The graph is replaced at its construction seam. CLI parsing, config resolution,
portfolio loading and the Markdown writer are real; no LLM/network is used.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from typer.testing import CliRunner

import cli.headless as h
import cli.main as main
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.reporting import write_report_tree


@pytest.fixture
def base_config(tmp_path, monkeypatch):
    for name in ("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "TRADINGAGENTS_MAX_RISK_ROUNDS"):
        monkeypatch.delenv(name, raising=False)
    config = deepcopy(DEFAULT_CONFIG)
    config.update(
        results_dir=str(tmp_path / "results"), data_cache_dir=str(tmp_path / "cache"),
        memory_log_path=str(tmp_path / "memory.md"), llm_provider="openai",
        quick_think_llm="gpt-4.1-mini", deep_think_llm="gpt-4.1",
        llm_headers=None, max_debate_rounds=1, max_risk_discuss_rounds=1,
        max_tokens=None, llm_max_retries=None, temperature=None,
    )
    monkeypatch.setattr(main, "DEFAULT_CONFIG", config)
    monkeypatch.setattr(h, "get_current_date", lambda: "2026-09-27")
    return config


@pytest.fixture
def graph_calls(monkeypatch):
    calls = []

    class Graph:
        def __init__(self, selected_analysts, config):
            self.config = config
            calls.append({"analysts": selected_analysts, "config": config})

        def propagate(self, ticker, date, *, asset_type, portfolio):
            calls[-1].update(ticker=ticker, date=date, asset_type=asset_type, portfolio=portfolio)
            return {
                "market_report": "Market report", "sentiment_report": "Sentiment report",
                "news_report": "News report", "fundamentals_report": "Fundamentals report",
                "investment_debate_state": {"bull_history": "Bull", "bear_history": "Bear", "judge_decision": "Research"},
                "trader_investment_plan": "Plan",
                "risk_debate_state": {"aggressive_history": "Aggressive", "conservative_history": "Conservative",
                                      "neutral_history": "Neutral", "judge_decision": "Hold"},
                "final_trade_decision": "Hold",
            }, "Hold"

        def save_reports(self, state, ticker, save_path):
            calls[-1]["saved"] = Path(save_path)
            return write_report_tree(state, ticker, save_path)

    monkeypatch.setattr(h, "_create_graph", Graph)

    def no_interactive(**kwargs):
        pytest.fail("Headless analysis entered the interactive runner")

    monkeypatch.setattr(main, "run_analysis", no_interactive)
    return calls


@pytest.fixture
def runner(base_config, graph_calls):
    return CliRunner()


def test_symbol_only_is_today_all_analysts_medium_and_saves(runner, graph_calls, base_config):
    result = runner.invoke(main.app, ["analyze", "nvda"])
    assert result.exit_code == 0, result.output
    call = graph_calls[0]
    assert call["ticker"] == "NVDA"
    assert call["date"] == "2026-09-27"
    assert call["analysts"] == ["market", "social", "news", "fundamentals"]
    assert call["config"]["max_debate_rounds"] == 3
    assert call["config"]["max_risk_discuss_rounds"] == 3
    assert call["config"]["data_cache_dir"] == base_config["data_cache_dir"]
    assert call["config"]["memory_log_path"] == base_config["memory_log_path"]
    assert base_config["max_debate_rounds"] == 1
    assert "Save report?" not in result.output
    assert (call["saved"] / "complete_report.md").exists()
    assert (call["saved"] / "1_analysts" / "market.md").exists()
    assert (call["saved"] / "5_portfolio" / "decision.md").exists()
    metadata = json.loads((call["saved"].parent / "run.json").read_text())
    assert metadata["decision"] == "Hold"
    assert metadata["report"] in result.output


def test_symbol_is_mandatory(runner, graph_calls):
    result = runner.invoke(main.app, ["analyze"])
    assert result.exit_code == 2
    assert "Missing argument" in result.output
    assert graph_calls == []


@pytest.mark.parametrize("argv,rounds", [([], 3), (["--effort", "shallow"], 1),
    (["--effort", "medium"], 3), (["--effort", "deep"], 5), (["--depth", "DEEP"], 5)])
def test_effort_levels(runner, graph_calls, argv, rounds):
    result = runner.invoke(main.app, ["analyze", "NVDA", *argv])
    assert result.exit_code == 0, result.output
    assert graph_calls[0]["config"]["max_debate_rounds"] == rounds
    assert graph_calls[0]["config"]["max_risk_discuss_rounds"] == rounds


def test_env_rounds_then_explicit_effort_then_specific_rounds(base_config, monkeypatch):
    base_config.update(max_debate_rounds=7, max_risk_discuss_rounds=8)
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "7")
    monkeypatch.setenv("TRADINGAGENTS_MAX_RISK_ROUNDS", "8")
    env = h.build_headless_config(base_config)
    assert (env["max_debate_rounds"], env["max_risk_discuss_rounds"]) == (7, 8)
    explicit = h.build_headless_config(base_config, effort="shallow", risk_rounds=4)
    assert (explicit["max_debate_rounds"], explicit["max_risk_discuss_rounds"]) == (1, 4)
    # A single explicit env count does not turn the other headless default to 1.
    monkeypatch.delenv("TRADINGAGENTS_MAX_RISK_ROUNDS")
    partial = h.build_headless_config(base_config)
    assert (partial["max_debate_rounds"], partial["max_risk_discuss_rounds"]) == (7, 3)


def test_overrides_reach_graph(runner, graph_calls, tmp_path):
    output = tmp_path / "chosen-run"
    result = runner.invoke(main.app, [
        "analyze", "700.HK", "--date", "2026-09-25", "--analysts", "news,sentiment,market,market",
        "--effort", "deep", "--debate-rounds", "2", "--risk-rounds", "4",
        "--provider", "opencode-go", "--quick-model", "glm-5.3-flash", "--deep-model", "kimi-k3",
        "--backend-url", "https://example.test/v1", "--header", "X-Test: one:two",
        "--language", "Chinese", "--max-tokens", "8192", "--max-retries", "0",
        "--temperature", "0.2", "--checkpoint", "--output-dir", str(output),
    ])
    assert result.exit_code == 0, result.output
    call = graph_calls[0]
    assert call["ticker"] == "0700.HK"
    assert call["date"] == "2026-09-25"
    assert call["analysts"] == ["market", "social", "news"]
    config = call["config"]
    assert config["llm_provider"] == "opencode-go"
    assert config["quick_think_llm"] == "glm-5.3-flash"
    assert config["deep_think_llm"] == "kimi-k3"
    assert config["backend_url"] == "https://example.test/v1"
    assert config["llm_headers"] == {"X-Test": "one:two"}
    assert config["output_language"] == "Chinese"
    assert config["max_tokens"] == 8192 and config["llm_max_retries"] == 0
    assert config["temperature"] == 0.2
    assert config["checkpoint_enabled"] is True
    assert (config["max_debate_rounds"], config["max_risk_discuss_rounds"]) == (2, 4)
    assert call["saved"] == output / "reports"


@pytest.mark.parametrize("argv,expected", [
    (["--date", "2099-01-01"], "future"), (["--date", "2026-9-01"], "YYYY-MM-DD"),
    (["--date", "2026-02-30"], "YYYY-MM-DD"), (["--date", ""], "YYYY-MM-DD"),
    (["--analysts", ""], "analysts"), (["--analysts", "market,"], "analysts"),
    (["--analysts", "unknown"], "analysts"), (["--analysts", "all,market"], "analysts"),
    (["--effort", "typo"], "Invalid value"), (["--debate-rounds", "0"], "Invalid value"),
    (["--risk-rounds", "-1"], "Invalid value"), (["--max-tokens", "0"], "Invalid value"),
    (["--max-retries", "-1"], "Invalid value"), (["--temperature", "nan"], "finite"),
    (["--header", "missing-colon"], "header"), (["--header", "X-Test: value\nsecret"], "control"),
    (["--provider", "opencode-go"], "both --quick-model and --deep-model"),
])
def test_bad_inputs_never_construct_graph(runner, graph_calls, argv, expected):
    result = runner.invoke(main.app, ["analyze", "NVDA", *argv])
    assert result.exit_code != 0
    assert expected in result.output
    assert graph_calls == []
    assert "Traceback" not in result.output


@pytest.mark.parametrize("symbol", ["", "..", "../../etc", "AAPL,MSFT", "A" * 33])
def test_bad_symbol_never_constructs_graph(runner, graph_calls, symbol):
    result = runner.invoke(main.app, ["analyze", symbol])
    assert result.exit_code != 0
    assert graph_calls == []


def test_json_stdout_and_tool_diagnostics_stderr(runner, monkeypatch):
    def noisy_run(*args, **kwargs):
        print("diagnostic from a tool")
        return {"symbol": "NVDA", "decision": "Hold"}

    monkeypatch.setattr(main, "run_headless_analysis", noisy_run)
    result = runner.invoke(main.app, ["analyze", "NVDA", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"symbol": "NVDA", "decision": "Hold"}
    assert "diagnostic from a tool" in result.stderr


def test_json_and_saved_metadata_match_without_header_secrets(runner, graph_calls):
    result = runner.invoke(main.app, ["analyze", "NVDA", "--json", "--header", "X-Secret: never-print-me"])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary == json.loads((Path(summary["output_dir"]) / "run.json").read_text())
    assert "never-print-me" not in result.output
    assert graph_calls[0]["config"]["llm_headers"]["X-Secret"] == "never-print-me"


def test_repeated_run_uses_different_state_and_report_roots(runner, graph_calls):
    for _ in range(2):
        assert runner.invoke(main.app, ["analyze", "NVDA"]).exit_code == 0
    assert graph_calls[0]["config"]["results_dir"] != graph_calls[1]["config"]["results_dir"]
    assert graph_calls[0]["saved"] != graph_calls[1]["saved"]


def test_output_directory_cannot_overwrite_existing_files(runner, graph_calls, tmp_path):
    (tmp_path / "keep.txt").write_text("keep")
    result = runner.invoke(main.app, ["analyze", "NVDA", "--output-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "new or empty" in result.output
    assert graph_calls == []
    assert (tmp_path / "keep.txt").read_text() == "keep"


def test_results_root_override(runner, graph_calls, tmp_path):
    root = tmp_path / "other-root"
    result = runner.invoke(main.app, ["analyze", "NVDA", "--results-dir", str(root)])
    assert result.exit_code == 0, result.output
    assert Path(graph_calls[0]["config"]["results_dir"]).parent == root / "runs"


def test_headers_merge_case_insensitively_without_mutating_defaults(base_config):
    base_config["llm_headers"] = '{"X-Keep":"unchanged","x-replace":"old"}'
    config = h.build_headless_config(base_config, headers=["X-Replace: first", "X-REPLACE: last"])
    assert config["llm_headers"] == {"X-Keep": "unchanged", "X-REPLACE": "last"}
    assert base_config["llm_headers"] == '{"X-Keep":"unchanged","x-replace":"old"}'


def test_provider_change_drops_unrelated_endpoint_and_headers(base_config):
    base_config["backend_url"] = "https://old-provider.example/v1"
    base_config["llm_headers"] = {"X-Private": "old-secret"}
    config = h.build_headless_config(base_config, llm_provider="opencode-go",
        quick_think_llm="glm-5.3-flash", deep_think_llm="kimi-k3")
    assert config["backend_url"] is None and config["llm_headers"] is None
    assert base_config["llm_headers"] == {"X-Private": "old-secret"}


def test_go_environment_config_is_preserved(base_config):
    base_config.update(llm_provider="opencode-go", quick_think_llm="glm-5.3-flash",
                       deep_think_llm="kimi-k3", opencode_go_api="auto")
    config = h.build_headless_config(base_config)
    assert config["llm_provider"] == "opencode-go"
    assert config["opencode_go_api"] == "auto"
    assert config["quick_think_llm"] == "glm-5.3-flash"


def test_numeric_env_strings_are_accepted(base_config):
    base_config.update(max_tokens="8192", llm_max_retries="0", temperature="0.2")
    config = h.build_headless_config(base_config)
    assert config["max_tokens"] == 8192
    assert config["llm_max_retries"] == 0
    assert config["temperature"] == 0.2


@pytest.mark.parametrize("override", [{"max_tokens": True}, {"max_tokens": 1.2},
    {"llm_max_retries": -1}, {"temperature": "nan"}, {"temperature": "inf"}])
def test_invalid_numeric_config_is_rejected(base_config, override):
    with pytest.raises(ValueError):
        h.build_headless_config({**base_config, **override})


def test_crypto_matches_interactive_applicable_analysts(runner, graph_calls):
    result = runner.invoke(main.app, ["analyze", "BTCUSDT"])
    assert result.exit_code == 0, result.output
    assert graph_calls[0]["ticker"] == "BTC-USD"
    assert graph_calls[0]["asset_type"] == "crypto"
    assert graph_calls[0]["analysts"] == ["market", "social", "news"]


def test_crypto_explicit_fundamentals_is_not_silently_dropped(runner, graph_calls):
    result = runner.invoke(main.app, ["analyze", "BTC-USD", "--analysts", "fundamentals"])
    assert result.exit_code == 1
    assert graph_calls == []


def test_explicit_asset_type(runner, graph_calls):
    assert runner.invoke(main.app, ["analyze", "ABC-USD", "--asset-type", "stock"]).exit_code == 0
    assert graph_calls[0]["asset_type"] == "stock"
    assert len(graph_calls[0]["analysts"]) == 4


def test_portfolio_is_loaded_without_prompt(runner, graph_calls, tmp_path):
    path = tmp_path / "portfolio.json"
    path.write_text('{"cash":1000,"currency":"USD","positions":[]}')
    result = runner.invoke(main.app, ["analyze", "NVDA", "--portfolio", str(path)])
    assert result.exit_code == 0, result.output
    assert graph_calls[0]["portfolio"].cash == 1000


def test_invalid_portfolio_fails_before_graph(runner, graph_calls, tmp_path):
    path = tmp_path / "bad-portfolio.json"
    path.write_text("{not json}")
    result = runner.invoke(main.app, ["analyze", "NVDA", "--portfolio", str(path)])
    assert result.exit_code == 1
    assert graph_calls == []


def test_no_checkpoint_overrides_env(runner, graph_calls, base_config):
    base_config["checkpoint_enabled"] = True
    result = runner.invoke(main.app, ["analyze", "NVDA", "--no-checkpoint"])
    assert result.exit_code == 0, result.output
    assert graph_calls[0]["config"]["checkpoint_enabled"] is False


@pytest.mark.parametrize("failure_point", ["constructor", "propagate", "save_reports"])
def test_runtime_and_save_errors_are_nonzero_without_traceback(runner, monkeypatch, failure_point):
    class BrokenGraph:
        def propagate(self, *a, **kw):
            if failure_point == "propagate":
                raise RuntimeError("request failed")
            return {}, "Hold"

        def save_reports(self, *a, **kw):
            raise OSError("report write failed")

    def factory(*a):
        if failure_point == "constructor":
            raise ValueError("Set OPENCODE_GO_API_KEY")
        return BrokenGraph()

    monkeypatch.setattr(h, "_create_graph", factory)
    result = runner.invoke(main.app, ["analyze", "NVDA", "--json"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Error:" in result.stderr
    assert "Traceback" not in result.output


def test_parent_options_are_not_silently_ignored(runner, graph_calls):
    result = runner.invoke(main.app, ["--checkpoint", "analyze", "NVDA"])
    assert result.exit_code == 2
    assert "--checkpoint" in result.output and "analyze" in result.output
    assert graph_calls == []


def test_interactive_entry_point_is_unchanged(base_config, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "run_analysis", lambda **kw: calls.append(kw))
    result = CliRunner().invoke(main.app, [])
    assert result.exit_code == 0, result.output
    assert calls == [{"checkpoint": None, "portfolio": None}]


def test_command_help_lists_the_new_parameters(runner, graph_calls):
    import re

    result = runner.invoke(main.app, ["analyze", "--help"])
    assert result.exit_code == 0, result.output
    text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    for option in ("--date", "--analysts", "--effort", "--provider", "--header", "--output-dir", "--json"):
        assert option in text
    assert graph_calls == []
