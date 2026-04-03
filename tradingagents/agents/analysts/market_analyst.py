from datetime import datetime, timedelta
import queue
import threading

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    format_prefetched_context,
    prefetch_tools_parallel,
)
from tradingagents.agents.utils.core_stock_tools import get_stock_data
from tradingagents.agents.utils.fundamental_data_tools import get_macro_regime
from tradingagents.agents.utils.output_validation import (
    build_market_report_structured,
    infer_macro_regime_from_prefetched_report,
)
from tradingagents.agents.utils.technical_indicators_tools import get_indicators
from tradingagents.default_config import DEFAULT_CONFIG


_INDICATOR_PLANS = {
    "risk_on": [
        "close_10_ema",
        "close_50_sma",
        "macd",
        "macds",
        "macdh",
        "rsi",
        "vwma",
        "atr",
    ],
    "risk_off": [
        "close_200_sma",
        "close_50_sma",
        "atr",
        "boll",
        "boll_ub",
        "boll_lb",
        "rsi",
        "vwma",
    ],
    "transition": [
        "close_10_ema",
        "close_50_sma",
        "close_200_sma",
        "macd",
        "rsi",
        "atr",
        "boll",
        "vwma",
    ],
}


def _compact_timeseries_text(raw_text: str, *, max_data_rows: int, marker: str) -> str:
    """Keep prompt-safe slices of large CSV/indicator blocks."""
    text = str(raw_text or "").strip()
    if not text or text.startswith("[Error"):
        return text
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= max_data_rows + 1:
        return text
    header = lines[0]
    tail = lines[-max_data_rows:]
    omitted = len(lines) - (max_data_rows + 1)
    return "\n".join([header, f"# [{marker}: truncated {omitted} older rows]", *tail])


def _build_indicator_prefetches(
    *,
    ticker: str,
    current_date: str,
    lookback_days: int,
    macro_regime_report: str,
) -> list[dict]:
    regime = infer_macro_regime_from_prefetched_report(macro_regime_report)
    indicators = _INDICATOR_PLANS.get(regime) or _INDICATOR_PLANS["transition"]
    return [
        {
            "tool": get_indicators,
            "args": {
                "symbol": ticker,
                "indicator": indicator,
                "curr_date": current_date,
                "look_back_days": lookback_days,
            },
            "label": f"Technical Indicator: {indicator}",
        }
        for indicator in indicators
    ]


def _invoke_with_timeout(chain, messages, timeout_seconds: float):
    """Invoke a chain with a hard wall-clock timeout."""
    result_queue: "queue.Queue[tuple[str, object]]" = queue.Queue(maxsize=1)

    def _runner():
        try:
            result_queue.put(("ok", chain.invoke(messages)))
        except Exception as exc:  # pragma: no cover - exercised via caller behavior
            result_queue.put(("err", exc))

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout=max(1.0, float(timeout_seconds)))
    if thread.is_alive():
        return None, TimeoutError(f"market analyst invoke exceeded {timeout_seconds:.1f}s")

    status, payload = result_queue.get()
    if status == "err":
        return None, payload
    return payload, None


def _build_timeout_fallback_report(
    *,
    ticker: str,
    as_of_date: str,
    macro_regime_report: str,
    timeout_seconds: float,
) -> str:
    regime = infer_macro_regime_from_prefetched_report(macro_regime_report)
    regime_label = regime.replace("_", "-").upper() if regime != "unknown" else "UNKNOWN"
    return (
        f"{ticker} Market Analysis (Timeout Fallback)\n\n"
        f"- Model generation exceeded {timeout_seconds:.0f}s and was cut over to deterministic fallback mode.\n"
        f"- Macro regime from pre-loaded context: {regime_label}.\n"
        f"- Preserve scanner context values as ground truth for downstream weighting.\n"
        f"- Recommend rerunning market analysis when model latency stabilizes.\n\n"
        "| Field | Value |\n"
        "|---|---|\n"
        f"| Ticker | {ticker} |\n"
        f"| Date | {as_of_date} |\n"
        f"| Macro Regime | {regime_label} |\n"
        f"| Mode | Timeout fallback |\n"
    )


