"""
Algo Trading Workflow

Complete workflow for screening stocks, detecting pump signals, and executing
trades algorithmically with portfolio management and risk controls.

Usage:
    from algo_trading_workflow import AlgoTradingBot
    
    bot = AlgoTradingBot(
        portfolio_cash=10000,
        paper_trading=True,
    )
    
    # Run continuous trading loop
    bot.run()
    
    # Or run single iteration
    bot.run_iteration()
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import asdict

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.strategy.portfolio_manager import PortfolioManager
from tradingagents.strategy.exit_strategy import ExitStrategy, ExitConfig
from tradingagents.strategy.trade_validator import TradeValidator
from tradingagents.agents.trader.paper_trading import PaperTrader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AlgoTradingBot:
    """
    Algorithmic Trading Bot
    
    Orchestrates:
    1. Stock screening (find candidates)
    2. Signal detection (identify opportunities)
    3. Position management (8% rule, max positions)
    4. Trade execution (Webull paper trading)
    5. Exit management (profit targets, stop losses)
    """
    
    def __init__(
        self,
        portfolio_cash: float = 10000.0,
        paper_trading: bool = True,
        selected_analysts: Optional[List[str]] = None,
        webull_email: Optional[str] = None,
        webull_password: Optional[str] = None,
        webull_pin: Optional[str] = None,
    ):
        """
        Initialize algo trading bot.
        
        Args:
            portfolio_cash: Starting capital
            paper_trading: Use paper trading (True) or simulation (False)
            selected_analysts: Which analysts to use (market, social, news, fundamentals)
            webull_email: Webull account email
            webull_password: Webull account password
            webull_pin: Webull trading PIN
        """
        self.portfolio_cash = portfolio_cash
        self.paper_trading = paper_trading
        self.selected_analysts = selected_analysts or ["market", "social"]
        
        # Initialize components
        self.graph = TradingAgentsGraph(
            include_screening=True,
            include_pump_detection=True,
            selected_analysts=self.selected_analysts,
        )
        
        self.portfolio_manager = PortfolioManager(
            portfolio_cash=portfolio_cash,
            max_position_pct=0.08,  # 8% per stock
            max_risky_pct=0.25,     # 25% in risky trades
            max_positions=10,
        )
        
        self.exit_strategy = ExitStrategy(
            ExitConfig(
                profit_target_pct=5.0,    # Take profit at 5%
                stop_loss_pct=2.0,        # Stop loss at 2%
                max_hold_days=5,          # Max 5 days
                trailing_stop_pct=2.0,    # Trailing stop 2%
            )
        )
        
        # Paper trading
        self.paper_trader = None
        if paper_trading:
            self.paper_trader = PaperTrader(
                email=webull_email,
                password=webull_password,
                is_paper=True,
            )
            if webull_email and webull_password:
                self._setup_paper_trading(webull_pin)
        
        self.validator = TradeValidator()
        
        # Tracking
        self.iteration_count = 0
        self.last_iteration = None
        self.trade_log: List[Dict] = []
        
        logger.info(f"AlgoTradingBot initialized with ${portfolio_cash:.2f}")
    
    def _setup_paper_trading(self, pin: Optional[str] = None):
        """Setup Webull paper trading connection"""
        if not self.paper_trader:
            return False
        
        if not self.paper_trader.login():
            logger.warning("Failed to login to Webull")
            return False
        
        if pin and not self.paper_trader.get_trade_token(pin):
            logger.warning("Failed to get trade token")
            return False
        
        logger.info("Paper trading ready")
        return True
    
    def run_iteration(self):
        """
        Run one complete trading iteration:
        1. Analyze stock
        2. Check for buy signals
        3. Execute buy if signal strong
        4. Check existing positions for exits
        5. Execute sells if needed
        """
        self.iteration_count += 1
        iteration_start = datetime.now()
        
        logger.info(f"\n{'='*60}")
        logger.info(f"ITERATION {self.iteration_count} - {iteration_start}")
        logger.info(f"{'='*60}")
        
        # Get portfolio status
        portfolio_status = self.portfolio_manager.get_portfolio_status()
        logger.info(f"Portfolio: ${portfolio_status['total_value']:.2f} "
                   f"(Cash: ${portfolio_status['cash']:.2f})")
        
        # TODO: Implement stock selection logic
        # For now, demonstrate with a hardcoded example
        stocks_to_analyze = ["NVDA", "AAPL", "TSLA"]  # From screening agent
        
        for ticker in stocks_to_analyze:
            logger.info(f"\nAnalyzing {ticker}...")
            
            try:
                # Run graph analysis
                final_state, signal = self.graph.propagate(
                    ticker,
                    datetime.now().strftime("%Y-%m-%d")
                )
                
                # Check for pump detection signal
                pump_report = final_state.get("pump_report", "")
                screening_report = final_state.get("screening_report", "")
                
                # Parse signal score from reports
                pump_score = self._extract_pump_score(pump_report)
                
                logger.info(f"  Pump Score: {pump_score:.1f}")
                
                # Check if we should buy
                if pump_score > 70:  # Threshold for entry
                    self._attempt_buy(ticker, pump_score)
            
            except Exception as e:
                logger.error(f"Error analyzing {ticker}: {e}")
        
        # Check existing positions for exit signals
        self._check_exit_conditions()
        
        # Log iteration
        self.last_iteration = datetime.now()
        iteration_duration = (self.last_iteration - iteration_start).total_seconds()
        logger.info(f"\nIteration completed in {iteration_duration:.1f}s")
    
    def _attempt_buy(self, ticker: str, signal_score: float):
        """Attempt to buy a stock"""
        logger.info(f"  Buy signal for {ticker} (score: {signal_score:.1f})")
        
        # Get current price
        if self.paper_trader:
            quote = self.paper_trader.get_stock_quote(ticker)
            if not quote:
                logger.warning(f"  Could not get quote for {ticker}")
                return
            current_price = quote["price"]
        else:
            # Simulated price
            current_price = 100.0  # Demo value
        
        # Calculate position size
        position_size = self.portfolio_manager.calculate_position_size(
            current_price=current_price,
            signal_score=signal_score,
            position_type="pump",
        )
        
        if not position_size:
            logger.info(f"  Could not calculate position size")
            return
        
        shares = position_size["shares"]
        
        # Validate order
        validation = self.validator.validate_buy_order(
            ticker=ticker,
            shares=shares,
            price=current_price,
            available_cash=self.portfolio_manager.cash,
            portfolio_value=self.portfolio_manager.portfolio_value,
        )
        
        if not validation["is_valid"]:
            logger.warning(f"  Order validation failed: {validation['issues']}")
            return
        
        # Place order
        if self.paper_trader:
            order = self.paper_trader.place_buy_order(
                ticker=ticker,
                quantity=shares,
                limit_price=current_price,
            )
            if not order:
                logger.error(f"  Failed to place buy order")
                return
        
        # Add to portfolio
        if self.portfolio_manager.add_position(
            ticker=ticker,
            shares=shares,
            entry_price=current_price,
            signal_score=signal_score,
            position_type="pump",
        ):
            logger.info(f"  ✓ Bought {shares} shares of {ticker} @ ${current_price:.2f}")
            self.trade_log.append({
                "action": "BUY",
                "ticker": ticker,
                "shares": shares,
                "price": current_price,
                "timestamp": datetime.now().isoformat(),
                "signal_score": signal_score,
            })
        else:
            logger.error(f"  Failed to add position to portfolio")
    
    def _check_exit_conditions(self):
        """Check all positions for exit signals"""
        positions_to_check = list(self.portfolio_manager.positions.keys())
        
        for ticker in positions_to_check:
            position = self.portfolio_manager.positions[ticker]
            
            # Get current price
            if self.paper_trader:
                quote = self.paper_trader.get_stock_quote(ticker)
                if not quote:
                    continue
                current_price = quote["price"]
            else:
                current_price = 100.0  # Demo value
            
            # Check exit conditions
            exit_signal = self.exit_strategy.evaluate_exit(
                ticker=ticker,
                current_price=current_price,
                entry_price=position.entry_price,
                entry_date=position.entry_date,
                signal_score=position.signal_score,
                position_type=position.position_type,
            )
            
            if exit_signal and exit_signal.get("exit_signal"):
                self._attempt_sell(
                    ticker=ticker,
                    exit_price=current_price,
                    reason=exit_signal["reason"],
                )
    
    def _attempt_sell(self, ticker: str, exit_price: float, reason: str):
        """Attempt to sell a position"""
        logger.info(f"  Sell signal for {ticker} ({reason})")
        
        position = self.portfolio_manager.positions.get(ticker)
        if not position:
            logger.warning(f"  No position found for {ticker}")
            return
        
        shares = position.shares
        
        # Validate order
        validation = self.validator.validate_sell_order(
            ticker=ticker,
            shares=shares,
            price=exit_price,
            position_shares=position.shares,
            position_value=position.shares * position.entry_price,
        )
        
        if not validation["is_valid"]:
            logger.warning(f"  Order validation failed: {validation['issues']}")
            return
        
        # Place order
        if self.paper_trader:
            order = self.paper_trader.place_sell_order(
                ticker=ticker,
                quantity=shares,
                limit_price=exit_price,
            )
            if not order:
                logger.error(f"  Failed to place sell order")
                return
        
        # Close position
        result = self.portfolio_manager.close_position(
            ticker=ticker,
            exit_price=exit_price,
            reason=reason,
        )
        
        if result:
            logger.info(
                f"  ✓ Sold {shares} shares of {ticker} @ ${exit_price:.2f} "
                f"(P/L: ${result['profit']:.2f}, {result['profit_pct']:.1f}%)"
            )
            self.trade_log.append({
                "action": "SELL",
                "ticker": ticker,
                "shares": shares,
                "price": exit_price,
                "timestamp": datetime.now().isoformat(),
                "profit": result["profit"],
                "profit_pct": result["profit_pct"],
                "reason": reason,
            })
    
    def _extract_pump_score(self, pump_report: str) -> float:
        """Extract pump score from pump report"""
        # Simple extraction - look for "score:" or percentage
        if not pump_report:
            return 0.0
        
        import re
        # Look for number followed by % or "score"
        matches = re.findall(r'(\d+(?:\.\d+)?)\s*%?', pump_report)
        if matches:
            try:
                return float(matches[0])
            except ValueError:
                pass
        
        return 0.0
    
    def run(self, iterations: int = -1, interval_seconds: int = 300):
        """
        Run trading loop continuously.
        
        Args:
            iterations: Number of iterations (-1 for infinite)
            interval_seconds: Seconds between iterations (default 5 min)
        """
        iteration = 0
        logger.info(f"Starting algo trading loop (interval: {interval_seconds}s)")
        
        try:
            while iterations < 0 or iteration < iterations:
                self.run_iteration()
                iteration += 1
                
                if iterations < 0 or iteration < iterations:
                    logger.info(f"Next iteration in {interval_seconds}s...")
                    time.sleep(interval_seconds)
        
        except KeyboardInterrupt:
            logger.info("\nTrading loop interrupted by user")
        finally:
            self.save_state()
    
    def get_status(self) -> Dict:
        """Get current bot status"""
        portfolio_status = self.portfolio_manager.get_portfolio_status()
        
        return {
            "iteration": self.iteration_count,
            "last_iteration": self.last_iteration.isoformat() if self.last_iteration else None,
            "portfolio": portfolio_status,
            "trades": len(self.trade_log),
            "paper_trading": self.paper_trading,
        }
    
    def save_state(self, filepath: str = "trading_bot_state.json"):
        """Save bot state to file"""
        state = {
            "iteration": self.iteration_count,
            "timestamp": datetime.now().isoformat(),
            "portfolio": self.portfolio_manager.to_dict(),
            "exit_strategy": self.exit_strategy.to_dict(),
            "trades": self.trade_log,
        }
        
        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2)
        
        logger.info(f"State saved to {filepath}")
    
    def print_summary(self):
        """Print trading summary"""
        portfolio_status = self.portfolio_manager.get_portfolio_status()
        
        print(f"\n{'='*60}")
        print(f"TRADING SUMMARY")
        print(f"{'='*60}")
        print(f"Iterations: {self.iteration_count}")
        print(f"Portfolio Value: ${portfolio_status['total_value']:.2f}")
        print(f"Cash: ${portfolio_status['cash']:.2f}")
        print(f"Positions: {portfolio_status['num_positions']}")
        print(f"Total Trades: {len(self.trade_log)}")
        
        # Calculate P/L
        pnl = 0.0
        for trade in self.trade_log:
            if trade["action"] == "SELL" and "profit" in trade:
                pnl += trade["profit"]
        
        print(f"Net P/L: ${pnl:.2f}")
        print(f"Cash Utilization: {portfolio_status['cash_utilization']:.1f}%")
        print(f"Risky Exposure: {portfolio_status['risky_exposure']:.1f}%")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    # Example usage
    bot = AlgoTradingBot(
        portfolio_cash=10000.0,
        paper_trading=False,  # Demo mode (no Webull auth)
        selected_analysts=["market"],
    )
    
    # Run single iteration
    logger.info("Running demo iteration (not connected to Webull)...")
    bot.run_iteration()
    bot.print_summary()
