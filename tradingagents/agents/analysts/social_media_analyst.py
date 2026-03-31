from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    format_prefetched_context,
    prefetch_tools_parallel,
)
from tradingagents.agents.utils.news_data_tools import get_social_sentiment


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)

        # ── Pre-fetch headline sentiment signals for the past 7 days ─────────
        trade_date = datetime.strptime(current_date, "%Y-%m-%d")
        start_date = (trade_date - timedelta(days=7)).strftime("%Y-%m-%d")

        prefetched = prefetch_tools_parallel(
            [
                {
                    "tool": get_social_sentiment,
                    "args": {
                        "ticker": ticker,
                        "start_date": start_date,
                        "end_date": current_date,
                    },
                    "label": "Headline Sentiment Signals (Last 7 Days)",
                },
            ]
        )
        prefetched_context = format_prefetched_context(prefetched)

        macro_regime_report = state.get("macro_regime_report", "")
        macro_regime_section = (
            "\n## Current Macro Regime\n"
            f"{macro_regime_report}\n\n"
            "Weight sentiment signals differently based on the current regime. In risk-off "
            "environments, negative sentiment carries more weight. In risk-on environments, "
            "positive momentum signals are more actionable.\n"
            if macro_regime_report
            else ""
        )

        system_message = (
            "You are analyzing market sentiment signals from headline patterns and publisher "
            "coverage for a specific company over the past week.\n\n"
            "## Pre-loaded Data\n\n"
            "Headline-level sentiment signals for the past 7 days have already been fetched and "
            "are provided in the **Pre-loaded Context** section below. The data includes each "
            "article headline with a polarity score (positive keywords minus negative keywords), "
            "the publishing outlet, an overall sentiment distribution, a publisher breakdown, "
            "and a first-half vs second-half trend. "
            "Do NOT call any news tool — the data is already available.\n\n"
            f"{macro_regime_section}"
            "## Your Task\n\n"
            "STRICT CONSTRAINTS:\n"
            "- Output ONLY bulleted quantitative analysis with a summary table.\n"
            "- Cite exact values in standard format: $X.XX, +Y.Y% YoY. No superlatives (\"massive\", \"huge\", \"significant\"). Every claim must reference a specific number, date, or source.\n"
            "- Focus on sentiment polarity shifts and volume-weighted signal strength.\n"
            "- Separate verified corporate actions from speculative social chatter.\n\n"
            "Using the pre-loaded news and social media data, write a comprehensive long report "
            "detailing your analysis, insights, and implications for traders and investors on "
            "this company's current state. Cover:\n"
            "- Social media sentiment and what people are saying about the company\n"
            "- Daily sentiment shifts over the past week\n"
            "- Recent company news and its implications\n\n"
            "Provide specific, actionable insights with supporting evidence to help traders make "
            "informed decisions. Make sure to append a Markdown table at the end of the report "
            "to organise key points, making it easy to read."
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
                    "## Pre-loaded Context\n\n{prefetched_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(prefetched_context=prefetched_context)

        # No tools remain — use direct invocation (no bind_tools, no tool loop)
        chain = prompt | llm

        result = chain.invoke(state["messages"])

        report = result.content or ""

        return {
            "messages": [result],
            "sentiment_report": report,
        }

    return social_media_analyst_node
