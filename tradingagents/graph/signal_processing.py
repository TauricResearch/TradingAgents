# TradingAgents/graph/signal_processing.py

from langchain_openai import ChatOpenAI


class SignalProcessor:
    """Processes trading signals to extract actionable decisions."""

    def __init__(self, quick_thinking_llm: ChatOpenAI):
        """Initialize with an LLM for processing."""
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> dict:
        """
        Process a full trading signal to extract the core decision and hold_days.

        Args:
            full_signal: Complete trading signal text

        Returns:
            Dict with 'decision' (BUY/SELL/HOLD) and 'hold_days' (int or None)
        """
        messages = [
            (
                "system",
                "You are an efficient assistant designed to analyze paragraphs or financial reports "
                "provided by a group of analysts. Extract two pieces of information:\n"
                "1. The investment decision: SELL, BUY, or HOLD\n"
                "2. The recommended holding period in trading days (only for BUY or HOLD decisions)\n\n"
                "Respond in exactly this format (nothing else):\n"
                "DECISION: <BUY|SELL|HOLD>\n"
                "HOLD_DAYS: <number|N/A>\n\n"
                "For SELL decisions, always use HOLD_DAYS: N/A\n"
                "For BUY or HOLD decisions, extract the number of days if mentioned, otherwise default to 5.",
            ),
            ("human", full_signal),
        ]

        response = self.quick_thinking_llm.invoke(messages).content
        return self._parse_signal_response(response)

    def _parse_signal_response(self, response: str) -> dict:
        """Parse the structured LLM response into decision and hold_days."""
        decision = "HOLD"
        hold_days = None

        for line in response.strip().split("\n"):
            line = line.strip()
            upper = line.upper()
            if upper.startswith("DECISION:"):
                raw = upper.split(":", 1)[1].strip()
                # Strip markdown bold markers
                raw = raw.replace("*", "").strip()
                if raw in ("BUY", "SELL", "HOLD"):
                    decision = raw
            elif upper.startswith("HOLD_DAYS:"):
                raw = upper.split(":", 1)[1].strip()
                raw = raw.replace("*", "").strip()
                if raw not in ("N/A", "NA", "NONE", "-", ""):
                    try:
                        hold_days = int(raw)
                        # Clamp to reasonable range
                        hold_days = max(1, min(90, hold_days))
                    except (ValueError, TypeError):
                        hold_days = None

        # Enforce: SELL never has hold_days; BUY/HOLD default to 5 if missing
        if decision == "SELL":
            hold_days = None
        elif hold_days is None:
            hold_days = 5  # Default hold period

        return {"decision": decision, "hold_days": hold_days}