def create_market_analyst(llm):
    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        scanner_context = state.get("scanner_context_packet", "")

        lookback_days = DEFAULT_CONFIG.get("trading_lookback_days", 90)
        indicator_lookback_days = max(20, min(int(lookback_days), 45))
        trade_date = datetime.strptime(current_date, "%Y-%m-%d")
        stock_window_days = max(100, indicator_lookback_days + 20)
        stock_start = (trade_date - timedelta(days=stock_window_days)).strftime("%Y-%m-%d")

        prefetched = prefetch_tools_parallel(
            [
                {
                    "tool": get_macro_regime,
                    "args": {"curr_date": current_date},
                    "label": "Macro Regime Classification",
                },
                {
                    "tool": get_stock_data,
                    "args": {
                        "symbol": ticker,
                        "start_date": stock_start,
                        "end_date": current_date,
                    },
                    "label": "Stock Price Data",
                },
            ]
        )
        stock_blob = prefetched.get("Stock Price Data", "")
        if stock_blob:
            prefetched["Stock Price Data"] = _compact_timeseries_text(
                stock_blob,
                max_data_rows=40,
                marker="stock data compacted",
            )

        macro_regime_report = ""
        regime_data = prefetched.get("Macro Regime Classification", "")
        if regime_data and not regime_data.startswith("[Error"):
            macro_regime_report = regime_data

        indicator_prefetched = prefetch_tools_parallel(
            _build_indicator_prefetches(
                ticker=ticker,
                current_date=current_date,
                lookback_days=indicator_lookback_days,
                macro_regime_report=macro_regime_report,
            )
        )
        for key, value in list(indicator_prefetched.items()):
            indicator_prefetched[key] = _compact_timeseries_text(
                value,
                max_data_rows=12,
                marker="indicator data compacted",
            )
        prefetched_context = format_prefetched_context({**prefetched, **indicator_prefetched})

        system_message = (
            "You are a trading assistant tasked with analyzing financial markets.\n\n"
            "## Pre-loaded Data\n\n"
            "The macro regime classification, recent stock price data, and a regime-specific "
            "technical indicator pack for the company under analysis have already been fetched "
            "and are provided in the **Pre-loaded Context** section below. Do NOT call "
            "`get_macro_regime`, `get_stock_data`, or `get_indicators` — the data is already "
            "available.\n\n"
            "## Your Task\n\n"
            "0. **STRICT GROUND TRUTH**: Treat all values in the **Scanner Context** section "
            "(commodity prices, FX rates, and calendar dates) as absolute ground-truth. "
            "Do NOT deviate from these numbers or dates in your report. If the Scanner "
            "Context contains a 30-day directional prediction, incorporate it into your "
            "assessment of the market backdrop.\n\n"
            "1. Read the macro regime classification from the pre-loaded context. Use it to "
            "weight the significance of the indicator pack that follows. In risk-off "
            "environments, emphasize volatility, capital preservation, and long-term support "
            "levels. In risk-on environments, emphasize momentum, trend confirmation, and "
            "breakout continuation. In transition regimes, highlight conflicting signals.\n\n"
            "## CRITICAL ABORT TRIGGER\n\n"
            "If you detect any of the following CATASTROPHIC market conditions, you MUST immediately "
            "prepend `[CRITICAL ABORT]` to your report and provide specific reasoning:\n\n"
            "### Trading and Market Issues:\n"
            "- Trading halted pending delisting or investigation\n"
            "- Delisting announcement from exchange or regulatory body\n"
            "- Trading halted due to catastrophic news or material information\n"
            "- Market cap collapse (e.g., < $50M or > 90% decline in 24h)\n"
            "- Extreme volatility (e.g., > 200% daily move)\n\n"
            "### Regulatory and Legal Issues:\n"
            "- SEC enforcement action or investigation\n"
            "- Regulatory shutdown or cease-and-desist order\n"
            "- Bankruptcy or insolvency filing\n"
            "- Material fraud or accounting scandal\n"
            "- Going concern warning from auditor\n\n"
            "### Catastrophic News and Events:\n"
            "- Earnings miss with -90% or worse guidance\n"
            "- Major product recall or safety issue\n"
            "- CEO resignation or major leadership scandal\n"
            "- Lawsuit with > $1B damages or regulatory fine\n"
            "- Natural disaster or catastrophic event impacting operations\n\n"
            "### Format Requirements:\n"
            "When triggering a critical abort, your report MUST start with:\n"
            "`[CRITICAL ABORT] Reason: <specific reason for abort>`\n\n"
            "Example: `[CRITICAL ABORT] Reason: Trading halted pending delisting - SEC notice of non-compliance`\n\n"
            "## Normal Operation\n\n"
            "STRICT CONSTRAINTS:\n"
            "- Output ONLY bulleted quantitative analysis with a summary table.\n"
            "- Cite exact values in standard format: $X.XX, +Y.Y% YoY, X.Xbps. No superlatives (\"massive\", \"huge\", \"significant\"). Every claim must reference a specific number, date, or source.\n\n"
            "- Keep the report concise: maximum 12 bullets and one compact markdown table.\n"
            "- Target <= 700 words total.\n\n"
            "If no catastrophic conditions are detected, continue with your analysis:\n\n"
            "2. Use the provided indicator pack to explain trend direction, momentum, "
            "volatility, and support/resistance. Anchor the report on the explicit values in "
            "the indicator sections; do not invent missing metrics.\n\n"
            "3. The indicator set was preselected for the detected regime. If one indicator "
            "conflicts with the broader setup, call that conflict out explicitly instead of "
            "rewriting the evidence.\n\n"
            "4. Write a detailed market report with actionable insights supported by the "
            "pre-loaded stock data, macro regime, and indicator readings. Make sure to append "
            "a Markdown table at the end of the report to organise key points for easy review."
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}\n\n"
                    "## Scanner Context\n\n{scanner_context}\n\n"
                    "## Pre-loaded Context\n\n{prefetched_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(scanner_context=scanner_context)
        prompt = prompt.partial(prefetched_context=prefetched_context)

        llm_for_market = llm
        if hasattr(llm, "bind"):
            try:
                llm_for_market = llm.bind(max_tokens=900)
            except Exception:
                llm_for_market = llm

        chain = prompt | llm_for_market
        configured_timeout = float(
            DEFAULT_CONFIG.get("quick_think_llm_timeout")
            or DEFAULT_CONFIG.get("llm_timeout")
            or 120.0
        )
        invoke_timeout = min(configured_timeout, 45.0)
        result, invoke_error = _invoke_with_timeout(
            chain,
            state["messages"],
            timeout_seconds=invoke_timeout,
        )
        if invoke_error is not None:
            if isinstance(invoke_error, TimeoutError):
                report = _build_timeout_fallback_report(
                    ticker=ticker,
                    as_of_date=current_date,
                    macro_regime_report=macro_regime_report,
                    timeout_seconds=invoke_timeout,
                )
                result = AIMessage(content=report)
            else:
                raise invoke_error

        report = result.content or ""
        structured = build_market_report_structured(
            ticker=ticker,
            as_of_date=current_date,
            market_report=report,
            macro_regime_report=macro_regime_report,
        )

        return {
            "messages": [result],
            "market_report": report,
            "macro_regime_report": macro_regime_report,
            "market_report_structured": structured,
        }

    return market_analyst_node
