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
            Extracted decision (BUY, SELL, or HOLD)
        """
        if not full_signal or len(full_signal.strip()) < 10:
            return "HOLD"

        import re

        signal_upper = full_signal.upper()

        buy_patterns = [
            r'FINAL\s+TRANSACTION\s+PROPOSAL:\s*\*\*BUY\*\*',
            r'FINAL\s+DECISION:\s*BUY',
            r'RECOMMENDATION:\s*BUY',
            r'DECISION:\s*BUY',
            r'PROPOSE:\s*BUY',
            r'\bBUY\b(?=\s*[.!]|\s*$)',
        ]

        sell_patterns = [
            r'FINAL\s+TRANSACTION\s+PROPOSAL:\s*\*\*SELL\*\*',
            r'FINAL\s+DECISION:\s*SELL',
            r'RECOMMENDATION:\s*SELL',
            r'DECISION:\s*SELL',
            r'PROPOSE:\s*SELL',
            r'\bSELL\b(?=\s*[.!]|\s*$)',
        ]

        hold_patterns = [
            r'FINAL\s+TRANSACTION\s+PROPOSAL:\s*\*\*HOLD\*\*',
            r'FINAL\s+DECISION:\s*HOLD',
            r'RECOMMENDATION:\s*HOLD',
            r'DECISION:\s*HOLD',
            r'PROPOSE:\s*HOLD',
            r'\bHOLD\b(?=\s*[.!]|\s*$)',
        ]

        for pattern in buy_patterns:
            if re.search(pattern, signal_upper):
                return "BUY"

        for pattern in sell_patterns:
            if re.search(pattern, signal_upper):
                return "SELL"

        for pattern in hold_patterns:
            if re.search(pattern, signal_upper):
                return "HOLD"

        buy_count = len(re.findall(r'\bBUY\b', signal_upper))
        sell_count = len(re.findall(r'\bSELL\b', signal_upper))
        hold_count = len(re.findall(r'\bHOLD\b', signal_upper))

        if buy_count > sell_count and buy_count > hold_count:
            return "BUY"
        elif sell_count > buy_count and sell_count > hold_count:
            return "SELL"
        elif hold_count > 0:
            return "HOLD"

        return "HOLD"
