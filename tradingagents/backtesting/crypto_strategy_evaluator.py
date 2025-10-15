"""
Crypto Strategy Evaluator
Evaluates trading strategies using crypto agents and backtesting engine
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from .crypto_backtest_engine import CryptoBacktestEngine, OrderType
from .crypto_data_loader import CryptoDataLoader


class AgentDecision:
    """Represents an agent's trading decision."""
    def __init__(self, signal: str, confidence: float = 0.5, reasoning: str = ""):
        self.signal = signal.upper()  # BUY, SELL, HOLD
        self.confidence = confidence  # 0.0 to 1.0
        self.reasoning = reasoning


class CryptoStrategyEvaluator:
    """
    Evaluate crypto trading strategies with agent integration.

    Supports:
    - Agent-based decision making
    - Walk-forward testing
    - Multiple asset backtesting
    - Performance comparison
    """

    def __init__(
        self,
        backtest_engine: Optional[CryptoBacktestEngine] = None,
        data_loader: Optional[CryptoDataLoader] = None
    ):
        """
        Initialize strategy evaluator.

        Args:
            backtest_engine: Backtesting engine instance
            data_loader: Data loader instance
        """
        self.engine = backtest_engine or CryptoBacktestEngine()
        self.data_loader = data_loader or CryptoDataLoader()

        # Agent performance tracking
        self.agent_decisions: List[Dict] = []
        self.agent_accuracy: Dict[str, Dict] = {}

    def run_backtest(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        strategy_func: Callable,
        timeframe: str = '1d'
    ) -> Dict:
        """
        Run backtest with a strategy function.

        Args:
            symbol: Trading pair
            start_date: Backtest start date
            end_date: Backtest end date
            strategy_func: Function that returns OrderType given (date, price_data, engine)
            timeframe: Data timeframe

        Returns:
            Performance metrics dictionary
        """
        # Load historical data
        df = self.data_loader.fetch_ohlcv(symbol, timeframe, start_date, end_date)

        print(f"\nRunning backtest for {symbol}")
        print(f"Period: {start_date.date()} to {end_date.date()}")
        print(f"Data points: {len(df)}")
        print(f"Initial capital: ${self.engine.initial_capital:,.2f}\n")

        # Iterate through each day
        for timestamp, row in df.iterrows():
            current_price = row['close']
            current_prices = {symbol: current_price}

            # Check stop loss / take profit
            self.engine.check_stop_loss_take_profit(timestamp, current_prices)

            # Get strategy decision
            try:
                order_type, reason = strategy_func(timestamp, row, self.engine)

                # Execute trade
                if order_type != OrderType.HOLD:
                    self.engine.execute_trade(
                        timestamp, symbol, order_type, current_price, reason
                    )
            except Exception as e:
                print(f"Error in strategy at {timestamp}: {e}")

            # Update portfolio value
            self.engine.update_portfolio_value(timestamp, current_prices)

        # Get performance metrics
        metrics = self.engine.get_performance_metrics()

        print(f"\n{'='*60}")
        print(f"BACKTEST RESULTS")
        print(f"{'='*60}")
        print(f"Final Capital:    ${metrics['final_capital']:,.2f}")
        print(f"Total Return:     {metrics['total_return_pct']:.2f}%")
        print(f"Max Drawdown:     {metrics['max_drawdown_pct']:.2f}%")
        print(f"Sharpe Ratio:     {metrics['sharpe_ratio']:.2f}")
        print(f"Total Trades:     {metrics['total_trades']}")
        print(f"Win Rate:         {metrics['win_rate_pct']:.2f}%")
        print(f"{'='*60}\n")

        return metrics

    def run_agent_backtest(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        agent_func: Callable[[datetime, pd.Series], AgentDecision],
        timeframe: str = '1d'
    ) -> Dict:
        """
        Run backtest with agent decision function.

        Args:
            symbol: Trading pair
            start_date: Start date
            end_date: End date
            agent_func: Function that returns AgentDecision
            timeframe: Data timeframe

        Returns:
            Performance metrics with agent accuracy
        """
        def agent_strategy(timestamp: datetime, row: pd.Series, engine: CryptoBacktestEngine):
            # Get agent decision
            decision = agent_func(timestamp, row)

            # Record decision for accuracy tracking
            self.agent_decisions.append({
                'timestamp': timestamp,
                'price': row['close'],
                'signal': decision.signal,
                'confidence': decision.confidence,
                'reasoning': decision.reasoning
            })

            # Convert to OrderType
            if decision.signal == 'BUY':
                return OrderType.BUY, decision.reasoning
            elif decision.signal == 'SELL':
                return OrderType.SELL, decision.reasoning
            else:
                return OrderType.HOLD, decision.reasoning

        # Run backtest
        metrics = self.run_backtest(symbol, start_date, end_date, agent_strategy, timeframe)

        # Calculate agent accuracy
        agent_metrics = self._calculate_agent_accuracy(symbol)
        metrics.update(agent_metrics)

        return metrics

    def _calculate_agent_accuracy(self, symbol: str) -> Dict:
        """
        Calculate agent prediction accuracy.

        Compares agent signals to actual price movements.

        Returns:
            Dictionary with accuracy metrics
        """
        if len(self.agent_decisions) < 2:
            return {'agent_accuracy': 0.0}

        correct_predictions = 0
        total_predictions = 0

        for i in range(len(self.agent_decisions) - 1):
            current = self.agent_decisions[i]
            next_price = self.agent_decisions[i + 1]['price']
            current_price = current['price']

            # Calculate actual price movement
            price_change = (next_price - current_price) / current_price

            # Check if signal was correct
            if current['signal'] == 'BUY' and price_change > 0:
                correct_predictions += 1
            elif current['signal'] == 'SELL' and price_change < 0:
                correct_predictions += 1
            elif current['signal'] == 'HOLD' and abs(price_change) < 0.02:
                correct_predictions += 1

            total_predictions += 1

        accuracy = correct_predictions / total_predictions if total_predictions > 0 else 0

        return {
            'agent_accuracy': accuracy,
            'agent_accuracy_pct': accuracy * 100,
            'agent_correct_predictions': correct_predictions,
            'agent_total_predictions': total_predictions
        }

    def run_walk_forward_test(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        strategy_func: Callable,
        train_period_days: int = 90,
        test_period_days: int = 30,
        timeframe: str = '1d'
    ) -> List[Dict]:
        """
        Run walk-forward testing (rolling window).

        Args:
            symbol: Trading pair
            start_date: Overall start date
            end_date: Overall end date
            strategy_func: Strategy function
            train_period_days: Training period length
            test_period_days: Testing period length
            timeframe: Data timeframe

        Returns:
            List of performance metrics for each test period
        """
        results = []
        current_date = start_date

        while current_date < end_date:
            # Define train and test periods
            train_start = current_date
            train_end = train_start + timedelta(days=train_period_days)
            test_start = train_end
            test_end = test_start + timedelta(days=test_period_days)

            if test_end > end_date:
                break

            print(f"\nWalk-Forward Period:")
            print(f"  Train: {train_start.date()} to {train_end.date()}")
            print(f"  Test:  {test_start.date()} to {test_end.date()}")

            # Create new engine for this period
            period_engine = CryptoBacktestEngine(
                initial_capital=self.engine.initial_capital,
                commission_rate=self.engine.commission_rate,
                slippage_rate=self.engine.slippage_rate
            )

            # Create temporary evaluator
            temp_evaluator = CryptoStrategyEvaluator(period_engine, self.data_loader)

            # Run test period backtest
            metrics = temp_evaluator.run_backtest(
                symbol, test_start, test_end, strategy_func, timeframe
            )

            metrics['train_start'] = train_start
            metrics['train_end'] = train_end
            metrics['test_start'] = test_start
            metrics['test_end'] = test_end

            results.append(metrics)

            # Move to next period
            current_date = test_end

        # Aggregate results
        print(f"\n{'='*60}")
        print(f"WALK-FORWARD RESULTS SUMMARY")
        print(f"{'='*60}")
        print(f"Total periods:    {len(results)}")

        if results:
            avg_return = np.mean([r['total_return_pct'] for r in results])
            avg_sharpe = np.mean([r['sharpe_ratio'] for r in results])
            avg_drawdown = np.mean([r['max_drawdown_pct'] for r in results])

            print(f"Avg Return:       {avg_return:.2f}%")
            print(f"Avg Sharpe:       {avg_sharpe:.2f}")
            print(f"Avg Drawdown:     {avg_drawdown:.2f}%")

        print(f"{'='*60}\n")

        return results

    def compare_strategies(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        strategies: Dict[str, Callable],
        timeframe: str = '1d'
    ) -> pd.DataFrame:
        """
        Compare multiple strategies.

        Args:
            symbol: Trading pair
            start_date: Start date
            end_date: End date
            strategies: Dictionary of strategy_name -> strategy_function
            timeframe: Data timeframe

        Returns:
            DataFrame comparing strategy performance
        """
        results = []

        for strategy_name, strategy_func in strategies.items():
            print(f"\nEvaluating strategy: {strategy_name}")

            # Create new engine for fair comparison
            engine = CryptoBacktestEngine(
                initial_capital=self.engine.initial_capital,
                commission_rate=self.engine.commission_rate,
                slippage_rate=self.engine.slippage_rate
            )

            evaluator = CryptoStrategyEvaluator(engine, self.data_loader)
            metrics = evaluator.run_backtest(
                symbol, start_date, end_date, strategy_func, timeframe
            )

            metrics['strategy_name'] = strategy_name
            results.append(metrics)

        # Create comparison DataFrame
        df = pd.DataFrame(results)

        # Reorder columns
        cols = ['strategy_name', 'total_return_pct', 'sharpe_ratio', 'max_drawdown_pct',
                'win_rate_pct', 'total_trades', 'profit_factor']
        df = df[[c for c in cols if c in df.columns]]

        print(f"\n{'='*80}")
        print(f"STRATEGY COMPARISON")
        print(f"{'='*80}")
        print(df.to_string(index=False))
        print(f"{'='*80}\n")

        return df

    def test_on_market_cycles(
        self,
        symbol: str,
        strategy_func: Callable,
        cycles: List[Dict],
        timeframe: str = '1d'
    ) -> Dict[str, Dict]:
        """
        Test strategy on specific market cycles (bull/bear).

        Args:
            symbol: Trading pair
            strategy_func: Strategy function
            cycles: List of cycle dictionaries with start/end dates
            timeframe: Data timeframe

        Returns:
            Dictionary of cycle_name -> metrics
        """
        results = {}

        for cycle in cycles:
            cycle_name = cycle.get('name', f"{cycle['type']} cycle")
            start_date = pd.to_datetime(cycle['start'])
            end_date = pd.to_datetime(cycle['end'])

            print(f"\nTesting on: {cycle_name}")
            print(f"  Type: {cycle['type']}")
            print(f"  Period: {start_date.date()} to {end_date.date()}")

            # Create new engine
            engine = CryptoBacktestEngine(
                initial_capital=self.engine.initial_capital,
                commission_rate=self.engine.commission_rate,
                slippage_rate=self.engine.slippage_rate
            )

            evaluator = CryptoStrategyEvaluator(engine, self.data_loader)
            metrics = evaluator.run_backtest(
                symbol, start_date, end_date, strategy_func, timeframe
            )

            metrics['cycle_name'] = cycle_name
            metrics['cycle_type'] = cycle['type']
            results[cycle_name] = metrics

        return results
