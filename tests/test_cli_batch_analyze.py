from pathlib import Path
from unittest import mock

import pytest

import cli.main as m


@pytest.mark.unit
def test_parse_batch_depth_labels_and_integer():
    assert m._parse_batch_depth("shallow") == 1
    assert m._parse_batch_depth("medium") == 3
    assert m._parse_batch_depth("deep") == 5
    assert m._parse_batch_depth("2") == 2


@pytest.mark.unit
@pytest.mark.parametrize("value", ["", "zero", "0", "-1"])
def test_parse_batch_depth_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        m._parse_batch_depth(value)


@pytest.mark.unit
def test_parse_batch_analysts_all_and_subset():
    assert m._parse_batch_analysts("all") == ["market", "social", "news", "fundamentals"]
    assert m._parse_batch_analysts("news,market") == ["market", "news"]


@pytest.mark.unit
def test_parse_batch_analysts_rejects_unknown():
    with pytest.raises(ValueError, match="unknown analyst"):
        m._parse_batch_analysts("market,charts")


@pytest.mark.unit
def test_parse_batch_tickers_from_cli_and_file(tmp_path):
    tickers_file = tmp_path / "tickers.txt"
    tickers_file.write_text("msft\nnvda, 0700.hk\n", encoding="utf-8")

    assert m._parse_batch_tickers(" aapl, spy ", tickers_file) == [
        "AAPL",
        "SPY",
        "MSFT",
        "NVDA",
        "0700.HK",
    ]


@pytest.mark.unit
def test_parse_batch_tickers_requires_source():
    with pytest.raises(ValueError, match="provide --tickers"):
        m._parse_batch_tickers(None, None)


@pytest.mark.unit
def test_build_batch_selections_model_sets_quick_and_deep():
    patched = dict(
        m.DEFAULT_CONFIG,
        llm_provider="openai",
        backend_url=None,
        quick_think_llm="default-quick",
        deep_think_llm="default-deep",
    )
    with mock.patch.object(m, "DEFAULT_CONFIG", patched):
        selections = m._build_batch_selections(
            provider="openrouter",
            model="deepseek/deepseek-v4-flash",
            quick_model=None,
            deep_model=None,
            depth="shallow",
        )

    assert selections["llm_provider"] == "openrouter"
    assert selections["backend_url"] == "https://openrouter.ai/api/v1"
    assert selections["shallow_thinker"] == "deepseek/deepseek-v4-flash"
    assert selections["deep_thinker"] == "deepseek/deepseek-v4-flash"
    assert selections["research_depth"] == 1


@pytest.mark.unit
def test_build_batch_selections_quick_and_deep_override_model():
    patched = dict(
        m.DEFAULT_CONFIG,
        llm_provider="openai",
        backend_url=None,
        quick_think_llm="default-quick",
        deep_think_llm="default-deep",
    )
    with mock.patch.object(m, "DEFAULT_CONFIG", patched):
        selections = m._build_batch_selections(
            provider="openrouter",
            model="shared",
            quick_model="quick-only",
            deep_model="deep-only",
            depth="2",
        )

    assert selections["shallow_thinker"] == "quick-only"
    assert selections["deep_thinker"] == "deep-only"
    assert selections["research_depth"] == 2


@pytest.mark.unit
def test_build_batch_selections_env_models_win(monkeypatch):
    patched = dict(
        m.DEFAULT_CONFIG,
        llm_provider="openai",
        backend_url=None,
        quick_think_llm="env-quick",
        deep_think_llm="env-deep",
    )
    monkeypatch.setenv("TRADINGAGENTS_QUICK_THINK_LLM", "env-quick")
    monkeypatch.setenv("TRADINGAGENTS_DEEP_THINK_LLM", "env-deep")

    with mock.patch.object(m, "DEFAULT_CONFIG", patched):
        selections = m._build_batch_selections(
            provider="openrouter",
            model="shared",
            quick_model="quick-only",
            deep_model="deep-only",
            depth="shallow",
        )

    assert selections["shallow_thinker"] == "env-quick"
    assert selections["deep_thinker"] == "env-deep"


@pytest.mark.unit
def test_run_batch_analysis_continues_after_failure(monkeypatch, tmp_path):
    calls = []
    saved_reports = []

    class FakeGraph:
        def __init__(self, selected_analysts, config, debug):
            self.selected_analysts = selected_analysts
            self.config = config
            self.debug = debug

        def propagate(self, ticker, analysis_date, asset_type="stock"):
            calls.append((ticker, analysis_date, asset_type, self.selected_analysts, self.config))
            if ticker == "FAIL":
                raise RuntimeError("boom")
            return {"final_trade_decision": f"decision {ticker}"}, f"Signal-{ticker}"

        def save_reports(self, final_state, ticker, save_path=None):
            save_path = Path(save_path)
            save_path.mkdir(parents=True, exist_ok=True)
            report = save_path / "complete_report.md"
            report.write_text(final_state["final_trade_decision"], encoding="utf-8")
            saved_reports.append((ticker, report))
            return report

    monkeypatch.setattr(m, "TradingAgentsGraph", FakeGraph)

    rows = m._run_batch_analysis(
        tickers=["AAPL", "FAIL", "MSFT"],
        analysis_date="2026-05-29",
        analyst_keys=["market", "news"],
        config={"results_dir": str(tmp_path), "llm_provider": "openrouter"},
        batch_dir=tmp_path / "batch",
    )

    assert [call[0] for call in calls] == ["AAPL", "FAIL", "MSFT"]
    assert [row["status"] for row in rows] == ["success", "failed", "success"]
    assert rows[0]["signal"] == "Signal-AAPL"
    assert rows[1]["error"] == "boom"
    assert rows[2]["signal"] == "Signal-MSFT"
    assert [ticker for ticker, _ in saved_reports] == ["AAPL", "MSFT"]
    assert (tmp_path / "batch" / "summary.csv").exists()
    assert (tmp_path / "batch" / "summary.md").exists()
