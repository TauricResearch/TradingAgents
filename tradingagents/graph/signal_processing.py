# TradingAgents/graph/signal_processing.py

import re
from langchain_openai import ChatOpenAI


class SignalProcessor:
    """Processes trading signals to extract actionable decisions."""

    def __init__(self, quick_thinking_llm: ChatOpenAI):
        """Initialize with an LLM for processing."""
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> dict:
        """
        Process a full trading signal to extract the core decision, hold_days,
        confidence, and risk level.

        Args:
            full_signal: Complete trading signal text

        Returns:
            Dict with 'decision', 'hold_days', 'confidence', 'risk'
        """
        messages = [
            (
                "system",
                "You are an efficient assistant designed to analyze financial reports "
                "provided by a group of analysts. Extract the following information:\n"
                "1. The investment decision: SELL, BUY, or HOLD\n"
                "2. The recommended holding period in trading days (only for BUY or HOLD decisions)\n"
                "3. The confidence level of the decision: HIGH, MEDIUM, or LOW\n"
                "4. The risk level of the investment: HIGH, MEDIUM, or LOW\n"
                "5. A brief rationale explaining the decision\n"
                "6. Key supporting evidence (top 3 data points)\n"
                "7. Key opposing evidence (top 2 data points arguing against the decision)\n\n"
                "Respond in exactly this format:\n"
                "DECISION: <BUY|SELL|HOLD>\n"
                "HOLD_DAYS: <number|N/A>\n"
                "CONFIDENCE: <HIGH|MEDIUM|LOW>\n"
                "RISK_LEVEL: <HIGH|MEDIUM|LOW>\n"
                "RATIONALE: <2-3 sentence explanation of WHY this decision>\n"
                "SUPPORTING: <top 3 data points, semicolon-separated>\n"
                "OPPOSING: <top 2 counter-arguments, semicolon-separated>\n\n"
                "For SELL decisions, always use HOLD_DAYS: N/A\n"
                "For BUY or HOLD decisions, extract the EXACT number of days mentioned in the report. "
                "Look for phrases like 'N-day hold', 'N trading days', 'hold for N days', "
                "'N-day horizon', 'over N days'. If no specific number is mentioned, use 5.\n"
                "For CONFIDENCE and RISK_LEVEL, infer from the tone and content of the report. Default to MEDIUM if unclear.\n"
                "For RATIONALE, summarize the core reasoning in 2-3 sentences.\n"
                "For SUPPORTING, list the 3 strongest data points that support the decision.\n"
                "For OPPOSING, list the 2 strongest counter-arguments or risks.",
            ),
            ("human", full_signal),
        ]

        response = self.quick_thinking_llm.invoke(messages).content
        result = self._parse_signal_response(response)

        # If LLM returned default hold_days (5) or failed to extract, try regex on original text
        if result["decision"] != "SELL" and result["hold_days"] == 5:
            regex_days = self._extract_hold_days_regex(full_signal)
            if regex_days is not None:
                result["hold_days"] = regex_days

        return result

    @staticmethod
    def _extract_hold_days_regex(text: str) -> int | None:
        """Extract hold period from text using regex patterns.

        Looks for common patterns like '15-day hold', 'hold for 45 days',
        '30 trading days', 'N-day horizon', etc.
        """
        patterns = [
            # "15-day hold", "45-day horizon", "30-day period"
            r'(\d+)[\s-]*(?:day|trading[\s-]*day)[\s-]*(?:hold|horizon|period|timeframe)',
            # "hold for 15 days", "holding period of 45 days"
            r'(?:hold|holding)[\s\w]*?(?:for|of|period\s+of)[\s]*(\d+)[\s]*(?:trading\s+)?days?',
            # "setting 45 trading days"
            r'setting\s+(\d+)\s+(?:trading\s+)?days',
            # "over 15 days", "within 30 days"
            r'(?:over|within|next)\s+(\d+)\s+(?:trading\s+)?days',
            # "N trading days (~2 months)" pattern
            r'(\d+)\s+trading\s+days?\s*\(',
        ]

        candidates = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                days = int(match.group(1))
                if 1 <= days <= 90:
                    candidates.append(days)

        if not candidates:
            return None

        # If multiple matches, prefer the one that appears in the conclusion
        # (last ~500 chars of text, which is typically the RATIONALE section)
        conclusion = text[-500:]
        for pattern in patterns:
            for match in re.finditer(pattern, conclusion, re.IGNORECASE):
                days = int(match.group(1))
                if 1 <= days <= 90:
                    return days

        # Fall back to most common candidate
        return max(set(candidates), key=candidates.count)

    def _parse_signal_response(self, response: str) -> dict:
        """Parse the structured LLM response into decision, hold_days, confidence, risk, and explainability fields."""
        decision = "HOLD"
        hold_days = None
        confidence = "MEDIUM"
        risk = "MEDIUM"
        rationale = ""
        supporting = ""
        opposing = ""

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
            elif upper.startswith("CONFIDENCE:"):
                raw = upper.split(":", 1)[1].strip()
                raw = raw.replace("*", "").strip()
                if raw in ("HIGH", "MEDIUM", "LOW"):
                    confidence = raw
            elif upper.startswith("RISK_LEVEL:") or upper.startswith("RISK:"):
                raw = upper.split(":", 1)[1].strip()
                raw = raw.replace("*", "").strip()
                if raw in ("HIGH", "MEDIUM", "LOW"):
                    risk = raw
            elif upper.startswith("RATIONALE:"):
                rationale = line.split(":", 1)[1].strip()
            elif upper.startswith("SUPPORTING:"):
                supporting = line.split(":", 1)[1].strip()
            elif upper.startswith("OPPOSING:"):
                opposing = line.split(":", 1)[1].strip()

        # Enforce: SELL never has hold_days; BUY/HOLD default to 5 if missing
        if decision == "SELL":
            hold_days = None
        elif hold_days is None:
            hold_days = 5  # Default hold period

        result = {"decision": decision, "hold_days": hold_days, "confidence": confidence, "risk": risk}
        if rationale:
            result["rationale"] = rationale
        if supporting:
            result["supporting"] = supporting
        if opposing:
            result["opposing"] = opposing
        return result
