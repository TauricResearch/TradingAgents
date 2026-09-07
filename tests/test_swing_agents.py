"""Unit tests for the Vietnam Swing Trading 3-Agent Architecture.

Tests:
1. RegimeAgent: VN-Index trend detection, distribution days, traffic light logic.
2. SetupAgent: Liquidity gate, VCP contraction, Volume Dry-Up (VDU), Breakout triggers.
3. RiskAgent: Lot 100 constraints, NAV risk budgeting, T+2.5 settlement cycle, exit actions.
"""

from datetime import datetime, time, timedelta
import numpy as np
import pandas as pd
import pytest

from tradingagents.swing.regime_agent import MarketRegimeResult, RegimeAgent, RegimeStatus
from tradingagents.swing.risk_agent import (
    ExitAction,
    PortfolioPosition,
    PositionPlan,
    RiskAgent,
    TPlusStatus,
)
from tradingagents.swing.setup_agent import SetupAgent, SetupResult, SetupStatus


def make_sample_ohlcv(
    n_bars: int = 60,
    base_price: float = 50_000.0,
    trend_slope: float = 0.001,
    base_volume: float = 1_000_000.0,
    tighten_end: bool = False,
    volume_dry_end: bool = False,
    breakout_last_bar: bool = False,
) -> pd.DataFrame:
    """Generate synthetic OHLCV bars for testing."""
    records = []
    price = base_price

    for i in range(n_bars):
        price = price * (1.0 + trend_slope)
        daily_range = price * 0.03

        # Simulate tightening volatility at the end (VCP)
        if tighten_end and i >= n_bars - 5:
            daily_range = price * 0.008

        high = price + daily_range / 2
        low = price - daily_range / 2
        open_p = low + (high - low) * 0.4
        close_p = low + (high - low) * 0.6
        vol = base_volume

        if volume_dry_end and i >= n_bars - 4:
            vol = base_volume * 0.4  # Volume dry-up

        records.append({
            "Open": open_p,
            "High": high,
            "Low": low,
            "Close": close_p,
            "Volume": vol,
        })

    df = pd.DataFrame(records)

    if breakout_last_bar:
        # Last bar shoots up with massive volume
        df.loc[n_bars - 1, "High"] = df["High"].max() * 1.03
        df.loc[n_bars - 1, "Close"] = df["High"].max() * 1.02
        df.loc[n_bars - 1, "Volume"] = base_volume * 2.5

    return df


# ==============================================================================
# 1. REGIME AGENT TESTS
# ==============================================================================
def test_regime_agent_uptrend():
    agent = RegimeAgent()
    # Continuous upward trend, no distribution days
    df = make_sample_ohlcv(n_bars=60, base_price=1200.0, trend_slope=0.003)
    result = agent.evaluate(df)

    assert result.status == RegimeStatus.UPTREND
    assert result.allow_new_buys is True
    assert result.distribution_days < 4
    assert result.recommended_cash_pct <= 20.0
    assert "ĐÈN XANH" in result.action_directive_vi


def test_regime_agent_downtrend_and_distribution_days():
    agent = RegimeAgent()
    # Downward trend with distribution days
    df = make_sample_ohlcv(n_bars=60, base_price=1250.0, trend_slope=-0.005, base_volume=500_000)

    # Inject 5 distribution days (drop > 0.2% with higher volume)
    for idx in range(45, 55, 2):
        df.loc[idx, "Close"] = df.loc[idx - 1, "Close"] * 0.985
        df.loc[idx, "Volume"] = df.loc[idx - 1, "Volume"] * 1.5

    result = agent.evaluate(df)
    assert result.status == RegimeStatus.DOWNTREND
    assert result.allow_new_buys is False
    assert result.distribution_days >= 4
    assert result.recommended_cash_pct >= 80.0
    assert "ĐÈN ĐỎ" in result.action_directive_vi


# ==============================================================================
# 2. SETUP AGENT TESTS
# ==============================================================================
def test_setup_agent_rejects_penny_and_low_liquidity():
    agent = SetupAgent(min_avg_volume_20d=300_000, min_price=10_000)

    # Penny stock test (< 10k VND)
    penny_df = make_sample_ohlcv(n_bars=60, base_price=5_000.0, base_volume=1_000_000)
    penny_res = agent.evaluate("PENNY.VN", penny_df)
    assert penny_res.status == SetupStatus.REJECTED_LIQUIDITY
    assert "10.000 đ" in penny_res.details_vi

    # Illiquid stock test (< 300k volume)
    illiquid_df = make_sample_ohlcv(n_bars=60, base_price=50_000.0, base_volume=50_000)
    illiquid_res = agent.evaluate("ILLIQ.VN", illiquid_df)
    assert illiquid_res.status == SetupStatus.REJECTED_LIQUIDITY
    assert "Thanh khoản thấp" in illiquid_res.details_vi


