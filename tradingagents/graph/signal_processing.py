"""Signal processing for extracting structured prediction decisions."""

import json
import re


class SignalProcessor:
    """Processes raw LLM output into structured prediction decisions."""

    def __init__(self, quick_thinking_llm):
        self.llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> str:
        """Extract structured JSON decision from the final decision text."""
        prompt = f"""Extract the final prediction decision from the following analysis.
Return ONLY a valid JSON object with these exact fields:
- "action": one of "YES", "NO", or "SKIP"
- "confidence": a float between 0.0 and 1.0
- "edge": estimated probability minus market price (float, can be negative)
- "position_size": recommended bet size as fraction of bankroll (float 0.0-1.0)
- "reasoning": one sentence summary
- "time_horizon": time until event resolution

Analysis:
{full_signal}

Return ONLY the JSON object, no other text."""

        response = self.llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        try:
            json_match = re.search(r'\{[^\{\}]*\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                required = ["action", "confidence", "edge", "position_size", "reasoning", "time_horizon"]
                if all(k in parsed for k in required):
                    parsed["action"] = parsed["action"].upper().strip()
                    if parsed["action"] not in ("YES", "NO", "SKIP"):
                        parsed["action"] = "SKIP"
                    return json.dumps(parsed)
        except (json.JSONDecodeError, AttributeError):
            pass

        action = "SKIP"
        text_upper = content.upper()
        if "YES" in text_upper and "NO" not in text_upper:
            action = "YES"
        elif "NO" in text_upper and "YES" not in text_upper:
            action = "NO"

        return json.dumps({
            "action": action,
            "confidence": 0.5,
            "edge": 0.0,
            "position_size": 0.0,
            "reasoning": "Could not parse structured output from LLM response.",
            "time_horizon": "unknown",
        })
