from tradingagents.agents.utils.agent_utils import get_language_instruction
from tradingagents.audit.prompt_registry import default_registry


def create_bull_researcher(llm, prompt_registry=None):
    """Create the Bull researcher node.

    ``prompt_registry`` accepts a :class:`PromptRegistry` for tests that
    want to point at a custom prompts directory; the default uses the
    process-wide registry which reads from ``tradingagents/prompts/``.
    """
    registry = prompt_registry or default_registry()

    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        asset_type = state.get("asset_type", "stock")
        target_label = "stock" if asset_type == "stock" else "asset"
        fundamentals_label = (
            "Company fundamentals report"
            if asset_type == "stock"
            else "Asset fundamentals report (may be unavailable for crypto)"
        )

        version = state.get("prompt_versions", {}).get("researchers/bull_researcher", "v1")
        prompt, prompt_hash = registry.render(
            "researchers/bull_researcher",
            version=version,
            target_label=target_label,
            fundamentals_label=fundamentals_label,
            market_research_report=market_research_report,
            sentiment_report=sentiment_report,
            news_report=news_report,
            fundamentals_report=fundamentals_report,
            history=history,
            current_response=current_response,
            language_instruction=get_language_instruction(),
        )

        # Tag the LLM call with prompt provenance so TraceCallback's
        # metadata-extraction path picks it up automatically (no
        # callback changes required).
        response = llm.invoke(
            prompt,
            config={
                "metadata": {
                    "prompt_key": "researchers/bull_researcher",
                    "prompt_version": version,
                    "prompt_hash": prompt_hash,
                }
            },
        )

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
