from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from tradingagents.agents.utils.agent_utils import (
    build_capital_context,
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.conflict_detector import format_conflict_report_for_prompt


BROAD_INDEX_TICKERS = {
    "SPY",
    "VOO",
    "IVV",
    "QQQ",
    "QQQM",
    "DIA",
    "IWM",
    "VTI",
    "VT",
    "^GSPC",
    "^IXIC",
    "^DJI",
    "^RUT",
}


class PriceSizeBlock(BaseModel):
    price: Optional[float] = Field(default=None, description="Plain numeric limit price, or null when unused.")
    size_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class StopLossBlock(BaseModel):
    price: Optional[float] = Field(default=None, description="Plain numeric stop price, or null when unused.")


class PortfolioStrategy(BaseModel):
    schema_version: Literal["v3"] = "v3"
    ticker: str
    as_of_date: str = Field(description="YYYY-MM-DD analysis date.")
    action: Literal["BUY", "HOLD", "SELL"]
    entry: PriceSizeBlock
    add_position: PriceSizeBlock
    take_profit: PriceSizeBlock = Field(
        description="Sell on rise (high >= price). size_pct=100 means full take-profit close."
    )
    reduce_stop: PriceSizeBlock = Field(
        description="Partial defensive sell on drop (low <= price). Price must sit above stop_loss."
    )
    stop_loss: StopLossBlock = Field(
        description="Full-close stop. Triggered when low <= price; closes 100% of the position."
    )
    rationale_summary: str

    @model_validator(mode="after")
    def normalize_sell_orders(self):
        if self.action == "SELL":
            self.entry = PriceSizeBlock()
            self.add_position = PriceSizeBlock()
            self.take_profit = PriceSizeBlock()
            self.reduce_stop = PriceSizeBlock()
        return self

    @model_validator(mode="after")
    def validate_risk_levels(self):
        if self.action == "SELL":
            return self
        rs_price = self.reduce_stop.price
        sl_price = self.stop_loss.price
        if (
            rs_price is not None
            and sl_price is not None
            and self.reduce_stop.size_pct > 0
            and rs_price <= sl_price
        ):
            raise ValueError(
                f"reduce_stop.price ({rs_price}) must be ABOVE stop_loss.price ({sl_price}); "
                "otherwise the partial trim has no defensive value over the hard stop."
            )
        if self.action == "BUY" and self.entry.size_pct > 0 and sl_price is None:
            raise ValueError("BUY with a non-zero entry must define stop_loss.price.")
        if self.add_position.size_pct > 0 and sl_price is None:
            raise ValueError("add_position with size_pct > 0 must be paired with stop_loss.price.")
        return self


def _is_broad_index_instrument(ticker: str) -> bool:
    normalized = ticker.upper()
    return normalized in BROAD_INDEX_TICKERS or normalized.endswith((".INDEX", ".IDX"))


def _classify_volume_regime(volume_ratio: Optional[float]) -> str:
    if volume_ratio is None:
        return "unavailable"
    if volume_ratio >= 1.5:
        return "expanding"
    if volume_ratio < 0.7:
        return "shrinking"
    if volume_ratio >= 0.9:
        return "normal"
    return "soft"


def _clamp_size(block: dict, max_size: float) -> None:
    block["size_pct"] = min(float(block.get("size_pct") or 0.0), float(max_size))
    if block["size_pct"] <= 0:
        block["size_pct"] = 0.0
        block["price"] = None


def _distance_pct(price: Optional[float], current_price: Optional[float]) -> Optional[float]:
    if price is None or current_price in (None, 0):
        return None
    return abs(float(price) - float(current_price)) / float(current_price) * 100.0


def _append_rule_note(strategy: dict, note: str) -> None:
    rationale = strategy.get("rationale_summary") or ""
    if note not in rationale:
        strategy["rationale_summary"] = (rationale + " Rule adjustment: " + note).strip()


def _clear_entry_orders(strategy: dict) -> None:
    strategy["entry"] = PriceSizeBlock().model_dump()
    strategy["add_position"] = PriceSizeBlock().model_dump()


def _enforce_strategy_rules(strategy: dict, anchors: Optional[dict], constraints: dict, holdings_info: dict) -> dict:
    strategy = PortfolioStrategy.model_validate(strategy).model_dump()
    has_position = float(holdings_info.get("quantity") or 0.0) > 0
    current_price = anchors.get("current_price") if anchors else None

    if strategy["action"] not in constraints["allowed_actions"]:
        original_action = strategy["action"]
        strategy["action"] = "HOLD" if original_action == "SELL" or has_position else "BUY"
        if strategy["action"] not in constraints["allowed_actions"]:
            strategy["action"] = constraints["allowed_actions"][0]
        _append_rule_note(
            strategy,
            f"{original_action} was outside allowed_actions={constraints['allowed_actions']}; action set to {strategy['action']}.",
        )
        if original_action == "SELL":
            _clear_entry_orders(strategy)

    _clamp_size(strategy["entry"], constraints["max_entry_size_pct"])
    _clamp_size(strategy["add_position"], constraints["max_add_position_size_pct"])

    if constraints["entry_mode"] == "no_new_or_add":
        _clear_entry_orders(strategy)
        if not has_position and strategy["action"] == "BUY":
            strategy["action"] = "HOLD"
        _append_rule_note(strategy, "new entries and adds blocked by deterministic volume divergence rule.")

    entry_distance = _distance_pct(strategy["entry"].get("price"), current_price)
    if entry_distance is not None and entry_distance > 10:
        strategy["entry"]["size_pct"] = 0.0
        strategy["entry"]["price"] = None
        _append_rule_note(strategy, "entry more than 10% from current price was removed.")

    add_distance = _distance_pct(strategy["add_position"].get("price"), current_price)
    if add_distance is not None and add_distance > 10:
        strategy["add_position"]["size_pct"] = 0.0
        strategy["add_position"]["price"] = None
        _append_rule_note(strategy, "add-position level more than 10% from current price was removed.")

    if strategy["action"] == "BUY" and strategy["entry"]["size_pct"] <= 0 and strategy["add_position"]["size_pct"] <= 0:
        strategy["action"] = "HOLD"
        _append_rule_note(strategy, "BUY without an executable entry/add was converted to HOLD.")

    if strategy["action"] in ("BUY", "HOLD") and (
        strategy["entry"]["size_pct"] > 0 or strategy["add_position"]["size_pct"] > 0
    ):
        if strategy["stop_loss"]["price"] is None and anchors:
            reference = strategy["entry"]["price"] or current_price
            stop = min(
                anchors.get("nearest_support") or reference,
                float(reference) - 1.5 * float(anchors["atr14"]),
            )
            strategy["stop_loss"]["price"] = round(max(stop, 0.01), 4)
            _append_rule_note(strategy, "missing stop_loss was filled from support/ATR anchor.")

    return PortfolioStrategy.model_validate(strategy).model_dump()


def create_portfolio_manager(llm, memory):
    def portfolio_manager_node(state) -> dict:
        # Lazy import: portfolio_state_manager imports schemas from this module,
        # so a top-level import here would be circular.
        from tradingagents.agents.managers.portfolio_state_manager import (
            _compute_short_term_market_anchors,
            _derive_short_term_rule_constraints,
            _format_short_term_market_anchors,
            _format_short_term_rule_constraints,
        )

        instrument_context = build_instrument_context(state["company_of_interest"])
        capital_context = build_capital_context(state.get("holdings_info"))

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]
        holdings_info = state.get("holdings_info") or {}

        ticker = state["company_of_interest"]
        trade_date = state["trade_date"]
        anchors = _compute_short_term_market_anchors(ticker, trade_date)
        anchors_block = (
            "\n\n" + _format_short_term_market_anchors(anchors) if anchors else ""
        )
        constraints = _derive_short_term_rule_constraints(anchors, holdings_info, ticker)
        constraints_block = "\n\n" + _format_short_term_rule_constraints(constraints)
        conflict_block = format_conflict_report_for_prompt(state.get("conflict_report"))

        # P0.4 — required-data degradation gate. Core technical anchors must be
        # present to make a directional short-term call; without them the LLM
        # would be guessing levels from prose. Force HOLD instead of fabricating.
        required_anchors = ("current_price", "atr14", "ema10", "ema20")
        missing_required = (
            list(required_anchors)
            if anchors is None
            else [k for k in required_anchors if anchors.get(k) is None]
        )
        if missing_required:
            forced = (
                "**Decision**: HOLD\n\n"
                "**Rationale**: FORCED HOLD — required market anchors "
                f"{missing_required} were unavailable for {ticker} on {trade_date}. "
                "System policy: no directional short-term recommendation when core "
                "technical anchors are missing; re-run once the data feed is restored.\n\n"
                "**Decision Audit**:\n"
                "- Data-supported: none (anchor computation failed)\n"
                "- Inferred: none\n"
                f"- Missing data: {', '.join(missing_required)}\n"
                "- Invalidation triggers: n/a\n"
                "- Watch-list: restore OHLCV / indicator data feed, then re-run analysis."
            )
            return {
                "risk_debate_state": {
                    **risk_debate_state,
                    "judge_decision": forced,
                    "latest_speaker": "Judge",
                },
                "final_trade_decision": forced,
                "structured_strategy": None,
            }

        curr_situation = (
            f"{state['market_report']}\n\n{state['sentiment_report']}\n\n"
            f"{state['news_report']}\n\n{state['fundamentals_report']}"
        )
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        lessons_section = f"- Lessons from past decisions: **{past_memory_str}**\n" if past_memory_str else ""
        holdings_section = ""
        if holdings_info:
            quantity = float(holdings_info.get("quantity") or 0.0)
            cash = holdings_info.get("cash")
            avg_buy_price = holdings_info.get("avg_buy_price")
            mark_price = holdings_info.get("mark_price")
            equity = holdings_info.get("equity")
            stop_loss = holdings_info.get("stop_loss")
            if quantity > 0:
                holdings_section = (
                    "- Current simulated holdings: "
                    f"{quantity:g} shares"
                    + (f", average buy price {float(avg_buy_price):g}" if avg_buy_price is not None else "")
                    + (f", mark price {float(mark_price):g}" if mark_price is not None else "")
                    + (f", active stop {float(stop_loss):g}" if stop_loss is not None else "")
                    + (f", cash {float(cash):g}" if cash is not None else "")
                    + (f", equity {float(equity):g}" if equity is not None else "")
                    + ". Manage this existing position; do not behave as if the portfolio is flat.\n"
                )
            else:
                holdings_section = (
                    "- Current simulated holdings: no open position"
                    + (f", cash {float(cash):g}" if cash is not None else "")
                    + (f", equity {float(equity):g}" if equity is not None else "")
                    + ". If the regime is favorable, prioritize establishing a starter position.\n"
                )

        capital_block = f"\n\n{capital_context}" if capital_context else ""
        prompt = f"""You are the Portfolio Manager. Synthesize the risk analysts' debate and deliver the final short-term trading decision.

{instrument_context}{capital_block}

**Decision** (choose one): **BUY** | **HOLD** | **SELL**

**Context:**
- Research Manager's plan: {research_plan}
- Trader's proposal: {trader_plan}
{lessons_section}
{holdings_section}
**Risk Analysts Debate:**
{history}{anchors_block}{constraints_block}{conflict_block}

Use the precomputed market anchors verbatim — do not re-derive prices, ATR, support/resistance, or volume_ratio from the analyst reports. Treat the rule constraints as hard caps: position sizing and allowed_actions must respect them even when the debate suggests otherwise; note any constraint that overrode the debate wording in your rationale.

Be decisive and ground every parameter in specific evidence from the debate.{get_language_instruction()}

**Required Output:**
1. **Decision**: BUY / HOLD / SELL
2. **Trade Parameters**: Initial entry, add-position level, take-profit level, reduce-stop level, stop-loss level, expected holding period (days to weeks)
3. **Position Sizing**: Suggested allocation as % of portfolio and rationale
4. **Rationale**: Key reasoning grounded in the analysts' debate
5. **Decision Audit** (be honest — if you cannot cite specific evidence for a claim, list it under Inferred, not Data-supported):
   - **Data-supported**: conclusions backed by a specific anchor or report citation; include the number or date
   - **Inferred**: conclusions reached by reasoning over signals rather than direct evidence
   - **Missing data**: required inputs that were unavailable or returned a NOTICE (e.g. options chain, volume_ratio)
   - **Invalidation triggers**: specific observable events that would flip this recommendation
   - **Watch-list**: the top 3 things to monitor before the next review"""

        response = llm.invoke(prompt)
        decision_text = response.content

        new_risk_debate_state = {
            "judge_decision": decision_text,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": decision_text,
            "structured_strategy": None,
        }

    return portfolio_manager_node
