# TradingAgents/graph/signal_processing.py

from langchain_openai import ChatOpenAI


class SignalProcessor:
    """Processes trading signals to extract actionable decisions."""

    def __init__(self, quick_thinking_llm: ChatOpenAI):
        """Initialize with an LLM for processing."""
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> str:
        """
        Process a full trading signal to extract the core decision.

        Args:
            full_signal: Complete trading signal text

        Returns:
            Extracted decision (LONG, SHORT, or HOLD)
        """
        messages = [
            (
                "system",
                "You are an efficient assistant designed to analyze paragraphs or financial reports provided by a group of analysts. Your task is to extract the investment decision: LONG, SHORT, or HOLD. Provide only the extracted decision (LONG, SHORT, or HOLD) as your output, without adding any additional text or information."
                 + """Output strictly a JSON block with the following format: {"position": "Long" | "Short" | "Hold", explanation: str, "profit_estimate_pct": float, "risk_level": "Low" | "Medium" | "High"}""",
            ),
            ("human", full_signal),
        ]

        return self.quick_thinking_llm.invoke(messages).content
