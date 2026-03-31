from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


def create_macro_synthesis(llm):
    def macro_synthesis_node(state):
        scan_date = state["scan_date"]

        # ── Collect all Phase 1/2 summaries for a high-level final report ──
        # We prefer pre-computed summaries over raw reports for token efficiency.
        context_parts = [
            f"Geopolitical & Macro: {state.get('geopolitical_summary', state.get('geopolitical_report', 'N/A'))}",
            f"Market Movers: {state.get('market_movers_summary', state.get('market_movers_report', 'N/A'))}",
            f"Sector Performance: {state.get('sector_summary', state.get('sector_performance_report', 'N/A'))}",
            f"Factor Alignment: {state.get('factor_alignment_summary', state.get('factor_alignment_report', 'N/A'))}",
            f"Drift Opportunities: {state.get('drift_opportunities_summary', state.get('drift_opportunities_report', 'N/A'))}",
            f"Smart Money: {state.get('smart_money_summary', state.get('smart_money_report', 'N/A'))}",
            f"Industry Deep Dive: {state.get('industry_deep_dive_report', 'N/A')}",
        ]
        context_section = "\n\n".join(context_parts)

        system_message = (
            "You are a Chief Investment Officer and Economist performing a final macro synthesis. "
            "Your objective is to integrate all scan reports into a clinical, actionable executive summary. "
            "STRICT CONSTRAINTS: Output ONLY bulleted quantitative analysis followed by a JSON list of tickers. NO conversational filler. "
            "Your report must include: "
            "(1) Global Macro Regime Decision (Risk-On/Risk-Off/Neutral), "
            "(2) Top 3 High-Conviction Sector themes, "
            "(3) Strategic Asset Allocation bias (Value/Growth/Defensive), "
            "(4) Validated Watchlist: A JSON array of 5-15 specific tickers to investigate further. "
            "Example JSON format at the end of your report: "
            "```json\n{\"stocks_to_investigate\": [\"AAPL\", \"NVDA\"]}\n```"
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Execute what you can to make progress."
                    "\n{system_message}"
                    " For your reference, the current date is {current_date}.\n\n"
                    "## Scan Reports Context\n\n{context_section}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=scan_date)
        prompt = prompt.partial(context_section=context_section)

        # Direct invocation (no tools)
        chain = prompt | llm

        result = chain.invoke(state["messages"])

        report = result.content or ""

        return {
            "messages": [result],
            "macro_scan_summary": report,
            "sender": "macro_synthesis",
        }

    return macro_synthesis_node
