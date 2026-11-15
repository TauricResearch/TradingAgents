"""Shared application entry: execute, check, finalize, and publish one run."""

from __future__ import annotations

import hashlib
import logging
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import tradingagents
from tradingagents.agents.rating import run_rating
from tradingagents.default_config import DEFAULT_CONFIG

from .checks import OutputChecker
from .context import ConsentState
from .events import EventSink
from .finalize import OutcomeFinalizer
from .persist import PersistenceError, publish_run
from .redact import Redactor
from .reporting import build_envelope, render_body, verify_envelope_header_matches
from .result import RunResult

logger = logging.getLogger(__name__)


def _source_revision() -> str:
    try:
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root,
                                capture_output=True, text=True, timeout=1, check=True)
        return f"git:{result.stdout.strip()}"
    except Exception:
        return "unknown"


def _prompt_hash(selected_analysts) -> str:
    root = Path(__file__).resolve().parents[1] / "agents"
    names = {
        "market": "analysts/market_analyst.py", "social": "analysts/sentiment_analyst.py",
        "news": "analysts/news_analyst.py", "fundamentals": "analysts/fundamentals_analyst.py",
    }
    files = {"agents/context.py", "agents/managers/research_manager.py",
             "agents/managers/portfolio_manager.py", "agents/trader/trader.py",
             "agents/researchers/bull_researcher.py", "agents/researchers/bear_researcher.py",
             "agents/risk_mgmt/aggressive_debator.py", "agents/risk_mgmt/conservative_debator.py",
             "agents/risk_mgmt/neutral_debator.py"}
    files.update(f"agents/{names[key]}" for key in selected_analysts if key in names)
    pairs = []
    for relative in sorted(files):
        path = root.parent / relative
        try:
            pairs.append((relative, path.read_text(encoding="utf-8")))
        except OSError:
            continue
    from .checks import DISCLAIMER, NO_PORTFOLIO_NOTICE
    pairs.extend([("frozen.disclaimer", DISCLAIMER), ("frozen.no_portfolio_notice", NO_PORTFOLIO_NOTICE)])
    material = "\n\n".join(f"{name}\n{text}" for name, text in sorted(pairs))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _effective_config(config: dict, graph=None) -> dict:
    try:
        settings = graph.run_settings() if graph and hasattr(graph, "run_settings") else {}
    except Exception as exc:
        logger.warning("Could not read graph run settings: %s", Redactor().diagnostic(exc))
        settings = {}
    def get(key, default=None):
        return settings.get(key, config.get(key, default))
    safe = {
        "llm_provider": get("llm_provider"),
        "deep_think_provider": get("deep_think_provider"),
        "deep_think_llm": get("deep_think_llm"),
        "quick_think_provider": get("quick_think_provider"),
        "quick_think_llm": get("quick_think_llm"),
        "analysts": list(get("analysts", config.get("selected_analysts", [])) or []),
        "max_debate_rounds": get("max_debate_rounds"),
        "max_risk_discuss_rounds": get("max_risk_discuss_rounds"),
        "output_language": get("output_language", "English"),
        "temperature": get("temperature"), "max_tokens": get("max_tokens"),
        "context_cap_tokens": int(get("context_cap_tokens", 24000)),
        "compaction_threshold_tokens": int(get("compaction_threshold_tokens", 19200)),
        "data_vendors": get("data_vendors", {}) or {},
        "tool_vendors": get("tool_vendors", {}) or {},
    }
    return Redactor().scrub(safe)


def _default_graph_factory(selected_analysts, config, callbacks=None):
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    return TradingAgentsGraph(selected_analysts, config=config, debug=False,
                              callbacks=callbacks or [])


def _default_engine_runner(graph, context, config):
    portfolio = context.portfolio_context()
    if hasattr(graph, "run_transient"):
        state, _rating = graph.run_transient(
            context.ticker, context.analysis_date,
            asset_type=config.get("asset_type", "stock"), portfolio=portfolio,
        )
        return state
    state, _rating = graph.propagate(
        context.ticker, context.analysis_date,
        asset_type=config.get("asset_type", "stock"), portfolio=portfolio,
    )
    return state


