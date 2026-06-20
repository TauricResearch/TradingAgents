"""Tests for the re-check workflow.

Covers:
- ``TradingAgentsGraph.resolve_original_thesis``: pulls the latest initial
  audit-log record for the ticker, formats it for prompt injection,
  returns empty string when no prior initial run exists.
- ``propagate(run_purpose="recheck")``: auto-resolves the original thesis
  from the audit log when one isn't passed explicitly.
- Portfolio Manager prompt: contains the original thesis and the explicit
  intact / weakening / broken instruction only when ``original_thesis`` is
  non-empty in state; behaves as a normal initial run otherwise.
"""

import functools
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating
from tradingagents.agents.utils.audit_log import AuditLog
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.graph.trading_graph import TradingAgentsGraph


def _make_pm_state(original_thesis: str = "", position_size_gbp: float | None = None):
    """Minimal AgentState dict for the portfolio_manager_node."""
    return {
        "company_of_interest": "NVDA",
        "past_context": "",
        "original_thesis": original_thesis,
        "position_size_gbp": position_size_gbp,
        "risk_debate_state": {
            "history": "Risk debate history.",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 1,
        },
        "market_report": "Market report.",
        "sentiment_report": "Sentiment report.",
        "news_report": "News report.",
        "fundamentals_report": "Fundamentals report.",
        "investment_plan": "Research plan.",
        "trader_investment_plan": "Trader plan.",
    }


