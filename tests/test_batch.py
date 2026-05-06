import json
import inspect
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from cli.main import app
from cli.models import AnalystType
from tradingagents.batch import (
    BatchTickerResult,
    PortfolioHolding,
    build_batch_summary_markdown,
    load_batch_inputs,
    parse_ticker_list,
    run_batch_analysis,
    write_batch_outputs,
)
from tradingagents.allocation import build_allocation_plan


def test_load_batch_inputs_accepts_holdings_csv(tmp_path):
    csv_path = tmp_path / "portfolio.csv"
    csv_path.write_text(
        "ticker,quantity,average_cost,market_value,target_weight,notes\n"
        " aapl ,10,150,2000,0.4,core holding\n"
        "msft,,,3000,0.6,\n",
        encoding="utf-8",
    )

    holdings = load_batch_inputs(input_path=csv_path, tickers=None)

    assert holdings == [
        PortfolioHolding(
            ticker="AAPL",
            quantity=10.0,
            average_cost=150.0,
            market_value=2000.0,
            target_weight=0.4,
            notes="core holding",
        ),
        PortfolioHolding(ticker="MSFT", market_value=3000.0, target_weight=0.6),
    ]


def test_load_batch_inputs_accepts_json_list(tmp_path):
    json_path = tmp_path / "portfolio.json"
    json_path.write_text(
        json.dumps([
            {"ticker": "nvda", "quantity": 2, "average_cost": 900},
            {"ticker": "brk.b", "market_value": 500},
        ]),
        encoding="utf-8",
    )

    holdings = load_batch_inputs(input_path=json_path, tickers=None)

    assert holdings[0].ticker == "NVDA"
    assert holdings[0].market_value == 1800.0
    assert holdings[1].ticker == "BRK.B"
    assert holdings[1].market_value == 500.0


