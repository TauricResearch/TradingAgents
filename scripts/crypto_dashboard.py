"""Local web dashboard for TradingAgents Crypto.

Run:
    python scripts/crypto_dashboard.py
    python scripts/crypto_dashboard.py --memory-dir /tmp/tradingagents_crypto_memory_case

The dashboard is intentionally dependency-free: it uses Python's standard
library HTTP server and vanilla HTML/CSS/JS. It is designed for local use and
does not place orders.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import threading
import time
import uuid
import webbrowser
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from tradingagents.agents.utils.crypto_memory import CryptoTrainingMemory
from tradingagents.crypto import CryptoTrainRunner
from tradingagents.default_config import CRYPTO_TRAIN_CONFIG
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.crypto_data import _fetch_ohlcv
from tradingagents.dataflows.crypto_news import get_global_crypto_news
from tradingagents.dataflows.crypto_sentiment import get_crypto_fear_greed
from tradingagents.execution import PaperTradingLedger
from tradingagents.memory import CryptoMemoryStore, LessonValidator, MemoryProcessor
from tradingagents.notifications import TelegramNotifier
from tradingagents.scanner import FastCryptoScanner
from tradingagents.storage import SQLiteTradingStore


DEFAULT_STATE = {
    "mode": "training",  # training | trade
    "trading_enabled": False,
    "dry_run": True,
    "require_confirmation": True,
    "min_confidence": 0.65,
    "max_position_pct": 0.10,
    "max_position_usdt": 100.0,
    "paper_min_allocation_pct": 0.02,
    "sizing_min_trades": 5,
    "paper_symbols": [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT",
        "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "TON/USDT", "SUI/USDT",
        "DOT/USDT", "NEAR/USDT", "APT/USDT", "OP/USDT", "ARB/USDT",
    ],
    "paper_allocation_pct": 0.10,
    "training_memory_tiers": ["lesson"],
    "telegram_enabled": False,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "telegram_update_offset": 0,
    "auto_scan_enabled": False,
    "scan_interval_minutes": 10,
    "last_auto_scan_at": "",
    "last_auto_scan_status": "idle",
    "scanner_timeframe": "1h",
    "scanner_timeframes": ["15m", "30m", "1h"],
    "scanner_enable_rsi_reversal": True,
    "scanner_enable_breakout": False,
    "scanner_enable_ema_crossover": False,
    "scanner_enable_rsi_momentum": False,
    "scanner_enable_trend_pullback": False,
    "scanner_enable_liquidity_sweep": True,
    "scanner_enable_range_bounce": True,
    "scanner_enable_bb_reversion": True,
    "scanner_enable_orderflow": False,
    "scanner_enable_regime_flip": False,
    "scanner_enable_ensemble": True,
    "scanner_ensemble_min_votes": 3,
    "scanner_ensemble_base_bonus": 0.05,
    "scanner_ensemble_max_bonus": 0.12,
    "scanner_range_lookback": 20,
    "scanner_range_bounce_max_pos": 0.35,
    "scanner_range_min_width_atr": 1.6,
    "scanner_range_min_volume_spike": 0.20,
    "scanner_sideway_min_rsi": 28,
    "scanner_sideway_max_rsi": 65,
    "scanner_rsi_oversold": 35,
    "scanner_rsi_extreme": 25,
    "scanner_max_reversal_rsi": 35,
    "scanner_max_breakout_rsi": 68,
    "scanner_min_momentum_volume_spike": 0.50,
    "scanner_min_reward_risk": 1.20,
    "scanner_min_strength": 0.65,
    "scanner_llm_soft_override": False,
    "scanner_llm_soft_override_min_strength": 0.55,
    "scanner_auto_approve_strong": True,
    "scanner_auto_approve_min_strength": 0.72,
    "scanner_auto_approve_min_confidence": 0.65,
    "telegram_auto_approve_test_mode": False,
    "scanner_max_open_positions": 5,
    "scanner_max_hold_hours": 24,
    "scanner_breakeven_trigger_pct": 0.6,
    "scanner_trailing_stop_pct": 0.5,
    "storage_backend": "file",
    "active_user_id": "admin",
    "training_memory_space_id": "default",
    "trade_memory_space_id": "default",
}


def _resolve_safe_memory_dir(memory_dir: str, allow_temp_memory: bool = False) -> Path:
    """Avoid using volatile temp folders for dashboard/training state by default."""
    requested = Path(memory_dir).expanduser()
    try:
        resolved = requested.resolve(strict=False)
        temp_roots = [Path(tempfile.gettempdir()).resolve(strict=False)]
    except OSError:
        resolved = requested.absolute()
        temp_roots = [Path(tempfile.gettempdir()).absolute()]
    for candidate in ("/tmp", "/private/tmp", "/var/tmp"):
        temp_roots.append(Path(candidate).resolve(strict=False))
    is_temp = any(resolved == root or root in resolved.parents for root in temp_roots)
    if not allow_temp_memory and is_temp:
        fallback = Path(CRYPTO_TRAIN_CONFIG.get("crypto_memory_dir", "~/.tradingagents/crypto_memory")).expanduser()
        print(
            f"WARNING: refusing volatile memory dir {requested}; using persistent {fallback}. "
            "Pass --allow-temp-memory only for throwaway tests.",
            flush=True,
        )
        return fallback
    return requested


def _normalize_training_memory_tiers(value: Any) -> List[str]:
    allowed = {"raw", "lesson", "global"}
    if isinstance(value, str):
        candidates = [item.strip().lower() for item in value.split(",")]
    elif isinstance(value, list):
        candidates = [str(item).strip().lower() for item in value]
    else:
        candidates = []
    tiers: List[str] = []
    for item in candidates:
        if item in allowed and item not in tiers:
            tiers.append(item)
    return tiers or ["lesson"]


def _json_from_text(text: str) -> Dict[str, Any]:
    """Parse a JSON object from an LLM response, tolerating markdown wrappers."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {"decisions": []}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"decisions": []}


def _json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _html_response(handler: BaseHTTPRequestHandler, html: str) -> None:
    data = html.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _extract_decision_field(decision: str, field: str) -> str:
    pattern = rf"(?im)^\s*(?:[-*]\s*)?\*{{0,2}}{re.escape(field)}\*{{0,2}}\s*[:：]\s*(.+)$"
    match = re.search(pattern, decision or "")
    return match.group(1).strip() if match else ""


def _normalize_action(record: Dict[str, Any]) -> str:
    decision = record.get("final_trade_decision", "")
    action = (
        record.get("signal")
        or record.get("action")
        or _extract_decision_field(decision, "Action")
        or record.get("rating")
        or "UNKNOWN"
    )
    return str(action).strip().upper()


def _normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    symbol = record.get("symbol") or record.get("coin") or record.get("ticker") or "UNKNOWN"
    timestamp = _parse_datetime(record.get("timestamp_utc") or record.get("trade_date") or record.get("date"))
    pnl = record.get("pnl")
    if pnl is None:
        pnl = record.get("pnl_pct")
    try:
        pnl = float(pnl) if pnl is not None else None
    except (TypeError, ValueError):
        pnl = None

    result = str(record.get("result") or "").upper()
    if not result and pnl is not None:
        result = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "FLAT"

    decision = record.get("final_trade_decision", "")
    confidence = record.get("confidence") or _extract_decision_field(decision, "Confidence")
    try:
        confidence = float(str(confidence).replace("%", ""))
        if confidence > 1:
            confidence = confidence / 100
    except (TypeError, ValueError):
        confidence = None

    return {
        **record,
        "symbol_normalized": str(symbol),
        "timestamp_normalized": timestamp.isoformat() if timestamp else "",
        "date_normalized": timestamp.date().isoformat() if timestamp else str(record.get("trade_date") or ""),
        "week_normalized": f"{timestamp.isocalendar().year}-W{timestamp.isocalendar().week:02d}" if timestamp else "unknown",
        "month_normalized": timestamp.strftime("%Y-%m") if timestamp else "unknown",
        "action_normalized": _normalize_action(record),
        "pnl_normalized": pnl,
        "result_normalized": result,
        "confidence_normalized": confidence,
    }


