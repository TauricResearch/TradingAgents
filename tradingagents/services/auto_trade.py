from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from tradingagents.graph.propagation import Propagator
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.services.account import AccountSnapshot


@dataclass
class SequentialPlan:
    actions: List[str]
    next_decision: str
    notes: str
    reasoning: List[str] = field(default_factory=list)


@dataclass
class StrategyDirective:
    name: str
    horizon_hours: float
    target_pct: float
    stop_pct: float
    success_metric: str
    failure_metric: str
    follow_up: str = "reevaluate"
    urgency: str = "medium"
    deadline: Optional[str] = ""
    notes: str = ""
    success_price: Optional[float] = None
    failure_price: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "horizon_hours": self.horizon_hours,
            "target_pct": self.target_pct,
            "stop_pct": self.stop_pct,
            "success_metric": self.success_metric,
            "failure_metric": self.failure_metric,
            "follow_up": self.follow_up,
            "urgency": self.urgency,
            "deadline": self.deadline,
            "notes": self.notes,
            "success_price": self.success_price,
            "failure_price": self.failure_price,
        }


@dataclass
class TickerDecision:
    ticker: str
    hypothesis: Dict[str, Any]
    sequential_plan: SequentialPlan
    action_queue: List[str]
    immediate_action: str
    priority: float
    final_decision: str = ""
    trader_plan: str = ""
    final_notes: str = ""
    strategy: StrategyDirective = None  # type: ignore

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "hypothesis": self.hypothesis,
            "sequential_plan": {
                "actions": self.sequential_plan.actions,
                "next_decision": self.sequential_plan.next_decision,
                "notes": self.sequential_plan.notes,
                "reasoning": self.sequential_plan.reasoning,
            },
            "action_queue": self.action_queue,
            "immediate_action": self.immediate_action,
            "priority": self.priority,
            "final_decision": self.final_decision,
            "trader_plan": self.trader_plan,
            "final_notes": self.final_notes,
            "strategy": self.strategy.to_dict() if self.strategy else None,
        }


@dataclass
class AutoTradeResult:
    focus_tickers: List[str]
    decisions: List[TickerDecision]
    account_snapshot: AccountSnapshot
    raw_state: Dict[str, Any]

    def summary(self) -> Dict[str, Any]:
        return {
            "focus_tickers": self.focus_tickers,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "buying_power": self.account_snapshot.buying_power(),
            "cash": self.account_snapshot.cash(),
            "portfolio_value": self.account_snapshot.portfolio_value(),
            "fetched_at": self.account_snapshot.fetched_at.isoformat(),
        }


