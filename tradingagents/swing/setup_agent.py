"""Setup Agent: Technical Stock Screener & Pattern Detector for Vietnam equities.

Specialized in:
1. Liquidity & Minimum Price Gate (Filters penny stocks and illiquid traps).
2. Trend Filter (Mark Minervini SEPA Trend Template).
3. VCP (Volatility Contraction Pattern) & Flat Base Detection.
4. Volume Dry-Up (VDU - Cạn kiệt nguồn cung trước khi bùng nổ).
5. Pivot Point & Breakout Trigger.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import numpy as np
import pandas as pd


class SetupStatus(str, Enum):
    BREAKOUT_BUY = "BREAKOUT_BUY"  # Đang bùng nổ vượt Pivot với Vol lớn
    FORMING_WATCHLIST = "FORMING_WATCHLIST"  # Co hẹp chặt chẽ (VCP) + Vol cạn kiệt, chờ nổ
    CONSOLIDATING = "CONSOLIDATING"  # Đang tích lũy nền, chưa đủ độ chặt
    NO_SETUP = "NO_SETUP"  # Không có mẫu hình hoặc gãy xu hướng
    REJECTED_LIQUIDITY = "REJECTED_LIQUIDITY"  # Thanh khoản thấp, nguy cơ kẹt sàn T+


@dataclass(frozen=True)
class SetupResult:
    symbol: str
    status: SetupStatus
    score: float  # Điểm chất lượng setup 0 - 100
    current_price: float
    pivot_price: float
    stop_loss_price: float
    target_price: float
    risk_pct: float  # % rủi ro từ điểm mua đến cắt lỗ
    reward_pct: float  # % lợi nhuận kỳ vọng
    risk_reward_ratio: float  # Tỷ lệ R:R (Target / Risk)
    avg_volume_20d: float
    avg_value_20d_vnd: float
    is_vdu: bool  # Volume Dry-Up (Vol cạn kiệt)
    tightness_pct: float  # Biên độ dao động 5 phiên gần nhất (%)
    details_vi: str


class SetupAgent:
    """Agent scanning stock universe for VCP and high-probability swing setups."""

    def __init__(
        self,
        min_avg_volume_20d: float = 300_000,  # Tối thiểu 300.000 cp/phiên
        min_avg_value_20d_vnd: float = 10_000_000_000,  # Tối thiểu 10 tỷ VNĐ/phiên
        min_price: float = 10_000.0,  # Tối thiểu 10.000 đ (loại penny trà đá)
        max_stop_loss_pct: float = 0.07,  # Cắt lỗ tối đa 7% (1 phiên sàn HOSE)
        target_rr_ratio: float = 2.5,  # R:R mục tiêu tối thiểu 2.5 : 1
    ) -> None:
        self.min_avg_volume_20d = min_avg_volume_20d
        self.min_avg_value_20d_vnd = min_avg_value_20d_vnd
        self.min_price = min_price
        self.max_stop_loss_pct = max_stop_loss_pct
        self.target_rr_ratio = target_rr_ratio

    def evaluate(self, symbol: str, df: pd.DataFrame) -> SetupResult:
        """Analyze a stock's historical OHLCV data to detect VCP and breakout setups."""
        clean_sym = symbol.strip().upper()

        # Minimum bar count requirement
        if df.empty or len(df) < 30:
            return self._empty_result(clean_sym, SetupStatus.NO_SETUP, "Không đủ dữ liệu lịch sử (cần tối thiểu 30 phiên).")

        df_calc = df.copy()
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in df_calc.columns:
                return self._empty_result(clean_sym, SetupStatus.NO_SETUP, f"Thiếu cột dữ liệu {col}.")

        # 1. LIQUIDITY & MINIMUM PRICE GATE
        latest_close = float(df_calc["Close"].iloc[-1])
        df_calc["Volume_SMA20"] = df_calc["Volume"].rolling(window=20).mean()
        avg_vol_20 = float(df_calc["Volume_SMA20"].iloc[-1])
        avg_val_20 = avg_vol_20 * latest_close

        if latest_close < self.min_price:
            return self._empty_result(
                clean_sym,
                SetupStatus.REJECTED_LIQUIDITY,
                f"Giá {latest_close:,.0f} đ < 10.000 đ (Penny trà đá, rủi ro cao).",
                current_price=latest_close,
                avg_vol=avg_vol_20,
                avg_val=avg_val_20,
            )

        if avg_vol_20 < self.min_avg_volume_20d or avg_val_20 < self.min_avg_value_20d_vnd:
            return self._empty_result(
                clean_sym,
                SetupStatus.REJECTED_LIQUIDITY,
                f"Thanh khoản thấp (KL TB: {avg_vol_20:,.0f} cp, GTGD: {avg_val_20/1e9:.1f} tỷ < {self.min_avg_value_20d_vnd/1e9:.0f} tỷ). Nguy cơ kẹt hàng T+!",
                current_price=latest_close,
                avg_vol=avg_vol_20,
                avg_val=avg_val_20,
            )

        # 2. TREND TEMPLATE (Minervini SEPA)
        df_calc["SMA20"] = df_calc["Close"].rolling(window=20).mean()
        df_calc["SMA50"] = df_calc["Close"].rolling(window=min(50, len(df_calc))).mean()

        sma20 = float(df_calc["SMA20"].iloc[-1])
        sma50 = float(df_calc["SMA50"].iloc[-1])
        high_60d = float(df_calc["High"].tail(60).max())

        # Condition: Price must not be lagging more than 25% from 60-day high
        pct_from_high = ((high_60d - latest_close) / high_60d) * 100
        in_uptrend_structure = (latest_close >= sma50 * 0.98) and (pct_from_high <= 25.0)

        if not in_uptrend_structure:
            return self._empty_result(
                clean_sym,
                SetupStatus.NO_SETUP,
                f"Không đạt tiêu chuẩn xu hướng (Giá cách đỉnh 60 phiên {pct_from_high:.1f}% hoặc dưới MA50).",
                current_price=latest_close,
                avg_vol=avg_vol_20,
                avg_val=avg_val_20,
            )

        # 3. VOLATILITY CONTRACTION PATTERN (VCP) & BASE TIGHTNESS
        # Analyze the last 5 sessions vs last 20 sessions
        recent_5 = df_calc.tail(5)
        high_5d = float(recent_5["High"].max())
        low_5d = float(recent_5["Low"].min())
        tightness_pct = ((high_5d - low_5d) / latest_close) * 100 if latest_close > 0 else 0.0

        # Calculate True Range contraction
        df_calc["TR"] = np.maximum(
            df_calc["High"] - df_calc["Low"],
            np.maximum(
                abs(df_calc["High"] - df_calc["Close"].shift(1)),
                abs(df_calc["Low"] - df_calc["Close"].shift(1)),
            ),
        )
        atr_5 = float(df_calc["TR"].tail(5).mean())
        atr_20 = float(df_calc["TR"].tail(20).mean())
        atr_ratio = (atr_5 / atr_20) if atr_20 > 0 else 1.0

        # 4. VOLUME DRY-UP (VDU)
        # Check if recent volume contracted significantly
        min_recent_vol = float(recent_5["Volume"].min())
        latest_vol = float(df_calc["Volume"].iloc[-1])
        is_vdu = (min_recent_vol <= avg_vol_20 * 0.70) or (latest_vol <= avg_vol_20 * 0.75)

        # 5. PIVOT POINT & STOP-LOSS DEFINITION
        # The pivot price is the resistance of the consolidation base (last 10-15 sessions)
        base_lookback = min(15, len(df_calc))
        base_df = df_calc.tail(base_lookback)
        pivot_price = float(base_df["High"].max())
        base_support = float(base_df["Low"].min())

        # Stop-loss calculation: below base support or fixed max 7%
        support_stop = base_support * 0.99  # 1% below base support
        fixed_max_stop = pivot_price * (1.0 - self.max_stop_loss_pct)
        stop_loss_price = max(support_stop, fixed_max_stop)

        risk_amount = pivot_price - stop_loss_price
        risk_pct = (risk_amount / pivot_price) * 100 if pivot_price > 0 else 5.0

        # Ensure realistic stop loss between 3% and 7%
        if risk_pct < 2.5:
            stop_loss_price = pivot_price * 0.97
            risk_pct = 3.0
            risk_amount = pivot_price - stop_loss_price

        target_amount = risk_amount * self.target_rr_ratio
        target_price = pivot_price + target_amount
        reward_pct = (target_amount / pivot_price) * 100
        rr_ratio = (target_price - pivot_price) / (pivot_price - stop_loss_price) if risk_amount > 0 else 0.0

        # 6. SETUP CLASSIFICATION & SCORING
        # Breakout condition: Latest price >= 99% of pivot with Volume >= 1.25x SMA20
        is_breakout = (latest_close >= pivot_price * 0.995) and (latest_vol >= avg_vol_20 * 1.25)
        # Forming condition: Price within 4% of pivot, tight base (tightness <= 7%), and VDU present
        is_forming = (latest_close >= pivot_price * 0.95) and (tightness_pct <= 7.5) and is_vdu

        # Scoring (0 - 100)
        score = 0.0
        # Component 1: Trend structure (25 pts)
        if latest_close >= sma20:
            score += 15.0
        if sma20 >= sma50:
            score += 10.0

        # Component 2: Tightness & Contraction (35 pts)
        if tightness_pct <= 4.0:
            score += 35.0
        elif tightness_pct <= 6.0:
            score += 25.0
        elif tightness_pct <= 8.0:
            score += 15.0

        # Component 3: Volume Dry-Up (25 pts)
        if is_vdu:
            score += 25.0
        elif min_recent_vol <= avg_vol_20 * 0.85:
            score += 15.0

        # Component 4: Volatility Ratio (15 pts)
        if atr_ratio <= 0.70:
            score += 15.0
        elif atr_ratio <= 0.85:
            score += 10.0

        if is_breakout:
            status = SetupStatus.BREAKOUT_BUY
            score = max(score, 85.0)
            details = (
                f"🚀 BÙNG NỔ PIVOT: Giá ({latest_close:,.0f} đ) vượt cản {pivot_price:,.0f} đ "
                f"với KL ({latest_vol:,.0f}) gấp {latest_vol/avg_vol_20:.1f}x MA20. "
                f"Cắt lỗ: {stop_loss_price:,.0f} đ (-{risk_pct:.1f}%), Target: {target_price:,.0f} đ (+{reward_pct:.1f}%)."
            )
        elif is_forming:
            status = SetupStatus.FORMING_WATCHLIST
            details = (
                f"🔍 NỀN VCP THU HẸP: Biên độ 5 phiên chặt ({tightness_pct:.1f}%), "
                f"Khối lượng cạn kiệt (VDU). Đang áp sát Pivot {pivot_price:,.0f} đ (cách {((pivot_price-latest_close)/pivot_price)*100:.1f}%). "
                f"Sẵn sàng nổ breakout."
            )
        elif tightness_pct <= 10.0:
            status = SetupStatus.CONSOLIDATING
            details = (
                f"⚖️ Đang tích lũy nền giá (Biên độ 5 phiên {tightness_pct:.1f}%). "
                f"Cần thêm phiên cạn kiệt thanh khoản hoặc siết chặt biên độ < 6%."
            )
        else:
            status = SetupStatus.NO_SETUP
            details = f"Biên độ dao động còn lỏng lẻo ({tightness_pct:.1f}% > 10%), chưa có mẫu hình VCP đạt chuẩn."

        return SetupResult(
            symbol=clean_sym,
            status=status,
            score=round(score, 1),
            current_price=latest_close,
            pivot_price=round(pivot_price, -1),
            stop_loss_price=round(stop_loss_price, -1),
            target_price=round(target_price, -1),
            risk_pct=round(risk_pct, 2),
            reward_pct=round(reward_pct, 2),
            risk_reward_ratio=round(rr_ratio, 2),
            avg_volume_20d=round(avg_vol_20, 0),
            avg_value_20d_vnd=round(avg_val_20, 0),
            is_vdu=is_vdu,
            tightness_pct=round(tightness_pct, 2),
            details_vi=details,
        )

    def _empty_result(
        self,
        symbol: str,
        status: SetupStatus,
        details: str,
        current_price: float = 0.0,
        avg_vol: float = 0.0,
        avg_val: float = 0.0,
    ) -> SetupResult:
        return SetupResult(
            symbol=symbol,
            status=status,
            score=0.0,
            current_price=current_price,
            pivot_price=0.0,
            stop_loss_price=0.0,
            target_price=0.0,
            risk_pct=0.0,
            reward_pct=0.0,
            risk_reward_ratio=0.0,
            avg_volume_20d=avg_vol,
            avg_value_20d_vnd=avg_val,
            is_vdu=False,
            tightness_pct=0.0,
            details_vi=details,
        )
