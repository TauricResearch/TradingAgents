"""Advanced portfolio orchestrator that prioritizes hypotheses and schedules analysts."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from tradingagents.dataflows.interface import route_to_vendor


def create_portfolio_orchestrator(
    llm: Any,
    profile: Dict[str, object],
    context_fetcher: Callable[[List[str]], List[Dict[str, str]]],
    fast_news_fetcher: Callable[[str, str, int, int], Dict[str, str]],
    plan_generator: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
):
    """Create an orchestrator node that generates and manages portfolio hypotheses."""

    profile_name = profile.get("profile_name", "Portfolio")
    mandate = profile.get("mandate", "")
    risk_limits = profile.get("risk_limits", {})
    notes = profile.get("notes", "")
    universe_raw = profile.get("universe", "")
    universe = [symbol.strip().upper() for symbol in universe_raw.split(",") if symbol.strip()]
    sentiment_lookback = profile.get("sentiment_lookback_days", 2)
    headline_limit = profile.get("news_headline_limit", 5)
    market_lookback = profile.get("market_data_lookback_days", 30)
    trade_policy = profile.get("trade_activation", {})
    threshold = profile.get("hypothesis_threshold", 0.6)
    max_hypotheses = profile.get("max_concurrent_hypotheses", 2)

    risk_blurb = (
        f"Max single position: {risk_limits.get('max_single_position_pct', 'n/a')} | "
        f"Max sector: {risk_limits.get('max_sector_pct', 'n/a')}"
    )

    def _parse_account(account_text: str) -> Dict[str, str]:
        summary = {}
        pattern = re.compile(r"^([A-Za-z ]+):\s*\$?([\d\.,\-]+)")
        for line in account_text.splitlines():
            match = pattern.match(line.strip())
            if match:
                key = match.group(1).strip().lower().replace(" ", "_")
                summary[key] = match.group(2).strip()
        return summary

    def _parse_positions(positions_text: str) -> List[Dict[str, str]]:
        positions: List[Dict[str, str]] = []
        current: Dict[str, str] = {}
        for line in positions_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("Symbol:"):
                if current:
                    positions.append(current)
                    current = {}
            if ":" in line:
                key, value = line.split(":", 1)
                current[key.strip().lower().replace(" ", "_")] = value.strip()
        if current:
            positions.append(current)
        return positions

    def _to_float(value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return 0.0
        cleaned = text.replace("$", "").replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    def orchestrator_node(state):
        override_symbols_raw = state.get("orchestrator_focus_override") or []
        override_symbols = [str(sym).upper() for sym in override_symbols_raw if str(sym).strip()]

        if override_symbols:
            symbols = override_symbols.copy()
        else:
            symbols = [sym.upper() for sym in dict.fromkeys(universe)]
        pending_override = [str(sym).upper() for sym in state.get("orchestrator_pending_tickers", []) if sym]
        incumbent = state.get("company_of_interest")
        if incumbent and incumbent.upper() not in symbols:
            symbols.append(incumbent.upper())

        # Step 1: Gather live portfolio context for the universe
        snapshots = context_fetcher(symbols)
        quick_signals: Dict[str, Dict[str, str]] = {
            str(key).upper(): value for key, value in (state.get("orchestrator_quick_signals", {}) or {}).items()
        }
        market_data_cache: Dict[str, str] = {
            str(key).upper(): value for key, value in (state.get("orchestrator_market_data", {}) or {}).items()
        }

        first_snapshot = snapshots[0] if snapshots else {}
        # Step 3: Ask the LLM to synthesize hypotheses and routing plan
        system_prompt = (
            "You are the head of trading. Review portfolio context, mandate, and quick signals to propose trading "
            "hypotheses. Each hypothesis must include: ticker, rationale, priority (0-1), required_analysts list (subset "
            "of ['market','social','news','fundamentals']), and immediate actions (monitor, abandon, escalate). Limit to the "
            f"strongest {max_hypotheses} hypotheses above priority {threshold}. Respond with valid JSON containing keys "
            "'hypotheses' (list), 'summary' (string), and 'status' (string)."
        )

        account_summary = _parse_account(first_snapshot.get("account", "")) if first_snapshot else {}
        positions_summary = _parse_positions(first_snapshot.get("positions", "")) if first_snapshot else []
        buying_power_value = _to_float(account_summary.get("buying_power") or account_summary.get("buying_power_usd"))
        cash_value = _to_float(account_summary.get("cash") or account_summary.get("cash_usd"))
        portfolio_value = _to_float(
            account_summary.get("portfolio_value")
            or account_summary.get("equity")
            or account_summary.get("equity_value")
        )
        current_holdings = set()
        for item in positions_summary:
            symbol = (item.get("symbol") or item.get("symbol:") or "").upper()
            qty_raw = item.get("quantity", "")
            qty_value = 0.0
            if qty_raw:
                match = re.search(r"[-+]?\d*\.?\d+", qty_raw.replace(",", ""))
                if match:
                    try:
                        qty_value = float(match.group(0))
                    except ValueError:
                        qty_value = 0.0
            if symbol and qty_value != 0.0:
                current_holdings.add(symbol)
        universe_gap = [sym for sym in symbols if sym not in current_holdings]

        payload = {
            "profile": {
                "name": profile_name,
                "mandate": mandate,
                "risk_limits": risk_limits,
                "notes": notes,
                "risk_summary": risk_blurb,
            },
            "portfolio_snapshots": snapshots,
            "quick_signals": {},
            "current_hypotheses": state.get("orchestrator_hypotheses", []),
            "account_summary": account_summary,
            "positions": positions_summary,
            "existing_holdings": list(current_holdings),
            "universe_candidates": universe_gap,
            "trade_policy": trade_policy,
        }

        response = llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload)},
            ]
        )

        try:
            parsed = json.loads(response.content if hasattr(response, "content") else str(response))
        except json.JSONDecodeError:
            parsed = {"hypotheses": [], "notes": "Failed to parse orchestrator response."}

        hypotheses_raw = parsed.get("hypotheses", [])[:max_hypotheses]
        if override_symbols:
            allowed = set(override_symbols)
            filtered = [item for item in hypotheses_raw if isinstance(item, dict) and str(item.get("ticker", "")).upper() in allowed]
            if filtered:
                hypotheses = filtered
            else:
                hypotheses = [hypotheses_raw[0]] if hypotheses_raw else []
        else:
            hypotheses = hypotheses_raw
        summary_text = parsed.get("summary") or first_snapshot.get("summary_prompt", "")
        status_text = parsed.get("status") or first_snapshot.get("status", "ok")

        trade_priority_threshold = float(trade_policy.get("priority_threshold", 0.8))
        min_cash_abs = float(trade_policy.get("min_cash_absolute", 0))
        min_cash_ratio = float(trade_policy.get("min_cash_ratio", 0))
        min_cash_required = max(min_cash_abs, portfolio_value * min_cash_ratio)

        if not hypotheses:
            fallback_ticker = None
            if override_symbols:
                fallback_ticker = override_symbols[0]
            elif symbols:
                fallback_ticker = symbols[0]
            elif incumbent:
                fallback_ticker = incumbent.upper()
            elif state.get("company_of_interest"):
                fallback_ticker = str(state.get("company_of_interest")).upper()

            if fallback_ticker:
                fallback_required = ["market", "news", "fundamentals"]
                can_trade = buying_power_value >= min_cash_required
                fallback_action = "trade" if can_trade else "escalate"
                fallback_priority = max(trade_priority_threshold, 0.8)
                fallback = {
                    "ticker": fallback_ticker,
                    "rationale": (
                        f"Generated fallback hypothesis for {fallback_ticker} to evaluate trading opportunities with available buying power "
                        f"of ${buying_power_value:,.0f}. Analysts should validate signals before execution."
                    ),
                    "priority": fallback_priority,
                    "required_analysts": fallback_required,
                    "immediate_actions": fallback_action,
                }
                hypotheses = [fallback]
                if override_symbols and fallback_ticker not in override_symbols:
                    override_symbols.append(fallback_ticker)
                if fallback_ticker not in symbols:
                    symbols.insert(0, fallback_ticker)

        candidate_pool = override_symbols or symbols

        try:
            print(f"[Orchestrator] Override focus: {override_symbols if override_symbols else '<none>'}")
        except Exception:
            pass

        focus_symbols: List[str] = []
        hypothesis_map: Dict[str, Dict[str, Any]] = {}
        for item in hypotheses:
            ticker_value = str(item.get("ticker", "")).upper() if isinstance(item, dict) else ""
            if ticker_value and ticker_value not in focus_symbols:
                focus_symbols.append(ticker_value)
                if isinstance(item, dict):
                    hypothesis_map[ticker_value] = item
            if ticker_value and isinstance(item, dict):
                hypothesis_map.setdefault(ticker_value, item)
        for holding in current_holdings:
            if holding not in focus_symbols:
                focus_symbols.append(holding)
        if incumbent:
            incumbent_u = incumbent.upper()
            if incumbent_u and incumbent_u not in focus_symbols:
                focus_symbols.append(incumbent_u)
        if not focus_symbols:
            focus_symbols = symbols[: max_hypotheses or 1]
        else:
            for symbol in symbols:
                if symbol not in focus_symbols:
                    focus_symbols.append(symbol)

        if pending_override:
            ordered_focus: List[str] = []
            for sym in pending_override:
                if sym in focus_symbols and sym not in ordered_focus:
                    ordered_focus.append(sym)
            for sym in focus_symbols:
                if sym not in ordered_focus:
                    ordered_focus.append(sym)
            focus_symbols = ordered_focus

        try:
            print(f"[Orchestrator] Focus tickers: {', '.join(focus_symbols)}")
        except Exception:  # pragma: no cover - defensive logging
            pass

        if pending_override:
            active_ticker = pending_override[0]
        elif focus_symbols:
            active_ticker = focus_symbols[0]
        else:
            active_ticker = state.get("target_ticker", state.get("company_of_interest", "")).upper()

        active = hypothesis_map.get(active_ticker)
        if active is None and hypotheses:
            fallback = hypotheses[0]
            if isinstance(fallback, dict) and fallback.get("ticker"):
                active_ticker = str(fallback.get("ticker")).upper()
                active = fallback

        scheduled_sequence: List[str] = []
        if active and isinstance(active, dict):
            for analyst in active.get("required_analysts", []):
                role = str(analyst).lower()
                if role not in scheduled_sequence:
                    scheduled_sequence.append(role)
        immediate_action = (active.get("immediate_actions") or active.get("action") or "").lower() if isinstance(active, dict) else ""

        priority_val = float(active.get("priority") or 0) if isinstance(active, dict) else 0.0

        holding_active = active_ticker in current_holdings
        if isinstance(active, dict) and immediate_action in {"", "monitor"}:
            if priority_val >= trade_priority_threshold:
                if not holding_active and buying_power_value >= min_cash_required:
                    immediate_action = "trade"
                    active["immediate_actions"] = "trade"
                else:
                    immediate_action = "escalate"
                    active["immediate_actions"] = "escalate"

        default_analysis_order = ["market", "news", "social", "fundamentals"]
        analysis_candidates = [
            item for item in scheduled_sequence if item in {"market", "social", "news", "fundamentals"}
        ]
        try:
            if analysis_candidates:
                print(f"[Orchestrator] Hypothesis requests analysts {analysis_candidates} for {active_ticker}.")
            else:
                print(f"[Orchestrator] No explicit analyst order from hypothesis; defaulting to {default_analysis_order}.")
        except Exception:
            pass

        try:
            print(
                f"[Orchestrator] Active {active_ticker or '<none>'} priority {priority_val:.2f} -> {immediate_action.upper()} "
                f"(cash ${cash_value:,.0f}, buying power ${buying_power_value:,.0f}, min cash ${min_cash_required:,.0f})"
            )
        except Exception:
            pass

        planner_raw: Dict[str, Any] = {}
        planner_actions: List[str] = []
        planner_immediate: str = ""
        planner_notes: str = ""
        planner_next_directive: Optional[str] = None
        ticker_plan_summaries: Dict[str, Any] = dict(state.get("orchestrator_ticker_plans", {}) or {})

        ACTION_ALIASES = {
            "market": "market",
            "market_analyst": "market",
            "run_market": "market",
            "run_market_analyst": "market",
            "news": "news",
            "news_analyst": "news",
            "run_news": "news",
            "social": "social",
            "social_analyst": "social",
            "fundamentals": "fundamentals",
            "fundamental": "fundamentals",
            "fundamentals_analyst": "fundamentals",
            "debate": "debate",
            "research_debate": "debate",
            "manager": "manager",
            "research_manager": "manager",
            "trader": "trader",
            "risk": "risk",
            "risk_manager": "risk",
            "orchestrator": "orchestrator",
            "stop": "end",
            "end": "end",
        }

        def normalise_action(value: str) -> Optional[str]:
            key = (value or "").strip().lower()
            return ACTION_ALIASES.get(key)

        def append_unique(target: List[str], items: List[str]) -> None:
            seen = set(target)
            for elem in items:
                if elem not in seen:
                    target.append(elem)
                    seen.add(elem)

        trade_date = state.get("trade_date", "")

        def _coerce_trade_date(value: str) -> date:
            if not value:
                return date.today()
            try:
                dt_value = datetime.fromisoformat(value)
            except ValueError:
                try:
                    dt_value = datetime.fromisoformat(f"{value}T00:00:00")
                except ValueError:
                    dt_value = datetime.today()
            return dt_value.date()

        trade_date_obj = _coerce_trade_date(trade_date)
        start_dt = trade_date_obj - timedelta(days=max(1, int(market_lookback)))
        start_date_str = start_dt.isoformat()
        end_date_str = trade_date_obj.isoformat()

        market_data: Dict[str, str] = dict(market_data_cache)

        for symbol in focus_symbols:
            cache_key = symbol.upper()
            if cache_key not in quick_signals or not quick_signals.get(cache_key):
                try:
                    quick_signals[cache_key] = fast_news_fetcher(symbol, trade_date, sentiment_lookback, headline_limit)
                except Exception as exc:  # pragma: no cover - vendor failure is non-critical
                    quick_signals[cache_key] = {"error": str(exc)}
            if cache_key not in market_data or not market_data.get(cache_key):
                try:
                    market_data[cache_key] = route_to_vendor("get_stock_data", symbol, start_date_str, end_date_str)
                except Exception as exc:  # pragma: no cover - vendor failure is non-critical
                    market_data[cache_key] = f"Error fetching market data: {exc}"

        try:
            print(
                "[Orchestrator] Retrieved market data for: "
                + ", ".join(sorted(market_data.keys()))
            )
        except Exception:  # pragma: no cover - defensive logging
            pass

        existing_plan = ticker_plan_summaries.get(active_ticker or "", {}) if active_ticker else {}
        if plan_generator is not None:
            planner_payload = {
                "profile": payload["profile"],
                "hypotheses": hypotheses,
                "active_hypothesis": active,
                "summary": summary_text,
                "status": status_text,
                "account_summary": account_summary,
                "positions_summary": positions_summary,
                "portfolio_snapshots": snapshots,
                "quick_signals": quick_signals,
                "market_data": market_data,
                "focus_symbols": focus_symbols,
                "focus_symbol": active_ticker,
                "trade_policy": trade_policy,
                "buying_power": buying_power_value,
                "cash_available": cash_value,
                "portfolio_value": portfolio_value,
            }
            if existing_plan:
                planner_raw = existing_plan
            else:
                planner_result = plan_generator(planner_payload) or {}
                if isinstance(planner_result, dict):
                    planner_raw = planner_result
                else:
                    planner_raw = {"text": str(planner_result)}
                ticker_plan_summaries[active_ticker or "<unknown>"] = planner_raw if planner_raw else {}

            if isinstance(planner_raw, dict):
                plan_structured = planner_raw.get("structured")
                planner_notes = planner_raw.get("text") or planner_raw.get("notes", "")
                if plan_structured is None:
                    plan_text = planner_raw.get("text")
                    if plan_text:
                        try:
                            plan_structured = json.loads(plan_text)
                        except json.JSONDecodeError:
                            plan_structured = None
                if plan_structured is None:
                    plan_structured = planner_raw.get("plan")
            else:
                plan_structured = None

            if isinstance(plan_structured, str):
                try:
                    plan_structured = json.loads(plan_structured)
                except json.JSONDecodeError:
                    plan_structured = None

            if isinstance(plan_structured, dict):
                raw_actions = plan_structured.get("actions") or plan_structured.get("steps") or []
                planner_immediate = str(plan_structured.get("next_decision") or "").lower()
                planner_notes = planner_notes or plan_structured.get("notes", "")
                planner_next_directive = plan_structured.get("next_directive")
            elif isinstance(plan_structured, list):
                raw_actions = plan_structured
            else:
                raw_actions = []

            if planner_immediate and not immediate_action:
                immediate_action = planner_immediate

            for item in raw_actions:
                if isinstance(item, str):
                    normalized = normalise_action(item)
                elif isinstance(item, dict):
                    action_value = item.get("action") or item.get("name") or item.get("tool")
                    normalized = normalise_action(str(action_value)) if action_value else None
                    if not planner_notes and item.get("reason"):
                        planner_notes = str(item.get("reason"))
                else:
                    normalized = None
                if normalized:
                    planner_actions.append(normalized)

            for symbol in focus_symbols:
                if symbol == active_ticker:
                    continue
                if override_symbols and symbol not in override_symbols:
                    continue
                extra_payload = {
                    "profile": payload["profile"],
                    "hypotheses": hypotheses,
                    "active_hypothesis": hypothesis_map.get(symbol),
                    "summary": summary_text,
                    "status": status_text,
                    "account_summary": account_summary,
                    "positions_summary": positions_summary,
                    "portfolio_snapshots": snapshots,
                    "quick_signals": quick_signals,
                    "market_data": market_data,
                    "focus_symbols": focus_symbols,
                    "focus_symbol": symbol,
                    "trade_policy": trade_policy,
                    "buying_power": buying_power_value,
                    "cash_available": cash_value,
                    "portfolio_value": portfolio_value,
                }
                if symbol in ticker_plan_summaries and ticker_plan_summaries[symbol]:
                    continue
                try:
                    extra_result = plan_generator(extra_payload) or {}
                except Exception as exc:  # pragma: no cover - planner failures shouldn't halt orchestration
                    extra_result = {"error": str(exc)}
                if isinstance(extra_result, dict):
                    ticker_plan_summaries[symbol] = extra_result
                else:
                    ticker_plan_summaries[symbol] = {"text": str(extra_result)}

        action_queue: List[str] = []
        if planner_actions:
            append_unique(action_queue, planner_actions)
            try:
                print(f"[Orchestrator] Sequential planner actions for {active_ticker}: {planner_actions}")
            except Exception:
                pass
        else:
            append_unique(action_queue, analysis_candidates or default_analysis_order)

        if immediate_action in {"escalate", "trade", "execute"}:
            append_unique(action_queue, ["debate"])
            append_unique(action_queue, ["manager"])
            append_unique(action_queue, ["trader"])
            if immediate_action in {"trade", "execute"}:
                append_unique(action_queue, ["risk"])

        next_directive_value = planner_next_directive or "end"
        if override_symbols:
            remaining_focus = []
            next_directive_value = "end"
        else:
            remaining_focus = [sym for sym in focus_symbols if sym != active_ticker]
            if remaining_focus and next_directive_value == "end":
                next_directive_value = "orchestrator"

        try:
            print(
                "[Orchestrator] Queue:"
                f" focus={focus_symbols} | active={active_ticker} | immediate={immediate_action} | queue={action_queue}"
            )
            print(
                "[Orchestrator] Ticker plans generated for: "
                + ", ".join(sorted(ticker_plan_summaries.keys()))
            )
        except Exception:  # pragma: no cover - defensive logging
            pass

        # Log initial hypothesis for debugging
        try:
            formatted = json.dumps(
                {
                    "hypotheses": hypotheses,
                    "summary": summary_text,
                    "status": status_text,
                    "action": immediate_action,
                    "queue": action_queue,
                    "planner_plan": planner_raw,
                },
                indent=2,
            )
            print(f"[Orchestrator] Initial hypotheses:\n{formatted}")
        except Exception:
            pass

        analyst_schedule = [item for item in action_queue if item in {"market", "social", "news", "fundamentals"}]
        if planner_actions:
            plan_snapshot = planner_actions
        else:
            plan_snapshot = analysis_candidates or [item for item in default_analysis_order if item in action_queue]

        serializable_plan = planner_raw
        if isinstance(planner_raw, dict):
            serializable_plan = {k: v for k, v in planner_raw.items() if k != "raw"}
            if "raw" in planner_raw:
                try:
                    serializable_plan.setdefault("raw_repr", repr(planner_raw["raw"]))
                except Exception:
                    serializable_plan.setdefault("raw_repr", "<non-serializable>")

        state_update = {
            "messages": [response],
            "portfolio_profile": profile,
            "portfolio_summary": summary_text,
            "orchestrator_status": status_text,
            "alpaca_account_text": first_snapshot.get("account", ""),
            "alpaca_positions_text": first_snapshot.get("positions", ""),
            "alpaca_orders_text": first_snapshot.get("orders", ""),
            "orchestrator_hypotheses": hypotheses,
            "active_hypothesis": active,
            "scheduled_analysts": analyst_schedule,
            "scheduled_analysts_plan": plan_snapshot,
            "company_of_interest": active_ticker or state.get("company_of_interest"),
            "target_ticker": active_ticker,
            "orchestrator_action": immediate_action,
            "portfolio_account_summary": account_summary,
            "portfolio_positions_summary": positions_summary,
            "orchestrator_focus_symbols": focus_symbols,
            "orchestrator_quick_signals": quick_signals,
            "orchestrator_market_data": market_data,
            "orchestrator_ticker_plans": ticker_plan_summaries,
            "orchestrator_pending_tickers": remaining_focus,
            "orchestrator_buying_power": buying_power_value,
            "orchestrator_cash_available": cash_value,
            "orchestrator_portfolio_value": portfolio_value,
            "action_queue": action_queue,
            "next_directive": next_directive_value,
            "planner_plan": serializable_plan,
            "planner_notes": planner_notes,
            "orchestrator_focus_override": override_symbols,
        }

        return state_update

    return orchestrator_node
