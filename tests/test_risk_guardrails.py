"""Tests for the deterministic risk guardrails module."""

import sys
import os
import pytest
import importlib.util

# Load risk_guardrails directly by file path to avoid the graph __init__.py
# chain which eagerly imports langgraph (not installed in test-only environments).
_spec = importlib.util.spec_from_file_location(
    "risk_guardrails",
    os.path.join(os.path.dirname(__file__), "..", "tradingagents", "graph", "risk_guardrails.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
RiskGuardrails = _mod.RiskGuardrails
GuardrailConfig = _mod.GuardrailConfig


# ── Fixtures ──

SAMPLE_BUY_DECISION = """**Rating**: Buy

**Executive Summary**: Strong momentum setup with bullish EMA stack and rising volume.

**Investment Thesis**: Technical indicators align with fundamental strength. RSI at 62 suggests room for upside.

**Entry Price**: 150.00

**Stop Loss**: 142.50

**Position Sizing**: 30% of portfolio

**Time Horizon**: 2-4 weeks"""

SAMPLE_BUY_NO_STOP = """**Rating**: Buy

**Executive Summary**: Strong setup, enter at market.

**Investment Thesis**: Everything looks great.

**Entry Price**: 50.00

**Position Sizing**: 10% of portfolio"""

SAMPLE_OVERSIZE = """**Rating**: Overweight

**Executive Summary**: Go heavy on this one.

**Investment Thesis**: Once in a lifetime opportunity.

**Entry Price**: 200.00

**Stop Loss**: 190.00

**Position Sizing**: 60% of portfolio

**Time Horizon**: 1-3 months"""

SAMPLE_WIDE_STOP = """**Rating**: Buy

**Executive Summary**: Volatile stock, need room to breathe.

**Investment Thesis**: High ATR play.

**Entry Price**: 100.00

**Stop Loss**: 80.00

**Position Sizing**: 15% of portfolio"""


class TestGuardrailsDisabled:
    """When guardrails are disabled, decisions pass through unchanged."""

    def test_passthrough(self):
        guardrails = RiskGuardrails({"risk_guardrails_enabled": False})
        result = guardrails.check(SAMPLE_BUY_DECISION)
        assert not result.was_modified
        assert result.modified_decision == SAMPLE_BUY_DECISION
        assert len(result.violations) == 0


class TestPositionSizingCap:
    """Position sizing should be clamped to max_position_pct."""

    def test_oversize_clamped(self):
        guardrails = RiskGuardrails({
            "risk_guardrails_enabled": True,
            "max_position_pct": 25.0,
        })
        result = guardrails.check(SAMPLE_OVERSIZE)
        assert result.was_modified
        assert "25%" in result.modified_decision
        assert "CLAMPED" in result.violations[0]
        assert "Position Sizing" in result.clamped_fields

    def test_within_limit_passes(self):
        guardrails = RiskGuardrails({
            "risk_guardrails_enabled": True,
            "max_position_pct": 50.0,
        })
        result = guardrails.check(SAMPLE_BUY_DECISION)
        # 30% is within 50% limit — only stop-loss check might trigger
        assert "CLAMPED" not in str(result.violations)


class TestStopLossRequirement:
    """Buy/Overweight without stop-loss should trigger a warning."""

    def test_missing_stop_loss_warning(self):
        guardrails = RiskGuardrails({
            "risk_guardrails_enabled": True,
            "require_stop_loss": True,
        })
        result = guardrails.check(SAMPLE_BUY_NO_STOP)
        assert result.was_modified
        assert "Risk Guardrail Warning" in result.modified_decision
        assert any("stop-loss" in v.lower() for v in result.violations)

    def test_stop_loss_present_passes(self):
        guardrails = RiskGuardrails({
            "risk_guardrails_enabled": True,
            "require_stop_loss": True,
            "max_position_pct": 100.0,  # don't trigger size cap
        })
        result = guardrails.check(SAMPLE_BUY_DECISION)
        assert not any("stop-loss" in v.lower() for v in result.violations)


class TestWideStopAlert:
    """Stop-loss distance exceeding max_single_loss_pct triggers an alert."""

    def test_wide_stop_alert(self):
        guardrails = RiskGuardrails({
            "risk_guardrails_enabled": True,
            "max_single_loss_pct": 5.0,
        })
        result = guardrails.check(SAMPLE_WIDE_STOP)
        # 100 → 80 = 20% loss, way over 5%
        assert result.was_modified
        assert any("stop-loss distance" in v.lower() for v in result.violations)

    def test_tight_stop_passes(self):
        guardrails = RiskGuardrails({
            "risk_guardrails_enabled": True,
            "max_single_loss_pct": 10.0,
            "max_position_pct": 100.0,
        })
        result = guardrails.check(SAMPLE_BUY_DECISION)
        # 150 → 142.50 = 5% loss, within 10%
        assert not any("stop-loss distance" in v.lower() for v in result.violations)


class TestBlockedRatings:
    """Blocked ratings should be overridden to Hold."""

    def test_blocked_buy(self):
        guardrails = RiskGuardrails({
            "risk_guardrails_enabled": True,
            "blocked_ratings": ["Buy"],
            "max_position_pct": 100.0,
        })
        result = guardrails.check(SAMPLE_BUY_DECISION)
        assert result.was_modified
        assert "Hold" in result.modified_decision
        assert "BLOCKED" in result.violations[0]

    def test_unblocked_passes(self):
        guardrails = RiskGuardrails({
            "risk_guardrails_enabled": True,
            "blocked_ratings": ["Sell"],
            "max_position_pct": 100.0,
        })
        result = guardrails.check(SAMPLE_BUY_DECISION)
        assert "BLOCKED" not in str(result.violations)


class TestFieldParsing:
    """Edge cases in markdown field extraction."""

    def test_extract_field(self):
        text = "**Rating**: Buy\n**Stop Loss**: 42.50"
        assert RiskGuardrails._extract_field(text, "Rating") == "Buy"
        assert RiskGuardrails._extract_field(text, "Stop Loss") == "42.50"
        assert RiskGuardrails._extract_field(text, "Nonexistent") is None

    def test_extract_percentage(self):
        assert RiskGuardrails._extract_percentage("30% of portfolio") == 30.0
        assert RiskGuardrails._extract_percentage("no pct here") is None
        assert RiskGuardrails._extract_percentage("5.5% allocation") == 5.5
