"""The P0 freshness gate runs automatically in the real flow.

``record_decision`` extracts the filings known at the analysis date from
SEC EDGAR (point-in-time) and the period the fundamentals analyst used
from the run's own report, so the gate needs no explicit caller
parameters. These tests pin that wiring: a stale report blocks through
the real path, a non-US filer degrades to FUNDAMENTALS_UNAVAILABLE, and a
failure in the extraction never sinks the run.
"""

from __future__ import annotations

import json

import pytest

from tradingagents.dataflows.filing_freshness import FilingRecord
from tradingagents.graph.trading_graph import TradingAgentsGraph

Q3 = FilingRecord("2026-Q3", "2026-09-30", published_date="2026-11-07",
                  form_type="8-K")


def _read_audit(results_root, ticker, analysis_date):
    """The audit of the single run this test made.

    Audits are run-scoped since §2 of P4: the dated filename it used to have was
    overwritten by any second analysis of the same instrument that day, which is
    the defect that phase removes. Reading by glob asserts the run exists without
    pinning the behaviour that lost data.
    """
    directory = results_root / ticker / "reliability_audit"
    audits = sorted(directory.glob(f"audit_{analysis_date}_*.json"))
    assert len(audits) == 1, f"expected one run-scoped audit, got {audits}"
    return json.loads(audits[0].read_text(encoding="utf-8"))


def _graph(tmp_path):
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {
        "results_dir": str(tmp_path / "results"),
        "deep_think_llm": "glm-5.3:cloud",
        "quick_think_llm": "deepseek-v4.1-flash:cloud",
        "fundamentals_freshness_gate": True,
    }
    graph.selected_analysts = []

    class _Log:
        def __init__(self):
            self.stored = None

        def store_decision(self, **kwargs):
            self.stored = kwargs

    graph.memory_log = _Log()
    return graph


def _state(fundamentals_report="", rating="Hold"):
    return {
        "company_of_interest": "BRK-B",
        "trade_date": "2026-11-08",
        "market_report": "",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": fundamentals_report,
        "investment_debate_state": {"bull_history": "", "bear_history": "",
                                    "history": "", "current_response": ""},
        "trader_investment_plan": "",
        "risk_debate_state": {"aggressive_history": "", "conservative_history": "",
                              "neutral_history": "", "history": ""},
        "investment_plan": "",
        "final_rating": rating,
        "final_trade_decision": f"**Rating**: {rating}\nMaintain.",
        # A snapshot the engine can certify from. These tests exercise the
        # freshness gate, not the authorisation rule, so a certified metric is
        # supplied to keep the run otherwise approvable (§4: no certified
        # metric means no order, which would mask what is under test here).
        "verified_market_snapshot": {"close": 570.89, "sma200": 497.723,
                                     "previous_close": 572.33},
    }


class TestUsedPeriodExtraction:
    def test_iso_period_end_is_read_from_the_report(self):
        from tradingagents.dataflows.filing_freshness import (
            used_period_end_from_report,
        )

        report = (
            "# Balance Sheet for BRK-B (quarterly)\n"
            "Period,Total Assets\n"
            "2026-06-30,1200\n"
        )
        assert used_period_end_from_report(report) == "2026-06-30"

    def test_quarter_label_is_converted_to_its_end(self):
        from tradingagents.dataflows.filing_freshness import (
            used_period_end_from_report,
        )

        assert used_period_end_from_report("figures for 2026-Q2") == "2026-06-30"
        assert used_period_end_from_report("figures for Q3 2026") == "2026-09-30"

    def test_the_freshest_named_period_wins(self):
        from tradingagents.dataflows.filing_freshness import (
            used_period_end_from_report,
        )

        report = "Q2 2026 comparison; current figures 2026-09-30."
        assert used_period_end_from_report(report) == "2026-09-30"

    def test_an_undatable_report_returns_none(self):
        from tradingagents.dataflows.filing_freshness import (
            used_period_end_from_report,
        )

        assert used_period_end_from_report("no dates here") is None
        assert used_period_end_from_report("") is None
        assert used_period_end_from_report(None) is None


