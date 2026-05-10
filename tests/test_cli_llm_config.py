import datetime

import cli.main
import pytest
from pathlib import Path
from cli.models import AnalystType
from cli.llm_config import LLMConfigOverrides, ResolvedLLMConfig, resolve_llm_config
from typer.testing import CliRunner

from cli.main import app


def test_cli_loads_dotenv_from_user_cwd():
    with open("cli/main.py", encoding="utf-8") as f:
        source = f.read()

    assert "from dotenv import find_dotenv, load_dotenv" in source
    assert "load_dotenv(find_dotenv(usecwd=True))" in source
    assert 'load_dotenv(find_dotenv(".env.enterprise", usecwd=True), override=False)' in source


LLM_CONFIG_ENV_VARS = (
    "TRADINGAGENTS_LLM_PROVIDER",
    "TRADINGAGENTS_QUICK_MODEL",
    "TRADINGAGENTS_DEEP_MODEL",
    "TRADINGAGENTS_BACKEND_URL",
    "TRADINGAGENTS_OPENAI_REASONING_EFFORT",
    "TRADINGAGENTS_GOOGLE_THINKING_LEVEL",
    "TRADINGAGENTS_ANTHROPIC_EFFORT",
)


def clear_llm_config_env(monkeypatch):
    for env_var in LLM_CONFIG_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)


def test_env_resolves_openai_compatible_custom_model(monkeypatch):
    clear_llm_config_env(monkeypatch)
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    monkeypatch.setenv("TRADINGAGENTS_BACKEND_URL", "https://api.inceptionlabs.ai/v1")
    monkeypatch.setenv("TRADINGAGENTS_QUICK_MODEL", "mercury")
    monkeypatch.setenv("TRADINGAGENTS_DEEP_MODEL", "mercury")

    resolved = resolve_llm_config(LLMConfigOverrides())

    assert resolved.provider == "openai"
    assert resolved.backend_url == "https://api.inceptionlabs.ai/v1"
    assert resolved.quick_model == "mercury"
    assert resolved.deep_model == "mercury"
    assert resolved.is_complete is True


def test_cli_overrides_env(monkeypatch):
    clear_llm_config_env(monkeypatch)
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("TRADINGAGENTS_QUICK_MODEL", "claude-3-5-haiku-latest")
    monkeypatch.setenv("TRADINGAGENTS_DEEP_MODEL", "claude-3-7-sonnet-latest")
    monkeypatch.setenv("TRADINGAGENTS_BACKEND_URL", "https://api.anthropic.com")

    resolved = resolve_llm_config(
        LLMConfigOverrides(
            provider="openai",
            quick_model="gpt-5.4-mini",
            deep_model="gpt-5.4",
            backend_url="https://api.openai.com/v1",
        )
    )

    assert resolved.provider == "openai"
    assert resolved.quick_model == "gpt-5.4-mini"
    assert resolved.deep_model == "gpt-5.4"
    assert resolved.backend_url == "https://api.openai.com/v1"


def test_cli_provider_override_does_not_inherit_env_backend_url(monkeypatch):
    clear_llm_config_env(monkeypatch)
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    monkeypatch.setenv("TRADINGAGENTS_BACKEND_URL", "https://api.inceptionlabs.ai/v1")

    resolved = resolve_llm_config(LLMConfigOverrides(provider="google"))

    assert resolved.provider == "google"
    assert resolved.backend_url is None


def test_partial_config_is_not_complete(monkeypatch):
    clear_llm_config_env(monkeypatch)
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    monkeypatch.setenv("TRADINGAGENTS_QUICK_MODEL", "mercury")

    resolved = resolve_llm_config(LLMConfigOverrides())

    assert resolved.provider == "openai"
    assert resolved.quick_model == "mercury"
    assert resolved.deep_model is None
    assert resolved.is_complete is False


def test_analyze_accepts_llm_config_options(monkeypatch):
    runner = CliRunner()
    captured = {}

    def fake_run_analysis(*, checkpoint, llm_overrides, selection_overrides):
        captured["checkpoint"] = checkpoint
        captured["llm_overrides"] = llm_overrides
        captured["selection_overrides"] = selection_overrides

    monkeypatch.setattr("cli.main.run_analysis", fake_run_analysis)

    result = runner.invoke(
        app,
        [
            "--llm-provider",
            "openai",
            "--quick-model",
            "mercury",
            "--deep-model",
            "mercury",
            "--backend-url",
            "https://api.inceptionlabs.ai/v1",
        ],
    )

    assert result.exit_code == 0
    assert captured["llm_overrides"].provider == "openai"
    assert captured["llm_overrides"].quick_model == "mercury"
    assert captured["llm_overrides"].deep_model == "mercury"
    assert captured["llm_overrides"].backend_url == "https://api.inceptionlabs.ai/v1"


