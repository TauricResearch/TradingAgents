import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, Callable
from uuid import uuid4

from tradingagents.models.backtest import (
    BacktestConfig,
    BacktestResult,
    EquityCurvePoint,
    TradeLog,
)
from tradingagents.models.decisions import SignalType, TradingDecision
from tradingagents.models.portfolio import PortfolioSnapshot
from tradingagents.models.trading import Order, OrderSide, OrderStatus, Fill, Trade

from .data_loader import DataLoader
from .metrics import MetricsCalculator

logger = logging.getLogger(__name__)


class BacktestEngine:
    def __init__(
        self,
        config: BacktestConfig,
        decision_callback: Optional[Callable[[str, date, dict], TradingDecision]] = None,
    ):
        self.config = config
        self.decision_callback = decision_callback
        self.data_loader = DataLoader()
        self.metrics_calculator = MetricsCalculator(config.risk_free_rate)

        self.portfolio: Optional[PortfolioSnapshot] = None
        self.trade_log: Optional[TradeLog] = None
        self.equity_curve: list[EquityCurvePoint] = []
        self.daily_returns: list[Decimal] = []
        self.decisions: list[TradingDecision] = []
        self.open_trades: dict[str, Trade] = {}

    def run(self) -> BacktestResult:
        started_at = datetime.now()

        try:
            self._initialize()
            self._preload_data()
            trading_days = self._get_trading_days()

            for i, trading_date in enumerate(trading_days):
                if i < self.config.warmup_period:
                    continue

                self._process_day(trading_date, i)

            self._close_all_positions(trading_days[-1] if trading_days else self.config.end_date)

            metrics = self.metrics_calculator.calculate_metrics(
                self.equity_curve,
                self.trade_log,
            )

            completed_at = datetime.now()

            return BacktestResult(
                config=self.config,
                metrics=metrics,
                trade_log=self.trade_log,
                equity_curve=self.equity_curve,
                daily_returns=self.daily_returns,
                started_at=started_at,
                completed_at=completed_at,
                status="completed",
            )

        except (ValueError, KeyError, RuntimeError, FileNotFoundError, OSError) as e:
            logger.exception("Backtest failed: %s", e)
            completed_at = datetime.now()

            return BacktestResult(
                config=self.config,
                metrics=self._empty_metrics(),
                trade_log=self.trade_log or TradeLog(),
                equity_curve=self.equity_curve,
                daily_returns=self.daily_returns,
                started_at=started_at,
                completed_at=completed_at,
                status="failed",
                error_message=str(e),
            )

    def _initialize(self):
        self.portfolio = PortfolioSnapshot(
            cash=self.config.portfolio_config.initial_cash,
        )
        self.trade_log = TradeLog()
        self.equity_curve = []
        self.daily_returns = []
        self.decisions = []
        self.open_trades = {}

    def _preload_data(self):
        logger.info("Preloading data for %s tickers", len(self.config.tickers))
        for ticker in self.config.tickers:
            self.data_loader.load_ohlcv(
                ticker,
                self.config.start_date - timedelta(days=self.config.warmup_period + 10),
                self.config.end_date,
            )

    def _get_trading_days(self) -> list[date]:
        primary_ticker = self.config.tickers[0]
        return self.data_loader.get_trading_days(
            primary_ticker,
            self.config.start_date,
            self.config.end_date,
        )

    def _process_day(self, trading_date: date, day_index: int):
        prices = self.data_loader.get_prices_dict(self.config.tickers, trading_date)

        if not prices:
            logger.debug("No prices available for %s", trading_date)
            return

        for ticker in self.config.tickers:
            if ticker not in prices:
                continue

            decision = self._get_decision(ticker, trading_date, day_index)
            if decision:
                self.decisions.append(decision)
                self._execute_decision(decision, prices[ticker], trading_date)

        self._record_equity(trading_date, prices)

    def _get_decision(
        self,
        ticker: str,
        trading_date: date,
        day_index: int,
    ) -> Optional[TradingDecision]:
        if self.decision_callback:
            context = {
                "day_index": day_index,
                "portfolio": self.portfolio,
                "open_trade": self.open_trades.get(ticker),
            }
            return self.decision_callback(ticker, trading_date, context)

        return self._simple_strategy(ticker, trading_date)

    def _simple_strategy(
        self,
        ticker: str,
        trading_date: date,
    ) -> Optional[TradingDecision]:
        return None

    def _execute_decision(
        self,
        decision: TradingDecision,
        price: Decimal,
        trading_date: date,
    ):
        ticker = decision.ticker
        config = self.config.portfolio_config
        position = self.portfolio.get_position(ticker)

        if decision.is_buy and position.quantity == 0:
            execution_price = config.calculate_slippage(price, OrderSide.BUY)

            if decision.recommended_quantity:
                quantity = decision.recommended_quantity
            else:
                max_position_value = self.portfolio.cash * (config.max_position_size_percent / 100)
                quantity = int(max_position_value / execution_price)

            if quantity <= 0:
                return

            if not self.portfolio.can_afford(ticker, quantity, execution_price, config):
                quantity = self.portfolio.max_shares_affordable(ticker, execution_price, config)

            if quantity <= 0:
                return

            commission = config.calculate_commission(quantity, execution_price)

            order = Order(
                ticker=ticker,
                side=OrderSide.BUY,
                quantity=quantity,
                status=OrderStatus.FILLED,
                filled_quantity=quantity,
                filled_avg_price=execution_price,
                filled_at=datetime.combine(trading_date, datetime.min.time()),
                commission=commission,
            )

            fill = Fill(
                order_id=order.id,
                ticker=ticker,
                side=OrderSide.BUY,
                quantity=quantity,
                price=execution_price,
                commission=commission,
                timestamp=datetime.combine(trading_date, datetime.min.time()),
            )

            self.portfolio.apply_fill(fill)

            trade = Trade(
                ticker=ticker,
                side=OrderSide.BUY,
                entry_price=execution_price,
                entry_quantity=quantity,
                entry_time=datetime.combine(trading_date, datetime.min.time()),
                entry_order_id=order.id,
            )
            self.open_trades[ticker] = trade

            logger.debug(
                "BUY %s: %d shares @ $%.2f on %s",
                ticker, quantity, execution_price, trading_date
            )

        elif decision.is_sell and position.quantity > 0:
            execution_price = config.calculate_slippage(price, OrderSide.SELL)
            quantity = position.quantity
            commission = config.calculate_commission(quantity, execution_price)

            order = Order(
                ticker=ticker,
                side=OrderSide.SELL,
                quantity=quantity,
                status=OrderStatus.FILLED,
                filled_quantity=quantity,
                filled_avg_price=execution_price,
                filled_at=datetime.combine(trading_date, datetime.min.time()),
                commission=commission,
            )

            fill = Fill(
                order_id=order.id,
                ticker=ticker,
                side=OrderSide.SELL,
                quantity=quantity,
                price=execution_price,
                commission=commission,
                timestamp=datetime.combine(trading_date, datetime.min.time()),
            )

            self.portfolio.apply_fill(fill)

            if ticker in self.open_trades:
                trade = self.open_trades[ticker]
                trade.exit_price = execution_price
                trade.exit_quantity = quantity
                trade.exit_time = datetime.combine(trading_date, datetime.min.time())
                trade.exit_order_id = order.id
                trade.commission = (
                    config.calculate_commission(trade.entry_quantity, trade.entry_price) +
                    commission
                )
                self.trade_log.add_trade(trade)
                del self.open_trades[ticker]

            logger.debug(
                "SELL %s: %d shares @ $%.2f on %s",
                ticker, quantity, execution_price, trading_date
            )

    def _record_equity(self, trading_date: date, prices: dict[str, Decimal]):
        equity = self.portfolio.total_equity(prices)
        positions_value = self.portfolio.positions_value(prices)

        point = EquityCurvePoint(
            timestamp=datetime.combine(trading_date, datetime.min.time()),
            equity=equity,
            cash=self.portfolio.cash,
            positions_value=positions_value,
        )
        self.equity_curve.append(point)

        if len(self.equity_curve) > 1:
            prev_equity = self.equity_curve[-2].equity
            if prev_equity > 0:
                daily_return = (equity - prev_equity) / prev_equity
                self.daily_returns.append(daily_return)

    def _close_all_positions(self, final_date: date):
        prices = self.data_loader.get_prices_dict(self.config.tickers, final_date)

        for ticker, trade in list(self.open_trades.items()):
            if ticker in prices:
                decision = TradingDecision(
                    ticker=ticker,
                    timestamp=datetime.now(),
                    decision_date=datetime.combine(final_date, datetime.min.time()),
                    signal=SignalType.SELL,
                    confidence=Decimal("1.0"),
                    recommended_action="SELL",
                    final_decision="SELL - End of backtest",
                    rationale="Closing position at end of backtest period",
                )
                self._execute_decision(decision, prices[ticker], final_date)

    def _empty_metrics(self):
        from tradingagents.models.backtest import BacktestMetrics
        return BacktestMetrics(
            start_equity=self.config.portfolio_config.initial_cash,
            end_equity=self.portfolio.cash if self.portfolio else self.config.portfolio_config.initial_cash,
        )


