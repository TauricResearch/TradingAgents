"""Extended tests for agent_utils functions not covered by test_instrument_identity.py.

Covers get_language_instruction, get_instrument_context_from_state, and create_msg_delete.
"""

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.agents.utils.agent_utils import (
    _clean_identity_value,
    create_msg_delete,
    get_instrument_context_from_state,
    get_language_instruction,
)

# ---------------------------------------------------------------------------
# _clean_identity_value
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCleanIdentityValue:
    def test_normal_string(self):
        assert _clean_identity_value("Apple Inc.") == "Apple Inc."

    def test_strips_whitespace(self):
        assert _clean_identity_value("  NVIDIA  ") == "NVIDIA"

    def test_empty_string_returns_none(self):
        assert _clean_identity_value("") is None

    def test_whitespace_only_returns_none(self):
        assert _clean_identity_value("   ") is None

    def test_none_input_returns_none(self):
        assert _clean_identity_value(None) is None

    def test_non_string_returns_none(self):
        assert _clean_identity_value(42) is None
        assert _clean_identity_value(3.14) is None

    def test_placeholder_values_return_none(self):
        for val in ("None", "N/A", "nan", "null", "NONE", "n/a", "NaN", "NULL"):
            assert _clean_identity_value(val) is None, f"Failed for {val}"


# ---------------------------------------------------------------------------
# get_language_instruction
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetLanguageInstruction:
    @patch("tradingagents.dataflows.config.get_config")
    def test_english_returns_empty(self, mock_config):
        mock_config.return_value = {"output_language": "English"}
        assert get_language_instruction() == ""

    @patch("tradingagents.dataflows.config.get_config")
    def test_english_case_insensitive(self, mock_config):
        mock_config.return_value = {"output_language": "english"}
        assert get_language_instruction() == ""

    @patch("tradingagents.dataflows.config.get_config")
    def test_english_with_whitespace(self, mock_config):
        mock_config.return_value = {"output_language": " English "}
        assert get_language_instruction() == ""

    @patch("tradingagents.dataflows.config.get_config")
    def test_non_english_returns_instruction(self, mock_config):
        mock_config.return_value = {"output_language": "Japanese"}
        result = get_language_instruction()
        assert "Japanese" in result
        assert "Write your entire response" in result

    @patch("tradingagents.dataflows.config.get_config")
    def test_missing_language_defaults_to_english(self, mock_config):
        mock_config.return_value = {}
        assert get_language_instruction() == ""


# ---------------------------------------------------------------------------
# get_instrument_context_from_state
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetInstrumentContextFromState:
    def test_returns_precomputed_context(self):
        state = {
            "company_of_interest": "NVDA",
            "asset_type": "stock",
            "instrument_context": "The instrument to analyze is `NVDA`. Company: NVIDIA.",
        }
        result = get_instrument_context_from_state(state)
        assert result == "The instrument to analyze is `NVDA`. Company: NVIDIA."

    def test_falls_back_to_ticker_only_when_context_empty(self):
        state = {
            "company_of_interest": "AAPL",
            "asset_type": "stock",
            "instrument_context": "",
        }
        result = get_instrument_context_from_state(state)
        assert "AAPL" in result

    def test_falls_back_when_context_missing(self):
        state = {
            "company_of_interest": "TSLA",
            "asset_type": "stock",
        }
        result = get_instrument_context_from_state(state)
        assert "TSLA" in result

    def test_falls_back_when_context_whitespace(self):
        state = {
            "company_of_interest": "GOOG",
            "asset_type": "stock",
            "instrument_context": "   ",
        }
        result = get_instrument_context_from_state(state)
        assert "GOOG" in result

    def test_crypto_fallback(self):
        state = {
            "company_of_interest": "BTC-USD",
            "asset_type": "crypto",
        }
        result = get_instrument_context_from_state(state)
        assert "BTC-USD" in result
        assert "crypto" in result.lower()


# ---------------------------------------------------------------------------
# create_msg_delete
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCreateMsgDelete:
    def test_returns_callable(self):
        fn = create_msg_delete()
        assert callable(fn)

    def test_clears_messages_and_adds_placeholder(self):
        msg1 = MagicMock(id="msg-1")
        msg2 = MagicMock(id="msg-2")
        state = {
            "messages": [msg1, msg2],
            "company_of_interest": "NVDA",
            "asset_type": "stock",
            "trade_date": "2026-01-15",
        }
        fn = create_msg_delete()
        result = fn(state)
        messages = result["messages"]
        assert len(messages) == 3
        assert messages[-1].content
        assert "NVDA" in messages[-1].content
        assert "2026-01-15" in messages[-1].content

    def test_placeholder_includes_instrument_context(self):
        state = {
            "messages": [],
            "company_of_interest": "AAPL",
            "asset_type": "stock",
            "instrument_context": "The instrument to analyze is `AAPL`. Company: Apple Inc.",
            "trade_date": "2026-06-01",
        }
        fn = create_msg_delete()
        result = fn(state)
        placeholder = result["messages"][-1]
        assert "AAPL" in placeholder.content
        assert "Apple Inc." in placeholder.content

    def test_placeholder_uses_default_date_when_missing(self):
        state = {
            "messages": [],
            "company_of_interest": "NVDA",
            "asset_type": "stock",
        }
        fn = create_msg_delete()
        result = fn(state)
        placeholder = result["messages"][-1]
        assert "the requested date" in placeholder.content
