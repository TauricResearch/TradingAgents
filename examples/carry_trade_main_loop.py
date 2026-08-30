"""
Carry Trade Portfolio Main Loop
================================
Continuous monitoring and execution of carry trade portfolio.

Features:
- Real-time market data monitoring
- Automatic portfolio rebalancing
- Position execution on Alpaca Paper Trading
- Alert system for rate changes
- Performance tracking

Usage:
    python examples/carry_trade_main_loop.py
    python examples/carry_trade_main_loop.py --interval 300  # 5 minutes
    python examples/carry_trade_main_loop.py --execute  # Enable execution
"""

import os
import re
import sys
import json
import time
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

_SECRET_RE = re.compile(r"(ALPACA_API_KEY|ALPACA_SECRET_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY|FRED_API_KEY|BYMA_TOKEN|ALPHA_VANTAGE_API_KEY|api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[^'\"\s,}\n]+['\"]?", re.IGNORECASE)


def _redact(text: str) -> str:
    if not text:
        return text
    return _SECRET_RE.sub(lambda m: m.group(1) + "=***", text)

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradingagents.dataflows.providers.interest_rates import GlobalInterestRatesProvider
from tradingagents.dataflows.providers.fx_multi_currency import MultiCurrencyFXProvider
from tradingagents.chains.portfolio_manager import CarryTradePortfolioManager
from tradingagents.chains.alpaca_executor import CarryTradeExecutor


