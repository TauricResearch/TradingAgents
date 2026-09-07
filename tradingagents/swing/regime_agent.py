"""Regime Agent: Evaluates Vietnam market condition (VN-Index) for swing trading.

Traffic light mechanism:
- GREEN (UPTREND): VN-Index > SMA20, healthy distribution days count (< 4). Full buying allowed.
- YELLOW (UPTREND_UNDER_PRESSURE): 4-5 distribution days or testing SMA20. Tighten criteria, 50% position size.
- RED (DOWNTREND): VN-Index < SMA20 & SMA50, >= 5 distribution days. STRICT BAN on new buys, cash preservation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import pandas as pd


class RegimeStatus(str, Enum):
    UPTREND = "UPTREND"  # Đèn xanh: Thị trường thuận lợi
    UPTREND_UNDER_PRESSURE = "UPTREND_UNDER_PRESSURE"  # Đèn vàng: Áp lực bán gia tăng
    DOWNTREND = "DOWNTREND"  # Đèn đỏ: Thị trường gãy trend, cấm mua mới


@dataclass(frozen=True)
class MarketRegimeResult:
    status: RegimeStatus
    allow_new_buys: bool
    recommended_cash_pct: float
    current_close: float
    sma20: float
    sma50: float
    distribution_days: int
    summary_vi: str
    action_directive_vi: str


class RegimeAgent:
    """Agent monitoring VN-Index market trend and distribution days."""

    def __init__(
        self,
        distribution_lookback: int = 25,
        distribution_loss_threshold: float = -0.002,  # -0.2% drop with higher volume
    ) -> None:
        self.distribution_lookback = distribution_lookback
        self.distribution_loss_threshold = distribution_loss_threshold

    def count_distribution_days(self, df: pd.DataFrame) -> int:
        """Count distribution days in the last N sessions.

        A distribution day occurs when:
        1. Index Close is down by at least 0.2% compared to previous Close.
        2. Volume is greater than the previous day's Volume.
        """
        if len(df) < 2:
            return 0

        recent_df = df.tail(self.distribution_lookback + 1).copy()
        pct_change = recent_df["Close"].pct_change()
        vol_change = recent_df["Volume"].diff()

        # Condition: pct_change <= threshold AND vol_change > 0
        dist_mask = (pct_change <= self.distribution_loss_threshold) & (vol_change > 0)
        return int(dist_mask.sum())

    def evaluate(self, df: pd.DataFrame) -> MarketRegimeResult:
        """Evaluate the market regime from VN-Index historical OHLCV data."""
        if df.empty or len(df) < 20:
            return MarketRegimeResult(
                status=RegimeStatus.UPTREND_UNDER_PRESSURE,
                allow_new_buys=False,
                recommended_cash_pct=50.0,
                current_close=0.0,
                sma20=0.0,
                sma50=0.0,
                distribution_days=0,
                summary_vi="Không đủ dữ liệu lịch sử VN-Index để xác định xu hướng thị trường.",
                action_directive_vi="Thận trọng: Tạm ngừng mua mới cho đến khi đủ dữ liệu.",
            )

        df_calc = df.copy()
        df_calc["SMA20"] = df_calc["Close"].rolling(window=20).mean()
        df_calc["SMA50"] = df_calc["Close"].rolling(window=min(50, len(df_calc))).mean()

        latest_close = float(df_calc["Close"].iloc[-1])
        sma20 = float(df_calc["SMA20"].iloc[-1])
        sma50 = float(df_calc["SMA50"].iloc[-1])

        dist_days = self.count_distribution_days(df_calc)

        # Decision Matrix
        is_above_sma20 = latest_close >= sma20
        is_above_sma50 = latest_close >= sma50

        if is_above_sma20 and dist_days < 4:
            status = RegimeStatus.UPTREND
            allow_buys = True
            cash_pct = 10.0  # Giải ngân 90%
            summary = f"VN-Index ({latest_close:,.1f}) nằm trên MA20 ({sma20:,.1f}), số ngày phân phối thấp ({dist_days}/25)."
            action = "🟢 ĐÈN XANH: Thị trường Uptrend xác nhận. Cho phép Setup Agent quét và mở vị thế mua theo tỷ trọng chuẩn."

        elif is_above_sma20 and dist_days >= 4:
            status = RegimeStatus.UPTREND_UNDER_PRESSURE
            allow_buys = True
            cash_pct = 40.0  # Giữ ít nhất 40% tiền mặt
            summary = f"VN-Index ({latest_close:,.1f}) trên MA20 nhưng số ngày phân phối cao ({dist_days}/25)."
            action = "🟡 ĐÈN VÀNG: Xu hướng chịu áp lực bán. Chỉ giải ngân 50% khối lượng chuẩn cho các setup VCP xuất sắc nhất."

        elif not is_above_sma20 and (is_above_sma50 or dist_days < 5):
            status = RegimeStatus.UPTREND_UNDER_PRESSURE
            allow_buys = False
            cash_pct = 60.0
            summary = f"VN-Index ({latest_close:,.1f}) chớm gãy MA20 ({sma20:,.1f})."
            action = "🟡 ĐÈN VÀNG: Cảnh báo điều chỉnh. Tạm dừng mở vị thế mua mới, theo dõi giữ vị thế có sẵn."

        else:
            status = RegimeStatus.DOWNTREND
            allow_buys = False
            cash_pct = 90.0
            summary = f"VN-Index ({latest_close:,.1f}) gãy MA20 ({sma20:,.1f}) và MA50 ({sma50:,.1f}), tích lũy {dist_days} ngày phân phối."
            action = "🔴 ĐÈN ĐỎ: DOWNTREND XÁC NHẬN. CẤM MỞ VỊ THẾ MUA MỚI! Bảo toàn vốn, canh hạ tỷ trọng khi có nhịp hồi."

        return MarketRegimeResult(
            status=status,
            allow_new_buys=allow_buys,
            recommended_cash_pct=cash_pct,
            current_close=latest_close,
            sma20=sma20,
            sma50=sma50,
            distribution_days=dist_days,
            summary_vi=summary,
            action_directive_vi=action,
        )
