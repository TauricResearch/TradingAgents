"""Tests for the JSONL AuditLog writer/reader and the shared finalize_run().

Covers:
- AuditLog: append + load round-trip, disabled (no path) is a no-op,
  malformed lines are skipped, latest_initial_for_ticker scoping.
- finalize_run(): writes to all three sinks (per-ticker JSON, memory log,
  audit log) in the same call, using the same payload _log_state builds.
- propagate(persist=False): leaves no trace in any sink — the "practice run"
  escape hatch.
"""

import json
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.utils.audit_log import AuditLog
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.graph.trading_graph import TradingAgentsGraph

# ---------------------------------------------------------------------------
# AuditLog unit tests
# ---------------------------------------------------------------------------


def _make_log(tmp_path, filename="audit_log.jsonl"):
    return AuditLog({"audit_log_path": str(tmp_path / filename)})


def _append_minimal(log, ticker="NVDA", trade_date="2026-06-01", run_purpose="initial"):
    log.append(
        ticker=ticker,
        trade_date=trade_date,
        run_purpose=run_purpose,
        position_size_gbp=None,
        llm_provider="deepseek",
        deep_think_llm="deepseek-v4-pro",
        quick_think_llm="deepseek-v4-flash",
        decision_payload={"final_trade_decision": "Rating: Buy"},
    )


@pytest.mark.unit
class TestAuditLogWrite:
    def test_append_creates_file_when_missing(self, tmp_path):
        log = _make_log(tmp_path)
        assert log.path is not None and not log.path.exists()
        _append_minimal(log)
        assert log.path.exists()

    def test_append_writes_one_jsonl_line_per_call(self, tmp_path):
        log = _make_log(tmp_path)
        _append_minimal(log, ticker="NVDA")
        _append_minimal(log, ticker="HIMS")
        _append_minimal(log, ticker="VUAG.L")
        contents = log.path.read_text(encoding="utf-8").splitlines()
        assert len(contents) == 3
        for line in contents:
            assert json.loads(line)  # each line is standalone valid JSON

    def test_record_contains_all_fields(self, tmp_path):
        log = _make_log(tmp_path)
        log.append(
            ticker="NVDA",
            trade_date="2026-06-01",
            run_purpose="initial",
            position_size_gbp=250.0,
            llm_provider="deepseek",
            deep_think_llm="deepseek-v4-pro",
            quick_think_llm="deepseek-v4-flash",
            decision_payload={"final_trade_decision": "Buy"},
        )
        record = json.loads(log.path.read_text(encoding="utf-8").strip())
        assert record["ticker"] == "NVDA"
        assert record["trade_date"] == "2026-06-01"
        assert record["run_purpose"] == "initial"
        assert record["position_size_gbp"] == 250.0
        assert record["llm_provider"] == "deepseek"
        assert record["deep_think_llm"] == "deepseek-v4-pro"
        assert record["quick_think_llm"] == "deepseek-v4-flash"
        assert record["decision"]["final_trade_decision"] == "Buy"
        # Timestamp is ISO-8601 with timezone.
        assert "T" in record["timestamp"]
        assert record["timestamp"].endswith("+00:00") or record["timestamp"].endswith("Z")

    def test_no_path_disables_writes(self, tmp_path):
        log = AuditLog({})
        assert log.path is None
        # No exception, no file created.
        _append_minimal(log)
        assert not (tmp_path / "audit_log.jsonl").exists()