class AutoTradeService:
    """High level orchestration of the auto-trade workflow."""

    def __init__(
        self,
        config: Dict[str, Any],
        graph: Optional[TradingAgentsGraph] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config = config
        self.graph = graph or TradingAgentsGraph(config=config)
        self.logger = logger or logging.getLogger(__name__)
        self.propagator: Propagator = getattr(self.graph, "propagator", Propagator())

    def run(
        self,
        snapshot: AccountSnapshot,
        *,
        focus_override: Optional[List[str]] = None,
        allow_market_closed: bool = False,
    ) -> AutoTradeResult:
        """Execute the auto-trade workflow using the provided account snapshot."""

        auto_trade_cfg = self.config.get("auto_trade", {}) or {}
        skip_when_market_closed = bool(auto_trade_cfg.get("skip_when_market_closed"))
        if skip_when_market_closed and not allow_market_closed:
            checker = getattr(self.graph, "check_market_status", None)
            status = checker() if callable(checker) else None
            if status and not status.get("is_open", False):
                clock_text = status.get("clock_text")
                message = (
                    "Auto-trade skipped: market is currently closed. "
                    "Set AUTO_TRADE_SKIP_WHEN_MARKET_CLOSED=false to override."
                )
                if clock_text:
                    message = f"{message}\n{clock_text.strip()}"
                elif status.get("reason"):
                    message = f"{message}\nReason: {status['reason']}"
                self.logger.info(message)
                return AutoTradeResult(
                    focus_tickers=[],
                    decisions=[],
                    account_snapshot=snapshot,
                    raw_state={
                        "skip_reason": message,
                        "market_clock": clock_text,
                    },
                )

        mode = str(auto_trade_cfg.get("mode") or "graph").lower()
        if mode == "responses":
            from .responses_auto_trade import ResponsesAutoTradeService

            responses_service = ResponsesAutoTradeService(
                config=self.config,
                graph=self.graph,
                logger=self.logger,
            )
            result = responses_service.run(snapshot, focus_override=focus_override)
            if hasattr(self.graph, "clear_manual_portfolio_snapshot"):
                try:
                    self.graph.clear_manual_portfolio_snapshot()  # type: ignore[attr-defined]
                except Exception:
                    pass
            return result

        if hasattr(self.graph, "set_manual_portfolio_snapshot"):
            try:
                self.graph.set_manual_portfolio_snapshot(snapshot)  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - defensive
                self.logger.debug("Unable to seed manual portfolio snapshot", exc_info=True)

        seed_symbols = focus_override or self._determine_focus_tickers(snapshot)
        worklist = list(dict.fromkeys((symbol or "").upper() for symbol in seed_symbols if symbol))
        if not worklist:
            worklist = ["SPY"]

        max_runs = auto_trade_cfg.get("max_tickers")
        try:
            max_runs_int = int(max_runs) if max_runs is not None else 12
        except (TypeError, ValueError):
            max_runs_int = 12
        if max_runs_int <= 0:
            max_runs_int = len(worklist) or 1

        decisions: List[TickerDecision] = []
        raw_state: Dict[str, Any] = {}
        visited: Set[str] = set()
        discovered_order: List[str] = []
        discovered_seen: Set[str] = set()
        cached_quick_signals: Dict[str, Any] = {}
        cached_market_data: Dict[str, Any] = {}
        cached_ticker_plans: Dict[str, Any] = {}
        cached_pending: List[str] = []

        while worklist and len(visited) < max_runs_int:
            ticker = (worklist.pop(0) or "").upper()
            if not ticker or ticker in visited:
                continue

            initial_overrides: Dict[str, Any] = {}
            if cached_quick_signals:
                initial_overrides["orchestrator_quick_signals"] = dict(cached_quick_signals)
            if cached_market_data:
                initial_overrides["orchestrator_market_data"] = dict(cached_market_data)
            if cached_ticker_plans:
                initial_overrides["orchestrator_ticker_plans"] = dict(cached_ticker_plans)
            if cached_pending:
                initial_overrides["orchestrator_pending_tickers"] = list(cached_pending)
            if discovered_order:
                initial_overrides["orchestrator_focus_symbols"] = list(discovered_order)
            initial_overrides["orchestrator_focus_override"] = [ticker]

            overrides = initial_overrides or None

            try:
                final_state, processed = self.graph.propagate(
                    ticker,
                    date.today().isoformat(),
                    initial_overrides=overrides,
                )
            except Exception as exc:  # pragma: no cover - surfaced to CLI
                self.logger.exception("Graph propagation failed for %s", ticker)
                raw_state[ticker] = {"error": str(exc)}
                visited.add(ticker)
                continue

            raw_state[ticker] = {
                "final_state": final_state,
                "processed": processed,
            }

            try:
                decision = self._decision_from_state(ticker, final_state, processed)
                decisions.append(decision)
                if decision.ticker not in discovered_seen:
                    discovered_order.append(decision.ticker)
                    discovered_seen.add(decision.ticker)
            except Exception as exc:  # pragma: no cover - best-effort diagnostics
                self.logger.exception("Failed to build decision for %s", ticker)
            finally:
                visited.add(ticker)

            new_symbols = self._extract_focus_symbols(final_state)
            for sym in new_symbols:
                if sym not in discovered_seen:
                    discovered_order.append(sym)
                    discovered_seen.add(sym)
                if sym and sym not in visited and sym not in worklist:
                    worklist.append(sym)

            quick_signals_state = final_state.get("orchestrator_quick_signals") or {}
            if isinstance(quick_signals_state, dict):
                for key, value in quick_signals_state.items():
                    key_u = str(key).upper()
                    if value:
                        cached_quick_signals[key_u] = value

            market_data_state = final_state.get("orchestrator_market_data") or {}
            if isinstance(market_data_state, dict):
                for key, value in market_data_state.items():
                    key_u = str(key).upper()
                    if value:
                        cached_market_data[key_u] = value

            ticker_plans_state = final_state.get("orchestrator_ticker_plans") or {}
            if isinstance(ticker_plans_state, dict):
                for key, value in ticker_plans_state.items():
                    key_u = str(key).upper()
                    if value:
                        cached_ticker_plans[key_u] = value

            pending_state = final_state.get("orchestrator_pending_tickers") or []
            if isinstance(pending_state, list):
                cached_pending = [str(item).upper() for item in pending_state if str(item).strip()]

        focus_tickers = list(dict.fromkeys(discovered_order))
        if not focus_tickers:
            focus_tickers = list(dict.fromkeys(decision.ticker for decision in decisions))
        if not focus_tickers:
            focus_tickers = worklist[:]
        if not focus_tickers:
            focus_tickers = list(dict.fromkeys((symbol or "").upper() for symbol in seed_symbols if symbol)) or ["SPY"]

        if hasattr(self.graph, "clear_manual_portfolio_snapshot"):
            try:
                self.graph.clear_manual_portfolio_snapshot()  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - defensive
                pass

        return AutoTradeResult(
            focus_tickers=focus_tickers,
            decisions=decisions,
            account_snapshot=snapshot,
            raw_state=raw_state,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _determine_focus_tickers(self, snapshot: AccountSnapshot) -> List[str]:
        universe_raw = self.config.get("portfolio_orchestrator", {}).get("universe", "")
        universe = [sym.strip().upper() for sym in universe_raw.split(",") if sym.strip()]
        holdings = snapshot.position_symbols()
        combined: List[str] = []
        for symbol in list(dict.fromkeys(universe + holdings)):
            if symbol:
                combined.append(symbol)
        return combined or ["SPY"]

    def _decision_from_state(
        self,
        requested_ticker: str,
        final_state: Dict[str, Any],
        processed: Dict[str, Any],
    ) -> TickerDecision:
        focus_symbol = str(final_state.get("target_ticker") or requested_ticker or "").upper()
        hypotheses = final_state.get("orchestrator_hypotheses") or []
        active = final_state.get("active_hypothesis") or {}
        hypothesis = _select_hypothesis_for_ticker(focus_symbol, hypotheses, active)

        plans = final_state.get("orchestrator_ticker_plans")
        plan_raw = plans.get(focus_symbol) if isinstance(plans, dict) else None
        if plan_raw is None and isinstance(plans, dict):
            plan_raw = plans.get(requested_ticker.upper())
        actions, next_decision, plan_notes, reasoning = self._parse_plan(plan_raw)

        immediate_action = str(
            final_state.get("orchestrator_action")
            or hypothesis.get("immediate_actions")
            or next_decision
            or ""
        ).strip().lower()
        if not immediate_action:
            immediate_action = "monitor"
        if not next_decision:
            next_decision = immediate_action

        try:
            priority = float(hypothesis.get("priority") or 0.0)
        except (TypeError, ValueError):
            priority = 0.0

        action_queue = self._string_list(final_state.get("action_queue"), lower=True)

        processed_decision = processed.get("decision") if isinstance(processed, dict) else None
        final_decision = str(processed_decision or "").strip().upper()
        if not final_decision and immediate_action:
            final_decision = immediate_action.upper()
        if final_decision == "PLEASE PROVIDE THE PARAGRAPH OR FINANCIAL REPORT FOR ANALYSIS.":
            final_decision = immediate_action.upper()
        final_trade_text = str(final_state.get("final_trade_decision") or "").strip()
        if final_trade_text:
            if final_decision and final_trade_text.lower() not in final_decision.lower():
                final_decision = f"{final_decision} | {final_trade_text}"
            elif not final_decision:
                final_decision = final_trade_text

        trader_plan = str(
            final_state.get("trader_investment_plan")
            or final_state.get("investment_plan")
            or ""
        ).strip()

        notes_parts: List[str] = []
        for key in ("portfolio_summary", "planner_notes"):
            value = final_state.get(key)
            if value:
                notes_parts.append(str(value).strip())
        if plan_notes:
            notes_parts.append(plan_notes)
        execution = processed.get("execution") if isinstance(processed, dict) else None
        if execution:
            notes_parts.append("Execution: " + json.dumps(execution, default=str))
        final_notes = "\n\n".join(dict.fromkeys(part for part in notes_parts if part))

        sequential_plan = SequentialPlan(
            actions=actions,
            next_decision=next_decision,
            notes=plan_notes,
            reasoning=reasoning,
        )

        strategy_raw = final_state.get("orchestrator_strategy") or hypothesis.get("strategy")
        strategy = resolve_strategy_directive(self.config, strategy_raw)

        return TickerDecision(
            ticker=focus_symbol or requested_ticker.upper(),
            hypothesis=hypothesis,
            sequential_plan=sequential_plan,
            action_queue=action_queue,
            immediate_action=immediate_action,
            priority=priority,
            final_decision=final_decision,
            trader_plan=trader_plan,
            final_notes=final_notes,
            strategy=strategy,
        )

    def _parse_plan(self, plan_raw: Any) -> Tuple[List[str], str, str, List[str]]:
        actions: List[str] = []
        next_decision = ""
        notes = ""
        reasoning: List[str] = []

        structured: Any = None
        if isinstance(plan_raw, dict):
            structured = plan_raw.get("structured")
            if structured is None and any(key in plan_raw for key in ("actions", "steps", "reasoning", "next_decision")):
                structured = {
                    key: plan_raw.get(key)
                    for key in ("actions", "steps", "reasoning", "next_decision", "notes")
                    if plan_raw.get(key) is not None
                }
            if structured is None:
                structured = self._extract_json_candidate(plan_raw.get("text") or plan_raw.get("plan"))
        elif isinstance(plan_raw, str):
            structured = self._extract_json_candidate(plan_raw)

        if isinstance(structured, dict):
            actions = self._string_list(structured.get("actions") or structured.get("steps"), lower=True)
            next_decision = str(structured.get("next_decision") or "").strip().lower()
            notes = str(structured.get("notes") or notes or "")
            reasoning = self._string_list(structured.get("reasoning"))
        elif isinstance(structured, list):
            actions = self._string_list(structured, lower=True)

        if not actions and isinstance(plan_raw, dict):
            actions = self._string_list(plan_raw.get("actions"), lower=True)

        if not notes and isinstance(plan_raw, dict):
            note_candidate = plan_raw.get("notes") or plan_raw.get("text") or plan_raw.get("error")
            if isinstance(note_candidate, str):
                notes = note_candidate.strip()

        if not reasoning and isinstance(plan_raw, dict):
            reasoning = self._string_list(plan_raw.get("reasoning"))

        return actions, next_decision, notes, reasoning

    @staticmethod
    def _extract_json_candidate(text: Optional[str]) -> Optional[Any]:
        if not text or not isinstance(text, str):
            return None
        candidate = text.strip()
        if not candidate:
            return None
        if candidate.startswith("```"):
            parts = candidate.split("```")
            for part in parts:
                segment = part.strip()
                if not segment:
                    continue
                try:
                    return json.loads(segment)
                except json.JSONDecodeError:
                    continue
            return None
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _string_list(value: Any, *, lower: bool = False) -> List[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            iterable = list(value)
        else:
            iterable = [value]

        result: List[str] = []
        for item in iterable:
            if item is None:
                continue
            if isinstance(item, dict):
                text_value = (
                    item.get("action")
                    or item.get("name")
                    or item.get("tool")
                    or item.get("role")
                    or item.get("value")
                )
                text = str(text_value or "").strip()
            else:
                text = str(item).strip()
            if not text:
                continue
            result.append(text.lower() if lower else text)
        return result

    @staticmethod
    def _as_iterable(value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            return list(value)
        return [value]

    def _extract_focus_symbols(self, final_state: Dict[str, Any]) -> List[str]:
        collected: List[str] = []
        seen: Set[str] = set()

        def push(symbol: Any) -> None:
            text = str(symbol or "").strip().upper()
            if text and text not in seen:
                seen.add(text)
                collected.append(text)

        push(final_state.get("target_ticker"))
        push(final_state.get("company_of_interest"))
        active = final_state.get("active_hypothesis")
        if isinstance(active, dict):
            push(active.get("ticker"))

        for key in ("orchestrator_focus_symbols", "orchestrator_pending_tickers"):
            for item in self._as_iterable(final_state.get(key)):
                if isinstance(item, dict):
                    push(item.get("ticker"))
                else:
                    push(item)

        return collected


def _select_hypothesis_for_ticker(
    ticker: str,
    hypotheses: List[Dict[str, Any]],
    active: Dict[str, Any],
) -> Dict[str, Any]:
    ticker = ticker.upper()
    if str(active.get("ticker") or "").upper() == ticker:
        return active
    for hypothesis in hypotheses:
        if str(hypothesis.get("ticker") or "").upper() == ticker:
            return hypothesis
    return active


def resolve_strategy_directive(
    config: Dict[str, Any],
    overrides: Optional[Any] = None,
) -> StrategyDirective:
    strategies_cfg = config.get("trading_strategies", {}) or {}
    presets = strategies_cfg.get("presets", {}) or {}

    if isinstance(overrides, dict):
        overrides_dict = overrides
    elif isinstance(overrides, str):
        overrides_dict = {"name": overrides}
    else:
        overrides_dict = {}

    def _preset_fallback() -> Dict[str, Any]:
        default_key = str(strategies_cfg.get("default") or "").lower()
        if default_key and default_key in presets:
            return presets[default_key]
        if "swing" in presets:
            return presets["swing"]
        if presets:
            return next(iter(presets.values()))
        return {}

    preset_name = str(overrides_dict.get("name") or strategies_cfg.get("default") or "swing").lower()
    preset = presets.get(preset_name) or _preset_fallback()

    def _resolve_value(key: str, default: Any) -> Any:
        value = overrides_dict.get(key)
        if value not in (None, ""):
            return value
        if preset and preset.get(key) not in (None, ""):
            return preset[key]
        return default

    horizon_hours = float(_resolve_value("horizon_hours", 72))
    target_pct = float(_resolve_value("target_pct", 0.03))
    stop_pct = float(_resolve_value("stop_pct", 0.015))
    follow_up = str(_resolve_value("follow_up", "reevaluate"))
    urgency = str(_resolve_value("urgency", "medium"))
    success_metric = str(
        _resolve_value(
            "success_metric",
            f"Gain at least +{target_pct * 100:.1f}% within {horizon_hours:.0f}h",
        )
    )
    failure_metric = str(
        _resolve_value(
            "failure_metric",
            f"Drawdown of -{stop_pct * 100:.1f}% or thesis invalidated before {horizon_hours:.0f}h",
        )
    )
    notes = str(_resolve_value("notes", ""))

    deadline = _resolve_value("deadline", "")
    if not deadline:
        deadline_dt = datetime.utcnow() + timedelta(hours=horizon_hours)
        deadline = deadline_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    success_price = overrides_dict.get("success_price")
    failure_price = overrides_dict.get("failure_price")
    try:
        success_price = float(success_price) if success_price is not None else None
    except (TypeError, ValueError):
        success_price = None
    try:
        failure_price = float(failure_price) if failure_price is not None else None
    except (TypeError, ValueError):
        failure_price = None

    return StrategyDirective(
        name=preset_name,
        horizon_hours=horizon_hours,
        target_pct=target_pct,
        stop_pct=stop_pct,
        success_metric=success_metric,
        failure_metric=failure_metric,
        follow_up=follow_up,
        urgency=urgency,
        deadline=str(deadline),
        notes=notes,
        success_price=success_price,
        failure_price=failure_price,
    )
