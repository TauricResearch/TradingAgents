from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_indicators,
    get_language_instruction,
    get_options_chain,
    get_stock_data,
)
from tradingagents.dataflows.config import get_config


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_stock_data,
            get_indicators,
            get_options_chain,
        ]

        system_message = (
            "You are a market analyst focused on short-term swing trades over the next 1-5 trading days. Call get_stock_data first, then call get_indicators. "
            "Select up to 9 indicators from this exact list of parameter names: "
            "close_5_ema, close_10_ema, close_20_ema, close_5_sma, close_10_sma, close_50_sma, macd, macds, macdh, rsi, boll, boll_ub, boll_lb, atr, vwma, mfi, volume, volume_20_sma, volume_50_sma. "
            "Prioritize short-term indicators as your primary signals: close_5_ema, close_10_ema, close_20_ema, macd, macdh, rsi, atr, volume, volume_20_sma. "
            "Use close_5_ema vs close_10_ema vs close_20_ema to judge immediate trend direction, pullback quality, and whether price is reclaiming or losing short-term momentum. "
            "Include close_50_sma only as a higher-timeframe reference level; do not let it dominate a short-term trade unless price is breaking it decisively. "
            "Always pull volume and volume_20_sma when judging breakouts, breakdowns, or 'holding above key level' setups: "
            "compute today's volume / volume_20_sma ratio and explicitly state whether a move is on expanding (>1.5x), normal (~1x), or shrinking (<0.7x) participation. "
            "A breakout or 放量站稳 (holding above resistance) reading should only be called valid when price action and volume confirmation align. "
            "Also call get_options_chain once to obtain near-expiry max pain, top-OI strikes, ATM IV, and IV skew — "
            "treat these as supplemental price-magnet / volatility-regime context, not as primary triggers. "
            "Structure your report in four sections: "
            "(1) Short-term signals — what the short-period indicators reveal about near-term direction, momentum, and optimal entry/exit timing; "
            "(2) Short-term levels — compare price against 5/10/20 EMA, recent 5-10 day support/resistance, "
            "and assess whether the short-term signal aligns with or diverges from the broader trend, and what that divergence implies for risk; "
            "(3) Volume confirmation — today's volume vs volume_20_sma, whether the recent move is backed by participation, and any divergence between price and volume; "
            "(4) Options-implied levels & volatility — note max pain and the nearest high-OI call/put strikes as candidate magnets or resistance/support, "
            "report ATM IV (rich vs cheap relative to recent realized volatility if knowable) and IV skew (a strongly positive put-call skew implies the market is paying up for downside hedges). "
            "Append a Markdown summary table at the end."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Use the provided tools to gather data and write your report."
                    " If you cannot fully answer, that's OK — your report will be used by downstream agents."
                    " Tools: {tool_names}.\n{system_message}"
                    " Current date: {current_date}. Strict-cutoff: use only data and events dated on or before this current date; never use later information. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "market_report": report,
        }

    return market_analyst_node