def run_analysis_api(
    run_context,
    *,
    config: dict | None = None,
    selected_analysts: list[str] | tuple[str, ...] | None = None,
    graph_factory: Callable[..., object] | None = None,
    event_sink: EventSink | None = None,
    redactor: Redactor | None = None,
    engine_runner: Callable | None = None,
    callbacks: list | None = None,
    html: bool = True,
    message_log_provider: Callable[[], str] | None = None,
) -> RunResult:
    """Run a confirmed context through the one supported app boundary.

    A custom ``engine_runner`` is intended for adapters such as the CLI live view;
    it cannot bypass output checking, finalization, redaction, or publication.
    """
    if run_context.consent_state != ConsentState.CONFIRMED:
        raise ValueError("run_analysis_api requires a confirmed RunContext")
    config = dict(config or DEFAULT_CONFIG)
    selected_analysts = list(selected_analysts or config.get("selected_analysts") or
                             ("market", "social", "news", "fundamentals"))
    redactor = redactor or Redactor()
    event_sink = event_sink or EventSink(run_context.run_id, run_context.ticker, redactor)
    checker = OutputChecker()
    finalizer = OutcomeFinalizer()
    start = datetime.now(UTC)
    event_sink.emit("input", "input.mode_resolved", run_context.mode.value)
    event_sink.emit("input", "input.consent", "CONFIRMED")
    event_sink.emit("engine", "run.started", "STARTED")

    graph = None
    final_state: dict = {}
    engine_error = None
    try:
        factory = graph_factory or _default_graph_factory
        graph = factory(selected_analysts=selected_analysts, config=config, callbacks=callbacks or [])
        runner = engine_runner or (lambda engine, context: _default_engine_runner(engine, context, config))
        final_state = runner(graph, run_context)
        if isinstance(final_state, tuple):
            final_state = final_state[0]
        if not isinstance(final_state, dict) or not final_state:
            raise RuntimeError("Analysis returned no usable final state.")
    except BaseException as exc:
        engine_error = exc

    trusted = run_context.safe_input_metadata()
    final_rating = run_rating(final_state) if engine_error is None else None
    try:
        body, parts = render_body(final_state, run_context, redactor)
    except Exception as exc:
        body, parts = render_body({}, run_context, redactor)
        if engine_error is None:
            engine_error = exc
            final_rating = None

    if engine_error is None:
        from .checks import render_provenance
        provenance_fragment = render_provenance(trusted)
        try:
            check = checker.evaluate(trusted, provenance_fragment, final_rating, body)
        except Exception as exc:
            check = checker.error_result(exc)
        event_sink.emit("output", "output.check", check.output_check)
        logical = finalizer.finalize(
            run_id=run_context.run_id, ticker=run_context.ticker,
            analysis_date=run_context.analysis_date, input_mode=run_context.mode.value,
            final_rating=final_rating, check_result=check,
        )
    else:
        check = None
        reason = finalizer.incomplete(
            run_id=run_context.run_id, ticker=run_context.ticker,
            analysis_date=run_context.analysis_date, input_mode=run_context.mode.value,
            reason=__import__("tradingagents.runapi.finalize", fromlist=["classify_exception"])
            .classify_exception(engine_error),
        )
        logical = reason
        diagnostic = redactor.diagnostic(engine_error)
        body = redactor.scrub(body + f"\n\nAnalysis stopped: {diagnostic}\n")

    if hasattr(final_state, "copy"):
        final_state = dict(final_state)
    state_for_html = dict(final_state or {})
    if logical.final_rating:
        state_for_html["final_rating"] = logical.final_rating
    state_for_html["trade_date"] = run_context.analysis_date
    envelope = build_envelope(
        trusted, logical.run_outcome, logical.stop_reason, logical.final_rating,
        logical.output_check, logical.findings, redactor,
    )
    if not verify_envelope_header_matches(envelope, trusted):
        logical = finalizer.incomplete(
            run_id=run_context.run_id, ticker=run_context.ticker,
            analysis_date=run_context.analysis_date, input_mode=run_context.mode.value,
            reason="INTERNAL_ERROR",
        )
        check = None
        envelope = build_envelope(trusted, "INCOMPLETE", "INTERNAL_ERROR", None,
                                  "NOT_RUN", (), redactor)

    settings = _effective_config(config, graph)
    selected_for_hash = settings.get("analysts") or selected_analysts
    end = datetime.now(UTC)
    manifest = {
        "schema_version": "1", **trusted,
        "run_outcome": logical.run_outcome, "stop_reason": logical.stop_reason,
        "final_rating": logical.final_rating, "output_check": logical.output_check,
        "findings": [finding.as_dict() for finding in logical.findings],
        "code_version": tradingagents.__version__, "source_revision": _source_revision(),
        "prompt_hash": _prompt_hash(selected_for_hash), "effective_config": settings,
        "start_ts_utc": start.isoformat().replace("+00:00", "Z"),
        "end_ts_utc": end.isoformat().replace("+00:00", "Z"),
    }
    final_state_for_html = state_for_html
    final_state_for_html["final_trade_decision"] = (
        final_state_for_html.get("final_trade_decision") or
        ("" if logical.run_outcome == "INCOMPLETE" else f"**Rating**: {logical.final_rating}")
    )
    try:
        html_report = None
        if html:
            from tradingagents.report_html import render_report
            html_report = render_report(
                run_context.ticker, final_state_for_html, settings, parts,
                body_markdown=body, run_metadata={**manifest, "findings": manifest["findings"]},
            )
        safe_state = dict(final_state or {})
        for forbidden in ("portfolio_context", "messages", "raw_prompt", "provider_payload"):
            safe_state.pop(forbidden, None)
        safe_state = redactor.scrub(safe_state)
        try:
            message_log = message_log_provider() if message_log_provider else None
        except Exception:
            message_log = None
            event_sink.emit("output", "message_log.capture", "BEST_EFFORT_FAILED")
        artifacts = publish_run(
            config.get("results_dir", DEFAULT_CONFIG["results_dir"]), run_context.ticker,
            run_context.run_id, envelope + body, html_report, manifest, event_sink, redactor,
            state_data=safe_state if safe_state else None, message_log=message_log,
            terminal_outcome=logical.run_outcome,
        )
        if logical.run_outcome == "COMPLETED" and graph is not None:
            decision = final_state.get("final_trade_decision")
            memory_log = getattr(graph, "memory_log", None)
            if decision and memory_log is not None and hasattr(memory_log, "store_decision"):
                try:
                    memory_log.store_decision(
                        ticker=run_context.ticker, trade_date=run_context.analysis_date,
                        final_trade_decision=redactor.scrub(decision), rating=logical.final_rating,
                    )
                except Exception as exc:
                    logger.warning("Decision memory could not be written: %s", redactor.diagnostic(exc))
            elif decision and hasattr(graph, "record_decision"):
                # Compatibility for graph adapters predating the memory-log
                # attribute; the in-tree graph takes the scoped path above.
                try:
                    graph.record_decision(run_context.ticker, run_context.analysis_date,
                                          {**final_state, "final_trade_decision": redactor.scrub(decision)})
                except Exception as exc:
                    logger.warning("Compatibility decision log could not be written: %s",
                                   redactor.diagnostic(exc))
        if logical.run_outcome == "COMPLETED" and graph is not None and hasattr(graph, "clear_checkpoint_on_success"):
            try:
                graph.clear_checkpoint_on_success(
                    run_context.ticker, run_context.analysis_date,
                    config.get("asset_type", "stock"), run_context.portfolio_context(),
                )
            except Exception as exc:
                logger.warning("Completed run checkpoint cleanup failed: %s", redactor.diagnostic(exc))
        return RunResult(
            logical.run_id, logical.ticker, logical.analysis_date, logical.input_mode,
            logical.run_outcome, logical.stop_reason, logical.final_rating,
            logical.output_check, logical.findings, str(artifacts.manifest_path),
            str(artifacts.report_path),
        )
    except PersistenceError:
        failed = finalizer.incomplete(
            run_id=run_context.run_id, ticker=run_context.ticker,
            analysis_date=run_context.analysis_date, input_mode=run_context.mode.value,
            reason="PERSISTENCE_ERROR",
        )
        return failed
    except Exception as exc:
        logger.warning("Run artifact rendering or publication failed: %s", redactor.diagnostic(exc))
        return finalizer.incomplete(
            run_id=run_context.run_id, ticker=run_context.ticker,
            analysis_date=run_context.analysis_date, input_mode=run_context.mode.value,
            reason="PERSISTENCE_ERROR",
        )
