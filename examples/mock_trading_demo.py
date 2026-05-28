"""Example: Mock trading system demonstration."""

import sys
import logging
from datetime import datetime

# Add project root to path
sys.path.insert(0, '/home/lykia/Desktop/TradingAgents')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import mock trading modules
from tradingagents.mock_trading import (
    TradingDatabase,
    PortfolioManager,
    OrderManager,
    PriceType,
    CorporateActionsHandler,
    AsyncAnalyzer,
    AIDecisionMaker,
    RewardCalculator,
    RewardType,
    TradingScheduler,
)


def example_basic_trading():
    """Example 1: Basic buy/sell operations."""
    print("\n" + "="*60)
    print("EXAMPLE 1: Basic Trading Operations")
    print("="*60)
    
    # Create database and portfolio
    db = TradingDatabase(":memory:")
    portfolio_id = db.create_portfolio(1000.0)
    
    # Create portfolio manager
    pm = PortfolioManager(portfolio_id, 1000.0)
    
    logger.info("Initial portfolio value: $%.2f" % pm.initial_capital)
    
    # Simulate trades
    pm.buy("NVDA", quantity=5, price=100.0, fees=10.0)
    logger.info("Bought 5 NVDA @ $100 | Cash: $%.2f" % pm.cash_available)
    
    pm.buy("AAPL", quantity=10, price=150.0, fees=15.0)
    logger.info("Bought 10 AAPL @ $150 | Cash: $%.2f" % pm.cash_available)
    
    # Update prices
    prices = {"NVDA": 105.0, "AAPL": 155.0}
    for ticker, price in prices.items():
        pm.update_holding_price(ticker, price)
    
    # Check performance
    metrics = pm.get_performance_metrics(prices)
    logger.info("Portfolio value: $%.2f | Unrealized P&L: $%.2f" % 
               (metrics["portfolio_value"], metrics["unrealized_pl"]))
    
    # Sell position
    pm.sell("NVDA", quantity=5, price=105.0, fees=10.0)
    logger.info("Sold 5 NVDA @ $105 | Cash: $%.2f" % pm.cash_available)
    
    print("✓ Example 1 complete")


def example_order_execution():
    """Example 2: Order execution with slippage and status tracking."""
    print("\n" + "="*60)
    print("EXAMPLE 2: Order Execution with States")
    print("="*60)
    
    om = OrderManager()
    
    # Create orders
    order1 = om.create_order("NVDA", "BUY", quantity=10, price_type=PriceType.CLOSE,
                            reference_price=100.0, slippage_tolerance_pct=2.0)
    logger.info("Order 1: %s | Status: %s" % (order1, om.get_order_status(order1)))
    
    # Execute with acceptable slippage
    success = om.execute_order(order1, execution_price=101.5, quantity_filled=10,
                              available_volume=1000)
    logger.info("Execution result: %s | Status: %s | Slippage: %.2f%%" %
               (success, om.get_order_status(order1), om.get_slippage(order1)))
    
    # Create second order
    order2 = om.create_order("AAPL", "BUY", quantity=5, price_type=PriceType.CLOSE,
                            reference_price=150.0, slippage_tolerance_pct=1.0)
    
    # Try to execute with excessive slippage (should be rejected)
    success = om.execute_order(order2, execution_price=155.0, quantity_filled=5,
                              available_volume=500)
    logger.info("Execution result: %s | Status: %s (rejected due to slippage)" %
               (success, om.get_order_status(order2)))
    
    # Order summary
    summary = om.get_all_orders_summary()
    logger.info("Order Summary: %d filled, %d rejected" %
               (summary["filled"], summary["rejected"]))
    
    print("✓ Example 2 complete")


