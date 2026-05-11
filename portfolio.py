import json
import os
from datetime import datetime


class Portfolio:
    def __init__(self):
        self.cash: float = 100_000.0
        self.positions: dict = {}   # ticker -> {"shares": float, "avg_cost": float}
        self.trades: list = []

    def load(self, path: str = "portfolio.json") -> None:
        if not os.path.exists(path):
            self.cash = 100_000.0
            self.positions = {}
            self.trades = []
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.cash = float(data.get("cash", 100_000.0))
        self.positions = data.get("positions", {})
        self.trades = data.get("trades", [])

    def save(self, path: str = "portfolio.json") -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"cash": self.cash, "positions": self.positions, "trades": self.trades},
                f, indent=2,
            )
        os.replace(tmp, path)

    def buy(self, ticker: str, amount_usd: float, price: float) -> dict:
        shares = amount_usd / price
        if ticker in self.positions:
            pos = self.positions[ticker]
            total_shares = pos["shares"] + shares
            new_avg = (pos["shares"] * pos["avg_cost"] + shares * price) / total_shares
            self.positions[ticker] = {"shares": total_shares, "avg_cost": round(new_avg, 4)}
        else:
            self.positions[ticker] = {"shares": shares, "avg_cost": round(price, 4)}
        self.cash -= amount_usd
        self.trades.append({
            "ticker": ticker, "side": "BUY",
            "shares": round(shares, 6), "price": round(price, 4),
            "amount": round(amount_usd, 2),
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        })
        return dict(self.positions[ticker])

    def sell(self, ticker: str, amount_usd: float, price: float) -> dict:
        pos = self.positions[ticker]
        shares_to_sell = min(amount_usd / price, pos["shares"])
        actual_amount = shares_to_sell * price
        remaining = pos["shares"] - shares_to_sell
        if remaining < 1e-9:
            del self.positions[ticker]
        else:
            self.positions[ticker] = {"shares": remaining, "avg_cost": pos["avg_cost"]}
        self.cash += actual_amount
        self.trades.append({
            "ticker": ticker, "side": "SELL",
            "shares": round(shares_to_sell, 6), "price": round(price, 4),
            "amount": round(actual_amount, 2),
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        })
        return {"shares_sold": round(shares_to_sell, 6), "actual_amount": round(actual_amount, 2)}

    def get_state(self, prices: dict) -> dict:
        positions_out = {}
        total_positions_value = 0.0
        for ticker, pos in self.positions.items():
            current_price = prices.get(ticker, pos["avg_cost"])
            unrealised_pnl = (current_price - pos["avg_cost"]) * pos["shares"]
            cost_basis = pos["avg_cost"] * pos["shares"]
            unrealised_pnl_pct = (unrealised_pnl / cost_basis * 100) if cost_basis else 0.0
            total_positions_value += current_price * pos["shares"]
            positions_out[ticker] = {
                "shares": pos["shares"],
                "avg_cost": pos["avg_cost"],
                "current_price": round(current_price, 4),
                "unrealised_pnl": round(unrealised_pnl, 2),
                "unrealised_pnl_pct": round(unrealised_pnl_pct, 2),
            }
        return {
            "cash": round(self.cash, 2),
            "positions": positions_out,
            "total_value": round(self.cash + total_positions_value, 2),
        }
