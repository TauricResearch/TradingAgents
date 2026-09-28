"""
/**
 * @module: TradingAgents
 * @file: test_credit_fundamentals_analyst.py
 * @description: Tests for credit fundamentals analyst
 * @author: AI Assistant
 * @created: 2026-09-28T10:35:23
 * @updated: 2026-09-28T10:35:23
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from unittest.mock import MagicMock
from tradingagents.agents.analysts.credit_fundamentals_analyst import create_credit_fundamentals_analyst


def test_create_credit_fundamentals_analyst_returns_function():
    """create_credit_fundamentals_analyst should return a callable node function."""
    llm = MagicMock()
    node = create_credit_fundamentals_analyst(llm)
    assert callable(node)


def test_credit_fundamentals_analyst_invokes_llm():
    """Credit fundamentals analyst should invoke LLM with tools."""
    llm = MagicMock()
    llm.bind_tools.return_value = MagicMock()
    llm.bind_tools.return_value.invoke.return_value = MagicMock(content="Test report", tool_calls=[])
    
    node = create_credit_fundamentals_analyst(llm)
    state = {
        "trade_date": "2026-09-27",
        "messages": [],
        "company_of_interest": "PETR4",
    }
    
    result = node(state)
    
    assert "messages" in result
    assert "fundamentals_report" in result
    assert llm.bind_tools.called