def test_analyze_accepts_all_prompt_input_options(monkeypatch):
    runner = CliRunner()
    captured = {}

    def fake_run_analysis(*, checkpoint, llm_overrides, selection_overrides):
        captured["checkpoint"] = checkpoint
        captured["llm_overrides"] = llm_overrides
        captured["selection_overrides"] = selection_overrides

    monkeypatch.setattr("cli.main.run_analysis", fake_run_analysis)

    result = runner.invoke(
        app,
        [
            "--ticker",
            "SPY",
            "--analysis-date",
            "2026-05-01",
            "--output-language",
            "English",
            "--analysts",
            "market,news",
            "--research-depth",
            "3",
            "--save-report",
            "--save-path",
            "reports/spy",
            "--no-display-report",
            "--llm-provider",
            "openai",
            "--quick-model",
            "mercury",
            "--deep-model",
            "mercury",
            "--backend-url",
            "https://api.inceptionlabs.ai/v1",
        ],
    )

    assert result.exit_code == 0
    assert captured["selection_overrides"].ticker == "SPY"
    assert captured["selection_overrides"].analysis_date == "2026-05-01"
    assert captured["selection_overrides"].output_language == "English"
    assert captured["selection_overrides"].analysts == [
        AnalystType.MARKET,
        AnalystType.NEWS,
    ]
    assert captured["selection_overrides"].research_depth == 3
    assert captured["selection_overrides"].save_report is True
    assert captured["selection_overrides"].save_path == Path("reports/spy")
    assert captured["selection_overrides"].display_report is False


def test_analyze_accepts_today_as_analysis_date(monkeypatch):
    runner = CliRunner()
    captured = {}

    def fake_run_analysis(*, checkpoint, llm_overrides, selection_overrides):
        captured["selection_overrides"] = selection_overrides

    monkeypatch.setattr("cli.main.run_analysis", fake_run_analysis)

    result = runner.invoke(
        app,
        [
            "--analysis-date",
            "today",
            "--llm-provider",
            "openai",
            "--quick-model",
            "mercury",
            "--deep-model",
            "mercury",
        ],
    )

    assert result.exit_code == 0
    assert captured["selection_overrides"].analysis_date == datetime.datetime.now().strftime(
        "%Y-%m-%d"
    )


def test_analyze_accepts_all_analysts_alias(monkeypatch):
    runner = CliRunner()
    captured = {}

    def fake_run_analysis(*, checkpoint, llm_overrides, selection_overrides):
        captured["selection_overrides"] = selection_overrides

    monkeypatch.setattr("cli.main.run_analysis", fake_run_analysis)

    result = runner.invoke(
        app,
        [
            "--analysts",
            "all",
            "--llm-provider",
            "openai",
            "--quick-model",
            "mercury",
            "--deep-model",
            "mercury",
        ],
    )

    assert result.exit_code == 0
    assert captured["selection_overrides"].analysts == [
        AnalystType.MARKET,
        AnalystType.SOCIAL,
        AnalystType.NEWS,
        AnalystType.FUNDAMENTALS,
    ]


