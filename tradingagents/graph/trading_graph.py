# TradingAgents/graph/trading_graph.py

import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yfinance as yf
from langgraph.prebuilt import ToolNode

# Import the abstract tool methods from agent_utils
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_global_news,
    get_income_statement,
    get_indicators,
    get_insider_transactions,
    get_macro_indicators,
    get_news,
    get_prediction_markets,
    get_stock_data,
    get_verified_market_snapshot,
    resolve_instrument_identity,
)
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.market_data_validator import build_verified_market_snapshot_payload
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.evidence import EvidenceLedger, verify_citations
from tradingagents.guardrails import (
    MathGuardrailEngine,
    QuantitativeAnchor,
    build_market_price_anchor,
)
from tradingagents.llm_clients import create_llm_client
from tradingagents.reporting import build_evidence_audit, write_report_tree

from .checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from .conditional_logic import ConditionalLogic
from .propagation import Propagator
from .reflection import Reflector
from .setup import GraphSetup
from .signal_processing import SignalProcessor

logger = logging.getLogger(__name__)


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=("market", "social", "news", "fundamentals"),
        debug=False,
        config: dict[str, Any] = None,
        callbacks: list | None = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []

        # Update the interface's config
        set_config(self.config)

        # Create necessary directories
        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        # Initialize LLMs with provider-specific thinking configuration
        llm_kwargs = self._get_provider_kwargs()

        # Add callbacks to kwargs if provided (passed to LLM constructor)
        if self.callbacks:
            llm_kwargs["callbacks"] = self.callbacks

        deep_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["deep_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        quick_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["quick_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )

        self.deep_thinking_llm = deep_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()

        self.memory_log = TradingMemoryLog(self.config)

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # Initialize components
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.conditional_logic,
        )

        self.propagator = Propagator(
            max_recur_limit=self.config.get("max_recur_limit", 100),
        )
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        # Set up the graph: keep the workflow for recompilation with a checkpointer.
        self.workflow = self.graph_setup.setup_graph(selected_analysts)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None

    def _get_provider_kwargs(self) -> dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation."""
        kwargs = {}
        provider = self.config.get("llm_provider", "").lower()

        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level

        elif provider == "openai":
            reasoning_effort = self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort

        elif provider == "anthropic":
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort

        # Sampling temperature is cross-provider: forward it whenever set.
        # float() here so a value coming from a TRADINGAGENTS_TEMPERATURE env
        # string ("0.2") works the same as a programmatic float.
        temperature = self.config.get("temperature")
        if temperature is not None and temperature != "":
            kwargs["temperature"] = float(temperature)

        return kwargs

    def _create_tool_nodes(self) -> dict[str, ToolNode]:
        """Create tool nodes for different data sources using abstract methods."""
        return {
            "market": ToolNode(
                [
                    # Core stock data tools
                    get_stock_data,
                    # Technical indicators
                    get_indicators,
                    # Deterministic verification snapshot (bound to the analyst
                    # LLM and required by its prompt; must be executable here or
                    # the call fails and the model reports it "unavailable").
                    get_verified_market_snapshot,
                ]
            ),
            "social": ToolNode(
                [
                    # News tools for social media analysis
                    get_news,
                ]
            ),
            "news": ToolNode(
                [
                    # News and insider information
                    get_news,
                    get_global_news,
                    get_insider_transactions,
                    get_macro_indicators,
                    get_prediction_markets,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    # Fundamental analysis tools
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                ]
            ),
        }

    def _resolve_benchmark(self, ticker: str) -> str:
        """Pick the benchmark ticker for alpha calculation against ``ticker``.

        ``config["benchmark_ticker"]`` overrides everything when set; otherwise
        the suffix map matches the ticker's exchange suffix (e.g. ``.T`` for
        Tokyo). US-listed tickers without a dotted suffix fall through to the
        empty-suffix entry (SPY by default). Unrecognised suffixes (including
        US tickers with dots like ``BRK.B``) also fall back to the empty-suffix
        entry, which is the right default because the alpha calculation works
        in USD.
        """
        explicit = self.config.get("benchmark_ticker")
        if explicit:
            return explicit
        benchmark_map = self.config.get("benchmark_map", {})
        ticker_upper = ticker.upper()
        for suffix, benchmark in benchmark_map.items():
            if suffix and ticker_upper.endswith(suffix.upper()):
                return benchmark
        return benchmark_map.get("", "SPY")

    def _fetch_returns(
        self, ticker: str, trade_date: str, holding_days: int = 5,
        benchmark: str = "SPY",
    ) -> tuple[float | None, float | None, int | None]:
        """Fetch raw and alpha return for ticker over holding_days from trade_date.

        ``benchmark`` is the index used as the alpha baseline (resolved by the
        caller via ``_resolve_benchmark``). Returns ``(raw_return, alpha_return,
        actual_holding_days)`` or ``(None, None, None)`` if price data is
        unavailable (too recent, delisted, or network error).
        """
        from tradingagents.dataflows.symbol_utils import normalize_symbol

        try:
            start = datetime.strptime(trade_date, "%Y-%m-%d")
            end = start + timedelta(days=holding_days + 7)  # buffer for weekends/holidays
            end_str = end.strftime("%Y-%m-%d")

            # Normalize so the realized-return lookup hits the same instrument
            # the analysis priced (e.g. XAUUSD -> GC=F) (#984). The benchmark is
            # already a canonical Yahoo symbol from ``_resolve_benchmark``.
            stock = yf.Ticker(normalize_symbol(ticker)).history(start=trade_date, end=end_str)
            bench = yf.Ticker(benchmark).history(start=trade_date, end=end_str)

            if len(stock) < 2 or len(bench) < 2:
                return None, None, None

            actual_days = min(holding_days, len(stock) - 1, len(bench) - 1)
            raw = float(
                (stock["Close"].iloc[actual_days] - stock["Close"].iloc[0])
                / stock["Close"].iloc[0]
            )
            bench_ret = float(
                (bench["Close"].iloc[actual_days] - bench["Close"].iloc[0])
                / bench["Close"].iloc[0]
            )
            alpha = raw - bench_ret
            return raw, alpha, actual_days
        except Exception as e:
            logger.warning(
                "Could not resolve outcome for %s on %s vs %s (will retry next run): %s",
                ticker, trade_date, benchmark, e,
            )
            return None, None, None

    def _resolve_pending_entries(self, ticker: str) -> None:
        """Resolve pending log entries for ticker at the start of a new run.

        Fetches returns for each same-ticker pending entry, generates reflections,
        then writes all updates in a single atomic batch write to avoid redundant I/O.
        Skips entries whose price data is not yet available (too recent or delisted).

        Trade-off: only same-ticker entries are resolved per run.  Entries for
        other tickers accumulate until that ticker is run again.
        """
        pending = [e for e in self.memory_log.get_pending_entries() if e["ticker"] == ticker]
        if not pending:
            return

        benchmark = self._resolve_benchmark(ticker)
        updates = []
        for entry in pending:
            raw, alpha, days = self._fetch_returns(
                ticker, entry["date"], benchmark=benchmark,
            )
            if raw is None:
                continue  # price not available yet — try again next run
            reflection = self.reflector.reflect_on_final_decision(
                final_decision=entry.get("decision", ""),
                raw_return=raw,
                alpha_return=alpha,
                benchmark_name=benchmark,
            )
            updates.append({
                "ticker": ticker,
                "trade_date": entry["date"],
                "raw_return": raw,
                "alpha_return": alpha,
                "holding_days": days,
                "reflection": reflection,
            })

        if updates:
            self.memory_log.batch_update_with_outcomes(updates)

    def resolve_instrument_context(self, ticker: str, asset_type: str = "stock") -> str:
        """Resolve ticker identity once and return the full instrument context.

        Deterministic yfinance lookup (cached, fail-open) injected into a
        context string so every agent anchors to the real company instead of
        hallucinating one from the price chart (#814). Both the propagate()
        path and the CLI call this so the resolved identity reaches the whole
        graph regardless of entry point.
        """
        identity = resolve_instrument_identity(ticker)
        return build_instrument_context(ticker, asset_type, identity)

    def propagate(self, company_name, trade_date, asset_type: str = "stock"):
        """Run the trading agents graph for a company on a specific date.

        ``asset_type`` selects between the stock pipeline (default) and the
        crypto pipeline (``"crypto"``) shipped in #567 — the CLI auto-detects
        from the ticker; programmatic callers pass it explicitly. When
        ``checkpoint_enabled`` is set in config, the graph is recompiled with
        a per-ticker SqliteSaver so a crashed run can resume from the last
        successful node on a subsequent invocation with the same ticker+date.
        """
        self.ticker = company_name

        # Resolve any pending memory-log entries for this ticker before the pipeline runs.
        self._resolve_pending_entries(company_name)

        # Recompile with a checkpointer if the user opted in.
        if self.config.get("checkpoint_enabled"):
            self._checkpointer_ctx = get_checkpointer(
                self.config["data_cache_dir"], company_name
            )
            saver = self._checkpointer_ctx.__enter__()
            self.graph = self.workflow.compile(checkpointer=saver)

            step = checkpoint_step(
                self.config["data_cache_dir"], company_name, str(trade_date)
            )
            if step is not None:
                logger.info(
                    "Resuming from step %d for %s on %s", step, company_name, trade_date
                )
            else:
                logger.info("Starting fresh for %s on %s", company_name, trade_date)

        try:
            return self._run_graph(company_name, trade_date, asset_type=asset_type)
        finally:
            if self._checkpointer_ctx is not None:
                self._checkpointer_ctx.__exit__(None, None, None)
                self._checkpointer_ctx = None
                self.graph = self.workflow.compile()

    def save_reports(self, final_state, ticker, save_path=None) -> Path:
        """Write the markdown report tree for a completed run, like the CLI does.

        Programmatic callers get the same on-disk reports the CLI produces. Pass
        an explicit ``save_path`` or let it default under ``results_dir``.
        """
        if save_path is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = (
                Path(self.config["results_dir"])
                / "reports"
                / f"{safe_ticker_component(ticker)}_{stamp}"
            )
        return write_report_tree(final_state, ticker, save_path)

    def _empty_evidence_pack(self, warnings: list[str] | None = None) -> dict[str, Any]:
        return {
            "evidence_ledger": {"items": []},
            "evidence_summary": "",
            "quantitative_anchors": [],
            "math_guardrail_events": [],
            "citation_verification": None,
            "evidence_warnings": list(warnings or []),
        }

    def _build_evidence_pack(self, company_name: str, trade_date: str) -> dict[str, Any]:
        if not self.config.get("evidence_enabled", True):
            return self._empty_evidence_pack()

        try:
            payload = build_verified_market_snapshot_payload(company_name, str(trade_date))
            ledger = EvidenceLedger()
            evidence = ledger.register(
                source="verified_market_snapshot",
                title=f"Verified market snapshot for {company_name}",
                as_of_date=str(payload.get("latest_date") or trade_date),
                payload=payload,
                aliases=[f"EVD-MKT-{company_name.upper()}-{trade_date}"],
            )
            anchors = []
            if self.config.get("quant_anchor_enabled", True):
                anchor = build_market_price_anchor(
                    symbol=company_name,
                    as_of_date=str(trade_date),
                    market_snapshot_payload=payload,
                    evidence_id=evidence.evidence_id,
                )
                anchors.append(anchor.model_dump())
            summary = (
                f"- {evidence.evidence_id}: {evidence.title}; "
                f"as_of={evidence.as_of_date}; source={evidence.source}"
            )
            return {
                "evidence_ledger": ledger.to_dict(),
                "evidence_summary": summary,
                "quantitative_anchors": anchors,
                "math_guardrail_events": [],
                "citation_verification": None,
                "evidence_warnings": [],
            }
        except Exception as exc:  # noqa: BLE001 - evidence audit must not block analysis
            logger.warning(
                "Could not build evidence pack for %s on %s: %s",
                company_name,
                trade_date,
                exc,
            )
            return self._empty_evidence_pack(
                [f"Evidence pack unavailable for {company_name} on {trade_date}: {exc}"]
            )

    def _merge_evidence_defaults(
        self,
        final_state: dict[str, Any],
        evidence_pack: dict[str, Any],
    ) -> None:
        for key, value in evidence_pack.items():
            final_state.setdefault(key, value)

    def _audit_final_state(self, final_state: dict[str, Any]) -> None:
        warnings = list(final_state.get("evidence_warnings") or [])
        strict_mode = str(self.config.get("evidence_strict_mode", "warn")).strip().lower()
        blocking_reasons: list[str] = []
        ledger = EvidenceLedger.from_dict(final_state.get("evidence_ledger") or {"items": []})
        decision = final_state.get("final_trade_decision", "")

        if self.config.get("citation_verification_enabled", True):
            result = verify_citations(
                str(decision),
                ledger,
                require_citation=bool(self.config.get("evidence_enabled", True) and ledger.list_items()),
            )
            final_state["citation_verification"] = result.model_dump()
            warnings.extend(result.warnings)
            if not result.passed:
                blocking_reasons.extend(result.warnings or ["Citation verification failed."])

        if self.config.get("quant_anchor_enabled", True):
            price_target = TradingAgentsGraph._extract_price_target(str(decision))
            engine = MathGuardrailEngine(
                warn_multiple=float(self.config.get("price_target_warn_multiple", 3.0)),
                block_multiple=float(self.config.get("price_target_block_multiple", 5.0)),
            )
            events = list(final_state.get("math_guardrail_events") or [])
            for anchor_payload in final_state.get("quantitative_anchors") or []:
                anchor = QuantitativeAnchor(**anchor_payload)
                for event in engine.check_price_target(anchor, price_target):
                    dumped = event.model_dump()
                    events.append(dumped)
                    if event.status != "pass":
                        warnings.append(event.message)
                    if event.status == "blocked":
                        blocking_reasons.append(f"{event.rule_id}: {event.message}")
            final_state["math_guardrail_events"] = events

        final_state["evidence_warnings"] = warnings
        final_state["evidence_strict_mode"] = strict_mode
        final_state["evidence_blocking_reasons"] = blocking_reasons
        if strict_mode == "block" and blocking_reasons:
            final_state["evidence_strict_blocked"] = True
            final_state["evidence_decision_status"] = "blocked"
            final_state["evidence_actionable"] = False
            final_state["original_final_trade_decision"] = str(decision)
            final_state["final_trade_decision"] = TradingAgentsGraph._render_strict_blocked_decision(
                original_decision=str(decision),
                blocking_reasons=blocking_reasons,
            )
        else:
            final_state["evidence_strict_blocked"] = False
            final_state["evidence_decision_status"] = "actionable"
            final_state["evidence_actionable"] = True
            final_state["original_final_trade_decision"] = None
        risk_state = final_state.get("risk_debate_state")
        if isinstance(risk_state, dict):
            risk_state["judge_decision"] = final_state["final_trade_decision"]
        final_state["evidence_audit"] = build_evidence_audit(final_state)

    @staticmethod
    def _render_strict_blocked_decision(
        original_decision: str,
        blocking_reasons: list[str],
    ) -> str:
        reasons = "\n".join(f"- {reason}" for reason in blocking_reasons)
        return (
            "**Rating**: Hold\n\n"
            "**Decision Status**: Blocked - Not Actionable\n\n"
            "**Executive Summary**: The original portfolio judgment is blocked "
            "from actionable use because required evidence checks failed. Treat "
            "the affected conclusions as invalid until the blocking reasons are "
            "resolved.\n\n"
            f"**Blocking Reasons**:\n{reasons}\n\n"
            "### Original blocked decision\n\n"
            f"{original_decision}"
        )

    @staticmethod
    def _extract_price_target(decision: str) -> float | None:
        match = re.search(
            r"(?:\*\*)?Price\s+Target(?:\*\*)?\s*:\s*\$?\s*([-+]?\d+(?:,\d{3})*(?:\.\d+)?)",
            decision,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return None

    def _run_graph(self, company_name, trade_date, asset_type: str = "stock"):
        """Execute the graph and write the resulting state to disk and memory log."""
        # Initialize state — inject memory log context for PM and the
        # deterministically resolved instrument identity for all agents.
        past_context = self.memory_log.get_past_context(company_name)
        instrument_context = self.resolve_instrument_context(company_name, asset_type)
        evidence_pack = TradingAgentsGraph._build_evidence_pack(
            self, company_name, str(trade_date)
        )
        init_agent_state = self.propagator.create_initial_state(
            company_name,
            trade_date,
            asset_type=asset_type,
            past_context=past_context,
            instrument_context=instrument_context,
            **evidence_pack,
        )
        args = self.propagator.get_graph_args()

        # Inject thread_id so same ticker+date resumes, different date starts fresh.
        if self.config.get("checkpoint_enabled"):
            tid = thread_id(company_name, str(trade_date))
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

        if self.debug:
            trace = []
            last_printed = None
            for chunk in self.graph.stream(init_agent_state, **args):
                if chunk["messages"]:
                    msg = chunk["messages"][-1]
                    # Nodes after the trader don't append to messages, so the
                    # same trailing message repeats across chunks. Print it only
                    # when it changes (#1027); the trace/state merge is unchanged.
                    signature = (type(msg).__name__, getattr(msg, "content", None))
                    if signature != last_printed:
                        msg.pretty_print()
                        last_printed = signature
                    trace.append(chunk)
            # Streamed chunks are per-node deltas. Merge them so the returned
            # state matches what graph.invoke() yields in the non-debug path.
            final_state = {}
            for chunk in trace:
                final_state.update(chunk)
        else:
            final_state = self.graph.invoke(init_agent_state, **args)

        TradingAgentsGraph._merge_evidence_defaults(self, final_state, evidence_pack)
        TradingAgentsGraph._audit_final_state(self, final_state)

        # Store current state for reflection.
        self.curr_state = final_state

        # Log state to disk.
        self._log_state(trade_date, final_state)

        # Store only actionable decisions for deferred performance reflection.
        if final_state.get("evidence_decision_status") != "blocked":
            self.memory_log.store_decision(
                ticker=company_name,
                trade_date=trade_date,
                final_trade_decision=final_state["final_trade_decision"],
            )

        # Clear checkpoint on successful completion to avoid stale state.
        if self.config.get("checkpoint_enabled"):
            clear_checkpoint(
                self.config["data_cache_dir"], company_name, str(trade_date)
            )

        return final_state, self.process_signal(final_state["final_trade_decision"])

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
                "judge_decision": final_state["investment_debate_state"][
                    "judge_decision"
                ],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
            "evidence_ledger": final_state.get("evidence_ledger", {"items": []}),
            "evidence_summary": final_state.get("evidence_summary", ""),
            "quantitative_anchors": final_state.get("quantitative_anchors", []),
            "math_guardrail_events": final_state.get("math_guardrail_events", []),
            "citation_verification": final_state.get("citation_verification"),
            "evidence_warnings": final_state.get("evidence_warnings", []),
            "evidence_strict_mode": final_state.get("evidence_strict_mode", "warn"),
            "evidence_strict_blocked": final_state.get("evidence_strict_blocked", False),
            "evidence_decision_status": final_state.get(
                "evidence_decision_status", "actionable"
            ),
            "evidence_actionable": final_state.get("evidence_actionable", True),
            "evidence_blocking_reasons": final_state.get("evidence_blocking_reasons", []),
            "original_final_trade_decision": final_state.get("original_final_trade_decision"),
            "evidence_audit": build_evidence_audit(final_state),
        }

        # Save to file. Reject ticker values that would escape the
        # results directory when joined as a path component.
        safe_ticker = safe_ticker_component(self.ticker)
        directory = Path(self.config["results_dir"]) / safe_ticker / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.log_states_dict[str(trade_date)], f, indent=4)

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)