class SimpleBacktestEngine(BacktestEngine):
    def __init__(
        self,
        config: BacktestConfig,
        buy_signal: Callable[[str, date, dict], bool] = None,
        sell_signal: Callable[[str, date, dict], bool] = None,
    ):
        super().__init__(config)
        self.buy_signal = buy_signal
        self.sell_signal = sell_signal

    def _get_decision(
        self,
        ticker: str,
        trading_date: date,
        day_index: int,
    ) -> Optional[TradingDecision]:
        context = {
            "day_index": day_index,
            "portfolio": self.portfolio,
            "data_loader": self.data_loader,
            "open_trade": self.open_trades.get(ticker),
        }

        position = self.portfolio.get_position(ticker)

        if position.quantity == 0 and self.buy_signal and self.buy_signal(ticker, trading_date, context):
            return TradingDecision(
                ticker=ticker,
                timestamp=datetime.now(),
                decision_date=datetime.combine(trading_date, datetime.min.time()),
                signal=SignalType.BUY,
                confidence=Decimal("0.7"),
                recommended_action="BUY",
                final_decision="BUY",
                rationale="Buy signal triggered",
            )

        if position.quantity > 0 and self.sell_signal and self.sell_signal(ticker, trading_date, context):
            return TradingDecision(
                ticker=ticker,
                timestamp=datetime.now(),
                decision_date=datetime.combine(trading_date, datetime.min.time()),
                signal=SignalType.SELL,
                confidence=Decimal("0.7"),
                recommended_action="SELL",
                final_decision="SELL",
                rationale="Sell signal triggered",
            )

        return None