def test_get_user_selections_skips_llm_prompts_when_config_complete(monkeypatch):
    monkeypatch.setattr("cli.main.fetch_announcements", lambda: [])
    monkeypatch.setattr("cli.main.display_announcements", lambda console, announcements: None)
    monkeypatch.setattr("cli.main.get_ticker", lambda: "SPY")
    monkeypatch.setattr("cli.main.get_analysis_date", lambda: "2026-05-01")
    monkeypatch.setattr("cli.main.ask_output_language", lambda: "English")
    monkeypatch.setattr("cli.main.select_analysts", lambda: [])
    monkeypatch.setattr("cli.main.select_research_depth", lambda: 1)
    monkeypatch.setattr("cli.main.ask_openai_reasoning_effort", lambda: None)

    monkeypatch.setattr(
        "cli.main.select_llm_provider",
        lambda: pytest.fail("provider prompt should be skipped"),
    )
    monkeypatch.setattr(
        "cli.main.select_shallow_thinking_agent",
        lambda provider: pytest.fail("quick model prompt should be skipped"),
    )
    monkeypatch.setattr(
        "cli.main.select_deep_thinking_agent",
        lambda provider: pytest.fail("deep model prompt should be skipped"),
    )

    selections = cli.main.get_user_selections(
        ResolvedLLMConfig(
            provider="openai",
            quick_model="mercury",
            deep_model="mercury",
            backend_url="https://api.inceptionlabs.ai/v1",
            openai_reasoning_effort=None,
            google_thinking_level=None,
            anthropic_effort=None,
        )
    )

    assert selections["llm_provider"] == "openai"
    assert selections["shallow_thinker"] == "mercury"
    assert selections["deep_thinker"] == "mercury"
    assert selections["backend_url"] == "https://api.inceptionlabs.ai/v1"


def test_custom_openai_base_url_skips_reasoning_effort_prompt(monkeypatch):
    monkeypatch.setattr("cli.main.fetch_announcements", lambda: [])
    monkeypatch.setattr("cli.main.display_announcements", lambda console, announcements: None)
    monkeypatch.setattr("cli.main.get_ticker", lambda: "SPY")
    monkeypatch.setattr("cli.main.get_analysis_date", lambda: "2026-05-01")
    monkeypatch.setattr("cli.main.ask_output_language", lambda: "English")
    monkeypatch.setattr("cli.main.select_analysts", lambda: [])
    monkeypatch.setattr("cli.main.select_research_depth", lambda: 1)
    monkeypatch.setattr(
        "cli.main.ask_openai_reasoning_effort",
        lambda: pytest.fail("reasoning effort prompt should be skipped for custom base URLs"),
    )

    selections = cli.main.get_user_selections(
        ResolvedLLMConfig(
            provider="openai",
            quick_model="mercury",
            deep_model="mercury",
            backend_url="https://api.inceptionlabs.ai/v1",
            openai_reasoning_effort=None,
            google_thinking_level=None,
            anthropic_effort=None,
        )
    )

    assert selections["openai_reasoning_effort"] is None


def test_get_user_selections_skips_all_pre_run_prompts_when_complete(monkeypatch):
    monkeypatch.setattr(
        "cli.main.fetch_announcements",
        lambda: pytest.fail("announcements should be skipped"),
    )
    monkeypatch.setattr(
        "cli.main.get_ticker",
        lambda: pytest.fail("ticker prompt should be skipped"),
    )
    monkeypatch.setattr(
        "cli.main.get_analysis_date",
        lambda: pytest.fail("date prompt should be skipped"),
    )
    monkeypatch.setattr(
        "cli.main.ask_output_language",
        lambda: pytest.fail("language prompt should be skipped"),
    )
    monkeypatch.setattr(
        "cli.main.select_analysts",
        lambda: pytest.fail("analysts prompt should be skipped"),
    )
    monkeypatch.setattr(
        "cli.main.select_research_depth",
        lambda: pytest.fail("research depth prompt should be skipped"),
    )
    monkeypatch.setattr(
        "cli.main.select_llm_provider",
        lambda: pytest.fail("provider prompt should be skipped"),
    )
    monkeypatch.setattr(
        "cli.main.select_shallow_thinking_agent",
        lambda provider: pytest.fail("quick model prompt should be skipped"),
    )
    monkeypatch.setattr(
        "cli.main.select_deep_thinking_agent",
        lambda provider: pytest.fail("deep model prompt should be skipped"),
    )

    selections = cli.main.get_user_selections(
        ResolvedLLMConfig(
            provider="openai",
            quick_model="mercury",
            deep_model="mercury",
            backend_url="https://api.inceptionlabs.ai/v1",
            openai_reasoning_effort=None,
            google_thinking_level=None,
            anthropic_effort=None,
        ),
        cli.main.SelectionOverrides(
            ticker="SPY",
            analysis_date="2026-05-01",
            output_language="English",
            analysts=[AnalystType.MARKET, AnalystType.NEWS],
            research_depth=3,
        ),
    )

    assert selections["ticker"] == "SPY"
    assert selections["analysis_date"] == "2026-05-01"
    assert selections["output_language"] == "English"
    assert selections["analysts"] == [AnalystType.MARKET, AnalystType.NEWS]
    assert selections["research_depth"] == 3
    assert selections["llm_provider"] == "openai"


