# TradingAgents/graph/signal_processing.py

import re

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
            Extracted decision (BUY or PASS) - legacy mode
        """
        messages = [
            (
                "system",
                "너는 애널리스트 리포트에서 최종 투자 결론만 추출하는 파서다. 한국어/영어 혼합 문서도 처리한다. 우선순위는 (1) 마지막 `FINAL TRANSACTION PROPOSAL: **BUY/PASS**` 표기, (2) 명시적 최종 권고 문장이다. 출력은 반드시 BUY 또는 PASS 한 단어만 반환하고, 다른 문구는 절대 출력하지 마라.",
            ),
            ("human", full_signal),
        ]

        return self.quick_thinking_llm.invoke(messages).content

    def process_swing_signal(self, full_signal: str) -> dict:
        """
        Process a swing trading signal to extract decision + order parameters.

        Args:
            full_signal: Complete trading signal text with SWING_ORDER block

        Returns:
            Dict with action, entry_price, stop_loss, take_profit,
            position_size_pct, max_hold_days, rationale
        """
        result = {
            "action": "PASS",
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
            "position_size_pct": None,
            "max_hold_days": None,
            "rationale": "",
        }

        # Try to extract SWING_ORDER block first
        order_block = self._extract_swing_order(full_signal)
        if order_block:
            result.update(order_block)
        else:
            # Fallback: use LLM to extract
            result = self._llm_extract_swing_signal(full_signal)

        # Validate action
        if result["action"] not in ("BUY", "SELL", "HOLD", "PASS"):
            result["action"] = "PASS"

        return result

    def _extract_swing_order(self, text: str) -> dict | None:
        """Extract structured SWING_ORDER block from text using regex."""
        pattern = r"SWING_ORDER:\s*\n(.*?)(?:\n```|\Z)"
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            # Try without code block
            pattern = r"SWING_ORDER:\s*\n((?:\s+\w+:.*\n?)+)"
            match = re.search(pattern, text, re.DOTALL)
        if not match:
            return None

        block = match.group(1)
        result = {}

        field_map = {
            "ACTION": ("action", str),
            "ENTRY_PRICE": ("entry_price", float),
            "STOP_LOSS": ("stop_loss", float),
            "TAKE_PROFIT": ("take_profit", float),
            "POSITION_SIZE_PCT": ("position_size_pct", float),
            "MAX_HOLD_DAYS": ("max_hold_days", int),
            "RATIONALE": ("rationale", str),
        }

        for key, (field_name, converter) in field_map.items():
            field_pattern = rf"{key}:\s*(.+?)(?:\n|$)"
            field_match = re.search(field_pattern, block)
            if field_match:
                raw_value = field_match.group(1).strip()
                try:
                    if converter in (float, int):
                        # Remove commas and currency symbols
                        cleaned = re.sub(r"[^\d.\-]", "", raw_value)
                        if cleaned:
                            result[field_name] = converter(cleaned)
                    else:
                        result[field_name] = raw_value
                except (ValueError, TypeError):
                    pass

        return result if "action" in result else None

    def _llm_extract_swing_signal(self, full_signal: str) -> dict:
        """Fallback: use LLM to extract swing trading signal."""
        messages = [
            (
                "system",
                """너는 스윙 트레이딩 리포트에서 최종 투자 결론과 주문 정보를 추출하는 파서다.
반드시 아래 JSON 형식만 출력하라. 다른 텍스트는 절대 출력하지 마라.

{"action": "BUY|SELL|HOLD|PASS", "entry_price": 숫자|null, "stop_loss": 숫자|null, "take_profit": 숫자|null, "position_size_pct": 숫자|null, "max_hold_days": 숫자|null, "rationale": "한 줄 요약"}""",
            ),
            ("human", full_signal),
        ]

        import json

        response = self.quick_thinking_llm.invoke(messages).content
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Last resort: extract action only
            action = "PASS"
            for keyword in ("BUY", "SELL", "HOLD", "PASS"):
                if keyword in response.upper():
                    action = keyword
                    break
            return {
                "action": action,
                "entry_price": None,
                "stop_loss": None,
                "take_profit": None,
                "position_size_pct": None,
                "max_hold_days": None,
                "rationale": "",
            }