def test_setup_agent_detects_vcp_forming_and_breakout():
    agent = SetupAgent(min_avg_volume_20d=200_000, min_avg_value_20d_vnd=5_000_000_000)

    # 1. Forming VCP pattern with volume dry-up
    forming_df = make_sample_ohlcv(
        n_bars=60,
        base_price=30_000.0,
        trend_slope=0.001,
        base_volume=800_000,
        tighten_end=True,
        volume_dry_end=True,
        breakout_last_bar=False,
    )
    res_forming = agent.evaluate("HPG.VN", forming_df)
    assert res_forming.status in {SetupStatus.FORMING_WATCHLIST, SetupStatus.CONSOLIDATING}
    assert res_forming.is_vdu is True
    assert res_forming.tightness_pct < 6.0
    assert res_forming.risk_reward_ratio >= 2.0

    # 2. Breakout trigger with explosive volume
    breakout_df = make_sample_ohlcv(
        n_bars=60,
        base_price=30_000.0,
        trend_slope=0.001,
        base_volume=800_000,
        tighten_end=True,
        volume_dry_end=False,
        breakout_last_bar=True,
    )
    res_breakout = agent.evaluate("FPT.VN", breakout_df)
    assert res_breakout.status == SetupStatus.BREAKOUT_BUY
    assert res_breakout.score >= 80.0
    assert "BÙNG NỔ PIVOT" in res_breakout.details_vi


# ==============================================================================
# 3. RISK AGENT TESTS
# ==============================================================================
def test_risk_agent_position_sizing_lot_100():
    agent = RiskAgent(risk_per_trade_pct=0.015, max_allocation_pct=0.25)
    account_equity = 100_000_000.0  # 100M VND

    # Entry: 50,000; Stop loss: 47,500 (-5%); Target: 56,250 (+12.5%)
    # Max loss = 100M * 1.5% = 1.5M VND
    # Risk per share = 2,500 VND -> max shares by risk = 600 shares
    # Max capital = 25M VND -> max shares by capital = 500 shares
    # Min = 500 shares -> lot 100 -> 500 shares
    plan = agent.calculate_position(
        symbol="VNM.VN",
        entry_price=50_000.0,
        stop_loss_price=47_500.0,
        target_price=56_250.0,
        account_equity_vnd=account_equity,
    )

    assert plan.can_execute is True
    assert plan.shares == 500
    assert plan.shares % 100 == 0
    assert plan.total_cost_vnd == 25_000_000.0
    assert plan.max_loss_vnd <= 1_500_000.0


def test_risk_agent_t_plus_settlement_states():
    agent = RiskAgent()

    # Base Monday purchase
    buy_dt = datetime(2026, 9, 7, 10, 0)  # Monday 10:00

    # Same day Monday -> T+0 Locked
    now_t0 = datetime(2026, 9, 7, 14, 0)
    assert agent.evaluate_t_plus_status(buy_dt, now_t0) == TPlusStatus.T_0_LOCKED

    # Tuesday -> T+1 Locked
    now_t1 = datetime(2026, 9, 8, 10, 0)
    assert agent.evaluate_t_plus_status(buy_dt, now_t1) == TPlusStatus.T_1_LOCKED

    # Wednesday morning (before 13:00) -> T+2 Morning Locked
    now_t2_am = datetime(2026, 9, 9, 10, 30)
    assert agent.evaluate_t_plus_status(buy_dt, now_t2_am) == TPlusStatus.T_2_MORNING_LOCKED

    # Wednesday afternoon (after 13:00) -> T+2.5 Ready!
    now_t2_pm = datetime(2026, 9, 9, 13, 15)
    assert agent.evaluate_t_plus_status(buy_dt, now_t2_pm) == TPlusStatus.T_2_5_READY

    # Thursday onwards -> Available
    now_t3 = datetime(2026, 9, 10, 9, 30)
    assert agent.evaluate_t_plus_status(buy_dt, now_t3) == TPlusStatus.AVAILABLE_READY


def test_risk_agent_exit_signals():
    agent = RiskAgent()
    buy_dt = datetime(2026, 9, 7, 10, 0)
    pos = PortfolioPosition(
        symbol="MWG.VN",
        quantity=1000,
        avg_entry_price=50_000.0,
        buy_date=buy_dt,
        stop_loss_price=47_000.0,
        target_price=56_000.0,
        trailing_stop_price=0.0,
    )

    # Scenario 1: Stop-loss breached on Day T+1 (KẸT T+)
    t1_time = datetime(2026, 9, 8, 14, 0)
    signal_trapped = agent.evaluate_position_exit(pos, current_price=46_500.0, current_datetime=t1_time)
    assert signal_trapped.action == ExitAction.LOCKED_STOP_LOSS_TRAP
    assert signal_trapped.shares_to_sell == 0
    assert "CẢNH BÁO KẸT T+" in signal_trapped.message_vi

    # Scenario 2: Stop-loss breached on Day T+2 afternoon (HÀNG ĐÃ VỀ -> HARD STOP LOSS)
    t2_pm_time = datetime(2026, 9, 9, 13, 30)
    signal_exit = agent.evaluate_position_exit(pos, current_price=46_500.0, current_datetime=t2_pm_time)
    assert signal_exit.action == ExitAction.HARD_STOP_LOSS
    assert signal_exit.shares_to_sell == 1000
    assert "KÍCH HOẠT CẮT LỖ" in signal_exit.message_vi

    # Scenario 3: Target reached on Day T+3 -> TAKE PROFIT HALF
    t3_time = datetime(2026, 9, 10, 10, 0)
    signal_tp = agent.evaluate_position_exit(pos, current_price=57_000.0, current_datetime=t3_time)
    assert signal_tp.action == ExitAction.TAKE_PROFIT_HALF
    assert signal_tp.shares_to_sell == 500  # Half of 1000