def example_async_analysis():
    """Example 3: Asynchronous AI analysis."""
    print("\n" + "="*60)
    print("EXAMPLE 3: Asynchronous Analysis")
    print("="*60)
    
    analyzer = AsyncAnalyzer(max_workers=2)
    
    # Define mock analysis function
    def mock_analysis(ticker, date):
        """Simulate AI analysis."""
        import time
        logger.info("Analyzing %s on %s..." % (ticker, date))
        time.sleep(2)  # Simulate analysis time
        return {
            "ticker": ticker,
            "date": date,
            "recommendation": "BUY" if ticker == "NVDA" else "HOLD",
            "confidence": 0.75 if ticker == "NVDA" else 0.50,
        }
    
    # Queue multiple analyses
    task1 = analyzer.queue_analysis("NVDA", "2025-01-15", mock_analysis)
    task2 = analyzer.queue_analysis("AAPL", "2025-01-15", mock_analysis)
    
    logger.info("Queued 2 analysis tasks: %s, %s" % (task1, task2))
    
    # Get results
    result1 = analyzer.wait_for_result(task1, timeout_sec=10)
    logger.info("Result 1: %s recommendation (%.0f%% confidence)" %
               (result1["recommendation"], result1["confidence"] * 100))
    
    result2 = analyzer.wait_for_result(task2, timeout_sec=10)
    logger.info("Result 2: %s recommendation (%.0f%% confidence)" %
               (result2["recommendation"], result2["confidence"] * 100))
    
    # Stats
    stats = analyzer.get_analysis_latency_stats()
    logger.info("Analysis latency: avg=%.1fs, min=%.1fs, max=%.1fs" %
               (stats["avg_sec"], stats["min_sec"], stats["max_sec"]))
    
    print("✓ Example 3 complete")


def example_reward_calculation():
    """Example 4: Hindsight RL reward calculation."""
    print("\n" + "="*60)
    print("EXAMPLE 4: Reward Calculation for Hindsight RL")
    print("="*60)
    
    rc = RewardCalculator(benchmark_ticker="SPY")
    
    # Record decision outcomes
    rc.record_decision_outcome(
        decision_id=1,
        decision_type="BUY",
        entry_price=100.0,
        entry_date="2025-01-01",
        exit_price=110.0,
        exit_date="2025-01-10",
        quantity=10.0
    )
    logger.info("Decision 1: Buy NVDA @ $100, sold @ $110")
    
    rc.record_decision_outcome(
        decision_id=2,
        decision_type="BUY",
        entry_price=150.0,
        entry_date="2025-01-01",
        exit_price=145.0,
        exit_date="2025-01-10",
        quantity=5.0
    )
    logger.info("Decision 2: Buy AAPL @ $150, sold @ $145")
    
    # Calculate rewards
    ret1 = rc.calculate_absolute_return(1)
    ret2 = rc.calculate_absolute_return(2)
    
    logger.info("Decision 1 return: +%.2f%%" % ret1)
    logger.info("Decision 2 return: %.2f%%" % ret2)
    
    # Summary stats
    stats = rc.get_summary_stats()
    logger.info("Win rate: %.0f%% | Avg return: %.2f%%" %
               (stats["win_rate"], stats["avg_return_pct"]))
    
    print("✓ Example 4 complete")


def example_scheduler():
    """Example 5: Trading scheduler."""
    print("\n" + "="*60)
    print("EXAMPLE 5: Trading Scheduler")
    print("="*60)
    
    try:
        scheduler = TradingScheduler(timezone="America/New_York")
        
        # Define mock trading functions
        def morning_analysis():
            logger.info("Morning analysis phase: queuing AI decisions...")
            return {"phase": "analysis", "time": "09:30"}
        
        def afternoon_execution():
            logger.info("Afternoon execution phase: executing cached decisions...")
            return {"phase": "execution", "time": "14:00"}
        
        # Schedule jobs
        job1 = scheduler.schedule_daily_execution(9, 30, morning_analysis, job_id="analysis_09_30")
        job2 = scheduler.schedule_daily_execution(14, 0, afternoon_execution, job_id="execute_14_00")
        
        logger.info("Scheduled 2 trading jobs:")
        for job_info in scheduler.get_all_jobs():
            logger.info("  - %s: %s @ %s (next: %s)" %
                       (job_info.get("job").id if hasattr(job_info.get("job"), "id") else "unknown",
                        job_info["function"],
                        job_info["schedule"],
                        job_info["next_run"]))
        
        status = scheduler.get_scheduler_status()
        logger.info("Scheduler status: %d jobs scheduled, running=%s" %
                   (status["num_jobs"], status["running"]))
        
        print("✓ Example 5 complete (scheduler ready, not started)")
    
    except ImportError as e:
        logger.warning("Scheduler example skipped: %s" % e)
        print("⊘ Example 5 skipped (APScheduler not available)")


if __name__ == "__main__":
    try:
        example_basic_trading()
        example_order_execution()
        example_async_analysis()
        example_reward_calculation()
        example_scheduler()
        
        print("\n" + "="*60)
        print("✅ ALL EXAMPLES COMPLETED SUCCESSFULLY")
        print("="*60)
        
    except Exception as e:
        logger.error("Example failed: %s" % e)
        import traceback
        traceback.print_exc()
        sys.exit(1)
