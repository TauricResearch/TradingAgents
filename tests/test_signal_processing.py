"""Tests for tradingagents.graph.signal_processing (SignalProcessor)."""

from unittest.mock import MagicMock

from tradingagents.graph.signal_processing import SignalProcessor


class TestSignalProcessor:
    def _make_processor(self, llm_response: str):
        """Create a SignalProcessor with a mocked LLM that returns the given text."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content=llm_response)
        return SignalProcessor(mock_llm), mock_llm

    def test_buy_signal(self):
        proc, llm = self._make_processor("BUY")
        result = proc.process_signal("Analysts recommend buying this stock.")
        assert result == "BUY"

    def test_sell_signal(self):
        proc, llm = self._make_processor("SELL")
        result = proc.process_signal("We recommend selling all positions.")
        assert result == "SELL"

    def test_hold_signal(self):
        proc, llm = self._make_processor("HOLD")
        result = proc.process_signal("Maintain current position, no action needed.")
        assert result == "HOLD"

    def test_llm_receives_correct_messages(self):
        proc, llm = self._make_processor("BUY")
        signal_text = "Strong bullish signal detected."
        proc.process_signal(signal_text)

        llm.invoke.assert_called_once()
        messages = llm.invoke.call_args[0][0]
        assert len(messages) == 2
        assert messages[0][0] == "system"
        assert "SELL, BUY, or HOLD" in messages[0][1]
        assert messages[1][0] == "human"
        assert messages[1][1] == signal_text

    def test_empty_signal(self):
        proc, llm = self._make_processor("HOLD")
        result = proc.process_signal("")
        assert result == "HOLD"
        llm.invoke.assert_called_once()

    def test_long_signal_text(self):
        """Processor should handle long analysis reports."""
        long_text = "Detailed analysis: " * 500
        proc, llm = self._make_processor("SELL")
        result = proc.process_signal(long_text)
        assert result == "SELL"
