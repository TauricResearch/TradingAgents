"""VectorBT harness with pandas fallback (no hard dep)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import vectorbt as vbt  # type: ignore

    _HAS_VECTORBT = True
except ImportError:  # pragma: no cover
    vbt = None  # type: ignore
    _HAS_VECTORBT = False


@dataclass
class BacktestResult:
    total_return: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    num_trades: int
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    method: str = "unknown"
    net_sharpe: float = 0.0


class VectorBTBacktest:
    """Backtest harness; integration point for portfolio_manager validation."""

    def __init__(self, fees: float = 0.001, cost_model=None) -> None:
        # cost_model: CostModel optional — when provided fees derived from cost_model
        if cost_model is not None:
            try:
                fees = cost_model.total_rate()
            except Exception:
                pass
            self.cost_model = cost_model
        else:
            self.cost_model = None
        self.fees = fees
        if not _HAS_VECTORBT:
            logger.warning("vectorbt not installed — pandas fallback")

    def run(self, price: pd.DataFrame | pd.Series, entries: pd.Series, exits: pd.Series, fees: Optional[float] = None, cost_model=None) -> BacktestResult:
        # cost_model overrides fees when provided
        if cost_model is not None:
            try:
                fees = cost_model.total_rate()
            except Exception:
                pass
        elif self.cost_model is not None and fees is None:
            fees = self.cost_model.total_rate()
        fee = self.fees if fees is None else fees
        close = self._to_series(price)
        entries = entries.reindex(close.index).fillna(False).astype(bool)
        exits = exits.reindex(close.index).fillna(False).astype(bool)
        if _HAS_VECTORBT:
            try:
                return self._run_vectorbt(close, entries, exits, fee)
            except Exception as exc:  # pragma: no cover
                logger.warning("vectorbt run failed (%s) — fallback", exc)
        return self._run_fallback(close, entries, exits, fee)

    def run_grid_search(self, price: pd.DataFrame | pd.Series, fast_windows: List[int], slow_windows: List[int], fees: Optional[float] = None) -> Tuple[pd.DataFrame, Dict]:
        """SMA crossover grid: entry when fast crosses above slow."""
        fee = self.fees if fees is None else fees
        close = self._to_series(price)
        rows: List[Dict] = []
        for fast in fast_windows:
            for slow in slow_windows:
                if fast >= slow:
                    continue
                fast_sma = close.rolling(fast, min_periods=fast).mean()
                slow_sma = close.rolling(slow, min_periods=slow).mean()
                entries = (fast_sma > slow_sma) & (fast_sma.shift(1) <= slow_sma.shift(1))
                exits = (fast_sma < slow_sma) & (fast_sma.shift(1) >= slow_sma.shift(1))
                r = self.run(close, entries.fillna(False), exits.fillna(False), fees=fee)
                rows.append({"fast": fast, "slow": slow, "total_return": r.total_return, "sharpe": r.sharpe, "max_drawdown": r.max_drawdown, "win_rate": r.win_rate, "num_trades": r.num_trades})
        if not rows:
            return pd.DataFrame(), {}
        df = pd.DataFrame(rows).sort_values("sharpe", ascending=False).reset_index(drop=True)
        return df, df.iloc[0].to_dict()

    @staticmethod
    def _to_series(price: pd.DataFrame | pd.Series) -> pd.Series:
        if isinstance(price, pd.DataFrame):
            s = price["Close"] if "Close" in price.columns else price.iloc[:, 0]
            return pd.Series(s).dropna()
        return pd.Series(price).dropna()

    @staticmethod
    def _run_vectorbt(close: pd.Series, entries: pd.Series, exits: pd.Series, fees: float) -> BacktestResult:
        # fees includes fee+slippage+fx_spread (one-way) when cost_model used
        pf = vbt.Portfolio.from_signals(close, entries, exits, fees=fees, freq="1D")  # type: ignore
        total_return = float(pf.total_return())
        sharpe = float(pf.sharpe_ratio()) if len(close) > 1 else 0.0
        max_dd = abs(float(pf.max_drawdown()))
        try:
            win_rate = float(pf.trades.win_rate()) if pf.trades.count() > 0 else 0.0
            num_trades = int(pf.trades.count())
        except Exception:
            win_rate, num_trades = 0.0, 0
        equity = pd.Series(pf.value(), index=close.index)
        # net_sharpe after costs: same as sharpe when fees incorporates costs
        net_sharpe = sharpe if np.isfinite(sharpe) else 0.0
        return BacktestResult(total_return=total_return, sharpe=sharpe if np.isfinite(sharpe) else 0.0, max_drawdown=max_dd, win_rate=win_rate, num_trades=num_trades, equity_curve=equity, method="vectorbt", net_sharpe=net_sharpe)

    @staticmethod
    def _run_fallback(close: pd.Series, entries: pd.Series, exits: pd.Series, fees: float) -> BacktestResult:
        # entry/exit price adjusted by fees+slippage+fx_spread (one-way)
        n = len(close)
        pos, entry_price, equity, rets, pnls = 0, 0.0, [1.0], [], []
        for i in range(1, n):
            prev, now = float(close.iloc[i - 1]), float(close.iloc[i])
            if entries.iloc[i] and pos == 0:
                pos, entry_price = 1, now * (1 + fees)
            elif exits.iloc[i] and pos == 1:
                pnls.append((now * (1 - fees) - entry_price) / entry_price)
                pos, entry_price = 0, 0.0
            ret = (now - prev) / prev if pos == 1 and prev else 0.0
            rets.append(ret)
            equity.append(equity[-1] * (1 + ret))
        equity_s = pd.Series(equity, index=close.index)
        arr = np.array(rets, dtype=float)
        sharpe = (float(np.mean(arr)) / float(np.std(arr)) * np.sqrt(252)) if len(arr) > 1 and float(np.std(arr)) > 1e-12 else 0.0
        max_dd = float(abs((equity_s - equity_s.cummax()).div(equity_s.cummax()).min())) if len(equity_s) else 0.0
        total_return = float(equity_s.iloc[-1] - 1.0) if len(equity_s) else 0.0
        win_rate = float(np.mean([1 if x > 0 else 0 for x in pnls])) if pnls else 0.0
        net_sharpe = sharpe if np.isfinite(sharpe) else 0.0
        return BacktestResult(total_return=total_return, sharpe=sharpe if np.isfinite(sharpe) else 0.0, max_drawdown=max_dd, win_rate=win_rate, num_trades=len(pnls), equity_curve=equity_s, method="fallback", net_sharpe=net_sharpe)
