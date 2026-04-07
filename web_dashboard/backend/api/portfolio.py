"""
Portfolio API — 自选股、持仓、每日建议
"""
import asyncio
import fcntl
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import yfinance

# Data directory
DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

WATCHLIST_FILE = DATA_DIR / "watchlist.json"
POSITIONS_FILE = DATA_DIR / "positions.json"
RECOMMENDATIONS_DIR = DATA_DIR / "recommendations"
WATCHLIST_LOCK = DATA_DIR / "watchlist.lock"
POSITIONS_LOCK = DATA_DIR / "positions.lock"


# ============== Watchlist ==============

def get_watchlist() -> list:
    if not WATCHLIST_FILE.exists():
        return []
    try:
        with open(WATCHLIST_LOCK, "w") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_SH)
            try:
                return json.loads(WATCHLIST_FILE.read_text()).get("watchlist", [])
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    except Exception:
        return []


def _save_watchlist(watchlist: list):
    with open(WATCHLIST_LOCK, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            WATCHLIST_FILE.write_text(json.dumps({"watchlist": watchlist}, ensure_ascii=False, indent=2))
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def add_to_watchlist(ticker: str, name: str) -> dict:
    with open(WATCHLIST_LOCK, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            watchlist = json.loads(WATCHLIST_FILE.read_text()).get("watchlist", []) if WATCHLIST_FILE.exists() else []
            if any(s["ticker"] == ticker for s in watchlist):
                raise ValueError(f"{ticker} 已在自选股中")
            entry = {
                "ticker": ticker,
                "name": name,
                "added_at": datetime.now().strftime("%Y-%m-%d"),
            }
            watchlist.append(entry)
            WATCHLIST_FILE.write_text(json.dumps({"watchlist": watchlist}, ensure_ascii=False, indent=2))
            return entry
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def remove_from_watchlist(ticker: str) -> bool:
    with open(WATCHLIST_LOCK, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            watchlist = json.loads(WATCHLIST_FILE.read_text()).get("watchlist", []) if WATCHLIST_FILE.exists() else []
            new_list = [s for s in watchlist if s["ticker"] != ticker]
            if len(new_list) == len(watchlist):
                return False
            WATCHLIST_FILE.write_text(json.dumps({"watchlist": new_list}, ensure_ascii=False, indent=2))
            return True
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


# ============== Accounts ==============

def get_accounts() -> dict:
    if not POSITIONS_FILE.exists():
        return {"accounts": {}}
    try:
        with open(POSITIONS_LOCK, "w") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_SH)
            try:
                return json.loads(POSITIONS_FILE.read_text())
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    except Exception:
        return {"accounts": {}}


def _save_accounts(data: dict):
    with open(POSITIONS_LOCK, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            POSITIONS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def create_account(account_name: str) -> dict:
    with open(POSITIONS_LOCK, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            accounts = json.loads(POSITIONS_FILE.read_text()) if POSITIONS_FILE.exists() else {"accounts": {}}
            if account_name in accounts.get("accounts", {}):
                raise ValueError(f"账户 {account_name} 已存在")
            accounts["accounts"][account_name] = {"positions": {}}
            POSITIONS_FILE.write_text(json.dumps(accounts, ensure_ascii=False, indent=2))
            return {"account_name": account_name}
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def delete_account(account_name: str) -> bool:
    with open(POSITIONS_LOCK, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            accounts = json.loads(POSITIONS_FILE.read_text()) if POSITIONS_FILE.exists() else {"accounts": {}}
            if account_name not in accounts.get("accounts", {}):
                return False
            del accounts["accounts"][account_name]
            POSITIONS_FILE.write_text(json.dumps(accounts, ensure_ascii=False, indent=2))
            return True
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


# ============== Positions =============

# Semaphore to limit concurrent yfinance requests (avoid rate limiting)
_yfinance_semaphore: asyncio.Semaphore = asyncio.Semaphore(5)


def _fetch_price(ticker: str) -> float | None:
    """Fetch current price synchronously (called in thread executor)"""
    try:
        stock = yfinance.Ticker(ticker)
        info = stock.info or {}
        return info.get("currentPrice") or info.get("regularMarketPrice")
    except Exception:
        return None


async def _fetch_price_throttled(ticker: str) -> float | None:
    """Fetch price with semaphore throttling."""
    async with _yfinance_semaphore:
        return _fetch_price(ticker)


async def get_positions(account: Optional[str] = None) -> list:
    """
    Returns positions with live price from yfinance and computed P&L.
    Uses asyncio executor with concurrency limit (max 5 simultaneous requests).
    """
    accounts = get_accounts()

    if account:
        acc = accounts.get("accounts", {}).get(account)
        if not acc:
            return []
        positions = [(_ticker, _pos) for _ticker, _positions in acc.get("positions", {}).items()
                    for _pos in _positions]
    else:
        positions = [
            (_ticker, _pos)
            for _acc_data in accounts.get("accounts", {}).values()
            for _ticker, _positions in _acc_data.get("positions", {}).items()
            for _pos in _positions
        ]

    if not positions:
        return []

    tickers = [t for t, _ in positions]
    prices = await asyncio.gather(*[_fetch_price_throttled(t) for t in tickers])

    result = []
    for (ticker, pos), current_price in zip(positions, prices):
        shares = pos.get("shares", 0)
        cost_price = pos.get("cost_price", 0)
        unrealized_pnl = None
        unrealized_pnl_pct = None
        if current_price is not None and cost_price:
            unrealized_pnl = (current_price - cost_price) * shares
            unrealized_pnl_pct = (current_price / cost_price - 1) * 100

        result.append({
            "ticker": ticker,
            "name": pos.get("name", ticker),
            "account": pos.get("account", "默认账户"),
            "shares": shares,
            "cost_price": cost_price,
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "purchase_date": pos.get("purchase_date"),
            "notes": pos.get("notes", ""),
            "position_id": pos.get("position_id"),
        })
    return result


def add_position(ticker: str, shares: float, cost_price: float,
                 purchase_date: Optional[str], notes: str, account: str) -> dict:
    with open(POSITIONS_LOCK, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            accounts = json.loads(POSITIONS_FILE.read_text()) if POSITIONS_FILE.exists() else {"accounts": {}}
            acc = accounts.get("accounts", {}).get(account)
            if not acc:
                if "默认账户" not in accounts.get("accounts", {}):
                    accounts["accounts"]["默认账户"] = {"positions": {}}
                acc = accounts["accounts"]["默认账户"]

            position_id = f"pos_{uuid.uuid4().hex[:6]}"
            position = {
                "position_id": position_id,
                "shares": shares,
                "cost_price": cost_price,
                "purchase_date": purchase_date,
                "notes": notes,
                "account": account,
                "name": ticker,
            }

            if ticker not in acc["positions"]:
                acc["positions"][ticker] = []
            acc["positions"][ticker].append(position)
            POSITIONS_FILE.write_text(json.dumps(accounts, ensure_ascii=False, indent=2))
            return position
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def remove_position(ticker: str, position_id: str, account: Optional[str]) -> bool:
    with open(POSITIONS_LOCK, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            accounts = json.loads(POSITIONS_FILE.read_text()) if POSITIONS_FILE.exists() else {"accounts": {}}
            if account:
                acc = accounts.get("accounts", {}).get(account)
                if acc and ticker in acc.get("positions", {}):
                    acc["positions"][ticker] = [
                        p for p in acc["positions"][ticker]
                        if p.get("position_id") != position_id
                    ]
                    if not acc["positions"][ticker]:
                        del acc["positions"][ticker]
                    POSITIONS_FILE.write_text(json.dumps(accounts, ensure_ascii=False, indent=2))
                    return True
            else:
                for acc_data in accounts.get("accounts", {}).values():
                    if ticker in acc_data.get("positions", {}):
                        original_len = len(acc_data["positions"][ticker])
                        acc_data["positions"][ticker] = [
                            p for p in acc_data["positions"][ticker]
                            if p.get("position_id") != position_id
                        ]
                        if len(acc_data["positions"][ticker]) < original_len:
                            if not acc_data["positions"][ticker]:
                                del acc_data["positions"][ticker]
                            POSITIONS_FILE.write_text(json.dumps(accounts, ensure_ascii=False, indent=2))
                            return True
            return False
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


# ============== Recommendations ==============

def get_recommendations(date: Optional[str] = None) -> list:
    """List recommendations, optionally filtered by date."""
    RECOMMENDATIONS_DIR.mkdir(parents=True, exist_ok=True)
    if date:
        date_dir = RECOMMENDATIONS_DIR / date
        if not date_dir.exists():
            return []
        return [
            json.loads(f.read_text())
            for f in date_dir.glob("*.json")
            if f.suffix == ".json"
        ]
    else:
        # Return most recent first
        all_recs = []
        for date_dir in sorted(RECOMMENDATIONS_DIR.iterdir(), reverse=True):
            if date_dir.is_dir() and date_dir.name.startswith("20"):
                for f in date_dir.glob("*.json"):
                    if f.suffix == ".json":
                        all_recs.append(json.loads(f.read_text()))
        return all_recs


def get_recommendation(date: str, ticker: str) -> Optional[dict]:
    path = RECOMMENDATIONS_DIR / date / f"{ticker}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def save_recommendation(date: str, ticker: str, data: dict):
    date_dir = RECOMMENDATIONS_DIR / date
    date_dir.mkdir(parents=True, exist_ok=True)
    (date_dir / f"{ticker}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
