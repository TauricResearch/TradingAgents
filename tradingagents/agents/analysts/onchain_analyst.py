"""On-chain Analyst — repurposed from the equity-era Fundamentals slot.

Bitcoin doesn't have earnings, P/E ratios, or insider trades. The
prediction-market equivalent of "look beyond price/news at the
underlying supply/demand structure" is **on-chain analytics**: who's
holding, who's moving coins onto exchanges, miner behavior, fee
pressure, ETF custody flows.

V1 uses free public data (blockchain.com + mempool.space). Glassnode /
CryptoQuant / Farside ETF flows are deferred to v1.1 — paid sources.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_kalshi_market,
    get_language_instruction,
    get_onchain_metrics,
)


def create_onchain_analyst(llm):
    def onchain_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_onchain_metrics, get_kalshi_market]

        system_message = (
            "You are the On-chain Analyst on a Kalshi prediction-market research desk. "
            "Bitcoin doesn't have a balance sheet, so the prediction-market analog of "
            "fundamentals is **on-chain activity**: hash rate, miner revenue, mempool "
            "depth + fee pressure, transaction volume. These reveal supply/demand "
            "pressure that won't show up in price charts or news headlines. "
            "Use `get_onchain_metrics(asset='BTC', look_back_days=7)` to pull the chain "
            "summary; use `get_kalshi_market(contract_id)` to anchor the discussion to "
            "the specific contract under analysis (status, YES/NO mid, settlement source). "
            "Write a comprehensive report tying each on-chain reading to a directional "
            "implication for the contract: rising hash rate + rising miner revenue suggest "
            "continued miner sell pressure; mempool congestion + high fees suggest "
            "elevated demand for block-space, often correlated with price runs; etc. "
            "Be honest where signals conflict — institutional rigor over hot-takes."
            " Append a Markdown table at the end summarizing the on-chain readings and their directional bias."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant collaborating with other analysts on a Kalshi "
                    "prediction-market research desk. Use the provided tools to progress towards "
                    "answering the question. If you or any other assistant has the FINAL TRANSACTION "
                    "PROPOSAL: **YES/NO/PASS** or deliverable, prefix your response with FINAL "
                    "TRANSACTION PROPOSAL: **YES/NO/PASS** so the team knows to stop. "
                    "You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
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
            "on_chain_report": report,
        }

    return onchain_analyst_node
