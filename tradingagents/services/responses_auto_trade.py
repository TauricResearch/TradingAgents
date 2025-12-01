from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import logging

from langchain_core.messages import HumanMessage
from openai import OpenAI
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.services.account import AccountSnapshot
from tradingagents.services.auto_trade import (
    AutoTradeResult,
    SequentialPlan,
    TickerDecision,
    StrategyDirective,
    resolve_strategy_directive,
)
from tradingagents.services.memory import TickerMemoryStore
from tradingagents.agents.analysts.market_analyst import create_market_analyst
from tradingagents.agents.analysts.news_analyst import create_news_analyst
from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst


def _extract_json_block(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    snippet = text.strip()
    if snippet.startswith("```"):
        parts = snippet.split("```")
        for part in parts:
            candidate = part.strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue
        return {}
    if snippet.startswith("{") and snippet.endswith("}"):
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            return {}
    # Fallback: scan for first JSON object within the text
    decoder = json.JSONDecoder()
    for idx, char in enumerate(snippet):
        if char == "{":
            try:
                data, _ = decoder.raw_decode(snippet[idx:])
                return data
            except json.JSONDecodeError:
                continue
    return {}


def _trimmed_json(payload: Any, *, limit: int = 400) -> str:
    try:
        text = json.dumps(payload, default=str)
    except Exception:
        text = str(payload)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


@dataclass
class ResponsesTool:
    name: str
    description: str
    schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], Dict[str, Any]]

    def spec(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.schema,
        }


