"""First-class, broker-neutral portfolio context for graph inputs (#1166).

The Trader, risk analysts, and Portfolio Manager can produce sizing and
Buy/Overweight/Hold/Underweight/Sell guidance, but the graph previously had
no typed representation of current holdings and capital. These tests pin the
input contract:

- ``PortfolioContext`` / ``PositionSnapshot`` schema validation
- ``None`` (not provided) is distinct from a known flat portfolio
- a deterministic renderer focused on the instrument under analysis
- the context reaching Trader / risk / Portfolio Manager prompts
- ``propagate(..., portfolio_context=...)`` wiring with full backward
  compatibility for existing calls
- the ``--portfolio-context`` CLI file loader
- saved-state metadata recording whether context was present

All tests are credential-free, network-free, and deterministic.
"""
from __future__ import annotations

import functools
import json
from unittest.mock import MagicMock

import pytest
import typer
from pydantic import ValidationError

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.schemas import (
    PortfolioContext,
    PortfolioDecision,
    PortfolioRating,
    PositionSnapshot,
    TraderAction,
    TraderProposal,
    render_portfolio_context,
)
from tradingagents.agents.trader.trader import create_trader
from tradingagents.agents.utils.agent_utils import (
    MISSING_PORTFOLIO_CONTEXT_NOTICE,
    get_portfolio_context_from_state,
    portfolio_prompt_block,
)
from tradingagents.graph.propagation import (
    MISSING_PORTFOLIO_FINGERPRINT,
    Propagator,
    normalize_portfolio_context,
    portfolio_context_fingerprint,
)


def _sample_context() -> PortfolioContext:
    return PortfolioContext(
        positions=[
            PositionSnapshot(
                symbol="NVDA", quantity=10.0, market_value=1895.0,
                average_entry_price=150.0,
            ),
            PositionSnapshot(symbol="MSFT", quantity=5.0),
        ],
        cash=25000.0,
        portfolio_value=120000.0,
        buying_power=50000.0,
        as_of="2026-01-15",
        source="paper-broker",
        currency="USD",
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPortfolioContextSchema:
    def test_empty_is_valid_known_flat(self):
        ctx = PortfolioContext()
        assert ctx.positions == []
        assert ctx.cash is None
        assert ctx.portfolio_value is None
        assert ctx.buying_power is None
        assert ctx.as_of is None
        assert ctx.source is None

    def test_valid_with_position(self):
        ctx = _sample_context()
        assert len(ctx.positions) == 2
        assert ctx.position_for("nvda") is not None  # case-insensitive
        assert ctx.position_for("AAPL") is None

    def test_symbol_blank_rejected(self):
        with pytest.raises(ValidationError):
            PositionSnapshot(symbol="   ", quantity=1.0)

    def test_quantity_malformed_rejected(self):
        with pytest.raises(ValidationError):
            PositionSnapshot(symbol="NVDA", quantity="abc")  # type: ignore[arg-type]

    def test_non_finite_numbers_rejected(self):
        with pytest.raises(ValidationError):
            PositionSnapshot(symbol="NVDA", quantity=float("nan"))
        with pytest.raises(ValidationError):
            PortfolioContext(cash=float("inf"))

    def test_positions_must_be_a_list(self):
        with pytest.raises(ValidationError):
            PortfolioContext(positions={"NVDA": 10.0})  # type: ignore[arg-type]

    def test_json_round_trip(self):
        ctx = _sample_context()
        dumped = ctx.model_dump(mode="json")
        json.dumps(dumped)  # must be JSON-serializable for checkpoints
        assert PortfolioContext.model_validate(dumped) == ctx
        assert PortfolioContext.model_validate_json(ctx.model_dump_json()) == ctx


# ---------------------------------------------------------------------------
# Renderer semantics: missing vs empty vs populated
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPortfolioRendering:
    def test_missing_context_notice(self):
        block = portfolio_prompt_block({"company_of_interest": "NVDA"})
        assert block == MISSING_PORTFOLIO_CONTEXT_NOTICE
        assert "flat" not in block.lower()
        assert "0" not in block  # must not invent a zero position

    def test_none_state_value_is_missing(self):
        assert get_portfolio_context_from_state({"portfolio_context": None}) is None

    def test_empty_positions_is_known_flat(self):
        block = portfolio_prompt_block({
            "company_of_interest": "NVDA",
            "portfolio_context": PortfolioContext().model_dump(mode="json"),
        })
        assert "flat" in block.lower()
        assert MISSING_PORTFOLIO_CONTEXT_NOTICE not in block

    def test_current_position_rendered_with_facts(self):
        text = render_portfolio_context(_sample_context(), "NVDA")
        assert "10 units" in text and "NVDA" in text
        assert "shares" not in text
        assert "1,895.00 USD" in text
        assert "avg entry 150.00" in text  # quote currency: no portfolio label
        assert "USD" not in text.split("avg entry")[1].split("\n")[0]
        assert "25,000.00 USD" in text  # cash
        assert "120,000.00 USD" in text  # portfolio value
        assert "2026-01-15" in text and "paper-broker" in text
        assert "$" not in text

    def test_other_holdings_summarized_not_dumped(self):
        text = render_portfolio_context(_sample_context(), "AAPL")
        assert "no current AAPL position" in text
        assert "2 other position(s)" in text
        assert "MSFT" not in text  # focus the current symbol; full data stays in state
        assert "{" not in text and "}" not in text  # never str(dict)

    def test_missing_capital_labelled(self):
        text = render_portfolio_context(PortfolioContext(), "NVDA")
        assert "no capital figures provided" in text

    def test_typed_model_accepted_from_state(self):
        ctx = _sample_context()
        assert get_portfolio_context_from_state({"portfolio_context": ctx}) == ctx


# ---------------------------------------------------------------------------
# Agent prompt propagation (fake LLMs, no network)
# ---------------------------------------------------------------------------


def _capturing_structured_trader(captured: dict):
    proposal = TraderProposal(action=TraderAction.BUY, reasoning="grounded case")
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or proposal
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


def _capturing_structured_pm(captured: dict):
    decision = PortfolioDecision(
        rating=PortfolioRating.HOLD,
        executive_summary="Hold; await catalyst.",
        investment_thesis="Balanced debate.",
    )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or decision
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


def _capturing_debator_llm(captured: dict):
    llm = MagicMock()
    llm.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt)
        or MagicMock(content="Debate argument.")
    )
    return llm


