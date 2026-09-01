"""Tests for time-horizon and stop-loss position plans."""

from __future__ import annotations

from tradingagents.execution.position_plan import (
    extract_time_horizon_from_pm,
    horizon_elapsed,
    horizon_end_date,
    is_within_horizon,
    plan_blocks_sell,
    plan_storage_key,
    stop_loss_breached,
)


class TestTimeHorizon:
    def test_extract_time_horizon(self):
        text = "**Rating**: Overweight\n\n**Time Horizon**: 3-6 months\n\n**Executive Summary**: Hold."
        assert extract_time_horizon_from_pm(text) == "3-6 months"

    def test_horizon_end_uses_longer_bound(self):
        assert horizon_end_date("2026-01-15", "3-6 months") == "2026-07-15"

    def test_within_horizon_before_end(self):
        plan = {"horizon_end_date": "2026-07-15", "time_horizon": "3-6 months"}
        assert is_within_horizon(plan=plan, trade_date="2026-03-01") is True
        assert horizon_elapsed(plan=plan, trade_date="2026-03-01") is False

    def test_sell_time_after_horizon(self):
        plan = {"horizon_end_date": "2026-07-15", "time_horizon": "3-6 months"}
        assert horizon_elapsed(plan=plan, trade_date="2026-07-16") is True
        assert is_within_horizon(plan=plan, trade_date="2026-07-16") is False


class TestStopAndHold:
    def test_stop_loss_breached(self):
        assert stop_loss_breached(current_price=90.0, stop_loss=95.0) is True
        assert stop_loss_breached(current_price=100.0, stop_loss=95.0) is False

    def test_hold_inside_window_even_if_pm_says_sell(self):
        plan = {
            "horizon_end_date": "2026-07-15",
            "time_horizon": "3-6 months",
            "stop_loss": 90.0,
        }
        blocked, reason = plan_blocks_sell(
            plan=plan,
            trade_date="2026-03-01",
            parsed_decision={"rating": "Sell", "stop_loss": 90.0},
            current_price=120.0,
        )
        assert blocked is True
        assert "Within plan window" in reason

    def test_allow_sell_when_stop_is_breached(self):
        plan = {
            "horizon_end_date": "2026-07-15",
            "time_horizon": "3-6 months",
            "stop_loss": 95.0,
        }
        blocked, reason = plan_blocks_sell(
            plan=plan,
            trade_date="2026-03-01",
            parsed_decision={"rating": "Hold", "stop_loss": 95.0},
            current_price=90.0,
        )
        assert blocked is False
        assert "Stop-loss" in reason

    def test_sell_time_after_horizon_does_not_block(self):
        plan = {
            "horizon_end_date": "2026-07-15",
            "time_horizon": "3-6 months",
            "stop_loss": 90.0,
        }
        blocked, reason = plan_blocks_sell(
            plan=plan,
            trade_date="2026-08-01",
            parsed_decision={"rating": "Sell", "stop_loss": 90.0},
            current_price=120.0,
        )
        assert blocked is False
        assert "Sell time" in reason

    def test_storage_key_is_account_scoped(self):
        assert plan_storage_key(account_scope="alpaca:123:1111", ticker="nvda") == (
            "alpaca:123:1111:NVDA"
        )
