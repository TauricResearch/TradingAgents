"""Headless defaults and native execution/artifact parity; no live model calls."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from typer.testing import CliRunner

import cli.headless as h
import cli.main as main
import cli.run as native
from cli.models import AnalystType
from tests.native_cli_helpers import RecordingGraph
from tradingagents.default_config import DEFAULT_CONFIG


@pytest.fixture
def setup(tmp_path, monkeypatch):
    for name in ("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "TRADINGAGENTS_MAX_RISK_ROUNDS"):
        monkeypatch.delenv(name, raising=False)
    config = deepcopy(DEFAULT_CONFIG)
    config.update(results_dir=str(tmp_path / "results"), data_cache_dir=str(tmp_path / "cache"),
                  memory_log_path=str(tmp_path / "memory.md"), llm_provider="openai",
                  quick_think_llm="gpt-4.1-mini", deep_think_llm="gpt-4.1", llm_headers=None,
                  max_tokens=None, llm_max_retries=None, temperature=None, checkpoint_enabled=False)
    monkeypatch.setattr(main, "DEFAULT_CONFIG", config)
    monkeypatch.setattr(h, "get_current_date", lambda: "2026-09-27")
    monkeypatch.setattr(native, "get_current_date", lambda: "2026-09-27")
    graphs = []

    def create(analysts, settings, callbacks=None):
        graph = RecordingGraph(analysts, settings, callbacks)
        graphs.append(graph)
        return graph

    monkeypatch.setattr(h, "_create_graph", create)
    monkeypatch.setattr(native, "get_user_selections", lambda: pytest.fail("headless opened the wizard"))
    return config, graphs, CliRunner()


def test_symbol_only_uses_native_paths_and_default_settings(setup):
    config, graphs, runner = setup
    out = runner.invoke(main.app, ["analyze", "nvda", "--json"])
    assert out.exit_code == 0, out.output
    summary = json.loads(out.stdout)
    root = Path(config["results_dir"])
    run = root / "NVDA" / "2026-09-27"
    assert Path(summary["output_dir"]) == run
    assert not (root / "runs").exists()
    assert graphs[0].config["results_dir"] == config["results_dir"]
    assert graphs[0].selected == ["market", "social", "news", "fundamentals"]
    assert (summary["debate_rounds"], summary["risk_rounds"]) == (3, 3)
    assert summary["date"] == "2026-09-27"
    assert summary["status"] == "completed"
    assert summary == json.loads((run / "run.json").read_text())
    assert Path(summary["report"]).parent.parent == root / "reports"
    for name in ("market_report", "sentiment_report", "news_report", "fundamentals_report",
                 "investment_plan", "trader_investment_plan", "final_trade_decision"):
        assert (run / "reports" / f"{name}.md").is_file()
    assert (root / "NVDA" / "TradingAgentsStrategy_logs" / "full_states_log_2026-09-27.json").is_file()
    log = (run / "message_tool.log").read_text()
    assert log.count("[Tool Call] get_stock_data(symbol=NVDA)") == 1
    assert log.count("[Agent] NVDA market_report 中文") == 1
    assert "Save report?" not in out.output
    assert [call[0] for call in graphs[0].calls] == ["create", "begin", "stream", "json", "record", "clear", "end"]


@pytest.mark.parametrize("argv,expected", [([], 3), (["--effort", "shallow"], 1),
    (["--effort", "medium"], 3), (["--effort", "deep"], 5), (["--depth", "DEEP"], 5)])
def test_effort_defaults_and_presets(setup, argv, expected):
    _, graphs, runner = setup
    result = runner.invoke(main.app, ["analyze", "NVDA", *argv])
    assert result.exit_code == 0, result.output
    assert graphs[0].config["max_debate_rounds"] == expected
    assert graphs[0].config["max_risk_discuss_rounds"] == expected


def test_env_then_effort_then_explicit_round_precedence(setup, monkeypatch):
    base, _, _ = setup
    base.update(max_debate_rounds=7, max_risk_discuss_rounds=8)
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "7")
    monkeypatch.setenv("TRADINGAGENTS_MAX_RISK_ROUNDS", "8")
    assert h.build_headless_config(base)["max_debate_rounds"] == 7
    configured = h.build_headless_config(base, effort="shallow", risk_rounds=4)
    assert (configured["max_debate_rounds"], configured["max_risk_discuss_rounds"]) == (1, 4)
    monkeypatch.delenv("TRADINGAGENTS_MAX_RISK_ROUNDS")
    assert h.build_headless_config(base)["max_risk_discuss_rounds"] == 3


def test_flags_and_export_override_do_not_move_native_logs(setup, tmp_path):
    base, graphs, runner = setup
    export = tmp_path / "export"
    export.mkdir()
    (export / "keep.txt").write_text("keep")
    out = runner.invoke(main.app, ["analyze", "700.HK", "--date", "2026-09-25",
        "--analysts", "news,sentiment,market,market", "--effort", "deep", "--debate-rounds", "2",
        "--risk-rounds", "4", "--provider", "opencode-go", "--quick-model", "glm-5.3-flash",
        "--deep-model", "kimi-k3", "--backend-url", "https://example.test/v1",
        "--header", "X-Test: one:two", "--language", "Chinese", "--max-tokens", "8192",
        "--max-retries", "0", "--temperature", "0.2", "--checkpoint", "--output-dir", str(export), "--json"])
    assert out.exit_code == 0, out.output
    graph = graphs[0]
    assert graph.selected == ["market", "social", "news"]
    assert graph.ticker == "0700.HK"
    assert graph.date == "2026-09-25"
    for key, expected in {"llm_provider": "opencode-go", "quick_think_llm": "glm-5.3-flash",
                         "deep_think_llm": "kimi-k3", "backend_url": "https://example.test/v1",
                         "llm_headers": {"X-Test": "one:two"}, "output_language": "Chinese",
                         "max_tokens": 8192, "llm_max_retries": 0, "temperature": 0.2,
                         "checkpoint_enabled": True, "max_debate_rounds": 2, "max_risk_discuss_rounds": 4}.items():
        assert graph.config[key] == expected
    assert (export / "complete_report.md").is_file()
    assert (export / "keep.txt").read_text() == "keep"
    assert graph.config["results_dir"] == base["results_dir"]
    assert Path(json.loads(out.stdout)["output_dir"]) == Path(base["results_dir"]) / "0700.HK" / "2026-09-25"


@pytest.mark.parametrize("args,expected", [
    ([], "Missing argument"), (["NVDA", "--date", "2099-01-01"], "future"),
    (["NVDA", "--date", "2026-9-01"], "YYYY-MM-DD"), (["NVDA", "--date", "2026-02-30"], "YYYY-MM-DD"),
    (["NVDA", "--analysts", ""], "analysts"), (["NVDA", "--analysts", "market,"], "analysts"),
    (["NVDA", "--analysts", "invalid"], "analysts"), (["NVDA", "--analysts", "all,market"], "analysts"),
    (["NVDA", "--effort", "typo"], "Invalid value"), (["NVDA", "--risk-rounds", "0"], "Invalid value"),
    (["NVDA", "--debate-rounds", "0"], "Invalid value"), (["NVDA", "--max-tokens", "0"], "Invalid value"),
    (["NVDA", "--max-retries", "-1"], "Invalid value"), (["NVDA", "--temperature", "nan"], "finite"),
    (["NVDA", "--header", "missing-colon"], "header"), (["NVDA", "--header", "X-Test: bad\nvalue"], "control"),
    (["NVDA", "--provider", "opencode-go"], "both --quick-model and --deep-model"),
])
def test_invalid_inputs_do_not_construct_graph(setup, args, expected):
    _, graphs, runner = setup
    result = runner.invoke(main.app, ["analyze", *args])
    assert result.exit_code != 0
    assert expected in result.output
    assert graphs == []
    assert "Traceback" not in result.output


@pytest.mark.parametrize("symbol", ["", "..", "../../etc", "AAPL,MSFT", "A" * 33])
def test_bad_symbols(setup, symbol):
    _, graphs, runner = setup
    assert runner.invoke(main.app, ["analyze", symbol]).exit_code != 0
    assert not graphs


def test_reruns_append_native_logs_and_do_not_leak_between_tickers(setup):
    base, _, runner = setup
    root = Path(base["results_dir"])
    assert runner.invoke(main.app, ["analyze", "GOOG"]).exit_code == 0
    log = root / "GOOG" / "2026-09-27" / "message_tool.log"
    first = log.read_text()
    assert runner.invoke(main.app, ["analyze", "MSFT"]).exit_code == 0
    assert log.read_text() == first
    assert runner.invoke(main.app, ["analyze", "GOOG"]).exit_code == 0
    assert log.read_text().count("Selected ticker: GOOG") == 2
    assert "MSFT" not in log.read_text()
    assert not (root / "runs").exists()
    assert "add_message" not in vars(native.message_buffer)


@pytest.mark.parametrize("failure", [RuntimeError("failed later"), KeyboardInterrupt()])
def test_partial_reports_exist_before_failure_and_lifecycle_is_clean(setup, monkeypatch, failure):
    base, graphs, _ = setup
    real_create = h._create_graph
    observed = []

    def create(*args):
        graph = real_create(*args)
        graph.failure = failure

        def probe(graph, state):
            path = Path(base["results_dir"]) / "NVDA" / "2026-09-27"
            assert (path / "reports" / "market_report.md").read_text() == state["market_report"]
            assert "[Tool Call]" in (path / "message_tool.log").read_text()
            observed.append(True)
        graph.probe = probe
        return graph

    monkeypatch.setattr(h, "_create_graph", create)
    with pytest.raises(type(failure)):
        h.run_headless_analysis("NVDA", config=h.build_headless_config(base), progress_mode="off")
    assert observed
    assert [x[0] for x in graphs[0].calls] == ["create", "begin", "stream", "end"]
    assert "add_message" not in vars(native.message_buffer)
    summary = json.loads((Path(base["results_dir"]) / "NVDA" / "2026-09-27" / "run.json").read_text())
    assert summary["status"] in {"failed", "interrupted"}
    assert summary["report"] is None


def test_resume_passes_none_and_keeps_memory_and_cache_paths(setup, monkeypatch):
    base, graphs, runner = setup
    create_original = h._create_graph

    def create(*args):
        graph = create_original(*args)
        graph.resume = True
        return graph
    monkeypatch.setattr(h, "_create_graph", create)
    out = runner.invoke(main.app, ["analyze", "NVDA", "--checkpoint", "--json"])
    assert out.exit_code == 0, out.output
    stream = next(call for call in graphs[0].calls if call[0] == "stream")
    assert stream[1] is None
    assert stream[2]["config"]["configurable"]["thread_id"] == "checkpoint-thread"
    assert graphs[0].config["memory_log_path"] == base["memory_log_path"]
    assert graphs[0].config["data_cache_dir"] == base["data_cache_dir"]
    assert "Resuming the saved run" in Path(json.loads(out.stdout)["log_file"]).read_text()


def test_prompted_and_headless_share_incremental_report_contents(setup, monkeypatch, tmp_path):
    base, _, runner = setup
    headless = runner.invoke(main.app, ["analyze", "NVDA", "--no-progress"])
    assert headless.exit_code == 0, headless.output
    prompted = {**base, "results_dir": str(tmp_path / "prompted")}
    answers = iter(["Y", str(tmp_path / "prompted-export"), "N"])
    monkeypatch.setattr(native.typer, "prompt", lambda *a, **k: next(answers))
    result = native.run_analysis(config=prompted,
        selections={"ticker": "NVDA", "analysis_date": "2026-09-27", "asset_type": "stock",
                    "analysts": list(AnalystType)}, progress_mode="off", graph_factory=RecordingGraph)
    original = Path(base["results_dir"]) / "NVDA" / "2026-09-27" / "reports"
    other = result.directory / "reports"
    assert {p.name: p.read_text() for p in original.glob("*.md")} == {p.name: p.read_text() for p in other.glob("*.md")}
    assert result.report == tmp_path / "prompted-export" / "complete_report.md"


def test_json_summary_and_optional_report_display_use_separate_streams(setup):
    _, _, runner = setup
    result = runner.invoke(main.app, ["analyze", "NVDA", "--json", "--show-report", "--header", "X-Secret: never-print-me"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["decision"] == "Hold"
    assert "Complete Analysis Report" in result.stderr
    assert "never-print-me" not in result.output


def test_export_failure_does_not_return_an_old_success_summary(setup, monkeypatch):
    base, _, runner = setup
    assert runner.invoke(main.app, ["analyze", "NVDA"]).exit_code == 0

    def fail(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(native, "write_report_tree", fail)
    result = runner.invoke(main.app, ["analyze", "NVDA", "--json"])
    assert result.exit_code == 1
    assert result.stdout == ""
    summary = json.loads((Path(base["results_dir"]) / "NVDA" / "2026-09-27" / "run.json").read_text())
    assert summary["status"] == "failed" and summary["report"] is None


def test_results_root_override_and_existing_runs_left_untouched(setup, tmp_path):
    base, _, runner = setup
    legacy = Path(base["results_dir"]) / "runs" / "old"
    legacy.mkdir(parents=True)
    (legacy / "keep.md").write_text("previous run")
    root = tmp_path / "new-root"
    out = runner.invoke(main.app, ["analyze", "NVDA", "--results-dir", str(root), "--json"])
    assert out.exit_code == 0, out.output
    assert Path(json.loads(out.stdout)["output_dir"]) == root / "NVDA" / "2026-09-27"
    assert (legacy / "keep.md").read_text() == "previous run"


def test_crypto_and_portfolio_inputs_are_preserved(setup, tmp_path):
    _, graphs, runner = setup
    book = tmp_path / "portfolio.json"
    book.write_text('{"cash":1000,"currency":"CAD","positions":[]}')
    result = runner.invoke(main.app, ["analyze", "BTCUSDT", "--portfolio", str(book)])
    assert result.exit_code == 0, result.output
    assert graphs[0].selected == ["market", "social", "news"]
    call = graphs[0].calls[0]
    assert call[1] == "BTC-USD" and call[3] == "crypto"
    assert call[4].cash == 1000
    assert runner.invoke(main.app, ["analyze", "BTC-USD", "--analysts", "fundamentals"]).exit_code == 1


def test_headers_provider_safety_and_numeric_env_settings(setup):
    base, _, _ = setup
    base.update(llm_headers='{"X-Keep":"yes","X-Replace":"old"}', max_tokens="8192", llm_max_retries="0", temperature="0.2")
    result = h.build_headless_config(base, headers=["x-replace: first", "X-REPLACE: last"])
    assert result["llm_headers"] == {"X-Keep": "yes", "X-REPLACE": "last"}
    assert result["max_tokens"] == 8192 and result["llm_max_retries"] == 0 and result["temperature"] == 0.2
    other = h.build_headless_config(base, llm_provider="opencode-go", quick_think_llm="glm-5.3-flash", deep_think_llm="kimi-k3")
    assert other["llm_headers"] is None and other["backend_url"] is None
    assert base["llm_headers"].startswith("{")


@pytest.mark.parametrize("change", [{"max_tokens": True}, {"max_tokens": 1.2}, {"llm_max_retries": -1}, {"temperature": "inf"}])
def test_invalid_numeric_settings(setup, change):
    with pytest.raises(ValueError):
        h.build_headless_config({**setup[0], **change})


def test_interactive_config_does_not_erase_environment_reasoning(setup, monkeypatch):
    base, _, _ = setup
    base["openai_reasoning_effort"] = "medium"
    monkeypatch.setattr(native, "DEFAULT_CONFIG", base)
    selections = {"research_depth": 3, "quick_think_llm": "gpt-4.1-mini", "deep_think_llm": "gpt-4.1",
                  "backend_url": None, "llm_provider": "opencode-go", "openai_reasoning_effort": None}
    assert native._build_run_config(selections, None)["openai_reasoning_effort"] == "medium"


def test_no_complete_export_still_writes_native_sections(setup):
    base, _, runner = setup
    out = runner.invoke(main.app, ["analyze", "NVDA", "--json", "--no-save-report"])
    assert out.exit_code == 0, out.output
    summary = json.loads(out.stdout)
    assert summary["status"] == "completed" and summary["report"] is None
    assert (Path(summary["output_dir"]) / "reports" / "market_report.md").exists()
    assert not (Path(base["results_dir"]) / "reports").exists()


def test_clear_checkpoints_is_explicit_and_uses_native_cache(setup, monkeypatch):
    from tradingagents.graph import checkpointer

    base, _, runner = setup
    cleared = []
    monkeypatch.setattr(checkpointer, "clear_all_checkpoints", lambda path: cleared.append(path) or 2)
    out = runner.invoke(main.app, ["analyze", "NVDA", "--clear-checkpoints", "--json"])
    assert out.exit_code == 0, out.output
    assert cleared == [base["data_cache_dir"]]
    assert "Cleared 2 checkpoint(s)" in out.stderr
    assert json.loads(out.stdout)["decision"] == "Hold"
    cleared.clear()
    assert runner.invoke(main.app, ["analyze", "NVDA", "--json"]).exit_code == 0
    assert not cleared


def test_empty_stream_retains_checkpoint_and_fails(setup, monkeypatch):
    _, graphs, runner = setup
    original = h._create_graph

    def create(*args):
        graph = original(*args)
        graph.stream = lambda *a, **kw: iter(())
        return graph
    monkeypatch.setattr(h, "_create_graph", create)
    out = runner.invoke(main.app, ["analyze", "NVDA", "--json", "--checkpoint"])
    assert out.exit_code == 1
    assert "produced no state" in out.stderr
    assert not out.stdout
    assert ("end",) in graphs[0].calls
    assert ("clear",) not in graphs[0].calls


def test_explicit_checkpoint_before_analyze_is_rejected(setup):
    _, graphs, runner = setup
    out = runner.invoke(main.app, ["--clear-checkpoints", "analyze", "NVDA"])
    assert out.exit_code == 2
    assert not graphs
