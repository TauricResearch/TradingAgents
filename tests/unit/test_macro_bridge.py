"""Tests for the macro bridge module — JSON parsing, filtering, and report rendering."""

import json
import tempfile
from pathlib import Path

import pytest


EXAMPLE_MACRO_JSON = {
    "timeframe": "1 month",
    "region": "Global",
    "executive_summary": "Test summary",
    "macro_context": {
        "economic_cycle": "Late expansion",
        "central_bank_stance": "Fed on hold",
        "geopolitical_risks": ["US-China tensions"],
        "key_indicators": [
            {"name": "10Y UST", "status": "4.45%", "signal": "neutral"}
        ],
    },
    "key_themes": [
        {
            "theme": "AI infrastructure",
            "description": "Hyperscaler capex elevated",
            "conviction": "high",
            "timeframe": "3-6 months",
            "supporting_factors": ["NVDA revenue"],
        }
    ],
    "sector_opportunities": [],
    "stocks_to_investigate": [
        {
            "ticker": "NVDA",
            "name": "NVIDIA Corporation",
            "sector": "Technology — Semiconductors",
            "rationale": "AI accelerator dominance",
            "thesis_angle": "growth",
            "conviction": "high",
            "key_catalysts": ["Blackwell ramp"],
            "risks": ["export controls"],
        },
        {
            "ticker": "LMT",
            "name": "Lockheed Martin",
            "sector": "Defense",
            "rationale": "F-35 backlog",
            "thesis_angle": "catalyst",
            "conviction": "medium",
            "key_catalysts": ["NATO orders"],
            "risks": ["budget risk"],
        },
        {
            "ticker": "XYZ",
            "name": "Low Conv Corp",
            "sector": "Other",
            "rationale": "Speculative",
            "thesis_angle": "momentum",
            "conviction": "low",
            "key_catalysts": [],
            "risks": [],
        },
    ],
    "risk_factors": ["Higher for longer"],
}


@pytest.fixture
def macro_json_file(tmp_path):
    path = tmp_path / "macro_output.json"
    path.write_text(json.dumps(EXAMPLE_MACRO_JSON))
    return path


class TestParseMacroOutput:

    def test_parses_context_and_candidates(self, macro_json_file):
        from tradingagents.pipeline.macro_bridge import parse_macro_output

        ctx, candidates = parse_macro_output(macro_json_file)
        assert ctx.economic_cycle == "Late expansion"
        assert ctx.executive_summary == "Test summary"
        assert len(candidates) == 3
        assert candidates[0].ticker == "NVDA"
        assert candidates[0].conviction == "high"

    def test_missing_fields_default_gracefully(self, tmp_path):
        from tradingagents.pipeline.macro_bridge import parse_macro_output

        minimal = {"stocks_to_investigate": [{"ticker": "TEST"}]}
        path = tmp_path / "minimal.json"
        path.write_text(json.dumps(minimal))
        ctx, candidates = parse_macro_output(path)
        assert len(candidates) == 1
        assert candidates[0].ticker == "TEST"
        assert candidates[0].conviction == "medium"  # default


class TestFilterCandidates:

    def test_filter_high_conviction(self, macro_json_file):
        from tradingagents.pipeline.macro_bridge import (
            parse_macro_output,
            filter_candidates,
        )

        _, candidates = parse_macro_output(macro_json_file)
        filtered = filter_candidates(candidates, "high", None)
        assert len(filtered) == 1
        assert filtered[0].ticker == "NVDA"

    def test_filter_medium_conviction(self, macro_json_file):
        from tradingagents.pipeline.macro_bridge import (
            parse_macro_output,
            filter_candidates,
        )

        _, candidates = parse_macro_output(macro_json_file)
        filtered = filter_candidates(candidates, "medium", None)
        assert len(filtered) == 2
        tickers = {c.ticker for c in filtered}
        assert tickers == {"NVDA", "LMT"}

    def test_filter_by_ticker(self, macro_json_file):
        from tradingagents.pipeline.macro_bridge import (
            parse_macro_output,
            filter_candidates,
        )

        _, candidates = parse_macro_output(macro_json_file)
        filtered = filter_candidates(candidates, "low", ["LMT"])
        assert len(filtered) == 1
        assert filtered[0].ticker == "LMT"

    def test_sorted_by_conviction_desc(self, macro_json_file):
        from tradingagents.pipeline.macro_bridge import (
            parse_macro_output,
            filter_candidates,
        )

        _, candidates = parse_macro_output(macro_json_file)
        filtered = filter_candidates(candidates, "low", None)
        assert filtered[0].conviction == "high"
        assert filtered[-1].conviction == "low"


