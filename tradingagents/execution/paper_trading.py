"""Paper trading ledger for crypto scan -> LLM -> fake execution workflows.

The ledger never sends real orders. It stores a simple cash account, open
positions, and closed paper trades under the configured crypto memory folder.
Closed trades are also mirrored into raw memory so the dashboard can compute
win-rate and the training memory can learn from reviewed outcomes.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from tradingagents.storage import SQLiteTradingStore


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


@dataclass
class PaperPosition:
    id: str
    symbol: str
    side: str
    strategy: str
    entry_price: float
    quantity: float
    notional: float
    stop_loss: float
    take_profit: float
    opened_at: str
    signal: Dict[str, Any]
    llm_decision: Dict[str, Any]
    confidence: Optional[float] = None
    allocation_pct: Optional[float] = None
    allocation_meta: Optional[Dict[str, Any]] = None
    last_price: Optional[float] = None
    last_checked_at: Optional[str] = None
    highest_price: Optional[float] = None
    breakeven_armed: bool = False
    trailing_armed: bool = False
    stop_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PaperTradingLedger:
    """Fake-money portfolio for local training/testing.

    The legacy backend stores JSON/JSONL files under ``memory_dir``.  The
    SQLite backend keeps the same payload dictionaries in relational tables so
    multiple users can share selected memory spaces safely.
    """

    def __init__(
        self,
        memory_dir: Path | str,
        storage_backend: Optional[str] = None,
        sqlite_path: Optional[Path | str] = None,
        user_id: Optional[str] = None,
        memory_space_id: Optional[str] = None,
    ):
        self.memory_dir = Path(memory_dir).expanduser()
        self.paper_dir = self.memory_dir / "paper"
        self.paper_dir.mkdir(parents=True, exist_ok=True)
        self.account_path = self.paper_dir / "account.json"
        self.positions_path = self.paper_dir / "positions.json"
        self.paper_trades_path = self.paper_dir / "trades.jsonl"
        self.raw_memory_path = self.memory_dir / "raw" / "raw.jsonl"
        self.storage_backend = (storage_backend or os.getenv("TRADINGAGENTS_STORAGE_BACKEND") or "file").lower()
        self.user_id = user_id or os.getenv("TRADINGAGENTS_USER_ID") or "admin"
        self.memory_space_id = memory_space_id or os.getenv("TRADINGAGENTS_MEMORY_SPACE_ID") or "default"
        self.sqlite: Optional[SQLiteTradingStore] = None
        if self.storage_backend == "sqlite":
            db_path = Path(sqlite_path or os.getenv("TRADINGAGENTS_SQLITE_PATH") or self.memory_dir / "tradingagents.db").expanduser()
            self.sqlite = SQLiteTradingStore(db_path, user_id=self.user_id)

    def load_account(self) -> Dict[str, Any]:
        default_account = {
            "currency": "USDT",
            "cash": 0.0,
            "total_deposits": 0.0,
            "realized_pnl": 0.0,
            "created_at": _utc_now(),
        }
        if self.sqlite:
            account = self.sqlite.load_account(self.user_id, self.memory_space_id, default_account)
            account.setdefault("currency", "USDT")
            account.setdefault("cash", 0.0)
            account.setdefault("total_deposits", 0.0)
            account.setdefault("realized_pnl", 0.0)
            return account
        account = _read_json(
            self.account_path,
            default_account,
        )
        account.setdefault("currency", "USDT")
        account.setdefault("cash", 0.0)
        account.setdefault("total_deposits", 0.0)
        account.setdefault("realized_pnl", 0.0)
        return account

    def save_account(self, account: Dict[str, Any]) -> Dict[str, Any]:
        account["updated_at"] = _utc_now()
        if self.sqlite:
            self.sqlite.save_account(self.user_id, self.memory_space_id, account)
            return account
        self.account_path.write_text(json.dumps(account, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return account

    def deposit(self, amount: float, note: str = "paper deposit") -> Dict[str, Any]:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        account = self.load_account()
        account["cash"] = float(account.get("cash", 0.0)) + amount
        account["total_deposits"] = float(account.get("total_deposits", 0.0)) + amount
        account.setdefault("deposits", []).append({"amount": amount, "note": note, "timestamp_utc": _utc_now()})
        return self.save_account(account)

    def reset(self, initial_cash: float = 0.0) -> Dict[str, Any]:
        account = {
            "currency": "USDT",
            "cash": 0.0,
            "total_deposits": 0.0,
            "realized_pnl": 0.0,
            "created_at": _utc_now(),
            "deposits": [],
        }
        self.save_positions([])
        if initial_cash > 0:
            self.save_account(account)
            return self.deposit(initial_cash, note="paper reset initial cash")
        return self.save_account(account)

    def load_positions(self) -> List[Dict[str, Any]]:
        if self.sqlite:
            return self.sqlite.load_positions(self.user_id, self.memory_space_id)
        rows = _read_json(self.positions_path, [])
        return rows if isinstance(rows, list) else []

    def save_positions(self, positions: Iterable[Dict[str, Any]]) -> None:
        if self.sqlite:
            self.sqlite.save_positions(self.user_id, self.memory_space_id, positions)
            return
        self.positions_path.write_text(
            json.dumps(list(positions), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def open_position(
        self,
        signal: Dict[str, Any],
        llm_decision: Dict[str, Any],
        allocation_pct: float = 0.10,
        min_confidence: float = 0.0,
        notional_cap: Optional[float] = None,
        allocation_meta: Optional[Dict[str, Any]] = None,
        opened_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        action = str(llm_decision.get("action") or signal.get("action") or "").upper()
        if action != "BUY":
            return {"status": "skipped", "reason": "paper_spot_only_opens_buy", "signal": signal, "llm_decision": llm_decision}

        confidence = llm_decision.get("confidence")
        try:
            confidence_f = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence_f = None
        if confidence_f is not None and confidence_f < min_confidence:
            return {"status": "skipped", "reason": "confidence_below_threshold", "confidence": confidence_f}

        account = self.load_account()
        cash = float(account.get("cash", 0.0))
        if cash <= 0:
            return {"status": "skipped", "reason": "paper_cash_empty"}

        allocation_pct = max(0.0, min(1.0, float(allocation_pct)))
        notional = cash * allocation_pct
        if notional_cap is not None and float(notional_cap) > 0:
            notional = min(notional, float(notional_cap))
        notional = round(min(notional, cash), 8)
        if notional <= 0:
            return {"status": "skipped", "reason": "notional_too_small"}

        entry = float(signal["entry"])
        quantity = notional / entry
        position = PaperPosition(
            id=str(uuid.uuid4()),
            symbol=str(signal["symbol"]),
            side="LONG",
            strategy=str(signal.get("strategy") or "scanner"),
            entry_price=entry,
            quantity=quantity,
            notional=notional,
            stop_loss=float(signal.get("stop_loss") or entry * 0.98),
            take_profit=float(signal.get("take_profit") or entry * 1.02),
            opened_at=opened_at or str(signal.get("timestamp_utc") or _utc_now()),
            signal=signal,
            llm_decision=llm_decision,
            confidence=confidence_f,
            allocation_pct=allocation_pct,
            allocation_meta=allocation_meta or {},
            last_price=entry,
            last_checked_at=opened_at or str(signal.get("timestamp_utc") or _utc_now()),
            highest_price=entry,
        )
        account["cash"] = round(cash - notional, 8)
        self.save_account(account)
        positions = self.load_positions()
        positions.append(position.to_dict())
        self.save_positions(positions)
        return {"status": "opened", "position": position.to_dict(), "account": account}

    def mark_open_positions(self, prices: Dict[str, float]) -> List[Dict[str, Any]]:
        now = _utc_now()
        positions = self.load_positions()
        for position in positions:
            symbol = position.get("symbol")
            if symbol in prices:
                position["last_price"] = float(prices[symbol])
                position["last_checked_at"] = now
        self.save_positions(positions)
        return positions

    def check_exits(
        self,
        candles: Dict[str, Dict[str, Any]],
        timestamp_utc: Optional[str] = None,
        max_hold_hours: Optional[float] = None,
        breakeven_trigger_pct: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Close positions whose stop/take profit was hit by the supplied candles.

        Candle values may include high/low/close. If high/low are omitted, close is
        used for both. For conservative accounting, if SL and TP are both touched
        in the same candle, stop-loss wins. When ``max_hold_hours`` is provided,
        positions that have gone stale are closed at the supplied close price.
        Optional breakeven/trailing settings protect open profits before the
        hard time exit triggers.
        """
        timestamp_utc = timestamp_utc or _utc_now()
        now_dt = _parse_utc(timestamp_utc) or datetime.now(timezone.utc)
        max_hold = float(max_hold_hours) if max_hold_hours is not None else 0.0
        breakeven_trigger = max(0.0, float(breakeven_trigger_pct or 0.0))
        trailing_stop = max(0.0, float(trailing_stop_pct or 0.0))
        remaining: List[Dict[str, Any]] = []
        closed: List[Dict[str, Any]] = []
        for position in self.load_positions():
            candle = candles.get(position.get("symbol"))
            if not candle:
                remaining.append(position)
                continue
            close = float(candle.get("close", position.get("last_price") or position["entry_price"]))
            high = float(candle.get("high", close))
            low = float(candle.get("low", close))
            entry = float(position["entry_price"])
            highest = max(float(position.get("highest_price") or entry), high, close)
            position["highest_price"] = highest

            current_stop = float(position["stop_loss"])
            if breakeven_trigger > 0 and highest >= entry * (1 + breakeven_trigger / 100.0) and current_stop < entry:
                current_stop = entry
                position["stop_loss"] = round(current_stop, 8)
                position["breakeven_armed"] = True
                position["stop_reason"] = "BREAKEVEN_STOP"

            if trailing_stop > 0 and highest >= entry * (1 + trailing_stop / 100.0):
                trailed_stop = highest * (1 - trailing_stop / 100.0)
                if trailed_stop > current_stop:
                    current_stop = trailed_stop
                    position["stop_loss"] = round(current_stop, 8)
                    position["trailing_armed"] = True
                    position["stop_reason"] = "TRAILING_STOP"

            exit_price: Optional[float] = None
            exit_reason = ""
            if low <= float(position["stop_loss"]):
                exit_price = float(position["stop_loss"])
                exit_reason = str(position.get("stop_reason") or "STOP_LOSS")
            elif high >= float(position["take_profit"]):
                exit_price = float(position["take_profit"])
                exit_reason = "TAKE_PROFIT"
            elif max_hold > 0:
                opened_at = _parse_utc(position.get("opened_at"))
                if opened_at and (now_dt - opened_at).total_seconds() >= max_hold * 3600:
                    exit_price = close
                    exit_reason = "TIME_EXIT"

            position["last_price"] = close
            position["last_checked_at"] = timestamp_utc
            if exit_price is None:
                remaining.append(position)
                continue
            closed.append(self.close_position(position, exit_price, exit_reason, timestamp_utc, save_positions=False))

        self.save_positions(remaining)
        return closed

    def force_close(self, position_id: str, exit_price: float, reason: str = "FORCE_CLOSE", timestamp_utc: Optional[str] = None) -> Dict[str, Any]:
        positions = self.load_positions()
        remaining: List[Dict[str, Any]] = []
        target: Optional[Dict[str, Any]] = None
        for position in positions:
            if position.get("id") == position_id:
                target = position
            else:
                remaining.append(position)
        if target is None:
            raise ValueError(f"Open paper position not found: {position_id}")
        trade = self.close_position(target, float(exit_price), reason, timestamp_utc or _utc_now(), save_positions=False)
        self.save_positions(remaining)
        return trade

    def close_position(
        self,
        position: Dict[str, Any],
        exit_price: float,
        exit_reason: str,
        timestamp_utc: str,
        save_positions: bool = True,
    ) -> Dict[str, Any]:
        entry = float(position["entry_price"])
        quantity = float(position["quantity"])
        pnl_amount = (float(exit_price) - entry) * quantity
        pnl_pct = ((float(exit_price) - entry) / entry) * 100 if entry else 0.0
        result = "WIN" if pnl_amount > 0 else "LOSS" if pnl_amount < 0 else "FLAT"

        account = self.load_account()
        account["cash"] = round(float(account.get("cash", 0.0)) + quantity * float(exit_price), 8)
        account["realized_pnl"] = round(float(account.get("realized_pnl", 0.0)) + pnl_amount, 8)
        self.save_account(account)

        decision = position.get("llm_decision") or {}
        signal = position.get("signal") or {}
        trade = {
            "schema": "crypto_paper_trade_v1",
            "timestamp_utc": timestamp_utc,
            "opened_at": position.get("opened_at"),
            "closed_at": timestamp_utc,
            "coin": position.get("symbol"),
            "symbol": position.get("symbol"),
            "strategy": position.get("strategy"),
            "signal": signal.get("action") or "BUY",
            "action": decision.get("action") or signal.get("action") or "BUY",
            "result": result,
            "pnl": round(pnl_pct, 6),
            "pnl_pct": round(pnl_pct, 6),
            "pnl_amount": round(pnl_amount, 8),
            "pnl_usdt": round(pnl_amount, 8),
            "entry": entry,
            "exit": float(exit_price),
            "entry_price": entry,
            "exit_price": float(exit_price),
            "quantity": quantity,
            "notional": float(position.get("notional", 0.0)),
            "allocation_pct": position.get("allocation_pct"),
            "allocation_meta": position.get("allocation_meta") or {},
            "stop_loss": float(position.get("stop_loss", 0.0)),
            "take_profit": float(position.get("take_profit", 0.0)),
            "exit_reason": exit_reason,
            "confidence": position.get("confidence"),
            "reasoning": decision.get("reasoning") or signal.get("reason") or "paper trade closed",
            "llm_decision": decision,
            "market_context": {
                "market_regime": signal.get("market_regime"),
                "rsi": signal.get("rsi"),
                "volume_spike": signal.get("volume_spike"),
                "strength": signal.get("strength"),
            },
            "mode_id": "paper_trade",
            "cash_after": account["cash"],
        }
        if self.sqlite:
            self.sqlite.append_trade(self.user_id, self.memory_space_id, trade)
        else:
            _append_jsonl(self.paper_trades_path, trade)
            _append_jsonl(self.raw_memory_path, trade)

        if save_positions:
            self.save_positions([p for p in self.load_positions() if p.get("id") != position.get("id")])
        return trade

    def load_closed_trades(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        if self.sqlite:
            return self.sqlite.load_trades(self.user_id, self.memory_space_id, limit=limit)
        if not self.paper_trades_path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for line in self.paper_trades_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        rows.reverse()
        return rows[:limit] if limit else rows

    def portfolio(self) -> Dict[str, Any]:
        account = self.load_account()
        positions = self.load_positions()
        trades = self.load_closed_trades()
        wins = sum(1 for trade in trades if trade.get("result") == "WIN")
        losses = sum(1 for trade in trades if trade.get("result") == "LOSS")
        closed_total = wins + losses
        open_value = 0.0
        unrealized_pnl = 0.0
        for position in positions:
            last = float(position.get("last_price") or position.get("entry_price") or 0.0)
            qty = float(position.get("quantity") or 0.0)
            value = qty * last
            open_value += value
            unrealized_pnl += value - float(position.get("notional") or 0.0)
        cash = float(account.get("cash", 0.0))
        equity = cash + open_value
        deposits = float(account.get("total_deposits", 0.0))
        realized = float(account.get("realized_pnl", 0.0))
        return {
            "account": account,
            "cash": cash,
            "open_value": round(open_value, 8),
            "equity": round(equity, 8),
            "total_deposits": deposits,
            "realized_pnl": realized,
            "unrealized_pnl": round(unrealized_pnl, 8),
            "total_pnl": round(equity - deposits, 8),
            "total_pnl_pct": ((equity - deposits) / deposits * 100) if deposits else 0.0,
            "realized_pnl_pct": (realized / deposits * 100) if deposits else 0.0,
            "open_positions": positions,
            "closed_trades": trades[:50],
            "stats": {
                "open_positions": len(positions),
                "closed_trades": len(trades),
                "wins": wins,
                "losses": losses,
                "win_rate": wins / closed_total if closed_total else None,
            },
        }
