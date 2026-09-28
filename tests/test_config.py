"""
/**
 * @module: TradingAgents
 * @file: test_config.py
 * @description: Tests for default configuration
 * @author: AI Assistant
 * @created: 2026-09-28T10:52:01
 * @updated: 2026-09-28T10:52:01
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from tradingagents.default_config import DEFAULT_CONFIG


def test_benchmark_map_has_brazil():
    """Benchmark map should include .SA (Brazil) entry."""
    assert ".SA" in DEFAULT_CONFIG["benchmark_map"]
    assert DEFAULT_CONFIG["benchmark_map"][".SA"] == "^IRFM"


def test_credit_holding_period_days():
    """Config should include credit_holding_period_days."""
    assert "credit_holding_period_days" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["credit_holding_period_days"] == 30