class TestAutomaticWiring:
    def test_a_stale_report_blocks_through_the_real_path(self, tmp_path, monkeypatch):
        """T01 end to end: Q2 report, Q3 filed — the audit says BLOCK."""
        graph = _graph(tmp_path)
        monkeypatch.setattr(graph, "_known_filings", lambda t, d: [Q3])
        state = _state(fundamentals_report="Period,Assets\n2026-06-30,1200\n")
        graph.record_decision("BRK-B", "2026-11-08", state)

        assert state["execution_action"] == "BLOCK"
        assert "DATA_QUALITY_BLOCKED" in state["execution_reason_codes"]
        audit = _read_audit(tmp_path / "results", "BRK-B", "2026-11-08")
        assert audit["data_quality"]["fundamentals_freshness"]["status"] == \
            "STALE_FUNDAMENTALS"

    def test_a_current_report_is_not_blocked(self, tmp_path, monkeypatch):
        graph = _graph(tmp_path)
        monkeypatch.setattr(graph, "_known_filings", lambda t, d: [Q3])
        state = _state(fundamentals_report="Period,Assets\n2026-09-30,1300\n")
        graph.record_decision("BRK-B", "2026-11-08", state)

        assert "DATA_QUALITY_BLOCKED" not in state["execution_reason_codes"]

    def test_a_non_us_filer_degrades_to_unavailable_not_a_crash(self, tmp_path, monkeypatch):
        """ENI.MI is not an SEC filer: no filings, the gate says UNAVAILABLE."""
        graph = _graph(tmp_path)
        monkeypatch.setattr(graph, "_known_filings", lambda t, d: [])
        state = _state(fundamentals_report="Period,Assets\n2026-06-30,100\n")
        graph.record_decision("ENI.MI", "2026-11-08", state)

        assert state["execution_action"] == "BLOCK"
        audit = _read_audit(tmp_path / "results", "ENI.MI", "2026-11-08")
        assert audit["data_quality"]["fundamentals_freshness"]["status"] == \
            "FUNDAMENTALS_UNAVAILABLE"

    def test_an_extraction_failure_fails_closed_not_open(self, tmp_path, monkeypatch):
        """A broken vendor must not skip the gate: no filings means
        UNAVAILABLE, which blocks — and the run itself still completes."""
        graph = _graph(tmp_path)

        def boom(ticker, as_of):
            raise RuntimeError("SEC down")

        monkeypatch.setattr(
            "tradingagents.graph.trading_graph.filings_from_sec_edgar", boom
        )

        state = _state(fundamentals_report="Period,Assets\n2026-06-30,100\n")
        graph.record_decision("BRK-B", "2026-11-08", state)  # must not raise

        assert graph.memory_log.stored["ticker"] == "BRK-B"
        assert state["execution_action"] == "BLOCK"
        audit = _read_audit(tmp_path / "results", "BRK-B", "2026-11-08")
        assert audit["data_quality"]["fundamentals_freshness"]["status"] == \
            "FUNDAMENTALS_UNAVAILABLE"

    def test_the_gate_can_be_disabled_by_config(self, tmp_path, monkeypatch):
        graph = _graph(tmp_path)
        graph.config["fundamentals_freshness_gate"] = False
        monkeypatch.setattr(
            "tradingagents.graph.trading_graph.filings_from_sec_edgar",
            lambda *a, **k: pytest.fail("must not be called when disabled"),
        )
        state = _state(fundamentals_report="Period,Assets\n2026-06-30,100\n")
        graph.record_decision("BRK-B", "2026-11-08", state)

        assert "DATA_QUALITY_BLOCKED" not in state["execution_reason_codes"]
        # Disabled means None (check not run), not an empty list (which the
        # gate would read as "no filings known" and fail closed).
        assert graph._known_filings("BRK-B", "2026-11-08") is None


class TestKnownFilings:
    def test_extraction_is_filtered_to_the_analysis_date(self, monkeypatch, tmp_path):
        """No look-ahead: a filing dated after the run date is invisible."""
        from tradingagents.dataflows.vendors import sec_edgar

        graph = _graph(tmp_path)
        monkeypatch.setattr(sec_edgar, "cik_for", lambda t: "0001067983")
        monkeypatch.setattr(sec_edgar, "_cached_json", lambda url, name: {
            "facts": {"us-gaap": {
                "Revenues": {"units": {"USD": [
                    {"end": "2026-06-30", "filed": "2026-08-07", "val": 1.0},
                    {"end": "2026-09-30", "filed": "2026-11-07", "val": 2.0},
                ]}},
            }},
        })
        filings = graph._known_filings("BRK-B", "2026-11-08")
        ends = {f.period_end for f in filings}
        assert "2026-06-30" in ends and "2026-09-30" in ends

        early = graph._known_filings("BRK-B", "2026-11-06")
        assert "2026-09-30" not in {f.period_end for f in early}
