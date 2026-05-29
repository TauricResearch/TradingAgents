import unittest
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage, RemoveMessage

from tradingagents.agents.utils.agent_utils import create_msg_delete


class CreateMsgDeleteTests(unittest.TestCase):
    def _make_state(self, ticker="AAPL", asset_type="stock", trade_date="2026-01-15"):
        msg = MagicMock()
        msg.id = "msg-1"
        return {
            "messages": [msg],
            "company_of_interest": ticker,
            "asset_type": asset_type,
            "trade_date": trade_date,
        }

    def test_placeholder_contains_ticker(self):
        state = self._make_state(ticker="EC")
        result = create_msg_delete()(state)
        human_messages = [m for m in result["messages"] if hasattr(m, "content")]
        self.assertTrue(any("`EC`" in m.content for m in human_messages))

    def test_placeholder_contains_trade_date(self):
        state = self._make_state(trade_date="2026-05-28")
        result = create_msg_delete()(state)
        human_messages = [m for m in result["messages"] if hasattr(m, "content")]
        self.assertTrue(any("2026-05-28" in m.content for m in human_messages))

    def test_placeholder_contains_asset_type(self):
        state = self._make_state(asset_type="crypto")
        result = create_msg_delete()(state)
        human_messages = [m for m in result["messages"] if hasattr(m, "content")]
        self.assertTrue(any("crypto" in m.content for m in human_messages))

    def test_placeholder_is_not_bare_continue(self):
        state = self._make_state()
        result = create_msg_delete()(state)
        human_messages = [m for m in result["messages"] if hasattr(m, "content")]
        self.assertFalse(
            any(m.content.strip() == "Continue" for m in human_messages),
            "Placeholder must not be the bare word 'Continue'",
        )

    def test_removes_existing_messages(self):
        state = self._make_state()
        result = create_msg_delete()(state)
        remove_ops = [m for m in result["messages"] if isinstance(m, RemoveMessage)]
        human_ops = [m for m in result["messages"] if isinstance(m, HumanMessage)]
        self.assertEqual(len(remove_ops), 1)
        self.assertEqual(len(human_ops), 1)