def _prompt_text(prompt) -> str:
    if isinstance(prompt, str):
        return prompt
    parts = []
    for m in prompt:
        parts.append(
            m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
        )
    return "\n".join(str(p) for p in parts)


def _trader_state(**overrides):
    state = {
        "company_of_interest": "NVDA",
        "investment_plan": "**Recommendation**: Buy",
        "market_report": "Current price $189.5; ATR 4.2.",
    }
    state.update(overrides)
    return state


def _pm_state(**overrides):
    state = {
        "company_of_interest": "NVDA",
        "risk_debate_state": {
            "history": "h", "aggressive_history": "a",
            "conservative_history": "c", "neutral_history": "n",
            "current_aggressive_response": "", "current_conservative_response": "",
            "current_neutral_response": "", "latest_speaker": "Neutral", "count": 1,
        },
        "investment_plan": "plan",
        "trader_investment_plan": "trader plan",
    }
    state.update(overrides)
    return state


def _risk_state(**overrides):
    state = {
        "company_of_interest": "NVDA",
        "market_report": "m", "sentiment_report": "s",
        "news_report": "n", "fundamentals_report": "f",
        "trader_investment_plan": "Buy NVDA.",
        "risk_debate_state": {
            "history": "", "aggressive_history": "", "conservative_history": "",
            "neutral_history": "", "current_aggressive_response": "",
            "current_conservative_response": "", "current_neutral_response": "",
            "latest_speaker": "", "count": 0,
        },
    }
    state.update(overrides)
    return state


