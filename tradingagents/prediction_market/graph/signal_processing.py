# TradingAgents/prediction_market/graph/signal_processing.py

import json
from langchain_openai import ChatOpenAI


class PMSignalProcessor:
    """Processes prediction market trading signals to extract actionable decisions."""

    def __init__(self, quick_thinking_llm: ChatOpenAI):
        """Initialize with an LLM for processing."""
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> str:
        """
        Process a full prediction market trading signal to extract the core decision
        and structured data.

        Args:
            full_signal: Complete trading signal text from the risk manager

        Returns:
            JSON string with signal, estimated_probability, market_price, edge,
            position_size, and confidence
        """
        messages = [
            (
                "system",
                """You are an efficient assistant designed to analyze paragraphs or financial reports provided by a group of prediction market analysts. Your task is to extract the investment decision and key metrics.

Extract the following from the report:
1. signal: The investment decision - must be exactly one of: BUY_YES, BUY_NO, or PASS
2. estimated_probability: The estimated true probability (0.0 to 1.0), or null if not stated
3. market_price: The current market price/probability (0.0 to 1.0), or null if not stated
4. edge: The perceived edge (estimated_probability - market_price for YES, or market_price - estimated_probability for NO), or null if not stated
5. position_size: The recommended position size as a fraction (0.0 to 1.0), or null if not stated
6. confidence: The confidence level (low, medium, high), or null if not stated

Respond with ONLY valid JSON, no other text. Example:
{"signal": "BUY_YES", "estimated_probability": 0.65, "market_price": 0.50, "edge": 0.15, "position_size": 0.03, "confidence": "medium"}""",
            ),
            ("human", full_signal),
        ]

        result = self.quick_thinking_llm.invoke(messages).content

        # Try to parse as JSON; if it fails, wrap the raw signal
        try:
            parsed = json.loads(result)
            # Ensure signal field is valid
            if parsed.get("signal") not in ("BUY_YES", "BUY_NO", "PASS"):
                parsed["signal"] = "PASS"
            return json.dumps(parsed)
        except (json.JSONDecodeError, TypeError):
            # Fallback: extract just the signal keyword
            upper_result = result.upper()
            if "BUY_YES" in upper_result:
                signal = "BUY_YES"
            elif "BUY_NO" in upper_result:
                signal = "BUY_NO"
            else:
                signal = "PASS"

            return json.dumps({
                "signal": signal,
                "estimated_probability": None,
                "market_price": None,
                "edge": None,
                "position_size": None,
                "confidence": None,
                "raw_output": result,
            })