class DashboardStore:
    """Read TradingAgents crypto memory in file or SQLite layouts.

    SQLite mode adds multi-user memory spaces while keeping payload dictionaries
    compatible with the previous JSON/JSONL implementation.
    """

    def __init__(
        self,
        memory_dir: Path,
        storage_backend: Optional[str] = None,
        sqlite_path: Optional[Path | str] = None,
        user_id: Optional[str] = None,
        actor_user_id: Optional[str] = None,
    ):
        self.memory_dir = memory_dir.expanduser()
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.memory_dir / "dashboard_state.json"
        self.storage_backend = str(storage_backend or os.getenv("TRADINGAGENTS_STORAGE_BACKEND") or "file").lower()
        self.user_id = str(user_id or os.getenv("TRADINGAGENTS_USER_ID") or "admin")
        self.actor_user_id = str(actor_user_id or os.getenv("TRADINGAGENTS_ACTOR_USER_ID") or self.user_id)
        self.sqlite_path = Path(sqlite_path or os.getenv("TRADINGAGENTS_SQLITE_PATH") or self.memory_dir / "tradingagents.db").expanduser()
        self.sqlite: Optional[SQLiteTradingStore] = None
        if self.storage_backend == "sqlite":
            self.sqlite = SQLiteTradingStore(self.sqlite_path, user_id=self.user_id)
        self._lock = threading.Lock()

    @property
    def raw_paths(self) -> List[Path]:
        return [self.memory_dir / "raw.jsonl", self.memory_dir / "raw" / "raw.jsonl"]

    @property
    def lesson_paths(self) -> List[Path]:
        return [self.memory_dir / "lessons.jsonl", self.memory_dir / "lessons" / "lessons.jsonl"]

    @property
    def global_paths(self) -> List[Path]:
        return [self.memory_dir / "global.jsonl", self.memory_dir / "global" / "global.jsonl"]

    def load_state(self) -> Dict[str, Any]:
        state = dict(DEFAULT_STATE)
        if self.sqlite:
            state.update(self.sqlite.load_dashboard_state(self.user_id))
            state["storage_backend"] = "sqlite"
            state["active_user_id"] = self.user_id
            state["training_memory_space_id"] = self.sqlite.selected_memory_space(self.user_id, "training")
            state["trade_memory_space_id"] = self.sqlite.selected_memory_space(self.user_id, "trade")
            state["memory_spaces"] = self.sqlite.list_memory_spaces()
        elif self.state_path.exists():
            try:
                state.update(json.loads(self.state_path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass
        return state

    def update_state(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            state = self.load_state()
            allowed = set(DEFAULT_STATE)
            for key, value in updates.items():
                if key in allowed:
                    state[key] = value
            if state["mode"] not in {"training", "trade"}:
                state["mode"] = "training"
            state["training_memory_tiers"] = _normalize_training_memory_tiers(state.get("training_memory_tiers"))
            if isinstance(state.get("paper_symbols"), str):
                state["paper_symbols"] = [item.strip() for item in state["paper_symbols"].split(",") if item.strip()]
            if not isinstance(state.get("paper_symbols"), list) or not state["paper_symbols"]:
                state["paper_symbols"] = DEFAULT_STATE["paper_symbols"]
            if isinstance(state.get("scanner_timeframes"), str):
                state["scanner_timeframes"] = [item.strip() for item in state["scanner_timeframes"].split(",") if item.strip()]
            if not isinstance(state.get("scanner_timeframes"), list) or not state["scanner_timeframes"]:
                state["scanner_timeframes"] = DEFAULT_STATE["scanner_timeframes"]
            state["paper_allocation_pct"] = max(0.0, min(1.0, float(state.get("paper_allocation_pct") or 0.10)))
            state["paper_min_allocation_pct"] = max(0.0, min(1.0, float(state.get("paper_min_allocation_pct") or 0.02)))
            state["max_position_pct"] = max(0.0, min(1.0, float(state.get("max_position_pct") or 0.10)))
            state["max_position_usdt"] = max(0.0, float(state.get("max_position_usdt") or 0.0))
            state["sizing_min_trades"] = max(1, int(float(state.get("sizing_min_trades") or 5)))
            state["scan_interval_minutes"] = max(1, int(float(state.get("scan_interval_minutes") or 10)))
            state["scanner_max_hold_hours"] = max(0.0, float(state.get("scanner_max_hold_hours") or 0.0))
            state["scanner_breakeven_trigger_pct"] = max(0.0, float(state.get("scanner_breakeven_trigger_pct") or 0.0))
            state["scanner_trailing_stop_pct"] = max(0.0, float(state.get("scanner_trailing_stop_pct") or 0.0))
            state["scanner_min_reward_risk"] = max(0.0, float(state.get("scanner_min_reward_risk") or 0.0))
            state["scanner_max_open_positions"] = max(1, int(float(state.get("scanner_max_open_positions") or DEFAULT_STATE["scanner_max_open_positions"])))
            state["scanner_rsi_extreme"] = max(0.0, float(state.get("scanner_rsi_extreme") or DEFAULT_STATE["scanner_rsi_extreme"]))
            state["scanner_max_reversal_rsi"] = max(0.0, float(state.get("scanner_max_reversal_rsi") or DEFAULT_STATE["scanner_max_reversal_rsi"]))
            state["scanner_max_breakout_rsi"] = max(0.0, float(state.get("scanner_max_breakout_rsi") or DEFAULT_STATE["scanner_max_breakout_rsi"]))
            state["scanner_min_momentum_volume_spike"] = max(0.0, float(state.get("scanner_min_momentum_volume_spike") or 0.0))
            state["scanner_range_bounce_max_pos"] = min(0.45, max(0.10, float(state.get("scanner_range_bounce_max_pos") or DEFAULT_STATE["scanner_range_bounce_max_pos"])))
            state["scanner_range_min_width_atr"] = max(1.0, float(state.get("scanner_range_min_width_atr") or DEFAULT_STATE["scanner_range_min_width_atr"]))
            state["scanner_sideway_min_rsi"] = max(0.0, min(100.0, float(state.get("scanner_sideway_min_rsi") or DEFAULT_STATE["scanner_sideway_min_rsi"])))
            state["scanner_sideway_max_rsi"] = max(0.0, min(100.0, float(state.get("scanner_sideway_max_rsi") or DEFAULT_STATE["scanner_sideway_max_rsi"])))
            if state["scanner_sideway_min_rsi"] > state["scanner_sideway_max_rsi"]:
                state["scanner_sideway_min_rsi"], state["scanner_sideway_max_rsi"] = state["scanner_sideway_max_rsi"], state["scanner_sideway_min_rsi"]
            state["telegram_auto_approve_test_mode"] = bool(state.get("telegram_auto_approve_test_mode", False))
            if state["paper_min_allocation_pct"] > state["max_position_pct"]:
                state["paper_min_allocation_pct"] = state["max_position_pct"]
            if state["paper_allocation_pct"] > state["max_position_pct"]:
                state["paper_allocation_pct"] = state["max_position_pct"]
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            if self.sqlite:
                training_space = str(state.get("training_memory_space_id") or "default")
                trade_space = str(state.get("trade_memory_space_id") or "default")
                if training_space != self.sqlite.selected_memory_space(self.user_id, "training"):
                    self.sqlite.set_memory_selection(self.user_id, "training", training_space, actor_user_id=self.actor_user_id)
                if trade_space != self.sqlite.selected_memory_space(self.user_id, "trade"):
                    self.sqlite.set_memory_selection(self.user_id, "trade", trade_space, actor_user_id=self.actor_user_id)
                state["storage_backend"] = "sqlite"
                state["active_user_id"] = self.user_id
                state["memory_spaces"] = self.sqlite.list_memory_spaces()
                self.sqlite.save_dashboard_state(self.user_id, state)
            else:
                self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            return state

    def active_memory_space_id(self, mode: Optional[str] = None) -> str:
        if not self.sqlite:
            return "default"
        mode = mode if mode in {"training", "trade"} else str(self.load_state().get("mode") or "training")
        mode = mode if mode in {"training", "trade"} else "training"
        return self.sqlite.selected_memory_space(self.user_id, mode)

    def load_raw(self) -> List[Dict[str, Any]]:
        if self.sqlite:
            rows = [
                _normalize_record(item)
                for item in self.sqlite.load_memory("raw", memory_space_id=self.active_memory_space_id())
            ]
            rows.sort(key=lambda row: row.get("timestamp_normalized") or row.get("date_normalized"), reverse=True)
            return rows
        rows: List[Dict[str, Any]] = []
        seen = set()
        for path in self.raw_paths:
            for item in _read_jsonl(path):
                key = json.dumps(item, sort_keys=True, ensure_ascii=False)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(_normalize_record(item))
        rows.sort(key=lambda row: row.get("timestamp_normalized") or row.get("date_normalized"), reverse=True)
        return rows

    def load_lessons(self) -> List[Dict[str, Any]]:
        if self.sqlite:
            return self._sort_memory_rows(self.sqlite.load_memory("lesson", memory_space_id=self.active_memory_space_id("training")))
        return self._load_tier(self.lesson_paths)

    def load_global(self) -> List[Dict[str, Any]]:
        if self.sqlite:
            return self._sort_memory_rows(self.sqlite.load_memory("global", memory_space_id=self.active_memory_space_id("training")))
        return self._load_tier(self.global_paths)

    @staticmethod
    def _sort_memory_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows.sort(key=lambda row: str(row.get("timestamp_utc") or row.get("created_at") or row.get("promoted_at") or ""), reverse=True)
        return rows

    @staticmethod
    def _load_tier(paths: Iterable[Path]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        seen = set()
        for path in paths:
            for item in _read_jsonl(path):
                key = json.dumps(item, sort_keys=True, ensure_ascii=False)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(item)
        rows.sort(key=lambda row: str(row.get("timestamp_utc") or row.get("created_at") or row.get("promoted_at") or ""), reverse=True)
        return rows

    def paths(self) -> Dict[str, Any]:
        payload = {
            "memory_dir": str(self.memory_dir),
            "state_path": str(self.state_path),
            "raw_paths": [str(path) for path in self.raw_paths],
            "lesson_paths": [str(path) for path in self.lesson_paths],
            "global_paths": [str(path) for path in self.global_paths],
        }
        if self.sqlite:
            payload.update(
                {
                    "storage_backend": "sqlite",
                    "sqlite_path": str(self.sqlite_path),
                    "active_user_id": self.user_id,
                    "training_memory_space_id": self.active_memory_space_id("training"),
                    "trade_memory_space_id": self.active_memory_space_id("trade"),
                }
            )
        return payload

    def crypto_store(self) -> CryptoMemoryStore:
        return CryptoMemoryStore(
            self.memory_dir,
            storage_backend=self.storage_backend,
            sqlite_path=self.sqlite_path,
            user_id=self.user_id,
            memory_space_id=self.active_memory_space_id("training"),
        )

    def paper_ledger(self) -> PaperTradingLedger:
        return PaperTradingLedger(
            self.memory_dir,
            storage_backend=self.storage_backend,
            sqlite_path=self.sqlite_path,
            user_id=self.user_id,
            memory_space_id=self.active_memory_space_id("trade"),
        )

    @property
    def approvals_path(self) -> Path:
        return self.memory_dir / "paper" / "pending_approvals.json"

    def load_approvals(self) -> List[Dict[str, Any]]:
        if self.sqlite:
            return self.sqlite.load_approvals(self.user_id, self.active_memory_space_id("trade"))
        rows = _read_json(self.approvals_path, [])
        return rows if isinstance(rows, list) else []

    def save_approvals(self, approvals: List[Dict[str, Any]]) -> None:
        if self.sqlite:
            self.sqlite.save_approvals(self.user_id, self.active_memory_space_id("trade"), approvals)
            return
        self.approvals_path.parent.mkdir(parents=True, exist_ok=True)
        self.approvals_path.write_text(json.dumps(approvals, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    @property
    def candidates_path(self) -> Path:
        return self.memory_dir / "paper" / "scan_candidates.jsonl"

    def load_candidates(self, limit: int = 100) -> List[Dict[str, Any]]:
        if self.sqlite:
            return self.sqlite.load_candidates(self.user_id, self.active_memory_space_id("trade"), limit=limit)
        rows = _read_jsonl(self.candidates_path)
        rows.sort(key=lambda r: str(r.get("scanned_at") or ""), reverse=True)
        return rows[:limit]

    def save_candidate(self, candidate: Dict[str, Any]) -> None:
        if self.sqlite:
            self.sqlite.append_candidate(self.user_id, self.active_memory_space_id("trade"), candidate)
            return
        self.candidates_path.parent.mkdir(parents=True, exist_ok=True)
        with self.candidates_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(candidate, ensure_ascii=False) + "\n")

    def clear_candidates(self) -> int:
        if self.sqlite:
            return self.sqlite.clear_candidates(self.user_id, self.active_memory_space_id("trade"))
        if self.candidates_path.exists():
            count = len(_read_jsonl(self.candidates_path))
            self.candidates_path.unlink()
            return count
        return 0

    def load_processed_signal_keys(self, cutoff_iso: str) -> Dict[str, str]:
        if not self.sqlite:
            return {}
        return self.sqlite.load_processed_signal_keys(self.user_id, self.active_memory_space_id("trade"), cutoff_iso)

    def save_processed_signal_keys(self, cache: Dict[str, str]) -> None:
        if self.sqlite:
            self.sqlite.save_processed_signal_keys(self.user_id, self.active_memory_space_id("trade"), cache)


def compute_bucket_stats(rows: List[Dict[str, Any]], bucket_key: str) -> List[Dict[str, Any]]:
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("result_normalized") in {"WIN", "LOSS", "FLAT"}:
            buckets[row.get(bucket_key) or "unknown"].append(row)

    stats: List[Dict[str, Any]] = []
    for bucket, items in buckets.items():
        wins = sum(1 for item in items if item.get("result_normalized") == "WIN")
        losses = sum(1 for item in items if item.get("result_normalized") == "LOSS")
        pnl_values = [item["pnl_normalized"] for item in items if item.get("pnl_normalized") is not None]
        total = wins + losses
        stats.append(
            {
                "bucket": bucket,
                "trades": len(items),
                "wins": wins,
                "losses": losses,
                "win_rate": wins / total if total else None,
                "avg_pnl": sum(pnl_values) / len(pnl_values) if pnl_values else 0.0,
                "total_pnl": sum(pnl_values) if pnl_values else 0.0,
            }
        )
    stats.sort(key=lambda item: item["bucket"], reverse=True)
    return stats


def config_payload(store: DashboardStore) -> Dict[str, Any]:
    """Dashboard configuration and environment paths grouped away from data overview."""
    return {"state": store.load_state(), "paths": store.paths()}


def _trade_pnl_amount(trade: Dict[str, Any]) -> float:
    try:
        return float(trade.get("pnl_amount", trade.get("pnl_usdt", 0.0)) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _trade_notional(trade: Dict[str, Any]) -> float:
    try:
        return abs(float(trade.get("notional") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _position_unrealized(position: Dict[str, Any]) -> Dict[str, float]:
    entry = float(position.get("entry_price") or 0.0)
    last = float(position.get("last_price") or entry or 0.0)
    qty = float(position.get("quantity") or 0.0)
    notional = float(position.get("notional") or 0.0)
    pnl = (last - entry) * qty if entry and qty else 0.0
    return {"pnl": pnl, "notional": notional}


def _period_start(now: datetime, period: str) -> datetime:
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)


def paper_performance_payload(store: DashboardStore) -> Dict[str, Any]:
    """Current paper PnL by day/month/year including open unrealized PnL."""
    ledger = store.paper_ledger()
    portfolio = ledger.portfolio()
    trades = ledger.load_closed_trades()
    positions = ledger.load_positions()
    now = datetime.now(timezone.utc)
    periods = [
        ("day", "Hôm nay", now.strftime("%Y-%m-%d")),
        ("month", "Tháng này", now.strftime("%Y-%m")),
        ("year", "Năm nay", now.strftime("%Y")),
    ]
    rows: List[Dict[str, Any]] = []
    for key, label, bucket in periods:
        start = _period_start(now, key)
        closed_rows = []
        for trade in trades:
            ts = _parse_datetime(trade.get("closed_at") or trade.get("timestamp_utc"))
            if ts and ts >= start:
                closed_rows.append(trade)
        open_rows = []
        for position in positions:
            ts = _parse_datetime(position.get("opened_at"))
            if ts and ts >= start:
                open_rows.append(position)
        realized = sum(_trade_pnl_amount(trade) for trade in closed_rows)
        realized_basis = sum(_trade_notional(trade) for trade in closed_rows)
        open_parts = [_position_unrealized(position) for position in open_rows]
        unrealized = sum(item["pnl"] for item in open_parts)
        open_basis = sum(item["notional"] for item in open_parts)
        pnl = realized + unrealized
        basis = realized_basis + open_basis
        wins = sum(1 for trade in closed_rows if trade.get("result") == "WIN")
        losses = sum(1 for trade in closed_rows if trade.get("result") == "LOSS")
        total = wins + losses
        rows.append(
            {
                "period": key,
                "label": label,
                "bucket": bucket,
                "pnl_amount": round(pnl, 8),
                "pnl_pct": (pnl / basis * 100) if basis else 0.0,
                "realized_pnl": round(realized, 8),
                "unrealized_pnl": round(unrealized, 8),
                "basis_usdt": round(basis, 8),
                "closed_trades": len(closed_rows),
                "open_positions": len(open_rows),
                "wins": wins,
                "losses": losses,
                "win_rate": wins / total if total else None,
            }
        )
    return {
        "operation": "paper_performance",
        "as_of": now.isoformat(),
        "periods": rows,
        "total": {
            "pnl_amount": portfolio.get("total_pnl", 0.0),
            "pnl_pct": portfolio.get("total_pnl_pct", 0.0),
            "realized_pnl": portfolio.get("realized_pnl", 0.0),
            "unrealized_pnl": portfolio.get("unrealized_pnl", 0.0),
            "equity": portfolio.get("equity", 0.0),
            "deposits": portfolio.get("total_deposits", 0.0),
        },
    }


def trading_payload(store: DashboardStore) -> Dict[str, Any]:
    """Grouped paper-trading data used by the trading dashboard card."""
    approvals = store.load_approvals()
    return {
        "paper": store.paper_ledger().portfolio(),
        "approvals": {
            "pending": len([item for item in approvals if item.get("status") == "pending"]),
            "recent": list(reversed(approvals))[:30],
        },
        "performance": paper_performance_payload(store),
    }


def overview_payload(store: DashboardStore, symbol: Optional[str] = None) -> Dict[str, Any]:
    rows = store.load_raw()
    if symbol:
        rows = [row for row in rows if row.get("symbol_normalized") == symbol]
    trade_rows = [row for row in rows if row.get("result_normalized") in {"WIN", "LOSS", "FLAT"}]
    wins = sum(1 for row in trade_rows if row.get("result_normalized") == "WIN")
    losses = sum(1 for row in trade_rows if row.get("result_normalized") == "LOSS")
    pnl_values = [row["pnl_normalized"] for row in trade_rows if row.get("pnl_normalized") is not None]
    total = wins + losses
    symbols = sorted({row.get("symbol_normalized") for row in rows if row.get("symbol_normalized")})
    actions = defaultdict(int)
    for row in rows:
        actions[row.get("action_normalized", "UNKNOWN")] += 1
    return {
        "symbols": symbols,
        "counts": {
            "raw": len(rows),
            "trades": len(trade_rows),
            "lessons": len(store.load_lessons()),
            "global": len(store.load_global()),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / total if total else None,
            "avg_pnl": sum(pnl_values) / len(pnl_values) if pnl_values else None,
            "total_pnl": sum(pnl_values) if pnl_values else 0.0,
        },
        "actions": dict(sorted(actions.items())),
        "daily": compute_bucket_stats(rows, "date_normalized")[:14],
        "weekly": compute_bucket_stats(rows, "week_normalized")[:12],
        "monthly": compute_bucket_stats(rows, "month_normalized")[:12],
        "latest": rows[:8],
    }


def paper_payload(store: DashboardStore) -> Dict[str, Any]:
    return store.paper_ledger().portfolio()


def paper_deposit_payload(store: DashboardStore, amount: float, note: str = "dashboard deposit") -> Dict[str, Any]:
    ledger = store.paper_ledger()
    account = ledger.deposit(float(amount), note=note)
    return {"operation": "paper_deposit", "account": account, "paper": ledger.portfolio()}


def paper_reset_payload(store: DashboardStore, initial_cash: float = 0.0) -> Dict[str, Any]:
    ledger = store.paper_ledger()
    account = ledger.reset(float(initial_cash or 0.0))
    return {"operation": "paper_reset", "account": account, "paper": ledger.portfolio()}


def paper_mark_payload(store: DashboardStore, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """Refresh open paper positions with latest Binance close and close TP/SL hits."""
    ledger = store.paper_ledger()
    state = store.load_state()
    symbols = symbols or sorted({p.get("symbol") for p in ledger.load_positions() if p.get("symbol")})
    candles: Dict[str, Dict[str, Any]] = {}
    for symbol in symbols:
        df = _fetch_ohlcv(symbol, limit=2)
        if df.empty:
            continue
        last = df.iloc[-1]
        candles[symbol] = {
            "high": float(last["High"]),
            "low": float(last["Low"]),
            "close": float(last["Close"]),
        }
    closed = ledger.check_exits(
        candles,
        max_hold_hours=float(state.get("scanner_max_hold_hours") or 0.0),
        breakeven_trigger_pct=float(state.get("scanner_breakeven_trigger_pct") or 0.0),
        trailing_stop_pct=float(state.get("scanner_trailing_stop_pct") or 0.0),
    )
    ledger.mark_open_positions({symbol: candle["close"] for symbol, candle in candles.items()})
    telegram_notifications: List[Dict[str, Any]] = []
    if closed and state.get("telegram_enabled"):
        notifier = _telegram_notifier_from_state(state)
        for trade in closed:
            try:
                telegram_notifications.append({"trade_id": trade.get("id"), "telegram": notifier.send_trade_closed(trade)})
            except Exception as exc:
                telegram_notifications.append({"trade_id": trade.get("id"), "telegram": {"status": "error", "error": str(exc)}})
    return {"operation": "paper_mark", "closed": closed, "telegram": telegram_notifications, "paper": ledger.portfolio()}


def paper_force_close_payload(store: DashboardStore, position_id: str, exit_price: Optional[float] = None) -> Dict[str, Any]:
    """Close one open paper position immediately at the latest available price."""
    ledger = store.paper_ledger()
    position = next((p for p in ledger.load_positions() if p.get("id") == position_id), None)
    if not position:
        return {"operation": "paper_force_close", "status": "not_found", "id": position_id, "paper": ledger.portfolio()}

    symbol = str(position.get("symbol") or "")
    close_price = float(exit_price) if exit_price is not None else float(position.get("last_price") or position.get("entry_price") or 0.0)
    if exit_price is None and symbol:
        try:
            df = _fetch_ohlcv(symbol, limit=2, timeframe="1m")
            if df is not None and len(df) > 0:
                close_price = float(df.iloc[-1]["Close"])
        except Exception:
            pass
    if close_price <= 0:
        return {"operation": "paper_force_close", "status": "error", "error": "invalid_exit_price", "id": position_id, "paper": ledger.portfolio()}

    trade = ledger.force_close(position_id, close_price, reason="MANUAL_CLOSE")
    notification = _notify_paper_trade_closed(store, trade)
    if notification:
        trade["telegram"] = notification
    return {"operation": "paper_force_close", "status": "closed", "trade": trade, "paper": ledger.portfolio()}


def paper_force_close_all_payload(store: DashboardStore) -> Dict[str, Any]:
    """Close every open paper position at the latest available price per symbol."""
    ledger = store.paper_ledger()
    positions = ledger.load_positions()
    if not positions:
        return {"operation": "paper_force_close_all", "status": "empty", "closed": [], "paper": ledger.portfolio()}

    prices: Dict[str, float] = {}
    for symbol in sorted({str(position.get("symbol") or "") for position in positions if position.get("symbol")}):
        try:
            df = _fetch_ohlcv(symbol, limit=2, timeframe="1m")
            if df is not None and len(df) > 0:
                prices[symbol] = float(df.iloc[-1]["Close"])
        except Exception:
            pass

    closed: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for position in positions:
        position_id = str(position.get("id") or "")
        symbol = str(position.get("symbol") or "")
        close_price = prices.get(symbol, float(position.get("last_price") or position.get("entry_price") or 0.0))
        if not position_id or close_price <= 0:
            errors.append({"id": position_id, "symbol": symbol, "error": "invalid_exit_price"})
            continue
        try:
            trade = ledger.force_close(position_id, close_price, reason="MANUAL_CLOSE_ALL")
            notification = _notify_paper_trade_closed(store, trade)
            if notification:
                trade["telegram"] = notification
            closed.append(trade)
        except Exception as exc:
            errors.append({"id": position_id, "symbol": symbol, "error": str(exc)})
    return {
        "operation": "paper_force_close_all",
        "status": "closed" if closed and not errors else "partial" if closed else "error",
        "closed": closed,
        "errors": errors,
        "paper": ledger.portfolio(),
    }


def _confidence_value(decision: Dict[str, Any]) -> Optional[float]:
    try:
        value = decision.get("confidence")
        if value is None:
            return None
        confidence = float(str(value).replace("%", ""))
        return confidence / 100 if confidence > 1 else confidence
    except (TypeError, ValueError):
        return None


def _closed_trade_stats(trades: List[Dict[str, Any]], symbol: Optional[str] = None) -> Dict[str, Any]:
    rows = [trade for trade in trades if not symbol or trade.get("symbol") == symbol or trade.get("coin") == symbol]
    wins = sum(1 for trade in rows if trade.get("result") == "WIN")
    losses = sum(1 for trade in rows if trade.get("result") == "LOSS")
    total = wins + losses
    return {"symbol": symbol or "ALL", "wins": wins, "losses": losses, "closed_trades": total, "win_rate": wins / total if total else None}


def dynamic_sizing(store: DashboardStore, signal: Dict[str, Any], decision: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """Size a paper order from real closed-trade win-rate, bounded by dashboard caps."""
    ledger = store.paper_ledger()
    portfolio = ledger.portfolio()
    cash = float(portfolio.get("cash") or 0.0)
    symbol = str(signal.get("symbol") or signal.get("coin") or "")
    min_pct = max(0.0, min(1.0, float(state.get("paper_min_allocation_pct") or 0.02)))
    base_pct = max(0.0, min(1.0, float(state.get("paper_allocation_pct") or 0.05)))
    max_pct = max(min_pct, min(1.0, float(state.get("max_position_pct") or base_pct)))
    max_usdt = max(0.0, float(state.get("max_position_usdt") or 0.0))
    min_trades = max(1, int(float(state.get("sizing_min_trades") or 5)))
    trades = ledger.load_closed_trades()
    symbol_stats = _closed_trade_stats(trades, symbol)
    global_stats = _closed_trade_stats(trades)
    stats = symbol_stats if symbol_stats["closed_trades"] >= min_trades else global_stats
    source = "symbol" if stats is symbol_stats else "global"
    win_rate = stats.get("win_rate") if stats.get("closed_trades", 0) >= min_trades else None
    confidence = _confidence_value(decision)

    if win_rate is None:
        allocation_pct = min(base_pct, max_pct)
        reason = f"not enough real closed trades (need {min_trades}); using base allocation"
    else:
        # Map 40% win-rate -> min size, 75%+ -> max size, with a small confidence adjustment.
        win_score = max(0.0, min(1.0, (float(win_rate) - 0.40) / 0.35))
        conf_score = 0.5 if confidence is None else max(0.0, min(1.0, (confidence - 0.50) / 0.40))
        combined = 0.75 * win_score + 0.25 * conf_score
        allocation_pct = min_pct + (max_pct - min_pct) * combined
        reason = f"{source} real win-rate sizing"

    allocation_pct = max(min_pct, min(max_pct, allocation_pct))
    notional = cash * allocation_pct
    if max_usdt > 0:
        notional = min(notional, max_usdt)
    return {
        "allocation_pct": round(allocation_pct, 6),
        "notional_usdt": round(max(0.0, notional), 2),
        "max_position_pct": max_pct,
        "max_position_usdt": max_usdt,
        "min_allocation_pct": min_pct,
        "cash": round(cash, 8),
        "stats": stats,
        "symbol_stats": symbol_stats,
        "global_stats": global_stats,
        "min_trades": min_trades,
        "confidence": confidence,
        "reason": reason,
    }


def _telegram_notifier_from_state(state: Dict[str, Any]) -> TelegramNotifier:
    token = state.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = state.get("telegram_chat_id") or os.getenv("TELEGRAM_CHAT_ID")
    return TelegramNotifier(token=token, chat_id=chat_id, dry_run=not bool(state.get("telegram_enabled")))


def _notify_paper_order_opened(store: DashboardStore, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Best-effort Telegram notification for a newly opened paper order."""
    if order.get("status") != "opened":
        return None
    state = store.load_state()
    if not state.get("telegram_enabled"):
        return None
    try:
        return _telegram_notifier_from_state(state).send_order_opened(order)
    except Exception as exc:
        print(f"WARNING: telegram order-open notification failed: {exc}", flush=True)
        return {"status": "error", "error": str(exc)}


def _notify_paper_trade_closed(store: DashboardStore, trade: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Best-effort Telegram notification for a manually or automatically closed paper trade."""
    state = store.load_state()
    if not state.get("telegram_enabled"):
        return None
    try:
        return _telegram_notifier_from_state(state).send_trade_closed(trade)
    except Exception as exc:
        print(f"WARNING: telegram trade-close notification failed: {exc}", flush=True)
        return {"status": "error", "error": str(exc)}


def _send_scan_summary_telegram(store: DashboardStore, result: Dict[str, Any], symbols: List[str]) -> None:
    """Send a Telegram heartbeat after every auto-scan, signal or not."""
    try:
        state = store.load_state()
        if not state.get("telegram_enabled"):
            return
        status = result.get("status", "?")
        signals = result.get("signals") or []
        orders = result.get("orders") or []
        pre_llm_skipped = len(result.get("risk_rejected") or [])
        pending = sum(1 for o in orders if o.get("status") == "pending_approval")
        opened = sum(1 for o in orders if o.get("status") == "opened")
        skipped = pre_llm_skipped + sum(1 for o in orders if o.get("status") == "skipped")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        # Use RSI map already computed during the scan (no re-fetch needed)
        rsi_map: Dict[str, float] = result.get("rsi_map") or {}
        scan_debug: Dict[str, Dict[str, Any]] = result.get("scan_debug") or {}
        rsi_rows: List[tuple] = sorted((rsi, sym) for sym, rsi in rsi_map.items())
        top5 = rsi_rows[:5]

        if status == "no_signal":
            icon = "📊"
            title = "Scan xong: không có tín hiệu"
        else:
            icon = "🔔"
            title = f"Scan xong: {len(signals)} tín hiệu"

        lines = [
            f"{icon} {title}",
            f"{ts} · Symbols {len(symbols)} · Signals {len(signals)} · Pending {pending} · Opened {opened} · Skipped {skipped}",
        ]
        if top5:
            lines.append("")
            lines.append("RSI thấp nhất:")
            for rsi, sym in top5:
                bar = "🔴" if rsi < 35 else ("🟡" if rsi < 45 else "🟢")
                debug = scan_debug.get(sym) or {}
                lines.append(f"  {bar} {sym}: RSI {rsi:.1f} · {debug.get('market_regime') or '?'} · {debug.get('strategy') or 'none'}")
        if signals:
            lines.append("")
            lines.append("Tín hiệu:")
            for sig in signals[:5]:
                rr = _long_reward_risk(sig)
                rr_text = f" RR={rr:.2f}" if rr is not None else ""
                lines.append(
                    f"  → {sig.get('symbol')} {sig.get('action')} · {sig.get('strategy')} · {sig.get('market_regime')} "
                    f"RSI={sig.get('rsi')} Str={sig.get('strength')}{rr_text}"
                )
        text = "\n".join(lines)
        _telegram_notifier_from_state(state).send_text(text)
        print(f"[Telegram] Scan summary sent ({status}, {len(signals)} signals, RSI rows={len(rsi_rows)})", flush=True)
    except Exception as exc:
        print(f"WARNING: scan summary telegram failed: {exc}", flush=True)


def create_pending_approval(
    store: DashboardStore,
    signal: Dict[str, Any],
    decision: Dict[str, Any],
    sizing: Dict[str, Any],
    source: str = "dashboard",
) -> Dict[str, Any]:
    approval = {
        "id": uuid.uuid4().hex[:12],
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "signal": signal,
        "llm_decision": decision,
        "sizing": sizing,
    }
    approvals = store.load_approvals()
    approvals.append(approval)
    store.save_approvals(approvals)
    state = store.load_state()
    try:
        approval["telegram"] = _telegram_notifier_from_state(state).send_approval_request(approval)
    except Exception as exc:
        approval["telegram"] = {"status": "error", "error": str(exc)}
    approvals[-1] = approval
    store.save_approvals(approvals)
    return approval


def approvals_payload(store: DashboardStore) -> Dict[str, Any]:
    approvals = store.load_approvals()
    return {
        "operation": "paper_approvals",
        "pending": [item for item in approvals if item.get("status") == "pending"],
        "recent": list(reversed(approvals))[:30],
    }


def approve_pending_payload(store: DashboardStore, approval_id: str, approved_by: str = "dashboard") -> Dict[str, Any]:
    approvals = store.load_approvals()
    for approval in approvals:
        if approval.get("id") != approval_id:
            continue
        if approval.get("status") != "pending":
            return {"operation": "approve_pending", "status": "skipped", "reason": f"already_{approval.get('status')}", "approval": approval}
        sizing = approval.get("sizing") or {}
        order = store.paper_ledger().open_position(
            approval.get("signal") or {},
            approval.get("llm_decision") or {},
            allocation_pct=float(sizing.get("allocation_pct") or 0.0),
            min_confidence=float(store.load_state().get("min_confidence") or 0.0),
            notional_cap=float(sizing.get("max_position_usdt") or 0.0),
            allocation_meta=sizing,
        )
        order_notification = _notify_paper_order_opened(store, order)
        if order_notification:
            order["telegram"] = order_notification
        approval.update({"status": "approved", "approved_at": datetime.now(timezone.utc).isoformat(), "approved_by": approved_by, "order": order})
        store.save_approvals(approvals)
        return {"operation": "approve_pending", "status": "approved", "approval": approval, "order": order, "paper": store.paper_ledger().portfolio()}
    return {"operation": "approve_pending", "status": "not_found", "id": approval_id}


def reject_pending_payload(store: DashboardStore, approval_id: str, rejected_by: str = "dashboard") -> Dict[str, Any]:
    approvals = store.load_approvals()
    for approval in approvals:
        if approval.get("id") == approval_id and approval.get("status") == "pending":
            approval.update({"status": "rejected", "rejected_at": datetime.now(timezone.utc).isoformat(), "rejected_by": rejected_by})
            store.save_approvals(approvals)
            return {"operation": "reject_pending", "status": "rejected", "approval": approval}
    return {"operation": "reject_pending", "status": "not_found", "id": approval_id}


def poll_telegram_payload(store: DashboardStore) -> Dict[str, Any]:
    state = store.load_state()
    notifier = _telegram_notifier_from_state(state)
    offset = int(state.get("telegram_update_offset") or 0)
    updates = notifier.get_updates(offset=offset + 1, timeout=0)
    actions: List[Dict[str, Any]] = []
    max_update_id = offset
    for update in updates.get("result", []):
        max_update_id = max(max_update_id, int(update.get("update_id", 0)))
        callback = update.get("callback_query") or {}
        data = str(callback.get("data") or "")
        callback_id = str(callback.get("id") or "")
        if not data.startswith(("approve:", "reject:")):
            continue
        action, approval_id = data.split(":", 1)
        if action == "approve":
            result = approve_pending_payload(store, approval_id, approved_by="telegram")
            notifier.answer_callback(callback_id, "Approved" if result.get("status") == "approved" else result.get("status", "skipped"))
        else:
            result = reject_pending_payload(store, approval_id, rejected_by="telegram")
            notifier.answer_callback(callback_id, "Rejected" if result.get("status") == "rejected" else result.get("status", "skipped"))
        actions.append(result)
    if max_update_id > offset:
        store.update_state({"telegram_update_offset": max_update_id})
    return {"operation": "telegram_poll", "updates": len(updates.get("result", [])), "actions": actions}


def _float_config_value(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _decision_confidence(decision: Dict[str, Any]) -> Optional[float]:
    try:
        return float(decision.get("confidence"))
    except (TypeError, ValueError):
        return None


def _long_reward_risk(signal: Dict[str, Any]) -> Optional[float]:
    try:
        entry = float(signal.get("entry"))
        stop_loss = float(signal.get("stop_loss"))
        take_profit = float(signal.get("take_profit"))
    except (TypeError, ValueError):
        return None
    risk = entry - stop_loss
    reward = take_profit - entry
    if entry <= 0 or risk <= 0 or reward <= 0:
        return None
    return reward / risk


def _scanner_risk_rejection(signal: Dict[str, Any], state: Dict[str, Any]) -> Optional[str]:
    """Conservative guardrail before spending LLM calls or opening paper orders."""
    action = str(signal.get("action") or "").upper()
    if action != "BUY":
        return "paper_spot_only_buy"

    rr = _long_reward_risk(signal)
    min_rr = _float_config_value(state.get("scanner_min_reward_risk", 1.20), 1.20)
    if rr is None or rr < min_rr:
        return f"reward_risk_below_{min_rr:.2f}"

    strategy = str(signal.get("strategy") or "")
    regime = str(signal.get("market_regime") or "")
    rsi = _float_config_value(signal.get("rsi"), 50.0)
    volume_spike = _float_config_value(signal.get("volume_spike"), 0.0)

    if strategy == "rsi_reversal":
        if rsi >= _float_config_value(state.get("scanner_rsi_oversold", DEFAULT_STATE["scanner_rsi_oversold"]), DEFAULT_STATE["scanner_rsi_oversold"]):
            return "rsi_reversal_not_oversold_enough"
    if strategy == "breakout":
        if regime != "trend_up":
            return "breakout_not_in_trend_up"
        if rsi > _float_config_value(state.get("scanner_max_breakout_rsi", 68), 68):
            return "breakout_rsi_overheated"
    if strategy in {"range_bounce", "bb_reversion"}:
        if regime != "sideway":
            return "sideway_strategy_not_in_sideway"
        if rsi > _float_config_value(state.get("scanner_sideway_max_rsi", DEFAULT_STATE["scanner_sideway_max_rsi"]), DEFAULT_STATE["scanner_sideway_max_rsi"]):
            return "sideway_rsi_too_high"
    if strategy in {"ema_crossover", "rsi_momentum", "trend_pullback", "orderflow_approx", "regime_flip"}:
        if regime != "trend_up":
            return "momentum_not_in_trend_up"
        if rsi > _float_config_value(state.get("scanner_max_breakout_rsi", 68), 68):
            return "momentum_rsi_overheated"
        if volume_spike < _float_config_value(state.get("scanner_min_momentum_volume_spike", DEFAULT_STATE["scanner_min_momentum_volume_spike"]), DEFAULT_STATE["scanner_min_momentum_volume_spike"]):
            return "momentum_volume_too_weak"

    return None


def _filter_scan_signals_by_risk(store: "DashboardStore", signals: List[Any], state: Dict[str, Any]) -> tuple[List[Any], List[Dict[str, Any]]]:
    accepted: List[Any] = []
    rejected: List[Dict[str, Any]] = []
    for signal in signals:
        signal_dict = signal.to_dict()
        reason = _scanner_risk_rejection(signal_dict, state)
        if not reason:
            accepted.append(signal)
            continue
        candidate = {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "symbol": signal_dict.get("symbol"),
            "strategy": signal_dict.get("strategy"),
            "scanner_action": signal_dict.get("action"),
            "rsi": signal_dict.get("rsi"),
            "strength": signal_dict.get("strength"),
            "market_regime": signal_dict.get("market_regime"),
            "reward_risk": _long_reward_risk(signal_dict),
            "llm_action": "SKIPPED_BEFORE_LLM",
            "llm_confidence": None,
            "llm_reasoning": f"Risk filter: {reason}",
        }
        store.save_candidate(candidate)
        rejected.append(candidate)
    return accepted, rejected


def _dedup_signals(store: "DashboardStore", signals: List["ScanSignal"]) -> List["ScanSignal"]:
    """Filter out signals whose (symbol, strategy, candle_timestamp) was already processed
    within the last 2 hours, preventing duplicate orders from repeated scans on the same
    completed 1h candle (10-min scan × 6 = 6 identical signals per candle otherwise).
    """
    cache_path = store.memory_dir / "paper" / "processed_signal_keys.json"
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=2)).isoformat()
    if getattr(store, "sqlite", None):
        cache = store.load_processed_signal_keys(cutoff)
    else:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            cache: Dict[str, str] = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        except (json.JSONDecodeError, OSError):
            cache = {}
        cache = {k: v for k, v in cache.items() if v >= cutoff}
    fresh: List["ScanSignal"] = []
    for sig in signals:
        key = f"{sig.symbol}::{sig.strategy}::{sig.timestamp_utc}"
        if key in cache:
            continue
        fresh.append(sig)
        cache[key] = now.isoformat()
    if getattr(store, "sqlite", None):
        store.save_processed_signal_keys(cache)
    else:
        try:
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return fresh


def paper_scan_trade_payload(store: DashboardStore, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Run scanner -> one batch LLM -> open fake-money positions for approved signals."""
    state = store.load_state()
    symbols_value = updates.get("symbols") or state.get("paper_symbols") or DEFAULT_STATE["paper_symbols"]
    if isinstance(symbols_value, str):
        symbols = [item.strip() for item in symbols_value.split(",") if item.strip()]
    else:
        symbols = [str(item).strip() for item in symbols_value if str(item).strip()]
    symbols = symbols or DEFAULT_STATE["paper_symbols"]

    config = CRYPTO_TRAIN_CONFIG.copy()
    config.update({"crypto_memory_dir": str(store.memory_dir)})
    if getattr(store, "sqlite", None):
        config.update(
            {
                "crypto_storage_backend": "sqlite",
                "crypto_sqlite_path": str(store.sqlite_path),
                "crypto_user_id": store.user_id,
                "crypto_memory_space_id": store.active_memory_space_id("trade"),
            }
        )
    for key in (
        "scanner_min_strength",
        "scanner_enable_rsi_reversal",
        "scanner_enable_breakout",
        "scanner_enable_ema_crossover",
        "scanner_enable_rsi_momentum",
        "scanner_enable_trend_pullback",
        "scanner_enable_liquidity_sweep",
        "scanner_enable_range_bounce",
        "scanner_enable_bb_reversion",
        "scanner_enable_orderflow",
        "scanner_enable_regime_flip",
        "scanner_enable_ensemble",
        "scanner_ensemble_min_votes",
        "scanner_ensemble_base_bonus",
        "scanner_ensemble_max_bonus",
        "scanner_rsi_oversold",
        "scanner_rsi_extreme",
        "scanner_max_reversal_rsi",
        "scanner_max_breakout_rsi",
        "scanner_min_momentum_volume_spike",
        "scanner_min_reward_risk",
        "scanner_range_lookback",
        "scanner_range_bounce_max_pos",
        "scanner_range_min_width_atr",
        "scanner_range_min_volume_spike",
        "scanner_sideway_min_rsi",
        "scanner_sideway_max_rsi",
        "scanner_timeframe",
        "scanner_timeframes",
    ):
        if key in updates:
            config[key] = updates[key]
        elif state.get(key) is not None:
            config[key] = state[key]
    set_config(config)

    scanner = FastCryptoScanner(config)
    signals = scanner.scan(symbols)
    rsi_map: Dict[str, float] = getattr(scanner, "last_rsi_map", {})
    scan_debug: Dict[str, Dict[str, Any]] = getattr(scanner, "last_scan_map", {})
    effective_state = dict(state)
    effective_state.update({key: config[key] for key in config if key.startswith("scanner_")})
    signals, risk_rejected = _filter_scan_signals_by_risk(store, signals, effective_state)

    # Max 1 open position per symbol: skip signals for symbols already holding a position.
    open_positions = store.paper_ledger().load_positions()
    open_symbols = {p["symbol"] for p in open_positions}
    open_filtered: List[Any] = []
    for signal in signals:
        if signal.symbol not in open_symbols:
            open_filtered.append(signal)
            continue
        signal_dict = signal.to_dict()
        candidate = {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "symbol": signal_dict.get("symbol"),
            "strategy": signal_dict.get("strategy"),
            "scanner_action": signal_dict.get("action"),
            "rsi": signal_dict.get("rsi"),
            "strength": signal_dict.get("strength"),
            "market_regime": signal_dict.get("market_regime"),
            "reward_risk": _long_reward_risk(signal_dict),
            "llm_action": "SKIPPED_BEFORE_LLM",
            "llm_confidence": None,
            "llm_reasoning": "Position filter: open_position_exists",
        }
        store.save_candidate(candidate)
        risk_rejected.append(candidate)

    max_open_positions = max(1, int(float(effective_state.get("scanner_max_open_positions") or DEFAULT_STATE["scanner_max_open_positions"])))
    slots_available = max(0, max_open_positions - len(open_positions))
    if slots_available <= 0:
        for signal in open_filtered:
            signal_dict = signal.to_dict()
            candidate = {
                "scanned_at": datetime.now(timezone.utc).isoformat(),
                "symbol": signal_dict.get("symbol"),
                "strategy": signal_dict.get("strategy"),
                "scanner_action": signal_dict.get("action"),
                "rsi": signal_dict.get("rsi"),
                "strength": signal_dict.get("strength"),
                "market_regime": signal_dict.get("market_regime"),
                "reward_risk": _long_reward_risk(signal_dict),
                "llm_action": "SKIPPED_BEFORE_LLM",
                "llm_confidence": None,
                "llm_reasoning": f"Position filter: max_open_positions_reached ({max_open_positions})",
            }
            store.save_candidate(candidate)
            risk_rejected.append(candidate)
        open_filtered = []
    elif len(open_filtered) > slots_available:
        ranked = sorted(open_filtered, key=lambda sig: float(getattr(sig, "strength", 0.0) or 0.0), reverse=True)
        open_filtered = ranked[:slots_available]
        for signal in ranked[slots_available:]:
            signal_dict = signal.to_dict()
            candidate = {
                "scanned_at": datetime.now(timezone.utc).isoformat(),
                "symbol": signal_dict.get("symbol"),
                "strategy": signal_dict.get("strategy"),
                "scanner_action": signal_dict.get("action"),
                "rsi": signal_dict.get("rsi"),
                "strength": signal_dict.get("strength"),
                "market_regime": signal_dict.get("market_regime"),
                "reward_risk": _long_reward_risk(signal_dict),
                "llm_action": "SKIPPED_BEFORE_LLM",
                "llm_confidence": None,
                "llm_reasoning": f"Position filter: max_open_positions_slot_limit ({max_open_positions})",
            }
            store.save_candidate(candidate)
            risk_rejected.append(candidate)
    signals = _dedup_signals(store, open_filtered)

    if not signals:
        return {
            "operation": "paper_scan_trade",
            "status": "no_signal",
            "symbols": symbols,
            "signals": [],
            "decisions": [],
            "orders": [],
            "risk_rejected": risk_rejected,
            "rsi_map": rsi_map,
            "scan_debug": scan_debug,
            "paper": store.paper_ledger().portfolio(),
        }

    trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    runner = CryptoTrainRunner(symbols, config=config, profile="compact")
    memory = CryptoTrainingMemory(config)
    signal_contexts = [runner._signal_context(signal, trade_date, memory) for signal in signals]
    prompt = runner._compact_batch_prompt(
        trade_date,
        signal_contexts,
        get_global_crypto_news(trade_date, limit=5),
        get_crypto_fear_greed(days=7),
    )
    llm = runner._create_compact_llm()
    response = llm.invoke(prompt)
    response_text = getattr(response, "content", str(response))
    parsed = _json_from_text(response_text)
    decisions = parsed.get("decisions", []) if isinstance(parsed, dict) else []
    decision_by_symbol = {str(item.get("symbol")): item for item in decisions if isinstance(item, dict)}

    ledger = store.paper_ledger()
    orders: List[Dict[str, Any]] = []
    for signal in signals:
        decision = decision_by_symbol.get(signal.symbol, {"symbol": signal.symbol, "action": "WAIT", "reasoning": "LLM did not return a decision"})
        signal_dict = signal.to_dict()
        decision_action = str(decision.get("action") or "").upper()
        signal_strength = float(getattr(signal, "strength", signal_dict.get("strength") or 0.0))
        auto_approve_enabled = bool(updates.get("scanner_auto_approve_strong", state.get("scanner_auto_approve_strong", True)))
        auto_approve_min = _float_config_value(updates.get("scanner_auto_approve_min_strength", state.get("scanner_auto_approve_min_strength", 0.72)), 0.72)
        is_strong_signal = signal_strength >= auto_approve_min
        if decision_action != signal.action and signal.action == "BUY" and decision_action in {"", "WAIT", "HOLD"} and is_strong_signal:
            review_decision = dict(decision)
            original_action = decision_action or "WAIT"
            original_reasoning = str(decision.get("reasoning") or "")
            review_decision.update(
                {
                    "action": signal.action,
                    "confidence": max(_decision_confidence(decision) or 0.0, min(0.85, max(0.55, signal_strength))),
                    "human_review_required": True,
                    "llm_original_action": original_action,
                    "llm_original_reasoning": original_reasoning,
                    "reasoning": (
                        f"Manual review required: scanner {signal.strategy} strength={signal_strength:.3f} >= {auto_approve_min:.2f}, "
                        f"but LLM said {original_action}. {original_reasoning}"
                    ).strip(),
                }
            )
            sizing_state = dict(state)
            if "allocation_pct" in updates:
                sizing_state["paper_allocation_pct"] = float(updates["allocation_pct"])
            sizing = dynamic_sizing(store, signal_dict, review_decision, sizing_state)
            approval = create_pending_approval(store, signal_dict, review_decision, sizing, source=str(updates.get("source") or "dashboard"))
            if state.get("telegram_auto_approve_test_mode"):
                _ar = approve_pending_payload(store, approval["id"], approved_by="telegram_auto_test")
                orders.append({"status": "opened", "order": _ar.get("order"), "signal": signal_dict, "llm_decision": review_decision, "sizing": sizing, "auto_approved_test": True})
            else:
                orders.append({"status": "pending_approval", "reason": "strong_signal_llm_wait_requires_approval", "approval": approval, "signal": signal_dict, "llm_decision": review_decision, "sizing": sizing})
            store.save_candidate({
                "scanned_at": datetime.now(timezone.utc).isoformat(),
                "symbol": signal.symbol,
                "strategy": signal.strategy,
                "scanner_action": signal.action,
                "rsi": getattr(signal, "rsi", signal.to_dict().get("rsi")),
                "strength": getattr(signal, "strength", signal.to_dict().get("strength")),
                "market_regime": getattr(signal, "market_regime", signal.to_dict().get("market_regime")),
                "reward_risk": _long_reward_risk(signal_dict),
                "llm_action": original_action,
                "llm_confidence": decision.get("confidence"),
                "llm_reasoning": original_reasoning[:300],
            })
            continue
        if decision_action != signal.action:
            orders.append({"status": "skipped", "reason": "llm_action_not_matching_signal", "signal": signal.to_dict(), "llm_decision": decision})
            store.save_candidate({
                "scanned_at": datetime.now(timezone.utc).isoformat(),
                "symbol": signal.symbol,
                "strategy": signal.strategy,
                "scanner_action": signal.action,
                "rsi": getattr(signal, "rsi", signal.to_dict().get("rsi")),
                "strength": getattr(signal, "strength", signal.to_dict().get("strength")),
                "market_regime": getattr(signal, "market_regime", signal.to_dict().get("market_regime")),
                "reward_risk": _long_reward_risk(signal_dict),
                "llm_action": str(decision.get("action") or "WAIT").upper(),
                "llm_confidence": decision.get("confidence"),
                "llm_reasoning": str(decision.get("reasoning") or "")[:300],
            })
            continue
        sizing_state = dict(state)
        if "allocation_pct" in updates:
            sizing_state["paper_allocation_pct"] = float(updates["allocation_pct"])
        sizing = dynamic_sizing(store, signal_dict, decision, sizing_state)
        auto_approve = auto_approve_enabled and signal_dict.get("action") == "BUY" and is_strong_signal and decision_action == signal.action
        if auto_approve:
            decision = dict(decision)
            decision["confidence"] = max(
                _decision_confidence(decision) or 0.0,
                _float_config_value(state.get("scanner_auto_approve_min_confidence", 0.55), 0.55),
                min(0.9, signal_strength),
            )
            decision["auto_approved"] = True
            decision["auto_approve_reason"] = f"LLM agreed and signal_strength {signal_strength:.3f} >= {auto_approve_min:.2f}"
        if bool(updates.get("require_confirmation", state.get("require_confirmation", True))) and not auto_approve:
            approval = create_pending_approval(store, signal_dict, decision, sizing, source=str(updates.get("source") or "dashboard"))
            if state.get("telegram_auto_approve_test_mode"):
                _ar = approve_pending_payload(store, approval["id"], approved_by="telegram_auto_test")
                orders.append({"status": "opened", "order": _ar.get("order"), "signal": signal_dict, "llm_decision": decision, "sizing": sizing, "auto_approved_test": True})
            else:
                orders.append({"status": "pending_approval", "approval": approval, "signal": signal_dict, "llm_decision": decision, "sizing": sizing})
            continue
        order = ledger.open_position(
            signal_dict,
            decision,
            allocation_pct=float(sizing.get("allocation_pct") or 0.0),
            min_confidence=float(updates.get("min_confidence", state.get("min_confidence", 0.0))),
            notional_cap=float(sizing.get("max_position_usdt") or 0.0),
            allocation_meta=sizing,
        )
        if auto_approve:
            order["auto_approved"] = True
            order["auto_approve_reason"] = f"LLM agreed and signal_strength {signal_strength:.3f} >= {auto_approve_min:.2f}"
        order_notification = _notify_paper_order_opened(store, order)
        if order_notification:
            order["telegram"] = order_notification
        orders.append(order)

    return {
        "operation": "paper_scan_trade",
        "status": "ok",
        "symbols": symbols,
        "signals": [signal.to_dict() for signal in signals],
        "decisions": decisions,
        "orders": orders,
        "risk_rejected": risk_rejected,
        "rsi_map": rsi_map,
        "scan_debug": scan_debug,
        "llm_response": response_text,
        "paper": ledger.portfolio(),
    }


def runs_payload(store: DashboardStore, symbol: Optional[str] = None, limit: int = 80) -> Dict[str, Any]:
    rows = store.load_raw()
    if symbol:
        rows = [row for row in rows if row.get("symbol_normalized") == symbol]
    return {"runs": rows[:limit], "total": len(rows)}


def memory_payload(store: DashboardStore) -> Dict[str, Any]:
    return {
        "raw_count": len(store.load_raw()),
        "raw_recent": store.load_raw()[:25],
        "lessons": store.load_lessons(),
        "global": store.load_global(),
    }


def memory_context_payload(store: DashboardStore, symbol: Optional[str] = None) -> Dict[str, Any]:
    state = store.load_state()
    tiers = _normalize_training_memory_tiers(state.get("training_memory_tiers"))
    symbols = sorted({row.get("symbol_normalized") for row in store.load_raw() if row.get("symbol_normalized")})
    symbol = symbol or (symbols[0] if symbols else "BTC/USDT")
    memory = CryptoTrainingMemory(
        {
            "crypto_memory_dir": str(store.memory_dir),
            "crypto_training_memory_tiers": tiers,
        }
    )
    return {"symbol": symbol, "training_memory_tiers": tiers, "context": memory.get_past_context(symbol)}


def process_lessons_payload(store: DashboardStore, min_cases: int = 5) -> Dict[str, Any]:
    min_cases = max(1, int(min_cases))
    crypto_store = store.crypto_store()
    created = MemoryProcessor(crypto_store, min_cases=min_cases).process()
    return {
        "operation": "process_lessons",
        "created": len(created),
        "created_lessons": created,
        "min_cases": min_cases,
        "raw_count": len(crypto_store.load_raw()),
        "lesson_count": len(crypto_store.load_lessons()),
        "global_count": len(crypto_store.load_global()),
    }


def promote_global_payload(
    store: DashboardStore,
    min_cases: int = 30,
    min_confidence: float = 0.8,
    min_source_modes: int = 2,
    reviewed_by: str = "human-dashboard",
) -> Dict[str, Any]:
    min_cases = max(1, int(min_cases))
    min_confidence = max(0.0, min(1.0, float(min_confidence)))
    min_source_modes = max(1, int(min_source_modes))
    crypto_store = store.crypto_store()
    promoted = LessonValidator(
        crypto_store,
        min_cases=min_cases,
        min_confidence=min_confidence,
        min_source_modes=min_source_modes,
    ).promote(reviewed_by=reviewed_by or "human-dashboard")
    return {
        "operation": "promote_global",
        "promoted": len(promoted),
        "promoted_lessons": promoted,
        "min_cases": min_cases,
        "min_confidence": min_confidence,
        "min_source_modes": min_source_modes,
        "raw_count": len(crypto_store.load_raw()),
        "lesson_count": len(crypto_store.load_lessons()),
        "global_count": len(crypto_store.load_global()),
    }


HTML = r"""
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>TradingAgents Crypto Command Center</title>
  <style>
    :root {
      --bg: #07111f;
      --panel: rgba(15, 23, 42, 0.78);
      --panel-2: rgba(30, 41, 59, 0.82);
      --line: rgba(148, 163, 184, 0.18);
      --text: #e5edf7;
      --muted: #92a4b8;
      --green: #22c55e;
      --red: #ef4444;
      --yellow: #f59e0b;
      --blue: #38bdf8;
      --purple: #a78bfa;
      --shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(56, 189, 248, 0.22), transparent 32rem),
        radial-gradient(circle at 80% 10%, rgba(167, 139, 250, 0.20), transparent 26rem),
        linear-gradient(135deg, #020617 0%, #07111f 55%, #0f172a 100%);
    }
    .shell { display: grid; grid-template-columns: 280px 1fr; min-height: 100vh; }
    aside { padding: 24px; border-right: 1px solid var(--line); background: rgba(2, 6, 23, 0.44); backdrop-filter: blur(22px); }
    main { padding: 24px; }
    .brand { display: flex; align-items: center; gap: 12px; margin-bottom: 28px; }
    .logo { width: 44px; height: 44px; border-radius: 16px; display: grid; place-items: center; background: linear-gradient(135deg, var(--blue), var(--purple)); box-shadow: 0 16px 40px rgba(56, 189, 248, .22); font-size: 22px; }
    .brand h1 { margin: 0; font-size: 18px; line-height: 1.1; }
    .brand p { margin: 4px 0 0; color: var(--muted); font-size: 12px; }
    .nav button { width: 100%; margin-bottom: 8px; border: 1px solid transparent; color: var(--muted); background: transparent; border-radius: 14px; padding: 12px 14px; text-align: left; cursor: pointer; font-weight: 700; }
    .nav button.active, .nav button:hover { color: var(--text); border-color: var(--line); background: rgba(30, 41, 59, .72); }
    .side-card { margin-top: 22px; padding: 16px; border: 1px solid var(--line); border-radius: 20px; background: var(--panel); box-shadow: var(--shadow); }
    .side-card label { display: block; color: var(--muted); font-size: 12px; margin-bottom: 8px; }
    .select, .input { width: 100%; border: 1px solid var(--line); background: rgba(15, 23, 42, .82); color: var(--text); border-radius: 12px; padding: 10px 12px; outline: none; }
    .topbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 22px; }
    .title h2 { margin: 0; font-size: 28px; letter-spacing: -.03em; }
    .title p { margin: 6px 0 0; color: var(--muted); }
    .pill-row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
    .pill { padding: 9px 12px; border: 1px solid var(--line); border-radius: 999px; background: rgba(15, 23, 42, .70); color: var(--muted); font-size: 13px; font-weight: 800; }
    .pill.good { color: #bbf7d0; border-color: rgba(34,197,94,.35); background: rgba(22,101,52,.25); }
    .pill.bad { color: #fecaca; border-color: rgba(239,68,68,.35); background: rgba(127,29,29,.25); }
    .grid { display: grid; gap: 16px; }
    .kpis { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .two { grid-template-columns: 1.2fr .8fr; }
    .three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .card { border: 1px solid var(--line); border-radius: 24px; background: var(--panel); box-shadow: var(--shadow); overflow: hidden; }
    .card-body { padding: 18px; }
    .card-head { padding: 18px 18px 0; display: flex; justify-content: space-between; gap: 12px; align-items: center; }
    .card h3 { margin: 0; font-size: 15px; letter-spacing: -.01em; }
    .hero { position: relative; overflow: hidden; border: 1px solid rgba(56,189,248,.22); border-radius: 28px; padding: 22px; margin-bottom: 16px; background: linear-gradient(135deg, rgba(15,23,42,.92), rgba(30,41,59,.74)); box-shadow: var(--shadow); }
    .hero:before { content: ""; position: absolute; inset: -40% -15% auto auto; width: 340px; height: 340px; border-radius: 999px; background: radial-gradient(circle, rgba(56,189,248,.22), transparent 68%); pointer-events: none; }
    .hero h2 { margin: 0; font-size: 30px; letter-spacing: -.04em; }
    .hero p { margin: 8px 0 0; color: var(--muted); max-width: 760px; }
    .metric-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
    .metric-card { border: 1px solid var(--line); border-radius: 20px; padding: 14px; background: rgba(2,6,23,.32); }
    .metric-card .meta { display: flex; justify-content: space-between; gap: 10px; color: var(--muted); font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; }
    .metric-card .amount { font-size: 26px; font-weight: 950; margin: 10px 0 4px; letter-spacing: -.035em; }
    .metric-card .detail { color: var(--muted); font-size: 12px; line-height: 1.45; }
    .section-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
    .muted { color: var(--muted); }
    .kpi .label { color: var(--muted); font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em; }
    .kpi .value { font-size: 34px; font-weight: 900; margin: 8px 0 4px; letter-spacing: -.04em; }
    .kpi .sub { font-size: 13px; color: var(--muted); }
    .switch-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 13px 0; border-bottom: 1px solid var(--line); }
    .switch-row:last-child { border-bottom: 0; }
    .switch { position: relative; width: 54px; height: 30px; }
    .switch input { display: none; }
    .slider { position: absolute; inset: 0; border-radius: 999px; background: rgba(100,116,139,.55); cursor: pointer; transition: .2s; }
    .slider:before { content: ""; width: 24px; height: 24px; border-radius: 50%; background: white; position: absolute; left: 3px; top: 3px; transition: .2s; }
    .switch input:checked + .slider { background: linear-gradient(135deg, var(--green), var(--blue)); }
    .switch input:checked + .slider:before { transform: translateX(24px); }
    .mode-toggle { display: grid; grid-template-columns: 1fr 1fr; border: 1px solid var(--line); border-radius: 16px; overflow: hidden; }
    .mode-toggle button { border: 0; padding: 12px; color: var(--muted); background: rgba(15, 23, 42, .42); cursor: pointer; font-weight: 900; }
    .mode-toggle button.active { color: #fff; background: linear-gradient(135deg, rgba(56,189,248,.55), rgba(167,139,250,.55)); }
    .btn { border: 1px solid var(--line); color: var(--text); background: rgba(56,189,248,.16); border-radius: 12px; padding: 10px 12px; cursor: pointer; font-weight: 900; }
    .btn:hover { border-color: rgba(56,189,248,.5); background: rgba(56,189,248,.24); }
    .btn.danger { background: rgba(245,158,11,.14); }
    .btn.small { padding: 6px 9px; font-size: 12px; border-radius: 10px; }
    .pnl-good { color: #bbf7d0; font-weight: 900; }
    .pnl-bad { color: #fecaca; font-weight: 900; }
    .pager { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; margin-top: 10px; color: var(--muted); font-size: 12px; }
    .pager button { border: 1px solid var(--line); color: var(--text); background: rgba(15,23,42,.58); border-radius: 10px; padding: 6px 9px; cursor: pointer; font-weight: 800; }
    .pager button:disabled { opacity: .45; cursor: not-allowed; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 12px 10px; border-bottom: 1px solid var(--line); font-size: 13px; vertical-align: top; }
    th { color: var(--muted); text-transform: uppercase; font-size: 11px; letter-spacing: .06em; }
    .badge { display: inline-flex; align-items: center; gap: 6px; padding: 5px 9px; border-radius: 999px; font-weight: 900; font-size: 11px; border: 1px solid var(--line); }
    .badge.buy, .badge.win { color: #bbf7d0; background: rgba(22, 101, 52, .28); border-color: rgba(34,197,94,.30); }
    .badge.sell, .badge.loss { color: #fecaca; background: rgba(127, 29, 29, .32); border-color: rgba(239,68,68,.30); }
    .badge.wait, .badge.hold, .badge.flat { color: #fde68a; background: rgba(120, 53, 15, .26); border-color: rgba(245,158,11,.30); }
    .bar { height: 10px; border-radius: 99px; background: rgba(51,65,85,.8); overflow: hidden; min-width: 110px; }
    .bar span { display: block; height: 100%; background: linear-gradient(90deg, var(--red), var(--yellow), var(--green)); }
    .tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
    .tab { border: 1px solid var(--line); color: var(--muted); background: rgba(15,23,42,.58); border-radius: 12px; padding: 9px 12px; cursor: pointer; font-weight: 900; }
    .tab.active { color: #fff; background: rgba(56,189,248,.24); border-color: rgba(56,189,248,.40); }
    .memory-list { display: grid; gap: 12px; max-height: 620px; overflow: auto; padding-right: 4px; }
    .memory-item { border: 1px solid var(--line); border-radius: 16px; background: rgba(15,23,42,.56); padding: 14px; }
    .memory-item h4 { margin: 0 0 8px; font-size: 14px; }
    .memory-item p { margin: 6px 0; color: var(--muted); line-height: 1.5; }
    .json { white-space: pre-wrap; overflow-wrap: anywhere; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #bae6fd; font-size: 12px; background: rgba(2,6,23,.45); border-radius: 12px; padding: 12px; max-height: 260px; overflow: auto; }
    .checklist { display: grid; gap: 10px; }
    .check { display: flex; gap: 10px; padding: 12px; border: 1px solid var(--line); border-radius: 15px; background: rgba(15,23,42,.48); }
    .check strong { display: block; margin-bottom: 3px; }
    .check span { color: var(--muted); font-size: 13px; }
    .hidden { display: none !important; }
    @media (max-width: 1050px) { .shell { grid-template-columns: 1fr; } aside { position: static; } .kpis, .two, .three, .metric-grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand">
        <div class="logo">₿</div>
        <div><h1>Crypto Command</h1><p>TradingAgents control room</p></div>
      </div>
      <div class="nav">
        <button class="active" data-view="overview">📊 Tổng quan</button>
        <button data-view="trades">📈 Lệnh & win-rate</button>
        <button data-view="memory">🧠 Memory</button>
        <button data-view="risk">🛡️ Risk checklist</button>
                <button data-view="config">⚙️ Cấu hình</button>
      </div>
      <div class="side-card">
        <label>Symbol filter</label>
        <select id="symbolSelect" class="select"><option value="">Tất cả symbol</option></select>
      </div>
      <div class="side-card">
        <label>Memory folder</label>
        <div id="memoryPath" class="muted" style="font-size:12px; word-break:break-all"></div>
      </div>
    </aside>
    <main>
      <div class="topbar">
        <div class="title"><h2>Dashboard giao dịch crypto</h2><p>Xem mode, win-rate, cách vào lệnh và memory theo tầng.</p></div>
        <div class="pill-row"><span id="modePill" class="pill">MODE</span><span id="tradePill" class="pill">TRADING</span><span id="updatedPill" class="pill">--</span></div>
      </div>

      <section id="view-overview">
                <div class="hero">
                    <div class="section-actions">
                        <div>
                            <h2>Paper Trading Command Center</h2>
                            <p>Theo dõi equity, PnL đã/đang mở và hiệu suất ngày · tháng · năm theo thời gian thực. Config đã được tách sang route riêng để overview chỉ còn dữ liệu vận hành.</p>
                        </div>
                        <div class="pill-row">
                            <button id="paperCloseAllBtn" class="btn danger">Chốt tất cả lệnh mở</button>
                            <button id="paperMarkTopBtn" class="btn">Cập nhật giá</button>
                        </div>
                    </div>
                    <div id="paperPeriodStats" class="metric-grid"></div>
                </div>
        <div class="grid kpis">
          <div class="card kpi"><div class="card-body"><div class="label">Win-rate tổng</div><div id="kpiWin" class="value">--</div><div id="kpiWinSub" class="sub">--</div></div></div>
          <div class="card kpi"><div class="card-body"><div class="label">Avg PnL / trade</div><div id="kpiAvg" class="value">--</div><div id="kpiPnlSub" class="sub">--</div></div></div>
          <div class="card kpi"><div class="card-body"><div class="label">Global lessons</div><div id="kpiGlobal" class="value">--</div><div id="kpiLessonSub" class="sub">draft lessons</div></div></div>
          <div class="card kpi"><div class="card-body"><div class="label">Raw records</div><div id="kpiRaw" class="value">--</div><div id="kpiRawSub" class="sub">agent/backtest logs</div></div></div>
        </div>
                <div class="card" style="margin-top:16px">
                    <div class="card-head"><h3>Ví paper trading — tiền ảo training</h3><span class="muted">Scan → LLM → đặt lệnh giả → tính thắng/thua</span></div>
                    <div class="card-body">
                        <div class="grid kpis">
                            <div class="kpi"><div class="label">Số dư còn lại</div><div id="paperCash" class="value">--</div><div class="sub">USDT cash</div></div>
                            <div class="kpi"><div class="label">Equity hiện tại</div><div id="paperEquity" class="value">--</div><div id="paperPnlSub" class="sub">--</div></div>
                            <div class="kpi"><div class="label">Win-rate paper</div><div id="paperWin" class="value">--</div><div id="paperWinSub" class="sub">--</div></div>
                            <div class="kpi"><div class="label">Lệnh đang mở</div><div id="paperOpen" class="value">--</div><div class="sub">fake positions</div></div>
                        </div>
                        <div class="pill-row" style="margin-top:12px">
                            <button id="paperScanTradeBtn" class="btn">Scan + gọi LLM + đặt lệnh giả</button>
                            <button id="paperMarkBtn" class="btn">Cập nhật giá / đóng TP-SL</button>
                            <button id="paperCloseAllInlineBtn" class="btn danger">Chốt tất cả lệnh mở</button>
                            <button id="paperResetBtn" class="btn danger">Reset ví paper</button>
                        </div>
                        <div id="paperOpsResult" class="json" style="margin-top:12px; display:none"></div>
                        <div class="grid two" style="margin-top:14px">
                            <div><h3>Lệnh đang mở</h3><table><thead><tr><th>Symbol</th><th>Entry</th><th>Last</th><th>PnL</th><th>SL / TP</th><th>Notional</th><th>LLM</th><th>Action</th></tr></thead><tbody id="paperOpenRows"></tbody></table><div id="paperOpenPager" class="pager"></div></div>
                            <div><h3>Lệnh đã đóng gần đây</h3><table><thead><tr><th>Time</th><th>Symbol</th><th>Result</th><th>PnL</th><th>Exit</th></tr></thead><tbody id="paperClosedRows"></tbody></table><div id="paperClosedPager" class="pager"></div></div>
                        </div>
                        <div style="margin-top:14px"><div style="display:flex;align-items:center;gap:12px;margin-bottom:8px"><h3 style="margin:0">Lệnh chờ approve</h3><button id="approveAllBtn" class="btn" style="font-size:12px;padding:6px 10px" onclick="approveAllOrders()">✅ Approve Tất Cả</button><button id="rejectAllBtn" class="btn danger" style="font-size:12px;padding:6px 10px" onclick="rejectAllOrders()">❌ Reject Tất Cả</button></div><table><thead><tr><th>Time</th><th>Symbol</th><th>Win-rate sizing</th><th>Vốn</th><th>Action</th></tr></thead><tbody id="approvalRows"></tbody></table><div id="approvalPager" class="pager"></div></div>
                        <div style="margin-top:14px">
                          <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">
                            <h3 style="margin:0">⚠️ Scanner Candidates — skipped / LLM WAIT</h3>
                            <span class="muted" style="font-size:12px">Scanner thấy tín hiệu nhưng bị risk/position filter hoặc LLM từ chối</span>
                            <button id="clearCandidatesBtn" class="btn" style="margin-left:auto;font-size:12px;padding:6px 10px">Xóa tất cả</button>
                          </div>
                          <table><thead><tr><th>Time</th><th>Symbol</th><th>Scanner</th><th>RSI</th><th>Strength</th><th>LLM action</th><th>Conf</th><th>Reasoning</th></tr></thead><tbody id="candidateRows"></tbody></table><div id="candidatePager" class="pager"></div>
                        </div>
                    </div>
                </div>
                <div class="card" style="margin-top:16px">
                    <div class="card-head"><h3>Win-rate theo thời gian</h3><div class="tabs"><button class="tab active" data-period="daily">Ngày</button><button class="tab" data-period="weekly">Tuần</button><button class="tab" data-period="monthly">Tháng</button></div></div>
                    <div class="card-body"><table><thead><tr><th>Kỳ</th><th>Trades</th><th>Win-rate</th><th>Avg PnL</th><th>Total PnL</th></tr></thead><tbody id="periodRows"></tbody></table></div>
                </div>
      </section>

      <section id="view-trades" class="hidden">
        <div class="card"><div class="card-head"><h3>Lịch sử vào lệnh / signal</h3><span class="muted">Hiển thị entry, SL, TP, result, reasoning</span></div><div class="card-body"><table><thead><tr><th>Time</th><th>Symbol</th><th>Action</th><th>Strategy</th><th>Entry → Exit</th><th>SL / TP</th><th>Result</th><th>Confidence</th><th>Reason</th></tr></thead><tbody id="tradeRows"></tbody></table><div id="tradePager" class="pager"></div></div></div>
      </section>

      <section id="view-memory" class="hidden">
                <div class="card" style="margin-bottom:16px">
                    <div class="card-head"><h3>Nguồn memory cho training</h3><span class="muted">Điều chỉnh context đưa vào prompt</span></div>
                    <div class="card-body">
                        <div class="grid three">
                            <div class="switch-row"><div><strong>Raw memory</strong><div class="muted">Case thô, chưa review; nhiều nhiễu nhất</div></div><label class="switch"><input id="tierRaw" type="checkbox"><span class="slider"></span></label></div>
                            <div class="switch-row"><div><strong>Lesson memory</strong><div class="muted">Draft lesson đã gom thống kê</div></div><label class="switch"><input id="tierLesson" type="checkbox"><span class="slider"></span></label></div>
                            <div class="switch-row"><div><strong>Global memory</strong><div class="muted">Lesson đã validate/promote</div></div><label class="switch"><input id="tierGlobal" type="checkbox"><span class="slider"></span></label></div>
                        </div>
                        <div class="grid three" style="margin-top:12px">
                            <div><label class="muted">Symbol preview</label><input id="memoryContextSymbol" class="input" value="BTC/USDT"></div>
                            <div style="display:flex; align-items:end"><button id="saveMemoryTiersBtn" class="btn">Lưu nguồn training</button></div>
                            <div style="display:flex; align-items:end"><button id="previewMemoryContextBtn" class="btn">Preview context</button></div>
                        </div>
                        <p class="muted">Mặc định an toàn là chỉ dùng lesson. Raw có thể giúp training nhìn case thật gần đây nhưng chưa kiểm duyệt, dễ overfit/nhiễu.</p>
                        <div id="memoryContextPreview" class="json" style="display:none"></div>
                    </div>
                </div>
                <div class="card" style="margin-bottom:16px">
                    <div class="card-head"><h3>Nạp memory thủ công</h3><span class="muted">Raw → lesson draft → global validated</span></div>
                    <div class="card-body">
                        <div class="grid three">
                            <div><label class="muted">Min cases để tạo lesson</label><input id="processMinCases" class="input" type="number" min="1" value="5"></div>
                            <div><label class="muted">Min cases để promote global</label><input id="promoteMinCases" class="input" type="number" min="1" value="30"></div>
                            <div><label class="muted">Min confidence global</label><input id="promoteMinConfidence" class="input" type="number" min="0" max="1" step="0.01" value="0.8"></div>
                        </div>
                        <div class="grid three" style="margin-top:12px">
                            <div><label class="muted">Min source modes</label><input id="promoteMinModes" class="input" type="number" min="1" value="2"></div>
                            <div style="display:flex; align-items:end"><button id="processLessonsBtn" class="btn">Tạo lesson từ raw</button></div>
                            <div style="display:flex; align-items:end"><button id="promoteGlobalBtn" class="btn danger">Promote global</button></div>
                        </div>
                        <p class="muted" style="margin-bottom:0">Khuyến nghị an toàn: global nên dùng min cases ≥ 30, confidence ≥ 0.8, source modes ≥ 2. Nếu chỉ test backtest một mode, có thể hạ source modes về 1 để kiểm thử UI nhưng không nên bật trading thật.</p>
                        <div id="memoryOpsResult" class="json" style="margin-top:12px; display:none"></div>
                    </div>
                </div>
                <div class="grid three">
          <div class="card"><div class="card-head"><h3>Global memory</h3><span class="muted">Trade mode chỉ được đọc tầng này</span></div><div class="card-body"><div id="globalMemory" class="memory-list"></div><div id="globalMemoryPager" class="pager"></div></div></div>
          <div class="card"><div class="card-head"><h3>Lesson draft</h3><span class="muted">Hypothesis, chưa dùng để trade thật</span></div><div class="card-body"><div id="lessonMemory" class="memory-list"></div><div id="lessonMemoryPager" class="pager"></div></div></div>
                    <div class="card"><div class="card-head"><h3>Raw memory</h3><span class="muted">25 case gần nhất</span></div><div class="card-body"><div id="rawMemory" class="memory-list"></div><div id="rawMemoryPager" class="pager"></div></div></div>
        </div>
      </section>

      <section id="view-risk" class="hidden">
        <div class="grid two">
          <div class="card"><div class="card-head"><h3>Các phần quan trọng còn thiếu / cần theo dõi</h3><span class="muted">Senior trade checklist</span></div><div class="card-body"><div class="checklist" id="riskChecklist"></div></div></div>
          <div class="card"><div class="card-head"><h3>Action distribution</h3><span class="muted">Tỷ lệ BUY/SELL/WAIT</span></div><div class="card-body"><table><thead><tr><th>Action</th><th>Số lần</th><th>Tỷ trọng</th></tr></thead><tbody id="actionRows"></tbody></table></div></div>
        </div>
      </section>

            <section id="view-config" class="hidden">
                <div class="grid two">
                    <div class="card">
                        <div class="card-head"><h3>Điều khiển mode</h3><span class="muted">Local dashboard state</span></div>
                        <div class="card-body">
                            <div class="mode-toggle"><button id="trainingBtn">Training</button><button id="tradeBtn">Trade</button></div>
                            <div class="switch-row"><div><strong>Bật trading</strong><div class="muted">Chỉ nên bật sau khi có global memory tốt</div></div><label class="switch"><input id="tradingEnabled" type="checkbox"><span class="slider"></span></label></div>
                            <div class="switch-row"><div><strong>Dry-run</strong><div class="muted">Không gửi lệnh thật</div></div><label class="switch"><input id="dryRun" type="checkbox"><span class="slider"></span></label></div>
                            <div class="switch-row"><div><strong>Yêu cầu xác nhận</strong><div class="muted">Human confirm trước executor</div></div><label class="switch"><input id="requireConfirm" type="checkbox"><span class="slider"></span></label></div>
                            <div style="margin-top:14px"><label class="muted">Min confidence để trade</label><input id="minConfidence" class="input" type="number" min="0" max="1" step="0.01"></div>
                            <div style="margin-top:14px"><label class="muted">Training memory tiers</label><div id="trainingTierSummary" class="json" style="max-height:80px"></div></div>
                        </div>
                    </div>
                    <div class="card">
                        <div class="card-head"><h3>Scheduler & Telegram</h3><span class="muted">Auto scan / approval</span></div>
                        <div class="card-body">
                            <div class="switch-row"><div><strong>Auto scan</strong><div class="muted">Chạy scan định kỳ theo số phút đã set</div></div><label class="switch"><input id="autoScanEnabled" type="checkbox"><span class="slider"></span></label></div>
                            <div class="switch-row"><div><strong>Telegram approval</strong><div class="muted">Gửi lệnh lên Telegram để bấm approve/reject</div></div><label class="switch"><input id="telegramEnabled" type="checkbox"><span class="slider"></span></label></div>
                            <div class="switch-row"><div><strong>Telegram auto-approve (test)</strong><div class="muted">Tự động approve mọi lệnh pending — chỉ dùng khi test, không dùng thật</div></div><label class="switch"><input id="telegramAutoApproveTestMode" type="checkbox"><span class="slider"></span></label></div>
                            <div style="margin-top:14px"><label class="muted">Telegram bot token</label><input id="telegramBotToken" class="input" type="password" placeholder="Có thể để trống nếu dùng TELEGRAM_BOT_TOKEN trong .env"></div>
                            <div style="margin-top:14px"><label class="muted">Telegram chat id</label><input id="telegramChatId" class="input" placeholder="Có thể để trống nếu dùng TELEGRAM_CHAT_ID trong .env"></div>
                            <div class="pill-row" style="margin-top:12px"><button id="telegramTestBtn" class="btn">Test Telegram</button><button id="telegramPollBtn" class="btn">Poll approvals</button></div>
                        </div>
                    </div>
                </div>
                <div class="card" style="margin-top:16px">
                    <div class="card-head"><h3>Sizing / Scanner / Scheduler</h3><span class="muted">Các config đã được chuyển khỏi tab tổng quan</span></div>
                    <div class="card-body">
                        <div class="grid three">
                            <div><label class="muted">Nạp tiền ảo (USDT)</label><input id="paperDepositAmount" class="input" type="number" min="1" value="1000"></div>
                            <div><label class="muted">Symbols scan</label><input id="paperSymbols" class="input" value="BTC/USDT,ETH/USDT,SOL/USDT,XRP/USDT,BNB/USDT,DOGE/USDT,AVAX/USDT,LINK/USDT,TON/USDT,SUI/USDT,DOT/USDT,NEAR/USDT,APT/USDT,OP/USDT,ARB/USDT"></div>
                            <div><label class="muted">Base vốn/lệnh</label><input id="paperAllocationPct" class="input" type="number" min="0.01" max="1" step="0.01" value="0.05"></div>
                        </div>
                        <div class="grid three" style="margin-top:12px">
                            <div><label class="muted">Min vốn/lệnh</label><input id="paperMinAllocationPct" class="input" type="number" min="0" max="1" step="0.01" value="0.02"></div>
                            <div><label class="muted">Max % cash/lệnh</label><input id="maxPositionPct" class="input" type="number" min="0.01" max="1" step="0.01" value="0.10"></div>
                            <div><label class="muted">Max USDT/lệnh</label><input id="maxPositionUsdt" class="input" type="number" min="0" step="1" value="100"></div>
                        </div>
                        <div class="grid three" style="margin-top:12px">
                            <div><label class="muted">Max lệnh mở đồng thời</label><input id="scannerMaxOpenPositions" class="input" type="number" min="1" step="1" value="5" title="Giới hạn tổng vị thế mở để tránh mở cả batch coin tương quan cùng lúc"></div>
                            <div><label class="muted">User hiện tại</label><input id="activeUserId" class="input" disabled value="admin"></div>
                            <div><label class="muted">Trade memory space</label><input id="tradeMemorySpaceId" class="input" value="default" title="SQLite mode: chỉ admin được đổi memory space dùng cho trade"></div>
                        </div>
                        <div class="grid three" style="margin-top:12px">
                            <div><label class="muted">Min trades để tin win-rate</label><input id="sizingMinTrades" class="input" type="number" min="1" step="1" value="5"></div>
                            <div><label class="muted">Scan interval phút</label><input id="scanIntervalMinutes" class="input" type="number" min="1" step="1" value="10"></div>
                            <div><label class="muted">Scanner timeframe</label><select id="scannerTimeframe" class="input" title="Khung thời gian nến để tính RSI scanner (1h = RSI swing rõ hơn)"><option value="15m">15m</option><option value="1h" selected>1h</option><option value="4h">4h</option></select></div>
                        </div>
                        <div class="grid three" style="margin-top:12px">
                            <div><label class="muted">RSI oversold threshold</label><input id="scannerRsiOversold" class="input" type="number" min="20" max="50" step="1" value="38" title="Signal khi RSI thấp hơn ngưỡng này"></div>
                            <div><label class="muted">RSI extreme threshold</label><input id="scannerRsiExtreme" class="input" type="number" min="10" max="40" step="1" value="25" title="RSI cực thấp: cho phép reversal không cần recovery candle"></div>
                            <div><label class="muted">Min strength scanner</label><input id="scannerMinStrength" class="input" type="number" min="0.1" max="1" step="0.05" value="0.50" title="Độ mạnh tối thiểu của tín hiệu kỹ thuật"></div>
                        </div>
                        <div class="grid three" style="margin-top:12px">
                            <div><label class="muted">Range bounce vùng đáy</label><input id="scannerRangeBounceMaxPos" class="input" type="number" min="0.10" max="0.45" step="0.01" value="0.35" title="0.35 = mua khi giá ở 35% đáy range thay vì chỉ 28%"></div>
                            <div><label class="muted">Range width min (ATR)</label><input id="scannerRangeMinWidthAtr" class="input" type="number" min="1" max="5" step="0.1" value="1.6" title="Nới từ 2.4 xuống 1.6 để bắt sideway nén/chop nhiều hơn"></div>
                            <div><label class="muted">Sideway RSI min</label><input id="scannerSidewayMinRsi" class="input" type="number" min="10" max="60" step="1" value="28" title="Cho phép range bounce khi RSI tụt sâu ở đáy range"></div>
                        </div>
                        <div class="grid three" style="margin-top:12px">
                            <div><label class="muted">Sideway RSI max</label><input id="scannerSidewayMaxRsi" class="input" type="number" min="30" max="90" step="1" value="65" title="Nới trần RSI sideway để không bỏ lỡ bounce khi RSI hồi nhanh"></div>
                            <div><label class="muted">Ngưỡng strong + LLM đồng ý</label><input id="scannerAutoApproveMinStrength" class="input" type="number" min="0.5" max="1" step="0.01" value="0.72" title="Chỉ auto-open khi scanner đủ strong và LLM cũng trả BUY. Nếu LLM WAIT thì vẫn cần approve."></div>
                            <div><label class="muted">Max giữ lệnh (giờ)</label><input id="scannerMaxHoldHours" class="input" type="number" min="0" step="1" value="24" title="0 = tắt time exit; mặc định 24h để tránh vốn bị treo quá lâu"></div>
                        </div>
                        <div class="grid three" style="margin-top:12px">
                            <div><label class="muted">Breakeven trigger (%)</label><input id="scannerBreakevenTriggerPct" class="input" type="number" min="0" step="0.1" value="0.6" title="Khi lệnh lời tới ngưỡng này, SL được kéo về entry"></div>
                            <div><label class="muted">Trailing stop (%)</label><input id="scannerTrailingStopPct" class="input" type="number" min="0" step="0.1" value="0.5" title="Sau khi có lời, SL bám theo đỉnh để bảo vệ profit"></div>
                            <div style="display:flex;align-items:end;gap:12px"><button id="saveRiskBtn" class="btn">Lưu sizing/scanner/scheduler</button><span id="unsavedBadge" style="display:none;background:#e6b800;color:#000;padding:2px 8px;border-radius:4px;font-size:0.8em;font-weight:600">⚠ Chưa lưu</span><button id="paperDepositBtn" class="btn">Nạp tiền ảo</button></div>
                        </div>
                    </div>
                </div>
                <div class="card" style="margin-top:16px">
                    <div class="card-head"><h3>Strategy scanner theo regime</h3><span class="muted">Mặc định tắt trend strategies, giữ nhóm sideway/reversal</span></div>
                    <div class="card-body">
                        <div class="grid three">
                            <div>
                                <h3>Down trend / Reversal</h3>
                                <div class="switch-row"><div><strong>RSI reversal</strong><div class="muted">Bắt hồi khi RSI quá bán trong trend_down/sideway</div></div><label class="switch"><input id="scannerEnableRsiReversal" type="checkbox"><span class="slider"></span></label></div>
                                <div class="switch-row"><div><strong>Breakout / breakdown</strong><div class="muted">Breakdown SELL hoặc breakout BUY theo volume</div></div><label class="switch"><input id="scannerEnableBreakout" type="checkbox"><span class="slider"></span></label></div>
                            </div>
                            <div>
                                <h3>Up trend / Momentum</h3>
                                <div class="switch-row"><div><strong>EMA crossover</strong><div class="muted">EMA10 cắt SMA50 trong trend_up</div></div><label class="switch"><input id="scannerEnableEmaCrossover" type="checkbox"><span class="slider"></span></label></div>
                                <div class="switch-row"><div><strong>RSI momentum</strong><div class="muted">RSI vượt 50, giá trên EMA10</div></div><label class="switch"><input id="scannerEnableRsiMomentum" type="checkbox"><span class="slider"></span></label></div>
                                <div class="switch-row"><div><strong>Trend pullback</strong><div class="muted">Giá reclaim EMA10 trong trend_up</div></div><label class="switch"><input id="scannerEnableTrendPullback" type="checkbox"><span class="slider"></span></label></div>
                                <div class="switch-row"><div><strong>Orderflow approx</strong><div class="muted">Volume-weighted candle delta</div></div><label class="switch"><input id="scannerEnableOrderflow" type="checkbox"><span class="slider"></span></label></div>
                                <div class="switch-row"><div><strong>Regime flip</strong><div class="muted">Sideway/down vừa chuyển sang trend_up</div></div><label class="switch"><input id="scannerEnableRegimeFlip" type="checkbox"><span class="slider"></span></label></div>
                            </div>
                            <div>
                                <h3>Sideway / Mean reversion</h3>
                                <div class="switch-row"><div><strong>Liquidity sweep</strong><div class="muted">Quét swing low rồi đóng lại trên vùng quét</div></div><label class="switch"><input id="scannerEnableLiquiditySweep" type="checkbox"><span class="slider"></span></label></div>
                                <div class="switch-row"><div><strong>Range bounce</strong><div class="muted">Mua vùng 35% đáy range, RSI 28–65</div></div><label class="switch"><input id="scannerEnableRangeBounce" type="checkbox"><span class="slider"></span></label></div>
                                <div class="switch-row"><div><strong>BB reversion</strong><div class="muted">Giá reclaim lower volatility band</div></div><label class="switch"><input id="scannerEnableBbReversion" type="checkbox"><span class="slider"></span></label></div>
                                <div class="switch-row"><div><strong>Ensemble</strong><div class="muted">Gộp nhiều BUY strategies khi đủ vote</div></div><label class="switch"><input id="scannerEnableEnsemble" type="checkbox"><span class="slider"></span></label></div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <div class="card-head"><h3>Route cấu hình riêng</h3><span class="muted">GET /api/config · POST /api/config</span></div>
                    <div class="card-body">
                        <p class="muted">Config runtime, scheduler, scanner, sizing, Telegram và memory space đã được tách khỏi overview payload. Overview chỉ còn dữ liệu tổng quan/analytics.</p>
                        <div id="configSummary" class="json"></div>
                    </div>
                </div>
            </section>
    </main>
  </div>

<script>
const hasNumber = (v) => v !== null && v !== undefined && Number.isFinite(Number(v));
const fmtPct = (v) => hasNumber(v) ? `${(Number(v) * 100).toFixed(1)}%` : '—';
const fmtPnl = (v) => hasNumber(v) ? `${Number(v).toFixed(4)}%` : '—';
const fmtMoney = (v) => `${Number(v || 0).toFixed(2)} USDT`;
const fmtPaperPct = (v) => hasNumber(v) ? `${Number(v).toFixed(2)}%` : '—';
const numVal = (id, fallback) => {
    const raw = String(document.getElementById(id).value || '').replace(',', '.');
    const value = Number(raw);
    return Number.isFinite(value) ? value : fallback;
};
const checkedVal = (id) => !!document.getElementById(id).checked;
const setChecked = (id, value) => { document.getElementById(id).checked = !!value; };
const PAGE_SIZE = 8;
let pages = { openPositions: 1, closedTrades: 1, approvals: 1, candidates: 1, trades: 1, globalMemory: 1, lessonMemory: 1, rawMemory: 1 };
let state = { period: 'daily', symbol: '' };
let overview = null;
let config = null;
let trading = null;
let configDirty = false;

function currentPageItems(name, rows, pageSize=PAGE_SIZE) {
    const totalPages = Math.max(1, Math.ceil((rows || []).length / pageSize));
    pages[name] = Math.min(Math.max(1, pages[name] || 1), totalPages);
    const start = (pages[name] - 1) * pageSize;
    return (rows || []).slice(start, start + pageSize);
}

function pagerHtml(name, total, pageSize=PAGE_SIZE) {
    const totalPages = Math.max(1, Math.ceil((total || 0) / pageSize));
    if (totalPages <= 1) return '';
    const page = Math.min(Math.max(1, pages[name] || 1), totalPages);
    return `<span>Trang ${page}/${totalPages} · ${total} dòng</span><button ${page <= 1 ? 'disabled' : ''} onclick="setPage('${name}', ${page - 1})">‹ Trước</button><button ${page >= totalPages ? 'disabled' : ''} onclick="setPage('${name}', ${page + 1})">Sau ›</button>`;
}

function setPage(name, page) {
    pages[name] = page;
    refresh();
}

function openPositionPnlPct(position) {
    const entry = Number(position.entry_price || 0);
    const last = Number(position.last_price ?? position.entry_price ?? 0);
    if (!entry || !Number.isFinite(entry) || !Number.isFinite(last)) return null;
    return ((last - entry) / entry) * 100;
}

function pnlClass(value) {
    return Number(value || 0) >= 0 ? 'pnl-good' : 'pnl-bad';
}

async function api(path, options={}) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

function badge(text) {
  const cls = String(text || '').toLowerCase();
  return `<span class="badge ${cls}">${text || '—'}</span>`;
}

function short(text, n=140) {
  text = String(text || '');
  return text.length > n ? text.slice(0, n) + '…' : text;
}

async function refresh() {
  const qs = state.symbol ? `?symbol=${encodeURIComponent(state.symbol)}` : '';
    [overview, config, trading] = await Promise.all([
        api('/api/overview' + qs),
        api('/api/config'),
        api('/api/trading'),
    ]);
  renderOverview();
  renderPeriods();
  renderActions();
    renderConfigSummary();
  await renderTrades();
  await renderMemory();
  await renderCandidates();
}

function renderPerformance(performance) {
        const rows = (performance || {}).periods || [];
        document.getElementById('paperPeriodStats').innerHTML = rows.map(row => {
                const pnl = Number(row.pnl_amount || 0);
                const pct = Number(row.pnl_pct || 0);
                const cls = pnl >= 0 ? 'pnl-good' : 'pnl-bad';
                return `<div class="metric-card">
                        <div class="meta"><span>${row.label}</span><span>${row.bucket}</span></div>
                        <div class="amount ${cls}">${fmtMoney(pnl)}</div>
                        <div class="detail">${fmtPaperPct(pct)} trên exposure ${fmtMoney(row.basis_usdt)}<br>Realized ${fmtMoney(row.realized_pnl)} · Open ${fmtMoney(row.unrealized_pnl)}<br>${row.closed_trades} closed · ${row.open_positions} open · WR ${fmtPct(row.win_rate)}</div>
                </div>`;
        }).join('') || '<div class="metric-card"><div class="detail">Chưa có dữ liệu PnL theo kỳ.</div></div>';
}

function renderConfigSummary() {
        const st = (config || {}).state || {};
        const paths = (config || {}).paths || {};
        const grouped = {
                runtime: { mode: st.mode, trading_enabled: st.trading_enabled, dry_run: st.dry_run, require_confirmation: st.require_confirmation, auto_scan_enabled: st.auto_scan_enabled },
                sizing: { max_position_usdt: st.max_position_usdt, max_position_pct: st.max_position_pct, paper_allocation_pct: st.paper_allocation_pct, scanner_max_open_positions: st.scanner_max_open_positions },
                scanner: { timeframe: st.scanner_timeframe, min_strength: st.scanner_min_strength, max_hold_hours: st.scanner_max_hold_hours, breakeven_trigger_pct: st.scanner_breakeven_trigger_pct, trailing_stop_pct: st.scanner_trailing_stop_pct },
                sideway_tuning: { range_bounce_max_pos: st.scanner_range_bounce_max_pos, range_min_width_atr: st.scanner_range_min_width_atr, sideway_min_rsi: st.scanner_sideway_min_rsi, sideway_max_rsi: st.scanner_sideway_max_rsi },
                strategies: {
                    down_trend: { rsi_reversal: st.scanner_enable_rsi_reversal, breakout_breakdown: st.scanner_enable_breakout },
                    up_trend: { ema_crossover: st.scanner_enable_ema_crossover, rsi_momentum: st.scanner_enable_rsi_momentum, trend_pullback: st.scanner_enable_trend_pullback, orderflow_approx: st.scanner_enable_orderflow, regime_flip: st.scanner_enable_regime_flip },
                    sideway: { liquidity_sweep: st.scanner_enable_liquidity_sweep, range_bounce: st.scanner_enable_range_bounce, bb_reversion: st.scanner_enable_bb_reversion, ensemble: st.scanner_enable_ensemble },
                },
                memory: { storage_backend: st.storage_backend, active_user_id: st.active_user_id, training_memory_space_id: st.training_memory_space_id, trade_memory_space_id: st.trade_memory_space_id, memory_dir: paths.memory_dir },
                telegram: { enabled: st.telegram_enabled, chat_id: st.telegram_chat_id ? 'configured' : 'empty', bot_token: st.telegram_bot_token ? 'configured' : 'empty' },
        };
        document.getElementById('configSummary').textContent = JSON.stringify(grouped, null, 2);
}

function renderOverview() {
  const c = overview.counts;
  document.getElementById('kpiWin').textContent = fmtPct(c.win_rate);
  document.getElementById('kpiWinSub').textContent = `${c.wins} wins / ${c.losses} losses / ${c.trades} trades`;
  document.getElementById('kpiAvg').textContent = fmtPnl(c.avg_pnl);
  document.getElementById('kpiPnlSub').textContent = `Total PnL ${fmtPnl(c.total_pnl)}`;
  document.getElementById('kpiGlobal').textContent = c.global;
  document.getElementById('kpiLessonSub').textContent = `${c.lessons} draft lessons`;
  document.getElementById('kpiRaw').textContent = c.raw;
    document.getElementById('memoryPath').textContent = ((config || {}).paths || {}).memory_dir || '—';
    const st = ((config || {}).state || {});
  document.getElementById('modePill').textContent = st.mode === 'trade' ? 'TRADE MODE' : 'TRAINING MODE';
  document.getElementById('modePill').className = 'pill ' + (st.mode === 'trade' ? 'good' : '');
  document.getElementById('tradePill').textContent = st.trading_enabled ? 'TRADING ON' : 'TRADING OFF';
  document.getElementById('tradePill').className = 'pill ' + (st.trading_enabled ? 'bad' : 'good');
  document.getElementById('updatedPill').textContent = 'Updated now';
  document.getElementById('trainingBtn').classList.toggle('active', st.mode === 'training');
  document.getElementById('tradeBtn').classList.toggle('active', st.mode === 'trade');
  document.getElementById('tradingEnabled').checked = !!st.trading_enabled;
  document.getElementById('dryRun').checked = !!st.dry_run;
  document.getElementById('requireConfirm').checked = !!st.require_confirmation;
    document.getElementById('autoScanEnabled').checked = !!st.auto_scan_enabled;
    document.getElementById('telegramEnabled').checked = !!st.telegram_enabled;
    document.getElementById('telegramAutoApproveTestMode').checked = !!st.telegram_auto_approve_test_mode;
    document.getElementById('telegramBotToken').value = st.telegram_bot_token || '';
    document.getElementById('telegramChatId').value = st.telegram_chat_id || '';
  document.getElementById('minConfidence').value = st.min_confidence;
    if (!configDirty) {
    document.getElementById('scanIntervalMinutes').value = st.scan_interval_minutes || 10;
    document.getElementById('scannerTimeframe').value = st.scanner_timeframe || '1h';
    document.getElementById('scannerRsiOversold').value = st.scanner_rsi_oversold || 38;
    document.getElementById('scannerRsiExtreme').value = st.scanner_rsi_extreme || 25;
    document.getElementById('scannerMinStrength').value = st.scanner_min_strength || 0.50;
    document.getElementById('scannerRangeBounceMaxPos').value = st.scanner_range_bounce_max_pos ?? 0.35;
    document.getElementById('scannerRangeMinWidthAtr').value = st.scanner_range_min_width_atr ?? 1.6;
    document.getElementById('scannerSidewayMinRsi').value = st.scanner_sideway_min_rsi ?? 28;
    document.getElementById('scannerSidewayMaxRsi').value = st.scanner_sideway_max_rsi ?? 65;
        document.getElementById('scannerAutoApproveMinStrength').value = st.scanner_auto_approve_min_strength || 0.72;
        document.getElementById('scannerMaxHoldHours').value = st.scanner_max_hold_hours ?? 24;
        document.getElementById('scannerBreakevenTriggerPct').value = st.scanner_breakeven_trigger_pct ?? 0.6;
        document.getElementById('scannerTrailingStopPct').value = st.scanner_trailing_stop_pct ?? 0.5;
    setChecked('scannerEnableRsiReversal', st.scanner_enable_rsi_reversal ?? true);
    setChecked('scannerEnableBreakout', st.scanner_enable_breakout);
    setChecked('scannerEnableEmaCrossover', st.scanner_enable_ema_crossover);
    setChecked('scannerEnableRsiMomentum', st.scanner_enable_rsi_momentum);
    setChecked('scannerEnableTrendPullback', st.scanner_enable_trend_pullback);
    setChecked('scannerEnableOrderflow', st.scanner_enable_orderflow);
    setChecked('scannerEnableRegimeFlip', st.scanner_enable_regime_flip);
    setChecked('scannerEnableLiquiditySweep', st.scanner_enable_liquidity_sweep ?? true);
    setChecked('scannerEnableRangeBounce', st.scanner_enable_range_bounce ?? true);
    setChecked('scannerEnableBbReversion', st.scanner_enable_bb_reversion ?? true);
    setChecked('scannerEnableEnsemble', st.scanner_enable_ensemble ?? true);
    renderTrainingTiers(st.training_memory_tiers || ['lesson']);
    }
    renderPerformance((trading || {}).performance || {});
    renderPaperWallet(((trading || {}).paper || {}));
  const select = document.getElementById('symbolSelect');
  const current = select.value;
  select.innerHTML = '<option value="">Tất cả symbol</option>' + overview.symbols.map(s => `<option value="${s}">${s}</option>`).join('');
  select.value = current;
}

function renderPaperWallet(paper) {
    const stats = paper.stats || {};
    const account = paper.account || {};
    const st = ((config || {}).state || {});
    document.getElementById('paperCash').textContent = fmtMoney(paper.cash);
    document.getElementById('paperEquity').textContent = fmtMoney(paper.equity);
    document.getElementById('paperPnlSub').textContent = `P&L ${fmtMoney(paper.total_pnl)} (${fmtPaperPct(paper.total_pnl_pct)}) · Deposit ${fmtMoney(paper.total_deposits)}`;
    document.getElementById('paperWin').textContent = fmtPct(stats.win_rate);
    document.getElementById('paperWinSub').textContent = `${stats.wins || 0} wins / ${stats.losses || 0} losses / ${stats.closed_trades || 0} closed`;
    document.getElementById('paperOpen').textContent = stats.open_positions || 0;
    if (!configDirty) {
    document.getElementById('paperSymbols').value = (st.paper_symbols || []).join(',');
    document.getElementById('paperAllocationPct').value = st.paper_allocation_pct || 0.10;
    document.getElementById('paperMinAllocationPct').value = st.paper_min_allocation_pct || 0.02;
    document.getElementById('maxPositionPct').value = st.max_position_pct || 0.10;
    document.getElementById('maxPositionUsdt').value = st.max_position_usdt || 100;
    document.getElementById('scannerMaxOpenPositions').value = st.scanner_max_open_positions || 5;
    document.getElementById('activeUserId').value = st.active_user_id || 'admin';
    document.getElementById('tradeMemorySpaceId').value = st.trade_memory_space_id || 'default';
    document.getElementById('sizingMinTrades').value = st.sizing_min_trades || 5;
    }
    const openPositions = paper.open_positions || [];
    const openPage = currentPageItems('openPositions', openPositions);
    document.getElementById('paperOpenRows').innerHTML = openPage.map(p => {
        const pnlPct = openPositionPnlPct(p);
        const pnlAmount = hasNumber(pnlPct) ? Number(p.notional || 0) * Number(pnlPct) / 100 : null;
        return `<tr><td><strong>${p.symbol}</strong><br><span class="muted">${p.strategy || ''}</span></td><td>${p.entry_price}</td><td>${p.last_price ?? '—'}</td><td><span class="${pnlClass(pnlPct)}">${fmtPaperPct(pnlPct)}</span><br><span class="muted">${hasNumber(pnlAmount) ? fmtMoney(pnlAmount) : '—'}</span></td><td>${p.stop_loss} / ${p.take_profit}</td><td>${fmtMoney(p.notional)}</td><td>${fmtPct(p.confidence || 0)}<br><span class="muted">${short((p.llm_decision || {}).reasoning || '', 90)}</span></td><td><button class="btn small danger" onclick="forceClosePosition('${p.id}', '${p.symbol}')">Chốt giá</button></td></tr>`;
    }).join('') || '<tr><td colspan="8" class="muted">Chưa có lệnh paper đang mở.</td></tr>';
    document.getElementById('paperOpenPager').innerHTML = pagerHtml('openPositions', openPositions.length);
    const closedTrades = paper.closed_trades || [];
    const closedPage = currentPageItems('closedTrades', closedTrades);
    document.getElementById('paperClosedRows').innerHTML = closedPage.map(t => `
        <tr><td>${t.closed_at || t.timestamp_utc || '—'}</td><td><strong>${t.symbol || t.coin}</strong></td><td>${badge(t.result)}</td><td>${fmtPaperPct(t.pnl_pct ?? t.pnl)}<br><span class="muted">${fmtMoney(t.pnl_amount)}</span></td><td>${t.exit_price ?? t.exit ?? '—'}<br><span class="muted">${t.exit_reason || ''}</span></td></tr>
    `).join('') || '<tr><td colspan="5" class="muted">Chưa có lệnh paper đã đóng.</td></tr>';
    document.getElementById('paperClosedPager').innerHTML = pagerHtml('closedTrades', closedTrades.length);
    const approvals = (((trading || {}).approvals || {}).recent || []).filter(a => a.status === 'pending');
    const approvalPage = currentPageItems('approvals', approvals);
    document.getElementById('approvalRows').innerHTML = approvalPage.map(a => {
        const sizing = a.sizing || {}; const stats = sizing.stats || {}; const sig = a.signal || {};
        const wr = hasNumber(stats.win_rate) ? `${(Number(stats.win_rate)*100).toFixed(1)}% (${stats.wins}W/${stats.losses}L)` : `chưa đủ mẫu (${stats.closed_trades || 0}/${sizing.min_trades || 0})`;
        return `<tr><td>${a.created_at || '—'}</td><td><strong>${sig.symbol}</strong><br><span class="muted">${sig.strategy || ''}</span></td><td>${wr}<br><span class="muted">${sizing.reason || ''}</span></td><td>${fmtMoney(sizing.notional_usdt)}<br><span class="muted">${(Number(sizing.allocation_pct || 0)*100).toFixed(2)}%</span></td><td><button class="btn" onclick="approveOrder('${a.id}')">Approve</button> <button class="btn danger" onclick="rejectOrder('${a.id}')">Reject</button></td></tr>`;
    }).join('') || '<tr><td colspan="5" class="muted">Không có lệnh chờ approve.</td></tr>';
    document.getElementById('approvalPager').innerHTML = pagerHtml('approvals', approvals.length);
    if (Number(account.cash || 0) <= 0 && Number(account.total_deposits || 0) <= 0) {
        document.getElementById('paperOpsResult').style.display = 'block';
        document.getElementById('paperOpsResult').textContent = 'Hãy nạp tiền ảo trước khi chạy scan + đặt lệnh giả.';
    } else if (document.getElementById('paperOpsResult').textContent.startsWith('Hãy nạp')) {
        document.getElementById('paperOpsResult').style.display = 'none';
    }
}

async function renderCandidates() {
    const payload = await api('/api/paper/candidates?limit=50');
    const rows = (payload.candidates || []);
    const pageRows = currentPageItems('candidates', rows);
    document.getElementById('candidateRows').innerHTML = pageRows.map(c => {
        const t = (c.scanned_at || '').replace('T', ' ').substring(0, 16);
        const conf = hasNumber(c.llm_confidence) ? (Number(c.llm_confidence) < 1 ? (Number(c.llm_confidence)*100).toFixed(0)+'%' : c.llm_confidence+'%') : '—';
        const rsi = hasNumber(c.rsi) ? Number(c.rsi).toFixed(1) : '—';
        const str = hasNumber(c.strength) ? Number(c.strength).toFixed(2) : '—';
        return `<tr>
            <td><span class="muted">${t}</span></td>
            <td><strong>${c.symbol || '—'}</strong></td>
            <td>${badge(c.scanner_action || 'BUY')}</td>
            <td>${rsi}</td>
            <td>${str}</td>
            <td><span class="badge wait">${c.llm_action || 'WAIT'}</span></td>
            <td>${conf}</td>
            <td class="muted">${short(c.llm_reasoning || '', 160)}</td>
        </tr>`;
    }).join('') || '<tr><td colspan="8" class="muted">Chưa có candidate nào. Scanner candidates sẽ xuất hiện khi scanner thấy tín hiệu nhưng LLM trả về WAIT.</td></tr>';
    document.getElementById('candidatePager').innerHTML = pagerHtml('candidates', rows.length);
}

function renderPeriods() {
  const rows = overview[state.period] || [];
  document.getElementById('periodRows').innerHTML = rows.map(r => `
    <tr><td><strong>${r.bucket}</strong></td><td>${r.trades}</td><td><div class="bar"><span style="width:${hasNumber(r.win_rate) ? Math.max(2, r.win_rate*100) : 0}%"></span></div><div class="muted">${fmtPct(r.win_rate)}</div></td><td>${fmtPnl(r.avg_pnl)}</td><td>${fmtPnl(r.total_pnl)}</td></tr>
  `).join('') || '<tr><td colspan="5" class="muted">Chưa có trade đã đóng để tính win-rate.</td></tr>';
}

async function renderTrades() {
  const qs = state.symbol ? `?symbol=${encodeURIComponent(state.symbol)}&limit=120` : '?limit=120';
  const payload = await api('/api/runs' + qs);
    const rows = payload.runs || [];
    const pageRows = currentPageItems('trades', rows);
    document.getElementById('tradeRows').innerHTML = pageRows.map(r => {
    const reason = r.reasoning || r.final_trade_decision || '';
    return `<tr>
      <td>${r.timestamp_normalized || r.date_normalized || '—'}</td><td><strong>${r.symbol_normalized}</strong></td><td>${badge(r.action_normalized)}</td><td>${r.strategy || '—'}</td>
      <td>${r.entry ?? '—'} ${r.exit !== undefined ? '→ ' + r.exit : ''}<br><span class="muted">PnL ${r.pnl_normalized === null ? '—' : fmtPnl(r.pnl_normalized)}</span></td>
      <td>${r.stop_loss ?? '—'} / ${r.take_profit ?? '—'}</td><td>${badge(r.result_normalized || r.rating || '—')}</td><td>${r.confidence_normalized === null ? '—' : fmtPct(r.confidence_normalized)}</td><td class="muted">${short(reason, 180)}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="9" class="muted">Chưa có dữ liệu lệnh/signal.</td></tr>';
    document.getElementById('tradePager').innerHTML = pagerHtml('trades', rows.length);
}

async function renderMemory() {
  const payload = await api('/api/memory');
  const item = (m) => `<div class="memory-item"><h4>${m.lesson_id || m.schema || 'memory item'}</h4><p>${m.lesson || m.recommendation || 'No summary'}</p><p><strong>Confidence:</strong> ${m.confidence ?? 'n/a'} · <strong>Evidence:</strong> ${m.evidence_count ?? 'n/a'} · <strong>Status:</strong> ${m.status ?? 'n/a'}</p><details><summary class="muted">JSON</summary><div class="json">${JSON.stringify(m, null, 2)}</div></details></div>`;
    const rawItem = (m) => `<div class="memory-item"><h4>${m.symbol_normalized || m.coin || m.symbol || 'raw case'} · ${m.result_normalized || m.result || '—'}</h4><p>${m.strategy || m.action_normalized || 'raw'} ${m.signal || ''} · PnL ${m.pnl_normalized === null ? '—' : fmtPnl(m.pnl_normalized)} · ${m.timestamp_normalized || m.date_normalized || ''}</p><details><summary class="muted">JSON</summary><div class="json">${JSON.stringify(m, null, 2)}</div></details></div>`;
    const globalRows = payload.global || [];
    const lessonRows = payload.lessons || [];
    const rawRows = payload.raw_recent || [];
    document.getElementById('globalMemory').innerHTML = currentPageItems('globalMemory', globalRows, 5).map(item).join('') || '<div class="memory-item"><h4>Chưa có global memory</h4><p>Trade mode nên thận trọng. Cần promote lesson sau khi đủ evidence.</p></div>';
    document.getElementById('globalMemoryPager').innerHTML = pagerHtml('globalMemory', globalRows.length, 5);
    document.getElementById('lessonMemory').innerHTML = currentPageItems('lessonMemory', lessonRows, 5).map(item).join('') || '<div class="memory-item"><h4>Chưa có lesson draft</h4><p>Chạy training/backtest thêm để tạo raw case rồi process lesson.</p></div>';
    document.getElementById('lessonMemoryPager').innerHTML = pagerHtml('lessonMemory', lessonRows.length, 5);
        document.getElementById('rawMemory').innerHTML = currentPageItems('rawMemory', rawRows, 5).map(rawItem).join('') || '<div class="memory-item"><h4>Chưa có raw memory</h4><p>Chạy backtest/training để tạo case thô.</p></div>';
        document.getElementById('rawMemoryPager').innerHTML = pagerHtml('rawMemory', rawRows.length, 5);
}

function currentTrainingTiers() {
    const tiers = [];
    if (document.getElementById('tierRaw').checked) tiers.push('raw');
    if (document.getElementById('tierLesson').checked) tiers.push('lesson');
    if (document.getElementById('tierGlobal').checked) tiers.push('global');
    return tiers.length ? tiers : ['lesson'];
}

function renderTrainingTiers(tiers) {
    const normalized = new Set(tiers && tiers.length ? tiers : ['lesson']);
    document.getElementById('tierRaw').checked = normalized.has('raw');
    document.getElementById('tierLesson').checked = normalized.has('lesson');
    document.getElementById('tierGlobal').checked = normalized.has('global');
    document.getElementById('trainingTierSummary').textContent = Array.from(normalized).join(', ');
}

async function previewMemoryContext() {
    const box = document.getElementById('memoryContextPreview');
    box.style.display = 'block';
    box.textContent = 'Đang tải context...';
    const symbol = document.getElementById('memoryContextSymbol').value || state.symbol || 'BTC/USDT';
    const payload = await api('/api/memory/context?symbol=' + encodeURIComponent(symbol));
    box.textContent = JSON.stringify(payload, null, 2);
}

function renderActions() {
  const actions = overview.actions || {};
  const total = Object.values(actions).reduce((a,b) => a + b, 0) || 1;
  document.getElementById('actionRows').innerHTML = Object.entries(actions).map(([a,n]) => `<tr><td>${badge(a)}</td><td>${n}</td><td>${fmtPct(n/total)}</td></tr>`).join('') || '<tr><td colspan="3" class="muted">Chưa có action.</td></tr>';
  const checks = [
    ['✅', 'Human confirmation', 'Executor mặc định yêu cầu xác nhận người dùng trước khi chạy.'],
    ['✅', 'Dry-run mặc định', 'UI có toggle dry-run; live order chưa được bật trong code.'],
        ['✅', 'Grouped routes', 'Config dùng /api/config; paper trading, approvals và performance dùng /api/trading.'],
        ['✅', 'Position cap', 'Paper sizing đã có max USDT/lệnh, max % cash/lệnh và max lệnh mở đồng thời.'],
        ['⚠️', 'Fee/slippage', 'Paper PnL hiện là PnL thô. Nên thêm phí Binance + slippage trước khi đánh giá thật.'],
    ['⚠️', 'Global memory evidence', 'Trade mode chỉ nên bật khi global rules có >30 cases, confidence >0.8.'],
        ['⚠️', 'Daily loss limit', 'Nên thêm circuit breaker theo ngày/tháng trước khi scale vốn thật.'],
        ['✅', 'Paper trading', 'Ledger paper đã có open/close, TP/SL, trailing, close một lệnh và close tất cả.'],
    ['🧠', 'On-chain data', 'Muốn có edge crypto tốt hơn nên thêm funding, open interest, liquidation, whale/on-chain.']
  ];
  document.getElementById('riskChecklist').innerHTML = checks.map(c => `<div class="check"><div style="font-size:22px">${c[0]}</div><div><strong>${c[1]}</strong><span>${c[2]}</span></div></div>`).join('');
}

async function saveState(patch) {
    await api('/api/config', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(patch) });
    configDirty = false;
    document.getElementById('unsavedBadge').style.display = 'none';
  await refresh();
}

async function runMemoryOp(path, payload) {
    const box = document.getElementById('memoryOpsResult');
    box.style.display = 'block';
    box.textContent = 'Đang chạy...';
    try {
        const result = await api(path, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
        box.textContent = JSON.stringify(result, null, 2);
        await refresh();
    } catch (err) {
        box.textContent = 'ERROR: ' + err.message;
    }
}

async function runPaperOp(path, payload) {
    const box = document.getElementById('paperOpsResult');
    box.style.display = 'block';
    box.textContent = 'Đang chạy paper flow...';
    try {
        const result = await api(path, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
        const compact = { operation: result.operation, status: result.status, signals: result.signals, decisions: result.decisions, orders: result.orders, risk_rejected: result.risk_rejected, scan_debug: result.scan_debug, approval: result.approval, order: result.order, actions: result.actions, closed: result.closed, paper: result.paper };
        box.textContent = JSON.stringify(compact, null, 2);
        await refresh();
    } catch (err) {
        box.textContent = 'ERROR: ' + err.message;
    }
}

async function approveOrder(id) {
    await runPaperOp('/api/paper/approve', {id});
}

async function rejectOrder(id) {
    await runPaperOp('/api/paper/reject', {id});
}

async function forceClosePosition(id, symbol) {
    if (!confirm(`Chốt ${symbol || 'position'} ngay tại giá hiện tại?`)) return;
    await runPaperOp('/api/paper/force-close', {id});
}

async function forceCloseAllPositions() {
    const openCount = Number((((trading || {}).paper || {}).stats || {}).open_positions || 0);
    if (!openCount) { alert('Không có lệnh mở để chốt.'); return; }
    if (!confirm(`Chốt đồng thời tất cả ${openCount} lệnh mở tại giá hiện tại?`)) return;
    await runPaperOp('/api/paper/force-close-all', {});
}

async function approveAllOrders() {
    const payload = await api('/api/paper/approvals');
    const pending = (payload.pending || []);
    if (!pending.length) { alert('Không có lệnh nào đang chờ.'); return; }
    if (!confirm(`Approve tất cả ${pending.length} lệnh?`)) return;
    for (const a of pending) {
        await api('/api/paper/approve', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id: a.id})});
    }
    await refresh();
    document.getElementById('paperOpsResult').style.display = 'block';
    document.getElementById('paperOpsResult').textContent = `Đã approve ${pending.length} lệnh.`;
}

async function rejectAllOrders() {
    const payload = await api('/api/paper/approvals');
    const pending = (payload.pending || []);
    if (!pending.length) { alert('Không có lệnh nào đang chờ.'); return; }
    if (!confirm(`Reject tất cả ${pending.length} lệnh?`)) return;
    for (const a of pending) {
        await api('/api/paper/reject', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id: a.id})});
    }
    await refresh();
    document.getElementById('paperOpsResult').style.display = 'block';
    document.getElementById('paperOpsResult').textContent = `Đã reject ${pending.length} lệnh.`;
}

document.querySelectorAll('.nav button').forEach(btn => btn.addEventListener('click', () => {
  document.querySelectorAll('.nav button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('main section').forEach(s => s.classList.add('hidden'));
  document.getElementById('view-' + btn.dataset.view).classList.remove('hidden');
}));
document.querySelectorAll('.tab').forEach(btn => btn.addEventListener('click', () => { document.querySelectorAll('.tab').forEach(b => b.classList.remove('active')); btn.classList.add('active'); state.period = btn.dataset.period; renderPeriods(); }));
document.getElementById('symbolSelect').addEventListener('change', (e) => { state.symbol = e.target.value; refresh(); });
document.getElementById('trainingBtn').addEventListener('click', () => saveState({mode:'training'}));
document.getElementById('tradeBtn').addEventListener('click', () => saveState({mode:'trade'}));
document.getElementById('tradingEnabled').addEventListener('change', e => saveState({trading_enabled:e.target.checked}));
document.getElementById('dryRun').addEventListener('change', e => saveState({dry_run:e.target.checked}));
document.getElementById('requireConfirm').addEventListener('change', e => saveState({require_confirmation:e.target.checked}));
document.getElementById('autoScanEnabled').addEventListener('change', e => saveState({auto_scan_enabled:e.target.checked}));
document.getElementById('telegramEnabled').addEventListener('change', e => saveState({telegram_enabled:e.target.checked}));
document.getElementById('telegramAutoApproveTestMode').addEventListener('change', e => saveState({telegram_auto_approve_test_mode:e.target.checked}));
document.getElementById('telegramBotToken').addEventListener('change', e => saveState({telegram_bot_token:e.target.value}));
document.getElementById('telegramChatId').addEventListener('change', e => saveState({telegram_chat_id:e.target.value}));
document.getElementById('minConfidence').addEventListener('change', e => saveState({min_confidence:numVal('minConfidence', 0.55)}));
document.getElementById('saveMemoryTiersBtn').addEventListener('click', () => saveState({training_memory_tiers:currentTrainingTiers()}));
document.getElementById('saveRiskBtn').addEventListener('click', () => saveState({
    paper_allocation_pct:numVal('paperAllocationPct', 0.05),
    paper_min_allocation_pct:numVal('paperMinAllocationPct', 0.02),
    max_position_pct:numVal('maxPositionPct', 0.10),
    max_position_usdt:numVal('maxPositionUsdt', 100),
    scanner_max_open_positions:numVal('scannerMaxOpenPositions', 5),
    trade_memory_space_id:document.getElementById('tradeMemorySpaceId').value || 'default',
    sizing_min_trades:numVal('sizingMinTrades', 5),
    scan_interval_minutes:numVal('scanIntervalMinutes', 10),
    scanner_timeframe:document.getElementById('scannerTimeframe').value || '1h',
    scanner_rsi_oversold:numVal('scannerRsiOversold', 38),
    scanner_rsi_extreme:numVal('scannerRsiExtreme', 25),
    scanner_min_strength:numVal('scannerMinStrength', 0.50),
    scanner_range_bounce_max_pos:numVal('scannerRangeBounceMaxPos', 0.35),
    scanner_range_min_width_atr:numVal('scannerRangeMinWidthAtr', 1.6),
    scanner_sideway_min_rsi:numVal('scannerSidewayMinRsi', 28),
    scanner_sideway_max_rsi:numVal('scannerSidewayMaxRsi', 65),
    scanner_enable_rsi_reversal:checkedVal('scannerEnableRsiReversal'),
    scanner_enable_breakout:checkedVal('scannerEnableBreakout'),
    scanner_enable_ema_crossover:checkedVal('scannerEnableEmaCrossover'),
    scanner_enable_rsi_momentum:checkedVal('scannerEnableRsiMomentum'),
    scanner_enable_trend_pullback:checkedVal('scannerEnableTrendPullback'),
    scanner_enable_orderflow:checkedVal('scannerEnableOrderflow'),
    scanner_enable_regime_flip:checkedVal('scannerEnableRegimeFlip'),
    scanner_enable_liquidity_sweep:checkedVal('scannerEnableLiquiditySweep'),
    scanner_enable_range_bounce:checkedVal('scannerEnableRangeBounce'),
    scanner_enable_bb_reversion:checkedVal('scannerEnableBbReversion'),
    scanner_enable_ensemble:checkedVal('scannerEnableEnsemble'),
    scanner_auto_approve_min_strength:numVal('scannerAutoApproveMinStrength', 0.72),
    scanner_max_hold_hours:numVal('scannerMaxHoldHours', 24),
    scanner_breakeven_trigger_pct:numVal('scannerBreakevenTriggerPct', 0.6),
    scanner_trailing_stop_pct:numVal('scannerTrailingStopPct', 0.5),
}));
document.getElementById('telegramTestBtn').addEventListener('click', () => runPaperOp('/api/telegram/test', {}));
document.getElementById('telegramPollBtn').addEventListener('click', () => runPaperOp('/api/telegram/poll', {}));
document.getElementById('previewMemoryContextBtn').addEventListener('click', previewMemoryContext);
document.getElementById('processLessonsBtn').addEventListener('click', () => runMemoryOp('/api/memory/process', {min_cases:numVal('processMinCases', 5)}));
document.getElementById('promoteGlobalBtn').addEventListener('click', () => runMemoryOp('/api/memory/promote', {min_cases:numVal('promoteMinCases', 30), min_confidence:numVal('promoteMinConfidence', 0.8), min_source_modes:numVal('promoteMinModes', 2)}));
document.getElementById('paperDepositBtn').addEventListener('click', () => runPaperOp('/api/paper/deposit', {amount:numVal('paperDepositAmount', 1000), note:'dashboard'}));
document.getElementById('paperScanTradeBtn').addEventListener('click', async () => {
    const symbols = document.getElementById('paperSymbols').value.split(',').map(s => s.trim()).filter(Boolean);
    const allocation_pct = numVal('paperAllocationPct', 0.10);
    await saveState({paper_symbols:symbols, paper_allocation_pct:allocation_pct});
    await runPaperOp('/api/paper/scan-trade', {symbols, allocation_pct, min_confidence:numVal('minConfidence', 0.55), require_confirmation:((config || {}).state || {}).require_confirmation});
});
document.getElementById('paperMarkBtn').addEventListener('click', () => runPaperOp('/api/paper/mark', {}));
document.getElementById('paperMarkTopBtn').addEventListener('click', () => runPaperOp('/api/paper/mark', {}));
document.getElementById('paperCloseAllBtn').addEventListener('click', forceCloseAllPositions);
document.getElementById('paperCloseAllInlineBtn').addEventListener('click', forceCloseAllPositions);
document.getElementById('paperResetBtn').addEventListener('click', () => runPaperOp('/api/paper/reset', {initial_cash:0}));
document.getElementById('clearCandidatesBtn').addEventListener('click', async () => {
    await api('/api/paper/candidates/clear', {method:'POST', body:'{}'});
    renderCandidates();
});
refresh();
setInterval(refresh, 15000);
// Mark config form dirty when user edits any deferred-save input
['scanIntervalMinutes','scannerTimeframe','scannerRsiOversold','scannerRsiExtreme','scannerMinStrength',
 'scannerRangeBounceMaxPos','scannerRangeMinWidthAtr','scannerSidewayMinRsi','scannerSidewayMaxRsi',
 'scannerAutoApproveMinStrength','scannerMaxHoldHours','scannerBreakevenTriggerPct','scannerTrailingStopPct',
 'scannerEnableRsiReversal','scannerEnableBreakout','scannerEnableEmaCrossover','scannerEnableRsiMomentum',
 'scannerEnableTrendPullback','scannerEnableOrderflow','scannerEnableRegimeFlip',
 'scannerEnableLiquiditySweep','scannerEnableRangeBounce','scannerEnableBbReversion','scannerEnableEnsemble',
 'paperSymbols','paperAllocationPct','paperMinAllocationPct','maxPositionPct','maxPositionUsdt',
 'scannerMaxOpenPositions','sizingMinTrades','tradeMemorySpaceId'
].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('input', () => { configDirty = true; document.getElementById('unsavedBadge').style.display = 'inline'; });
    el.addEventListener('change', () => { configDirty = true; document.getElementById('unsavedBadge').style.display = 'inline'; });
});
</script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    store: DashboardStore

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        symbol = qs.get("symbol", [""])[0] or None
        try:
            if parsed.path == "/":
                _html_response(self, HTML)
            elif parsed.path == "/api/state":
                _json_response(self, self.store.load_state())
            elif parsed.path == "/api/config":
                _json_response(self, config_payload(self.store))
            elif parsed.path == "/api/overview":
                _json_response(self, overview_payload(self.store, symbol=symbol))
            elif parsed.path == "/api/trading":
                _json_response(self, trading_payload(self.store))
            elif parsed.path == "/api/performance":
                _json_response(self, paper_performance_payload(self.store))
            elif parsed.path == "/api/runs":
                limit = int(qs.get("limit", [80])[0])
                _json_response(self, runs_payload(self.store, symbol=symbol, limit=limit))
            elif parsed.path == "/api/memory":
                _json_response(self, memory_payload(self.store))
            elif parsed.path == "/api/memory/context":
                _json_response(self, memory_context_payload(self.store, symbol=symbol))
            elif parsed.path == "/api/paper":
                _json_response(self, paper_payload(self.store))
            elif parsed.path == "/api/paper/approvals":
                _json_response(self, approvals_payload(self.store))
            elif parsed.path == "/api/paper/candidates":
                limit = int(qs.get("limit", [100])[0])
                rows = self.store.load_candidates(limit=limit)
                _json_response(self, {"candidates": rows, "total": len(rows)})
            elif parsed.path == "/api/paths":
                _json_response(self, self.store.paths())
            else:
                _json_response(self, {"error": "not found"}, status=404)
        except Exception as exc:  # keep local dashboard debuggable
            _json_response(self, {"error": str(exc)}, status=500)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            updates = json.loads(body or "{}")
            if parsed.path in {"/api/state", "/api/config"}:
                _json_response(self, self.store.update_state(updates))
            elif parsed.path == "/api/memory/process":
                _json_response(self, process_lessons_payload(self.store, min_cases=updates.get("min_cases", 5)))
            elif parsed.path == "/api/memory/promote":
                _json_response(
                    self,
                    promote_global_payload(
                        self.store,
                        min_cases=updates.get("min_cases", 30),
                        min_confidence=updates.get("min_confidence", 0.8),
                        min_source_modes=updates.get("min_source_modes", 2),
                        reviewed_by=updates.get("reviewed_by", "human-dashboard"),
                    ),
                )
            elif parsed.path == "/api/paper/deposit":
                _json_response(self, paper_deposit_payload(self.store, amount=updates.get("amount", 0), note=updates.get("note", "dashboard")))
            elif parsed.path == "/api/paper/reset":
                _json_response(self, paper_reset_payload(self.store, initial_cash=updates.get("initial_cash", 0)))
            elif parsed.path == "/api/paper/mark":
                _json_response(self, paper_mark_payload(self.store, symbols=updates.get("symbols")))
            elif parsed.path == "/api/paper/force-close":
                exit_price = updates.get("exit_price")
                _json_response(self, paper_force_close_payload(self.store, str(updates.get("id") or ""), exit_price=float(exit_price) if exit_price is not None else None))
            elif parsed.path == "/api/paper/force-close-all":
                _json_response(self, paper_force_close_all_payload(self.store))
            elif parsed.path == "/api/paper/scan-trade":
                _scan_result = paper_scan_trade_payload(self.store, updates)
                _json_response(self, _scan_result)
                _st = self.store.load_state()
                _send_scan_summary_telegram(self.store, _scan_result, _st.get("paper_symbols") or [])
            elif parsed.path == "/api/paper/approve":
                _json_response(self, approve_pending_payload(self.store, str(updates.get("id") or "")))
            elif parsed.path == "/api/paper/reject":
                _json_response(self, reject_pending_payload(self.store, str(updates.get("id") or "")))
            elif parsed.path == "/api/paper/candidates/clear":
                count = self.store.clear_candidates()
                _json_response(self, {"operation": "clear_candidates", "cleared": count})
            elif parsed.path == "/api/telegram/poll":
                _json_response(self, poll_telegram_payload(self.store))
            elif parsed.path == "/api/telegram/test":
                approval = {
                    "id": "test",
                    "signal": {"symbol": "BTC/USDT", "action": "BUY", "entry": 0, "stop_loss": 0, "take_profit": 0, "strategy": "test", "strength": 0},
                    "llm_decision": {"confidence": 0, "reasoning": "Telegram test from dashboard"},
                    "sizing": {"notional_usdt": 0, "allocation_pct": 0, "max_position_usdt": self.store.load_state().get("max_position_usdt"), "stats": {"win_rate": None}},
                }
                _json_response(self, _telegram_notifier_from_state(self.store.load_state()).send_approval_request(approval))
            else:
                _json_response(self, {"error": "not found"}, status=404)
        except Exception as exc:
            _json_response(self, {"error": str(exc)}, status=400)


class PositionMonitor:
    """Real-time TP/SL monitor using Binance WebSocket aggTrade streams.

    Subscribes to live trade streams for every open paper position.
    On each trade event the latest price is checked against TP/SL immediately —
    no polling delay. Falls back to REST fetch_ticker if WebSocket is unavailable.
    """

    WS_BASE = "wss://stream.binance.com:9443/stream"
    RECONNECT_SECONDS = 5
    FALLBACK_POLL_SECONDS = 15

    def __init__(self, store: DashboardStore):
        self.store = store
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="crypto-position-monitor", daemon=True)
        # latest price cache updated by WS thread, read by _check_exits
        self._prices: Dict[str, float] = {}
        self._prices_lock = threading.Lock()

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Main thread entry
    # ------------------------------------------------------------------
    def _run(self) -> None:
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._ws_loop())
        except Exception as exc:
            print(f"[PositionMonitor] WebSocket unavailable, falling back to polling: {exc}", flush=True)
            self._poll_loop()

    # ------------------------------------------------------------------
    # WebSocket path
    # ------------------------------------------------------------------
    async def _ws_loop(self) -> None:
        import asyncio
        import websockets  # type: ignore

        last_check = 0.0
        last_position_check = 0.0
        POSITION_REFRESH_SECONDS = 5.0  # re-evaluate open positions every 5s

        while not self.stop_event.is_set():
            positions = self.store.paper_ledger().load_positions()
            if not positions:
                await asyncio.sleep(2)
                continue

            subscribed_ids = {p["id"] for p in positions if p.get("id")}

            # Build combined stream URL: btcusdt@aggTrade/tonusdt@aggTrade/...
            streams = "/".join(
                p["symbol"].replace("/", "").lower() + "@aggTrade"
                for p in positions
                if p.get("symbol")
            )
            url = f"{self.WS_BASE}?streams={streams}"
            try:
                async with websockets.connect(url, ping_interval=20, close_timeout=5) as ws:
                    symbols_display = [p["symbol"] for p in positions if p.get("symbol")]
                    print(f"[PositionMonitor] WebSocket connected: {len(positions)} symbols {symbols_display}", flush=True)
                    while not self.stop_event.is_set():
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=5)
                        except asyncio.TimeoutError:
                            # On each recv timeout, check whether positions changed
                            now = time.monotonic()
                            if now - last_position_check >= POSITION_REFRESH_SECONDS:
                                last_position_check = now
                                current_ids = {p["id"] for p in self.store.paper_ledger().load_positions() if p.get("id")}
                                if current_ids != subscribed_ids:
                                    print(f"[PositionMonitor] Positions changed, reconnecting WS...", flush=True)
                                    break  # exit inner loop → reconnect with updated positions
                            continue
                        msg = json.loads(raw)
                        data = msg.get("data", msg)
                        symbol_raw = str(data.get("s", ""))  # e.g. "TONUSDT"
                        price_str = data.get("p")  # aggTrade price
                        if not symbol_raw or not price_str:
                            continue
                        # Normalise to "TON/USDT" style
                        symbol = self._normalise(symbol_raw)
                        price = float(price_str)
                        with self._prices_lock:
                            self._prices[symbol] = price
                        # Throttle exit checks to max once per second per symbol
                        now = time.monotonic()
                        if now - last_check >= 1.0:
                            last_check = now
                            self._check_exits()
                        # Also refresh position set periodically while receiving messages
                        if now - last_position_check >= POSITION_REFRESH_SECONDS:
                            last_position_check = now
                            current_ids = {p["id"] for p in self.store.paper_ledger().load_positions() if p.get("id")}
                            if current_ids != subscribed_ids:
                                print(f"[PositionMonitor] Positions changed, reconnecting WS...", flush=True)
                                break  # exit inner loop → reconnect with updated positions
            except Exception as exc:
                if not self.stop_event.is_set():
                    print(f"[PositionMonitor] WS error, reconnecting in {self.RECONNECT_SECONDS}s: {exc}", flush=True)
                    await asyncio.sleep(self.RECONNECT_SECONDS)

    @staticmethod
    def _normalise(raw: str) -> str:
        """Convert 'TONUSDT' → 'TON/USDT' (assumes USDT suffix)."""
        raw = raw.upper()
        for quote in ("USDT", "BTC", "ETH", "BNB"):
            if raw.endswith(quote):
                return raw[: -len(quote)] + "/" + quote
        return raw

    # ------------------------------------------------------------------
    # Fallback polling path (if websockets library missing or blocked)
    # ------------------------------------------------------------------
    def _poll_loop(self) -> None:
        from tradingagents.dataflows.crypto_data import _exchange
        while not self.stop_event.wait(self.FALLBACK_POLL_SECONDS):
            try:
                positions = self.store.paper_ledger().load_positions()
                if not positions:
                    continue
                exchange = _exchange()
                for pos in positions:
                    sym = pos.get("symbol")
                    if not sym:
                        continue
                    try:
                        ticker = exchange.fetch_ticker(sym)
                        price = float(ticker.get("last") or ticker.get("close") or 0)
                        if price > 0:
                            with self._prices_lock:
                                self._prices[sym] = price
                    except Exception:
                        pass
                self._check_exits()
            except Exception as exc:
                print(f"WARNING: position monitor poll error: {exc}", flush=True)

    # ------------------------------------------------------------------
    # Shared exit-check logic
    # ------------------------------------------------------------------
    def _check_exits(self) -> None:
        with self._prices_lock:
            prices = dict(self._prices)
        if not prices:
            return
        ledger = self.store.paper_ledger()
        candles = {sym: {"high": p, "low": p, "close": p} for sym, p in prices.items()}
        state = self.store.load_state()
        closed = ledger.check_exits(
            candles,
            max_hold_hours=float(state.get("scanner_max_hold_hours") or 0.0),
            breakeven_trigger_pct=float(state.get("scanner_breakeven_trigger_pct") or 0.0),
            trailing_stop_pct=float(state.get("scanner_trailing_stop_pct") or 0.0),
        )
        if not closed:
            return
        ledger.mark_open_positions(prices)
        if state.get("telegram_enabled"):
            notifier = _telegram_notifier_from_state(state)
            for trade in closed:
                try:
                    notifier.send_trade_closed(trade)
                except Exception as exc:
                    print(f"WARNING: position monitor telegram failed: {exc}", flush=True)
        for trade in closed:
            print(
                f"[PositionMonitor] {trade.get('symbol')} closed {trade.get('result')} "
                f"pnl={trade.get('pnl_amount', 0):+.4f} USDT via {trade.get('exit_reason')}",
                flush=True,
            )


class DashboardScheduler:
    """Local background worker for Telegram callbacks and scheduled paper scans.

    Uses an in-memory monotonic timer for scan interval enforcement so that
    concurrent state-file writes from the web UI cannot accidentally trigger
    early re-scans.  The interval *value* is still read from persisted state
    on every tick, so dashboard config changes take effect within 5 seconds.
    """

    def __init__(self, store: DashboardStore):
        self.store = store
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="crypto-dashboard-scheduler", daemon=True)
        self.position_monitor = PositionMonitor(store)
        # In-memory timer — immune to state-file race conditions or dashboard restarts.
        self._last_scan_time: float = 0.0  # time.monotonic() timestamp

    def start(self) -> None:
        self.thread.start()
        self.position_monitor.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.position_monitor.stop()
        self.thread.join(timeout=2)

    def _run(self) -> None:
        _last_tg_poll: float = 0.0
        import time as _time
        while not self.stop_event.wait(5):
            state = self.store.load_state()
            if state.get("telegram_enabled"):
                now = _time.monotonic()
                if now - _last_tg_poll >= 30:  # poll at most once every 30s to avoid throttling
                    try:
                        poll_telegram_payload(self.store)
                        _last_tg_poll = now
                    except Exception as exc:
                        _last_tg_poll = now  # back off even on error
                        print(f"WARNING: telegram poll failed: {exc}", flush=True)
            if not state.get("auto_scan_enabled"):
                continue

            # Read the interval value from persisted state (so dashboard changes
            # take effect) but enforce it against the in-memory timer.
            interval_minutes = max(1, int(float(state.get("scan_interval_minutes") or 10)))
            interval_seconds = interval_minutes * 60
            now = _time.monotonic()
            if self._last_scan_time > 0 and (now - self._last_scan_time) < interval_seconds:
                continue

            try:
                self._last_scan_time = now
                # Still persist for dashboard display / visibility.
                self.store.update_state({
                    "last_auto_scan_status": "running",
                    "last_auto_scan_at": datetime.now(timezone.utc).isoformat(),
                })
                paper_mark_payload(self.store)
                result = paper_scan_trade_payload(
                    self.store,
                    {
                        "symbols": state.get("paper_symbols"),
                        "min_confidence": state.get("min_confidence", 0.75),
                        "require_confirmation": state.get("require_confirmation", True),
                        "source": "auto_scheduler",
                    },
                )
                self.store.update_state({"last_auto_scan_status": result.get("status", "ok")})
                _send_scan_summary_telegram(self.store, result, state.get("paper_symbols") or [])
            except Exception as exc:
                self.store.update_state({"last_auto_scan_status": f"error: {exc}"})
                print(f"WARNING: auto scan failed: {exc}", flush=True)
                # Still send an error heartbeat
                try:
                    state2 = self.store.load_state()
                    if state2.get("telegram_enabled"):
                        _telegram_notifier_from_state(state2).send_text(f"⚠️ Auto-scan lỗi: {exc}")
                except Exception:
                    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TradingAgents crypto command center")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--memory-dir", default=CRYPTO_TRAIN_CONFIG.get("crypto_memory_dir", "~/.tradingagents/crypto_memory"))
    parser.add_argument("--allow-temp-memory", action="store_true", help="Allow volatile /tmp memory directory for throwaway tests only")
    parser.add_argument("--no-open", action="store_true", help="Do not open browser automatically")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = DashboardStore(_resolve_safe_memory_dir(args.memory_dir, allow_temp_memory=args.allow_temp_memory))
    DashboardHandler.store = store
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    scheduler = DashboardScheduler(store)
    scheduler.start()
    url = f"http://{args.host}:{args.port}"
    print(f"TradingAgents Crypto dashboard: {url}")
    print(f"Memory directory: {store.memory_dir}")
    if not args.no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard...")
    finally:
        scheduler.stop()
        server.server_close()


if __name__ == "__main__":
    main()