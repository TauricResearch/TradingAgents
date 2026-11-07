from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.analysts.turn import take_turn
from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.tools import get_dcf_valuation, get_peer_multiples

# The tools this analyst is offered; its tool node is built from the same tuple.
TOOLS = (
    get_dcf_valuation,
    get_peer_multiples,
)


def create_valuation_analyst(llm):
    def valuation_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        system_message = (
            "You are a valuation analyst. Estimate what the company is worth and compare it with the price, "
            "using two tools whose figures are computed in code: `get_dcf_valuation` (a discounted cash flow "
            "with its assumptions, a sensitivity table and the upside versus the last close) and "
            "`get_peer_multiples` (the company's P/E, EV/EBITDA, P/S and P/B against its peers' medians, with "
            "the price each implies). Call both tools once each, then write the report."
            " Rules: every number you cite must come from a tool result; never calculate, estimate or round "
            "a figure into existence yourself. When a tool says UNAVAILABLE, say that the figure is "
            "unavailable and give the reason it states; do not substitute your own. When the DCF says it does "
            "not apply (a bank or insurer), rely on P/B, P/E and ROE as the tools present them."
            " Interpret, don't recompute: say which assumptions drive the DCF value (growth, WACC, terminal "
            "share of enterprise value), read the sensitivity table for how fragile it is, say where the DCF "
            "and the peer multiples agree or disagree, and say what would have to be true for the price to be "
            "right. State the date and currency basis of the figures."
            " Make sure to append a Markdown table at the end of the report summarizing each method, its value "
            "per share, and the upside or downside versus the price."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " Report what your tools support; another agent decides the trade."
                    " You have access to the following tools: {tool_names}."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
                    "{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in TOOLS]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        result, report = take_turn(prompt, llm, TOOLS, state["messages"])

        return {
            "messages": [result],
            "valuation_report": report,
        }

    return valuation_analyst_node
