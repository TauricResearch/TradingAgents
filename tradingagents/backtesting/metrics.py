import math
from decimal import Decimal
from typing import Optional

from tradingagents.models.backtest import BacktestMetrics, EquityCurvePoint, TradeLog


class MetricsCalculator:
    TRADING_DAYS_PER_YEAR = 252

    def __init__(self, risk_free_rate: Decimal = Decimal("0.05")):
        self.risk_free_rate = risk_free_rate

    def calculate_metrics(
        self,
        equity_curve: list[EquityCurvePoint],
        trade_log: TradeLog,
        benchmark_curve: Optional[list[EquityCurvePoint]] = None,
    ) -> BacktestMetrics:
        if not equity_curve:
            raise ValueError("Equity curve cannot be empty")

        start_equity = equity_curve[0].equity
        end_equity = equity_curve[-1].equity
        trading_days = len(equity_curve)

        total_return = end_equity - start_equity
        total_return_percent = (total_return / start_equity) * 100

        years = Decimal(trading_days) / Decimal(self.TRADING_DAYS_PER_YEAR)
        if years > 0:
            annualized_return = ((end_equity / start_equity) ** (1 / years) - 1) * 100
        else:
            annualized_return = Decimal("0")

        daily_returns = self._calculate_daily_returns(equity_curve)
        volatility = self._calculate_volatility(daily_returns)
        annualized_volatility = volatility * Decimal(math.sqrt(self.TRADING_DAYS_PER_YEAR))

        downside_returns = [r for r in daily_returns if r < 0]
        downside_volatility = self._calculate_volatility(downside_returns) if downside_returns else Decimal("0")
        annualized_downside_vol = downside_volatility * Decimal(math.sqrt(self.TRADING_DAYS_PER_YEAR))

        max_dd, max_dd_pct, max_dd_duration, avg_dd = self._calculate_drawdown_metrics(equity_curve)

        sharpe = self._calculate_sharpe_ratio(annualized_return, annualized_volatility)
        sortino = self._calculate_sortino_ratio(annualized_return, annualized_downside_vol)
        calmar = self._calculate_calmar_ratio(annualized_return, max_dd_pct)

        benchmark_return = None
        benchmark_return_percent = None
        alpha = None
        beta = None
        information_ratio = None

        if benchmark_curve and len(benchmark_curve) == len(equity_curve):
            benchmark_return = benchmark_curve[-1].equity - benchmark_curve[0].equity
            benchmark_return_percent = (benchmark_return / benchmark_curve[0].equity) * 100

            benchmark_daily = self._calculate_daily_returns(benchmark_curve)
            alpha, beta = self._calculate_alpha_beta(daily_returns, benchmark_daily)
            information_ratio = self._calculate_information_ratio(
                daily_returns, benchmark_daily
            )

        all_pnls = [t.pnl for t in trade_log.trades if t.is_closed and t.pnl is not None]
        avg_trade_pnl = sum(all_pnls) / len(all_pnls) if all_pnls else None
        largest_win = max((p for p in all_pnls if p > 0), default=None)
        largest_loss = min((p for p in all_pnls if p < 0), default=None)

        return BacktestMetrics(
            total_return=total_return,
            total_return_percent=total_return_percent,
            annualized_return=annualized_return,
            benchmark_return=benchmark_return,
            benchmark_return_percent=benchmark_return_percent,
            alpha=alpha,
            beta=beta,
            volatility=volatility * 100,
            annualized_volatility=annualized_volatility * 100,
            downside_volatility=annualized_downside_vol * 100,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            information_ratio=information_ratio,
            max_drawdown=max_dd,
            max_drawdown_percent=max_dd_pct,
            max_drawdown_duration=max_dd_duration,
            avg_drawdown=avg_dd,
            total_trades=trade_log.total_trades,
            win_rate=trade_log.win_rate,
            profit_factor=trade_log.profit_factor,
            avg_trade_pnl=avg_trade_pnl,
            avg_win=trade_log.avg_win,
            avg_loss=trade_log.avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_holding_period_days=trade_log.avg_holding_period,
            trading_days=trading_days,
            start_equity=start_equity,
            end_equity=end_equity,
        )

    def _calculate_daily_returns(
        self,
        equity_curve: list[EquityCurvePoint],
    ) -> list[Decimal]:
        returns = []
        for i in range(1, len(equity_curve)):
            prev_equity = equity_curve[i - 1].equity
            curr_equity = equity_curve[i].equity
            if prev_equity > 0:
                daily_return = (curr_equity - prev_equity) / prev_equity
                returns.append(daily_return)
        return returns

    def _calculate_volatility(self, returns: list[Decimal]) -> Decimal:
        if len(returns) < 2:
            return Decimal("0")

        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        return Decimal(str(math.sqrt(float(variance))))

    def _calculate_drawdown_metrics(
        self,
        equity_curve: list[EquityCurvePoint],
    ) -> tuple[Decimal, Decimal, Optional[int], Decimal]:
        if not equity_curve:
            return Decimal("0"), Decimal("0"), None, Decimal("0")

        peak = equity_curve[0].equity
        max_drawdown = Decimal("0")
        max_drawdown_percent = Decimal("0")
        drawdown_start = 0
        max_drawdown_duration = 0
        current_drawdown_start = 0
        in_drawdown = False
        drawdowns = []

        for i, point in enumerate(equity_curve):
            equity = point.equity

            if equity > peak:
                if in_drawdown:
                    duration = i - current_drawdown_start
                    max_drawdown_duration = max(max_drawdown_duration, duration)
                    in_drawdown = False
                peak = equity
                current_drawdown_start = i
            else:
                if not in_drawdown:
                    in_drawdown = True
                    current_drawdown_start = i

                drawdown = peak - equity
                drawdown_pct = (drawdown / peak) * 100 if peak > 0 else Decimal("0")
                drawdowns.append(drawdown_pct)

                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                    max_drawdown_percent = drawdown_pct

                point.drawdown = drawdown
                point.drawdown_percent = drawdown_pct

        if in_drawdown:
            duration = len(equity_curve) - current_drawdown_start
            max_drawdown_duration = max(max_drawdown_duration, duration)

        avg_drawdown = sum(drawdowns) / len(drawdowns) if drawdowns else Decimal("0")

        return max_drawdown, max_drawdown_percent, max_drawdown_duration or None, avg_drawdown

    def _calculate_sharpe_ratio(
        self,
        annualized_return: Decimal,
        annualized_volatility: Decimal,
    ) -> Optional[Decimal]:
        if annualized_volatility == 0:
            return None

        excess_return = annualized_return - (self.risk_free_rate * 100)
        return excess_return / annualized_volatility

    def _calculate_sortino_ratio(
        self,
        annualized_return: Decimal,
        annualized_downside_vol: Decimal,
    ) -> Optional[Decimal]:
        if annualized_downside_vol == 0:
            return None

        excess_return = annualized_return - (self.risk_free_rate * 100)
        return excess_return / annualized_downside_vol

    def _calculate_calmar_ratio(
        self,
        annualized_return: Decimal,
        max_drawdown_percent: Decimal,
    ) -> Optional[Decimal]:
        if max_drawdown_percent == 0:
            return None

        return annualized_return / max_drawdown_percent

    def _calculate_alpha_beta(
        self,
        returns: list[Decimal],
        benchmark_returns: list[Decimal],
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        if len(returns) != len(benchmark_returns) or len(returns) < 2:
            return None, None

        n = len(returns)
        sum_x = sum(benchmark_returns)
        sum_y = sum(returns)
        sum_xy = sum(r * b for r, b in zip(returns, benchmark_returns))
        sum_xx = sum(b * b for b in benchmark_returns)

        denominator = n * sum_xx - sum_x * sum_x
        if denominator == 0:
            return None, None

        beta = (n * sum_xy - sum_x * sum_y) / denominator
        alpha = (sum_y - beta * sum_x) / n

        alpha_annualized = alpha * self.TRADING_DAYS_PER_YEAR

        return alpha_annualized, beta

    def _calculate_information_ratio(
        self,
        returns: list[Decimal],
        benchmark_returns: list[Decimal],
    ) -> Optional[Decimal]:
        if len(returns) != len(benchmark_returns) or len(returns) < 2:
            return None

        excess_returns = [r - b for r, b in zip(returns, benchmark_returns)]
        mean_excess = sum(excess_returns) / len(excess_returns)
        tracking_error = self._calculate_volatility(excess_returns)

        if tracking_error == 0:
            return None

        annualized_tracking_error = tracking_error * Decimal(math.sqrt(self.TRADING_DAYS_PER_YEAR))
        annualized_excess = mean_excess * self.TRADING_DAYS_PER_YEAR

        return annualized_excess / annualized_tracking_error

    def calculate_rolling_metrics(
        self,
        equity_curve: list[EquityCurvePoint],
        window: int = 20,
    ) -> dict[str, list[Decimal]]:
        if len(equity_curve) < window:
            return {"rolling_sharpe": [], "rolling_volatility": []}

        rolling_sharpe = []
        rolling_volatility = []

        daily_returns = self._calculate_daily_returns(equity_curve)

        for i in range(window - 1, len(daily_returns)):
            window_returns = daily_returns[i - window + 1:i + 1]
            vol = self._calculate_volatility(window_returns)
            annualized_vol = vol * Decimal(math.sqrt(self.TRADING_DAYS_PER_YEAR))

            mean_return = sum(window_returns) / len(window_returns)
            annualized_return = mean_return * self.TRADING_DAYS_PER_YEAR * 100

            sharpe = self._calculate_sharpe_ratio(annualized_return, annualized_vol * 100)

            rolling_sharpe.append(sharpe if sharpe else Decimal("0"))
            rolling_volatility.append(annualized_vol * 100)

        return {
            "rolling_sharpe": rolling_sharpe,
            "rolling_volatility": rolling_volatility,
        }
