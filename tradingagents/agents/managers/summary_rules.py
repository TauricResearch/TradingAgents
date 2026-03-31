"""Central rulesets for all prompt-compression summary nodes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SummaryRuleSet:
    name: str
    objective: str
    max_words: int
    sections: tuple[str, ...]
    rules: tuple[str, ...]


RESEARCH_PACKET_SUMMARY = SummaryRuleSet(
    name="research_packet_summary",
    objective="Compress multi-analyst trading research into a short downstream briefing.",
    max_words=350,
    sections=(
        "Market setup",
        "Fundamentals",
        "Sentiment and news",
        "Catalysts",
        "Risks",
        "Open questions",
    ),
    rules=(
        "Keep only evidence that is useful for downstream debate and portfolio decisions.",
        "Remove repetitive narrative, filler, and rhetorical phrasing.",
        "Prefer concrete facts, levels, catalysts, dates, and risks over commentary.",
        "Do not invent missing evidence.",
        "If a section has no evidence, write 'None noted.'",
    ),
)


INVESTMENT_DEBATE_SUMMARY = SummaryRuleSet(
    name="investment_debate_summary",
    objective="Maintain a rolling summary from the prior summary + the latest response.",
    max_words=220,
    sections=(
        "Bull case",
        "Bear case",
        "Disagreements",
        "Evidence to verify",
        "Current lean",
    ),
    rules=(
        "Keep only the strongest relevant arguments.",
        "Remove repetition and restatements.",
        "Keep tone neutral and decision-ready.",
        "Track unresolved factual disputes separately.",
        "Do not claim consensus unless both sides explicitly converge.",
    ),
)


RISK_DEBATE_SUMMARY = SummaryRuleSet(
    name="risk_debate_summary",
    objective="Maintain a rolling summary from the prior summary + the latest response.",
    max_words=220,
    sections=(
        "Upside case",
        "Risk case",
        "Positioning options",
        "Controls and stops",
        "Remaining conflicts",
    ),
    rules=(
        "Preserve only actionable portfolio-risk points.",
        "Remove repetition, rhetoric, and non-actionable commentary.",
        "Keep tone neutral and decision-ready.",
        "Prefer sizing, hedging, stop, and scenario language.",
        "Separate open disagreements from agreed controls.",
    ),
)


SCANNER_REPORT_SUMMARY = SummaryRuleSet(
    name="scanner_report_summary",
    objective="Compress a market-wide scanner report into a data-dense clinical summary for downstream synthesis.",
    max_words=250,
    sections=(
        "Primary Alpha Signals",
        "Quantified Macro Impact",
        "Ticker/Sector Outliers",
        "Systemic Risk Deltas",
    ),
    rules=(
        "Output ONLY clinical, quantitative analysis in bullet points.",
        "NO conversational filler, narrative, or roleplay.",
        "Retain all exact numeric values, percentages, and price levels.",
        "Prioritize evidence that contradicts or confirms existing macro themes.",
        "Ensure the summary is ready for algorithmic/quantitative synthesis.",
    ),
)


# Backward-compatible aliases while the rest of the codebase migrates.
RESEARCH_PACKET_SUMMARY_RULES = RESEARCH_PACKET_SUMMARY
INVESTMENT_DEBATE_SUMMARY_RULES = INVESTMENT_DEBATE_SUMMARY
RISK_DEBATE_SUMMARY_RULES = RISK_DEBATE_SUMMARY
SCANNER_REPORT_SUMMARY_RULES = SCANNER_REPORT_SUMMARY


def generate_summary_prompt(ruleset: SummaryRuleSet, input_text: str) -> str:
    sections_formatted = "\n".join(f"- **{section}**" for section in ruleset.sections)
    rules_formatted = "\n".join(f"- {rule}" for rule in ruleset.rules)

    return f"""You are a ruthless, highly precise quantitative financial summarizer.

## OBJECTIVE
{ruleset.objective}

## STRICT CONSTRAINTS
- **Maximum Length:** {ruleset.max_words} words. You will be penalized for exceeding this limit.
- **Tone:** Professional, clinical, and data-dense.

## REQUIRED SECTIONS
You must organize your output using EXACTLY these markdown headers, and nothing else:
{sections_formatted}

## SUMMARIZATION RULES
You must strictly adhere to the following rules:
{rules_formatted}

---

## INPUT TEXT TO SUMMARIZE:
{input_text}

## FINAL OUTPUT:
(Begin your summary now, strictly following the headers and rules above.)
"""
