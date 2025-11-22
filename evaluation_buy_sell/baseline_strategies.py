import pandas as pd
import numpy as np
from abc import ABC, abstractmethod


class BaseStrategy(ABC):
    """Base class for trading strategies (long-only, action-based)."""

    def __init__(self, initial_capital=100000):
        self.initial_capital = float(initial_capital)
        self.name = self.__class__.__name__

    def _close_series(self, data: pd.DataFrame) -> pd.Series:
        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            if close.shape[1] == 1:
                close = close.iloc[:, 0]
            else:
                raise ValueError("Multiple 'Close' columns detected. Pass single-ticker data.")
        return pd.to_numeric(close, errors="coerce")

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate *actions* by date:
            1 = BUY (open / go long, or stay long)
            0 = HOLD (no change)
           -1 = SELL (exit to flat)
        Shorting is NOT allowed.
        """
        pass

    def _prep_ohlcv(self, data: pd.DataFrame) -> pd.DataFrame:
        req = ["Open", "High", "Low", "Close"]
        for col in req:
            if col not in data.columns:
                raise ValueError(f"Data missing column '{col}'")
        return data.copy()

    @staticmethod
    def _actions_to_position(actions: pd.Series) -> pd.Series:
        """Convert action series to a long-only position series in {0,1}."""
        a = actions.astype(float).fillna(0.0).clip(-1, 1).values
        pos = np.zeros_like(a, dtype=float)
        for i in range(len(a)):
            if i == 0:
                pos[i] = 1.0 if a[i] > 0 else 0.0
            else:
                if a[i] > 0:       # buy → long
                    pos[i] = 1.0
                elif a[i] < 0:     # sell → flat
                    pos[i] = 0.0
                else:              # hold → keep previous
                    pos[i] = pos[i-1]
        return pd.Series(pos, index=actions.index, name="position")

    def backtest(self, data: pd.DataFrame) -> pd.DataFrame:
        df = self._prep_ohlcv(data)

        # 1) get actions (1, 0, -1)
        actions = self.generate_signals(df).reindex(df.index).fillna(0).clip(-1, 1).astype(float)

        # 2) map actions → long-only position {0,1}
        position = self._actions_to_position(actions)

        # 3) compute returns (note: sell today → flat tomorrow → 0 return tomorrow)
        close = self._close_series(df)
        market_ret = close.pct_change().fillna(0.0)
        exposure = position.shift(1).fillna(0.0)   # use yesterday's position
        strat_ret = (exposure * market_ret).astype(float)

        cumret = (1.0 + strat_ret).cumprod()
        portval = self.initial_capital * cumret

        portfolio = pd.DataFrame(index=df.index)
        portfolio["action"] = actions                      # 1 buy / 0 hold / -1 sell
        portfolio["position"] = position                   # 1 long / 0 flat
        portfolio["close"] = close
        if "Volume" in df.columns:
            vol = df["Volume"]
            if isinstance(vol, pd.DataFrame) and vol.shape[1] == 1:
                vol = vol.iloc[:, 0]
            if isinstance(vol, pd.Series):
                portfolio["Volume"] = vol
        portfolio["market_return"] = market_ret
        portfolio["strategy_return"] = strat_ret
        portfolio["cumulative_return"] = cumret
        portfolio["portfolio_value"] = portval
        portfolio["trade_delta"] = portfolio["position"].diff().fillna(0.0)  # +1 buy, -1 sell
        return portfolio


class BuyAndHoldStrategy(BaseStrategy):
    """Buy on day 1 and hold long (no shorting)."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        a = pd.Series(0.0, index=data.index)
        if len(a) > 0:
            a.iloc[0] = 1.0  # buy once at start
        return a


class MACDStrategy(BaseStrategy):
    """MACD(12,26,9) Contrarian, long-only：MACD>signal → SELL(退出)，MACD<signal → BUY(做多)."""

    def generate_signals(self, data):
        df = data.copy()
        ema_fast = df["Close"].ewm(span=12, adjust=False).mean()
        ema_slow = df["Close"].ewm(span=26, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=9, adjust=False).mean()
        diff = macd - signal

        a = pd.Series(0.0, index=df.index)
        a[diff > 0] = -1.0   # 卖出/退出（之前是做空）
        a[diff < 0] = 1.0    # 买入/做多
        return a


class KDJRSIStrategy(BaseStrategy):
    """KDJ + RSI 逆势逻辑（长多-only）：超买 → 卖出；超卖 → 买入"""

    def generate_signals(self, data):
        df = data.copy()

        # === RSI ===
        delta = df["Close"].diff()
        up, down = delta.clip(lower=0), -delta.clip(upper=0)
        rs = up.ewm(span=14, adjust=False).mean() / down.ewm(span=14, adjust=False).mean().replace(0, np.nan)
        df["rsi"] = 100 - 100 / (1 + rs)

        # === KDJ ===
        low = df["Low"].rolling(9).min()
        high = df["High"].rolling(9).max()
        denom = (high - low).replace(0, np.nan)
        rsv = 100 * (df["Close"] - low) / denom
        k = rsv.ewm(com=2, adjust=False).mean()
        df["kdj_k"] = k

        # === Actions ===
        a = pd.Series(0.0, index=df.index)
        # 收紧阈值：RSI>75,K>85 → 卖出；RSI<25,K<15 → 买入
        a[(df["rsi"] > 75) & (df["kdj_k"] > 85)] = -1.0
        a[(df["rsi"] < 25) & (df["kdj_k"] < 15)] = 1.0
        return a


class ZMRStrategy(BaseStrategy):

    def generate_signals(self, data):
        close = self._close_series(data)
        mean = close.rolling(50).mean()
        std = close.rolling(50).std()
        z = (close - mean) / std.replace(0, np.nan)

        a = pd.Series(0.0, index=data.index)
        a[z > 1.3] = -1.0   # 高估 → 卖出/退出
        a[z < -1.3] = 1.0   # 低估 → 买入/做多
        return a


class SMAStrategy(BaseStrategy):

    def __init__(self, initial_capital=100000, short_window=5, long_window=20):
        super().__init__(initial_capital)
        self.short_window = int(short_window)
        self.long_window = int(long_window)

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = self._close_series(data)
        short = close.rolling(window=self.short_window, min_periods=self.short_window).mean()
        long_ = close.rolling(window=self.long_window, min_periods=self.long_window).mean()
        a = pd.Series(0.0, index=data.index)
        a[short > long_] = 1.0
        a[short < long_] = -1.0
        return a


def get_all_baseline_strategies(initial_capital=100000):
    """Get all baseline strategies for comparison (long-only, action-based)."""
    return {
        "BuyAndHold": BuyAndHoldStrategy(initial_capital),
        "MACD": MACDStrategy(initial_capital),
        "KDJ&RSI": KDJRSIStrategy(initial_capital),
        "ZMR": ZMRStrategy(initial_capital),
        "SMA": SMAStrategy(initial_capital),
    }
