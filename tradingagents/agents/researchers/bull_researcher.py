from tradingagents.agents.utils.agent_utils import (
    truncate_prompt_text,
    use_compact_analysis_prompt,
)
from tradingagents.agents.utils.subagent_runner import (
    run_parallel_subagents,
    synthesize_subagent_results,
)


def create_bull_researcher(llm, memory):
    """
    Create a Bull Researcher node that uses parallel subagents for each dimension.

    Instead of a single large LLM call that times out, this implementation:
    1. Spawns parallel subagents for market, sentiment, news, fundamentals
    2. Each subagent has its own timeout (15s default)
    3. Synthesizes results into a unified bull argument
    4. If some subagents fail, still produces output with available results
    """
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(
            curr_situation,
            n_matches=1 if use_compact_analysis_prompt() else 2,
        )

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        # Build dimension-specific prompts for parallel execution
        dimension_configs = []

        # Market analysis subagent
        market_prompt = f"""You are a Bull Analyst focusing on MARKET data.

Based ONLY on the market report below, make a concise bull case (under 80 words).
Focus on: price trends, support/resistance, moving averages, technical indicators.
Address the latest bear argument directly if provided.

Market Report:
{truncate_prompt_text(market_research_report, 500)}

Debate History (for context):
{truncate_prompt_text(history, 200)}

Last Bear Argument:
{truncate_prompt_text(current_response, 150)}

Return your analysis in this format:
BULL CASE: [your concise bull argument]
CONFIDENCE: [HIGH/MEDIUM/LOW]
"""
        dimension_configs.append({
            "dimension": "market",
            "prompt": market_prompt,
        })

        # Sentiment analysis subagent
        sentiment_prompt = f"""You are a Bull Analyst focusing on SENTIMENT data.

Based ONLY on the sentiment report below, make a concise bull case (under 80 words).
Focus on: positive sentiment trends, social media bullishness, analyst upgrades.
Address the latest bear argument directly if provided.

Sentiment Report:
{truncate_prompt_text(sentiment_report, 300)}

Debate History (for context):
{truncate_prompt_text(history, 200)}

Last Bear Argument:
{truncate_prompt_text(current_response, 150)}

Return your analysis in this format:
BULL CASE: [your concise bull argument]
CONFIDENCE: [HIGH/MEDIUM/LOW]
"""
        dimension_configs.append({
            "dimension": "sentiment",
            "prompt": sentiment_prompt,
        })

        # News analysis subagent
        news_prompt = f"""You are a Bull Analyst focusing on NEWS data.

Based ONLY on the news report below, make a concise bull case (under 80 words).
Focus on: positive news, catalysts, strategic developments, partnerships.
Address the latest bear argument directly if provided.

News Report:
{truncate_prompt_text(news_report, 300)}

Debate History (for context):
{truncate_prompt_text(history, 200)}

Last Bear Argument:
{truncate_prompt_text(current_response, 150)}

Return your analysis in this format:
BULL CASE: [your concise bull argument]
CONFIDENCE: [HIGH/MEDIUM/LOW]
"""
        dimension_configs.append({
            "dimension": "news",
            "prompt": news_prompt,
        })

        # Fundamentals analysis subagent
        fundamentals_prompt = f"""You are a Bull Analyst focusing on FUNDAMENTALS data.

Based ONLY on the fundamentals report below, make a concise bull case (under 80 words).
Focus on: revenue growth, profit margins, cash flow, valuation metrics.
Address the latest bear argument directly if provided.

Fundamentals Report:
{truncate_prompt_text(fundamentals_report, 400)}

Debate History (for context):
{truncate_prompt_text(history, 200)}

Last Bear Argument:
{truncate_prompt_text(current_response, 150)}

Past Lessons:
{truncate_prompt_text(past_memory_str, 150)}

Return your analysis in this format:
BULL CASE: [your concise bull argument]
CONFIDENCE: [HIGH/MEDIUM/LOW]
"""
        dimension_configs.append({
            "dimension": "fundamentals",
            "prompt": fundamentals_prompt,
        })

        # Run all subagents in parallel with 25s timeout each (LLM can be slow)
        subagent_results = run_parallel_subagents(
            llm=llm,
            dimension_configs=dimension_configs,
            timeout_per_subagent=25.0,
            max_workers=4,
        )

        # Synthesize results into a unified bull argument
        synthesized_dimensions, synthesis_metadata = synthesize_subagent_results(
            subagent_results,
            max_chars_per_result=200,
        )

        # Generate the final bull argument using synthesis
        synthesis_prompt = f"""You are a Bull Analyst. Based on the following dimension analyses from your team,
synthesize a compelling bull argument (under 200 words) for this stock.

=== TEAM ANALYSIS RESULTS ===
{synthesized_dimensions}

=== SYNTHESIS INSTRUCTIONS ===
1. Combine the strongest bull points from each dimension
2. Address the latest bear argument directly
3. End with a clear stance: BUY, HOLD (with理由), or SELL (if overwhelming bear case)

Be decisive. Do not hedge. Present the bull case forcefully.
"""
        try:
            synthesis_response = llm.invoke(synthesis_prompt)
            final_argument = synthesis_response.content if hasattr(synthesis_response, 'content') else str(synthesis_response)
        except Exception as e:
            # Fallback: just use synthesized dimensions directly
            final_argument = f"""BULL SYNTHESIS FAILED: {str(e)}

=== AVAILABLE ANALYSES ===
{synthesized_dimensions}

FALLBACK CONCLUSION: Based on available data, the bull case is MIXTED.
Further analysis needed before making a definitive recommendation.
"""

        argument = f"Bull Analyst: {final_argument}"

        # Add subagent metadata to the argument for transparency
        timing_info = ", ".join([
            f"{dim}={timing}s"
            for dim, timing in synthesis_metadata["subagent_timings"].items()
        ])
        metadata_note = f"\n\n[Subagent timing: {timing_info}]"

        new_investment_debate_state = {
            "history": history + "\n" + argument + metadata_note,
            "bull_history": bull_history + "\n" + argument + metadata_note,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument + metadata_note,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
