"""The fork's CLI preserves report choices and metadata after the upstream merge."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from cli import main
from tradingagents.reporting import report_settings

pytestmark = pytest.mark.unit

STATE = {
    "trade_date": "2026-01-09",
    "market_report": "## Outlook\nGrounded analysis.",
    "final_trade_decision": "**Rating**: Hold\n**Price Target**: 120",
}


def _config(tmp_path):
    return {
        "reports_dir": str(tmp_path / "reports"),
        "llm_provider": "openai",
        "deep_think_provider": "anthropic",
        "deep_think_llm": "claude-opus-5-5",
        "quick_think_llm": "gpt-6-luna",
        "data_vendors": {"core_stock_apis": "yfinance"},
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
    }


@pytest.mark.parametrize("html", [False, True])
def test_cli_writer_records_run_settings_and_honors_html(tmp_path, html):
    settings = report_settings(_config(tmp_path), ["market"])

    report = main.save_report_to_disk(STATE, "NVDA", tmp_path, settings=settings, html=html)

    markdown = report.read_text()
    assert "deep anthropic claude-opus-5-5" in markdown
    assert "quick openai gpt-6-luna" in markdown
    assert "core_stock_apis yfinance" in markdown
    assert "#### Outlook" in markdown
    page = tmp_path / "complete_report.html"
    assert page.exists() is html
    if html:
        content = page.read_text()
        assert "claude-opus-5-5" in content and "gpt-6-luna" in content
        assert "<h4>Outlook</h4>" in content


@pytest.mark.parametrize("args, expected", [
    (["analyze"], None),
    (["analyze", "--no-html"], False),
    (["--no-html", "analyze"], False),
    (["--no-html", "analyze", "--html"], True),
])
def test_analyze_accepts_html_choice_from_either_option_location(monkeypatch, args, expected):
    seen = {}
    monkeypatch.setattr(main, "run_analysis", lambda **kwargs: seen.update(kwargs))

    result = CliRunner().invoke(main.app, args)

    assert result.exit_code == 0, result.output
    assert seen["post_html"] is expected


@pytest.mark.parametrize("prefix, suffix, expected", [
    ([], [], True),
    ([], ["--no-html"], False),
    (["--no-html"], [], False),
    (["--no-html"], ["--html"], True),
])
def test_headless_run_forwards_html_and_provider_settings(monkeypatch, prefix, suffix, expected):
    seen = {}
    monkeypatch.setattr(main, "run_analysis", lambda **kwargs: seen.update(kwargs))
    monkeypatch.setitem(main.DEFAULT_CONFIG, "anthropic_effort", "high")
    args = [*prefix, "run", "--ticker", "NVDA", "--date", "2026-01-09",
            "--provider", "openai", "--deep-model", "claude-opus-5-5",
            "--quick-model", "gpt-6-luna", *suffix]

    result = CliRunner().invoke(main.app, args)

    assert result.exit_code == 0, result.output
    assert seen["post_html"] is expected
    assert seen["selections"]["anthropic_effort"] == "high"


def test_html_only_flag_keeps_the_forks_interactive_flow(monkeypatch):
    from cli import run

    class MenuReached(Exception):
        pass

    def stop_at_menu():
        raise MenuReached

    monkeypatch.setattr(main, "get_user_selections", stop_at_menu)
    monkeypatch.setattr(run, "run_analysis", lambda **kwargs: pytest.fail("changed CLI flow"))

    with pytest.raises(MenuReached):
        main.run_analysis(flags={"html": False})


@pytest.mark.parametrize("html", [False, True])
def test_batch_reports_keep_settings_and_html_choice(tmp_path, html):
    config = _config(tmp_path)
    run = SimpleNamespace(trade_date=STATE["trade_date"], report_path=None)
    runner = SimpleNamespace(
        manifest=SimpleNamespace(config=config, selected_analysts=["market"], runs={"NVDA": run}),
        completed_states=lambda: {"NVDA": STATE},
        save=lambda: None,
    )

    reports = main._save_batch_reports(runner, html=html)

    assert len(reports) == 1
    report = reports[0]
    assert Path(run.report_path) == report
    assert "deep anthropic claude-opus-5-5" in report.read_text()
    assert report.with_suffix(".html").exists() is html
    assert main._save_batch_reports(runner, html=html) == []


@pytest.mark.parametrize("prefix, suffix, expected", [
    ([], [], True),
    ([], ["--no-html"], False),
    (["--no-html"], [], False),
    (["--no-html"], ["--html"], True),
])
def test_batch_collect_honors_html_choice(monkeypatch, prefix, suffix, expected):
    runner = SimpleNamespace(collect=lambda: None, status_summary=lambda: {})
    monkeypatch.setattr(main.BatchRunner, "load", lambda **kwargs: runner)
    seen = []
    monkeypatch.setattr(main, "_save_batch_reports", lambda runner, html: seen.append(html) or [])

    result = CliRunner().invoke(main.app, [*prefix, "batch", "collect", "saved-run", *suffix])

    assert result.exit_code == 0, result.output
    assert seen == [expected]


def test_batch_rejects_a_foreign_tier_before_keys_or_requests(monkeypatch):
    monkeypatch.setitem(main.DEFAULT_CONFIG, "deep_think_provider", "anthropic")
    monkeypatch.setattr(main, "ensure_api_key", lambda provider: pytest.fail("asked for a key"))

    result = CliRunner().invoke(main.app, ["batch", "submit", "--tickers", "NVDA", "--provider", "openai"])

    assert result.exit_code == 2, result.output
    assert "both model tiers" in result.output
    assert "synchronous" in result.output


@pytest.mark.parametrize("tier", ["quick", "deep"])
@pytest.mark.parametrize("command", ["submit", "batch-wait"])
def test_batch_rejects_custom_tier_endpoints_before_credentials_without_exposing_the_url(
    monkeypatch, tier, command,
):
    endpoint = "https://fixture-user:fixture-password@proxy.example.invalid/v1?key=fixture-key"
    monkeypatch.setitem(main.DEFAULT_CONFIG, f"{tier}_think_backend_url", endpoint)
    monkeypatch.setattr(main, "ensure_api_key", lambda provider: pytest.fail("asked for a key"))
    monkeypatch.setattr(main.BatchRunner, "create", lambda **kw: pytest.fail("created batch state"))
    if command == "submit":
        args = ["batch", "submit", "--tickers", "NVDA", "--provider", "openai"]
    else:
        args = ["run", "--ticker", "NVDA", "--date", "2026-01-09", "--provider", "openai",
                "--quick-model", "gpt-6-luna", "--deep-model", "gpt-6-sol", "--execution", "batch-wait"]

    result = CliRunner().invoke(main.app, args)

    assert result.exit_code == 2, result.output
    assert f"custom {tier} tier endpoint" in result.output
    assert "synchronous" in result.output
    assert "https://" not in result.output
    assert "fixture-" not in result.output


@pytest.mark.parametrize("provider, native_endpoint", [
    ("openai", "https://api.openai.com/v1"),
    ("anthropic", "https://api.anthropic.com"),
])
def test_batch_config_accepts_native_tier_endpoints(monkeypatch, provider, native_endpoint):
    monkeypatch.setitem(main.DEFAULT_CONFIG, "quick_think_backend_url", native_endpoint)
    monkeypatch.setitem(main.DEFAULT_CONFIG, "deep_think_backend_url", native_endpoint + "/")

    config = main._batch_config(
        provider=provider, deep_model=None, quick_model=None, depth=1,
        language="English", openai_reasoning_effort=None, anthropic_effort=None,
    )

    assert config["quick_think_backend_url"] == native_endpoint
    assert config["deep_think_backend_url"] == native_endpoint + "/"