class TradingToolbox:
    """Wrap the existing TradingAgents capabilities as Responses-ready tools."""

    def __init__(
        self,
        config: Dict[str, Any],
        graph: TradingAgentsGraph,
        snapshot: AccountSnapshot,
        logger: Optional[logging.Logger] = None,
        memory_store: Optional[TickerMemoryStore] = None,
    ) -> None:
        self.config = config
        self.graph = graph
        self.snapshot = snapshot
        self.logger = logger or logging.getLogger(__name__)
        self.memory_store = memory_store
        self._agent_runners = self._init_agent_runners()
        self._trade_tool_enabled = bool(
            (self.config.get("auto_trade", {}) or {}).get("responses_enable_trade_tool")
        )
        self._tools = self._build_tools()

    @property
    def specs(self) -> List[Dict[str, Any]]:
        return [tool.spec() for tool in self._tools.values()]

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self._tools:
            raise ValueError(f"Unknown tool requested: {name}")
        if self.logger:
            self.logger.debug("Responses tool call: %s args=%s", name, arguments)
        return self._tools[name].handler(arguments or {})

    def _build_tools(self) -> Dict[str, ResponsesTool]:
        tools: Dict[str, ResponsesTool] = {
            "get_account_overview": ResponsesTool(
                name="get_account_overview",
                description="Return the cached Alpaca account, position, and order snapshots for context.",
                schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=lambda _: {
                    "fetched_at": self.snapshot.fetched_at.isoformat(),
                    "account_text": self.snapshot.account_text,
                    "positions_text": self.snapshot.positions_text,
                    "orders_text": self.snapshot.orders_text,
                },
            ),
            "list_focus_tickers": ResponsesTool(
                name="list_focus_tickers",
                description="Return the configured trading universe merged with current holdings.",
                schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=lambda _: {
                    "universe": self._determine_focus_tickers(),
                },
            ),
            "fetch_market_data": ResponsesTool(
                name="fetch_market_data",
                description="Fetch OHLCV market data for a symbol over the requested lookback window (days).",
                schema={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "lookback_days": {"type": "integer", "minimum": 1, "default": 30},
                    },
                    "required": ["symbol"],
                    "additionalProperties": False,
                },
                handler=self._tool_fetch_market_data,
            ),
            "fetch_company_news": ResponsesTool(
                name="fetch_company_news",
                description="Fetch recent company-specific news articles for a symbol.",
                schema={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "lookback_days": {"type": "integer", "minimum": 1, "default": 5},
                    },
                    "required": ["symbol"],
                    "additionalProperties": False,
                },
                handler=self._tool_fetch_company_news,
            ),
            "fetch_global_news": ResponsesTool(
                name="fetch_global_news",
                description="Fetch macro/global news context for the requested lookback horizon.",
                schema={
                    "type": "object",
                    "properties": {
                        "lookback_days": {"type": "integer", "minimum": 1, "default": 3},
                        "limit": {"type": "integer", "minimum": 1, "default": 5},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
                handler=self._tool_fetch_global_news,
            ),
            "fetch_indicators": ResponsesTool(
                name="fetch_indicators",
                description="Fetch technical indicators for a symbol. Indicators should be provided as a list of canonical names (e.g., rsi, close_50_sma).",
                schema={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "indicators": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": ["rsi", "close_50_sma", "close_200_sma"],
                        },
                        "lookback_days": {"type": "integer", "minimum": 1, "default": 30},
                    },
                    "required": ["symbol"],
                    "additionalProperties": False,
                },
                handler=self._tool_fetch_indicators,
            ),
        }
        if self._trade_tool_enabled:
            tools["submit_trade_order"] = ResponsesTool(
                name="submit_trade_order",
                description=(
                    "Submit a trade directive (BUY/SELL/HOLD) for a ticker with optional sizing. Honors dry-run and market-open checks. "
                    "Provide quantity in shares when you can; otherwise pass notional and a reference price to convert."
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "action": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
                        "quantity": {
                            "type": "number",
                            "description": "Number of shares to trade (preferred).",
                        },
                        "notional": {
                            "type": "number",
                            "description": "Dollar amount to allocate; requires reference_price for conversion.",
                        },
                        "reference_price": {
                            "type": "number",
                            "description": "Price used to convert notional to shares; use your latest fetch_market_data/fetch_indicators price.",
                        },
                        "notes": {"type": "string"},
                    },
                    "required": ["symbol", "action"],
                    "additionalProperties": False,
                },
                handler=self._tool_submit_trade,
            )
        if self.memory_store and self.memory_store.is_enabled():
            tools["get_ticker_memory"] = ResponsesTool(
                name="get_ticker_memory",
                description="Retrieve recent decision memory for a ticker.",
                schema={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "default": self.memory_store.max_entries},
                    },
                    "required": ["symbol"],
                    "additionalProperties": False,
                },
                handler=self._tool_get_memory,
            )
        for agent_key in (self._agent_runners or {}):
            tool_name = f"run_{agent_key}_analyst"
            tools[tool_name] = ResponsesTool(
                name=tool_name,
                description=f"Run the {agent_key} analyst to produce a detailed report for a ticker.",
                schema={
                    "type": "object",
                    "properties": {"symbol": {"type": "string"}},
                    "required": ["symbol"],
                    "additionalProperties": False,
                },
                handler=lambda args, agent=agent_key: self._tool_run_agent(agent, args or {}),
            )
        return tools

    def _determine_focus_tickers(self) -> List[str]:
        universe_raw = self.config.get("portfolio_orchestrator", {}).get("universe", "")
        universe = [sym.strip().upper() for sym in universe_raw.split(",") if sym.strip()]
        holdings = self.snapshot.position_symbols()
        combined: List[str] = []
        for symbol in list(dict.fromkeys(universe + holdings)):
            if symbol:
                combined.append(symbol)
        return combined or ["SPY"]

    def _tool_fetch_market_data(self, args: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(args.get("symbol") or "").upper()
        lookback_days = int(args.get("lookback_days") or 30)
        end_date = date.today()
        start_date = end_date - timedelta(days=max(lookback_days, 1))
        payload = route_to_vendor("get_stock_data", symbol, start_date.isoformat(), end_date.isoformat())
        return {"symbol": symbol, "start": start_date.isoformat(), "end": end_date.isoformat(), "data": payload}

    def _tool_fetch_company_news(self, args: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(args.get("symbol") or "").upper()
        lookback_days = int(args.get("lookback_days") or 5)
        end_date = date.today()
        start_date = end_date - timedelta(days=max(lookback_days, 1))
        payload = route_to_vendor("get_news", symbol, start_date.isoformat(), end_date.isoformat())
        return {
            "symbol": symbol,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "data": payload,
        }
    def _tool_fetch_global_news(self, args: Dict[str, Any]) -> Dict[str, Any]:
        lookback_days = int(args.get("lookback_days") or 3)
        limit = int(args.get("limit") or 5)
        payload = route_to_vendor("get_global_news", date.today().isoformat(), lookback_days, limit)
        return {"lookback_days": lookback_days, "limit": limit, "data": payload}

    def _tool_fetch_indicators(self, args: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(args.get("symbol") or "").upper()
        lookback_days = int(args.get("lookback_days") or 30)
        indicators = args.get("indicators") or []
        if not indicators:
            indicators = ["rsi", "close_50_sma", "close_200_sma"]
        end_date = date.today().isoformat()
        payloads: Dict[str, Any] = {}
        for indicator_name in indicators:
            try:
                payloads[indicator_name] = route_to_vendor(
                    "get_indicators",
                    symbol,
                    indicator_name,
                    end_date,
                    lookback_days,
                )
            except Exception as exc:
                payloads[indicator_name] = {"error": str(exc)}
        return {
            "symbol": symbol,
            "indicators": indicators,
            "as_of": end_date,
            "lookback_days": lookback_days,
            "data": payloads,
        }

    def _tool_submit_trade(self, args: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(args.get("symbol") or "").upper()
        action = str(args.get("action") or "").upper()
        quantity = args.get("quantity")
        notional = args.get("notional")
        reference_price = args.get("reference_price")
        status = self.graph.check_market_status()
        market_open = bool(status.get("is_open", True))
        if not market_open:
            return {
                "status": "market_closed",
                "clock": status.get("clock_text"),
            }
        result = self.graph.execute_trade_directive(
            symbol,
            action,
            quantity=quantity,
            notional=notional,
            reference_price=reference_price,
        )
        return {"status": result.get("status"), "response": result}

    def _call_vendor(self, method: str, *args) -> Any:
        try:
            return route_to_vendor(method, *args)
        except Exception as exc:
            if self.logger:
                self.logger.warning("Vendor call %s failed: %s", method, exc)
            return {"error": str(exc)}

    def _tool_get_memory(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.memory_store:
            return {"entries": []}
        symbol = str(args.get("symbol") or "").upper()
        limit = int(args.get("limit") or self.memory_store.max_entries)
        entries = self.memory_store.load(symbol, limit)
        return {"symbol": symbol, "entries": entries}

    def _init_agent_runners(self) -> Dict[str, Any]:
        try:
            market = create_market_analyst(self.graph.quick_thinking_llm)
            news = create_news_analyst(self.graph.quick_thinking_llm)
            fundamentals = create_fundamentals_analyst(self.graph.quick_thinking_llm)
        except Exception as exc:
            if self.logger:
                self.logger.warning("Failed to initialize analyst agents: %s", exc)
            return {}
        return {
            "market": market,
            "news": news,
            "fundamentals": fundamentals,
        }

    def _tool_run_agent(self, agent_key: str, args: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(args.get("symbol") or "").upper()
        if not symbol:
            return {"error": "Missing symbol"}
        report = self._run_agent(agent_key, symbol)
        return {"symbol": symbol, "agent": agent_key, "report": report}

    def _run_agent(self, agent_key: str, symbol: str) -> str:
        runner = (self._agent_runners or {}).get(agent_key)
        if not runner:
            return f"{agent_key} analyst unavailable."
        state = self._build_agent_state(agent_key, symbol)
        try:
            result = runner(state)
        except Exception as exc:
            if self.logger:
                self.logger.warning("Analyst %s failed for %s: %s", agent_key, symbol, exc)
            return f"{agent_key} analyst failed: {exc}"
        report_key = {
            "market": "market_report",
            "news": "news_report",
            "fundamentals": "fundamentals_report",
        }.get(agent_key, "report")
        report = result.get(report_key)
        if not report:
            messages = result.get("messages") or []
            if messages:
                try:
                    report = messages[-1].content
                except Exception:
                    report = str(messages[-1])
        return report or f"{agent_key} analyst produced no narrative."

    def _build_agent_state(self, agent_key: str, symbol: str) -> Dict[str, Any]:
        today = date.today().isoformat()
        return {
            "messages": [HumanMessage(content=f"Provide {agent_key} analysis for {symbol} on {today}.")],
            "company_of_interest": symbol,
            "target_ticker": symbol,
            "trade_date": today,
            "scheduled_analysts": [agent_key],
            "scheduled_analysts_plan": [agent_key],
            "orchestrator_action": "execute",
        }


class ResponsesAutoTradeService:
    """Auto-trade orchestration powered by the OpenAI Responses API."""

    def __init__(
        self,
        config: Dict[str, Any],
        graph: Optional[TradingAgentsGraph] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config = config
        self.graph = graph or TradingAgentsGraph(config=config, skip_initial_probes=True)
        self.logger = logger or logging.getLogger(__name__)
        backend_url = config.get("backend_url")
        client_kwargs = {}
        if backend_url:
            client_kwargs["base_url"] = backend_url
        self.client = OpenAI(**client_kwargs)
        memory_cfg = (self.config.get("auto_trade") or {}).get("memory", {}) or {}
        memory_enabled = bool(memory_cfg.get("enabled", True))
        memory_dir = memory_cfg.get(
            "dir",
            os.path.join(self.config.get("results_dir", "./results"), "memory"),
        )
        max_entries = int(memory_cfg.get("max_entries", 5))
        self.memory_store = TickerMemoryStore(memory_dir, max_entries=max_entries, enabled=memory_enabled)
        self._strategy_brief_cache = self._strategy_presets_brief()
        auto_trade_cfg = self.config.get("auto_trade", {}) or {}
        self.trade_tool_enabled = bool(auto_trade_cfg.get("responses_enable_trade_tool"))
        self.plan_followup_limit = max(int(auto_trade_cfg.get("responses_plan_followup_limit", 2)), 0)
        self._plan_status_done_values = {
            "done",
            "complete",
            "completed",
            "skipped",
            "skip",
            "n/a",
            "na",
            "not_applicable",
        }

    def run(self, snapshot: AccountSnapshot, *, focus_override: Optional[List[str]] = None) -> AutoTradeResult:
        self._reference_prices = _snapshot_reference_prices(snapshot)
        toolbox = TradingToolbox(
            self.config,
            self.graph,
            snapshot,
            logger=self.logger,
            memory_store=self.memory_store,
        )
        system_prompt = self._build_system_prompt()
        focus_tickers = focus_override or toolbox._determine_focus_tickers()
        conversation: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "account": snapshot.account,
                        "positions": snapshot.positions,
                        "orders": snapshot.orders,
                        "focus_tickers": focus_tickers,
                        "fetched_at": snapshot.fetched_at.isoformat(),
                    }
                ),
            },
        ]
        if self.memory_store and self.memory_store.is_enabled():
            memory_payload = {}
            for ticker in focus_tickers:
                entries = self.memory_store.load(ticker, limit=3)
                if entries:
                    memory_payload[ticker] = entries
            if memory_payload:
                conversation.append(
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "memory_hint": "Historical decisions per ticker. Use get_ticker_memory if deeper detail needed.",
                                "entries": memory_payload,
                            }
                        ),
                    }
                )
        else:
            memory_payload = {}

        lacking_memory = [ticker for ticker in focus_tickers if ticker not in memory_payload]
        if lacking_memory:
            conversation.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "context_gap": "Some focus tickers currently have no stored memory.",
                            "tickers": lacking_memory,
                            "required_actions": (
                                "Before finalizing decisions for these tickers, gather baseline context by "
                                "calling `fetch_market_data` with at least a 7-day lookback and "
                                "`fetch_company_news` (and optionally `fetch_global_news` if macro forces matter). "
                                "Summarize what you learned from those tools so the operator can review your reasoning."
                            ),
                        }
                    ),
                }
            )

        conversation.append(
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "planning_protocol": (
                            "Before calling additional tools, outline a numbered plan where each step names the ticker and the tool/data you intend to use. "
                            "Track each step's status (`pending`, `in_progress`, `done`). After every tool call, explicitly state which step changed status and why. "
                            "If the plan changes mid-run, update the list immediately so the operator sees the live state of each action."
                        )
                    }
                ),
            }
        )

        if self._strategy_brief_cache.get("presets"):
            conversation.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "strategy_presets": self._strategy_brief_cache,
                            "instructions": (
                                "Select whichever preset best matches each ticker's urgency; override target/stop only when necessary."
                            ),
                        }
                    ),
                }
            )

        transcript: List[str] = []
        submitted_trades: Set[Tuple[str, str]] = set()
        response = self._responses_call(
            conversation,
            toolbox,
            transcript,
            allow_tools=True,
            submitted_trades=submitted_trades,
        )
        final_text = self._response_text(response)
        if final_text:
            conversation.append({"role": "assistant", "content": final_text})
        summary = _extract_json_block(final_text)

        if not summary.get("decisions"):
            conversation.append(
                {
                    "role": "user",
                    "content": (
                        "Provide the final decision summary strictly as JSON with the schema:\n"
                        '{"decisions":[{"ticker": "...", "action": "...", "priority": 0.0, '
                        '"plan_actions": [], "next_decision": "...", "notes": "...", '
                        '"plan_status": {"step description": "pending"}, '
                        '"strategy": {"name": "swing", "horizon_hours": 72, "target_pct": 0.04, '
                        '"stop_pct": 0.02, "success_metric": "...", "failure_metric": "...", '
                        '"follow_up": "reassess_every_close", "deadline": "2025-11-14T21:00:00Z", "urgency": "medium"}}]}'
                        " Do not include prose outside the JSON."
                    ),
                }
            )
            response = self._responses_call(
                conversation,
                toolbox,
                transcript,
                max_turns=2,
                allow_tools=False,
                submitted_trades=submitted_trades,
            )
            final_text = self._response_text(response)
            if final_text:
                conversation.append({"role": "assistant", "content": final_text})
            summary = _extract_json_block(final_text)

        guard_info = self._plan_guard(summary)
        followups = 0
        while (
            summary.get("decisions")
            and guard_info.get("needs_followup")
            and followups < self.plan_followup_limit
        ):
            followups += 1
            conversation.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "plan_validation": {
                                "status": "incomplete",
                                "details": guard_info.get("details"),
                                "instruction": (
                                    "Finish or explicitly skip (with justification) every plan step before "
                                    "finalizing the decision summary. Continue executing the scheduled tools; do "
                                    "not place trades until no steps remain pending."
                                ),
                            }
                        }
                    ),
                }
            )
            response = self._responses_call(
                conversation,
                toolbox,
                transcript,
                allow_tools=True,
                submitted_trades=submitted_trades,
            )
            final_text = self._response_text(response)
            if final_text:
                conversation.append({"role": "assistant", "content": final_text})
            summary = _extract_json_block(final_text)
            guard_info = self._plan_guard(summary)

        decisions, focus = self._decisions_from_summary(summary)
        raw_state = {
            "responses_transcript": transcript,
            "responses_summary": summary,
            "responses_output_text": final_text,
            "plan_guard": guard_info,
        }
        if guard_info.get("needs_followup") and guard_info.get("reason"):
            raw_state.setdefault("skip_reason", guard_info.get("reason"))
        if self.memory_store and self.memory_store.is_enabled() and decisions:
            payload: List[Dict[str, Any]] = []
            for decision in decisions:
                decision_dict = decision.to_dict()
                decision_dict["action"] = decision.final_decision or decision.immediate_action
                decision_dict["notes"] = decision.final_notes or decision_dict.get("final_notes") or ""
                decision_dict["priority"] = decision.priority
                payload.append(decision_dict)
            self.memory_store.record_decisions(payload)
        self._auto_execute_trades(
            decisions,
            submitted_trades,
            allow_execution=not bool(guard_info.get("blocked_actions")),
            guard_reason=guard_info.get("reason"),
        )

        return AutoTradeResult(
            focus_tickers=focus or focus_tickers,
            decisions=decisions,
            account_snapshot=snapshot,
            raw_state=raw_state,
        )

    def _responses_call(
        self,
        conversation: List[Dict[str, Any]],
        toolbox: TradingToolbox,
        transcript: List[str],
        *,
        max_turns: Optional[int] = None,
        allow_tools: bool = True,
        submitted_trades: Optional[Set[Tuple[str, str]]] = None,
    ):
        model = (
            self.config.get("auto_trade", {}).get("responses_model")
            or self.config.get("quick_think_llm")
        )
        if not model:
            raise RuntimeError("Missing responses model configuration.")

        reasoning_config = self.config.get("auto_trade", {}).get("responses_reasoning_effort", "")
        reasoning_text = (reasoning_config or "").strip()
        if not reasoning_text:
            reasoning_text = "medium"
        reasoning_enabled = reasoning_text and reasoning_text.lower() not in {"none", "off"}
        remaining_turns = max_turns or int(self.config.get("auto_trade", {}).get("responses_max_turns") or 8)

        if remaining_turns <= 0:
            raise RuntimeError("Responses conversation exceeded maximum turns without completion.")

        repeat_guard: Dict[str, int] = {}
        narration_reminder_issued = False

        while remaining_turns > 0:
            request_kwargs: Dict[str, Any] = {
                "model": model,
                "input": conversation,
                "store": False,
            }
            if allow_tools:
                request_kwargs["tools"] = toolbox.specs
            if reasoning_enabled:
                request_kwargs["reasoning"] = {"effort": reasoning_text}

            tool_call: Optional[Dict[str, Any]] = None
            final_response: Any = None

            response = self.client.responses.create(**request_kwargs)
            final_response = response
            thinking_traces = self._extract_reasoning_traces(response)
            for trace in thinking_traces:
                if trace:
                    transcript.append(f"[Thinking] {trace}")
                    self._emit_narration(f"[Thinking] {trace}")

            assistant_message = self._response_text(response)
            if assistant_message:
                transcript.append(assistant_message)
                self._emit_narration(assistant_message)
                conversation.append({"role": "assistant", "content": assistant_message})
                narration_reminder_issued = False

            tool_calls = self._extract_tool_calls(response)
            if tool_calls:
                for tool_call in tool_calls:
                    args = self._safe_json(tool_call.get("arguments"))
                    name = tool_call.get("name") or ""
                    tool_error: Optional[str] = None
                    try:
                        result = toolbox.invoke(name, args)
                    except Exception as exc:  # pragma: no cover - defensive
                        tool_error = f"{exc}"
                        result = {"error": tool_error}
                    self._emit_tool_event(name, args, result)
                    if (
                        tool_error is None
                        and submitted_trades is not None
                        and name == "submit_trade_order"
                    ):
                        symbol = str(args.get("symbol") or "").upper()
                        action = str(args.get("action") or "").upper()
                        if symbol and action:
                            submitted_trades.add((symbol, action))
                    conversation.append(
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "tool": name,
                                    "tool_call_id": tool_call.get("id")
                                    or tool_call.get("call_id")
                                    or tool_call.get("item_id"),
                                    "result": result,
                                },
                                default=str,
                            ),
                        }
                    )
                    guard_key = f"{name}:{json.dumps(args, sort_keys=True)}"
                    repeat_guard[guard_key] = repeat_guard.get(guard_key, 0) + 1
                    if repeat_guard[guard_key] >= 2:
                        conversation.append(
                            {
                                "role": "user",
                                "content": (
                                    f"You have already called `{name}` with the same arguments "
                                    f"{repeat_guard[guard_key]} times. Summarize the existing data and "
                                    "move on to the next required tool or generate the decision summary instead of "
                                    "repeating this call."
                                ),
                            }
                        )
                remaining_turns -= 1
                if not assistant_message and not narration_reminder_issued:
                    conversation.append(
                        {
                            "role": "user",
                            "content": (
                                "Narrate what you are doing before issuing more tool calls so the CLI can show your "
                                "reasoning in real time."
                            ),
                        }
                    )
                    narration_reminder_issued = True
                continue

            if final_response is None:
                raise RuntimeError("Streaming response did not complete.")
            return final_response

        raise RuntimeError("Responses conversation exceeded maximum turns without completion.")

    def _decisions_from_summary(self, summary: Dict[str, Any]) -> Tuple[List[TickerDecision], List[str]]:
        decisions_payload = summary.get("decisions") or []
        decisions: List[TickerDecision] = []
        focus: List[str] = []

        for entry in decisions_payload:
            ticker = str(entry.get("ticker") or "").upper()
            if not ticker:
                continue
            focus.append(ticker)
            priority = float(entry.get("priority") or entry.get("confidence") or 0)
            action = str(entry.get("action") or entry.get("decision") or "monitor").upper()
            plan_actions = entry.get("plan_actions") or entry.get("actions") or []
            if isinstance(plan_actions, str):
                plan_actions = [plan_actions]
            immediate = entry.get("immediate_action") or action.lower()
            sequential_plan = SequentialPlan(
                actions=[str(item).lower() for item in plan_actions],
                next_decision=str(entry.get("next_decision") or immediate).lower(),
                notes=str(entry.get("notes") or entry.get("rationale") or ""),
                reasoning=entry.get("reasoning") or [],
            )
            hypothesis = {
                "ticker": ticker,
                "rationale": entry.get("rationale") or entry.get("notes") or "",
                "priority": priority,
                "required_analysts": entry.get("required_analysts") or [],
                "immediate_actions": immediate,
            }
            trade_notes = entry.get("execution_plan") or entry.get("notes") or ""
            strategy = self._build_strategy(entry)
            triggers = self._build_triggers(strategy, entry)
            decision = TickerDecision(
                ticker=ticker,
                hypothesis=hypothesis,
                sequential_plan=sequential_plan,
                action_queue=triggers,
                immediate_action=str(immediate),
                priority=priority,
                final_decision=action,
                trader_plan=entry.get("trader_plan") or "",
                final_notes=trade_notes,
                strategy=strategy,
            )
            decisions.append(decision)

        return decisions, focus

    def _build_strategy(self, entry: Dict[str, Any]) -> StrategyDirective:
        overrides = entry.get("strategy")
        if overrides and isinstance(overrides, dict):
            overrides = {**overrides}  # shallow copy so we can enrich with derived prices
        strategy = resolve_strategy_directive(self.config, overrides)
        entry["strategy"] = strategy.to_dict()
        return strategy

    def _build_triggers(self, strategy: StrategyDirective, entry: Dict[str, Any]) -> List[str]:
        base_triggers = [str(item).lower() for item in entry.get("action_queue", []) if str(item).strip()]
        price = _extract_reference_price(entry)
        if not price and hasattr(self, "_reference_prices"):
            price = self._reference_prices.get(str(entry.get("ticker") or "").upper())
        derived: List[str] = []
        if price and strategy.target_pct:
            success_price = price * (1 + strategy.target_pct)
            strategy.success_price = success_price
            derived.append(f"price >= {success_price:.2f}")
        if price and strategy.stop_pct:
            failure_price = price * (1 - strategy.stop_pct)
            strategy.failure_price = failure_price
            derived.append(f"price <= {failure_price:.2f}")
        return base_triggers + derived

    def _plan_guard(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        decisions = summary.get("decisions") or []
        details: List[Dict[str, Any]] = []
        blocked: List[str] = []
        for entry in decisions:
            ticker = str(entry.get("ticker") or "").upper()
            if not ticker:
                continue
            statuses = entry.get("plan_status") or {}
            incomplete: List[str] = []
            if isinstance(statuses, dict) and statuses:
                for step, status in statuses.items():
                    label = str(step or "").strip() or "<unnamed step>"
                    status_text = str(status or "").strip()
                    normalized = status_text.lower()
                    ok = (
                        normalized in self._plan_status_done_values
                        or "done" in normalized
                        or "complete" in normalized
                        or "skip" in normalized
                        or "n/a" in normalized
                    )
                    if ok:
                        continue
                    display = f"{label} ({status_text or 'pending'})"
                    incomplete.append(display)
            elif entry.get("plan_actions"):
                for action in entry.get("plan_actions") or []:
                    incomplete.append(f"{action} (no status reported)")
            if incomplete:
                details.append({"ticker": ticker, "steps": incomplete})
                action = str(entry.get("action") or "").upper()
                if action in {"BUY", "SELL"} and ticker not in blocked:
                    blocked.append(ticker)
        reason = ""
        if details:
            joined = "; ".join(f"{item['ticker']}: {', '.join(item['steps'])}" for item in details)
            reason = f"Plan validation incomplete; pending steps -> {joined}"
        return {
            "needs_followup": bool(details),
            "blocked_actions": blocked,
            "details": details,
            "reason": reason,
        }

    def _extract_tool_calls(self, response: Any) -> List[Dict[str, Any]]:
        calls: List[Dict[str, Any]] = []
        output_items = getattr(response, "output", []) or []
        for item in output_items:
            if getattr(item, "type", None) != "function_call":
                continue
            call_id = getattr(item, "id", None) or getattr(item, "call_id", None)
            arguments = getattr(item, "arguments", "") or ""
            calls.append({"id": call_id, "name": getattr(item, "name", ""), "arguments": arguments})
        return calls

    def _extract_reasoning_traces(self, response: Any) -> List[str]:
        traces: List[str] = []
        output_items = getattr(response, "output", []) or []
        for item in output_items:
            if getattr(item, "type", None) != "reasoning":
                continue
            summary_bits: List[str] = []
            for summary in getattr(item, "summary", []) or []:
                text = getattr(summary, "text", "") or ""
                if text:
                    summary_bits.append(text.strip())
            detail_bits: List[str] = []
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", "") or ""
                if text:
                    detail_bits.append(text.strip())
            summary_text = "; ".join(bit for bit in summary_bits if bit)
            detail_text = " ".join(bit for bit in detail_bits if bit)
            if detail_text and detail_text != summary_text:
                snippet = f"{summary_text} — {detail_text}" if summary_text else detail_text
            else:
                snippet = summary_text or detail_text
            if snippet:
                traces.append(snippet)
        return traces

    def _response_text(self, response: Any) -> str:
        if not response:
            return ""
        if hasattr(response, "output_text") and response.output_text:
            return response.output_text
        pieces: List[str] = []
        for output in getattr(response, "output", []) or []:
            if getattr(output, "type", None) == "message":
                for content in getattr(output, "content", []) or []:
                    if getattr(content, "type", None) == "output_text":
                        pieces.append(getattr(content, "text", "") or "")
        return "\n".join(pieces).strip()

    def _emit_narration(self, message: str) -> None:
        snippet = message.strip()
        if not snippet:
            return
        try:
            print(f"[Responses Orchestrator] {snippet}")
        except Exception:
            pass

    def _emit_tool_event(self, name: str, args: Dict[str, Any], result: Dict[str, Any]) -> None:
        try:
            status = "OK"
            if isinstance(result, dict) and result.get("error"):
                status = "ERR"
            args_str = _trimmed_json(args)
            response_payload = result.get("report") if isinstance(result, dict) and isinstance(result.get("report"), str) else result
            response_str = _trimmed_json(response_payload)
            print(f"[Tool:{status}] {name}, Args:{args_str}")
            print(f"[Tool:{status}] {name}, Response:{response_str}")
        except Exception:
            pass

    def _auto_execute_trades(
        self,
        decisions: List[TickerDecision],
        submitted_trades: Set[Tuple[str, str]],
        *,
        allow_execution: bool = True,
        guard_reason: Optional[str] = None,
    ) -> None:
        exec_cfg = self.config.get("trade_execution", {}) or {}
        if not exec_cfg.get("enabled"):
            return
        if not allow_execution:
            message = guard_reason or "Plan guard blocked trade execution."
            try:
                print(f"[Auto Execution] Skipping trade execution: {message}")
            except Exception:
                pass
            return
        for decision in decisions:
            action = (decision.final_decision or decision.immediate_action or "").upper()
            if action not in {"BUY", "SELL"}:
                continue
            key = (decision.ticker.upper(), action)
            if key in submitted_trades:
                continue
            result = self.graph.execute_trade_directive(decision.ticker, action)
            try:
                print(f"[Auto Execution] {decision.ticker} {action} -> {result.get('status')}")
            except Exception:
                pass

    def _build_system_prompt(self) -> str:
        trade_clause = (
            "After producing the JSON, call `submit_trade_order` for every ticker whose action is BUY or SELL "
            "(subject to trade execution settings)."
            if self.trade_tool_enabled
            else "Do not call `submit_trade_order`; once your plan summary shows every step resolved, the autopilot "
            "will handle trade submission automatically."
        )
        return (
            "You are the trading orchestrator for TradingAgents. Every run must begin by calling "
            "`get_account_overview` exactly once (unless you explicitly refresh the Alpaca snapshot) and narrating the "
            "current buying power, cash, open positions, and any recent orders. Reuse that overview for the remainder of "
            "the run; do not call `get_account_overview` again until you intentionally refresh the snapshot.\n\n"
            "With that snapshot, immediately synthesize or update a trading hypothesis for each focus ticker using the "
            "account data, existing positions, buying power, cash, recent orders, and stored memory. Decide whether the "
            "current hypothesis already justifies HOLD/BUY/SELL before touching high-latency tools. Only call "
            "heavy-weight analysts or vendor data feeds when the hypothesis requires fresh evidence (e.g., preparing a "
            "trade, validating a catalyst, or detecting a change since the last run). If the prior plan still applies, "
            "log that decision and proceed without re-running every analyst.\n\n"
            "When deeper context is required, call `get_ticker_memory`, then use `fetch_market_data`, "
            "`fetch_indicators`, and `fetch_company_news` (plus `fetch_global_news` when macro context matters) before "
            "invoking the specialist analysts (`run_market_analyst`, `run_news_analyst`, `run_fundamentals_analyst`). "
            "For any ticker that lacks stored memory or an active position, you must at minimum gather the last 7 days of "
            "market data and the latest company news before finalizing your hypothesis so you remain curious and well-grounded.\n\n"
            "Every recommendation must map to a named strategy (e.g., day_trade, swing, position) taken from the provided presets. "
            "For each ticker, specify a measurable `strategy` object containing `name`, `horizon_hours`, `target_pct`, `stop_pct`, "
            "`success_metric`, `failure_metric`, `follow_up`, `urgency`, and an ISO8601 `deadline` that defines when the plan is reevaluated. "
            "Customize the preset parameters only when the evidence demands it, and ensure the success/failure metrics describe the exact "
            "conditions that complete or cancel the hypothesis so automation can act on them.\n\n"
            "Narrate every step before you make the tool call so the CLI can display your thinking live, and summarize what "
            "you learned from each tool. Be curious: when a ticker’s context is thin, proactively explore the smallest set "
            "of tools needed to form a defendable hypothesis rather than defaulting to HOLD. Maintain an explicit plan tracker: list "
            "each planned action (e.g., ‘Step 1 – Fetch TSLA market data’) along with its status (`pending`, `in_progress`, `done`), "
            "and after every tool call, announce which step changed status and why. Consider market-open status before "
            "trading, respect trade execution limits (but treat `day_trades_remaining` as informational—you may still "
            "recommend buys/sells), and keep narration concise but informative. Before the final summary, resolve every "
            "`plan_status` entry: either run the scheduled step or explicitly mark it as `skipped` with a short reason so "
            "no action remains `pending`.\n\n"
            "Conclude with a JSON summary containing decisions for each ticker. The final assistant message must include a "
            "JSON object with a `decisions` array where each entry specifies `ticker`, `action`, `priority`, "
            "`plan_actions`, `next_decision`, `notes`, `plan_status` (a mapping of each plan action to its status), the `strategy` object described above, "
            "and optional `action_queue` and `execution_plan` fields. "
            f"{trade_clause}"
        )

    def _safe_json(self, raw: str) -> Dict[str, Any]:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}

    def _strategy_presets_brief(self) -> Dict[str, Any]:
        cfg = self.config.get("trading_strategies", {}) or {}
        presets = cfg.get("presets", {}) or {}
        entries: List[Dict[str, Any]] = []
        for name, data in presets.items():
            entries.append(
                {
                    "name": name,
                    "label": data.get("label"),
                    "horizon_hours": data.get("horizon_hours"),
                    "target_pct": data.get("target_pct"),
                    "stop_pct": data.get("stop_pct"),
                    "follow_up": data.get("follow_up"),
                    "urgency": data.get("urgency"),
                }
            )
        return {"default": cfg.get("default", "swing"), "presets": entries}
def _extract_reference_price(entry: Dict[str, Any]) -> Optional[float]:
    candidates = [
        entry.get("reference_price"),
        (entry.get("state") or {}).get("price"),
        entry.get("last_price"),
    ]
    for value in candidates:
        try:
            price = float(value)
            if price > 0:
                return price
        except (TypeError, ValueError):
            continue
    return None


def _snapshot_reference_prices(snapshot: AccountSnapshot) -> Dict[str, float]:
    mapping: Dict[str, float] = {}
    for position in snapshot.positions:
        symbol = str(position.get("symbol") or position.get("symbol:") or "").upper()
        if not symbol:
            continue
        price_fields = [
            position.get("current_price"),
            position.get("price"),
            position.get("market_value"),
        ]
        value = None
        for field in price_fields:
            try:
                candidate = float(str(field).replace("$", ""))
                if candidate > 0:
                    value = candidate
                    break
            except (TypeError, ValueError, AttributeError):
                continue
        if value:
            mapping[symbol] = value
    return mapping
