"""P1 Task 1: the running process is identifiable, and its two open defects are pinned.

The data lineage audit could not tell from outside whether the serving process
ran the merged code. `/api/health` answers that since P1, but nothing printed it
at startup, and two defects keep the answer misleading or incomplete:

``R1`` ``service_started_at`` is the module's first-import time, not the process
     start — a value *later* than the process it describes.
``R2`` ``set_run_registry`` is never called outside the tests, so the analysts'
     certified-metric tool can never read the run's registry.

R1 and R2 are recorded, not fixed: both change the runtime identity contract or
the live graph path, which this verification branch deliberately leaves alone.
The tests below fail if the defects are *silently* removed without the
documented fix, and fail if they are fixed in a way that changes their shape —
so neither can be "fixed" by deleting the evidence.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import UTC, datetime

from tradingagents.build_info import LOADED_AT, build_info, commit_sha
from webapp.__main__ import startup_diagnostics

# ---------------------------------------------------------------------------
# The startup diagnostics this branch adds (R3, fixed).
# ---------------------------------------------------------------------------


class TestStartupDiagnostics:
    """The console that starts the process must name the build it runs."""

    def test_the_build_id_and_commit_are_reported(self):
        lines = startup_diagnostics()
        joined = "\n".join(lines)
        assert "commit" in joined
        assert commit_sha() in joined, "the startup output must name the live commit"

    def test_the_validator_status_is_reported(self):
        """A module that imports but was never called looks identical to one that works."""
        joined = "\n".join(startup_diagnostics())
        assert "validators" in joined
        assert "metric_registry" in joined

    def test_a_broken_checkout_still_starts(self, monkeypatch):
        """Diagnostics must never stop the server: one bad line is enough."""
        import tradingagents.build_info as module

        monkeypatch.setattr(module, "commit_sha",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no git")))
        lines = startup_diagnostics()
        assert lines, "a failure must still produce a line"
        assert any("unknown" in line or "no git" in line for line in lines)


# ---------------------------------------------------------------------------
# R1 — service_started_at is not the process start.
# ---------------------------------------------------------------------------


class TestR1ServiceStartedAt:
    """`service_started_at` equals LOADED_AT, which is a first-import timestamp."""

    def test_the_payload_still_reports_loaded_at_as_the_start(self):
        """Pins the current, defective shape so a fix must be deliberate."""
        info = build_info()
        assert info["service_started_at"] == LOADED_AT

    def test_loaded_at_cannot_be_earlier_than_the_process_it_describes(self):
        """A start time earlier than the interpreter is impossible; later is the defect.

        The process in a fresh interpreter began at ``T0``; importing the module
        afterwards can only produce a later ``LOADED_AT``. The health payload
        calls that later value the service start.
        """
        t0 = datetime.now(UTC)
        time.sleep(1.1)
        code = "from tradingagents.build_info import LOADED_AT; print(LOADED_AT)"
        out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, check=True).stdout.strip()
        reported = datetime.fromisoformat(out)
        assert reported > t0, (
            "LOADED_AT was expected to be later than the process start — that "
            "is the R1 defect; if this now fails, R1 has been fixed and the "
            "health payload must stop calling it service_started_at"
        )


# ---------------------------------------------------------------------------
# R2 — the agents' certified-metric tool never receives a registry.
# ---------------------------------------------------------------------------


class TestR2AgentRegistry:
    """`set_run_registry` is called by the tests only, so the tool is inert."""

    def test_the_graph_never_attaches_a_registry(self):
        """No production module calls the setter: the tool can only answer UNSUPPORTED."""
        result = subprocess.run(
            ["grep", "-rn", "set_run_registry", "tradingagents/", "cli/", "webapp/",
             "--include=*.py"],
            capture_output=True, text=True, check=False,
        )
        call_sites = [
            line for line in result.stdout.splitlines()
            if line.strip() and "__pycache__" not in line
            and "def set_run_registry" not in line
        ]
        assert call_sites == [], (
            "set_run_registry now has a production call site: R2 has been fixed "
            "and docs/audits/P1_RUNTIME_VERIFICATION.md must be updated"
        )

    def test_the_tool_answers_unsupported_without_a_registry(self):
        """The behaviour R2 produces: a certified metric is unreadable to the agent."""
        from tradingagents.agents import math_tools
        from tradingagents.dataflows.math.run_registry import (
            RunInputs,
            build_run_registry,
        )

        registry = build_run_registry(
            RunInputs(price=576.74, book_value_per_share=359.5599), run_id="r1")
        assert registry.get("price_to_book").is_usable is True, (
            "precondition: the gate's own registry certifies a P/B"
        )

        # Reset first: the global is process-wide (R2), so a registry another
        # test attached would otherwise leak in — which is the defect itself.
        math_tools.set_run_registry(None)
        try:
            payload = json.loads(math_tools.get_certified_metric.invoke(
                {"metric_name": "price_to_book", "ticker": "BRK-B"}))
        finally:
            math_tools.set_run_registry(None)
        assert payload["value"] is None
        assert payload["calculation_status"] == "UNSUPPORTED"
        assert payload["blocks_decision"] is True

    def test_a_registry_attached_for_one_run_is_visible_to_the_next(self):
        """R2's second harm: the global is shared, so runs are not isolated.

        A registry attached while evaluating one analysis stays readable after
        that analysis ends. Two analyses in one process therefore share it,
        which is what `run_registry`'s module docstring says must never happen.
        """
        from tradingagents.agents import math_tools
        from tradingagents.dataflows.math.run_registry import (
            RunInputs,
            build_run_registry,
        )

        first = build_run_registry(
            RunInputs(price=576.74, book_value_per_share=359.5599), run_id="run-a")
        math_tools.set_run_registry(first)
        try:
            leaked = json.loads(math_tools.get_certified_metric.invoke(
                {"metric_name": "price_to_book", "ticker": "BRK-B"}))
        finally:
            math_tools.set_run_registry(None)

        assert leaked["value"] is not None, (
            "the attached registry was expected to leak into the next read — "
            "if this fails, run isolation has been fixed and R2 is resolved"
        )


# ---------------------------------------------------------------------------
# The behaviour the audit cares about most: none of this weakens the gate.
# ---------------------------------------------------------------------------


class TestTheGateStaysClosed:
    def test_a_critical_metric_that_cannot_be_verified_still_blocks(self):
        """R2 must never be 'solved' by letting an unverified metric through."""
        from tradingagents.dataflows.gate_integration import (
            ExecutionAuthorization,
            attach_registry_status,
            attach_to_state,
            evaluate_decision,
        )

        state = {
            "company_of_interest": "BRK-B",
            "trade_date": "2026-11-09",
            "market_report": "P/B of 1.6040x.",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "investment_debate_state": {"bull_history": "", "bear_history": "",
                                        "history": "", "current_response": ""},
            "trader_investment_plan": "Entry 557.00, stop 547.40, ATR 9.408.",
            "risk_debate_state": {"aggressive_history": "", "conservative_history": "",
                                  "neutral_history": "", "history": ""},
            "investment_plan": "",
            "final_rating": "Overweight",
            "final_trade_decision": "**Rating**: Overweight\nBuy.",
        }
        _, decision = evaluate_decision(
            "BRK-B", "2026-11-09", state, snapshot_id="s", trigger_met=True,
            equity=100_000.0, cash=100_000.0, risk_budget=1_000.0,
            max_symbol_exposure=0.05, metric_registry=None,
        )
        attach_to_state(state, decision)
        attach_registry_status(state, None)
        assert state["execution_authorization"] == str(
            ExecutionAuthorization.BLOCKED)
        assert decision.creates_order is False