@pytest.mark.unit
class TestDecisionNodePrompts:
    def test_trader_prompt_gets_context(self):
        captured = {}
        create_trader(_capturing_structured_trader(captured))(
            _trader_state(
                portfolio_context=_sample_context().model_dump(mode="json")
            )
        )
        text = _prompt_text(captured["prompt"])
        assert "Portfolio Context:" in text
        assert "10" in text and "NVDA" in text

    def test_trader_prompt_missing_notice_without_context(self):
        """Backward compatible: old-style states without the key still work."""
        captured = {}
        create_trader(_capturing_structured_trader(captured))(_trader_state())
        assert MISSING_PORTFOLIO_CONTEXT_NOTICE in _prompt_text(captured["prompt"])

    def test_pm_prompt_gets_context(self):
        captured = {}
        create_portfolio_manager(_capturing_structured_pm(captured))(
            _pm_state(portfolio_context=_sample_context().model_dump(mode="json"))
        )
        text = _prompt_text(captured["prompt"])
        assert "Portfolio Context:" in text
        assert "25,000.00 USD" in text

    def test_pm_prompt_missing_notice_without_context(self):
        captured = {}
        create_portfolio_manager(_capturing_structured_pm(captured))(_pm_state())
        assert MISSING_PORTFOLIO_CONTEXT_NOTICE in _prompt_text(captured["prompt"])

    @pytest.mark.parametrize(
        "factory",
        [create_aggressive_debator, create_conservative_debator, create_neutral_debator],
        ids=["aggressive", "conservative", "neutral"],
    )
    def test_risk_debators_get_context(self, factory):
        captured = {}
        factory(_capturing_debator_llm(captured))(
            _risk_state(
                portfolio_context=_sample_context().model_dump(mode="json")
            )
        )
        assert "Portfolio Context:" in captured["prompt"]

    @pytest.mark.parametrize(
        "factory",
        [create_aggressive_debator, create_conservative_debator, create_neutral_debator],
        ids=["aggressive", "conservative", "neutral"],
    )
    def test_risk_debators_missing_notice_without_context(self, factory):
        captured = {}
        factory(_capturing_debator_llm(captured))(_risk_state())
        assert MISSING_PORTFOLIO_CONTEXT_NOTICE in captured["prompt"]


