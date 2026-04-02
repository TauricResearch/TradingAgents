"""Summary nodes that compress analyst and debate context for downstream agents."""

from __future__ import annotations

from tradingagents.agents.managers.summary_rules import (
    RESEARCH_PACKET_SUMMARY,
    generate_summary_prompt,
)
from tradingagents.agents.utils.summary_context import (
    build_investment_debate_summary,
    build_risk_debate_summary,
)

def _build_research_packet_input(
    market_report: str,
    sentiment_report: str,
    news_report: str,
    fundamentals_report: str,
    macro_regime_report: str,
    scanner_context_packet: str = "",
) -> str:
    scanner_section = f"Scanner Context (Phase 1):\n{scanner_context_packet}\n\n" if scanner_context_packet else ""
    return f"""{scanner_section}Market report:
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
        scanner_context_packet = str(state.get("scanner_context_packet") or "").strip()

        if not any(
            (market_report, sentiment_report, news_report, fundamentals_report, macro_regime_report, scanner_context_packet)
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
                scanner_context_packet,
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
        summary = build_investment_debate_summary(debate_state) or "Investment debate in progress..."

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
        summary = build_risk_debate_summary(debate_state) or "Risk debate in progress..."

        return {
            "risk_debate_state": {
                **debate_state,
                "summary": summary,
            },
            "sender": "risk_debate_summary",
        }

    return risk_debate_summary_node
