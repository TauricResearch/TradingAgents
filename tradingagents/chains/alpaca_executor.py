"""
Carry Trade Portfolio Executor
===============================
Executes carry trade portfolio positions on Alpaca Paper Trading.

Features:
- Buy and hold ETF positions for carry trade currencies
- Automatic rebalancing based on portfolio manager signals
- Position sizing based on risk parameters
- Paper trading mode with real market data

Supported ETFs:
- BRL: EWZ (Brazil), BRAQ (Brazil)
- TRY: TUR (Turkey)
- MXN: EWW (Mexico)
- INR: INDA (India), PIN (India)
- ZAR: EZA (South Africa)
- CLP: (no direct ETF - use CLP futures or skip)
- PLN: (no direct ETF - use PLN futures or skip)
- COP: (no direct ETF - use COP futures or skip)
- IDR: (no direct ETF - use IDR futures or skip)
- THB: (no direct ETF - use THB futures or skip)
- PHP: (no direct ETF - use PHP futures or skip)

Usage:
    from tradingagents.chains.alpaca_executor import CarryTradeExecutor
    
    executor = CarryTradeExecutor(dry_run=False)
    executor.execute_portfolio(portfolio)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient


@dataclass
class Position:
    """Position in the carry trade portfolio"""
    symbol: str
    currency: str
    side: str  # "long" or "short"
    quantity: float
    notional: float
    entry_price: float
    current_price: float
    pnl: float
    pnl_pct: float
    allocation_pct: float
    expected_return: float
    risk_level: str


@dataclass
class ExecutionOrder:
    """Order to execute"""
    symbol: str
    side: OrderSide
    quantity: Optional[float]
    notional: Optional[float]
    order_type: str
    time_in_force: TimeInForce
    limit_price: Optional[float] = None
    currency: str = ""
    strategy: str = ""


class CarryTradeExecutor:
    """
    Execute carry trade portfolio positions on Alpaca Paper Trading.
    
    This executor translates portfolio signals into actual orders.
    """
    
    # Mapping from currency to tradeable ETFs
    CURRENCY_ETF_MAP = {
        "BRL": {"symbol": "EWZ", "name": "iShares MSCI Brazil ETF"},
        "MXN": {"symbol": "EWW", "name": "iShares MSCI Mexico ETF"},
        "INR": {"symbol": "INDA", "name": "iShares MSCI India ETF"},
        "ZAR": {"symbol": "EZA", "name": "iShares MSCI South Africa ETF"},
        "TRY": {"symbol": "TUR", "name": "iShares MSCI Turkey ETF"},
        "CLP": {"symbol": "ILF", "name": "iShares Latin America 40 ETF"},
        "PLN": {"symbol": "EPOL", "name": "iShares MSCI Poland ETF"},
        "COP": {"symbol": "ILF", "name": "iShares Latin America 40 ETF"},
        "IDR": {"symbol": "VWO", "name": "Vanguard FTSE Emerging Markets ETF"},
        "THB": {"symbol": "THD", "name": "iShares MSCI Thailand ETF"},
        "PHP": {"symbol": "VWO", "name": "Vanguard FTSE Emerging Markets ETF"},
    }
    
    def __init__(self, dry_run: bool = True, use_paper: bool = True):
        """
        Initialize Alpaca executor.
        
        Args:
            dry_run: If True, simulate execution without real orders
            use_paper: If True, use paper trading account
        """
        self.dry_run = dry_run
        self.use_paper = use_paper
        
        # Initialize Alpaca client
        api_key = os.getenv("ALPACA_PAPER_KEY")
        secret_key = os.getenv("ALPACA_PAPER_SECRET")
        
        if api_key and secret_key:
            self.client = TradingClient(
                api_key=api_key,
                secret_key=secret_key,
                paper=use_paper
            )
            self.data_client = StockHistoricalDataClient(api_key, secret_key)
            print("[OK] Connected to Alpaca Paper Trading")
        else:
            self.client = None
            self.data_client = None
            print("[WARN] Alpaca API keys not found - running in dry_run mode")
            self.dry_run = True
    
    def get_account(self) -> Optional[Dict]:
        """Get account information"""
        if not self.client:
            return None
        
        try:
            account = self.client.get_account()
            return {
                "portfolio_value": float(account.portfolio_value),
                "buying_power": float(account.buying_power),
                "cash": float(account.cash),
                "equity": float(account.equity),
                "status": account.status,
            }
        except Exception as e:
            print(f"Error getting account: {e}")
            return None
    
    def get_positions(self) -> List[Dict]:
        """Get current positions"""
        if not self.client:
            return []
        
        try:
            positions = self.client.get_all_positions()
            return [
                {
                    "symbol": pos.symbol,
                    "quantity": float(pos.qty),
                    "market_value": float(pos.market_value),
                    "avg_entry_price": float(pos.avg_entry_price),
                    "current_price": float(pos.current_price),
                    "unrealized_pl": float(pos.unrealized_pl),
                    "unrealized_plpc": float(pos.unrealized_plpc),
                    "side": pos.side,
                }
                for pos in positions
            ]
        except Exception as e:
            print(f"Error getting positions: {e}")
            return []
    
    def get_quote(self, symbol: str) -> Optional[Dict]:
        """Get latest quote for a symbol"""
        if not self.data_client:
            return None
        
        try:
            from alpaca.data.requests import StockLatestQuoteRequest
            
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quote = self.data_client.get_stock_latest_quote(request)
            
            return {
                "symbol": symbol,
                "bid_price": float(quote.bid_price),
                "ask_price": float(quote.ask_price),
                "bid_size": quote.bid_size,
                "ask_size": quote.ask_size,
                "timestamp": quote.timestamp,
            }
        except Exception as e:
            print(f"Error getting quote for {symbol}: {e}")
            return None
    
    def create_market_order(
        self,
        symbol: str,
        side: OrderSide,
        notional: Optional[float] = None,
        quantity: Optional[float] = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
    ) -> ExecutionOrder:
        """Create a market order"""
        return ExecutionOrder(
            symbol=symbol,
            side=side,
            quantity=quantity,
            notional=notional,
            order_type="market",
            time_in_force=time_in_force,
        )
    
    def create_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        limit_price: float,
        quantity: Optional[float] = None,
        notional: Optional[float] = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
    ) -> ExecutionOrder:
        """Create a limit order"""
        return ExecutionOrder(
            symbol=symbol,
            side=side,
            quantity=quantity,
            notional=notional,
            order_type="limit",
            time_in_force=time_in_force,
            limit_price=limit_price,
        )
    
    def execute_order(self, order: ExecutionOrder) -> Optional[Dict]:
        """Execute an order"""
        if self.dry_run:
            print(f"  [DRY RUN] Would execute: {order.side.value} {order.symbol}")
            if order.notional:
                print(f"    Notional: ${order.notional:.2f}")
            if order.quantity:
                print(f"    Quantity: {order.quantity}")
            return {"status": "dry_run", "order": order}
        
        if not self.client:
            print(f"  ❌ No Alpaca client available")
            return None
        
        try:
            if order.order_type == "market":
                request = MarketOrderRequest(
                    symbol=order.symbol,
                    side=order.side,
                    time_in_force=order.time_in_force,
                    notional=order.notional,
                    qty=order.quantity,
                )
            elif order.order_type == "limit":
                request = LimitOrderRequest(
                    symbol=order.symbol,
                    side=order.side,
                    time_in_force=order.time_in_force,
                    limit_price=order.limit_price,
                    notional=order.notional,
                    qty=order.quantity,
                )
            else:
                print(f"  ❌ Unknown order type: {order.order_type}")
                return None
            
            submitted_order = self.client.submit_order(request)
            
            return {
                "status": "submitted",
                "order_id": str(submitted_order.id),
                "symbol": submitted_order.symbol,
                "side": submitted_order.side,
                "qty": submitted_order.qty,
                "notional": submitted_order.notional,
                "type": submitted_order.type,
                "limit_price": submitted_order.limit_price,
                "submitted_at": str(submitted_order.submitted_at),
            }
        except Exception as e:
            print(f"  ❌ Error executing order: {e}")
            return None
    
    def rebalance_portfolio(
        self,
        target_allocations: Dict[str, float],
        total_value: float,
        risk_params: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Rebalance portfolio to match target allocations.
        
        Args:
            target_allocations: Dict mapping symbols to target allocation percentages
            total_value: Total portfolio value
            risk_params: Optional risk parameters
            
        Returns:
            List of execution results
        """
        print("\n" + "=" * 60)
        print("REBALANCING PORTFOLIO")
        print("=" * 60)
        
        results = []
        current_positions = self.get_positions()
        
        # Get current portfolio value
        if not self.dry_run and self.client:
            account = self.get_account()
            if account:
                total_value = account["portfolio_value"]
        
        print(f"Total Portfolio Value: ${total_value:,.2f}")
        print(f"Target Allocations: {target_allocations}")
        
        # Calculate target notional for each position
        target_notional = {}
        for symbol, allocation in target_allocations.items():
            target_notional[symbol] = total_value * allocation
        
        # Get current notional for each position
        current_notional = {}
        for pos in current_positions:
            current_notional[pos["symbol"]] = pos["market_value"]
        
        # Calculate required trades
        print("\nCalculating trades...")
        
        for symbol, target in target_notional.items():
            current = current_notional.get(symbol, 0)
            diff = target - current
            
            if abs(diff) < 100:  # Skip if difference is less than $100
                continue
            
            # Get current price
            quote = self.get_quote(symbol)
            if not quote:
                print(f"  ⚠️  Could not get quote for {symbol} - skipping")
                continue
            
            current_price = (quote["bid_price"] + quote["ask_price"]) / 2
            
            if diff > 0:
                # Need to buy
                side = OrderSide.BUY
                notional = diff
                print(f"  BUY {symbol}: ${notional:,.2f} (target: ${target:,.2f}, current: ${current:,.2f})")
            else:
                # Need to sell
                side = OrderSide.SELL
                notional = abs(diff)
                print(f"  SELL {symbol}: ${notional:,.2f} (target: ${target:,.2f}, current: ${current:,.2f})")
            
            # Create and execute order
            order = self.create_market_order(
                symbol=symbol,
                side=side,
                notional=notional,
            )
            
            result = self.execute_order(order)
            if result:
                results.append(result)
        
        # Handle positions not in target allocations
        for pos in current_positions:
            if pos["symbol"] not in target_allocations:
                print(f"  SELL {pos['symbol']}: ${pos['market_value']:,.2f} (not in target allocations)")
                
                order = self.create_market_order(
                    symbol=pos["symbol"],
                    side=OrderSide.SELL,
                    notional=pos["market_value"],
                )
                
                result = self.execute_order(order)
                if result:
                    results.append(result)
        
        print(f"\nRebalancing complete: {len(results)} orders executed")
        return results
    
    def execute_carry_trade_strategy(
        self,
        strategy_name: str,
        currency_pairs: List[Tuple[str, str]],
        allocations: Dict[str, float],
        total_value: float,
    ) -> List[Dict]:
        """
        Execute a carry trade strategy.
        
        Args:
            strategy_name: Name of the strategy
            currency_pairs: List of (funding_currency, target_currency) tuples
            allocations: Dict mapping currencies to allocation percentages
            total_value: Total portfolio value
            
        Returns:
            List of execution results
        """
        print("\n" + "=" * 60)
        print(f"CARRY TRADE STRATEGY: {strategy_name}")
        print("=" * 60)
        
        results = []
        
        # Map currency pairs to ETFs
        etf_allocations = {}
        
        for funding_currency, target_currency in currency_pairs:
            if target_currency in self.CURRENCY_ETF_MAP:
                etf_info = self.CURRENCY_ETF_MAP[target_currency]
                symbol = etf_info["symbol"]
                
                # Add allocation
                if symbol in etf_allocations:
                    etf_allocations[symbol] += allocations.get(target_currency, 0)
                else:
                    etf_allocations[symbol] = allocations.get(target_currency, 0)
        
        # Rebalance to target allocations
        if etf_allocations:
            results = self.rebalance_portfolio(etf_allocations, total_value)
        
        return results
    
    def get_portfolio_summary(self) -> Dict:
        """Get current portfolio summary"""
        positions = self.get_positions()
        account = self.get_account()
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "account": account,
            "positions": positions,
            "total_positions": len(positions),
            "total_value": sum(pos["market_value"] for pos in positions),
            "total_pnl": sum(pos["unrealized_pl"] for pos in positions),
        }
        
        return summary
    
    def close(self):
        """Close client connections"""
        if self.client:
            self.client = None
        if self.data_client:
            self.data_client = None