def test_load_batch_inputs_requires_ticker_column(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("symbol,market_value\nAAPL,100\n", encoding="utf-8")

    try:
        load_batch_inputs(input_path=csv_path, tickers=None)
    except ValueError as exc:
        assert "ticker" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_parse_ticker_list_normalizes_and_rejects_unsafe_values():
    assert parse_ticker_list(" spy,cnc.to,^gspc ") == [
        PortfolioHolding(ticker="SPY"),
        PortfolioHolding(ticker="CNC.TO"),
        PortfolioHolding(ticker="^GSPC"),
    ]

    try:
        parse_ticker_list("AAPL,../MSFT")
    except ValueError as exc:
        assert "Invalid ticker" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_batch_summary_ranks_ratings_and_includes_holdings():
    results = [
        BatchTickerResult(
            ticker="MSFT",
            status="success",
            rating="Hold",
            trader_action="Hold",
            executive_summary="Balanced setup.",
            report_path=Path("MSFT/complete_report.md"),
            holding=PortfolioHolding(ticker="MSFT", market_value=3000, target_weight=0.6),
        ),
        BatchTickerResult(
            ticker="AAPL",
            status="success",
            rating="Buy",
            trader_action="Buy",
            executive_summary="Constructive setup.",
            report_path=Path("AAPL/complete_report.md"),
            holding=PortfolioHolding(ticker="AAPL", market_value=2000, target_weight=0.4),
        ),
        BatchTickerResult(
            ticker="TSLA",
            status="failed",
            error="provider timeout",
            holding=PortfolioHolding(ticker="TSLA"),
        ),
    ]

    markdown = build_batch_summary_markdown(results, "2026-05-05")

    assert markdown.index("| AAPL | success | Buy |") < markdown.index("| MSFT | success | Hold |")
    assert "| Total Provided Market Value | 5000.00 |" in markdown
    assert "| AAPL | 2000.00 | 40.00% | 40.00% | 0.00% |" in markdown
    assert "| TSLA | provider timeout |" in markdown


def test_write_batch_outputs_writes_markdown_html_and_json(tmp_path):
    results = [
        BatchTickerResult(
            ticker="AAPL",
            status="success",
            rating="Buy",
            trader_action="Buy",
            executive_summary="Constructive setup.",
            report_path=tmp_path / "AAPL" / "complete_report.md",
            holding=PortfolioHolding(ticker="AAPL", market_value=1000),
        )
    ]

    write_batch_outputs(tmp_path, results, "2026-05-05", narrative="Narrative summary.")

    assert (tmp_path / "batch_summary.md").exists()
    assert (tmp_path / "batch_summary.html").exists()
    assert (tmp_path / "batch_results.json").exists()
    assert "Narrative summary." in (tmp_path / "batch_summary.md").read_text(encoding="utf-8")
    data = json.loads((tmp_path / "batch_results.json").read_text(encoding="utf-8"))
    assert data[0]["ticker"] == "AAPL"
    assert data[0]["rating"] == "Buy"


def test_write_batch_outputs_writes_allocation_report_files(tmp_path):
    results = [
        BatchTickerResult(
            ticker="AAPL",
            status="success",
            rating="Buy",
            trader_action="Buy",
            holding=PortfolioHolding(ticker="AAPL", quantity=0, market_value=0),
        )
    ]
    allocation_plan = build_allocation_plan(
        results,
        available_cash=250,
        prices={"AAPL": 90},
    )

    write_batch_outputs(
        tmp_path,
        results,
        "2026-05-05",
        allocation_plan=allocation_plan,
    )

    assert (tmp_path / "allocation_plan.md").exists()
    assert (tmp_path / "allocation_plan.html").exists()
    assert (tmp_path / "allocation_plan.json").exists()
    assert "## Portfolio Allocation Plan" in (tmp_path / "allocation_plan.md").read_text(encoding="utf-8")
    data = json.loads((tmp_path / "allocation_plan.json").read_text(encoding="utf-8"))
    assert data["rows"][0]["ticker"] == "AAPL"
    assert data["leftover_cash"] == 70


def test_run_batch_analysis_allocation_options_are_backward_compatible():
    signature = inspect.signature(run_batch_analysis)

    assert signature.parameters["available_cash"].default == 0.0
    assert signature.parameters["allocate"].default is False
    assert signature.parameters["dry_run"].default is False
    assert signature.parameters["allocation_policy"].default is None


def test_run_batch_analysis_preserves_explicit_empty_prices(monkeypatch, tmp_path):
    captured = {}

    def fake_run_analysis(*, checkpoint, llm_overrides, selection_overrides):
        return SimpleNamespace(
            final_state={
                "final_trade_decision": "**Rating**: Buy\n\n**Executive Summary**: Buy setup.",
                "trader_investment_plan": "FINAL TRANSACTION PROPOSAL: BUY",
            },
            report_path=tmp_path / "AAPL" / "complete_report.md",
        )

    def fake_build_allocation_plan(results, *, available_cash, prices, policy=None):
        captured["prices"] = prices
        return None

    monkeypatch.setattr("cli.main.run_analysis", fake_run_analysis)
    monkeypatch.setattr("tradingagents.batch.build_llm_narrative", lambda results, llm_overrides: None)
    monkeypatch.setattr("tradingagents.allocation.build_allocation_plan", fake_build_allocation_plan)

    run_batch_analysis(
        holdings=[PortfolioHolding(ticker="AAPL", quantity=10, market_value=1000)],
        analysis_date="2026-05-05",
        output_language="English",
        analysts=[AnalystType.MARKET],
        research_depth=1,
        checkpoint=False,
        llm_overrides=None,
        save_path=tmp_path / "batch",
        display_report=False,
        continue_on_error=True,
        available_cash=0,
        allocate=True,
        dry_run=False,
        allocation_policy=None,
        prices={},
    )

    assert captured["prices"] == {}


def test_run_batch_analysis_excludes_failed_results_from_allocation(monkeypatch, tmp_path):
    captured = {}

    def fake_run_analysis(*, checkpoint, llm_overrides, selection_overrides):
        if selection_overrides.ticker == "TSLA":
            raise RuntimeError("provider timeout")
        return SimpleNamespace(
            final_state={
                "final_trade_decision": "**Rating**: Buy\n\n**Executive Summary**: Buy setup.",
                "trader_investment_plan": "FINAL TRANSACTION PROPOSAL: BUY",
            },
            report_path=tmp_path / selection_overrides.ticker / "complete_report.md",
        )

    def fake_build_allocation_plan(results, *, available_cash, prices, policy=None):
        captured["tickers"] = [result.ticker for result in results]
        return None

    monkeypatch.setattr("cli.main.run_analysis", fake_run_analysis)
    monkeypatch.setattr("tradingagents.batch.build_llm_narrative", lambda results, llm_overrides: None)
    monkeypatch.setattr("tradingagents.allocation.build_allocation_plan", fake_build_allocation_plan)

    run_batch_analysis(
        holdings=[
            PortfolioHolding(ticker="AAPL", quantity=10, market_value=1000),
            PortfolioHolding(ticker="TSLA", quantity=5, market_value=500),
        ],
        analysis_date="2026-05-05",
        output_language="English",
        analysts=[AnalystType.MARKET],
        research_depth=1,
        checkpoint=False,
        llm_overrides=None,
        save_path=tmp_path / "batch",
        display_report=False,
        continue_on_error=True,
        available_cash=0,
        allocate=True,
        dry_run=False,
        allocation_policy=None,
    )

    assert captured["tickers"] == ["AAPL"]


def test_run_batch_analysis_skips_allocation_when_all_results_fail(monkeypatch, tmp_path):
    builder_called = False

    def fake_run_analysis(*, checkpoint, llm_overrides, selection_overrides):
        raise RuntimeError("provider timeout")

    def fake_build_allocation_plan(results, *, available_cash, prices, policy=None):
        nonlocal builder_called
        builder_called = True
        return None

    monkeypatch.setattr("cli.main.run_analysis", fake_run_analysis)
    monkeypatch.setattr("tradingagents.batch.build_llm_narrative", lambda results, llm_overrides: None)
    monkeypatch.setattr("tradingagents.allocation.build_allocation_plan", fake_build_allocation_plan)

    run_batch_analysis(
        holdings=[PortfolioHolding(ticker="TSLA", quantity=5, market_value=500)],
        analysis_date="2026-05-05",
        output_language="English",
        analysts=[AnalystType.MARKET],
        research_depth=1,
        checkpoint=False,
        llm_overrides=None,
        save_path=tmp_path / "batch",
        display_report=False,
        continue_on_error=True,
        available_cash=0,
        allocate=True,
        dry_run=False,
        allocation_policy=None,
    )

    assert builder_called is False
    assert not (tmp_path / "batch" / "allocation_plan.md").exists()


def test_write_batch_outputs_uses_relative_report_links_in_markdown(tmp_path):
    report_path = tmp_path / "AAPL" / "complete_report.md"
    report_path.parent.mkdir()
    report_path.write_text("# AAPL", encoding="utf-8")
    results = [
        BatchTickerResult(
            ticker="AAPL",
            status="success",
            rating="Buy",
            trader_action="Buy",
            report_path=report_path,
            holding=PortfolioHolding(ticker="AAPL"),
        )
    ]

    write_batch_outputs(tmp_path, results, "2026-05-05")

    markdown = (tmp_path / "batch_summary.md").read_text(encoding="utf-8")
    assert "[report](AAPL/complete_report.md)" in markdown
    assert str(tmp_path) not in markdown


def test_batch_cli_rejects_input_and_tickers_together(tmp_path):
    runner = CliRunner()
    input_path = tmp_path / "portfolio.csv"
    input_path.write_text("ticker\nAAPL\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "batch",
            "--input",
            str(input_path),
            "--tickers",
            "AAPL,MSFT",
            "--analysis-date",
            "2026-05-05",
        ],
    )

    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_batch_cli_dispatches_config(monkeypatch, tmp_path):
    runner = CliRunner()
    captured = {}

    def fake_run_batch_analysis(
        *,
        holdings,
        analysis_date,
        output_language,
        analysts,
        research_depth,
        checkpoint,
        llm_overrides,
        save_path,
        display_report,
        continue_on_error,
        **kwargs,
    ):
        captured.update(locals())
        return []

    monkeypatch.setattr("cli.main.run_batch_analysis", fake_run_batch_analysis)

    result = runner.invoke(
        app,
        [
            "batch",
            "--tickers",
            "aapl,msft",
            "--analysis-date",
            "2026-05-05",
            "--output-language",
            "English",
            "--analysts",
            "market,news",
            "--research-depth",
            "1",
            "--llm-provider",
            "openai",
            "--quick-model",
            "mercury",
            "--deep-model",
            "mercury",
            "--save-path",
            str(tmp_path / "batch"),
            "--no-display-report",
            "--fail-fast",
        ],
    )

    assert result.exit_code == 0
    assert [holding.ticker for holding in captured["holdings"]] == ["AAPL", "MSFT"]
    assert captured["analysis_date"] == "2026-05-05"
    assert captured["analysts"] == [AnalystType.MARKET, AnalystType.NEWS]
    assert captured["continue_on_error"] is False