# ---------------------------------------------------------------------------
# Graph wiring
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGraphWiring:
    def test_initial_state_defaults_to_missing(self):
        state = Propagator().create_initial_state("NVDA", "2026-01-10")
        assert state["portfolio_context"] is None

    def test_initial_state_accepts_model_and_dict(self):
        ctx = _sample_context()
        from_model = Propagator().create_initial_state(
            "NVDA", "2026-01-10", portfolio_context=ctx
        )["portfolio_context"]
        from_dict = Propagator().create_initial_state(
            "NVDA", "2026-01-10", portfolio_context=ctx.model_dump(mode="json")
        )["portfolio_context"]
        assert from_model == from_dict
        json.dumps(from_model)  # checkpoint-safe

    def test_initial_state_rejects_malformed(self):
        with pytest.raises(ValidationError):
            Propagator().create_initial_state(
                "NVDA", "2026-01-10", portfolio_context={"cash": "lots"}
            )

    def test_normalize_helper(self):
        assert normalize_portfolio_context(None) is None
        dumped = normalize_portfolio_context(_sample_context())
        assert PortfolioContext.model_validate(dumped) == _sample_context()

    def test_propagate_threads_context(self, tmp_path):
        """propagate() forwards portfolio_context to state creation (mocked graph)."""
        from tradingagents.agents.utils.memory import TradingMemoryLog
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        fake_state = {
            "final_trade_decision": "Rating: Buy\nBuy NVDA.",
            "company_of_interest": "NVDA",
            "trade_date": "2026-01-10",
            "market_report": "", "sentiment_report": "", "news_report": "",
            "fundamentals_report": "",
            "investment_debate_state": {
                "bull_history": "", "bear_history": "", "history": "",
                "current_response": "", "judge_decision": "",
            },
            "investment_plan": "", "trader_investment_plan": "",
            "risk_debate_state": {
                "aggressive_history": "", "conservative_history": "",
                "neutral_history": "", "history": "", "judge_decision": "",
                "current_aggressive_response": "", "current_conservative_response": "",
                "current_neutral_response": "", "count": 1, "latest_speaker": "",
            },
        }
        mock_graph = MagicMock()
        mock_graph.memory_log = TradingMemoryLog(
            {"memory_log_path": str(tmp_path / "mem.md")}
        )
        mock_graph.log_states_dict = {}
        mock_graph.debug = False
        mock_graph.config = {"results_dir": str(tmp_path)}
        mock_graph.graph.invoke.return_value = fake_state
        mock_graph.propagator = Propagator()
        mock_graph.propagator.get_graph_args = MagicMock(return_value={})
        mock_graph.propagator.create_initial_state = MagicMock(
            wraps=mock_graph.propagator.create_initial_state
        )
        mock_graph.signal_processor.process_signal.return_value = "Buy"
        mock_graph.process_signal = functools.partial(
            TradingAgentsGraph.process_signal, mock_graph
        )
        mock_graph._run_graph = functools.partial(
            TradingAgentsGraph._run_graph, mock_graph
        )
        ctx = _sample_context()
        TradingAgentsGraph.propagate(
            mock_graph, "NVDA", "2026-01-10", portfolio_context=ctx
        )
        _, kwargs = mock_graph.propagator.create_initial_state.call_args
        assert kwargs["portfolio_context"] == ctx

    def test_propagate_without_context_stays_backward_compatible(self, tmp_path):
        """Existing propagate(ticker, date) calls pass portfolio_context=None."""
        from tradingagents.agents.utils.memory import TradingMemoryLog
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        fake_state = {
            "final_trade_decision": "Rating: Hold\nHold NVDA.",
            "company_of_interest": "NVDA",
            "trade_date": "2026-01-10",
            "market_report": "", "sentiment_report": "", "news_report": "",
            "fundamentals_report": "",
            "investment_debate_state": {
                "bull_history": "", "bear_history": "", "history": "",
                "current_response": "", "judge_decision": "",
            },
            "investment_plan": "", "trader_investment_plan": "",
            "risk_debate_state": {
                "aggressive_history": "", "conservative_history": "",
                "neutral_history": "", "history": "", "judge_decision": "",
                "current_aggressive_response": "", "current_conservative_response": "",
                "current_neutral_response": "", "count": 1, "latest_speaker": "",
            },
        }
        mock_graph = MagicMock()
        mock_graph.memory_log = TradingMemoryLog(
            {"memory_log_path": str(tmp_path / "mem.md")}
        )
        mock_graph.log_states_dict = {}
        mock_graph.debug = False
        mock_graph.config = {"results_dir": str(tmp_path)}
        mock_graph.graph.invoke.return_value = fake_state
        mock_graph.propagator = Propagator()
        mock_graph.propagator.get_graph_args = MagicMock(return_value={})
        mock_graph.propagator.create_initial_state = MagicMock(
            wraps=mock_graph.propagator.create_initial_state
        )
        mock_graph.signal_processor.process_signal.return_value = "Hold"
        mock_graph.process_signal = functools.partial(
            TradingAgentsGraph.process_signal, mock_graph
        )
        mock_graph._run_graph = functools.partial(
            TradingAgentsGraph._run_graph, mock_graph
        )
        _, signal = TradingAgentsGraph.propagate(mock_graph, "NVDA", "2026-01-10")
        assert signal == "Hold"
        _, kwargs = mock_graph.propagator.create_initial_state.call_args
        assert kwargs["portfolio_context"] is None


# ---------------------------------------------------------------------------
# Saved-state metadata
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSavedStateMetadata:
    def _bare_graph(self, tmp_path):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        g = object.__new__(TradingAgentsGraph)
        g.config = {"results_dir": str(tmp_path)}
        g.ticker = "NVDA"
        g.log_states_dict = {}
        return g

    def _final_state(self, **overrides):
        state = {
            "company_of_interest": "NVDA",
            "trade_date": "2026-01-10",
            "market_report": "", "sentiment_report": "", "news_report": "",
            "fundamentals_report": "",
            "investment_debate_state": {
                "bull_history": "", "bear_history": "", "history": "",
                "current_response": "", "judge_decision": "",
            },
            "trader_investment_plan": "",
            "risk_debate_state": {
                "aggressive_history": "", "conservative_history": "",
                "neutral_history": "", "history": "", "judge_decision": "",
            },
            "investment_plan": "",
            "final_trade_decision": "Rating: Hold",
        }
        state.update(overrides)
        return state

    def test_present_context_recorded(self, tmp_path):
        g = self._bare_graph(tmp_path)
        dumped = _sample_context().model_dump(mode="json")
        g._log_state("2026-01-10", self._final_state(portfolio_context=dumped))
        logged = g.log_states_dict["2026-01-10"]
        assert logged["portfolio_context_present"] is True
        assert logged["portfolio_context"] == dumped

    def test_missing_context_recorded_as_absent(self, tmp_path):
        g = self._bare_graph(tmp_path)
        g._log_state("2026-01-10", self._final_state(portfolio_context=None))
        logged = g.log_states_dict["2026-01-10"]
        assert logged["portfolio_context_present"] is False
        assert logged["portfolio_context"] is None