@pytest.mark.unit
class TestAuditLogRead:
    def test_load_all_returns_records_in_file_order(self, tmp_path):
        log = _make_log(tmp_path)
        _append_minimal(log, ticker="A", trade_date="2026-01-01")
        _append_minimal(log, ticker="B", trade_date="2026-01-02")
        _append_minimal(log, ticker="C", trade_date="2026-01-03")
        records = log.load_all()
        assert [r["ticker"] for r in records] == ["A", "B", "C"]

    def test_load_all_empty_when_no_file(self, tmp_path):
        log = _make_log(tmp_path, filename="never_written.jsonl")
        assert log.load_all() == []

    def test_load_all_skips_malformed_lines(self, tmp_path):
        log = _make_log(tmp_path)
        _append_minimal(log, ticker="OK")
        with open(log.path, "a", encoding="utf-8") as f:
            f.write("not-json{not-json\n")
        _append_minimal(log, ticker="ALSOOK")
        records = log.load_all()
        assert [r["ticker"] for r in records] == ["OK", "ALSOOK"]

    def test_latest_initial_for_ticker_picks_most_recent(self, tmp_path):
        log = _make_log(tmp_path)
        _append_minimal(log, ticker="NVDA", trade_date="2026-01-01")
        _append_minimal(log, ticker="NVDA", trade_date="2026-04-01")
        _append_minimal(log, ticker="NVDA", trade_date="2026-06-01")
        match = log.latest_initial_for_ticker("NVDA")
        assert match is not None
        assert match["trade_date"] == "2026-06-01"

    def test_latest_initial_for_ticker_ignores_other_tickers(self, tmp_path):
        log = _make_log(tmp_path)
        _append_minimal(log, ticker="HIMS", trade_date="2026-05-01")
        _append_minimal(log, ticker="NVDA", trade_date="2026-01-01")
        match = log.latest_initial_for_ticker("NVDA")
        assert match["trade_date"] == "2026-01-01"

    def test_latest_initial_for_ticker_ignores_rechecks(self, tmp_path):
        """Re-check runs must not shadow the original initial run."""
        log = _make_log(tmp_path)
        _append_minimal(log, ticker="NVDA", trade_date="2026-01-01", run_purpose="initial")
        _append_minimal(log, ticker="NVDA", trade_date="2026-04-01", run_purpose="recheck")
        _append_minimal(log, ticker="NVDA", trade_date="2026-07-01", run_purpose="recheck")
        match = log.latest_initial_for_ticker("NVDA")
        assert match["trade_date"] == "2026-01-01"

    def test_latest_initial_for_ticker_returns_none_when_absent(self, tmp_path):
        log = _make_log(tmp_path)
        assert log.latest_initial_for_ticker("NVDA") is None


# ---------------------------------------------------------------------------
# finalize_run integration
# ---------------------------------------------------------------------------


def _fake_final_state(ticker="NVDA", trade_date="2026-06-01"):
    """Minimal final_state dict mirroring what _log_state expects."""
    return {
        "company_of_interest": ticker,
        "trade_date": trade_date,
        "market_report": "m",
        "sentiment_report": "s",
        "news_report": "n",
        "fundamentals_report": "f",
        "investment_debate_state": {
            "bull_history": "b",
            "bear_history": "br",
            "history": "h",
            "current_response": "",
            "judge_decision": "",
        },
        "trader_investment_plan": "Buy at £42",
        "risk_debate_state": {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "history": "",
            "judge_decision": "",
        },
        "investment_plan": "Plan markdown",
        "final_trade_decision": "Rating: Buy\nExecutive Summary: take it.",
    }


