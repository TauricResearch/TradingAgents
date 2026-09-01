#!/usr/bin/env python3
"""
NIFTY 50 Live Options Trader with Broker Integration
Real-time trading with live market data and order execution
"""

import sys
import os
from datetime import datetime
from tradingagents.strategies import find_call_entry_points, find_put_entry_points
from tradingagents.brokers import get_broker, Order, MarketData


class NIFTY50Trader:
    """Main trading bot for NIFTY50 options."""
    
    def __init__(self, broker_type: str = "mock"):
        """
        Initialize trader.
        
        Args:
            broker_type: "mock", "zerodha", or other
        """
        self.broker = get_broker(broker_type)
        self.symbol = "NIFTY50"
        self.active_orders = {}
        self.trade_log = []
    
    def authenticate(self, credentials: dict = None):
        """Authenticate with broker."""
        if credentials is None:
            credentials = self._get_credentials()
        
        if not self.broker.authenticate(credentials):
            print("[ERROR] Authentication failed")
            sys.exit(1)
    
    def _get_credentials(self) -> dict:
        """Get broker credentials from environment or user input."""
        # Check environment variables first
        api_key = os.getenv("BROKER_API_KEY", "")
        access_token = os.getenv("BROKER_ACCESS_TOKEN", "")
        
        if not api_key or not access_token:
            print("\n[INFO] Broker credentials required")
            print("Set environment variables:")
            print("  export BROKER_API_KEY=<your_key>")
            print("  export BROKER_ACCESS_TOKEN=<your_token>")
            print("\nFor Zerodha: Get from https://kite.zerodha.com/")
            print("\nUsing MOCK broker for demo...")
            return {}
        
        return {
            "api_key": api_key,
            "access_token": access_token,
        }
    
    def fetch_market_data(self) -> MarketData:
        """Get current market data."""
        try:
            market_data = self.broker.get_market_data(self.symbol)
            print(f"\n[DATA] {self.symbol} - {market_data.timestamp}")
            print(f"       Price: {market_data.current_price:,.2f} (Bid: {market_data.bid:.2f}, Ask: {market_data.ask:.2f})")
            return market_data
        except Exception as e:
            print(f"[ERROR] Failed to fetch market data: {e}")
            sys.exit(1)
    
    def fetch_technicals(self) -> dict:
        """Calculate technical indicators."""
        try:
            technicals = self.broker.get_technicals(self.symbol)
            print(f"\n[TECH] RSI: {technicals.get('rsi', 'N/A'):.1f}")
            print(f"       ATR: {technicals.get('atr', 'N/A'):.2f}")
            print(f"       Support: {technicals.get('support', 'N/A'):,.2f}")
            print(f"       Resistance: {technicals.get('resistance', 'N/A'):,.2f}")
            print(f"       Volume: {technicals.get('volume_trend', 'N/A')}")
            return technicals
        except Exception as e:
            print(f"[ERROR] Failed to fetch technicals: {e}")
            sys.exit(1)
    
    def analyze_signals(self, market_data: MarketData, technicals: dict):
        """Analyze CALL and PUT signals."""
        print("\n" + "="*80)
        print("SIGNAL ANALYSIS")
        print("="*80)
        
        call_signal = find_call_entry_points(
            symbol=self.symbol,
            current_price=market_data.current_price,
            rsi=technicals.get('rsi', 50),
            support_level=technicals.get('support', market_data.low),
            resistance_level=technicals.get('resistance', market_data.high),
            atr=technicals.get('atr', 100),
            volume_trend=technicals.get('volume_trend', 'neutral')
        )
        
        put_signal = find_put_entry_points(
            symbol=self.symbol,
            current_price=market_data.current_price,
            rsi=technicals.get('rsi', 50),
            support_level=technicals.get('support', market_data.low),
            resistance_level=technicals.get('resistance', market_data.high),
            atr=technicals.get('atr', 100),
            volume_trend=technicals.get('volume_trend', 'neutral')
        )
        
        print("\n[CALL] BULLISH SIGNAL")
        print("-" * 80)
        print(call_signal)
        
        print("\n[PUT] BEARISH SIGNAL")
        print("-" * 80)
        print(put_signal)
        
        # Extract confidence scores
        call_conf = float(call_signal.split("Confidence Score: ")[1].split("%")[0])
        put_conf = float(put_signal.split("Confidence Score: ")[1].split("%")[0])
        
        return {
            "call_signal": call_signal,
            "call_confidence": call_conf,
            "put_signal": put_signal,
            "put_confidence": put_conf,
        }
    
    def should_execute_trade(self, signals: dict) -> tuple:
        """Determine if should execute a trade."""
        call_conf = signals['call_confidence']
        put_conf = signals['put_confidence']
        
        if call_conf > 75:
            return ("CALL", "BUY", call_conf)
        elif put_conf > 75:
            return ("PUT", "SELL", put_conf)
        else:
            return (None, None, None)
    
    def execute_trade(self, option_type: str, action: str, confidence: float, market_data: MarketData, technicals: dict):
        """Execute a trade order."""
        print("\n" + "="*80)
        print("EXECUTING TRADE")
        print("="*80)
        
        # Calculate entry, stop, target
        if option_type == "CALL":
            entry = technicals['support'] + (technicals['atr'] * 0.5)
            stop = technicals['support'] - (technicals['atr'] * 1.0)
            target = technicals['resistance']
        else:
            entry = technicals['resistance'] - (technicals['atr'] * 0.5)
            stop = technicals['resistance'] + (technicals['atr'] * 1.0)
            target = technicals['support']
        
        # Create order
        quantity = 1  # 1 lot of NIFTY
        order = Order(
            symbol=self.symbol,
            option_type=option_type,
            action=action,
            quantity=quantity,
            price=entry,
            stop_loss=stop,
            target=target,
            expiry="1 week"
        )
        
        print(f"\n[ORDER] {action} {option_type}")
        print(f"        Confidence: {confidence:.1f}%")
        print(f"        Entry: {entry:,.2f}")
        print(f"        Stop Loss: {stop:,.2f}")
        print(f"        Target: {target:,.2f}")
        print(f"        Quantity: {quantity} lot")
        
        # Place order
        try:
            order_id = self.broker.place_order(order)
            self.active_orders[order_id] = order
            self.trade_log.append({
                "timestamp": datetime.now().isoformat(),
                "order_id": order_id,
                "type": option_type,
                "action": action,
                "entry": entry,
                "stop": stop,
                "target": target,
                "status": "PLACED",
            })
            return order_id
        except Exception as e:
            print(f"[ERROR] Failed to place order: {e}")
            return None
    
    def monitor_positions(self):
        """Monitor active positions."""
        if not self.active_orders:
            print("\n[INFO] No active positions")
            return
        
        print("\n" + "="*80)
        print("ACTIVE POSITIONS")
        print("="*80)
        
        for order_id, order in self.active_orders.items():
            try:
                status = self.broker.get_order_status(order_id)
                print(f"\n[{order_id}] {order.option_type} {order.action}")
                print(f"         Entry: {order.price:,.2f}")
                print(f"         Stop: {order.stop_loss:,.2f}")
                print(f"         Target: {order.target:,.2f}")
                if status:
                    print(f"         Status: {status.get('status', 'UNKNOWN')}")
            except Exception as e:
                print(f"[ERROR] Failed to get status for {order_id}: {e}")
    
    def run_once(self):
        """Run single analysis and trade cycle."""
        print("\n" + "="*80)
        print("NIFTY 50 OPTIONS TRADER - START")
        print("="*80)
        
        # Get market data
        market_data = self.fetch_market_data()
        technicals = self.fetch_technicals()
        
        # Analyze signals
        signals = self.analyze_signals(market_data, technicals)
        
        # Check if should trade
        option_type, action, confidence = self.should_execute_trade(signals)
        
        if option_type:
            print(f"\n[SIGNAL] Strong {option_type} signal: {confidence:.1f}%")
            order_id = self.execute_trade(option_type, action, confidence, market_data, technicals)
            if order_id:
                print(f"[OK] Trade executed: {order_id}")
        else:
            print("\n[WAIT] No clear signal (need >75% confidence)")
        
        # Monitor positions
        self.monitor_positions()
        
        # Print trade log
        if self.trade_log:
            print("\n" + "="*80)
            print("TRADE LOG")
            print("="*80)
            for trade in self.trade_log:
                print(f"\n[{trade['timestamp']}]")
                print(f"  Order: {trade['order_id']}")
                print(f"  Type: {trade['type']} {trade['action']}")
                print(f"  Entry: {trade['entry']:,.2f} | Stop: {trade['stop']:,.2f} | Target: {trade['target']:,.2f}")
        
        print("\n" + "="*80)
        print("DISCLAIMERS")
        print("="*80)
        print("""
[!] This is educational software only
[!] Not financial advice - trade at your own risk
[!] Always verify signals before executing
[!] Use proper stop losses and position sizing
[!] Trade only with capital you can afford to lose
[!] Consult a financial advisor before trading
""")
        print("="*80 + "\n")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="NIFTY 50 Options Trader")
    parser.add_argument("--broker", default="mock", help="Broker: mock, zerodha")
    parser.add_argument("--api-key", help="Broker API key")
    parser.add_argument("--access-token", help="Broker access token")
    args = parser.parse_args()
    
    try:
        # Create trader
        trader = NIFTY50Trader(broker_type=args.broker)
        
        # Authenticate
        credentials = {}
        if args.api_key and args.access_token:
            credentials = {
                "api_key": args.api_key,
                "access_token": args.access_token,
            }
        trader.authenticate(credentials)
        
        # Run trading cycle
        trader.run_once()
        
    except KeyboardInterrupt:
        print("\n[EXIT] Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n[FATAL] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
