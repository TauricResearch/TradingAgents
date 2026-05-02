"""Orchestration engine for LangGraph pipeline executions.

This module owns the run lifecycle (scan, pipeline, portfolio, auto)
and delegates event mapping, scanner-context assembly, and report
persistence to dedicated helper modules.
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from agent_os.backend.services.event_mapper import (
    EventMapper,
    is_root_chain_end,
    system_log,
)
from agent_os.backend.services.report_helpers import (
    extract_pipeline_instruments_from_scan_data,
    normalize_scan_summary,
    sanitize_for_json,
    write_complete_report_md,
)
from agent_os.backend.services.run_helpers import (
    analysis_has_deep_dive,
    analysis_is_terminal,
    analysis_status,
    build_fallback_config,
    build_resume_guidance,
    fallback_model_summary,
    fetch_prices,
    infer_fallback_tier,
    is_fallback_eligible_error,
    is_policy_error,
    normalize_analysis_status,
    repair_checkpoint_messages,
    resolve_tier_model_provider,
    run_should_stop,
    tickers_from_decision,
)
from agent_os.backend.services.scanner_context import build_scanner_context_packet
from tradingagents.agents.utils.circuit_breaker import CircuitBreakerOpen
from tradingagents.agents.utils.json_utils import extract_json
from tradingagents.agents.utils.output_validation import build_market_report_structured
from tradingagents.daily_digest import append_to_digest
from tradingagents.dataflows.vendor_health import check_vendor_health
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.portfolio_graph import PortfolioGraph
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.scanner_facts.builder import (
    ensure_scanner_graph_facts,
    load_scanner_graph_facts,
)
from tradingagents.graph.scanner_facts.render import render_ticker_graph_context
from tradingagents.graph.scanner_graph import ScannerGraph
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.instruments import (
    CanonicalInstrument,
    is_equity_pipeline_supported,
    resolve_instrument,
)
from tradingagents.observability import RunLogger, set_run_logger
from tradingagents.portfolio.report_store import ReportStore
from tradingagents.portfolio.store_factory import create_report_store
from tradingagents.report_paths import (
    REPORTS_ROOT,
    get_daily_dir,
    get_market_dir,
    get_scanner_graph_facts_path,
    get_ticker_dir,
)

logger = logging.getLogger("agent_os.engine")

_REGIME_LABEL_RE = re.compile(r"\b(RISK-ON|RISK-OFF|TRANSITION)\b", re.IGNORECASE)
_REGIME_SCORE_RE = re.compile(r"(?:\(\s*|score\s+(?:of\s+)?)?([+-]?\d+)\s*/\s*6", re.IGNORECASE)
_SCAN_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ------------------------------------------------------------------
# Module-level helpers (formerly @staticmethod on the class)
# ------------------------------------------------------------------


def _root_run_id(run_id: str, params: dict[str, Any]) -> str:
    return params.get("run_id") or run_id


def _execution_key(run_id: str, params: dict[str, Any]) -> str:
    return params.get("_execution_key") or run_id


def _load_injected_market_report(file_path: str) -> dict[str, Any]:
    """Load a saved market report artifact for pipeline injection.

    Supports:
    - plain-text/markdown files containing only the market report
    - JSON artifacts with a top-level ``market_report`` key and optional
      ``macro_regime_report`` key
    - macro-scan JSON payloads that are already structured market summaries

    The resolved path must be within REPORTS_ROOT or the current working
    directory to prevent path-traversal attacks.
    """
    path = Path(str(file_path)).expanduser().resolve()

    # Guard against path traversal — only allow files under the reports
    # root or the working directory.
    allowed_bases = [REPORTS_ROOT.resolve(), Path.cwd().resolve()]
    if not any(path == base or base in path.parents for base in allowed_bases):
        raise PermissionError(f"Injected market report path escapes allowed directories: {path}")

    if not path.exists():
        raise FileNotFoundError(f"Injected market report file not found: {path}")

    raw_text = path.read_text(encoding="utf-8").strip()
    if not raw_text:
        raise ValueError(f"Injected market report file is empty: {path}")

    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Injected market report JSON is malformed: {path} ({e})") from e
        if not isinstance(payload, dict):
            raise ValueError(f"Injected market report JSON must be an object: {path}")
        market_report = str(payload.get("market_report") or "").strip()
        macro_regime_report = str(payload.get("macro_regime_report") or "").strip()
        if not market_report and any(
            key in payload
            for key in ("timeframe", "executive_summary", "key_themes", "stocks_to_investigate")
        ):
            market_report = json.dumps(payload, ensure_ascii=False)
        if not market_report:
            raise ValueError(
                f"Injected market report JSON missing non-empty 'market_report': {path}"
            )
        return {
            "market_report": market_report,
            "macro_regime_report": macro_regime_report,
            "market_report_structured": build_market_report_structured(
                ticker="",
                as_of_date="",
                market_report=market_report,
                macro_regime_report=macro_regime_report,
            ),
        }

    return {
        "market_report": raw_text,
        "macro_regime_report": "",
        "market_report_structured": {},
    }


def _parse_canonical_regime(macro_brief: str) -> dict[str, Any]:
    text = str(macro_brief or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("canonical_regime"), dict):
        canonical = payload["canonical_regime"]
        label = str(canonical.get("label") or "").strip().upper()
        score = canonical.get("score")
        confidence = str(canonical.get("confidence") or "").strip().lower()
        if label not in {"RISK-ON", "RISK-OFF", "TRANSITION"}:
            raise ValueError("structured canonical_regime has invalid label")
        if isinstance(score, bool) or not isinstance(score, int) or score < -6 or score > 6:
            raise ValueError("structured canonical_regime has invalid score")
        parsed: dict[str, Any] = {
            "label": label,
            "score": score,
            "brief": text,
        }
        if confidence:
            if confidence not in {"high", "medium", "low"}:
                raise ValueError("structured canonical_regime has invalid confidence")
            parsed["confidence"] = confidence
        return parsed
    label_match = _REGIME_LABEL_RE.search(text)
    score_match = _REGIME_SCORE_RE.search(text)
    if not label_match or not score_match:
        raise ValueError("canonical macro regime could not be parsed from macro brief")
    return {
        "label": label_match.group(1).upper(),
        "score": int(score_match.group(1)),
        "brief": text,
    }


def _resolve_macro_brief(sources: list[str]) -> str:
    """Return the first source _parse_canonical_regime can parse, else the first non-empty source."""
    first_nonempty = ""
    for src in sources:
        text = str(src or "").strip()
        if not text:
            continue
        if not first_nonempty:
            first_nonempty = text
        try:
            _parse_canonical_regime(text)
            return text
        except ValueError:
            continue
    return first_nonempty


def _require_scanner_date(params: dict[str, Any], *, run_kind: str) -> str:
    date = str(params.get("date") or "").strip()
    if not date:
        raise ValueError(f"{run_kind} requires explicit date (YYYY-MM-DD); no wall-clock fallback.")
    if not _SCAN_DATE_RE.fullmatch(date):
        raise ValueError(f"{run_kind} date must be YYYY-MM-DD, got {date!r}.")
    try:
        parsed = datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{run_kind} date must be YYYY-MM-DD, got {date!r}.") from exc
    if parsed.strftime("%Y-%m-%d") != date:
        raise ValueError(f"{run_kind} date must be YYYY-MM-DD, got {date!r}.")
    return date


def _build_trading_graph_initial_state(
    *,
    ticker: str,
    analysis_date: str,
    run_id: str,
    macro_brief: str = "",
    portfolio_context: str = "candidate",
    scanner_context_packet: str = "",
    scanner_graph_context_text: str = "",
    market_report: str = "",
    market_report_structured: dict[str, Any] | None = None,
    macro_regime_report: str = "",
) -> dict[str, Any]:
    return Propagator().create_initial_state(
        ticker,
        analysis_date,
        run_id=run_id,
        portfolio_context=portfolio_context,
        scanner_context_packet=scanner_context_packet,
        scanner_graph_context_text=scanner_graph_context_text,
        canonical_regime=_parse_canonical_regime(macro_brief),
        market_report=market_report,
        market_report_structured=market_report_structured,
        macro_regime_report=macro_regime_report,
    )


class AwaitPhase3Decision(RuntimeError):
    """Raised when auto mode must pause for a user decision before Phase 3."""

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        incomplete = payload.get("incomplete_tickers") or []
        summary = (
            ", ".join(
                f"{item.get('ticker')} ({item.get('reason')})"
                for item in incomplete
                if isinstance(item, dict)
            )
            or "unknown ticker state"
        )
        super().__init__(f"Ticker analyses require a decision before Phase 3: {summary}")


NODE_TO_PHASE = {
    # Phase analysts: re-run full pipeline from scratch
    "Market Analyst": "analysts",
    "Social Analyst": "analysts",
    "News Analyst": "analysts",
    "Fundamentals Analyst": "analysts",
    # Phase debate_and_trader: load analysts_checkpoint, skip analysts
    "Bull Researcher": "debate_and_trader",
    "Bear Researcher": "debate_and_trader",
    "Research Manager": "debate_and_trader",
    "Trader": "debate_and_trader",
    # Phase risk: load trader_checkpoint, skip analysts+debate+trader
    "Aggressive Analyst": "risk",
    "Conservative Analyst": "risk",
    "Neutral Analyst": "risk",
    "Portfolio Manager": "risk",
}

SCAN_NODE_TO_REPORT_FIELD = {
    "gatekeeper_scanner": "gatekeeper_universe_report",
    "geopolitical_scanner": "geopolitical_report",
    "market_movers_scanner": "market_movers_report",
    "sector_scanner": "sector_performance_report",
    "factor_alignment_scanner": "factor_alignment_report",
    "drift_scanner": "drift_opportunities_report",
    "smart_money_scanner": "smart_money_report",
    "industry_deep_dive": "industry_deep_dive_report",
    "macro_synthesis": "macro_scan_summary",
    # Summaries
    "summarize_gatekeeper": "gatekeeper_summary",
    "summarize_geopolitical": "geopolitical_summary",
    "summarize_market_movers": "market_movers_summary",
    "summarize_sector": "sector_summary",
    "summarize_factor_alignment": "factor_alignment_summary",
    "summarize_drift": "drift_opportunities_summary",
    "summarize_smart_money": "smart_money_summary",
    "summarize_industry_deep_dive": "industry_deep_dive_summary",
}
# Keys checked when saving analyst checkpoints
_ANALYST_KEYS = ("market_report", "sentiment_report", "news_report", "fundamentals_report")

_PIPELINE_ANALYST_PHASE_NODES = frozenset(
    {
        "Instrument Preflight",
        "Market Analyst",
        "Social Analyst",
        "News Analyst",
        "Fundamentals Analyst",
        "News Fact Checker",
        "Msg Clear Market",
        "Msg Clear Social",
        "Msg Clear News",
        "Msg Clear Fundamentals",
    }
)

_RESUMABLE_PIPELINE_STATE_KEYS = frozenset(
    {
        "run_id",
        "company_of_interest",
        "trade_date",
        "portfolio_context",
        "instrument_key",
        "asset_class",
        "instrument_type",
        "is_etf",
        "is_inverse",
        "is_leveraged",
        "scanner_context_packet",
        "sender",
        "market_report",
        "market_report_structured",
        "sentiment_report",
        "sentiment_report_structured",
        "news_report",
        "news_report_structured",
        "fundamentals_report",
        "fundamentals_report_structured",
        "research_packet_summary",
        "investment_debate_state",
        "investment_plan",
        "investment_plan_structured",
        "trader_investment_plan",
        "trader_plan_structured",
        "risk_debate_state",
        "risk_r1_aggressive",
        "risk_r1_conservative",
        "risk_r1_neutral",
        "risk_r2_aggressive",
        "risk_r2_conservative",
        "risk_r2_neutral",
        "final_trade_decision",
        "final_trade_decision_structured",
        "risk_synthesis_structured",
        "analysis_status",
        "terminal_action",
        "abort_signal",
        "macro_regime_report",
    }
)

_PIPELINE_NODE_RESULT_FIELDS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "research_packet_summary",
    "investment_debate_state",
    "investment_plan",
    "trader_investment_plan",
    "risk_debate_state",
    "risk_r1_aggressive",
    "risk_r1_conservative",
    "risk_r1_neutral",
    "risk_r2_aggressive",
    "risk_r2_conservative",
    "risk_r2_neutral",
    "final_trade_decision",
    "analysis_status",
    "terminal_action",
    "abort_signal",
)

_PORTFOLIO_NODE_RESULT_FIELDS = (
    "portfolio_data",
    "risk_metrics",
    "holding_reviews",
    "prioritized_candidates",
    "macro_brief",
    "micro_brief",
    "pm_decision",
    "cash_sweep",
    "execution_result",
)


def _extract_node_results(
    state: dict[str, Any],
    fields: tuple[str, ...],
) -> dict[str, Any]:
    """Return a compact node-results payload with non-empty values only."""
    return {
        field: state[field]
        for field in fields
        if field in state and state[field] not in (None, "", [], {})
    }


class PipelineRecoveryStore(Protocol):
    def save_pipeline_node_snapshot(
        self,
        date: str,
        ticker: str,
        data: dict[str, Any],
    ) -> Any: ...

    def save_analysts_checkpoint(
        self,
        date: str,
        ticker: str,
        data: dict[str, Any],
    ) -> Any: ...

    def save_trader_checkpoint(
        self,
        date: str,
        ticker: str,
        data: dict[str, Any],
    ) -> Any: ...

    def load_latest_pipeline_node_snapshot(
        self,
        date: str,
        ticker: str,
    ) -> dict[str, Any] | None: ...


def _is_top_level_langgraph_node_end(event: dict[str, Any]) -> bool:
    """Return True for terminal events emitted by top-level LangGraph nodes."""
    if event.get("event") != "on_chain_end":
        return False
    metadata = event.get("metadata") or {}
    if not metadata.get("langgraph_node"):
        return False
    return len(event.get("parent_ids", [])) == 1


def _build_analysts_checkpoint(
    state: dict[str, Any],
    *,
    ticker: str,
    date: str,
) -> dict[str, Any] | None:
    """Return the persisted analysts checkpoint payload when analyst output exists."""
    if not any(state.get(key) for key in _ANALYST_KEYS):
        return None
    return {
        "company_of_interest": ticker,
        "trade_date": date,
        **{key: state.get(key, "") for key in _ANALYST_KEYS},
        "market_report_structured": state.get("market_report_structured", {}),
        "news_report_structured": state.get("news_report_structured", {}),
        "fundamentals_report_structured": state.get("fundamentals_report_structured", {}),
        "macro_regime_report": state.get("macro_regime_report", ""),
        "portfolio_context": state.get("portfolio_context", "candidate"),
        "messages": state.get("messages", []),
    }


def _build_trader_checkpoint(
    state: dict[str, Any],
    *,
    ticker: str,
    date: str,
) -> dict[str, Any] | None:
    """Return the persisted trader checkpoint payload when trader output exists."""
    if not state.get("trader_investment_plan"):
        return None
    return {
        "company_of_interest": ticker,
        "trade_date": date,
        **{key: state.get(key, "") for key in _ANALYST_KEYS},
        "market_report_structured": state.get("market_report_structured", {}),
        "news_report_structured": state.get("news_report_structured", {}),
        "fundamentals_report_structured": state.get("fundamentals_report_structured", {}),
        "macro_regime_report": state.get("macro_regime_report", ""),
        "portfolio_context": state.get("portfolio_context", "candidate"),
        "investment_debate_state": state.get("investment_debate_state", {}),
        "investment_plan": state.get("investment_plan", ""),
        "trader_investment_plan": state.get("trader_investment_plan", ""),
        "messages": state.get("messages", []),
    }


def infer_pipeline_resume_phase(snapshot: dict[str, Any] | None) -> str | None:
    """Infer the earliest safe pipeline phase to resume from a saved snapshot."""
    if not isinstance(snapshot, dict):
        return None

    state = snapshot.get("state")
    if not isinstance(state, dict):
        state = {}

    status = normalize_analysis_status(state)
    if status in {"completed", "aborted"}:
        return None

    node_name = str(snapshot.get("node_name") or "").strip()
    if node_name in _PIPELINE_ANALYST_PHASE_NODES:
        return "analysts"
    if str(state.get("trader_investment_plan") or "").strip():
        return "risk"
    if any(str(state.get(key) or "").strip() for key in _ANALYST_KEYS):
        return "debate_and_trader"
    return "analysts"


def _apply_resume_state(
    initial_state: dict[str, Any],
    snapshot_state: dict[str, Any],
) -> dict[str, Any]:
    """Merge the resumable subset of a saved snapshot into an initial pipeline state."""
    for key in _RESUMABLE_PIPELINE_STATE_KEYS:
        if key in snapshot_state:
            initial_state[key] = snapshot_state[key]
    return initial_state


class LangGraphEngine:
    """Orchestrates LangGraph pipeline executions and streams events."""

    def __init__(self) -> None:
        self.config: dict[str, Any] = DEFAULT_CONFIG.copy()
        self.active_runs: dict[str, dict[str, Any]] = {}
        self._event_mapper = EventMapper(
            node_wall_clock_budget_sec=self.config.get("node_wall_clock_budget_sec")
        )
        self._run_loggers: dict[str, RunLogger] = {}

    def _persist_pipeline_recovery_artifacts(
        self,
        *,
        store: PipelineRecoveryStore,
        date: str,
        ticker: str,
        state: dict[str, Any],
        node_name: str,
    ) -> None:
        """Persist the latest resumable pipeline snapshot and derived checkpoints."""
        serializable_state = sanitize_for_json(state)
        snapshot = {
            "ticker": ticker,
            "trade_date": date,
            "node_name": node_name,
            "resume_phase": infer_pipeline_resume_phase(
                {"node_name": node_name, "state": serializable_state}
            ),
            "analysis_status": normalize_analysis_status(serializable_state),
            "state": serializable_state,
        }
        store.save_pipeline_node_snapshot(date, ticker, snapshot)

        analysts_ckpt = _build_analysts_checkpoint(serializable_state, ticker=ticker, date=date)
        if analysts_ckpt:
            store.save_analysts_checkpoint(date, ticker, analysts_ckpt)

        trader_ckpt = _build_trader_checkpoint(serializable_state, ticker=ticker, date=date)
        if trader_ckpt:
            store.save_trader_checkpoint(date, ticker, trader_ckpt)

    def _maybe_persist_pipeline_recovery_artifacts(
        self,
        *,
        event: dict[str, Any],
        current_state: dict[str, Any],
        store: PipelineRecoveryStore,
        date: str,
        ticker: str,
        root_run_id: str,
        error_context: str,
    ) -> None:
        """Update the rolling pipeline snapshot from a top-level LangGraph node event."""
        if not _is_top_level_langgraph_node_end(event):
            return
        output = (event.get("data") or {}).get("output")
        if not isinstance(output, dict):
            return
        current_state.update(output)
        try:
            self._persist_pipeline_recovery_artifacts(
                store=store,
                date=date,
                ticker=ticker,
                state=current_state,
                node_name=str((event.get("metadata") or {}).get("langgraph_node") or "unknown"),
            )
        except Exception:
            logger.exception(
                "Failed to persist %s snapshot run=%s ticker=%s",
                error_context,
                root_run_id,
                ticker,
            )

    # ------------------------------------------------------------------
    # Run logger lifecycle
    # ------------------------------------------------------------------

    def _start_run_logger(self, run_id: str, *, logger_key: str | None = None) -> RunLogger:
        """Create and register a ``RunLogger`` for the given canonical run id."""
        uri = self.config.get("mongo_uri")
        db = self.config.get("mongo_db") or "tradingagents"
        rl = RunLogger(run_id=run_id, mongo_uri=uri, mongo_db=db)
        self._run_loggers[logger_key or run_id] = rl
        set_run_logger(rl)
        return rl

    def _finish_run_logger(self, logger_key: str, log_dir: Path) -> None:
        """Persist the run log to *log_dir*/run_log.jsonl and clean up."""
        rl = self._run_loggers.pop(logger_key, None)
        if rl is None:
            return
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            rl.write_log(log_dir / "run_log.jsonl")
        except Exception:
            logger.exception("Failed to write run log for logger_key=%s", logger_key)
        finally:
            set_run_logger(None)

    def _configure_runtime_guards(self) -> None:
        self._event_mapper.node_wall_clock_budget_sec = self.config.get(
            "node_wall_clock_budget_sec"
        )

    def _vendor_health_warning_events(
        self,
        *,
        critical_methods: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        if not self.config.get("vendor_health_probes_enabled", True):
            return []
        events: list[dict[str, Any]] = []
        for warning in check_vendor_health(self.config, critical_methods=critical_methods):
            logger.warning("Vendor health degraded: %s", warning)
            events.append(
                {
                    "id": f"vendor_health_{time.time_ns()}",
                    "node_id": "__system__",
                    "type": "warning",
                    "agent": "SYSTEM",
                    "message": (
                        "Vendor health warning: "
                        f"{warning['method']} via {warning['vendor']} degraded "
                        f"({warning['reason']})"
                    ),
                    "warning": warning,
                    "metrics": {},
                }
            )
        return events

    def _failure_node_for(self, execution_key: str, exc: Exception | None = None) -> str | None:
        return (
            getattr(exc, "node_name", None)
            if exc is not None and getattr(exc, "node_name", None)
            else self._event_mapper.failure_node(execution_key)
        )

    # ------------------------------------------------------------------
    # Run helpers
    # ------------------------------------------------------------------

    async def run_scan(
        self, run_id: str, params: dict[str, Any]
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run the 3-phase macro scanner and stream events."""
        date = _require_scanner_date(params, run_kind="run_scan")
        root_run_id = _root_run_id(run_id, params)
        execution_key = _execution_key(run_id, params)
        store = create_report_store(run_id=root_run_id)

        rl = self._start_run_logger(root_run_id, logger_key=execution_key)
        scan_config = {**self.config}
        if params.get("max_tickers"):
            scan_config["max_auto_tickers"] = int(params["max_tickers"])
        scanner = ScannerGraph(config=scan_config)

        logger.info("Starting SCAN run=%s date=%s", root_run_id, date)
        yield system_log(f"Starting macro scan for {date}")
        self._configure_runtime_guards()
        for warning_event in self._vendor_health_warning_events(
            critical_methods=(
                "get_market_movers",
                "get_market_indices",
                "get_sector_performance",
                "get_industry_performance",
                "get_topic_news",
                "get_earnings_calendar",
            )
        ):
            yield warning_event

        initial_state = self._load_scan_state(root_run_id=root_run_id, date=date, store=store)
        # Ensure graph-required fields are present
        initial_state.setdefault("messages", [])
        initial_state.setdefault("sender", "")
        initial_state.setdefault("run_id", root_run_id)

        # Initialize missing report fields to empty strings for safety
        for key in SCAN_NODE_TO_REPORT_FIELD.values():
            initial_state.setdefault(key, "")
        initial_state.setdefault("macro_scan_summary", "")

        self._event_mapper.register_run(execution_key, "MARKET")
        final_state: dict[str, Any] = {}
        captured_root_state = False

        # Hard ceiling for the full scan.  A LangGraph fan-in deadlock (e.g. one
        # Phase-1a scanner returning an empty report) causes astream_events to hang
        # indefinitely without raising an exception.  The timeout converts that silent
        # hang into a RuntimeError so _run_and_store marks the run "failed" and
        # persists run_meta.json — rather than leaving it stuck at "running" forever.
        _scan_timeout = float(self.config.get("scan_timeout_seconds") or 1800)  # 30 min

        try:
            try:
                async with asyncio.timeout(_scan_timeout):
                    async for event in scanner.graph.astream_events(
                        initial_state, version="v2", config={"callbacks": [rl.callback]}
                    ):
                        if run_should_stop(root_run_id):
                            logger.info(
                                "SCAN run=%s: graceful stop requested, aborting early", root_run_id
                            )
                            yield system_log("Aborting macro scan due to graceful stop request.")
                            raise asyncio.CancelledError()

                        # Capture the complete final state from the root graph's terminal event.
                        # LangGraph v2 emits one root-level on_chain_end (parent_ids=[], no
                        # langgraph_node in metadata) whose data.output is the full
                        # accumulated state.
                        if is_root_chain_end(event):
                            output = (event.get("data") or {}).get("output")
                            if isinstance(output, dict):
                                captured_root_state = True
                                final_state = output
                        mapped = self._event_mapper.map_event(execution_key, event)
                        if mapped:
                            yield mapped
            except TimeoutError:
                msg = (
                    f"Macro scan timed out after {_scan_timeout:.0f}s — "
                    "likely a LangGraph fan-in deadlock caused by a scanner node "
                    "returning an empty report. Resume from the last completed Phase-1a node."
                )
                logger.error("SCAN run=%s: %s", root_run_id, msg)
                yield system_log(f"Error: {msg}")
                raise RuntimeError(msg) from None
            except Exception as exc:
                failing_node = self._failure_node_for(execution_key, exc)
                guidance = build_resume_guidance(
                    run_kind="scan",
                    failing_node=failing_node,
                    identifier=date,
                )
                logger.exception(
                    "SCAN run=%s failed at node=%s", root_run_id, failing_node or "unknown"
                )
                yield system_log(f"Error: {exc}. {guidance}")
                raise

            if not captured_root_state:
                message = (
                    f"Scan for {date} completed without a root final state; "
                    "refusing to re-run the graph because that can duplicate expensive work."
                )
                logger.error("SCAN run=%s: %s", root_run_id, message)
                yield system_log(f"Error: {message}")
                raise RuntimeError(message)

            if final_state:
                async for evt in self._save_scan_outputs(final_state, date, root_run_id, store):
                    yield evt

            logger.info("Completed SCAN run=%s", root_run_id)
        finally:
            self._event_mapper.unregister_run(execution_key)
            self._finish_run_logger(execution_key, get_market_dir(date, root_run_id))

    async def _save_scan_outputs(
        self,
        final_state: dict[str, Any],
        date: str,
        root_run_id: str,
        store: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Persist scan artifacts and emit system log events."""
        yield system_log("Saving scan reports…")
        try:
            save_dir = get_market_dir(date, root_run_id)
            save_dir.mkdir(parents=True, exist_ok=True)

            for key in SCAN_NODE_TO_REPORT_FIELD.values():
                content = final_state.get(key, "")
                if content:
                    (save_dir / f"{key}.md").write_text(content)

            summary_text = final_state.get("macro_scan_summary", "")
            if summary_text:
                try:
                    summary_data = normalize_scan_summary(extract_json(summary_text))
                    store.save_scan(date, summary_data)
                    # Write flat JSON for scanner_graph_facts builder
                    (save_dir / "macro_scan_summary.json").write_text(
                        json.dumps(summary_data, indent=2, sort_keys=True)
                    )
                except (ValueError, KeyError, TypeError):
                    logger.warning(
                        "macro_scan_summary for date=%s is not valid JSON "
                        "(summary already saved as .md — downstream loads may fail)",
                        date,
                    )

            scan_parts = []
            for key, label in (
                ("geopolitical_report", "Geopolitical & Macro"),
                ("market_movers_report", "Market Movers"),
                ("sector_performance_report", "Sector Performance"),
                ("industry_deep_dive_report", "Industry Deep Dive"),
                ("macro_scan_summary", "Macro Scan Summary"),
            ):
                content = final_state.get(key, "")
                if content:
                    scan_parts.append(f"### {label}\n{content}")
            if scan_parts:
                append_to_digest(date, "scan", "Market Scan", "\n\n".join(scan_parts))

            yield system_log(f"Scan reports saved to {save_dir}")
            logger.info("Saved scan reports run=%s date=%s dir=%s", root_run_id, date, save_dir)

            # Build scanner graph facts — fail loud on error (do NOT catch)
            graph_facts_path = ensure_scanner_graph_facts(scan_date=date, run_id=root_run_id)
            yield system_log(f"Scanner graph facts built: {graph_facts_path.name}")
            logger.info("Scanner graph facts built run=%s path=%s", root_run_id, graph_facts_path)
        except Exception as exc:
            logger.exception("Failed to save scan reports run=%s", root_run_id)
            yield system_log(f"Warning: could not save scan reports: {exc}")

    async def run_scan_from_node(
        self,
        run_id: str,
        params: dict[str, Any],
        start_node: str,
        initial_state: dict[str, Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Continue a market scan from *start_node* using a seeded state."""
        if start_node not in SCAN_NODE_TO_REPORT_FIELD:
            yield system_log(f"Unknown scan node '{start_node}' — skipping")
            return

        date = _require_scanner_date(params, run_kind="run_scan_from_node")
        root_run_id = _root_run_id(run_id, params)
        execution_key = _execution_key(run_id, params)
        store = create_report_store(run_id=root_run_id)

        rl = self._start_run_logger(root_run_id, logger_key=execution_key)
        scan_config = {**self.config}
        if params.get("max_tickers"):
            scan_config["max_auto_tickers"] = int(params["max_tickers"])
        scanner = ScannerGraph(config=scan_config)
        graph = scanner.graph_from(start_node)

        logger.info("Starting SCAN rerun run=%s node=%s date=%s", root_run_id, start_node, date)
        yield system_log(f"Continuing macro scan from {start_node} for {date}")
        self._configure_runtime_guards()
        for warning_event in self._vendor_health_warning_events(
            critical_methods=(
                "get_market_movers",
                "get_market_indices",
                "get_sector_performance",
                "get_industry_performance",
                "get_topic_news",
                "get_earnings_calendar",
            )
        ):
            yield warning_event

        seeded_state = {
            "scan_date": date,
            "messages": [],
            "gatekeeper_universe_report": "",
            "geopolitical_report": "",
            "market_movers_report": "",
            "sector_performance_report": "",
            "factor_alignment_report": "",
            "drift_opportunities_report": "",
            "smart_money_report": "",
            "industry_deep_dive_report": "",
            "macro_scan_summary": "",
            "sender": "",
            **initial_state,
        }
        seeded_state["scan_date"] = date
        seeded_state["run_id"] = root_run_id

        self._event_mapper.register_run(execution_key, "MARKET")
        final_state: dict[str, Any] = {}
        captured_root_state = False

        _scan_timeout = float(self.config.get("scan_timeout_seconds") or 1800)  # 30 min

        try:
            try:
                async with asyncio.timeout(_scan_timeout):
                    async for event in graph.astream_events(
                        seeded_state, version="v2", config={"callbacks": [rl.callback]}
                    ):
                        if is_root_chain_end(event):
                            output = (event.get("data") or {}).get("output")
                            if isinstance(output, dict):
                                captured_root_state = True
                                final_state = output
                        mapped = self._event_mapper.map_event(execution_key, event)
                        if mapped:
                            yield mapped
            except TimeoutError:
                msg = (
                    f"Scan rerun from {start_node} timed out after {_scan_timeout:.0f}s — "
                    "likely a LangGraph fan-in deadlock. Resume from an earlier completed node."
                )
                logger.error("SCAN rerun run=%s: %s", root_run_id, msg)
                yield system_log(f"Error: {msg}")
                raise RuntimeError(msg) from None
            except Exception as exc:
                failing_node = self._failure_node_for(execution_key, exc) or start_node
                guidance = build_resume_guidance(
                    run_kind="scan",
                    failing_node=failing_node,
                    identifier=date,
                )
                logger.exception("SCAN rerun run=%s failed at node=%s", root_run_id, failing_node)
                yield system_log(f"Error: {exc}. {guidance}")
                raise

            if not captured_root_state:
                message = f"Scan continuation from {start_node} for {date} completed without a root final state."
                logger.error("SCAN rerun run=%s: %s", root_run_id, message)
                yield system_log(f"Error: {message}")
                raise RuntimeError(message)

            if final_state:
                async for evt in self._save_scan_outputs(final_state, date, root_run_id, store):
                    yield evt

            logger.info("Completed SCAN rerun run=%s node=%s", root_run_id, start_node)
        finally:
            self._event_mapper.unregister_run(execution_key)
            self._finish_run_logger(execution_key, get_market_dir(date, root_run_id))

    async def run_pipeline(
        self, run_id: str, params: dict[str, Any]
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run per-ticker analysis pipeline and stream events."""
        instrument = resolve_instrument(params.get("ticker", "AAPL"), source_context="pipeline")
        ticker = instrument.canonical_symbol or "AAPL"
        date = params.get("date", time.strftime("%Y-%m-%d"))
        analysts = (
            params.get("analysts")
            or params.get("selected_analysts")
            or ["market", "news", "fundamentals"]
        )
        root_run_id = _root_run_id(run_id, params)
        execution_key = _execution_key(run_id, params)
        store = create_report_store(run_id=root_run_id)

        rl = self._start_run_logger(root_run_id, logger_key=execution_key)

        logger.info("Starting PIPELINE run=%s ticker=%s date=%s", root_run_id, ticker, date)

        if not is_equity_pipeline_supported(instrument):
            yield system_log(
                f"Skipping stock deep-dive for {ticker}: "
                f"classified as {instrument.instrument_type} ({instrument.asset_class})."
            )
            logger.info(
                "Skipping unsupported pipeline instrument run=%s ticker=%s type=%s",
                root_run_id,
                ticker,
                instrument.instrument_type,
            )
            self._finish_run_logger(execution_key, get_ticker_dir(date, ticker, root_run_id))
            return

        yield system_log(f"Starting analysis pipeline for {ticker} on {date}")
        self._configure_runtime_guards()
        for warning_event in self._vendor_health_warning_events(
            critical_methods=(
                "get_stock_data",
                "get_indicators",
                "get_fundamentals",
                "get_news",
                "get_insider_transactions",
            )
        ):
            yield warning_event

        injected_market = {
            "market_report": "",
            "macro_regime_report": "",
            "market_report_structured": {},
        }
        market_report_file = str(params.get("market_report_file") or "").strip()
        if market_report_file:
            injected_market = _load_injected_market_report(market_report_file)
            if injected_market["market_report"] and not injected_market["market_report_structured"]:
                injected_market["market_report_structured"] = build_market_report_structured(
                    ticker=ticker,
                    as_of_date=date,
                    market_report=injected_market["market_report"],
                    macro_regime_report=injected_market["macro_regime_report"],
                )
            elif injected_market["market_report_structured"]:
                injected_market["market_report_structured"]["ticker"] = ticker
                injected_market["market_report_structured"]["as_of_date"] = date
            yield system_log(
                f"Injecting saved market report for {ticker} from {market_report_file}"
            )
            logger.info(
                "PIPELINE run=%s ticker=%s using injected market report file=%s",
                root_run_id,
                ticker,
                market_report_file,
            )

        graph_wrapper = TradingAgentsGraph(
            selected_analysts=analysts,
            config=self.config,
            debug=True,
        )

        # Load scanner graph facts and render ticker-specific context
        scanner_graph_context_text = ""
        _graph_facts_path = get_scanner_graph_facts_path(date, root_run_id)
        if _graph_facts_path.exists():
            _facts = load_scanner_graph_facts(_graph_facts_path)
            try:
                scanner_graph_context_text = render_ticker_graph_context(_facts, ticker)
            except KeyError:
                scanner_graph_context_text = ""
                logger.warning(
                    "Ticker %s not found in scanner graph facts run=%s — context will be empty",
                    ticker,
                    root_run_id,
                )
        else:
            logger.info(
                "scanner_graph_facts.json missing for run=%s, date=%s. Proceeding with empty context.",
                root_run_id,
                date,
            )

        initial_state = graph_wrapper.propagator.create_initial_state(
            ticker,
            date,
            run_id=root_run_id,
            canonical_regime=_parse_canonical_regime(
                _resolve_macro_brief([
                    str(params.get("macro_brief") or ""),
                    str(params.get("macro_scan_summary") or ""),
                    str(injected_market.get("macro_regime_report") or ""),
                ])
            ),
            portfolio_context=params.get("portfolio_context", "candidate"),
            scanner_context_packet=params.get("scanner_context_packet", ""),
            scanner_graph_context_text=scanner_graph_context_text,
            market_report=injected_market["market_report"],
            market_report_structured=injected_market["market_report_structured"],
            macro_regime_report=injected_market["macro_regime_report"],
        )
        if params.get("resume_from_latest_snapshot"):
            resume_snapshot = store.load_latest_pipeline_node_snapshot(date, ticker)
            if resume_snapshot and isinstance(resume_snapshot.get("state"), dict):
                _apply_resume_state(initial_state, resume_snapshot["state"])
                resume_node = str(resume_snapshot.get("node_name") or "saved state")
                yield system_log(
                    f"Resuming analysis for {ticker} from saved state after {resume_node}."
                )

        self._event_mapper.register_run(execution_key, ticker.upper())
        final_state: dict[str, Any] = {}
        current_state: dict[str, Any] = dict(initial_state)

        try:
            async for event in graph_wrapper.graph.astream_events(
                initial_state,
                version="v2",
                config={
                    "recursion_limit": graph_wrapper.propagator.max_recur_limit,
                    "callbacks": [rl.callback],
                },
            ):
                if run_should_stop(root_run_id):
                    logger.info(
                        "PIPELINE run=%s ticker=%s: graceful stop requested, aborting early",
                        root_run_id,
                        ticker,
                    )
                    yield system_log(
                        f"Aborting analysis for {ticker} due to graceful stop request."
                    )
                    raise asyncio.CancelledError()

                # Capture the complete final state from the root graph's terminal event.
                if is_root_chain_end(event):
                    output = (event.get("data") or {}).get("output")
                    if isinstance(output, dict):
                        final_state = output
                self._maybe_persist_pipeline_recovery_artifacts(
                    event=event,
                    current_state=current_state,
                    store=store,
                    date=date,
                    ticker=ticker,
                    root_run_id=root_run_id,
                    error_context="pipeline node",
                )
                mapped = self._event_mapper.map_event(execution_key, event)
                if mapped:
                    yield mapped
        except Exception as exc:
            failing_node = self._failure_node_for(execution_key, exc)
            guidance = build_resume_guidance(
                run_kind="pipeline",
                failing_node=failing_node,
                identifier=ticker,
            )
            logger.exception(
                "PIPELINE run=%s ticker=%s failed at node=%s",
                root_run_id,
                ticker,
                failing_node or "unknown",
            )
            yield system_log(f"Error: {exc}. {guidance}")
            if is_policy_error(exc):
                failing_tier = infer_fallback_tier(self.config, exc)
                model, provider = resolve_tier_model_provider(self.config, failing_tier)
                raise RuntimeError(
                    f"LLM 404 (model={model}, provider={provider}): model blocked by "
                    f"provider policy — https://openrouter.ai/settings/privacy — "
                    f"or set TRADINGAGENTS_QUICK/MID/DEEP_THINK_FALLBACK_LLM."
                ) from exc
            raise
        finally:
            self._event_mapper.unregister_run(execution_key)

        # Fallback: if the root on_chain_end event was never captured (can happen
        # with deeply nested sub-graphs), re-invoke to get the complete final state.
        if not final_state:
            logger.warning(
                "PIPELINE run=%s ticker=%s: root on_chain_end not captured — "
                "falling back to ainvoke",
                root_run_id,
                ticker,
            )
            try:
                final_state = await graph_wrapper.graph.ainvoke(
                    initial_state,
                    config={"recursion_limit": graph_wrapper.propagator.max_recur_limit},
                )
            except Exception as exc:
                logger.warning("PIPELINE fallback ainvoke failed run=%s: %s", root_run_id, exc)

        # Save pipeline reports
        if final_state:
            yield system_log(f"Saving analysis report for {ticker}…")
            try:
                save_dir = get_ticker_dir(date, ticker, root_run_id)
                save_dir.mkdir(parents=True, exist_ok=True)

                # Sanitize final_state to remove non-JSON-serializable objects
                # (e.g. LangChain HumanMessage, AIMessage objects in "messages")
                serializable_state = sanitize_for_json(final_state)
                serializable_state.update(instrument.to_metadata())
                serializable_state["ticker"] = ticker
                serializable_state["analysis_status"] = normalize_analysis_status(
                    serializable_state
                )
                pipeline_node_results = _extract_node_results(
                    serializable_state,
                    _PIPELINE_NODE_RESULT_FIELDS,
                )
                if pipeline_node_results:
                    serializable_state["pipeline_node_results"] = pipeline_node_results

                # Save JSON via store (complete_report.json)
                store.save_analysis(date, ticker, serializable_state)

                # Write human-readable complete_report.md
                write_complete_report_md(final_state, ticker, save_dir)

                # Append to daily digest
                digest_content = (
                    final_state.get("final_trade_decision")
                    or final_state.get("trader_investment_plan")
                    or ""
                )
                if digest_content:
                    append_to_digest(date, "analyze", ticker, digest_content)

                # Save analysts checkpoint (any analyst report populated — social is optional)
                analysts_ckpt = _build_analysts_checkpoint(
                    serializable_state,
                    ticker=ticker,
                    date=date,
                )
                if analysts_ckpt:
                    store.save_analysts_checkpoint(date, ticker, analysts_ckpt)

                trader_ckpt = _build_trader_checkpoint(
                    serializable_state,
                    ticker=ticker,
                    date=date,
                )
                if trader_ckpt:
                    store.save_trader_checkpoint(date, ticker, trader_ckpt)

                yield system_log(f"Analysis report for {ticker} saved to {save_dir}")
                logger.info(
                    "Saved pipeline report run=%s ticker=%s dir=%s", root_run_id, ticker, save_dir
                )
            except Exception as exc:
                logger.exception(
                    "Failed to save pipeline reports run=%s ticker=%s", root_run_id, ticker
                )
                yield system_log(f"Warning: could not save analysis report for {ticker}: {exc}")

        logger.info("Completed PIPELINE run=%s", root_run_id)
        self._finish_run_logger(execution_key, get_ticker_dir(date, ticker, root_run_id))

    async def run_portfolio(
        self, run_id: str, params: dict[str, Any]
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run the portfolio manager workflow and stream events."""
        date = params.get("date", time.strftime("%Y-%m-%d"))
        portfolio_id = params.get("portfolio_id", "main_portfolio")
        root_run_id = _root_run_id(run_id, params)
        execution_key = _execution_key(run_id, params)
        store = create_report_store(run_id=root_run_id)
        reader_store = create_report_store(run_id=root_run_id)
        fallback_reader_store = create_report_store()

        rl = self._start_run_logger(root_run_id, logger_key=execution_key)

        logger.info(
            "Starting PORTFOLIO run=%s portfolio=%s date=%s",
            root_run_id,
            portfolio_id,
            date,
        )
        yield system_log(f"Starting portfolio manager for {portfolio_id} on {date}")
        self._configure_runtime_guards()
        for warning_event in self._vendor_health_warning_events(
            critical_methods=("get_stock_data", "get_news")
        ):
            yield warning_event

        scan_summary = normalize_scan_summary(
            reader_store.load_scan(date) or fallback_reader_store.load_scan(date) or {}
        )
        ticker_analyses: dict[str, Any] = {}

        search_dirs: list[Path] = []
        run_daily_dir = get_daily_dir(date, root_run_id)
        portfolio_graph = PortfolioGraph(
            config={
                **self.config,
                "run_path": str(store.portfolio_report_dir(date)),
            },
            callbacks=[rl.callback],
        )
        all_daily_dir = get_daily_dir(date)
        if run_daily_dir.exists():
            search_dirs.append(run_daily_dir)
        elif all_daily_dir.exists():
            search_dirs.extend(
                sorted((p for p in all_daily_dir.iterdir() if p.is_dir()), reverse=True)
            )

        seen_tickers: set[str] = set()
        incomplete_tickers: list[str] = []
        for base in search_dirs:
            for ticker_dir in base.iterdir():
                if (
                    ticker_dir.is_dir()
                    and ticker_dir.name not in ("market", "portfolio", "report")
                    and ticker_dir.name.upper() not in seen_tickers
                ):
                    analysis = reader_store.load_analysis(date, ticker_dir.name)
                    if analysis is None:
                        analysis = fallback_reader_store.load_analysis(date, ticker_dir.name)
                    instrument_key = (analysis or {}).get("instrument_key") or resolve_instrument(
                        ticker_dir.name, source_context="analysis"
                    ).instrument_key
                    if analysis_has_deep_dive(analysis):
                        ticker_analyses[instrument_key] = analysis
                        seen_tickers.add(instrument_key)
                    elif analysis:
                        incomplete_tickers.append(instrument_key)

        if scan_summary:
            yield system_log(f"Loaded macro scan summary for {date}")
        else:
            yield system_log(f"No scan summary found for {date}, proceeding without it")
        if ticker_analyses:
            yield system_log(f"Loaded analyses for: {', '.join(sorted(ticker_analyses.keys()))}")
        else:
            yield system_log("No per-ticker analyses found for this date")
        if incomplete_tickers:
            yield system_log(
                "Ignoring incomplete ticker analyses without deep-dive decisions: "
                + ", ".join(sorted(set(incomplete_tickers)))
            )

        # Merge ticker_analyses into scan_summary so portfolio graph nodes can access
        # per-ticker analysis data (PortfolioManagerState has no ticker_analyses field).
        if ticker_analyses:
            scan_summary["ticker_analyses"] = ticker_analyses

        # Collect tickers: current holdings + scan candidates, then fetch live prices
        holding_tickers: list[str] = []
        try:
            from tradingagents.portfolio.repository import PortfolioRepository

            _repo = PortfolioRepository()
            _, holdings = _repo.get_portfolio_with_holdings(portfolio_id)
            holding_tickers = [h.ticker for h in holdings]
        except CircuitBreakerOpen:
            logger.warning(
                "run_portfolio: circuit breaker open when loading holdings for price fetch; "
                "aborting portfolio run"
            )
            raise
        except Exception as exc:
            logger.warning("run_portfolio: could not load holdings for price fetch: %s", exc)
        analysis_tickers = [
            str(analysis.get("canonical_symbol") or analysis.get("ticker") or "").upper()
            for analysis in ticker_analyses.values()
        ]
        # Always include the cash-sweep ETF so the trade executor can price it
        CASH_SWEEP_ETF = "SGOV"
        all_tickers = list(
            {t.upper() for t in holding_tickers + analysis_tickers if t} | {CASH_SWEEP_ETF}
        )
        prices = fetch_prices(all_tickers) if all_tickers else {}

        initial_state = {
            "portfolio_id": portfolio_id,
            "run_id": root_run_id,
            "analysis_date": date,  # PortfolioManagerState uses analysis_date
            "prices": prices,
            "scan_summary": scan_summary,
            "ticker_analyses": ticker_analyses,
            "messages": [],
            "portfolio_data": "",
            "risk_metrics": "",
            "holding_reviews": "",
            "prioritized_candidates": "",
            "pm_decision": "",
            "execution_result": "",
            "sender": "",
        }

        self._event_mapper.register_run(execution_key, portfolio_id)
        final_state: dict[str, Any] = {}

        try:
            async for event in portfolio_graph.graph.astream_events(
                initial_state, version="v2", config={"callbacks": [rl.callback]}
            ):
                if run_should_stop(root_run_id):
                    logger.info(
                        "PORTFOLIO run=%s: graceful stop requested, aborting early", root_run_id
                    )
                    yield system_log("Aborting portfolio management due to graceful stop request.")
                    raise asyncio.CancelledError()

                if is_root_chain_end(event):
                    output = (event.get("data") or {}).get("output")
                    if isinstance(output, dict):
                        final_state = output
                mapped = self._event_mapper.map_event(execution_key, event)
                if mapped:
                    yield mapped
        except CircuitBreakerOpen:
            # Let the circuit-breaker signal propagate cleanly to the caller
            # (_run_auto_phase_three) which is responsible for yielding the
            # user-facing message and raising AwaitPhase3Decision.  Emitting an
            # additional error log here would produce a duplicate message.
            raise
        except Exception as exc:
            failing_node = self._failure_node_for(execution_key, exc)
            guidance = build_resume_guidance(
                run_kind="portfolio",
                failing_node=failing_node,
                identifier=portfolio_id,
            )
            logger.exception(
                "PORTFOLIO run=%s failed at node=%s", root_run_id, failing_node or "unknown"
            )
            yield system_log(f"Error: {exc}. {guidance}")
            raise
        finally:
            self._event_mapper.unregister_run(execution_key)

        # Fallback: if the root on_chain_end event was never captured, re-invoke.
        if not final_state:
            logger.warning(
                "PORTFOLIO run=%s: root on_chain_end not captured — falling back to ainvoke",
                root_run_id,
            )
            try:
                final_state = await portfolio_graph.graph.ainvoke(initial_state)
            except CircuitBreakerOpen:
                logger.warning(
                    "PORTFOLIO fallback ainvoke failed run=%s: circuit breaker open; "
                    "portfolio decision may be incomplete or missing",
                    root_run_id,
                )
                raise
            except Exception as exc:
                logger.warning("PORTFOLIO fallback ainvoke failed run=%s: %s", root_run_id, exc)

        # Save portfolio reports (Holding Reviews, Risk Metrics, PM Decision, Execution Result)
        if final_state:
            try:
                serializable_final_state = sanitize_for_json(final_state)
                portfolio_node_results = _extract_node_results(
                    serializable_final_state,
                    _PORTFOLIO_NODE_RESULT_FIELDS,
                )
                if portfolio_node_results:
                    store.save_portfolio_node_results(
                        date,
                        portfolio_id,
                        {
                            "portfolio_id": portfolio_id,
                            "analysis_date": date,
                            "node_results": portfolio_node_results,
                        },
                    )

                # 1. Holding Reviews — save the raw string via store
                holding_reviews_str = final_state.get("holding_reviews")
                if holding_reviews_str:
                    try:
                        reviews = (
                            json.loads(holding_reviews_str)
                            if isinstance(holding_reviews_str, str)
                            else holding_reviews_str
                        )
                        if isinstance(reviews, dict):
                            for ticker, review_data in reviews.items():
                                store.save_holding_review(date, ticker, review_data)
                        else:
                            logger.warning(
                                "Unexpected holding_reviews format run=%s: %s",
                                root_run_id,
                                type(reviews),
                            )
                    except Exception as exc:
                        logger.warning(
                            "Failed to save holding_reviews run=%s: %s", root_run_id, exc
                        )

                # 2. Risk Metrics
                risk_metrics_str = final_state.get("risk_metrics")
                if risk_metrics_str:
                    try:
                        metrics = (
                            json.loads(risk_metrics_str)
                            if isinstance(risk_metrics_str, str)
                            else risk_metrics_str
                        )
                        store.save_risk_metrics(date, portfolio_id, metrics)
                    except Exception as exc:
                        logger.warning("Failed to save risk_metrics run=%s: %s", root_run_id, exc)

                # 3. PM Decision
                pm_decision_str = final_state.get("pm_decision")
                if pm_decision_str:
                    try:
                        decision = (
                            json.loads(pm_decision_str)
                            if isinstance(pm_decision_str, str)
                            else pm_decision_str
                        )
                        store.save_pm_decision(date, portfolio_id, decision)
                    except CircuitBreakerOpen:
                        # Let the outer CircuitBreakerOpen handler log once and re-raise.
                        raise
                    except Exception as exc:
                        logger.warning("Failed to save pm_decision run=%s: %s", root_run_id, exc)

                # 4. Execution Result
                execution_result_str = final_state.get("execution_result")
                if execution_result_str:
                    try:
                        execution = (
                            json.loads(execution_result_str)
                            if isinstance(execution_result_str, str)
                            else execution_result_str
                        )
                        store.save_execution_result(date, portfolio_id, execution)
                    except CircuitBreakerOpen:
                        # Let the outer CircuitBreakerOpen handler log once and re-raise.
                        raise
                    except Exception as exc:
                        logger.warning(
                            "Failed to save execution_result run=%s: %s", root_run_id, exc
                        )

                yield system_log(
                    f"Portfolio stage reports (decision & execution) saved for {portfolio_id} on {date}"
                )
            except CircuitBreakerOpen:
                logger.warning(
                    "run_portfolio: circuit breaker open when saving portfolio reports for run=%s; "
                    "reports may be incomplete or missing",
                    root_run_id,
                )
                raise
            except Exception as exc:
                logger.exception("Failed to save portfolio reports run=%s", root_run_id)
                yield system_log(f"Warning: could not save portfolio reports: {exc}")

        logger.info("Completed PORTFOLIO run=%s", root_run_id)
        self._finish_run_logger(execution_key, get_daily_dir(date, root_run_id) / "portfolio")

    async def run_trade_execution(
        self,
        run_id: str,
        date: str,
        portfolio_id: str,
        decision: dict,
        prices: dict,
        store: ReportStore | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Manually execute a pre-computed PM decision (for resumability)."""
        logger.info(
            "Starting TRADE_EXECUTION run=%s portfolio=%s date=%s", run_id, portfolio_id, date
        )
        yield system_log(f"Resuming trade execution for {portfolio_id} using saved decision…")

        from tradingagents.portfolio.repository import PortfolioRepository
        from tradingagents.portfolio.trade_executor import TradeExecutor

        if not prices:
            tickers = tickers_from_decision(decision)
            if tickers:
                yield system_log(f"Fetching live prices for {tickers} from yfinance…")
                prices = fetch_prices(tickers)
                logger.info(
                    "TRADE_EXECUTION run=%s: fetched prices for %s", run_id, list(prices.keys())
                )
            if not prices:
                logger.warning(
                    "TRADE_EXECUTION run=%s: no prices available — execution may produce incomplete results",
                    run_id,
                )
                yield system_log(
                    f"Warning: no prices found for {portfolio_id} on {date} — trade execution may be incomplete."
                )

        _store = store or create_report_store(run_id=run_id)

        try:
            repo = PortfolioRepository()
            executor = TradeExecutor(repo=repo, config=self.config)

            # Execute decisions
            result = executor.execute_decisions(portfolio_id, decision, prices, date=date)

            # Save results using the shared store instance
            _store.save_execution_result(date, portfolio_id, result)

            yield system_log(
                f"Trade execution completed for {portfolio_id}. {result.get('summary', {})}"
            )
            logger.info("Completed TRADE_EXECUTION run=%s", run_id)
        except Exception as exc:
            logger.exception("Trade execution failed run=%s", run_id)
            yield system_log(f"Error during trade execution: {exc}")
            raise

    async def run_pipeline_from_phase(
        self,
        run_id: str,
        params: dict[str, Any],
        phase: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Re-run a single ticker's pipeline from a specific phase.

        Phases:
            analysts        - full re-run (delegates to run_pipeline)
            debate_and_trader - load analysts_checkpoint, run debate+trader+risk subgraph
            risk            - load trader_checkpoint, run risk subgraph only

        After the subgraph completes the ticker's reports and checkpoints are
        overwritten and the portfolio manager is re-run so that the PM
        decision reflects the updated ticker analysis.
        """
        ticker = params.get("ticker", params.get("identifier", "AAPL"))
        instrument = resolve_instrument(ticker, source_context="pipeline_rerun")
        date = params.get("date", time.strftime("%Y-%m-%d"))
        portfolio_id = params.get("portfolio_id", "main_portfolio")
        root_run_id = _root_run_id(run_id, params)
        execution_key = _execution_key(run_id, params)
        store = create_report_store(run_id=root_run_id)
        fallback_store = create_report_store()
        writer_store = create_report_store(run_id=root_run_id)

        if not is_equity_pipeline_supported(instrument):
            yield system_log(
                f"Skipping {phase} re-run for {ticker}: "
                f"classified as {instrument.instrument_type} ({instrument.asset_class})."
            )
            return

        if phase == "analysts":
            # Full re-run
            async for evt in self.run_pipeline(
                execution_key,
                {
                    "ticker": ticker,
                    "date": date,
                    "run_id": root_run_id,
                    "portfolio_context": params.get("portfolio_context", "candidate"),
                    "_execution_key": execution_key,
                },
            ):
                yield evt
        elif phase == "debate_and_trader":
            yield system_log(f"Loading analysts checkpoint for {ticker}...")
            ckpt = store.load_analysts_checkpoint(
                date, ticker
            ) or fallback_store.load_analysts_checkpoint(date, ticker)
            if not ckpt:
                yield system_log(
                    f"No analysts checkpoint found for {ticker} — falling back to full re-run"
                )
                async for evt in self.run_pipeline(
                    execution_key,
                    {
                        "ticker": ticker,
                        "date": date,
                        "run_id": root_run_id,
                        "portfolio_context": params.get("portfolio_context", "candidate"),
                        "_execution_key": execution_key,
                    },
                ):
                    yield evt
            else:
                yield system_log(f"Running debate + trader + risk for {ticker} from checkpoint...")
                graph_wrapper = TradingAgentsGraph(config=self.config, debug=True)

                # Resume path: inject graph context if available; warn if not
                _scanner_graph_context_text = ""
                _gfp = get_scanner_graph_facts_path(date, root_run_id)
                if _gfp.exists():
                    try:
                        _facts = load_scanner_graph_facts(_gfp)
                        _scanner_graph_context_text = render_ticker_graph_context(_facts, ticker)
                    except Exception as _exc:
                        logger.warning(
                            "Could not render graph context for resume %s: %s", ticker, _exc
                        )
                else:
                    logger.warning(
                        "WARNING: Resuming without scanner_graph_facts.json - "
                        "scanner_context_packet fallback active. run=%s ticker=%s",
                        root_run_id,
                        ticker,
                    )

                initial_state = graph_wrapper.propagator.create_initial_state(
                    ticker,
                    date,
                    run_id=root_run_id,
                    portfolio_context=ckpt.get("portfolio_context", "candidate"),
                    scanner_graph_context_text=_scanner_graph_context_text,
                )
                # Overlay checkpoint data onto initial state
                for k, v in ckpt.items():
                    if k in initial_state or k in (
                        "market_report",
                        "market_report_structured",
                        "sentiment_report",
                        "news_report",
                        "news_report_structured",
                        "fundamentals_report",
                        "fundamentals_report_structured",
                        "macro_regime_report",
                    ):
                        # Repair messages list if this is the messages key
                        if k == "messages" and isinstance(v, list):
                            v = repair_checkpoint_messages(v)
                        initial_state[k] = v

                rl = self._start_run_logger(root_run_id, logger_key=execution_key)
                self._event_mapper.register_run(execution_key, ticker.upper())
                final_state: dict[str, Any] = {}
                current_state: dict[str, Any] = dict(initial_state)

                async for event in graph_wrapper.debate_graph.astream_events(
                    initial_state,
                    version="v2",
                    config={
                        "recursion_limit": graph_wrapper.propagator.max_recur_limit,
                        "callbacks": [rl.callback],
                    },
                ):
                    if run_should_stop(root_run_id):
                        logger.info(
                            "PIPELINE_RERUN run=%s ticker=%s: graceful stop requested, aborting early",
                            root_run_id,
                            ticker,
                        )
                        yield system_log(
                            f"Aborting rerun for {ticker} due to graceful stop request."
                        )
                        raise asyncio.CancelledError()

                    if is_root_chain_end(event):
                        output = (event.get("data") or {}).get("output")
                        if isinstance(output, dict):
                            final_state = output
                    self._maybe_persist_pipeline_recovery_artifacts(
                        event=event,
                        current_state=current_state,
                        store=writer_store,
                        date=date,
                        ticker=ticker,
                        root_run_id=root_run_id,
                        error_context="debate rerun",
                    )
                    mapped = self._event_mapper.map_event(execution_key, event)
                    if mapped:
                        yield mapped

                self._event_mapper.unregister_run(execution_key)

                if final_state:
                    serializable_state = sanitize_for_json(final_state)
                    serializable_state["analysis_status"] = normalize_analysis_status(
                        serializable_state
                    )
                    pipeline_node_results = _extract_node_results(
                        serializable_state,
                        _PIPELINE_NODE_RESULT_FIELDS,
                    )
                    if pipeline_node_results:
                        serializable_state["pipeline_node_results"] = pipeline_node_results
                    writer_store.save_analysis(date, ticker, serializable_state)
                    # Overwrite checkpoints
                    trader_ckpt = _build_trader_checkpoint(
                        serializable_state,
                        ticker=ticker,
                        date=date,
                    )
                    if trader_ckpt:
                        writer_store.save_trader_checkpoint(date, ticker, trader_ckpt)

                self._finish_run_logger(execution_key, get_ticker_dir(date, ticker, root_run_id))
        elif phase == "risk":
            yield system_log(f"Loading trader checkpoint for {ticker}...")
            ckpt = store.load_trader_checkpoint(
                date, ticker
            ) or fallback_store.load_trader_checkpoint(date, ticker)
            if not ckpt:
                yield system_log(
                    f"No trader checkpoint found for {ticker} — falling back to full re-run"
                )
                async for evt in self.run_pipeline(
                    execution_key,
                    {
                        "ticker": ticker,
                        "date": date,
                        "run_id": root_run_id,
                        "portfolio_context": params.get("portfolio_context", "candidate"),
                        "_execution_key": execution_key,
                    },
                ):
                    yield evt
            else:
                yield system_log(f"Running risk phase for {ticker} from checkpoint...")
                graph_wrapper = TradingAgentsGraph(config=self.config, debug=True)

                # Resume path: inject graph context if available; warn if not
                _scanner_graph_context_text = ""
                _gfp = get_scanner_graph_facts_path(date, root_run_id)
                if _gfp.exists():
                    try:
                        _facts = load_scanner_graph_facts(_gfp)
                        _scanner_graph_context_text = render_ticker_graph_context(_facts, ticker)
                    except Exception as _exc:
                        logger.warning(
                            "Could not render graph context for resume %s: %s", ticker, _exc
                        )
                else:
                    logger.warning(
                        "WARNING: Resuming without scanner_graph_facts.json - "
                        "scanner_context_packet fallback active. run=%s ticker=%s",
                        root_run_id,
                        ticker,
                    )

                initial_state = graph_wrapper.propagator.create_initial_state(
                    ticker,
                    date,
                    run_id=root_run_id,
                    portfolio_context=ckpt.get("portfolio_context", "candidate"),
                    scanner_graph_context_text=_scanner_graph_context_text,
                )
                if not ckpt.get("investment_plan"):
                    raise ValueError(
                        f"Trader checkpoint for {ticker} on {date} is invalid: "
                        "missing required 'investment_plan'"
                    )
                for k, v in ckpt.items():
                    if k != "messages":
                        initial_state[k] = v
                    elif isinstance(v, list):
                        initial_state[k] = repair_checkpoint_messages(v)

                rl = self._start_run_logger(root_run_id, logger_key=execution_key)
                self._event_mapper.register_run(execution_key, ticker.upper())
                final_state: dict[str, Any] = {}
                current_state: dict[str, Any] = dict(initial_state)

                async for event in graph_wrapper.risk_graph.astream_events(
                    initial_state,
                    version="v2",
                    config={
                        "recursion_limit": graph_wrapper.propagator.max_recur_limit,
                        "callbacks": [rl.callback],
                    },
                ):
                    if run_should_stop(root_run_id):
                        logger.info(
                            "PIPELINE_RERUN_RISK run=%s ticker=%s: graceful stop requested, aborting early",
                            root_run_id,
                            ticker,
                        )
                        yield system_log(
                            f"Aborting risk rerun for {ticker} due to graceful stop request."
                        )
                        raise asyncio.CancelledError()

                    if is_root_chain_end(event):
                        output = (event.get("data") or {}).get("output")
                        if isinstance(output, dict):
                            final_state = output
                    self._maybe_persist_pipeline_recovery_artifacts(
                        event=event,
                        current_state=current_state,
                        store=writer_store,
                        date=date,
                        ticker=ticker,
                        root_run_id=root_run_id,
                        error_context="risk rerun",
                    )
                    mapped = self._event_mapper.map_event(execution_key, event)
                    if mapped:
                        yield mapped

                self._event_mapper.unregister_run(execution_key)

                if final_state:
                    serializable_state = sanitize_for_json(final_state)
                    serializable_state["analysis_status"] = normalize_analysis_status(
                        serializable_state
                    )
                    pipeline_node_results = _extract_node_results(
                        serializable_state,
                        _PIPELINE_NODE_RESULT_FIELDS,
                    )
                    if pipeline_node_results:
                        serializable_state["pipeline_node_results"] = pipeline_node_results
                    writer_store.save_analysis(date, ticker, serializable_state)

                self._finish_run_logger(execution_key, get_ticker_dir(date, ticker, root_run_id))
        else:
            yield system_log(f"Unknown phase '{phase}' — skipping")
            return

        # Cascade: re-run portfolio manager with updated data
        yield system_log(
            f"Cascading: re-running portfolio manager after {ticker} {phase} re-run..."
        )
        async for evt in self.run_portfolio(
            f"{root_run_id}:cascade_pm:{ticker}:{phase}",
            {
                "date": date,
                "portfolio_id": portfolio_id,
                "run_id": root_run_id,
                "_execution_key": f"{root_run_id}:cascade_pm:{ticker}:{phase}",
            },
        ):
            yield evt

    async def run_auto(
        self, run_id: str, params: dict[str, Any]
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run the full auto pipeline: scan → pipeline → portfolio."""
        date = _require_scanner_date(params, run_kind="run_auto")
        force = params.get("force", False)
        continue_on_ticker_failure = bool(params.get("continue_on_ticker_failure"))
        include_portfolio_holdings = params.get("include_portfolio_holdings", True)
        root_run_id = _root_run_id(run_id, params)
        execution_key = _execution_key(run_id, params)

        params = {**params, "run_id": root_run_id}
        store = create_report_store(run_id=root_run_id)

        self._start_run_logger(root_run_id, logger_key=execution_key)
        try:
            logger.info("Starting AUTO run=%s date=%s force=%s", root_run_id, date, force)
            yield system_log(
                f"Starting full auto workflow for {date} (force={force}, run={root_run_id})"
            )

            # Phase 1: Market scan
            yield system_log("Phase 1/3: Running market scan…")
            if not force and store.load_scan(date):
                yield system_log(f"Phase 1: Macro scan for {date} already exists, skipping.")
            else:
                scan_params = {
                    "date": date,
                    "run_id": root_run_id,
                    "_execution_key": f"{root_run_id}:scan",
                }
                if params.get("max_tickers"):
                    scan_params["max_tickers"] = params["max_tickers"]
                try:
                    async for evt in self.run_scan(f"{root_run_id}:scan", scan_params):
                        yield evt
                except Exception as exc:
                    if is_fallback_eligible_error(exc):
                        failing_tier = infer_fallback_tier(self.config, exc)
                        fallback_config = build_fallback_config(self.config, tier=failing_tier)
                        if fallback_config:
                            fallback_models = fallback_model_summary(self.config, fallback_config)
                            await asyncio.sleep(0)
                            yield system_log(
                                "Phase 1/3: primary scan model unavailable — retrying with "
                                f"fallback: {fallback_models or 'configured tier fallbacks'}…"
                            )
                            original_config = self.config
                            self.config = fallback_config
                            try:
                                async for evt in self.run_scan(
                                    f"{root_run_id}:scan:fallback",
                                    {
                                        **scan_params,
                                        "_execution_key": f"{root_run_id}:scan:fallback",
                                    },
                                ):
                                    yield evt
                            except Exception as fallback_exc:
                                logger.error(
                                    "Fallback scan also failed run=%s: %s",
                                    root_run_id,
                                    fallback_exc,
                                )
                                yield system_log(
                                    f"Phase 1/3: fallback scan also failed "
                                    f"({type(fallback_exc).__name__}): {fallback_exc}. "
                                    f"Both primary and fallback models are unavailable."
                                )
                                raise
                            finally:
                                self.config = original_config
                        else:
                            raise
                    else:
                        raise
            scan_state = self._load_scan_state(root_run_id=root_run_id, date=date, store=store)

            async for evt in self._run_auto_after_scan(
                root_run_id=root_run_id,
                date=date,
                force=force,
                params=params,
                store=store,
                scan_state=scan_state,
                continue_on_ticker_failure=continue_on_ticker_failure,
                include_portfolio_holdings=include_portfolio_holdings,
            ):
                yield evt

            logger.info("Completed AUTO run=%s", root_run_id)
        finally:
            self._finish_run_logger(execution_key, get_daily_dir(date, root_run_id))

    def _load_scan_state(self, *, root_run_id: str, date: str, store: Any) -> dict[str, Any]:
        """Load persisted Phase 1 reports into the state shape expected by Phase 2."""
        scan_state: dict[str, Any] = {"scan_date": date, "run_id": root_run_id}
        save_dir = get_market_dir(date, root_run_id)
        for key in SCAN_NODE_TO_REPORT_FIELD.values():
            report_file = save_dir / f"{key}.md"
            if report_file.exists():
                scan_state[key] = report_file.read_text()

        regime_file = save_dir / "macro_regime_report.md"
        if regime_file.exists():
            scan_state["macro_regime_report"] = regime_file.read_text()

        scan_summary = store.load_scan(date)
        if scan_summary:
            scan_state["macro_scan_summary"] = scan_summary
        return scan_state

    async def _run_auto_after_scan(
        self,
        *,
        root_run_id: str,
        date: str,
        force: bool,
        params: dict[str, Any],
        store: Any,
        scan_state: dict[str, Any],
        continue_on_ticker_failure: bool,
        include_portfolio_holdings: bool,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if run_should_stop(root_run_id):
            yield system_log("Graceful stop requested — finishing after the market scan phase.")
            return

        # Phase 2: Pipeline analysis — get tickers from scan report + portfolio holdings
        yield system_log("Phase 2/3: Loading stocks from scan report…")
        scan_data = normalize_scan_summary(store.load_scan(date) or {})
        scan_instruments = extract_pipeline_instruments_from_scan_data(scan_data)
        tracked_market_symbols = [
            str(item.get("ticker") or "")
            for item in (scan_data.get("tracked_market_instruments") or [])
            if isinstance(item, dict)
        ]
        tracked_crypto_symbols = [
            str(item.get("ticker") or "")
            for item in (scan_data.get("tracked_crypto_instruments") or [])
            if isinstance(item, dict)
        ]

        # Safety cap: truncate scan candidates to max_auto_tickers (portfolio holdings added after)
        max_t = int(params.get("max_tickers") or self.config.get("max_auto_tickers") or 10)
        scan_instruments = scan_instruments[:max_t]

        # Also include tickers from current portfolio holdings so the PM agent
        # has fresh analysis for existing positions (hold/sell/add decisions).
        portfolio_id = params.get("portfolio_id", "main_portfolio")
        holding_tickers: list[str] = []
        if include_portfolio_holdings:
            try:
                from tradingagents.portfolio.repository import PortfolioRepository

                _repo = PortfolioRepository()
                _, holdings = _repo.get_portfolio_with_holdings(portfolio_id)
                holding_tickers = [h.ticker.upper() for h in holdings]
            except Exception as exc:
                logger.warning("run_auto: could not load holdings for pipeline: %s", exc)
        else:
            yield system_log(
                "Phase 2/3: include_portfolio_holdings=False — skipping portfolio holdings, scan candidates only."
            )

        holding_instruments = [
            resolve_instrument(ticker, source_context="holding") for ticker in holding_tickers
        ]
        holding_instrument_keys = {
            instrument.instrument_key
            for instrument in holding_instruments
            if is_equity_pipeline_supported(instrument)
        }
        skipped_holding_symbols = [
            instrument.canonical_symbol
            for instrument in holding_instruments
            if instrument.canonical_symbol and not is_equity_pipeline_supported(instrument)
        ]

        # Merge & deduplicate (scan candidates first, then holdings-only tickers)
        seen: set[str] = set()
        queued_instruments: list[CanonicalInstrument] = []
        for instrument in scan_instruments:
            if instrument.instrument_key not in seen:
                seen.add(instrument.instrument_key)
                queued_instruments.append(instrument)
        holdings_only: list[str] = []
        for instrument in holding_instruments:
            if not is_equity_pipeline_supported(instrument):
                continue
            if instrument.instrument_key not in seen:
                seen.add(instrument.instrument_key)
                queued_instruments.append(instrument)
                holdings_only.append(instrument.canonical_symbol)

        if scan_instruments:
            yield system_log(
                f"Phase 2/3: {len(scan_instruments)} equity ticker(s) from scan report"
            )
        if tracked_market_symbols:
            yield system_log(
                "Phase 2/3: tracked market instruments kept out of stock deep-dive queue: "
                + ", ".join(tracked_market_symbols)
            )
        if tracked_crypto_symbols:
            yield system_log(
                "Phase 2/3: tracked crypto instruments kept out of stock deep-dive queue: "
                + ", ".join(tracked_crypto_symbols)
            )
        if holdings_only:
            yield system_log(
                f"Phase 2/3: {len(holdings_only)} additional ticker(s) from portfolio holdings: "
                + ", ".join(holdings_only)
            )
        if skipped_holding_symbols:
            yield system_log(
                "Phase 2/3: skipping non-stock holdings for the current deep-dive path: "
                + ", ".join(sorted(set(skipped_holding_symbols)))
            )
        if not queued_instruments:
            yield system_log(
                "Warning: no common-stock candidates found in scan summary and no supported portfolio holdings — "
                "ensure the scan completed successfully and produced a "
                "stocks_to_investigate list. Skipping pipeline phase."
            )
        else:
            max_concurrent = int(self.config.get("max_concurrent_pipelines", 2))
            failed_tickers: dict[str, str] = {}
            completed_tickers: list[str] = []
            aborted_tickers: list[str] = []
            yield system_log(
                f"Phase 2/3: Queuing {len(queued_instruments)} ticker(s) "
                f"(max {max_concurrent} concurrent)…"
            )

            # Keep the producer and per-ticker pipelines inside task groups so
            # stop/cancel/exception paths cannot leave orphan LLM work behind.
            _sentinel = object()
            pipeline_queue: asyncio.Queue = asyncio.Queue()
            scheduler_error: str | None = None

            async def _run_one_ticker(instrument: CanonicalInstrument) -> None:
                ticker = instrument.canonical_symbol

                def _record_failure(reason: str) -> None:
                    failed_tickers[ticker] = reason

                existing_analysis = store.load_analysis(date, ticker)
                latest_snapshot = (
                    None if force else store.load_latest_pipeline_node_snapshot(date, ticker)
                )
                resume_phase = infer_pipeline_resume_phase(latest_snapshot)
                if not force and analysis_is_terminal(existing_analysis):
                    status = analysis_status(existing_analysis)
                    await pipeline_queue.put(
                        system_log(
                            f"Phase 2: Analysis for {ticker} on {date} already exists, skipping."
                        )
                    )
                    if status == "completed":
                        completed_tickers.append(ticker)
                    elif status == "aborted":
                        aborted_tickers.append(ticker)
                    return
                await pipeline_queue.put(
                    system_log(f"Phase 2/3: Running analysis pipeline for {ticker}…")
                )
                scanner_packet = build_scanner_context_packet(scan_state, ticker)

                async def _run_ticker_pipeline(execution_label: str) -> None:
                    base_params = {
                        "ticker": ticker,
                        "date": date,
                        "run_id": root_run_id,
                        "macro_brief": _resolve_macro_brief([
                            scan_state.get("macro_brief") or "",
                            scan_state.get("macro_scan_summary") or "",
                            scan_state.get("macro_regime_report") or "",
                        ]),
                        "portfolio_context": "holding"
                        if instrument.instrument_key in holding_instrument_keys
                        else "candidate",
                        "scanner_context_packet": scanner_packet,
                        "_execution_key": execution_label,
                    }
                    if resume_phase == "analysts":
                        base_params["resume_from_latest_snapshot"] = True
                        if latest_snapshot:
                            resume_node = str(latest_snapshot.get("node_name") or "saved state")
                            await pipeline_queue.put(
                                system_log(
                                    f"Phase 2/3: Resuming {ticker} from saved state after {resume_node}."
                                )
                            )
                        async for evt in self.run_pipeline(execution_label, base_params):
                            await pipeline_queue.put(evt)
                        return
                    if resume_phase in {"debate_and_trader", "risk"}:
                        resume_node = str((latest_snapshot or {}).get("node_name") or resume_phase)
                        await pipeline_queue.put(
                            system_log(
                                f"Phase 2/3: Resuming {ticker} from {resume_node} via {resume_phase} checkpoint."
                            )
                        )
                        async for evt in self.run_pipeline_from_phase(
                            execution_label, base_params, resume_phase
                        ):
                            await pipeline_queue.put(evt)
                        return
                    async for evt in self.run_pipeline(execution_label, base_params):
                        await pipeline_queue.put(evt)

                try:
                    await _run_ticker_pipeline(f"{root_run_id}:pipeline:{ticker}")
                    saved_analysis = store.load_analysis(date, ticker)
                    saved_status = analysis_status(saved_analysis)
                    if saved_status == "aborted":
                        aborted_tickers.append(ticker)
                        await pipeline_queue.put(
                            system_log(
                                f"Phase 2/3: {ticker} hit terminal critical-abort path ({saved_analysis.get('terminal_action', 'ABORT')})."
                            )
                        )
                    elif saved_status == "completed":
                        completed_tickers.append(ticker)
                    else:
                        reason = "analysis finished without a completed deep-dive decision"
                        _record_failure(reason)
                        await pipeline_queue.put(
                            system_log(
                                f"Warning: pipeline for {ticker} produced no deep-dive decision; skipping ticker in portfolio stage."
                            )
                        )
                except Exception as exc:
                    if is_fallback_eligible_error(exc):
                        logger.error(
                            "Pipeline primary model unavailable ticker=%s run=%s: %s",
                            ticker,
                            root_run_id,
                            exc,
                        )
                        failing_tier = infer_fallback_tier(self.config, exc)
                        fallback_config = build_fallback_config(self.config, tier=failing_tier)
                        if fallback_config:
                            fallback_models = fallback_model_summary(self.config, fallback_config)
                            await pipeline_queue.put(
                                system_log(
                                    f"Primary model unavailable for {ticker} — retrying with "
                                    f"fallback: {fallback_models or 'configured tier fallbacks'}…"
                                )
                            )
                            original_config = self.config
                            self.config = fallback_config
                            try:
                                await _run_ticker_pipeline(f"{root_run_id}:fallback:{ticker}")
                                saved_analysis = store.load_analysis(date, ticker)
                                saved_status = analysis_status(saved_analysis)
                                if saved_status == "aborted":
                                    aborted_tickers.append(ticker)
                                    await pipeline_queue.put(
                                        system_log(
                                            f"Phase 2/3: {ticker} hit terminal critical-abort path ({saved_analysis.get('terminal_action', 'ABORT')})."
                                        )
                                    )
                                elif saved_status == "completed":
                                    completed_tickers.append(ticker)
                                else:
                                    reason = (
                                        "fallback finished without a completed deep-dive decision"
                                    )
                                    _record_failure(reason)
                                    await pipeline_queue.put(
                                        system_log(
                                            f"Warning: fallback pipeline for {ticker} produced no deep-dive decision; skipping ticker in portfolio stage."
                                        )
                                    )
                            except Exception as fallback_exc:
                                logger.error(
                                    "Fallback pipeline failed ticker=%s: %s",
                                    ticker,
                                    fallback_exc,
                                )
                                _record_failure(str(fallback_exc))
                                await pipeline_queue.put(
                                    system_log(
                                        f"Warning: pipeline for {ticker} failed "
                                        f"(fallback also failed): {fallback_exc}"
                                    )
                                )
                            finally:
                                self.config = original_config
                        else:
                            _record_failure(str(exc))
                            await pipeline_queue.put(
                                system_log(
                                    f"Warning: pipeline for {ticker} failed due to LLM provider availability. "
                                    f"{exc} — "
                                    f"Set TRADINGAGENTS_QUICK_THINK_FALLBACK_LLM (and MID/DEEP) "
                                    f"to auto-retry with a different model."
                                )
                            )
                    else:
                        logger.exception("Pipeline failed ticker=%s run=%s", ticker, root_run_id)
                        _record_failure(str(exc))
                        await pipeline_queue.put(
                            system_log(f"Warning: pipeline for {ticker} failed: {exc}")
                        )

            async def _pipeline_producer() -> None:
                nonlocal scheduler_error
                stop_logged = False

                try:
                    async with asyncio.TaskGroup() as ticker_group:
                        pending: set[asyncio.Task] = set()
                        iterator = iter(queued_instruments)

                        def _forget_task(task: asyncio.Task) -> None:
                            pending.discard(task)

                        while True:
                            while len(pending) < max_concurrent:
                                if run_should_stop(root_run_id):
                                    if not stop_logged:
                                        stop_logged = True
                                        await pipeline_queue.put(
                                            system_log(
                                                "Graceful stop requested — no new ticker pipelines will be queued."
                                            )
                                        )
                                    break
                                try:
                                    instrument = next(iterator)
                                except StopIteration:
                                    break
                                task = ticker_group.create_task(_run_one_ticker(instrument))
                                pending.add(task)
                                task.add_done_callback(_forget_task)

                            if not pending:
                                break

                            done, _ = await asyncio.wait(
                                tuple(pending),
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                            for task in done:
                                await task
                except Exception as exc:
                    scheduler_error = str(exc)
                    logger.exception("Pipeline scheduler failed run=%s", root_run_id)
                    failed_tickers["<scheduler>"] = str(exc)
                finally:
                    await pipeline_queue.put(_sentinel)

            generator_closed = False
            try:
                async with asyncio.TaskGroup() as producer_group:
                    producer_group.create_task(_pipeline_producer())
                    while True:
                        item = await pipeline_queue.get()
                        if item is _sentinel:
                            break
                        yield item
            except* GeneratorExit:
                generator_closed = True

            if generator_closed:
                return

            if failed_tickers:
                failed_summary = ", ".join(
                    f"{ticker} ({reason})" for ticker, reason in sorted(failed_tickers.items())
                )
                if continue_on_ticker_failure:
                    yield system_log(
                        "Phase 2/3: continuing to portfolio stage without failed tickers: "
                        + failed_summary
                    )
                else:
                    yield system_log(
                        "Phase 2/3: paused before portfolio stage because ticker analyses failed: "
                        + failed_summary
                    )
                    ticker_contexts = {
                        instrument.canonical_symbol: (
                            "holding"
                            if instrument.instrument_key in holding_instrument_keys
                            else "candidate"
                        )
                        for instrument in queued_instruments
                    }
                    raise AwaitPhase3Decision(
                        {
                            "date": date,
                            "portfolio_id": portfolio_id,
                            "incomplete_tickers": [
                                {
                                    "ticker": ticker,
                                    "reason": reason,
                                    "portfolio_context": ticker_contexts.get(ticker, "candidate"),
                                }
                                for ticker, reason in sorted(failed_tickers.items())
                                if ticker != "<scheduler>"
                            ],
                            "completed_tickers": sorted(completed_tickers),
                            "aborted_tickers": sorted(aborted_tickers),
                            "scheduler_error": scheduler_error,
                        }
                    )

        if run_should_stop(root_run_id):
            yield system_log(
                "Graceful stop requested — finishing after Phase 2 without starting portfolio management."
            )
            return

        async for evt in self._run_auto_phase_three(
            root_run_id=root_run_id,
            date=date,
            force=force,
            params=params,
            store=store,
        ):
            yield evt

    async def run_auto_from_scan_rerun(
        self,
        run_id: str,
        params: dict[str, Any],
        start_node: str,
        initial_state: dict[str, Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Continue an auto workflow after re-running part of the market scan."""
        date = _require_scanner_date(params, run_kind="run_auto_from_scan_rerun")
        force = params.get("force", False)
        continue_on_ticker_failure = bool(params.get("continue_on_ticker_failure"))
        include_portfolio_holdings = params.get("include_portfolio_holdings", True)
        root_run_id = _root_run_id(run_id, params)
        store = create_report_store(run_id=root_run_id)

        scan_params = {
            "date": date,
            "portfolio_id": params.get("portfolio_id", "main_portfolio"),
            "run_id": root_run_id,
            "max_tickers": params.get("max_tickers"),
            "_execution_key": f"{root_run_id}:scan-rerun:{start_node}",
        }
        async for evt in self.run_scan_from_node(
            f"{root_run_id}:scan-rerun:{start_node}",
            scan_params,
            start_node,
            initial_state,
        ):
            yield evt

        scan_state = self._load_scan_state(root_run_id=root_run_id, date=date, store=store)
        async for evt in self._run_auto_after_scan(
            root_run_id=root_run_id,
            date=date,
            force=force,
            params={**params, "run_id": root_run_id},
            store=store,
            scan_state=scan_state,
            continue_on_ticker_failure=continue_on_ticker_failure,
            include_portfolio_holdings=include_portfolio_holdings,
        ):
            yield evt

    async def _run_auto_phase_three(
        self,
        *,
        root_run_id: str,
        date: str,
        force: bool,
        params: dict[str, Any],
        store: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run or resume the portfolio stage for an auto workflow."""
        yield system_log("Phase 3/3: Running portfolio manager…")
        portfolio_params = {k: v for k, v in params.items() if k != "ticker"}
        portfolio_params["run_id"] = root_run_id
        portfolio_id = params.get("portfolio_id", "main_portfolio")

        # Check if portfolio stage is fully complete (execution result exists)
        if not force and store.load_execution_result(date, portfolio_id):
            yield system_log(
                f"Phase 3: Portfolio execution for {portfolio_id} on {date} already exists, skipping."
            )
        else:
            # Check if we can resume from a saved decision
            saved_decision = store.load_pm_decision(date, portfolio_id)
            if not force and saved_decision:
                yield system_log(
                    f"Phase 3: Found saved PM decision for {portfolio_id}, resuming trade execution…"
                )
                prices = fetch_prices(tickers_from_decision(saved_decision))
                async for evt in self.run_trade_execution(
                    root_run_id,
                    date,
                    portfolio_id,
                    saved_decision,
                    prices,
                    store=store,
                ):
                    yield evt
            else:
                try:
                    async for evt in self.run_portfolio(
                        f"{root_run_id}:portfolio",
                        {
                            "date": date,
                            **portfolio_params,
                            "_execution_key": f"{root_run_id}:portfolio",
                        },
                    ):
                        yield evt
                except CircuitBreakerOpen as exc:
                    yield system_log(f"Phase 3/3: paused before portfolio stage: {exc}")
                    raise AwaitPhase3Decision(
                        {
                            "date": date,
                            "portfolio_id": portfolio_id,
                            "incomplete_tickers": [
                                {
                                    "ticker": "PORTFOLIO",
                                    "reason": str(exc),
                                    "portfolio_context": "portfolio",
                                }
                            ],
                            "completed_tickers": [],
                            "aborted_tickers": ["PORTFOLIO"],
                        }
                    ) from exc

    async def run_auto_phase3_decision(
        self,
        run_id: str,
        params: dict[str, Any],
        retry_tickers: list[str],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Resolve an auto-run Phase 2 pause by retrying selected tickers or continuing."""
        root_run_id = _root_run_id(run_id, params)
        execution_key = _execution_key(run_id, params)
        date = params.get("date", time.strftime("%Y-%m-%d"))
        force = bool(params.get("force", False))
        store = create_report_store(run_id=root_run_id)
        from agent_os.backend.store import runs as live_runs

        run_record = live_runs.get(root_run_id) or {}
        pending = run_record.get("pending_phase3_decision") or {}
        incomplete = pending.get("incomplete_tickers") or []
        portfolio_id = pending.get("portfolio_id") or params.get("portfolio_id", "main_portfolio")
        self._start_run_logger(root_run_id, logger_key=execution_key)

        try:
            if not incomplete:
                raise ValueError(
                    "No incomplete ticker analyses are waiting for a Phase 3 decision."
                )

            incomplete_map = {
                str(item.get("ticker") or "").upper(): item
                for item in incomplete
                if isinstance(item, dict) and item.get("ticker")
            }
            invalid = [ticker for ticker in retry_tickers if ticker not in incomplete_map]
            if invalid:
                raise ValueError(
                    "Retry tickers are not in the current incomplete set: "
                    + ", ".join(sorted(invalid))
                )

            if retry_tickers:
                yield system_log(
                    "Phase 2/3: retrying selected incomplete ticker(s): "
                    + ", ".join(sorted(retry_tickers))
                )
                for ticker in retry_tickers:
                    if run_should_stop(root_run_id):
                        logger.info(
                            "AUTO_PHASE3_DECISION run=%s: graceful stop requested, aborting early",
                            root_run_id,
                        )
                        yield system_log("Aborting retry due to graceful stop request.")
                        raise asyncio.CancelledError()
                    item = incomplete_map[ticker]
                    async for evt in self.run_pipeline(
                        f"{root_run_id}:decision-retry:{ticker}",
                        {
                            "ticker": ticker,
                            "date": date,
                            "run_id": root_run_id,
                            "portfolio_context": item.get("portfolio_context", "candidate"),
                            "_execution_key": f"{root_run_id}:decision-retry:{ticker}",
                        },
                    ):
                        yield evt

                remaining_incomplete: list[dict[str, str]] = []
                completed_tickers: list[str] = []
                aborted_tickers: list[str] = []
                for ticker, item in sorted(incomplete_map.items()):
                    analysis = store.load_analysis(date, ticker)
                    status = analysis_status(analysis)
                    if status == "completed":
                        completed_tickers.append(ticker)
                    elif status == "aborted":
                        aborted_tickers.append(ticker)
                    else:
                        remaining_incomplete.append(
                            {
                                "ticker": ticker,
                                "reason": "analysis finished without a completed deep-dive decision"
                                if status == "missing"
                                else f"analysis artifact remained {status}",
                                "portfolio_context": item.get("portfolio_context", "candidate"),
                            }
                        )

                if remaining_incomplete:
                    failed_summary = ", ".join(
                        f"{item['ticker']} ({item['reason']})" for item in remaining_incomplete
                    )
                    yield system_log(
                        "Phase 2/3: paused again before portfolio stage because ticker analyses are still incomplete: "
                        + failed_summary
                    )
                    raise AwaitPhase3Decision(
                        {
                            "date": date,
                            "portfolio_id": portfolio_id,
                            "incomplete_tickers": remaining_incomplete,
                            "completed_tickers": sorted(
                                set((pending.get("completed_tickers") or []) + completed_tickers)
                            ),
                            "aborted_tickers": sorted(
                                set((pending.get("aborted_tickers") or []) + aborted_tickers)
                            ),
                            "scheduler_error": None,
                        }
                    )

            else:
                yield system_log(
                    "Phase 2/3: continuing to Phase 3 without retrying incomplete tickers."
                )

            async for evt in self._run_auto_phase_three(
                root_run_id=root_run_id,
                date=date,
                force=force,
                params={**params, "portfolio_id": portfolio_id, "run_id": root_run_id},
                store=store,
            ):
                yield evt
        finally:
            self._finish_run_logger(execution_key, get_daily_dir(date, root_run_id))