# ---------------------------------------------------------------------------
# CLI loader
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPortfolioContextFileLoader:
    def test_valid_file(self, tmp_path):
        from cli.main import load_portfolio_context_file

        payload = {
            "positions": [{"symbol": "NVDA", "quantity": 10}],
            "cash": 1000.0,
            "as_of": "2026-01-15",
            "source": "manual",
        }
        path = tmp_path / "portfolio.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        loaded = load_portfolio_context_file(str(path))
        assert PortfolioContext.model_validate(loaded) == PortfolioContext.model_validate(payload)

    def test_missing_file(self, tmp_path):
        from cli.main import load_portfolio_context_file

        with pytest.raises(typer.BadParameter, match="not found"):
            load_portfolio_context_file(str(tmp_path / "nope.json"))

    def test_malformed_json(self, tmp_path):
        from cli.main import load_portfolio_context_file

        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(typer.BadParameter, match="not valid JSON"):
            load_portfolio_context_file(str(path))

    def test_schema_violation(self, tmp_path):
        from cli.main import load_portfolio_context_file

        path = tmp_path / "invalid.json"
        path.write_text(json.dumps({"cash": "lots"}), encoding="utf-8")
        with pytest.raises(typer.BadParameter, match="failed validation"):
            load_portfolio_context_file(str(path))


# ---------------------------------------------------------------------------
# Optional currency label (market-neutral display, no FX conversion)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPortfolioCurrency:
    def test_defaults_to_none(self):
        assert PortfolioContext().currency is None

    def test_normalized_to_uppercase(self):
        assert PortfolioContext(currency="usd").currency == "USD"
        assert PortfolioContext(currency="  jpy ").currency == "JPY"

    def test_blank_rejected(self):
        with pytest.raises(ValidationError):
            PortfolioContext(currency="   ")

    def test_currency_participates_in_round_trip(self):
        ctx = PortfolioContext(currency="EUR", cash=100.0)
        assert PortfolioContext.model_validate(ctx.model_dump(mode="json")) == ctx


@pytest.mark.unit
class TestMarketNeutralRendering:
    def test_no_currency_renders_bare_numbers(self):
        ctx = PortfolioContext(
            positions=[PositionSnapshot(symbol="NVDA", quantity=10.0, market_value=1895.0)],
            cash=25000.0,
        )
        text = render_portfolio_context(ctx, "NVDA")
        assert "1,895.00" in text
        assert "25,000.00" in text
        assert "$" not in text

    def test_crypto_quantity_uses_units(self):
        ctx = PortfolioContext(
            positions=[PositionSnapshot(symbol="BTC-USD", quantity=0.5)],
        )
        text = render_portfolio_context(ctx, "BTC-USD")
        assert "0.5 units" in text
        assert "shares" not in text

    def test_jpy_snapshot_has_no_dollar_sign(self):
        ctx = PortfolioContext(
            currency="JPY",
            positions=[
                PositionSnapshot(
                    symbol="7203.T", quantity=100.0, market_value=280000.0,
                    average_entry_price=2700.0,
                )
            ],
            cash=100000.0,
            as_of="2026-01-15",
            source="paper-broker",
        )
        text = render_portfolio_context(ctx, "7203.T")
        assert "280,000.00 JPY" in text
        assert "100,000.00 JPY" in text
        assert "100 units" in text
        assert "$" not in text
        # Entry price is quoted in the instrument's own currency, which may
        # differ from the portfolio currency: no inherited label.
        assert "avg entry 2,700.00" in text


