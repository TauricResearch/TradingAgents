"""CLI/TUI parity at the input boundary and shared runner; no external calls."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

import cli.headless as headless
import cli.main as main
import cli.run as native
import cli.selections as selections_module
from cli.models import AnalystType
from tests.native_cli_helpers import RecordingGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.factory import build_llm_kwargs


@pytest.fixture
def parity_setup(tmp_path, monkeypatch):
    # DEFAULT_CONFIG is an import-time overlay. Isolate both its values and the
    # env-presence checks so a developer's actual .env cannot affect this suite.
    import os

    for name in tuple(os.environ):
        if name.startswith("TRADINGAGENTS_"):
            monkeypatch.delenv(name)
    config = deepcopy(DEFAULT_CONFIG)
    config.update(
        results_dir=str(tmp_path / "logs"),
        data_cache_dir=str(tmp_path / "cache"),
        memory_log_path=str(tmp_path / "memory.md"),
        llm_provider="openai",
        quick_think_llm="quick-from-config",
        deep_think_llm="deep-from-config",
        backend_url=None,
        llm_headers=None,
        output_language="Chinese",
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        google_thinking_level=None,
        openai_reasoning_effort=None,
        anthropic_effort=None,
        temperature=None,
        max_tokens=None,
        llm_max_retries=None,
        checkpoint_enabled=False,
    )
    for module in (main, native, selections_module):
        monkeypatch.setattr(module, "DEFAULT_CONFIG", config)
    for module in (headless, native):
        monkeypatch.setattr(module, "get_current_date", lambda: "2026-09-27")
    graphs = []

    def factory(analysts, settings, callbacks=None):
        graph = RecordingGraph(analysts, settings, callbacks)
        graphs.append(graph)
        return graph

    monkeypatch.setattr(headless, "_create_graph", factory)
    monkeypatch.setattr(native, "_default_graph_factory", factory)
    return config, graphs, CliRunner()


def _chosen(**overrides):
    return {
        "ticker": "NVDA",
        "analysis_date": "2026-09-27",
        "asset_type": "stock",
        "analysts": list(AnalystType),
        "research_depth": 3,
        "llm_provider": "openai",
        "quick_think_llm": "quick-from-config",
        "deep_think_llm": "deep-from-config",
        "backend_url": None,
        "output_language": "Chinese",
        "google_thinking_level": None,
        "openai_reasoning_effort": None,
        "anthropic_effort": None,
        **overrides,
    }


@pytest.mark.parametrize("provider,key,flag,value", [
    ("openai", "openai_reasoning_effort", "--openai-reasoning-effort", "high"),
    ("google", "google_thinking_level", "--google-thinking-level", "minimal"),
    ("anthropic", "anthropic_effort", "--anthropic-effort", "max"),
])
def test_headless_exposes_tui_reasoning_controls(parity_setup, provider, key, flag, value):
    config, graphs, runner = parity_setup
    config.update(llm_provider=provider)
    config[key] = "low"
    result = runner.invoke(main.app, ["analyze", "NVDA", flag, value, "--json"])
    assert result.exit_code == 0, result.output
    assert graphs[0].config[key] == value
    expected = native._build_run_config(_chosen(llm_provider=provider, **{key: value}), None)
    assert build_llm_kwargs(graphs[0].config) == build_llm_kwargs(expected)
    assert json.loads(result.stdout)["status"] == "completed"


@pytest.mark.parametrize("provider,key,value", [
    ("openai", "openai_reasoning_effort", "high"),
    ("google", "google_thinking_level", "minimal"),
    ("anthropic", "anthropic_effort", "max"),
    ("opencode-go", "openai_reasoning_effort", "medium"),
])
def test_omitting_reasoning_flags_preserves_config(parity_setup, provider, key, value):
    config, graphs, runner = parity_setup
    config.update(llm_provider=provider)
    config[key] = value
    result = runner.invoke(main.app, ["analyze", "NVDA", "--json"])
    assert result.exit_code == 0, result.output
    assert graphs[0].config[key] == value


def _stub_wizard(monkeypatch, provider):
    monkeypatch.setattr(selections_module, "fetch_announcements", lambda: [])
    monkeypatch.setattr(selections_module, "display_announcements", lambda *a: None)
    monkeypatch.setattr(selections_module, "get_ticker", lambda: "NVDA")
    monkeypatch.setattr(selections_module, "get_analysis_date", lambda: "2026-09-27")
    monkeypatch.setattr(selections_module, "ask_output_language", lambda *a: "Chinese")
    monkeypatch.setattr(selections_module, "select_analysts", lambda *a: list(AnalystType))
    monkeypatch.setattr(selections_module, "select_research_depth", lambda *a: 3)
    monkeypatch.setattr(selections_module, "select_llm_provider", lambda *a: (provider, None))
    monkeypatch.setattr(selections_module, "ensure_api_key", lambda *a: None)
    monkeypatch.setattr(selections_module, "ask_anthropic_effort", lambda: "high")
    shallow = Mock(return_value="claude-quick-selected")
    deep = Mock(return_value="claude-deep-selected")
    monkeypatch.setattr(selections_module, "select_shallow_thinking_agent", shallow)
    monkeypatch.setattr(selections_module, "select_deep_thinking_agent", deep)
    return shallow, deep


@pytest.mark.parametrize("configured", ["quick", "deep"])
@pytest.mark.parametrize("provider_from_env", [False, True])
def test_tui_model_env_overrides_are_independent(parity_setup, monkeypatch, configured, provider_from_env):
    config, _, _ = parity_setup
    provider = "anthropic"
    if provider_from_env:
        config["llm_provider"] = provider
        monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", provider)
    config[f"{configured}_think_llm"] = "claude-model-from-env"
    monkeypatch.setenv(f"TRADINGAGENTS_{configured.upper()}_THINK_LLM", "claude-model-from-env")
    shallow, deep = _stub_wizard(monkeypatch, provider)
    selected = selections_module._prompt_selections({})
    assert selected[f"{configured}_think_llm"] == "claude-model-from-env"
    if configured == "quick":
        shallow.assert_not_called()
        deep.assert_called_once_with(provider, None)
        assert selected["deep_think_llm"] == "claude-deep-selected"
    else:
        deep.assert_not_called()
        shallow.assert_called_once_with(provider, None)
        assert selected["quick_think_llm"] == "claude-quick-selected"


@pytest.mark.parametrize("provider", ["anthropic", "google", "opencode-go"])
def test_provider_switch_drops_previous_provider_headers_in_both_modes(parity_setup, provider):
    config, _, _ = parity_setup
    config["llm_headers"] = {"X-Private-Gateway": "synthetic-test-value"}
    chosen = _chosen(llm_provider=provider, quick_think_llm="selected-quick", deep_think_llm="selected-deep")
    interactive = native._build_run_config(chosen, None)
    unattended = headless.build_headless_config(
        config, llm_provider=provider, quick_think_llm="selected-quick", deep_think_llm="selected-deep"
    )
    assert interactive["llm_headers"] is None
    assert unattended["llm_headers"] is None
    assert config["llm_headers"] == {"X-Private-Gateway": "synthetic-test-value"}


def test_same_provider_keeps_configured_headers_in_both_modes(parity_setup):
    config, _, _ = parity_setup
    config["llm_headers"] = {"X-Private-Gateway": "synthetic-test-value"}
    interactive = native._build_run_config(_chosen(), None)
    unattended = headless.build_headless_config(config)
    assert interactive["llm_headers"] == unattended["llm_headers"] == config["llm_headers"]


def test_chinese_default_workflow_matches_tui_reports(parity_setup, monkeypatch, tmp_path):
    config, graphs, runner = parity_setup
    monkeypatch.setattr(native, "get_user_selections", lambda: pytest.fail("headless prompted"))
    unattended = runner.invoke(main.app, ["analyze", "nvda", "--json"])
    assert unattended.exit_code == 0, unattended.output
    summary = json.loads(unattended.stdout)
    assert graphs[0].config["output_language"] == "Chinese"
    assert graphs[0].selected == ["market", "social", "news", "fundamentals"]
    assert summary["date"] == "2026-09-27"
    assert (summary["debate_rounds"], summary["risk_rounds"]) == (3, 3)
    run_dir = Path(config["results_dir"]) / "NVDA" / "2026-09-27"
    assert Path(summary["output_dir"]) == run_dir
    expected_reports = {p.name: p.read_text(encoding="utf-8") for p in (run_dir / "reports").glob("*.md")}
    assert "中文" in expected_reports["market_report.md"]

    monkeypatch.setattr(native, "get_user_selections", lambda: _chosen())
    monkeypatch.setattr(native, "DEFAULT_CONFIG", {**config, "results_dir": str(tmp_path / "tui")})
    monkeypatch.setattr(native.typer, "prompt", lambda *a, **k: "N")
    interactive = native.run_analysis(progress_mode="off")
    actual_reports = {p.name: p.read_text(encoding="utf-8") for p in (interactive.directory / "reports").glob("*.md")}
    assert actual_reports == expected_reports
    assert graphs[1].selected == graphs[0].selected
    assert graphs[1].config["max_debate_rounds"] == graphs[0].config["max_debate_rounds"]
    assert [call[0] for call in graphs[1].calls] == [call[0] for call in graphs[0].calls]


@pytest.mark.parametrize("interactive", [False, True])
@pytest.mark.parametrize("failure", [RuntimeError("synthetic-private-error"), KeyboardInterrupt()])
def test_shared_failure_lifecycle_retains_checkpoint_and_reports(parity_setup, monkeypatch, interactive, failure):
    config, graphs, _ = parity_setup
    config["checkpoint_enabled"] = True
    factory = headless._create_graph

    def fail_after_report(*args, **kwargs):
        graph = factory(*args, **kwargs)
        graph.failure = failure
        return graph

    monkeypatch.setattr(native, "_default_graph_factory", fail_after_report)
    monkeypatch.setattr(headless, "_create_graph", fail_after_report)
    monkeypatch.setattr(native.typer, "prompt", lambda *a, **k: pytest.fail("failed run prompted"))
    with pytest.raises(type(failure)):
        if interactive:
            native.run_analysis(config=config, selections=_chosen(), progress_mode="off")
        else:
            headless.run_headless_analysis("NVDA", config=config, progress_mode="off")
    assert [call[0] for call in graphs[0].calls] == ["create", "begin", "stream", "end"]
    directory = Path(config["results_dir"]) / "NVDA" / "2026-09-27"
    assert "中文" in (directory / "reports" / "market_report.md").read_text(encoding="utf-8")
    log = (directory / "message_tool.log").read_text(encoding="utf-8")
    assert "synthetic-private-error" not in log
    assert "partial reports retained" in log
    assert not {"add_message", "add_tool_call", "update_report_section"}.intersection(vars(native.message_buffer))
    if not interactive:
        summary = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        assert summary["status"] == ("interrupted" if isinstance(failure, KeyboardInterrupt) else "failed")
        assert summary["needs_review"] is True
        assert summary["decision"] is None
        assert summary["report"] is None
        assert "synthetic-private-error" not in json.dumps(summary)


def test_invalid_input_does_not_clear_checkpoints(parity_setup, monkeypatch):
    from tradingagents.graph import checkpointer

    _, graphs, runner = parity_setup
    clear = Mock()
    monkeypatch.setattr(checkpointer, "clear_all_checkpoints", clear)
    result = runner.invoke(main.app, ["analyze", "NVDA", "--analysts", "unknown", "--clear-checkpoints"])
    assert result.exit_code == 1
    clear.assert_not_called()
    assert graphs == []


@pytest.mark.parametrize("provider,flag,key", [
    ("opencode-go", "--opencode-go-api", "opencode_go_api"),
    ("commandcode", "--commandcode-api", "commandcode_api"),
])
@pytest.mark.parametrize("api", ["auto", "chat_completions", "responses", "messages"])
def test_headless_protocol_overrides_reach_factory(parity_setup, provider, flag, key, api):
    config, graphs, runner = parity_setup
    config.update(llm_provider=provider, **{key: "messages"})
    result = runner.invoke(main.app, ["analyze", "NVDA", flag, api.upper(), "--json"])
    assert result.exit_code == 0, result.output
    assert graphs[0].config[key] == api
    assert build_llm_kwargs(graphs[0].config)["api"] == api


@pytest.mark.parametrize("provider,flag", [
    ("opencode-go", "--opencode-go-api"),
    ("commandcode", "--commandcode-api"),
])
def test_bad_protocol_is_rejected_before_graph_creation(parity_setup, provider, flag):
    config, graphs, runner = parity_setup
    config.update(llm_provider=provider)
    result = runner.invoke(main.app, ["analyze", "NVDA", flag, "typo", "--json"])
    assert result.exit_code == 2
    assert graphs == []
    assert not result.stdout.strip()


@pytest.mark.parametrize("cancelled", ["quick", "deep"])
def test_cancelling_model_selection_does_not_save_preferences(parity_setup, monkeypatch, cancelled):
    shallow, deep = _stub_wizard(monkeypatch, "anthropic")
    (shallow if cancelled == "quick" else deep).return_value = None
    saved = Mock()
    monkeypatch.setattr(selections_module, "load_last_run", lambda: {})
    monkeypatch.setattr(selections_module, "save_last_run", saved)
    with pytest.raises(main.typer.Abort):
        selections_module.get_user_selections()
    saved.assert_not_called()
    if cancelled == "quick":
        deep.assert_not_called()


@pytest.mark.parametrize("provider,key", [
    ("opencode-go", "opencode_go_api"),
    ("commandcode", "commandcode_api"),
])
def test_omitting_protocol_flag_preserves_config_in_both_modes(parity_setup, provider, key):
    config, graphs, runner = parity_setup
    config.update(llm_provider=provider, **{key: "responses"})
    result = runner.invoke(main.app, ["analyze", "NVDA", "--json"])
    assert result.exit_code == 0, result.output
    interactive = native._build_run_config(_chosen(llm_provider=provider), None)
    assert graphs[0].config[key] == interactive[key] == "responses"
    assert build_llm_kwargs(graphs[0].config)["api"] == build_llm_kwargs(interactive)["api"] == "responses"


@pytest.mark.parametrize("provider,quick,deep", [
    ("opencode-go", "gpt-6-luna", "kimi-k3"),
    ("commandcode", "gpt-6-luna", "claude-sonnet-5-5"),
])
def test_gateway_tui_routes_known_models_and_offers_relevant_effort(
    parity_setup, monkeypatch, provider, quick, deep
):
    shallow, deep_prompt = _stub_wizard(monkeypatch, provider)
    shallow.return_value = quick
    deep_prompt.return_value = deep
    effort = Mock(return_value="high")
    claude_effort = Mock(return_value="medium")
    monkeypatch.setattr(selections_module, "ask_openai_reasoning_effort", effort)
    monkeypatch.setattr(selections_module, "ask_anthropic_effort", claude_effort)
    selected = selections_module._prompt_selections({})
    key = provider.replace("-", "_") + "_api"
    assert selected[key] == "auto"
    assert selected["openai_reasoning_effort"] == "high"
    effort.assert_called_once_with()
    if provider == "commandcode":
        assert selected["anthropic_effort"] == "medium"
        claude_effort.assert_called_once_with()
    else:
        claude_effort.assert_not_called()
    config = native._build_run_config(selected, None)
    assert config[key] == "auto"
    assert build_llm_kwargs(config)["reasoning_effort"] == "high"


def test_gateway_tui_protocol_choice_reaches_run_config(parity_setup, monkeypatch):
    shallow, deep = _stub_wizard(monkeypatch, "commandcode")
    shallow.return_value = "new-quick"
    deep.return_value = "new-deep"
    choose_api = Mock(return_value="responses")
    monkeypatch.setattr(selections_module, "ask_provider_api", choose_api)
    selected = selections_module._prompt_selections({})
    choose_api.assert_called_once_with("commandcode", ["new-quick", "new-deep"], "auto")
    assert selected["commandcode_api"] == "responses"
    config = native._build_run_config(selected, None)
    assert build_llm_kwargs(config)["api"] == "responses"


@pytest.mark.parametrize("provider,cancelled", [
    ("openai", "ask_openai_reasoning_effort"),
    ("anthropic", "ask_anthropic_effort"),
    ("google", "ask_gemini_thinking_config"),
    ("commandcode", "ask_openai_reasoning_effort"),
    ("commandcode", "ask_anthropic_effort"),
])
def test_cancelling_thinking_settings_aborts_before_saving_preferences(
    parity_setup, monkeypatch, provider, cancelled
):
    shallow, deep = _stub_wizard(monkeypatch, provider)
    shallow.return_value = "gpt-6-luna"
    deep.return_value = "claude-sonnet-5-5"
    monkeypatch.setattr(selections_module, "ask_openai_reasoning_effort", lambda: "medium")
    monkeypatch.setattr(selections_module, cancelled, lambda: None)
    monkeypatch.setattr(selections_module, "load_last_run", lambda: {})
    saved = Mock()
    monkeypatch.setattr(selections_module, "save_last_run", saved)
    with pytest.raises(main.typer.Abort):
        selections_module.get_user_selections()
    saved.assert_not_called()