def test_save_report_to_disk_writes_complete_markdown_and_html(tmp_path):
    final_state = {
        "market_report": "market **details**",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
    }

    report_path = cli.main.save_report_to_disk(final_state, "SPY", tmp_path)

    html_path = tmp_path / "complete_report.html"
    assert report_path == tmp_path / "complete_report.md"
    assert report_path.exists()
    assert html_path.exists()

    markdown = report_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")

    assert "# Trading Analysis Report: SPY" in markdown
    assert "<h1>Trading Analysis Report: SPY</h1>" in html
    assert "<strong>details</strong>" in html


def test_save_report_to_disk_includes_llm_metadata_in_markdown_and_html(tmp_path):
    final_state = {
        "market_report": "market",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
    }

    report_path = cli.main.save_report_to_disk(
        final_state,
        "SPY",
        tmp_path,
        report_metadata={
            "LLM Provider": "openai",
            "Quick Model": "mercury",
            "Deep Model": "mercury-pro",
            "Backend URL": "https://api.inceptionlabs.ai/v1",
        },
    )

    markdown = report_path.read_text(encoding="utf-8")
    html = (tmp_path / "complete_report.html").read_text(encoding="utf-8")

    assert "**LLM Provider**: openai" in markdown
    assert "**Quick Model**: mercury" in markdown
    assert "**Deep Model**: mercury-pro" in markdown
    assert "**Backend URL**: https://api.inceptionlabs.ai/v1" in markdown
    assert "<strong>LLM Provider</strong>: openai" in html
    assert "<strong>Deep Model</strong>: mercury-pro" in html


def test_save_report_to_disk_writes_complete_pdf(tmp_path):
    final_state = {
        "market_report": "market **details**",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
    }

    cli.main.save_report_to_disk(
        final_state,
        "SPY",
        tmp_path,
        report_metadata={"LLM Provider": "openai"},
    )

    pdf_path = tmp_path / "complete_report.pdf"
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_save_report_to_disk_embeds_technical_charts(monkeypatch, tmp_path):
    final_state = {
        "company_of_interest": "SPY",
        "trade_date": "2026-05-01",
        "market_report": "market",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
    }

    def fake_generate_report_charts(symbol, trade_date, save_path):
        chart_path = save_path / "charts" / "technical-analysis.png"
        chart_path.parent.mkdir()
        chart_path.write_bytes(b"png")
        return [
            cli.main.ChartArtifact(
                title="SPY Technical Analysis",
                path=chart_path,
                description="Price, volume, MACD, Bollinger Bands, and RSI.",
            )
        ]

    monkeypatch.setattr(cli.main, "generate_report_charts", fake_generate_report_charts)

    report_path = cli.main.save_report_to_disk(final_state, "SPY", tmp_path)

    markdown = report_path.read_text(encoding="utf-8")
    html = (tmp_path / "complete_report.html").read_text(encoding="utf-8")
    assert "## Technical Charts" in markdown
    assert (
        "[![SPY Technical Analysis](charts/technical-analysis.png)]"
        "(charts/technical-analysis.png)"
    ) in markdown
    assert (
        '<a href="charts/technical-analysis.png">'
        '<img src="charts/technical-analysis.png" alt="SPY Technical Analysis"'
    ) in html
    assert "img {" in html
    assert "max-width: 100%;" in html
    assert "height: auto;" in html


def test_save_report_to_disk_passes_charts_and_metadata_to_pdf_writer(monkeypatch, tmp_path):
    final_state = {
        "company_of_interest": "SPY",
        "trade_date": "2026-05-01",
        "market_report": "market",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
    }
    captured = {}

    def fake_generate_report_charts(symbol, trade_date, save_path):
        chart_path = save_path / "charts" / "technical-analysis.png"
        return [
            cli.main.ChartArtifact(
                title="SPY Technical Analysis",
                path=chart_path,
                description="Price, volume, MACD, Bollinger Bands, and RSI.",
            )
        ]

    def fake_write_pdf_report(markdown_text, pdf_path, *, title, report_metadata, chart_artifacts):
        captured["markdown_text"] = markdown_text
        captured["pdf_path"] = pdf_path
        captured["title"] = title
        captured["report_metadata"] = report_metadata
        captured["chart_artifacts"] = chart_artifacts
        pdf_path.write_bytes(b"%PDF fake")
        return pdf_path

    monkeypatch.setattr(cli.main, "generate_report_charts", fake_generate_report_charts)
    monkeypatch.setattr(cli.main, "write_pdf_report", fake_write_pdf_report)

    cli.main.save_report_to_disk(
        final_state,
        "SPY",
        tmp_path,
        report_metadata={"LLM Provider": "openai", "Deep Model": "gpt-5.4"},
    )

    assert captured["pdf_path"] == tmp_path / "complete_report.pdf"
    assert captured["title"] == "Trading Analysis Report: SPY"
    assert captured["report_metadata"] == {"LLM Provider": "openai", "Deep Model": "gpt-5.4"}
    assert [artifact.title for artifact in captured["chart_artifacts"]] == ["SPY Technical Analysis"]
    assert "## Technical Charts" in captured["markdown_text"]


