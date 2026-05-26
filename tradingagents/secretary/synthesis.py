"""Brief synthesis prompt + LLM call.

R3 mitigation: the prompt MUST explicitly instruct the model to preserve
disagreement, not average it away. Disagreement is signal.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


_SYNTHESIS_TEMPLATE = """You are the IIC Secretary. Three persona investment teams have each produced
an analysis of {ticker}. Your job is to synthesize their reports for a human
decision-maker.

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

Here are the persona reports:

{persona_reports}
"""


def build_synthesis_prompt(*, ticker: str, persona_runs: List[Dict[str, Any]]) -> str:
    blocks = []
    for r in persona_runs:
        pid = r.get("persona_id", "?")
        decision = r.get("decision", "?")
        body = r.get("final_trade_decision", "")
        blocks.append(f"=== {pid} ({decision}) ===\n{body}\n")
    return _SYNTHESIS_TEMPLATE.format(
        ticker=ticker, persona_reports="\n".join(blocks)
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
) -> Dict[str, str]:
    """Call the LLM with the synthesis prompt; parse into 3 sections.

    Returns dict with keys ``consensus``, ``divergence``, ``recommendation``,
    plus ``raw`` (the full LLM response text).
    """
    prompt = build_synthesis_prompt(ticker=ticker, persona_runs=persona_runs)
    response = llm.invoke(prompt)
    raw = getattr(response, "content", str(response))
    return {
        "consensus": _extract_section(raw, "Consensus"),
        "divergence": _extract_section(raw, "Divergence"),
        "recommendation": _extract_section(raw, "Recommendation"),
        "raw": raw,
    }
