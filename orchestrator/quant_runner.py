import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from typing import Any

import yfinance as yf

from orchestrator.config import OrchestratorConfig
from orchestrator.signals import Signal

logger = logging.getLogger(__name__)


class QuantRunner:
    def __init__(self, config: OrchestratorConfig):
        if not config.quant_backtest_path:
            raise ValueError("OrchestratorConfig.quant_backtest_path must be set")
        self._config = config
        path = config.quant_backtest_path
        if path not in sys.path:
            sys.path.insert(0, path)
        self._db_path = f"{path}/research_results/runs.db"

    def get_signal(self, ticker: str, date: str) -> Signal:
        """
        获取指定股票在指定日期的量化信号。
        date 格式：'YYYY-MM-DD'
        返回 Signal(source="quant")
        """
        result = self._load_best_params()
        params: dict = result["params"]
        sharpe: float = result["sharpe_ratio"]

        # 获取 date 前 60 天的历史数据
        end_dt = datetime.strptime(date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=60)
        start_str = start_dt.strftime("%Y-%m-%d")

        df = yf.download(ticker, start=start_str, end=date, progress=False, auto_adjust=True)
        if df.empty:
            logger.warning("No price data for %s between %s and %s", ticker, start_str, date)
            return Signal(
                ticker=ticker,
                direction=0,
                confidence=0.0,
                source="quant",
                timestamp=datetime.now(timezone.utc),
                metadata={"reason": "no_data"},
            )

        # 标准化列名为小写
        df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]

        # 用最佳参数创建 BollingerStrategy 实例
        # Lazy import: requires quant_backtest_path to be in sys.path (set in __init__)
        from strategies.momentum import BollingerStrategy
        from core.data_models import Bar, OrderDirection

        strategy = BollingerStrategy(
            period=params.get("period", 20),
            num_std=params.get("num_std", 2.0),
            position_pct=params.get("position_pct", 0.20),
            stop_loss_pct=params.get("stop_loss_pct", 0.05),
            take_profit_pct=params.get("take_profit_pct", 0.15),
        )

        # 逐 bar 喂给策略，模拟历史回放
        direction = 0
        orders: list = []
        context: dict[str, Any] = {"positions": {}}

        for ts, row in df.iterrows():
            bar = Bar(
                symbol=ticker,
                timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0)),
            )
            orders = strategy.on_bar(bar, context)
            # 更新模拟持仓
            for order in orders:
                if order.direction == OrderDirection.BUY:
                    context["positions"][ticker] = order.volume
                elif order.direction == OrderDirection.SELL:
                    context["positions"][ticker] = 0

        # 最后一个 bar 的信号
        last_orders = orders if df.shape[0] > 0 else []
        for order in last_orders:
            if order.direction == OrderDirection.BUY:
                direction = 1
                break
            elif order.direction == OrderDirection.SELL:
                direction = -1
                break

        # 计算 max_sharpe（从 DB 中取全局最大值）
        try:
            with sqlite3.connect(self._db_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT MAX(sharpe_ratio) FROM backtest_results")
                row = cur.fetchone()
                max_sharpe = float(row[0]) if row and row[0] is not None else sharpe
        except Exception:
            max_sharpe = sharpe

        confidence = self._calc_confidence(sharpe, max_sharpe)

        return Signal(
            ticker=ticker,
            direction=direction,
            confidence=confidence,
            source="quant",
            timestamp=datetime.now(timezone.utc),
            metadata={"params": params, "sharpe_ratio": sharpe, "max_sharpe": max_sharpe},
        )

    def _load_best_params(self) -> dict:
        """
        直接查 SQLite 获取 BollingerStrategy 最佳参数。
        参数是全局最优，不区分股票（backtest_results 表无 ticker 列，优化是全局的）。
        strategy_type 支持 'BollingerStrategy' 和 'bollinger'（兼容两种写法）。
        """
        with sqlite3.connect(self._db_path) as conn:
            cur = conn.cursor()
            # 先按规格查 'BollingerStrategy'，再 fallback 到 'bollinger'
            cur.execute(
                """
                SELECT params, sharpe_ratio
                FROM backtest_results
                WHERE strategy_type IN ('BollingerStrategy', 'bollinger')
                ORDER BY sharpe_ratio DESC
                LIMIT 1
                """,
            )
            row = cur.fetchone()

        if row is None:
            raise ValueError(
                "No BollingerStrategy results found in ResultStore. "
                "Run optimization first: python quant_backtest/run_research.py"
            )

        params = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        return {"params": params, "sharpe_ratio": float(row[1])}

    def _calc_confidence(self, sharpe: float, max_sharpe: float) -> float:
        """
        Sharpe 归一化为置信度。
        - max_sharpe=0 时返回 0.5（默认值，避免除零）
        - sharpe/max_sharpe 上限截断到 1.0
        - 下限截断到 0.0（负 Sharpe 不产生负置信度）
        """
        if max_sharpe == 0:
            return 0.5
        ratio = sharpe / max_sharpe
        return max(0.0, min(1.0, ratio))