class TestReportRendering:

    def test_render_ticker_report(self, macro_json_file):
        from tradingagents.pipeline.macro_bridge import (
            parse_macro_output,
            TickerResult,
            render_ticker_report,
        )

        ctx, candidates = parse_macro_output(macro_json_file)
        result = TickerResult(
            ticker="NVDA",
            candidate=candidates[0],
            macro_context=ctx,
            analysis_date="2026-03-17",
            final_trade_decision="BUY",
        )
        report = render_ticker_report(result)
        assert "NVDA" in report
        assert "NVIDIA" in report
        assert "BUY" in report
        assert "Macro" in report

    def test_render_combined_summary(self, macro_json_file):
        from tradingagents.pipeline.macro_bridge import (
            parse_macro_output,
            TickerResult,
            render_combined_summary,
        )

        ctx, candidates = parse_macro_output(macro_json_file)
        results = [
            TickerResult(
                ticker=c.ticker,
                candidate=c,
                macro_context=ctx,
                analysis_date="2026-03-17",
                final_trade_decision="HOLD",
            )
            for c in candidates[:2]
        ]
        summary = render_combined_summary(results, ctx)
        assert "NVDA" in summary
        assert "LMT" in summary
        assert "Summary" in summary

    def test_save_results(self, macro_json_file, tmp_path):
        from tradingagents.pipeline.macro_bridge import (
            parse_macro_output,
            TickerResult,
            save_results,
        )

        ctx, candidates = parse_macro_output(macro_json_file)
        results = [
            TickerResult(
                ticker="NVDA",
                candidate=candidates[0],
                macro_context=ctx,
                analysis_date="2026-03-17",
                final_trade_decision="BUY",
            )
        ]
        output_dir = tmp_path / "output"
        save_results(results, ctx, output_dir)
        assert (output_dir / "summary.md").exists()
        assert (output_dir / "results.json").exists()
        assert (output_dir / "NVDA" / "2026-03-17_deep_dive.md").exists()


class TestCandidatesFromHoldings:
    """Tests for candidates_from_holdings — portfolio holdings → StockCandidate."""

    def _make_holding(self, ticker, sector=None, industry=None):
        """Minimal holding-like object with .ticker, .sector, .industry."""
        from types import SimpleNamespace
        return SimpleNamespace(ticker=ticker, sector=sector, industry=industry)

    def test_basic_conversion(self):
        from tradingagents.pipeline.macro_bridge import candidates_from_holdings

        holdings = [self._make_holding("AAPL", sector="Technology")]
        result = candidates_from_holdings(holdings)
        assert len(result) == 1
        assert result[0].ticker == "AAPL"
        assert result[0].thesis_angle == "portfolio_holding"
        assert result[0].conviction == "medium"
        assert result[0].sector == "Technology"

    def test_skips_existing_tickers(self):
        from tradingagents.pipeline.macro_bridge import candidates_from_holdings

        holdings = [
            self._make_holding("AAPL"),
            self._make_holding("TSLA"),
        ]
        result = candidates_from_holdings(holdings, existing_tickers={"AAPL"})
        assert len(result) == 1
        assert result[0].ticker == "TSLA"

    def test_case_insensitive_dedup(self):
        from tradingagents.pipeline.macro_bridge import candidates_from_holdings

        holdings = [self._make_holding("aapl")]
        result = candidates_from_holdings(holdings, existing_tickers={"AAPL"})
        assert len(result) == 0

    def test_empty_holdings(self):
        from tradingagents.pipeline.macro_bridge import candidates_from_holdings

        result = candidates_from_holdings([])
        assert result == []

    def test_deduplicates_within_holdings(self):
        from tradingagents.pipeline.macro_bridge import candidates_from_holdings

        holdings = [
            self._make_holding("AAPL"),
            self._make_holding("AAPL"),
        ]
        result = candidates_from_holdings(holdings)
        assert len(result) == 1

    def test_missing_sector_defaults_to_empty(self):
        from tradingagents.pipeline.macro_bridge import candidates_from_holdings

        holdings = [self._make_holding("TSLA")]
        result = candidates_from_holdings(holdings)
        assert result[0].sector == ""