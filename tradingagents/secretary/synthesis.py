"""Brief synthesis prompt + LLM call.

R3 mitigation: the prompt MUST explicitly instruct the model to preserve
disagreement, not average it away. Disagreement is signal.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# STABLE prefix: the fully-static rubric (role + section instructions + ##
# headings) is byte-identical across every call, so it must come FIRST for
# DeepSeek prefix-cache reuse. All VARIABLE content (ticker, persona reports,
# and the event_alert trigger block) is appended at the TAIL below.
_SYNTHESIS_TEMPLATE = """You are the IIC Secretary. The input contains one or more investment analyses
for a stock. Your job is to synthesize the reports for a human decision-maker.
If there is only one balanced analysis, surface the important internal
TradingAgents disagreements from that report. If there are multiple committee
analyses, compare them directly.

Produce EXACTLY three sections, in this order, with these exact headings:

## Consensus
What do all personas agree on? Be specific — name the thesis, not just "they
agreed it's a stock".

## Divergence
Where do the personas disagree, and why? This section is the most important
in the brief. Do NOT smooth over disagreement; surface it. Use this shape:
- Persona X says Y because Z. Persona A says B because C. The disagreement
  hinges on <the load-bearing assumption>.

## Recommendation
One of BUY / HOLD / SELL with a confidence rationale. If the divergence in
the previous section is material, explicitly say so and recommend HOLD with
a "low-confidence call" note.
"""


def build_synthesis_prompt(*, ticker: str, persona_runs: List[Dict[str, Any]]) -> str:
    blocks = []
    for r in persona_runs:
        pid = r.get("persona_id", "?")
        decision = r.get("decision", "?")
        body = r.get("final_trade_decision", "")
        blocks.append(f"=== {pid} ({decision}) ===\n{body}\n")
    persona_reports = "\n".join(blocks)
    return (
        _SYNTHESIS_TEMPLATE
        + f"\nThe persona reports below analyze {ticker}.\n\n"
        + f"Here are the persona reports:\n\n{persona_reports}\n"
    )


def _extract_section(text: str, heading: str) -> str:
    """Extract markdown section under '## <heading>' until the next '## ' or EOF."""
    pattern = rf"##\s+{re.escape(heading)}\s*\n(.+?)(?=\n##\s+|\Z)"
    m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""


def synthesize_brief(
    *,
    llm: Any,
    ticker: str,
    persona_runs: List[Dict[str, Any]],
    event_context: Optional[str] = None,
) -> Dict[str, str]:
    """Call the LLM with the synthesis prompt; parse into 3 sections.

    When ``event_context`` is non-empty (event_alert mode), it is appended
    to the prompt as the trigger context. None / empty ≡ deep-dive mode.

    Returns dict with keys ``consensus``, ``divergence``, ``recommendation``,
    plus ``raw`` (the full LLM response text).
    """
    prompt = build_synthesis_prompt(ticker=ticker, persona_runs=persona_runs)
    if event_context:
        # Append the variable trigger-event block at the TAIL so the static
        # rubric prefix stays byte-identical across calls for prompt caching.
        prompt = (
            prompt
            + f"\nTRIGGER EVENT for {ticker}:\n\n{event_context}\n\n"
            + f"Synthesize the three persona reports above into a terse "
            + f"consensus / divergence / recommendation for this event.\n"
        )
    response = llm.invoke(prompt)
    raw = getattr(response, "content", str(response))
    return {
        "consensus": _extract_section(raw, "Consensus"),
        "divergence": _extract_section(raw, "Divergence"),
        "recommendation": _extract_section(raw, "Recommendation"),
        "raw": raw,
    }
