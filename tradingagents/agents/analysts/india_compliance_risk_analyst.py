from langchain_core.messages import AIMessage

from tradingagents.agents.utils.agent_utils import get_instrument_context_from_state, get_language_instruction


INDIA_COMPLIANCE_DISCLAIMER = (
    "This output is for research and education only. It is not investment advice, "
    "a recommendation, an offer, or a solicitation to buy or sell securities. "
    "IndiaMarketAgents is not a SEBI-registered investment adviser or research analyst. "
    "Verify all data with official exchange/company filings and consult a qualified adviser before acting."
)


def create_india_compliance_risk_analyst(llm):
    def india_compliance_node(state):
        instrument_context = get_instrument_context_from_state(state)
        prompt = (
            "You are the India Compliance & Risk Guard Agent for IndiaMarketAgents. "
            "Review the accumulated reports for India-only scope, data gaps, SEBI/RA compliance concerns, "
            "live-trade language, personal-advice drift, unverified claims, and fabricated exchange data. "
            "Fail any report section that says execute trade now, gives order-placement instructions, "
            "or presents unavailable data as fact. Do not fabricate compliance conclusions; cite the "
            "specific report text or data-quality gap. Output compliance checks passed/failed, required "
            "disclaimers, data-quality warnings, and final guardrail notes. "
            "Require this disclaimer verbatim in the final report:\n\n"
            f"{INDIA_COMPLIANCE_DISCLAIMER}\n\n"
            f"{instrument_context}\n\n"
            f"Market report: {state.get('market_report', '')}\n\n"
            f"Fundamentals report: {state.get('fundamentals_report', '')}\n\n"
            f"News/filings report: {state.get('news_report', '')}\n\n"
            f"Macro/policy report: {state.get('india_macro_policy_report', '')}\n\n"
            f"Flows report: {state.get('india_flows_report', '')}\n\n"
            f"Sentiment report: {state.get('sentiment_report', '')}"
            + get_language_instruction()
        )
        response = llm.invoke(prompt)
        report = response.content
        return {"messages": [AIMessage(content=report)], "india_compliance_report": report}

    return india_compliance_node
