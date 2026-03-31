"""Summary nodes that compress analyst and debate context for downstream agents."""

from __future__ import annotations

from tradingagents.agents.managers.summary_rules import (
    INVESTMENT_DEBATE_SUMMARY,
    RESEARCH_PACKET_SUMMARY,
    RISK_DEBATE_SUMMARY,
    generate_summary_prompt,
)

def _build_research_packet_input(
    market_report: str,
    sentiment_report: str,
    news_report: str,
    fundamentals_report: str,
    macro_regime_report: str,
) -> str:
    return f"""Market report:
{market_report}

Sentiment report:
{sentiment_report}

News report:
{news_report}

Fundamentals report:
{fundamentals_report}

Macro regime report:
{macro_regime_report}"""


def _build_investment_debate_input(prior_summary: str, current_response: str) -> str:
    return f"""Previous summary:
{prior_summary or 'No prior summary.'}

Latest response:
{current_response}"""


def _build_risk_debate_input(prior_summary: str, latest_speaker: str, current_response: str) -> str:
    return f"""Previous summary:
{prior_summary or 'No prior summary.'}

Latest speaker:
{latest_speaker}

Latest response:
{current_response}"""


def create_research_packet_summary(llm):
    def research_packet_summary_node(state) -> dict:
        market_report = str(state.get("market_report") or "").strip()
        sentiment_report = str(state.get("sentiment_report") or "").strip()
        news_report = str(state.get("news_report") or "").strip()
        fundamentals_report = str(state.get("fundamentals_report") or "").strip()
        macro_regime_report = str(state.get("macro_regime_report") or "").strip()

        if not any(
            (market_report, sentiment_report, news_report, fundamentals_report, macro_regime_report)
        ):
            return {
                "research_packet_summary": "",
                "sender": "research_packet_summary",
            }

        prompt = generate_summary_prompt(
            RESEARCH_PACKET_SUMMARY,
            _build_research_packet_input(
                market_report,
                sentiment_report,
                news_report,
                fundamentals_report,
                macro_regime_report,
            ),
        )
        response = llm.invoke(prompt)
        return {
            "research_packet_summary": str(response.content).strip(),
            "sender": "research_packet_summary",
        }

    return research_packet_summary_node


def create_investment_debate_summary(llm):
    def investment_debate_summary_node(state) -> dict:
        debate_state = state["investment_debate_state"]
        
        # FAST PATH: Heuristic aggregation of summary points instead of LLM call.
        
        sections = []
        
        bull_sum = debate_state.get("current_bull_summary")
        if bull_sum:
            sections.append(f"### Bull Analyst Points\n{bull_sum}")
        elif debate_state.get("bull_history"):
            sections.append(f"### Bull Analyst Points\n(No specific summary provided)")

        bear_sum = debate_state.get("current_bear_summary")
        if bear_sum:
            sections.append(f"### Bear Analyst Points\n{bear_sum}")
        elif debate_state.get("bear_history"):
            sections.append(f"### Bear Analyst Points\n(No specific summary provided)")

        summary = "\n\n".join(sections) if sections else "Investment debate in progress..."

        return {
            "investment_debate_state": {
                **debate_state,
                "summary": summary,
            },
            "sender": "investment_debate_summary",
        }

    return investment_debate_summary_node


def create_risk_debate_summary(llm):
    def risk_debate_summary_node(state) -> dict:
        debate_state = state["risk_debate_state"]
        
        # FAST PATH: Heuristic aggregation of summary points instead of LLM call.
        # This removes the single biggest sequential bottleneck in the pipeline.
        
        sections = []
        
        agg_sum = debate_state.get("current_aggressive_summary")
        if agg_sum:
            sections.append(f"### Aggressive Analyst Points\n{agg_sum}")
        elif debate_state.get("current_aggressive_response"):
            sections.append(f"### Aggressive Analyst Points\n(No specific summary provided)")

        con_sum = debate_state.get("current_conservative_summary")
        if con_sum:
            sections.append(f"### Conservative Analyst Points\n{con_sum}")
        elif debate_state.get("current_conservative_response"):
            sections.append(f"### Conservative Analyst Points\n(No specific summary provided)")

        neu_sum = debate_state.get("current_neutral_summary")
        if neu_sum:
            sections.append(f"### Neutral Analyst Points\n{neu_sum}")
        elif debate_state.get("current_neutral_response"):
            sections.append(f"### Neutral Analyst Points\n(No specific summary provided)")

        summary = "\n\n".join(sections) if sections else "Risk debate in progress..."

        return {
            "risk_debate_state": {
                **debate_state,
                "summary": summary,
            },
            "sender": "risk_debate_summary",
        }

    return risk_debate_summary_node
