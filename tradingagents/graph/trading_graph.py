import hashlib
import json
import logging
import os
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import tradingagents
from tradingagents.agents.context import build_instrument_context, resolve_instrument_identity
from tradingagents.agents.rating import run_rating
from tradingagents.dataflows.config import run_config, run_config_context, set_config
from tradingagents.dataflows.date_window import get_current_date, is_historical
from tradingagents.dataflows.filing_freshness import (
    filings_from_sec_edgar,
    used_period_end_from_report,
)
from tradingagents.dataflows.gate_integration import (
    attach_registry_status,
    attach_to_state,
    evaluate_decision,
    write_audit_record,
)
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients import create_tier_client, tier_provider
from tradingagents.memory import TradingMemoryLog, settlement
from tradingagents.memory.reflection import Reflector
from tradingagents.reporting import write_report_tree
from tradingagents.usage import UsageCallback, UsageStore, new_context

from .checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from .conditional_logic import ConditionalLogic
from .propagation import Propagator
from .setup import GraphSetup

logger = logging.getLogger(__name__)


def _merge_extracted(base, extracted):
    """Combine the state's own figures with the ones read from the reports.

    The state wins: a structured value a node wrote is authoritative, while a
    figure recovered from report text is a fallback for the fields no node
    fills. ``claimed_inputs`` is a union rather than a fallback — it names
    inputs that came from model prose, and losing it would re-trust a figure
    that is only an assertion.
    """
    if base is None:
        return extracted
    if extracted is None:
        return base
    updates = {}
    for name in base.__dataclass_fields__:
        if name == "claimed_inputs":
            merged = tuple(sorted(set(base.claimed_inputs or ())
                                  | set(extracted.claimed_inputs or ())))
            if merged != tuple(base.claimed_inputs or ()):
                updates[name] = merged
            continue
        current = getattr(base, name, None)
        if current is not None and current != "":
            continue
        found = getattr(extracted, name, None)
        if found is not None:
            updates[name] = found
    return replace(base, **updates) if updates else base


def _portfolio_sizing_inputs(config: dict, portfolio, ticker: str) -> dict:
    """The portfolio figures deterministic sizing needs (§5 of P3).

    Returns an empty dict when no book was supplied, which leaves ``equity`` and
    ``risk_budget`` as ``None`` — the signal the engine reads as "cannot size"
    rather than "size zero". That distinction is the whole of F4: the previous
    run passed nothing, the engine had no equity to cap against, and the audit
    recorded ``qty_proposed: null``.

    ``equity`` is deliberately not derived from ``cash``: the base an exposure
    cap is a fraction of is not the same number as the free balance.
    """
    if portfolio is None:
        return {}

    equity = getattr(portfolio, "equity", None)
    if not isinstance(equity, (int, float)) or isinstance(equity, bool) \
            or equity <= 0:
        # A book without equity is still not sizeable; the engine says so.
        return {"cash": getattr(portfolio, "cash", None)}

    inputs: dict = {
        "equity": float(equity),
        "cash": getattr(portfolio, "cash", None),
        "risk_budget": float(equity) * float(
            config.get("risk_per_trade_pct") or 0.01),
        "max_symbol_exposure": config.get("max_symbol_exposure") or 0.05,
    }

    # Existing exposure in this instrument, so the cap counts what is already
    # held instead of sizing as if the book were empty.
    try:
        held = portfolio.position_in(ticker)
    except Exception:  # noqa: BLE001 — an unreadable book is not a flat one
        held = None
    if held is not None and getattr(held, "quantity", 0):
        price = getattr(held, "average_price", None)
        if isinstance(price, (int, float)) and price > 0:
            inputs["existing_notional"] = abs(float(held.quantity)) * float(price)
    return inputs


def _validate_trade_date(trade_date) -> str:
    """The run date as a canonical ``YYYY-MM-DD`` string no later than today."""
    value = str(trade_date)
    try:
        canonical = datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") == value
    except ValueError:
        canonical = False
    if not canonical:
        raise ValueError(f"trade_date must be a date in YYYY-MM-DD format, got {trade_date!r}")
    if value > get_current_date():
        raise ValueError(f"trade_date cannot be in the future: {value}")
    return value


