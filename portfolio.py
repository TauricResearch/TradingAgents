import json
import os
from datetime import datetime


class Portfolio:
    def __init__(self):
        self.cash: float = 100_000.0
        self.positions: dict = {}   # ticker -> {"shares": float, "avg_cost": float}
        self.trades: list = []
        self.day_start_value: float = 100_000.0
        self.day_start_date: str = datetime.now().strftime("%Y-%m-%d")

    def load(self, path: str = "portfolio.json") -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        if not os.path.exists(path):
            self.cash = 100_000.0
            self.positions = {}
            self.trades = []
            self.day_start_value = 100_000.0
            self.day_start_date = today
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.cash = float(data.get("cash", 100_000.0))
        self.positions = data.get("positions", {})
        self.trades = data.get("trades", [])
        self.day_start_value = float(data.get("day_start_value", 100_000.0))
        self.day_start_date = data.get("day_start_date", today)

    def save(self, path: str = "portfolio.json") -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "cash": self.cash,
                    "positions": self.positions,
                    "trades": self.trades,
                    "day_start_value": self.day_start_value,
                    "day_start_date": self.day_start_date,
                },
                f, indent=2,
            )
        os.replace(tmp, path)

    def check_day_reset(self, current_date: str) -> None:
        """If the date has rolled over, snapshot today's opening value."""
        if current_date != self.day_start_date:
            state = self.get_state({})  # uses avg_cost as price fallback
            self.day_start_value = state["total_value"]
            self.day_start_date = current_date
            self.save()

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
            mkt_value = current_price * pos["shares"]
            total_positions_value += mkt_value
            positions_out[ticker] = {
                "shares": pos["shares"],
                "avg_cost": pos["avg_cost"],
                "current_price": round(current_price, 4),
                "unrealised_pnl": round(unrealised_pnl, 2),
                "unrealised_pnl_pct": round(unrealised_pnl_pct, 2),
                "pct_of_portfolio": 0.0,  # filled in below once total_value is known
            }
        total_value = self.cash + total_positions_value
        # Fill pct_of_portfolio now that total_value is computed
        if total_value > 0:
            for ticker, pos_data in positions_out.items():
                mkt = pos_data["shares"] * pos_data["current_price"]
                pos_data["pct_of_portfolio"] = round(mkt / total_value * 100, 2)
        return {
            "cash": round(self.cash, 2),
            "positions": positions_out,
            "total_value": round(total_value, 2),
            "daily_pnl": round(total_value - self.day_start_value, 2),
        }
