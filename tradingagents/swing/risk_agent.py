"""Risk Agent: Position sizing, T+2.5 settlement cycle tracking, and exit execution.

Enforces:
1. 100-share lot allocation (HOSE/HNX statutory rules).
2. Risk-based position sizing (default 1.5% portfolio risk per trade, max 25% NAV per stock).
3. T+2.5 settlement cycle tracking (determines when shares can legally be sold).
4. Hard stop-loss and profit-taking trailing stop triggers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any

from tradingagents.dataflows.vn_data import calculate_vn_trade_friction, normalize_vn_symbol


class TPlusStatus(str, Enum):
    T_0_LOCKED = "T_0_LOCKED"  # Mua hôm nay (T+0), chưa về
    T_1_LOCKED = "T_1_LOCKED"  # Đang chờ (T+1), chưa về
    T_2_MORNING_LOCKED = "T_2_MORNING_LOCKED"  # Sáng T+2 (chờ 13h00)
    T_2_5_READY = "T_2_5_READY"  # Chiều T+2 (đã về, được phép bán)
    AVAILABLE_READY = "AVAILABLE_READY"  # Đã về từ trước (T+3 trở đi)


class ExitAction(str, Enum):
    HOLD = "HOLD"  # Tiếp tục nắm giữ
    HARD_STOP_LOSS = "HARD_STOP_LOSS"  # Cắt lỗ khẩn cấp (hàng đã khả dụng)
    LOCKED_STOP_LOSS_TRAP = "LOCKED_STOP_LOSS_TRAP"  # BÁO ĐỘNG KẸT T+: Lỗ nhưng hàng chưa về!
    TAKE_PROFIT_HALF = "TAKE_PROFIT_HALF"  # Chốt lời 50%, dời stop-loss về hòa vốn
    TRAILING_STOP = "TRAILING_STOP"  # Kích hoạt trailing stop bảo vệ lợi nhuận


@dataclass(frozen=True)
class PositionPlan:
    symbol: str
    entry_price: float
    stop_loss_price: float
    target_price: float
    shares: int  # Đã làm tròn lô 100
    total_cost_vnd: float
    max_loss_vnd: float
    expected_profit_vnd: float
    allocation_pct: float
    portfolio_risk_pct: float
    can_execute: bool
    reason_vi: str


@dataclass(frozen=True)
class PortfolioPosition:
    symbol: str
    quantity: int
    avg_entry_price: float
    buy_date: datetime
    stop_loss_price: float
    target_price: float
    trailing_stop_price: float


@dataclass(frozen=True)
class ExitSignal:
    symbol: str
    action: ExitAction
    current_price: float
    gain_pct: float
    t_status: TPlusStatus
    shares_to_sell: int
    net_pnl_vnd: float
    message_vi: str


class RiskAgent:
    """Agent managing capital sizing and T+2.5 life-cycle for Vietnamese swing trading."""

    def __init__(
        self,
        risk_per_trade_pct: float = 0.015,  # Mất tối đa 1.5% NAV nếu chạm stop-loss
        max_allocation_pct: float = 0.25,   # Tối đa 25% NAV cho một cổ phiếu (danh mục 4-5 mã)
    ) -> None:
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_allocation_pct = max_allocation_pct

    def calculate_position(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        target_price: float,
        account_equity_vnd: float,
    ) -> PositionPlan:
        """Calculate exact share lot size conforming to 100-share constraints and risk budgets."""
        clean_sym = normalize_vn_symbol(symbol)

        if account_equity_vnd <= 0:
            return PositionPlan(
                clean_sym, entry_price, stop_loss_price, target_price, 0, 0.0, 0.0, 0.0, 0.0, 0.0, False,
                "Tổng tài sản tài khoản không hợp lệ (<= 0).",
            )

        if stop_loss_price >= entry_price:
            return PositionPlan(
                clean_sym, entry_price, stop_loss_price, target_price, 0, 0.0, 0.0, 0.0, 0.0, 0.0, False,
                "Giá cắt lỗ phải thấp hơn giá mua vào.",
            )

        # 1. Size by risk budget
        max_loss_budget = account_equity_vnd * self.risk_per_trade_pct
        risk_per_share = entry_price - stop_loss_price
        shares_by_risk = max_loss_budget / risk_per_share if risk_per_share > 0 else 0

        # 2. Size by capital allocation ceiling
        max_capital = account_equity_vnd * self.max_allocation_pct
        shares_by_capital = max_capital / entry_price if entry_price > 0 else 0

        # 3. Choose the conservative size and enforce 100-share lot
        raw_shares = min(shares_by_risk, shares_by_capital)
        lot_shares = int(raw_shares // 100) * 100

        if lot_shares < 100:
            return PositionPlan(
                clean_sym, entry_price, stop_loss_price, target_price, 0, 0.0, 0.0, 0.0, 0.0, 0.0, False,
                f"Vốn không đủ để mở tối thiểu 1 lô 100 cổ phiếu (Cần tối thiểu {entry_price * 100:,.0f} đ).",
            )

        total_cost = lot_shares * entry_price
        actual_max_loss = lot_shares * risk_per_share
        expected_profit = lot_shares * (target_price - entry_price)
        allocation_pct = (total_cost / account_equity_vnd) * 100
        portfolio_risk_pct = (actual_max_loss / account_equity_vnd) * 100

        return PositionPlan(
            symbol=clean_sym,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            target_price=target_price,
            shares=lot_shares,
            total_cost_vnd=total_cost,
            max_loss_vnd=actual_max_loss,
            expected_profit_vnd=expected_profit,
            allocation_pct=round(allocation_pct, 1),
            portfolio_risk_pct=round(portfolio_risk_pct, 2),
            can_execute=True,
            reason_vi=(
                f"Khuyến nghị mua {lot_shares:,} cp {clean_sym} giá {entry_price:,.0f} đ. "
                f"Tổng vốn: {total_cost:,.0f} đ ({allocation_pct:.1f}% NAV). "
                f"Rủi ro tối đa: {actual_max_loss:,.0f} đ ({portfolio_risk_pct:.2f}% NAV)."
            ),
        )

    def count_trading_days(self, start_dt: datetime, current_dt: datetime) -> int:
        """Count completed trading days (excluding weekends) between two dates."""
        d1 = start_dt.date() if isinstance(start_dt, datetime) else start_dt
        d2 = current_dt.date() if isinstance(current_dt, datetime) else current_dt

        if d2 <= d1:
            return 0

        trading_days = 0
        cur = d1
        one_day = datetime(2000, 1, 2) - datetime(2000, 1, 1)

        while cur < d2:
            cur = date.fromordinal(cur.toordinal() + 1)
            # Monday is 0, Sunday is 6
            if cur.weekday() < 5:
                trading_days += 1

        return trading_days

    def evaluate_t_plus_status(self, buy_datetime: datetime, current_datetime: datetime | None = None) -> TPlusStatus:
        """Evaluate T+2.5 settlement status according to Vietnamese securities rules."""
        now = current_datetime or datetime.now()
        trading_days = self.count_trading_days(buy_datetime, now)

        if trading_days == 0:
            return TPlusStatus.T_0_LOCKED
        elif trading_days == 1:
            return TPlusStatus.T_1_LOCKED
        elif trading_days == 2:
            # Under T+2.5, shares become available at 13:00 (afternoon session) of Day T+2
            if now.time() < time(13, 0):
                return TPlusStatus.T_2_MORNING_LOCKED
            return TPlusStatus.T_2_5_READY
        else:
            return TPlusStatus.AVAILABLE_READY

    def evaluate_position_exit(
        self,
        position: PortfolioPosition,
        current_price: float,
        current_datetime: datetime | None = None,
    ) -> ExitSignal:
        """Determine whether to hold, stop-loss, or take-profit on an active position."""
        now = current_datetime or datetime.now()
        t_status = self.evaluate_t_plus_status(position.buy_date, now)
        is_sellable = t_status in {TPlusStatus.T_2_5_READY, TPlusStatus.AVAILABLE_READY}

        friction = calculate_vn_trade_friction(
            entry_price=position.avg_entry_price,
            exit_price=current_price,
            shares=position.quantity,
        )
        gain_pct = friction["net_roi_percent"]
        net_pnl = friction["net_profit"]

        # 1. HARD STOP LOSS CHECK
        effective_stop = max(position.stop_loss_price, position.trailing_stop_price)
        if current_price <= effective_stop:
            if not is_sellable:
                return ExitSignal(
                    symbol=position.symbol,
                    action=ExitAction.LOCKED_STOP_LOSS_TRAP,
                    current_price=current_price,
                    gain_pct=gain_pct,
                    t_status=t_status,
                    shares_to_sell=0,
                    net_pnl_vnd=net_pnl,
                    message_vi=(
                        f"🚨 CẢNH BÁO KẸT T+: Giá {current_price:,.0f} đ đã xuyên thủng cắt lỗ {effective_stop:,.0f} đ, "
                        f"nhưng cổ phiếu đang ở trạng thái {t_status.value} (chưa khả dụng). "
                        f"Kế hoạch: Chuẩn bị lệnh BÁN NGAY vào lúc 13h00 phiên T+2."
                    ),
                )
            else:
                return ExitSignal(
                    symbol=position.symbol,
                    action=ExitAction.HARD_STOP_LOSS,
                    current_price=current_price,
                    gain_pct=gain_pct,
                    t_status=t_status,
                    shares_to_sell=position.quantity,
                    net_pnl_vnd=net_pnl,
                    message_vi=(
                        f"🛑 KÍCH HOẠT CẮT LỖ: Giá ({current_price:,.0f} đ) chạm ngưỡng cắt lỗ {effective_stop:,.0f} đ. "
                        f"Hàng đã khả dụng. Khớp bán toàn bộ {position.quantity:,} cp. Lỗ ròng: {net_pnl:+,.0f} đ ({gain_pct:+.2f}%)."
                    ),
                )

        # 2. TAKE PROFIT CHECK (Target reached)
        if current_price >= position.target_price and is_sellable:
            half_qty = int((position.quantity // 2) // 100) * 100
            if half_qty == 0:
                half_qty = position.quantity

            return ExitSignal(
                symbol=position.symbol,
                action=ExitAction.TAKE_PROFIT_HALF,
                current_price=current_price,
                gain_pct=gain_pct,
                t_status=t_status,
                shares_to_sell=half_qty,
                net_pnl_vnd=net_pnl,
                message_vi=(
                    f"🎯 ĐẠT MỤC TIÊU LỢI NHUẬN: Giá ({current_price:,.0f} đ) đạt target {position.target_price:,.0f} đ "
                    f"({gain_pct:+.2f}%). Khuyến nghị chốt lời 50% ({half_qty:,} cp), dời stop-loss phần còn lại về giá vốn."
                ),
            )

        # 3. TRAILING STOP TRIGGER (If gained >= 7% -> raise stop to breakeven)
        breakeven_gain = friction["breakeven_gain_percent"]
        if gain_pct >= 7.0 and position.trailing_stop_price < position.avg_entry_price:
            return ExitSignal(
                symbol=position.symbol,
                action=ExitAction.TRAILING_STOP,
                current_price=current_price,
                gain_pct=gain_pct,
                t_status=t_status,
                shares_to_sell=0,
                net_pnl_vnd=net_pnl,
                message_vi=(
                    f"📈 NÂNG TRAILING STOP: Cổ phiếu tăng +{gain_pct:.2f}% (vượt ngưỡng an toàn 7%). "
                    f"Nâng ngưỡng dừng lỗ lên mức hòa vốn {position.avg_entry_price:,.0f} đ (bảo vệ tuyệt đối lợi nhuận)."
                ),
            )

        return ExitSignal(
            symbol=position.symbol,
            action=ExitAction.HOLD,
            current_price=current_price,
            gain_pct=gain_pct,
            t_status=t_status,
            shares_to_sell=0,
            net_pnl_vnd=net_pnl,
            message_vi=f"Tiếp tục nắm giữ. Lãi/Lỗ hiện tại: {gain_pct:+.2f}% ({net_pnl:+,.0f} đ). Trạng thái: {t_status.value}.",
        )
