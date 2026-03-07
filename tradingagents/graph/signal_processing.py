# TradingAgents/graph/signal_processing.py

import json
import re
from langchain_openai import ChatOpenAI


class SignalProcessor:
    """Processes trading signals to extract actionable decisions."""

    def __init__(self, quick_thinking_llm: ChatOpenAI):
        """Initialize with an LLM for processing."""
        self.quick_thinking_llm = quick_thinking_llm

    def _extract_json_from_response(self, response_str: str) -> str:
        """Extract JSON from response, handling markdown code blocks."""
        # Remove markdown code blocks if present
        code_block_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        match = re.search(code_block_pattern, response_str)
        if match:
            return match.group(1).strip()

        # Try to find JSON object directly
        json_pattern = r"\{[\s\S]*\}"
        match = re.search(json_pattern, response_str)
        if match:
            return match.group(0)

        return response_str

    def _extract_field_value(self, text: str, field: str, default):
        """Extract a field value from text using regex."""
        # Try to match "field": value or "field": "value"
        pattern = rf'"{field}"\s*:\s*("([^"]*?)"|(-?\d+\.?\d*))'
        match = re.search(pattern, text)
        if match:
            if match.group(2) is not None:  # String value
                return match.group(2)
            elif match.group(3) is not None:  # Numeric value
                try:
                    return float(match.group(3))
                except ValueError:
                    return default
        return default

    def _parse_response_with_regex(self, response_str: str) -> dict:
        """Parse response using regex when JSON parsing fails."""
        # Extract position
        position = "HOLD"
        pos_match = re.search(r'"position"\s*:\s*"(LONG|SHORT|HOLD)"', response_str, re.IGNORECASE)
        if pos_match:
            position = pos_match.group(1).upper()
        elif "LONG" in response_str.upper() and "SHORT" not in response_str.upper():
            position = "LONG"
        elif "SHORT" in response_str.upper() and "LONG" not in response_str.upper():
            position = "SHORT"

        # Extract numeric fields
        profit_match = re.search(r'"profit_estimate_pct"\s*:\s*(-?\d+\.?\d*)', response_str)
        profit = float(profit_match.group(1)) if profit_match else 0.0

        stop_loss_match = re.search(r'"stop_loss_pct"\s*:\s*(-?\d+\.?\d*)', response_str)
        stop_loss = float(stop_loss_match.group(1)) if stop_loss_match else 5.0

        # Extract risk level
        risk_match = re.search(r'"risk_level"\s*:\s*"(low|mid|high)"', response_str, re.IGNORECASE)
        risk_level = risk_match.group(1).lower() if risk_match else "mid"

        # Extract explanation - handle both quoted and unquoted
        explanation = "Unable to extract explanation."
        exp_match = re.search(r'"explanation"\s*:\s*"([^"]*)"', response_str)
        if exp_match:
            explanation = exp_match.group(1)
        else:
            # Try to get text after "explanation":
            exp_match = re.search(r'"explanation"\s*:\s*([^,}]+)', response_str)
            if exp_match:
                explanation = exp_match.group(1).strip().strip('"')

        return {
            "position": position,
            "profit_estimate_pct": profit,
            "stop_loss_pct": stop_loss,
            "risk_level": risk_level,
            "explanation": explanation[:300] if explanation else "Unable to extract explanation."
        }

    def process_signal(self, full_signal: str) -> dict:
        """
        Process a full trading signal to extract the core decision and analysis.

        Args:
            full_signal: Complete trading signal text

        Returns:
            Dictionary containing:
                - position: LONG, SHORT, or HOLD
                - profit_estimate_pct: Estimated profit percentage
                - stop_loss_pct: Recommended stop loss percentage
                - risk_level: low, mid, or high
                - explanation: Brief explanation of the decision
        """
        messages = [
            (
                "system",
                """You are an efficient assistant designed to analyze paragraphs or financial reports provided by a group of analysts for SHORT-TERM trading (1-2 week horizon). Your task is to extract the position recommendation and provide a structured analysis.

Extract and return a JSON object with the following fields:
1. "position": The position recommendation for the next 1-2 weeks - must be exactly one of: "LONG", "SHORT", or "HOLD"
2. "profit_estimate_pct": Your estimated profit/loss percentage over the next 1-2 weeks as a number (e.g., 5.5 for 5.5% profit, -3.0 for 3% loss). Base this on the short-term analysis provided.
3. "stop_loss_pct": The recommended stop loss percentage as a positive number (e.g., 3.0 for a 3% stop loss). This should be based on the risk level and volatility mentioned in the analysis.
4. "risk_level": The short-term risk level - must be exactly one of: "low", "mid", or "high"
5. "explanation": A brief 1-2 sentence explanation of why this position is recommended for the short-term (1-2 weeks)

Return ONLY the raw JSON object, no markdown formatting, no code blocks. Example:
{"position": "LONG", "profit_estimate_pct": 5.5, "stop_loss_pct": 3.0, "risk_level": "mid", "explanation": "Strong short-term momentum and upcoming catalyst support a bullish position for the next 1-2 weeks."}""",
            ),
            ("human", full_signal),
        ]

        response_content = self.quick_thinking_llm.invoke(messages).content
        print(response_content)
        response_str = str(response_content) if response_content else ""

        # Extract JSON from response (handles markdown code blocks)
        json_str = self._extract_json_from_response(response_str)

        try:
            result = json.loads(json_str)
            if "position" not in result:
                result["position"] = "HOLD"
            if "profit_estimate_pct" not in result:
                result["profit_estimate_pct"] = 0.0
            if "stop_loss_pct" not in result:
                result["stop_loss_pct"] = 5.0
            if "risk_level" not in result:
                result["risk_level"] = "mid"
            if "explanation" not in result:
                result["explanation"] = "Unable to extract detailed explanation."
            return result
        except json.JSONDecodeError:
            # Fallback to regex-based parsing
            return self._parse_response_with_regex(response_str)