# Config keys that do not change what a run writes: where it keeps its files,
# whether it checkpoints, and how often it retries a provider.
_NOT_IN_SIGNATURE = frozenset({
    "results_dir", "data_cache_dir", "memory_log_path", "checkpoint_enabled", "llm_max_retries",
    "usage_db_path", "usage_run_id", "usage_source",
})


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

        set_config(self.config)

        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        self.usage_context = new_context(self.config)
        def metered_llm(tier):
            handler = UsageCallback(self.usage_context, tier_provider(self.config, tier),
                                    self.config[f"{tier}_think_llm"],
                                    UsageStore(self.config.get("usage_db_path")))
            return create_tier_client(self.config, tier,
                                      callbacks=[*self.callbacks, handler]).get_llm()
        self.deep_thinking_llm = metered_llm("deep")
        self.quick_thinking_llm = metered_llm("quick")

        self.memory_log = TradingMemoryLog(self.config)

        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        # An analyst takes two graph steps per tool round, plus its first turn
        # and its wrap-up; a limit past the recursion limit would end the run
        # there instead.
        max_tool_rounds, max_recur_limit = self.config["max_tool_rounds"], self.config["max_recur_limit"]
        if 2 * max_tool_rounds + 2 >= max_recur_limit:
            raise ValueError(
                f"max_tool_rounds={max_tool_rounds} needs max_recur_limit above {2 * max_tool_rounds + 2}"
            )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.conditional_logic,
            max_tool_rounds,
        )

        self.propagator = Propagator(
            max_recur_limit=max_recur_limit,
        )
        self.reflector = Reflector(self.quick_thinking_llm)

        # Graph-shape-affecting run choices, kept for the checkpoint signature.
        self.selected_analysts = tuple(selected_analysts)

        # Set up the graph: keep the workflow for recompilation with a checkpointer.
        self.workflow = self.graph_setup.setup_graph(selected_analysts, memory_node=self._memory_step)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None
        self._resuming = False

    def resolve_instrument_context(self, ticker: str, asset_type: str = "stock",
                                   trade_date: str | None = None) -> str:
        """Resolve ticker identity once and return the full instrument context.

        Deterministic yfinance lookup (cached, fail-open) injected into a
        context string so every agent anchors to the real company instead of
        hallucinating one from the price chart (#814). Both the propagate()
        path and the CLI call this so the resolved identity reaches the whole
        graph regardless of entry point.
        """
        identity = resolve_instrument_identity(ticker)
        return build_instrument_context(ticker, asset_type, identity, trade_date)

    def _memory_as_of(self, trade_date) -> str | None:
        """Point-in-time cutoff for past-context lessons (#1251).

        A historical/backtest run (trade date before today) filters lessons to
        those already resolved by the trade date. A current-date run returns
        None, disabling the filter so live behavior and pre-migration entries
        (which have no stored resolution date) are unaffected.
        """
        return str(trade_date) if is_historical(trade_date) else None

    def _run_signature(self, asset_type: str, portfolio=None) -> str:
        """Run inputs that must invalidate a checkpoint if changed.

        Keyed into the checkpoint thread ID so a resume under a different analyst
        selection, debate/risk depth, or asset mode starts fresh instead of
        silently continuing the previous graph (#1089). The rest of the config
        counts too (provider, models, endpoint, language, vendors, limits): a
        resume must not carry reports that other settings produced. Only where
        the run keeps its files and how it retries are left out.
        """
        settings = {k: v for k, v in self.config.items() if k not in _NOT_IN_SIGNATURE}
        digest = hashlib.sha256(json.dumps(settings, sort_keys=True, default=str).encode()).hexdigest()[:12]
        return "|".join([
            "analysts=" + ",".join(self.selected_analysts),
            f"debate={self.config['max_debate_rounds']}",
            f"risk={self.config['max_risk_discuss_rounds']}",
            f"asset={asset_type}",
            # None, an empty book and a changed book are three different runs.
            f"portfolio={portfolio.fingerprint() if portfolio is not None else 'none'}",
            # The layout itself: a checkpoint saved when analysts ran one after
            # another has pending nodes this graph no longer has, and one saved
            # before the Memory Log step would resume without the lessons.
            "analysts=parallel",
            "memory=parallel",
            f"settings={digest}",
        ])

    def propagate(self, company_name, trade_date, asset_type: str = "stock", portfolio=None):
        """Run the trading agents graph for a company on a specific date.

        ``asset_type`` selects between the stock pipeline (default) and the
        crypto pipeline (``"crypto"``) shipped in #567 — the CLI auto-detects
        from the ticker; programmatic callers pass it explicitly. When
        ``checkpoint_enabled`` is set in config, the graph is recompiled with
        a per-ticker SqliteSaver so a crashed run can resume from the last
        successful node on a subsequent invocation with the same ticker+date.

        Returns ``(final_state, signal)`` where ``signal`` is one of the 5-tier
        ratings (Buy / Overweight / Hold / Underweight / Sell) or ``"REVIEW"``
        when the decision had no parseable rating (#1170); guard with
        ``tradingagents.agents.rating.is_review`` before mapping it to the
        PortfolioRating enum.
        """
        trade_date = _validate_trade_date(trade_date)

        with run_config(self.config), \
                self.checkpoint_scope(company_name, trade_date, asset_type, portfolio) as thread_id_value:
            return self._run_graph(
                company_name, trade_date, asset_type=asset_type,
                checkpoint_thread_id=thread_id_value, portfolio=portfolio,
            )

    def begin_checkpoint(self, company_name, trade_date, asset_type: str = "stock", portfolio=None) -> str | None:
        """Recompile the graph with a per-ticker checkpointer and return the
        ``thread_id`` to inject into the stream/invoke ``config`` (or ``None``
        when checkpointing is disabled).

        Pair every call with :meth:`end_checkpoint` in a ``finally``. Both
        ``propagate`` (via :meth:`checkpoint_scope`) and the CLI stream path use
        this so ``--checkpoint`` actually resumes (#1249); previously the setup
        lived only inside ``propagate`` and the CLI streamed the checkpointer-less
        graph, making the flag a no-op.
        """
        self._resuming = False
        if not self.config.get("checkpoint_enabled"):
            return None
        signature = self._run_signature(asset_type, portfolio)
        self._checkpointer_ctx = get_checkpointer(self.config["data_cache_dir"], company_name)
        saver = self._checkpointer_ctx.__enter__()
        self.graph = self.workflow.compile(checkpointer=saver)

        step = checkpoint_step(
            self.config["data_cache_dir"], company_name, str(trade_date), signature
        )
        self._resuming = step is not None
        if step is not None:
            logger.info("Resuming from step %d for %s on %s", step, company_name, trade_date)
        else:
            logger.info("Starting fresh for %s on %s", company_name, trade_date)
        return thread_id(company_name, str(trade_date), signature)

    def checkpoint_input(self, init_state):
        """The value to stream/invoke: ``None`` to resume an existing checkpoint,
        else the initial state for a fresh run.

        LangGraph resumes an interrupted thread when invoked with ``None``;
        re-passing the initial state instead appends it through the message
        reducer, duplicating messages in the resumed state (#1249).
        """
        return None if self._resuming else init_state

    def end_checkpoint(self):
        """Restore the plain uncheckpointed graph after a checkpointed run."""
        if self._checkpointer_ctx is not None:
            self._checkpointer_ctx.__exit__(None, None, None)
            self._checkpointer_ctx = None
            self.graph = self.workflow.compile()
        self._resuming = False

    @contextmanager
    def checkpoint_scope(self, company_name, trade_date, asset_type: str = "stock", portfolio=None):
        """Context-manager form of begin/end_checkpoint for the propagate path."""
        try:
            yield self.begin_checkpoint(company_name, trade_date, asset_type, portfolio)
        finally:
            self.end_checkpoint()

    def clear_checkpoint_on_success(self, company_name, trade_date, asset_type: str = "stock", portfolio=None):
        """Drop a completed run's checkpoint so a later run starts fresh (#1249)."""
        if self.config.get("checkpoint_enabled"):
            clear_checkpoint(
                self.config["data_cache_dir"], company_name, str(trade_date),
                self._run_signature(asset_type, portfolio),
            )

    def run_settings(self) -> dict:
        """What produces this graph's runs, for the saved report and state log.

        An allowlist: endpoints (a backend_url can carry credentials), keys and
        local paths are never recorded.
        """
        cfg = self.config
        return {
            "version": tradingagents.__version__,
            "llm_provider": cfg.get("llm_provider"),
            "deep_think_provider": tier_provider(cfg, "deep") if cfg.get("llm_provider") else None,
            "deep_think_llm": cfg.get("deep_think_llm"),
            "quick_think_provider": tier_provider(cfg, "quick") if cfg.get("llm_provider") else None,
            "quick_think_llm": cfg.get("quick_think_llm"),
            "analysts": list(self.selected_analysts),
            "max_debate_rounds": cfg.get("max_debate_rounds"),
            "max_risk_discuss_rounds": cfg.get("max_risk_discuss_rounds"),
            "output_language": cfg.get("output_language"),
            "data_vendors": dict(cfg.get("data_vendors") or {}),
            "tool_vendors": dict(cfg.get("tool_vendors") or {}),
        }

    def save_reports(self, final_state, ticker, save_path=None, html=True) -> Path:
        """Write the report tree for a completed run, like the CLI does.

        Programmatic callers get the same on-disk reports the CLI produces. Pass
        an explicit ``save_path`` or let it default under ``results_dir``; the
        report is also written as one HTML page unless ``html`` is False.
        """
        if save_path is None:
            save_path = self.default_report_path(ticker)
        return write_report_tree(final_state, ticker, save_path, settings=self.run_settings(), html=html)

    def default_report_path(self, ticker) -> Path:
        """Where a run's reports go unless told otherwise: under results_dir, stamped now."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return Path(self.config["results_dir"]) / "reports" / f"{safe_ticker_component(ticker)}_{stamp}"

    def create_run_state(self, company_name, trade_date, asset_type: str = "stock", portfolio=None):
        """Build a run's initial state; propagate() and the CLI both start here.

        Injects the resolved instrument identity for every agent (#814). The
        memory log's lessons are not here: the graph's Memory Log step settles
        and loads them alongside the analysts (see ``_memory_step``).
        """
        trade_date = _validate_trade_date(trade_date)
        self.usage_context.update(new_context(self.config), ticker=company_name, analysis_date=trade_date)
        return self.propagator.create_initial_state(
            company_name,
            trade_date,
            asset_type=asset_type,
            instrument_context=self.resolve_instrument_context(company_name, asset_type, trade_date),
            portfolio_context=portfolio.render(company_name) if portfolio is not None else "",
        )

    def _memory_step(self, state):
        """The graph's Memory Log step, alongside the analysts (#1428): settle every
        ticker's due decisions (#1445), then return the lessons known by the
        trade date for the Portfolio Manager (#1251).

        Settling fetches prices and asks the model for a reflection per decision,
        so it runs beside the analysts instead of before them. A failure here
        does not end the run: the analysts' work is kept, the lessons already in
        the log are used, and the report says what could not be settled.
        """
        note = ""
        try:
            # Another run settling the same log does the work; this one goes on.
            done = self.settle_all_pending(wait=False)
            if done.failed:
                note = (f"{len(done.failed)} past decision(s) could not be settled this run "
                        "and stay pending.")
        except Exception as exc:
            logger.warning("Settling past decisions failed: %s", exc)
            note = f"Past decisions could not be settled this run ({type(exc).__name__}); they stay pending."
        try:
            past_context = self.memory_log.get_past_context(
                state["company_of_interest"], as_of=self._memory_as_of(state["trade_date"]))
        except Exception as exc:
            logger.warning("Reading the memory log failed: %s", exc)
            past_context = ""
            note = note or f"The memory log could not be read this run ({type(exc).__name__})."
        return {"past_context": past_context, "memory_note": note}

    def settle_pending(self, company_name) -> settlement.Settlement:
        """Settle this ticker's decisions whose holding window has now traded.

        A run settles every due decision alongside its analysts, so its own
        decision stays pending until a later run. A caller that is done
        analyzing a ticker (a backtest sweep, a scheduled job) calls this to
        settle it now. Returns what was settled and what failed.
        """
        with run_config(self.config):
            return settlement.settle_pending(company_name, self.memory_log, self.reflector, self.config)

    def settle_all_pending(self, wait: bool = True) -> settlement.Settlement:
        """Settle every ticker's decisions whose holding window has now traded (#1445).

        For a scheduler whose tickers rotate: a ticker it stops analysing would
        otherwise keep its decisions pending, and their lessons out of later runs.
        With ``wait=False`` a pass already running on the same log is not waited for.
        """
        with run_config(self.config):
            return settlement.settle_all_pending(self.memory_log, self.reflector, self.config, wait=wait)

    def record_decision(self, company_name, trade_date, final_state, portfolio=None):
        """Record a finished run: its state log, and its decision in the memory log
        for reflection on the next same-ticker run. propagate() and the CLI both end here.

        ``portfolio`` is the caller's book. It is what makes deterministic sizing
        possible at all (§5 of P3): the risk budget and the per-symbol exposure
        cap are fractions of the account's equity, so without a book the engine
        refuses to size rather than inventing one. An unknown book is never
        treated as a flat one.
        """
        self._log_state(trade_date, final_state)
        self._evaluate_reliability(company_name, trade_date, final_state,
                                   portfolio=portfolio)
        decision = final_state.get("final_trade_decision")
        if not decision:
            logger.warning("No final decision for %s on %s; nothing added to the memory log",
                           company_name, trade_date)
            return
        self.memory_log.store_decision(
            ticker=company_name, trade_date=trade_date, final_trade_decision=decision,
            rating=run_rating(final_state),
        )

    def _evaluate_reliability(self, company_name, trade_date, final_state,
                              portfolio=None):
        """Run the decision through the Execution Gate and write the audit.

        Best-effort by design: a reliability-layer failure must not lose the
        run's own reports or memory entry, so any exception is logged and
        skipped. The gate's verdict is attached to the state (execution_action)
        and the audit JSON lands beside the state log.

        The P0.1 fundamentals-freshness gate runs automatically: the filings
        known at the analysis date come from SEC EDGAR (point-in-time, no
        look-ahead) and the period the analyst used is read from the run's
        own fundamentals report. A non-US filer or an unreachable SEC yields
        no filings, and the gate reports FUNDAMENTALS_UNAVAILABLE rather
        than guessing — an extraction failure must not skip the gate, it
        must fail closed.
        """
        filings = self._known_filings(company_name, trade_date)
        used_end = used_period_end_from_report(
            final_state.get("fundamentals_report")
        )
        # §3: a registry belongs to THIS run. Built here, attached here,
        # discarded with the analysis — a process-wide one would let one
        # analysis certify another's figures.
        registry = self._build_metric_registry(company_name, trade_date,
                                               final_state)
        # §2 of P4: one id shared by the audit and the run record, minted once
        # per analysis so the two files can be matched and neither can collide
        # with another run of the same instrument on the same day.
        from tradingagents.dataflows import run_record as rr
        run_id = rr.new_run_id(company_name)
        try:
            record, decision = evaluate_decision(
                company_name, trade_date, final_state,
                snapshot_id=f"{company_name}-{trade_date}",
                model_versions={
                    "deep": self.config.get("deep_think_llm"),
                    "quick": self.config.get("quick_think_llm"),
                },
                fundamentals_filings=filings,
                used_fundamentals_period_end=used_end,
                metric_registry=registry,
                **_portfolio_sizing_inputs(self.config, portfolio, company_name),
            )
            attach_to_state(final_state, decision)
            attach_registry_status(final_state, registry)
            path = write_audit_record(record, self.config["results_dir"],
                                      run_id=run_id)
            logger.info("Reliability audit for %s on %s: %s -> %s",
                        company_name, trade_date, decision.action.value, path)
            # §2 of P4: the audit filename is stamped by analysis date, so two
            # analyses of one instrument on one day replace each other. The run
            # record is addressed by a unique id instead, and keeps everything
            # needed to reproduce the decision.
            self._write_run_record(company_name, trade_date, final_state,
                                   record, decision, registry, filings,
                                   portfolio, run_id)
        except Exception:  # noqa: BLE001 — the audit must never sink the run
            logger.exception("Reliability evaluation failed for %s on %s",
                             company_name, trade_date)

    def _write_run_record(self, company_name, trade_date, final_state,
                          audit_record, decision, registry, filings,
                          portfolio, run_id):
        """Persist this analysis under a unique id (§2 of P4).

        Separate from the audit file and deliberately so: the audit answers
        "was this decision sound", the run record answers "what exactly ran, on
        what inputs, with what code". Best-effort like the rest of the
        reliability layer — losing the record must not lose the analysis — but
        a failure is logged at error level rather than swallowed, because a run
        without a record is the finding, not a detail.
        """
        try:
            from tradingagents.dataflows import run_record as rr

            results_dir = self.config["results_dir"]
            snapshot = final_state.get("verified_market_snapshot")
            record = rr.RunRecord(
                run_id=run_id,
                ticker=company_name,
                analysis_date=trade_date,
                fingerprint=rr.runtime_fingerprint(),
                model_config=rr.model_config(self.config),
                inputs=rr.redact({
                    "market_snapshot": snapshot,
                    "portfolio": (portfolio.model_dump()
                                  if portfolio is not None else None),
                    "asset_type": final_state.get("asset_type"),
                }),
                filings=list(filings or []),
                metric_registry=(registry.summary()
                                 if registry is not None else {}),
                agents={
                    "market": final_state.get("market_report"),
                    "sentiment": final_state.get("sentiment_report"),
                    "news": final_state.get("news_report"),
                    "fundamentals": final_state.get("fundamentals_report"),
                    "research_plan": final_state.get("investment_plan"),
                    "trader_plan": final_state.get("trader_investment_plan"),
                },
                decision={
                    "report": final_state.get("final_trade_decision"),
                    "rating": final_state.get("final_rating"),
                    "execution_action": decision.action.value,
                    "reason_codes": [r.value for r in decision.reasons],
                    "execution_authorization": final_state.get(
                        "execution_authorization"),
                },
                risk=audit_record.to_dict().get("risk", {}),
                execution_gate=audit_record.to_dict().get("execution", {}),
                audit=audit_record.to_dict(),
            )
            path = rr.write_run(
                results_dir, record,
                max_text_chars=int(
                    self.config.get("run_record_max_text_chars") or 20_000))
            final_state["run_id"] = run_id
            final_state["run_record_path"] = str(path)
            logger.info("Run record for %s on %s: %s",
                        company_name, trade_date, path)

            # An explicit limit only. An audit that ages out unasked is not an
            # audit, so nothing is pruned unless the operator set a number.
            keep = self.config.get("run_record_keep")
            if isinstance(keep, int) and keep > 0:
                rr.prune_runs(results_dir, company_name, keep)
        except Exception:  # noqa: BLE001 — a record failure must not sink the run
            logger.error("Could not write the run record for %s on %s",
                         company_name, trade_date, exc_info=True)


    def _build_metric_registry(self, company_name: str, trade_date: str,
                               final_state: dict):
        """The certified metrics for this run (§3).

        Best-effort like the rest of the reliability layer: a failure here must
        not lose the run's reports, and the gate still sees ``None`` — which it
        reports as "nothing was checked" rather than as a pass.
        """
        try:
            from tradingagents.dataflows.math.extraction import (
                extract_run_inputs,
            )
            from tradingagents.dataflows.math.run_registry import (
                build_run_registry,
                registry_inputs_from_state,
            )

            # The labelled figures the reports actually state are read first
            # (F2/F3): `registry_inputs_from_state` alone reads only state
            # keys no node writes, so every valuation metric came out
            # NOT_COMPUTABLE and the model's own numbers were never checked.
            extracted = extract_run_inputs(final_state)
            inputs = registry_inputs_from_state(final_state)
            inputs = _merge_extracted(inputs, extracted.inputs)
            return build_run_registry(
                inputs, run_id=f"{company_name}-{trade_date}")
        except Exception:  # noqa: BLE001 — an unavailable registry is not a pass
            logger.debug("Could not build the metric registry for %s on %s",
                         company_name, trade_date, exc_info=True)
            return None

    def _known_filings(self, ticker: str, trade_date: str) -> list | None:
        """The authoritative filings known at the analysis date, point-in-time.

        Reads SEC EDGAR's cached companyfacts through the freshness module's
        extractor, which filters every filing to ``filed <= trade_date`` —
        a backtest never sees a filing the market had not seen. Best-effort:
        an unreachable SEC or a non-US filer yields an empty list, which the
        freshness gate reports as FUNDAMENTALS_UNAVAILABLE (fail-closed),
        never a guess. Returns None when the operator disabled the gate: the
        check is then not run at all, rather than run against nothing.
        """
        if not self.config.get("fundamentals_freshness_gate", True):
            return None
        try:
            return filings_from_sec_edgar(ticker, trade_date)
        except Exception:  # noqa: BLE001 — an extraction failure is UNAVAILABLE
            logger.debug("Could not extract filings for %s as of %s",
                         ticker, trade_date, exc_info=True)
            return []

    def _run_graph(self, company_name, trade_date, asset_type: str = "stock",
                   checkpoint_thread_id: str | None = None, portfolio=None):
        """Execute the graph and write the resulting state to disk and memory log."""
        init_agent_state = self.create_run_state(company_name, trade_date, asset_type, portfolio)
        args = self.propagator.get_graph_args()

        # Inject the checkpoint thread_id (from checkpoint_scope) so the same
        # ticker+date+graph-shape resumes; a different one starts fresh (#1089).
        if checkpoint_thread_id is not None:
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = checkpoint_thread_id

        # None resumes an existing checkpoint; init_agent_state starts fresh (#1249).
        graph_input = self.checkpoint_input(init_agent_state)
        if self.debug:
            # A state repeats the messages before it, so each prints once (#1027).
            final_state, printed = {}, set()
            for messages, state in self.stream_run(graph_input, **args):
                for msg in messages:
                    key = getattr(msg, "id", None) or (type(msg).__name__, getattr(msg, "content", None))
                    if key not in printed:
                        printed.add(key)
                        msg.pretty_print()
                if state is not None:
                    final_state.update(state)
        else:
            final_state = self.graph.invoke(graph_input, **args)

        self.record_decision(company_name, trade_date, final_state,
                             portfolio=portfolio)

        # Clear checkpoint on successful completion to avoid stale state.
        self.clear_checkpoint_on_success(company_name, trade_date, asset_type, portfolio)

        return final_state, run_rating(final_state)

    def stream_run(self, graph_input, **args):
        """Stream a run as ``(messages, state)`` pairs.

        ``messages`` are the agents' messages, the analysts' included. ``state``
        is the run's state after a top-level step; for a step inside an analyst's
        graph it is that analyst's report once filed, else None.

        Each analyst works in a graph of its own, and the run's state takes the
        analysts' reports only when the slowest has finished, so their messages
        and reports come from their own finished steps ("tasks") as they happen.
        """
        args = {**args, "stream_mode": ["values", "tasks"]}
        # The graph's own config serves every tool call, as in propagate(), even
        # when the process-wide config has changed since. Each step runs in the
        # run's context, so the caller keeps its own between steps.
        context = run_config_context(self.config)
        stream = context.run(self.graph.stream, graph_input, subgraphs=True, **args)
        try:
            while (step := context.run(next, stream, None)) is not None:
                namespace, mode, chunk = step
                if namespace:
                    result = chunk.get("result") if mode == "tasks" else None
                    if isinstance(result, dict):
                        report = {k: v for k, v in result.items() if k != "messages" and v}
                        if result.get("messages") or report:
                            yield result.get("messages", []), report or None
                elif mode == "values":
                    yield chunk.get("messages", []), chunk
        finally:
            context.run(stream.close)

    def _log_state(self, trade_date, final_state):
        """Write a run's final state to JSON under the run's own ticker."""
        entry = {
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
            },
            "trader_investment_plan": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
            "final_rating": run_rating(final_state),
            "run_settings": self.run_settings(),
        }

        # A ticker that would escape the results directory is rejected.
        safe_ticker = safe_ticker_component(final_state["company_of_interest"])
        directory = Path(self.config["results_dir"]) / safe_ticker / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            # Reports can be in any language and this file is read by a person.
            json.dump(entry, f, indent=4, ensure_ascii=False)