def test_batch_cli_dispatches_allocation_and_dry_run_options(monkeypatch, tmp_path):
    runner = CliRunner()
    captured = {}

    def fake_run_batch_analysis(
        *,
        holdings,
        analysis_date,
        output_language,
        analysts,
        research_depth,
        checkpoint,
        llm_overrides,
        save_path,
        display_report,
        continue_on_error,
        available_cash,
        allocate,
        dry_run,
        allocation_policy,
        prices=None,
    ):
        captured.update(locals())
        return []

    monkeypatch.setattr("cli.main.run_batch_analysis", fake_run_batch_analysis)

    result = runner.invoke(
        app,
        [
            "batch",
            "--tickers",
            "AAPL,MSFT",
            "--cash",
            "1000",
            "--allocate",
            "--dry-run",
            "--analysis-date",
            "2026-05-05",
            "--save-path",
            str(tmp_path / "batch"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["available_cash"] == 1000
    assert captured["allocate"] is True
    assert captured["dry_run"] is True
    assert captured["prices"] is None


def test_batch_cli_rejects_negative_cash():
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "batch",
            "--tickers",
            "AAPL",
            "--cash",
            "-1",
        ],
    )

    assert result.exit_code != 0
    assert "cash must be non-negative" in result.output


def test_batch_cli_dry_run_implies_allocation(monkeypatch, tmp_path):
    runner = CliRunner()
    captured = {}

    def fake_run_batch_analysis(
        *,
        holdings,
        analysis_date,
        output_language,
        analysts,
        research_depth,
        checkpoint,
        llm_overrides,
        save_path,
        display_report,
        continue_on_error,
        available_cash,
        allocate,
        dry_run,
        allocation_policy,
        prices=None,
    ):
        captured.update(locals())
        return []

    monkeypatch.setattr("cli.main.run_batch_analysis", fake_run_batch_analysis)

    result = runner.invoke(
        app,
        [
            "batch",
            "--tickers",
            "AAPL",
            "--cash",
            "1000",
            "--dry-run",
            "--analysis-date",
            "2026-05-05",
            "--save-path",
            str(tmp_path / "batch"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["allocate"] is True
    assert captured["dry_run"] is True
