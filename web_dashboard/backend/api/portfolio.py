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
MAX_CONCURRENT_YFINANCE_REQUESTS = 5
_yfinance_semaphore: asyncio.Semaphore = asyncio.Semaphore(MAX_CONCURRENT_YFINANCE_REQUESTS)


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
    if not position_id:
        return False  # Require explicit position_id to prevent mass deletion
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

# Pagination defaults (must match main.py constants)
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


def _rating_to_direction(rating: Optional[str]) -> int:
    if rating in {"BUY", "OVERWEIGHT"}:
        return 1
    if rating in {"SELL", "UNDERWEIGHT"}:
        return -1
    return 0


def _normalize_recommendation_record(record: dict, *, date: Optional[str] = None, ticker: Optional[str] = None) -> dict:
    normalized = dict(record)
    if "result" in normalized and "contract_version" in normalized:
        normalized.setdefault("ticker", ticker or normalized.get("ticker"))
        normalized.setdefault("date", date or normalized.get("date") or normalized.get("analysis_date"))
        return normalized

    decision = normalized.get("decision", "HOLD")
    quant_signal = normalized.get("quant_signal")
    llm_signal = normalized.get("llm_signal")
    confidence = normalized.get("confidence")
    date_value = date or normalized.get("date") or normalized.get("analysis_date")
    ticker_value = ticker or normalized.get("ticker")
    return {
        "contract_version": "v1alpha1",
        "ticker": ticker_value,
        "name": normalized.get("name", ticker_value),
        "date": date_value,
        "status": normalized.get("status", "completed"),
        "created_at": normalized.get("created_at"),
        "result": {
            "decision": decision,
            "confidence": confidence,
            "signals": {
                "merged": {
                    "direction": _rating_to_direction(decision),
                    "rating": decision,
                },
                "quant": {
                    "direction": _rating_to_direction(quant_signal),
                    "rating": quant_signal,
                    "available": quant_signal is not None,
                },
                "llm": {
                    "direction": _rating_to_direction(llm_signal),
                    "rating": llm_signal,
                    "available": llm_signal is not None,
                },
            },
            "degraded": quant_signal is None or llm_signal is None,
        },
        "degradation": normalized.get("degradation") or {
            "degraded": quant_signal is None or llm_signal is None,
            "reason_codes": [],
        },
        "data_quality": normalized.get("data_quality"),
        "compat": {
            "analysis_date": date_value,
            "decision": decision,
            "quant_signal": quant_signal,
            "llm_signal": llm_signal,
            "confidence": confidence,
        },
    }


def get_recommendations(date: Optional[str] = None, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0) -> dict:
    """List recommendations, optionally filtered by date. Returns paginated results."""
    RECOMMENDATIONS_DIR.mkdir(parents=True, exist_ok=True)
    all_recs = []

    if date:
        date_dir = RECOMMENDATIONS_DIR / date
        if date_dir.exists():
            all_recs = [
                _normalize_recommendation_record(json.loads(f.read_text()), date=date_dir.name)
                for f in sorted(date_dir.glob("*.json"), reverse=True)
                if f.suffix == ".json"
            ]
    else:
        for date_dir in sorted(RECOMMENDATIONS_DIR.iterdir(), reverse=True):
            if date_dir.is_dir() and date_dir.name.startswith("20"):
                for f in sorted(date_dir.glob("*.json"), reverse=True):
                    if f.suffix == ".json":
                        all_recs.append(
                            _normalize_recommendation_record(
                                json.loads(f.read_text()),
                                date=date_dir.name,
                            )
                        )

    total = len(all_recs)
    return {
        "contract_version": "v1alpha1",
        "recommendations": all_recs[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_recommendation(date: str, ticker: str) -> Optional[dict]:
    # Validate inputs to prevent path traversal
    if ".." in ticker or "/" in ticker or "\\" in ticker:
        return None
    if ".." in date or "/" in date or "\\" in date:
        return None
    path = RECOMMENDATIONS_DIR / date / f"{ticker}.json"
    if not path.exists():
        return None
    # Ensure resolved path is within RECOMMENDATIONS_DIR (strict traversal check)
    try:
        path.resolve().relative_to(RECOMMENDATIONS_DIR.resolve())
    except ValueError:
        return None
    return _normalize_recommendation_record(json.loads(path.read_text()), date=date, ticker=ticker)


def save_recommendation(date: str, ticker: str, data: dict):
    date_dir = RECOMMENDATIONS_DIR / date
    date_dir.mkdir(parents=True, exist_ok=True)
    (date_dir / f"{ticker}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))


class LegacyPortfolioGateway:
    """Compatibility gateway that exposes the current portfolio API as a service boundary."""

    def get_watchlist(self) -> list:
        return get_watchlist()

    def add_to_watchlist(self, ticker: str, name: str) -> dict:
        return add_to_watchlist(ticker, name)

    def remove_from_watchlist(self, ticker: str) -> bool:
        return remove_from_watchlist(ticker)

    def get_accounts(self) -> dict:
        return get_accounts()

    def create_account(self, account_name: str) -> dict:
        return create_account(account_name)

    def delete_account(self, account_name: str) -> bool:
        return delete_account(account_name)

    async def get_positions(self, account: Optional[str] = None) -> list:
        return await get_positions(account)

    def add_position(
        self,
        ticker: str,
        shares: float,
        cost_price: float,
        purchase_date: Optional[str],
        notes: str,
        account: str,
    ) -> dict:
        return add_position(ticker, shares, cost_price, purchase_date, notes, account)

    def remove_position(self, ticker: str, position_id: str, account: Optional[str]) -> bool:
        return remove_position(ticker, position_id, account)

    def get_recommendations(self, date: Optional[str] = None, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0) -> dict:
        return get_recommendations(date, limit, offset)

    def get_recommendation(self, date: str, ticker: str) -> Optional[dict]:
        return get_recommendation(date, ticker)

    def save_recommendation(self, date: str, ticker: str, data: dict):
        save_recommendation(date, ticker, data)


def create_legacy_portfolio_gateway() -> LegacyPortfolioGateway:
    """Create a gateway instance for service-layer migration."""
    return LegacyPortfolioGateway()