def _structured_pm_llm(captured: dict, decision: PortfolioDecision | None = None):
    """MagicMock LLM whose structured binding captures the prompt and returns
    a real PortfolioDecision so render_pm_decision works."""
    if decision is None:
        decision = PortfolioDecision(
            rating=PortfolioRating.HOLD,
            executive_summary="Sit tight.",
            investment_thesis="Balanced view.",
            time_horizon="Condition-based — reassess after next earnings.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or decision
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


# ---------------------------------------------------------------------------
# resolve_original_thesis
# ---------------------------------------------------------------------------


def _seed_audit_log(tmp_path, *, ticker, trade_date, run_purpose="initial",
                    investment_plan="orig plan", final_decision="orig decision"):
    log = AuditLog({"audit_log_path": str(tmp_path / "audit.jsonl")})
    log.append(
        ticker=ticker,
        trade_date=trade_date,
        run_purpose=run_purpose,
        position_size_gbp=None,
        llm_provider="deepseek",
        deep_think_llm="deepseek-v4-pro",
        quick_think_llm="deepseek-v4-flash",
        decision_payload={
            "investment_plan": investment_plan,
            "final_trade_decision": final_decision,
        },
    )
    return log


@pytest.mark.unit
class TestResolveOriginalThesis:
    def test_returns_formatted_context_for_latest_initial(self, tmp_path):
        log = _seed_audit_log(
            tmp_path,
            ticker="NVDA",
            trade_date="2026-01-05",
            investment_plan="**Recommendation**: Buy\nAI capex cycle.",
            final_decision="**Rating**: Buy\nInitiate at £200.",
        )
        mock_graph = MagicMock(spec=TradingAgentsGraph)
        mock_graph.audit_log = log
        thesis = TradingAgentsGraph.resolve_original_thesis(mock_graph, "NVDA")
        assert "2026-01-05" in thesis
        assert "AI capex cycle." in thesis
        assert "Initiate at £200." in thesis
        # The re-check framing instruction is included.
        assert "RE-CHECK" in thesis.upper() or "re-check" in thesis

    def test_returns_empty_when_no_prior_initial_exists(self, tmp_path):
        log = AuditLog({"audit_log_path": str(tmp_path / "audit.jsonl")})
        mock_graph = MagicMock(spec=TradingAgentsGraph)
        mock_graph.audit_log = log
        assert TradingAgentsGraph.resolve_original_thesis(mock_graph, "NVDA") == ""

    def test_returns_empty_when_only_rechecks_exist(self, tmp_path):
        """Re-check entries must not shadow the missing original initial run."""
        log = _seed_audit_log(
            tmp_path, ticker="NVDA", trade_date="2026-04-01",
            run_purpose="recheck",
        )
        mock_graph = MagicMock(spec=TradingAgentsGraph)
        mock_graph.audit_log = log
        assert TradingAgentsGraph.resolve_original_thesis(mock_graph, "NVDA") == ""


# ---------------------------------------------------------------------------
# propagate(run_purpose="recheck") auto-resolution
# ---------------------------------------------------------------------------


def _fake_final_state():
    """Minimal final_state dict mirroring what _log_state expects."""
    return {
        "final_trade_decision": "Rating: Hold\nSit tight on the existing £800.",
        "company_of_interest": "NVDA",
        "trade_date": "2026-04-15",
        "market_report": "",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "investment_debate_state": {
            "bull_history": "", "bear_history": "", "history": "",
            "current_response": "", "judge_decision": "",
        },
        "investment_plan": "",
        "trader_investment_plan": "",
        "risk_debate_state": {
            "aggressive_history": "", "conservative_history": "",
            "neutral_history": "", "history": "", "judge_decision": "",
            "current_aggressive_response": "", "current_conservative_response": "",
            "current_neutral_response": "", "count": 1, "latest_speaker": "",
        },
    }


@pytest.mark.unit
class TestPropagateRecheckAutoResolve:
    def test_recheck_auto_resolves_when_thesis_not_passed(self, tmp_path):
        """Calling propagate with run_purpose='recheck' (and no explicit
        original_thesis) should auto-fetch from the audit log and inject it
        into create_initial_state."""
        # Seed the audit log with an earlier initial run.
        _seed_audit_log(
            tmp_path, ticker="NVDA", trade_date="2026-01-05",
            investment_plan="**Recommendation**: Buy\nOriginal plan body.",
            final_decision="**Rating**: Buy\nOriginal decision body.",
        )

        mock_graph = MagicMock()
        mock_graph.memory_log = TradingMemoryLog({"memory_log_path": str(tmp_path / "mem.md")})
        mock_graph.audit_log = AuditLog({"audit_log_path": str(tmp_path / "audit.jsonl")})
        mock_graph.log_states_dict = {}
        mock_graph.debug = False
        mock_graph.config = {
            "results_dir": str(tmp_path),
            "llm_provider": "deepseek",
            "deep_think_llm": "deepseek-v4-pro",
            "quick_think_llm": "deepseek-v4-flash",
        }
        mock_graph.graph.invoke.return_value = _fake_final_state()
        # create_initial_state is what we want to spy on — capture the kwargs.
        captured_kwargs: dict = {}
        def _capture_state(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return _fake_final_state()
        mock_graph.propagator.create_initial_state.side_effect = _capture_state
        mock_graph.propagator.get_graph_args.return_value = {}
        mock_graph.signal_processor.process_signal.return_value = "Hold"
        mock_graph._run_graph = functools.partial(
            TradingAgentsGraph._run_graph, mock_graph
        )
        mock_graph.finalize_run = functools.partial(
            TradingAgentsGraph.finalize_run, mock_graph
        )
        mock_graph._log_state = functools.partial(
            TradingAgentsGraph._log_state, mock_graph
        )
        # Bind resolve_original_thesis so propagate's auto-resolution runs
        # against the real audit log we seeded above.
        mock_graph.resolve_original_thesis = functools.partial(
            TradingAgentsGraph.resolve_original_thesis, mock_graph
        )

        TradingAgentsGraph.propagate(
            mock_graph, "NVDA", "2026-04-15", run_purpose="recheck",
        )

        assert "original_thesis" in captured_kwargs
        assert "Original plan body." in captured_kwargs["original_thesis"]
        assert "Original decision body." in captured_kwargs["original_thesis"]

    def test_initial_run_keeps_original_thesis_empty(self, tmp_path):
        """An initial run must NOT pick up an original thesis even when one
        exists for the ticker — the auto-resolve only triggers on recheck."""
        _seed_audit_log(
            tmp_path, ticker="NVDA", trade_date="2026-01-05",
            investment_plan="**Recommendation**: Buy\nSome plan.",
            final_decision="**Rating**: Buy\nSome decision.",
        )

        mock_graph = MagicMock()
        mock_graph.memory_log = TradingMemoryLog({"memory_log_path": str(tmp_path / "mem.md")})
        mock_graph.audit_log = AuditLog({"audit_log_path": str(tmp_path / "audit.jsonl")})
        mock_graph.log_states_dict = {}
        mock_graph.debug = False
        mock_graph.config = {
            "results_dir": str(tmp_path),
            "llm_provider": "deepseek",
            "deep_think_llm": "deepseek-v4-pro",
            "quick_think_llm": "deepseek-v4-flash",
        }
        mock_graph.graph.invoke.return_value = _fake_final_state()
        captured_kwargs: dict = {}
        def _capture_state(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return _fake_final_state()
        mock_graph.propagator.create_initial_state.side_effect = _capture_state
        mock_graph.propagator.get_graph_args.return_value = {}
        mock_graph.signal_processor.process_signal.return_value = "Hold"
        mock_graph._run_graph = functools.partial(
            TradingAgentsGraph._run_graph, mock_graph
        )
        mock_graph.finalize_run = functools.partial(
            TradingAgentsGraph.finalize_run, mock_graph
        )
        mock_graph._log_state = functools.partial(
            TradingAgentsGraph._log_state, mock_graph
        )
        mock_graph.resolve_original_thesis = functools.partial(
            TradingAgentsGraph.resolve_original_thesis, mock_graph
        )

        TradingAgentsGraph.propagate(
            mock_graph, "NVDA", "2026-06-01",  # default run_purpose="initial"
        )

        assert captured_kwargs.get("original_thesis") == ""


# ---------------------------------------------------------------------------
# Portfolio Manager prompt mode-switching
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPortfolioManagerRecheckMode:
    def test_prompt_omits_recheck_block_on_initial_run(self):
        """When original_thesis is empty the PM prompt must not contain the
        intact/weakening/broken instruction — that framing is re-check only."""
        captured = {}
        llm = _structured_pm_llm(captured)
        pm = create_portfolio_manager(llm)
        pm(_make_pm_state(original_thesis=""))
        prompt = captured["prompt"]
        assert "RE-CHECK" not in prompt
        assert "intact" not in prompt.lower()
        assert "thesis broken" not in prompt.lower()

    def test_prompt_includes_recheck_block_when_thesis_present(self):
        """When original_thesis is non-empty the PM prompt must surface it
        and explicitly ask for an intact / weakening / broken classification."""
        captured = {}
        llm = _structured_pm_llm(captured)
        pm = create_portfolio_manager(llm)
        original = (
            "Original initial-run thesis content with a distinctive marker: "
            "AI-CAPEX-MARKER-XYZ"
        )
        pm(_make_pm_state(original_thesis=original))
        prompt = captured["prompt"]
        assert "AI-CAPEX-MARKER-XYZ" in prompt
        assert "RE-CHECK" in prompt
        # All three classifications must appear so the model is forced into one.
        assert "intact" in prompt.lower()
        assert "weakening" in prompt.lower()
        assert "broken" in prompt.lower()
