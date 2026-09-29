"""
/**
 * @module: TradingAgents
 * @file: test_credit_news_analyst.py
 * @description: Tests for credit news analyst
 * @author: Maíra Pontin
 * @created: 2026-09-28T10:46:55
 * @updated: 2026-09-28T11:05:32
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from unittest.mock import MagicMock
from tradingagents.agents.analysts.credit_news_analyst import create_credit_news_analyst


def test_create_credit_news_analyst_returns_function():
    """create_credit_news_analyst should return a callable node function."""
    llm = MagicMock()
    node = create_credit_news_analyst(llm)
    assert callable(node)


def test_credit_news_analyst_invokes_llm():
    """Credit news analyst should invoke LLM with tools."""
    llm = MagicMock()
    llm.bind_tools.return_value = MagicMock()
    llm.bind_tools.return_value.invoke.return_value = MagicMock(content="Test news report", tool_calls=[])
    
    node = create_credit_news_analyst(llm)
    state = {
        "trade_date": "2026-09-27",
        "messages": [],
        "company_of_interest": "PETR4",
    }
    
    result = node(state)
    
    assert "messages" in result
    assert "news_report" in result
    assert llm.bind_tools.called