# ---------------------------------------------------------------------------
# Deterministic fingerprint for checkpoint identity
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPortfolioFingerprint:
    def test_deterministic(self):
        assert portfolio_context_fingerprint(_sample_context()) == (
            portfolio_context_fingerprint(_sample_context())
        )

    def test_model_vs_dict_agree(self):
        ctx = _sample_context()
        assert portfolio_context_fingerprint(ctx) == (
            portfolio_context_fingerprint(ctx.model_dump(mode="json"))
        )

    def test_dict_key_order_irrelevant(self):
        a = {"cash": 1000.0, "positions": [{"symbol": "NVDA", "quantity": 10.0}]}
        b = {"positions": [{"quantity": 10.0, "symbol": "NVDA"}], "cash": 1000.0}
        assert portfolio_context_fingerprint(a) == portfolio_context_fingerprint(b)

    def test_position_order_irrelevant(self):
        a = _sample_context()
        b = _sample_context()
        b.positions = list(reversed(b.positions))
        assert portfolio_context_fingerprint(a) == portfolio_context_fingerprint(b)

    def test_changed_holdings_change_fingerprint(self):
        base = portfolio_context_fingerprint(_sample_context())

        changed_qty = _sample_context()
        changed_qty.positions[0].quantity = 30.0
        assert portfolio_context_fingerprint(changed_qty) != base

        changed_cash = _sample_context()
        changed_cash.cash = 1.0
        assert portfolio_context_fingerprint(changed_cash) != base

        changed_value = _sample_context()
        changed_value.portfolio_value = 1.0
        assert portfolio_context_fingerprint(changed_value) != base

        changed_power = _sample_context()
        changed_power.buying_power = 1.0
        assert portfolio_context_fingerprint(changed_power) != base

        changed_list = _sample_context()
        changed_list.positions = changed_list.positions[:1]
        assert portfolio_context_fingerprint(changed_list) != base

        changed_asof = _sample_context()
        changed_asof.as_of = "2026-01-16"
        assert portfolio_context_fingerprint(changed_asof) != base

        changed_source = _sample_context()
        changed_source.source = "manual"
        assert portfolio_context_fingerprint(changed_source) != base

        changed_currency = _sample_context()
        changed_currency.currency = "EUR"
        assert portfolio_context_fingerprint(changed_currency) != base

    def test_missing_is_fixed_marker(self):
        assert portfolio_context_fingerprint(None) == MISSING_PORTFOLIO_FINGERPRINT
        assert MISSING_PORTFOLIO_FINGERPRINT == "none"

    def test_missing_differs_from_known_empty(self):
        """Missing context must never share checkpoint identity with a flat portfolio."""
        assert portfolio_context_fingerprint(None) != (
            portfolio_context_fingerprint(PortfolioContext())
        )

    def test_fingerprint_is_short_hex_without_holdings(self):
        fp = portfolio_context_fingerprint(_sample_context())
        assert len(fp) == 16
        int(fp, 16)  # hex
        assert "NVDA" not in fp and "{" not in fp


@pytest.mark.unit
class TestCheckpointIdentity:
    def _signature(self, stub_config, portfolio_context=None):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        stub = MagicMock()
        stub.config = stub_config
        stub.selected_analysts = ("market",)
        return TradingAgentsGraph._run_signature(stub, "stock", portfolio_context)

    def test_default_signature_marks_missing(self):
        config = {"max_debate_rounds": 1, "max_risk_discuss_rounds": 1}
        assert "portfolio=none" in self._signature(config)

    def test_same_snapshot_same_signature(self):
        config = {"max_debate_rounds": 1, "max_risk_discuss_rounds": 1}
        assert self._signature(config, _sample_context()) == (
            self._signature(config, _sample_context().model_dump(mode="json"))
        )

    def test_changed_snapshot_changes_signature(self):
        config = {"max_debate_rounds": 1, "max_risk_discuss_rounds": 1}
        changed = _sample_context()
        changed.positions[0].quantity = 30.0
        assert self._signature(config, _sample_context()) != (
            self._signature(config, changed)
        )

    def test_stale_checkpoint_unreachable(self):
        """A changed snapshot routes to a different checkpoint thread, so an
        old-context checkpoint can never be resumed by a new-context run."""
        from tradingagents.graph.checkpointer import thread_id

        config = {"max_debate_rounds": 1, "max_risk_discuss_rounds": 1}
        changed = _sample_context()
        changed.positions[0].quantity = 30.0
        sig_old = self._signature(config, _sample_context())
        sig_new = self._signature(config, changed)
        assert thread_id("NVDA", "2026-01-10", sig_old) != (
            thread_id("NVDA", "2026-01-10", sig_new)
        )
        # ...while an unchanged snapshot reproduces the identical thread.
        assert thread_id("NVDA", "2026-01-10", sig_old) == (
            thread_id("NVDA", "2026-01-10", self._signature(config, _sample_context()))
        )