def test_save_report_flag_uses_default_path_without_prompt(monkeypatch, tmp_path):
    final_state = {
        "final_trade_decision": "BUY",
        "market_report": "market",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
    }
    saved = {}

    monkeypatch.setattr(
        "cli.main.get_user_selections",
        lambda resolved_llm, selection_overrides: {
            "ticker": "SPY",
            "analysis_date": "2026-05-01",
            "analysts": [AnalystType.MARKET],
            "research_depth": 1,
            "shallow_thinker": "mercury",
            "deep_thinker": "mercury",
            "backend_url": "https://api.inceptionlabs.ai/v1",
            "llm_provider": "openai",
            "google_thinking_level": None,
            "openai_reasoning_effort": None,
            "anthropic_effort": None,
            "output_language": "English",
        },
    )
    monkeypatch.setattr("cli.main.TradingAgentsGraph", _fake_graph(final_state))
    monkeypatch.setattr("cli.main.StatsCallbackHandler", lambda: object())
    monkeypatch.setattr("cli.main.Live", _passthrough_live)
    monkeypatch.setattr("cli.main.update_display", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "cli.main.save_report_to_disk",
        lambda state, ticker, save_path, report_metadata=None: (
            saved.setdefault("metadata", report_metadata)
            and saved.setdefault("path", save_path)
        )
        or saved.setdefault("path", save_path)
        or save_path / "complete_report.md",
    )
    monkeypatch.setattr(
        "cli.main.typer.prompt",
        lambda *args, **kwargs: pytest.fail("save path prompt should be skipped"),
    )
    monkeypatch.setattr("cli.main.display_complete_report", lambda state: None)
    monkeypatch.setitem(cli.main.DEFAULT_CONFIG, "results_dir", str(tmp_path / "logs"))
    monkeypatch.setitem(cli.main.DEFAULT_CONFIG, "data_cache_dir", str(tmp_path / "cache"))
    monkeypatch.setitem(cli.main.DEFAULT_CONFIG, "memory_log_path", str(tmp_path / "memory.md"))
    monkeypatch.chdir(tmp_path)

    cli.main.run_analysis(
        llm_overrides=LLMConfigOverrides(
            provider="openai",
            quick_model="mercury",
            deep_model="mercury",
            backend_url="https://api.inceptionlabs.ai/v1",
        ),
        selection_overrides=cli.main.SelectionOverrides(
            ticker="SPY",
            analysis_date="2026-05-01",
            output_language="English",
            analysts=[AnalystType.MARKET],
            research_depth=1,
            save_report=True,
            display_report=False,
        ),
    )

    assert saved["path"].parent == tmp_path / "reports"
    assert saved["path"].name.startswith("SPY_")
    assert saved["metadata"] == {
        "LLM Provider": "openai",
        "Quick Model": "mercury",
        "Deep Model": "mercury",
        "Backend URL": "https://api.inceptionlabs.ai/v1",
    }


def _fake_graph(final_state):
    class FakePropagator:
        def create_initial_state(self, ticker, analysis_date):
            return {"ticker": ticker, "analysis_date": analysis_date}

        def get_graph_args(self, callbacks=None):
            return {}

    class FakeCompiledGraph:
        def stream(self, init_agent_state, **args):
            yield final_state

    class FakeGraph:
        def __init__(self, *args, **kwargs):
            self.propagator = FakePropagator()
            self.graph = FakeCompiledGraph()

        def process_signal(self, signal):
            return signal

    return FakeGraph


class _passthrough_live:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False
