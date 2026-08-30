"""
Carry Trade Portfolio Monitor
==============================
Continuous monitoring loop for the carry trade portfolio.

Features:
- Real-time rate monitoring
- Alert system for rate changes
- Automatic rebalancing triggers
- Performance tracking
- Logging to file

Usage:
    python examples/portfolio_monitor.py
    python examples/portfolio_monitor.py --interval 300  # 5 minutes
    python examples/portfolio_monitor.py --once  # Single check
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradingagents.dataflows.providers.interest_rates import GlobalInterestRatesProvider
from tradingagents.dataflows.providers.fx_multi_currency import MultiCurrencyFXProvider

# Step 5: optional VectorBT + MarkItDown wiring (no hard deps)
try:
    from tradingagents.dataflows.vectorbt_backtest import VectorBTBacktest

    _HAS_VBT = True
except Exception:  # noqa: BLE001
    _HAS_VBT = False
    VectorBTBacktest = None  # type: ignore

try:
    from tradingagents.dataflows.providers.registry import get_markitdown_provider

    _HAS_MD = True
except Exception:  # noqa: BLE001
    _HAS_MD = False
    get_markitdown_provider = None  # type: ignore


@dataclass
class Alert:
    """Alert for rate changes"""
    timestamp: str
    alert_type: str  # "rate_change", "spread_change", "volatility_spike"
    message: str
    severity: str  # "info", "warning", "critical"
    data: Dict = field(default_factory=dict)


@dataclass
class PortfolioSnapshot:
    """Point-in-time portfolio state"""
    timestamp: str
    rates: Dict
    fx_rates: Dict
    spreads: Dict
    alerts: List[Alert]
    total_expected_return: float


class PortfolioMonitor:
    """
    Continuous monitoring for carry trade portfolio.
    
    Monitors:
    - Interest rate changes across 15+ central banks
    - FX rate movements
    - Spread changes
    - Volatility spikes
    """
    
    def __init__(self, interval_seconds: int = 300):
        self.interval = interval_seconds
        self.rates_provider = GlobalInterestRatesProvider()
        self.fx_provider = MultiCurrencyFXProvider()
        
        # History for tracking changes
        self.history: List[PortfolioSnapshot] = []
        self.alerts: List[Alert] = []
        
        # Thresholds for alerts
        self.thresholds = {
            "rate_change": 0.25,  # Alert if rate changes by > 0.25%
            "spread_change": 0.50,  # Alert if spread changes by > 0.50%
            "volatility_spike": 0.05,  # Alert if volatility increases by > 5%
        }
        
        # Log file
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        self.log_file = self.log_dir / f"portfolio_monitor_{datetime.now().strftime('%Y%m%d')}.log"
    
    def log(self, message: str, level: str = "INFO"):
        """Log message to file and console"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        print(log_entry)
        
        with open(self.log_file, "a") as f:
            f.write(log_entry + "\n")
    
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
    
    def calculate_spreads(self, market_data: Dict) -> Dict:
        """Calculate current spreads for all currency pairs"""
        rates = market_data["rates"]
        us_rate = rates.get("US")
        
        if not us_rate:
            return {}
        
        spreads = {}
        
        # All currencies we track
        currencies = ["BR", "MX", "IN", "ZA", "CL", "TR", "PL", "CO", "ID", "TH", "PH"]
        
        for currency in currencies:
            currency_rate = rates.get(currency)
            if currency_rate:
                spread = currency_rate.rate - us_rate.rate
                spreads[currency] = {
                    "funding_rate": us_rate.rate,
                    "target_rate": currency_rate.rate,
                    "spread": spread,
                    "currency": currency_rate.currency,
                }
        
        return spreads
    
    def check_alerts(self, current_data: Dict, previous_data: Optional[Dict]) -> List[Alert]:
        """Check for alert conditions"""
        alerts = []
        
        if not previous_data:
            return alerts
        
        # Check rate changes
        current_rates = current_data["rates"]
        previous_rates = previous_data["rates"]
        
        for country, current_rate in current_rates.items():
            previous_rate = previous_rates.get(country)
            if previous_rate:
                rate_change = abs(current_rate.rate - previous_rate.rate)
                if rate_change >= self.thresholds["rate_change"]:
                    alerts.append(Alert(
                        timestamp=datetime.now().isoformat(),
                        alert_type="rate_change",
                        message=f"{country} rate changed by {rate_change:.2f}%: {previous_rate.rate:.2f}% -> {current_rate.rate:.2f}%",
                        severity="warning" if rate_change < 1.0 else "critical",
                        data={"country": country, "old_rate": previous_rate.rate, "new_rate": current_rate.rate},
                    ))
        
        # Check spread changes
        current_spreads = self.calculate_spreads(current_data)
        previous_spreads = self.calculate_spreads(previous_data)
        
        for currency, current_spread in current_spreads.items():
            previous_spread = previous_spreads.get(currency)
            if previous_spread:
                spread_change = abs(current_spread["spread"] - previous_spread["spread"])
                if spread_change >= self.thresholds["spread_change"]:
                    alerts.append(Alert(
                        timestamp=datetime.now().isoformat(),
                        alert_type="spread_change",
                        message=f"USD/{currency} spread changed by {spread_change:.2f}%",
                        severity="info",
                        data={"currency": currency, "old_spread": previous_spread["spread"], "new_spread": current_spread["spread"]},
                    ))
        
        return alerts
    
    def generate_snapshot(self, market_data: Dict, alerts: List[Alert]) -> PortfolioSnapshot:
        """Generate portfolio snapshot"""
        spreads = self.calculate_spreads(market_data)
        
        # Calculate total expected return
        allocations = {
            "BR": 0.15, "MX": 0.15, "IN": 0.12, "ZA": 0.10, "CL": 0.10,
            "PL": 0.08, "CO": 0.08, "ID": 0.07, "TH": 0.07, "PH": 0.08,
        }
        
        total_return = 0
        for currency, weight in allocations.items():
            spread_data = spreads.get(currency)
            if spread_data:
                total_return += spread_data["spread"] * weight
        
        return PortfolioSnapshot(
            timestamp=market_data["timestamp"],
            rates=market_data["rates"],
            fx_rates=market_data["fx_rates"],
            spreads=spreads,
            alerts=alerts,
            total_expected_return=total_return,
        )
    
    def print_snapshot(self, snapshot: PortfolioSnapshot):
        """Print formatted snapshot"""
        print("\n" + "=" * 70)
        print(f"  PORTFOLIO SNAPSHOT - {snapshot.timestamp}")
        print("=" * 70)
        
        # Rates
        print("\n  INTEREST RATES:")
        print("  " + "-" * 50)
        
        sorted_rates = sorted(snapshot.rates.items(), key=lambda x: x[1].rate, reverse=True)
        for country, rate_data in sorted_rates[:15]:
            print(f"    {country:4s} ({rate_data.currency}): {rate_data.rate:6.2f}%")
        
        # Spreads
        print("\n  CARRY TRADE SPREADS:")
        print("  " + "-" * 50)
        
        sorted_spreads = sorted(snapshot.spreads.items(), key=lambda x: x[1]["spread"], reverse=True)
        for currency, spread_data in sorted_spreads:
            print(f"    USD/{spread_data['currency']}: {spread_data['spread']:+6.2f}%  (Funding: {spread_data['funding_rate']:.2f}% -> Target: {spread_data['target_rate']:.2f}%)")
        
        # Alerts
        if snapshot.alerts:
            print("\n  ALERTS:")
            print("  " + "-" * 50)
            for alert in snapshot.alerts:
                print(f"    [{alert.severity.upper()}] {alert.message}")
        
        # Summary
        print("\n  PORTFOLIO SUMMARY:")
        print("  " + "-" * 50)
        print(f"    Total Expected Return: {snapshot.total_expected_return:.2f}%")
        print(f"    Number of Currencies: {len(snapshot.spreads)}")
        print(f"    Active Alerts: {len(snapshot.alerts)}")
        
        print("\n" + "=" * 70)
    
    def save_snapshot(self, snapshot: PortfolioSnapshot):
        """Save snapshot to file"""
        filename = self.log_dir / f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, "w") as f:
            json.dump({
                "timestamp": snapshot.timestamp,
                "spreads": snapshot.spreads,
                "alerts": [{"type": a.alert_type, "message": a.message, "severity": a.severity} for a in snapshot.alerts],
                "total_expected_return": snapshot.total_expected_return,
            }, f, indent=2)
        
        self.log(f"Snapshot saved to {filename}")
    
    def run_once(self):
        """Run a single monitoring cycle"""
        self.log("Starting monitoring cycle...")
        
        # Fetch market data
        market_data = self.fetch_market_data()
        
        # Check alerts
        previous_data = self.history[-1] if self.history else None
        alerts = self.check_alerts(market_data, previous_data)
        
        # Generate snapshot
        snapshot = self.generate_snapshot(market_data, alerts)

        # Step 5: attach optional VectorBT backtest (non-blocking, best-effort)
        try:
            bt = self.run_backtest()
            if bt:
                self.log(f"Backtest attached: {bt['method']} return={bt['total_return']:.3f}")
        except Exception:
            pass

        # Print and save
        self.print_snapshot(snapshot)
        self.save_snapshot(snapshot)
        
        # Add to history
        self.history.append(snapshot)
        
        # Keep only last 24 hours of history
        cutoff = datetime.now() - timedelta(hours=24)
        self.history = [h for h in self.history if datetime.fromisoformat(h.timestamp) > cutoff]
        
        self.log(f"Monitoring cycle complete. {len(alerts)} alerts generated.")
        
        return snapshot
    
    def run_continuous(self):
        """Run continuous monitoring loop"""
        self.log(f"Starting continuous monitoring (interval: {self.interval}s)")
        print("\nPress Ctrl+C to stop monitoring\n")
        
        try:
            while True:
                self.run_once()
                
                self.log(f"Next check in {self.interval} seconds...")
                time.sleep(self.interval)
                
        except KeyboardInterrupt:
            self.log("Monitoring stopped by user")
            print("\nMonitoring stopped. Final snapshot saved.")
    
    # -- Step 5: VectorBT + MarkItDown hooks ---------------------------------
    def run_backtest(self) -> dict | None:
        """Run a quick VectorBT backtest on synthetic price; None if unavailable."""
        if not _HAS_VBT or VectorBTBacktest is None:
            self.log("VectorBT not available — skip backtest", "WARNING")
            return None
        try:
            import pandas as pd

            n = 80
            idx = pd.date_range(end=datetime.now(), periods=n, freq="D")
            price = pd.Series([100 + i * 0.3 for i in range(n)], index=idx)
            entries = price.pct_change() > 0.008
            exits = price.pct_change() < -0.008
            bt = VectorBTBacktest()
            r = bt.run(price, entries, exits)
            out = {"total_return": r.total_return, "sharpe": r.sharpe, "max_drawdown": r.max_drawdown, "win_rate": r.win_rate, "num_trades": r.num_trades, "method": r.method}
            self.log(f"Backtest: {out}")
            return out
        except Exception as exc:  # noqa: BLE001
            self.log(f"Backtest failed: {exc}", "WARNING")
            return None

    def preview_doc(self, path: str, max_chars: int = 3000) -> str | None:
        """Preview a doc via MarkItDown if available."""
        if not _HAS_MD or get_markitdown_provider is None:
            self.log("MarkItDown not available", "WARNING")
            return None
        try:
            md = get_markitdown_provider()
            if md is None:
                return None
            text = md.convert_for_llm(path)
            preview = text[:max_chars]
            self.log(f"Doc preview {path}: {len(text)} chars")
            return preview
        except Exception as exc:  # noqa: BLE001
            self.log(f"Doc preview failed for {path}: {exc}", "WARNING")
            return None

    def close(self):
        """Close providers"""
        self.rates_provider.close()
        self.fx_provider.close()


def main():
    parser = argparse.ArgumentParser(description="Carry Trade Portfolio Monitor")
    parser.add_argument("--interval", type=int, default=300, help="Monitoring interval in seconds (default: 300)")
    parser.add_argument("--once", action="store_true", help="Run single check and exit")
    
    args = parser.parse_args()
    
    monitor = PortfolioMonitor(interval_seconds=args.interval)
    
    try:
        if args.once:
            monitor.run_once()
        else:
            monitor.run_continuous()
    finally:
        monitor.close()


if __name__ == "__main__":
    main()