class CarryTradeMainLoop:
    """
    Main loop for carry trade portfolio management.
    
    Orchestrates:
    1. Market data fetching (rates + FX)
    2. Portfolio signal generation
    3. Risk management
    4. Position execution
    5. Monitoring and alerts
    """
    
    def __init__(
        self,
        interval_seconds: int = 300,
        execute_trades: bool = False,
        portfolio_value: float = 100000.0,
    ):
        """
        Initialize main loop.
        
        Args:
            interval_seconds: Time between iterations
            execute_trades: If True, execute trades on Alpaca
            portfolio_value: Starting portfolio value
        """
        self.interval = interval_seconds
        self.execute_trades = execute_trades
        self.portfolio_value = portfolio_value
        
        # Initialize components
        self.rates_provider = GlobalInterestRatesProvider()
        self.fx_provider = MultiCurrencyFXProvider()
        self.portfolio_manager = CarryTradePortfolioManager()
        self.executor = CarryTradeExecutor(
            dry_run=not execute_trades,
            use_paper=True
        )
        
        # History
        self.history: List[Dict] = []
        self.rebalance_history: List[Dict] = []
        
        # Log file
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        self.log_file = self.log_dir / f"carry_trade_loop_{datetime.now().strftime('%Y%m%d')}.log"
        # secure log file permissions (best effort, ignore on Windows)
        try:
            self.log_file.touch(exist_ok=True)
            os.chmod(self.log_file, 0o600)
        except Exception:
            pass
    
    def log(self, message: str, level: str = "INFO"):
        """Log message with secret redaction"""
        message = _redact(message)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        print(log_entry)
        
        with open(self.log_file, "a") as f:
            f.write(log_entry + "\n")
        # enforce 600 after each write (best effort, ignore on Windows)
        try:
            os.chmod(self.log_file, 0o600)
        except Exception:
            pass
    
    def fetch_market_data(self) -> Dict:
        """Fetch current market data"""
        self.log("Fetching market data...")
        
        # Get interest rates
        rates = self.rates_provider.get_all_rates()
        
        # Get FX rates
        fx_pairs = [
            "USD_BRL", "USD_TRY", "USD_MXN", "USD_INR", 
            "USD_ZAR", "USD_ARS", "USD_CLP", "USD_PLN",
            "USD_COP", "USD_IDR", "USD_THB", "USD_PHP",
        ]
        fx_rates = {}
        
        for pair in fx_pairs:
            base, quote = pair.split("_")
            rate = self.fx_provider.get_rate(base, quote)
            if rate:
                fx_rates[pair] = rate.rate
        
        return {
            "rates": rates,
            "fx_rates": fx_rates,
            "timestamp": datetime.now().isoformat(),
        }
    
    def generate_signals(self, market_data: Dict) -> List[Dict]:
        """Generate trading signals from market data"""
        self.log("Generating trading signals...")
        
        signals = []
        
        # Get current rates
        rates = market_data["rates"]
        us_rate = rates.get("US")
        
        if not us_rate:
            self.log("No US rate data available", "WARNING")
            return signals
        
        # All currencies we track
        currencies = ["BR", "MX", "IN", "ZA", "CL", "TR", "PL", "CO", "ID", "TH", "PH"]
        
        for currency in currencies:
            currency_rate = rates.get(currency)
            if not currency_rate:
                continue
            
            # Calculate spread
            spread = currency_rate.rate - us_rate.rate
            
            # Generate signal based on spread
            if spread > 3.0:
                signal_strength = "strong_buy"
            elif spread > 1.5:
                signal_strength = "buy"
            elif spread < -1.0:
                signal_strength = "sell"
            elif spread < 0:
                signal_strength = "weak_sell"
            else:
                signal_strength = "hold"
            
            # Get FX rate
            fx_pair = f"USD_{currency_rate.currency}"
            fx_rate = market_data["fx_rates"].get(fx_pair)
            
            # Get FX volatility (simplified - use historical average)
            fx_volatility = self._get_fx_volatility(currency_rate.currency)
            
            signals.append({
                "currency": currency_rate.currency,
                "country": currency,
                "funding_rate": us_rate.rate,
                "target_rate": currency_rate.rate,
                "spread": spread,
                "signal": signal_strength,
                "fx_rate": fx_rate,
                "fx_volatility": fx_volatility,
                "timestamp": datetime.now().isoformat(),
            })
        
        # Sort by spread (highest first)
        signals.sort(key=lambda x: x["spread"], reverse=True)
        
        self.log(f"Generated {len(signals)} signals")
        
        return signals
    
    def _get_fx_volatility(self, currency: str) -> float:
        """Get historical FX volatility for a currency"""
        # Simplified volatility estimates
        volatility_map = {
            "BRL": 15.0,
            "TRY": 25.0,
            "MXN": 12.0,
            "INR": 8.0,
            "ZAR": 18.0,
            "ARS": 30.0,
            "CLP": 14.0,
            "PLN": 10.0,
            "COP": 16.0,
            "IDR": 12.0,
            "THB": 10.0,
            "PHP": 9.0,
        }
        
        return volatility_map.get(currency, 12.0)
    
    def check_rebalance_needed(
        self,
        signals: List[Dict],
        current_positions: List[Dict],
    ) -> Tuple[bool, Dict[str, float]]:
        """
        Check if rebalancing is needed.
        
        Returns:
            Tuple of (needs_rebalance, target_allocations)
        """
        # Calculate target allocations based on signals
        target_allocations = {}
        
        # Strategy: allocate more to higher spreads (with risk adjustment)
        total_weighted_spread = 0
        
        for signal in signals:
            if signal["signal"] in ["strong_buy", "buy"]:
                # Weight by spread, adjusted for volatility
                weight = signal["spread"] / (1 + signal["fx_volatility"] / 100)
                target_allocations[signal["currency"]] = weight
                total_weighted_spread += weight
        
        # Normalize to 100%
        if total_weighted_spread > 0:
            for currency in target_allocations:
                target_allocations[currency] /= total_weighted_spread
        
        # Check if rebalance is needed
        needs_rebalance = False
        
        # Get current allocations
        current_allocations = {}
        for pos in current_positions:
            # Map ETF symbol back to currency (simplified)
            currency = self._etf_to_currency(pos["symbol"])
            if currency:
                current_allocations[currency] = pos["market_value"] / self.portfolio_value
        
        # Compare allocations
        for currency, target in target_allocations.items():
            current = current_allocations.get(currency, 0)
            diff = abs(target - current)
            
            if diff > 0.05:  # 5% threshold
                needs_rebalance = True
                break
        
        return needs_rebalance, target_allocations
    
    def _etf_to_currency(self, etf_symbol: str) -> Optional[str]:
        """Map ETF symbol back to currency"""
        etf_currency_map = {
            "EWZ": "BRL",
            "EWW": "MXN",
            "INDA": "INR",
            "EZA": "ZAR",
            "TUR": "TRY",
            "ILF": "CLP",
            "EPOL": "PLN",
            "VWO": "IDR",
            "THD": "THB",
        }
        
        return etf_currency_map.get(etf_symbol)
    
    def execute_rebalance(self, target_allocations: Dict[str, float]):
        """Execute portfolio rebalancing"""
        self.log(f"Executing rebalance with targets: {target_allocations}")
        
        # Get current positions
        current_positions = self.executor.get_positions()
        
        # Execute rebalance
        results = self.executor.rebalance_portfolio(
            target_allocations=target_allocations,
            total_value=self.portfolio_value,
        )
        
        # Record rebalance
        self.rebalance_history.append({
            "timestamp": datetime.now().isoformat(),
            "targets": target_allocations,
            "results": results,
        })
        
        self.log(f"Rebalance complete: {len(results)} orders executed")
        
        return results
    
    def print_status(self, market_data: Dict, signals: List[Dict]):
        """Print current status"""
        print("\n" + "=" * 70)
        print(f"  CARRY TRADE PORTFOLIO STATUS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        
        # Top signals
        print("\n  TOP OPPORTUNITIES:")
        print("  " + "-" * 60)
        
        for signal in signals[:5]:
            marker = "[BUY]" if signal["signal"] in ["strong_buy", "buy"] else "[SELL]" if signal["signal"] in ["sell", "weak_sell"] else "[HOLD]"
            print(f"    {marker} {signal['currency']}: Spread {signal['spread']:+6.2f}% (Signal: {signal['signal']})")
        
        # Portfolio value
        print("\n  PORTFOLIO:")
        print("  " + "-" * 60)
        
        account = self.executor.get_account()
        if account:
            print(f"    Value: ${account['portfolio_value']:,.2f}")
            print(f"    Buying Power: ${account['buying_power']:,.2f}")
        
        positions = self.executor.get_positions()
        print(f"    Positions: {len(positions)}")
        
        for pos in positions:
            pnl = pos['unrealized_plpc'] * 100
            print(f"      {pos['symbol']}: ${pos['market_value']:,.2f} ({pnl:+.2f}%)")
        
        print("\n" + "=" * 70)
    
    def run_once(self):
        """Run one iteration of the main loop"""
        self.log("Starting iteration...")
        
        # Fetch market data
        market_data = self.fetch_market_data()
        
        # Generate signals
        signals = self.generate_signals(market_data)
        
        # Check if rebalance is needed
        current_positions = self.executor.get_positions()
        needs_rebalance, target_allocations = self.check_rebalance_needed(
            signals, current_positions
        )
        
        # Print status
        self.print_status(market_data, signals)
        
        # Execute rebalance if needed
        if needs_rebalance:
            self.log("Rebalance needed!")
            
            if self.execute_trades:
                self.execute_rebalance(target_allocations)
            else:
                self.log("Dry run mode - no trades executed")
        
        # Save snapshot
        self._save_snapshot(market_data, signals, needs_rebalance, target_allocations)
        
        # Add to history
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "market_data": market_data,
            "signals": signals,
            "needs_rebalance": needs_rebalance,
        })
        
        self.log("Iteration complete")
    
    def _save_snapshot(
        self,
        market_data: Dict,
        signals: List[Dict],
        needs_rebalance: bool,
        target_allocations: Dict,
    ):
        """Save snapshot to file"""
        filename = self.log_dir / f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "market_data": {
                    "fx_rates": market_data["fx_rates"],
                },
                "signals": signals,
                "needs_rebalance": needs_rebalance,
                "target_allocations": target_allocations,
            }, f, indent=2)
        
        self.log(f"Snapshot saved to {filename}")
    
    def run_continuous(self):
        """Run continuous monitoring loop"""
        self.log(f"Starting continuous loop (interval: {self.interval}s)")
        print("\nPress Ctrl+C to stop\n")
        
        try:
            while True:
                self.run_once()
                
                self.log(f"Next iteration in {self.interval} seconds...")
                time.sleep(self.interval)
                
        except KeyboardInterrupt:
            self.log("Loop stopped by user")
            print("\nLoop stopped.")
    
    def close(self):
        """Close all connections"""
        self.rates_provider.close()
        self.fx_provider.close()
        self.executor.close()


def main():
    parser = argparse.ArgumentParser(description="Carry Trade Portfolio Main Loop")
    parser.add_argument("--interval", type=int, default=300, help="Loop interval in seconds")
    parser.add_argument("--execute", action="store_true", help="Enable trade execution")
    parser.add_argument("--portfolio-value", type=float, default=100000.0, help="Portfolio value")
    
    args = parser.parse_args()
    
    loop = CarryTradeMainLoop(
        interval_seconds=args.interval,
        execute_trades=args.execute,
        portfolio_value=args.portfolio_value,
    )
    
    try:
        loop.run_continuous()
    finally:
        loop.close()


if __name__ == "__main__":
    main()