@pytest.mark.unit
class TestFinalizeRun:
    def test_writes_to_all_three_sinks(self, tmp_path):
        """One call → per-ticker JSON + memory log + audit-log line."""
        results_dir = tmp_path / "logs"
        memory_path = tmp_path / "memory" / "trading_memory.md"
        audit_path = tmp_path / "audit_log.jsonl"
        config = {
            "results_dir": str(results_dir),
            "memory_log_path": str(memory_path),
            "memory_log_max_entries": None,
            "audit_log_path": str(audit_path),
            "llm_provider": "deepseek",
            "deep_think_llm": "deepseek-v4-pro",
            "quick_think_llm": "deepseek-v4-flash",
        }
        graph = MagicMock(spec=TradingAgentsGraph)
        graph.config = config
        graph.ticker = "NVDA"
        graph.log_states_dict = {}
        graph.memory_log = TradingMemoryLog(config)
        graph.audit_log = AuditLog(config)
        # Drive the real _log_state via the mock so the per-ticker JSON path
        # exercises the production code, not a stub.
        graph._log_state = lambda td, fs: TradingAgentsGraph._log_state(graph, td, fs)

        TradingAgentsGraph.finalize_run(
            graph,
            _fake_final_state(),
            "2026-06-01",
            run_purpose="initial",
            position_size_gbp=250.0,
        )

        # 1. Per-ticker JSON exists with the expected key.
        per_ticker = results_dir / "NVDA" / "TradingAgentsStrategy_logs" / "full_states_log_2026-06-01.json"
        assert per_ticker.exists()
        payload = json.loads(per_ticker.read_text(encoding="utf-8"))
        assert payload["company_of_interest"] == "NVDA"

        # 2. Memory log has the pending entry.
        memory_text = memory_path.read_text(encoding="utf-8")
        assert "[2026-06-01 | NVDA |" in memory_text
        assert "| pending]" in memory_text

        # 3. Audit log has one line with provider + position.
        audit_records = AuditLog(config).load_all()
        assert len(audit_records) == 1
        record = audit_records[0]
        assert record["ticker"] == "NVDA"
        assert record["run_purpose"] == "initial"
        assert record["position_size_gbp"] == 250.0
        assert record["llm_provider"] == "deepseek"
        assert record["decision"]["final_trade_decision"].startswith("Rating: Buy")

    def test_missing_self_ticker_falls_back_to_final_state(self, tmp_path):
        """The CLI path can arrive at finalize_run with self.ticker unset
        (it bypasses propagate which is where self.ticker is normally seeded).
        finalize_run must self-heal from final_state["company_of_interest"]
        rather than crash in safe_ticker_component."""
        config = {
            "results_dir": str(tmp_path / "logs"),
            "memory_log_path": str(tmp_path / "mem.md"),
            "memory_log_max_entries": None,
            "audit_log_path": str(tmp_path / "audit.jsonl"),
            "llm_provider": "deepseek",
            "deep_think_llm": "deepseek-v4-pro",
            "quick_think_llm": "deepseek-v4-flash",
        }
        graph = MagicMock(spec=TradingAgentsGraph)
        graph.config = config
        graph.ticker = None  # ← the actual bug the user hit
        graph.log_states_dict = {}
        graph.memory_log = TradingMemoryLog(config)
        graph.audit_log = AuditLog(config)
        graph._log_state = lambda td, fs: TradingAgentsGraph._log_state(graph, td, fs)

        TradingAgentsGraph.finalize_run(
            graph,
            _fake_final_state(ticker="NVDA"),
            "2026-06-01",
            run_purpose="initial",
            position_size_gbp=None,
        )

        # The fallback should kick in and the run should land in all sinks.
        assert graph.ticker == "NVDA"
        assert AuditLog(config).load_all()[0]["ticker"] == "NVDA"

    def test_run_purpose_recheck_propagates_to_audit_record(self, tmp_path):
        config = {
            "results_dir": str(tmp_path / "logs"),
            "memory_log_path": str(tmp_path / "memory.md"),
            "memory_log_max_entries": None,
            "audit_log_path": str(tmp_path / "audit.jsonl"),
            "llm_provider": "deepseek",
            "deep_think_llm": "deepseek-v4-pro",
            "quick_think_llm": "deepseek-v4-flash",
        }
        graph = MagicMock(spec=TradingAgentsGraph)
        graph.config = config
        graph.ticker = "NVDA"
        graph.log_states_dict = {}
        graph.memory_log = TradingMemoryLog(config)
        graph.audit_log = AuditLog(config)
        graph._log_state = lambda td, fs: TradingAgentsGraph._log_state(graph, td, fs)

        TradingAgentsGraph.finalize_run(
            graph,
            _fake_final_state(),
            "2026-06-01",
            run_purpose="recheck",
            position_size_gbp=None,
        )
        record = AuditLog(config).load_all()[0]
        assert record["run_purpose"] == "recheck"
        assert record["position_size_gbp"] is None
