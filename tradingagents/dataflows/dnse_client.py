"""DNSE Entrade X Open API client and Paper Trading simulation engine.

Supports:
1. Paper Trading (Giả lập giao dịch):
   - Simulates cash balance (default 10,000,000 VND).
   - Realtime price execution with statutory Vietnam 0.1% sell tax and 0.15% fee deduction.
   - Enforces 100-share lot size and short selling prohibition.
   - Local JSON persistence in user data directory.
2. DNSE Entrade X Production & Sandbox Open API:
   - Authentication (API Key / Bearer Token).
   - Market quotes, account balance, and order placement endpoints.
   - Rate limit and timeout protection.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from .vn_data import calculate_vn_trade_friction, normalize_vn_symbol

logger = logging.getLogger(__name__)

# Default paper trading file path
PAPER_TRADING_PATH = Path(os.path.expanduser("~")) / ".tradingagents" / "paper_trading_vn.json"


class PaperTradingEngine:
    """Simulated exchange engine adhering to Vietnamese market rules and tax laws."""

    def __init__(self, storage_path: Path | None = None, initial_cash: float = 10_000_000.0):
        self.storage_path = storage_path or PAPER_TRADING_PATH
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.initial_cash = initial_cash
        self.state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.warning("Could not read paper trading state: %s. Re-initializing.", exc)

        return {
            "cash": self.initial_cash,
            "portfolio": {},  # {symbol: {"quantity": int, "avg_price": float, "updated_at": str}}
            "history": [],    # list of order records
        }

    def _save_state(self) -> None:
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.error("Failed to save paper trading state: %s", exc)

    def get_summary(self) -> dict[str, Any]:
        return {
            "cash": self.state["cash"],
            "portfolio": self.state["portfolio"],
            "history_count": len(self.state["history"]),
        }

    def place_buy_order(self, symbol: str, price: float, quantity: int) -> dict[str, Any]:
        """Execute a simulated buy order with 100-share lot and 0.15% fee validation."""
        clean_symbol = normalize_vn_symbol(symbol)
        if quantity <= 0 or quantity % 100 != 0:
            return {"success": False, "message": f"Số lượng {quantity} không hợp lệ. Phải là lô chẵn 100 cổ phiếu."}

        fee_rate = 0.0015
        order_val = price * quantity
        fee = order_val * fee_rate
        total_required = order_val + fee

        if self.state["cash"] < total_required:
            return {
                "success": False,
                "message": f"Số dư không đủ. Cần {total_required:,.0f} đ (gồm phí), hiện có {self.state['cash']:,.0f} đ.",
            }

        # Deduct cash
        self.state["cash"] -= total_required

        # Update portfolio
        port = self.state["portfolio"]
        current = port.get(clean_symbol, {"quantity": 0, "avg_price": 0.0})
        old_qty = current.get("quantity", 0)
        old_avg = current.get("avg_price", 0.0)
        buy_date = current.get("buy_date") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        new_qty = old_qty + quantity
        new_avg = ((old_avg * old_qty) + order_val) / new_qty if new_qty > 0 else price

        port[clean_symbol] = {
            "quantity": new_qty,
            "avg_price": round(new_avg, 2),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "buy_date": buy_date,
        }

        order_record = {
            "id": f"PAPER-BUY-{int(datetime.now().timestamp())}",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": clean_symbol,
            "side": "BUY",
            "quantity": quantity,
            "price": price,
            "gross_value": order_val,
            "fee": fee,
            "tax": 0.0,
            "total_impact": -total_required,
        }
        self.state["history"].insert(0, order_record)
        self._save_state()

        return {"success": True, "message": f"Khớp lệnh MUA {quantity:,} cp {clean_symbol} giá {price:,.0f} đ.", "order": order_record}

    def place_sell_order(self, symbol: str, price: float, quantity: int) -> dict[str, Any]:
        """Execute a simulated sell order deducting 0.1% personal income tax and 0.15% brokerage fee."""
        clean_symbol = normalize_vn_symbol(symbol)
        if quantity <= 0 or quantity % 100 != 0:
            return {"success": False, "message": f"Số lượng {quantity} không hợp lệ. Phải là lô chẵn 100 cổ phiếu."}

        port = self.state["portfolio"]
        if clean_symbol not in port or port[clean_symbol]["quantity"] < quantity:
            avail = port.get(clean_symbol, {}).get("quantity", 0)
            return {
                "success": False,
                "message": f"Cấm bán khống! Bạn chỉ có {avail} cp {clean_symbol} khả dụng, không thể bán {quantity} cp.",
            }

        friction = calculate_vn_trade_friction(
            entry_price=port[clean_symbol]["avg_price"],
            exit_price=price,
            shares=quantity,
        )

        net_received = friction["net_proceeds"]
        self.state["cash"] += net_received

        # Update remaining quantity
        port[clean_symbol]["quantity"] -= quantity
        if port[clean_symbol]["quantity"] == 0:
            del port[clean_symbol]

        order_record = {
            "id": f"PAPER-SELL-{int(datetime.now().timestamp())}",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": clean_symbol,
            "side": "SELL",
            "quantity": quantity,
            "price": price,
            "gross_value": friction["sell_value"],
            "fee": friction["sell_fee"],
            "tax": friction["sell_tax"],
            "net_profit": friction["net_profit"],
            "total_impact": net_received,
        }
        self.state["history"].insert(0, order_record)
        self._save_state()

        return {
            "success": True,
            "message": f"Khớp lệnh BÁN {quantity:,} cp {clean_symbol} giá {price:,.0f} đ. Lãi/Lỗ ròng: {friction['net_profit']:+,.0f} đ.",
            "order": order_record,
        }

    def reset_account(self, new_cash: float = 10_000_000.0) -> None:
        self.state = {
            "cash": new_cash,
            "portfolio": {},
            "history": [],
        }
        self._save_state()


class DNSEClient:
    """Client for DNSE Entrade X Open API."""

    def __init__(
        self,
        account_no: str | None = None,
        api_key: str | None = None,
        secret_key: str | None = None,
        is_sandbox: bool = False,
    ):
        self.account_no = account_no or os.getenv("DNSE_ACCOUNT_NO", "")
        self.api_key = api_key or os.getenv("DNSE_API_KEY", "")
        self.secret_key = secret_key or os.getenv("DNSE_SECRET_KEY", "")
        self.base_url = "https://api-sandbox.dnse.com.vn" if is_sandbox else "https://api.dnse.com.vn"

    @property
    def is_configured(self) -> bool:
        return bool(self.account_no and self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "TradingAgentsVietnam/0.4.0",
        }

    def get_market_quote(self, symbol: str) -> dict[str, Any]:
        """Fetch market quote from DNSE."""
        raw_sym = symbol.split(".")[0] if "." in symbol else symbol
        url = f"{self.base_url}/market-data/v1/stocks/{raw_sym}/quotes"
        try:
            r = requests.get(url, headers=self._headers(), timeout=10)
            if r.status_code == 200:
                return r.json()
            return {"error": f"HTTP {r.status_code}: {r.text}"}
        except Exception as exc:
            return {"error": str(exc)}
