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
        prior_summary = str(debate_state.get("summary") or "").strip()
        current_response = str(debate_state.get("current_response") or "").strip()

        if not current_response:
            return {
                "investment_debate_state": {
                    **debate_state,
                    "summary": prior_summary,
                },
                "sender": "investment_debate_summary",
            }

        prompt = generate_summary_prompt(
            INVESTMENT_DEBATE_SUMMARY,
            _build_investment_debate_input(prior_summary, current_response),
        )
        response = llm.invoke(prompt)
        return {
            "investment_debate_state": {
                **debate_state,
                "summary": str(response.content).strip(),
            },
            "sender": "investment_debate_summary",
        }

    return investment_debate_summary_node


def create_risk_debate_summary(llm):
    def risk_debate_summary_node(state) -> dict:
        debate_state = state["risk_debate_state"]
        prior_summary = str(debate_state.get("summary") or "").strip()
        latest_speaker = str(debate_state.get("latest_speaker") or "").strip()

        current_response = ""
        if latest_speaker.startswith("Aggressive"):
            current_response = str(debate_state.get("current_aggressive_response") or "").strip()
        elif latest_speaker.startswith("Conservative"):
            current_response = str(debate_state.get("current_conservative_response") or "").strip()
        elif latest_speaker.startswith("Neutral"):
            current_response = str(debate_state.get("current_neutral_response") or "").strip()

        if not current_response:
            return {
                "risk_debate_state": {
                    **debate_state,
                    "summary": prior_summary,
                },
                "sender": "risk_debate_summary",
            }

        prompt = generate_summary_prompt(
            RISK_DEBATE_SUMMARY,
            _build_risk_debate_input(prior_summary, latest_speaker, current_response),
        )
        response = llm.invoke(prompt)
        return {
            "risk_debate_state": {
                **debate_state,
                "summary": str(response.content).strip(),
            },
            "sender": "risk_debate_summary",
        }

    return risk_debate_summary_node