def main():
    """Example usage of CarryTradeExecutor"""
    print("=" * 60)
    print("CARRY TRADE EXECUTOR - ALPACA PAPER TRADING")
    print("=" * 60)
    
    # Initialize executor
    executor = CarryTradeExecutor(dry_run=True, use_paper=True)
    
    # Get account info
    account = executor.get_account()
    if account:
        print(f"\nAccount Status: {account['status']}")
        print(f"Portfolio Value: ${account['portfolio_value']:,.2f}")
        print(f"Buying Power: ${account['buying_power']:,.2f}")
    else:
        print("\n⚠️  Could not get account info")
    
    # Get current positions
    positions = executor.get_positions()
    print(f"\nCurrent Positions: {len(positions)}")
    for pos in positions:
        print(f"  {pos['symbol']}: {pos['quantity']} @ ${pos['avg_entry_price']:.2f} -> ${pos['current_price']:.2f} ({pos['unrealized_plpc']:.2%})")
    
    # Example: Execute carry trade strategy
    print("\n" + "=" * 60)
    print("EXECUTING CARRY TRADE STRATEGY")
    print("=" * 60)
    
    # Conservative strategy: USD/BRL
    results = executor.execute_carry_trade_strategy(
        strategy_name="Conservative_USD_BRL",
        currency_pairs=[("USD", "BRL")],
        allocations={"BRL": 0.40},
        total_value=100000,
    )
    
    print(f"\nExecution results: {len(results)} orders")
    
    executor.close()


if __name__ == "__main__":
    main()
