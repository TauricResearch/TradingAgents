"""Free-text refinement intent classifier.

One quick_think_llm call. Returns a fixed-schema dict. Best-effort: always
returns a structured object, no 'unclear' branch. Invalid JSON → all overrides None.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


_PROMPT_TEMPLATE = """You are extracting refinement parameters from a user reply to an investment brief.
The original brief was about ticker(s): {scope}.

User reply: "{reply_text}"

Available overrides (set null if user didn't address them):
  - personas: subset of ["macro", "value", "momentum"] to keep for the refined run
  - risk_tilt: "more_aggressive" | "more_conservative"
  - horizon: "days" | "weeks" | "months" | "quarters"
  - analysts.include / analysts.exclude: subset of ["market", "news", "social", "fundamentals", "derivatives"]

Return ONLY a JSON object with keys exactly:
  {{"personas": ..., "risk_tilt": ..., "horizon": ..., "analysts": ..., "interpretation": ...}}

If the reply asks for new information rather than refinement (e.g. "what about
earnings?"), still extract what you can — V1 treats all replies as refinements.

Also write a one-sentence interpretation in the user's voice that will be echoed
back (e.g. "Got it — re-running with momentum dropped and a shorter horizon.").
"""


def _safe_json(text: str) -> Optional[Dict[str, Any]]:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return None


def classify_and_extract(
    *, reply_text: str, parent_brief: Dict[str, Any], llm: Any,
) -> Dict[str, Any]:
    prompt = _PROMPT_TEMPLATE.format(
        scope=parent_brief.get("scope", "(unknown)"),
        reply_text=reply_text.replace('"', "'"),
    )
    response = llm.invoke(prompt)
    raw = getattr(response, "content", str(response))
    parsed = _safe_json(raw) or {}

    return {
        "personas": parsed.get("personas") if isinstance(parsed.get("personas"), list) else None,
        "risk_tilt": parsed.get("risk_tilt") if parsed.get("risk_tilt") in
                     ("more_aggressive", "more_conservative") else None,
        "horizon": parsed.get("horizon") if parsed.get("horizon") in
                   ("days", "weeks", "months", "quarters") else None,
        "analysts": parsed.get("analysts") if isinstance(parsed.get("analysts"), dict) else None,
        "interpretation": parsed.get("interpretation") or "Got it — re-running with your tweaks.",
    }
