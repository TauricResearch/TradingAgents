"""Selectable crypto training memory context: raw runs, draft lessons, or global lessons."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tradingagents.agents.utils.rating import parse_rating
from tradingagents.storage import SQLiteTradingStore


class CryptoTrainingMemory:
    """Store crypto training data and build prompt context from selected tiers.

    - raw: append-only JSONL of every agent run and decision.
    - lessons: append-only JSONL of reviewed outcomes/reflections.
    - global: validated lessons promoted from draft lessons.
    """

    def __init__(self, config: Optional[dict] = None):
        cfg = config or {}
        base_dir = Path(
            cfg.get("crypto_memory_dir")
            or cfg.get("memory_dir")
            or "~/.tradingagents/crypto_memory"
        ).expanduser()
        base_dir.mkdir(parents=True, exist_ok=True)
        self.base_dir = base_dir

        self.raw_path = Path(cfg.get("crypto_raw_memory_path") or base_dir / "raw.jsonl").expanduser()
        self.lesson_path = Path(cfg.get("crypto_lesson_memory_path") or base_dir / "lessons.jsonl").expanduser()
        self.tiered_raw_path = base_dir / "raw" / "raw.jsonl"
        self.tiered_lesson_path = base_dir / "lessons" / "lessons.jsonl"
        self.global_path = Path(cfg.get("crypto_global_memory_path") or base_dir / "global.jsonl").expanduser()
        self.tiered_global_path = base_dir / "global" / "global.jsonl"
        self.raw_path.parent.mkdir(parents=True, exist_ok=True)
        self.lesson_path.parent.mkdir(parents=True, exist_ok=True)
        self.global_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_lessons = int(cfg.get("crypto_lesson_context_limit", 8))
        self.memory_tiers = self._resolve_memory_tiers(cfg, base_dir)
        self.storage_backend = str(cfg.get("crypto_storage_backend") or os.getenv("TRADINGAGENTS_STORAGE_BACKEND") or "file").lower()
        self.user_id = str(cfg.get("crypto_user_id") or os.getenv("TRADINGAGENTS_USER_ID") or "admin")
        self.memory_space_id = str(cfg.get("crypto_memory_space_id") or os.getenv("TRADINGAGENTS_MEMORY_SPACE_ID") or "default")
        self.sqlite: Optional[SQLiteTradingStore] = None
        if self.storage_backend == "sqlite":
            db_path = Path(cfg.get("crypto_sqlite_path") or os.getenv("TRADINGAGENTS_SQLITE_PATH") or base_dir / "tradingagents.db").expanduser()
            self.sqlite = SQLiteTradingStore(db_path, user_id=self.user_id)

    def store_run(self, ticker: str, trade_date: str, final_state: Dict) -> None:
        """Append a raw memory entry for a completed training run."""
        final_decision = final_state.get("final_trade_decision", "")
        record = {
            "schema": "crypto_raw_v1",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "symbol": ticker,
            "trade_date": str(trade_date),
            "rating": parse_rating(final_decision),
            "final_trade_decision": final_decision,
            "reports": {
                "market": final_state.get("market_report", ""),
                "sentiment": final_state.get("sentiment_report", ""),
                "news": final_state.get("news_report", ""),
                "fundamentals": final_state.get("fundamentals_report", ""),
            },
            "plans": {
                "investment": final_state.get("investment_plan", ""),
                "trader": final_state.get("trader_investment_plan", ""),
            },
        }
        if self.sqlite:
            self.sqlite.append_memory("raw", record, memory_space_id=self.memory_space_id)
            return
        self._append_jsonl(self.raw_path, record)

    def store_decision(self, ticker: str, trade_date: str, final_trade_decision: str) -> None:
        """Compatibility path when only the final decision is available."""
        record = {
            "schema": "crypto_raw_v1",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "symbol": ticker,
            "trade_date": str(trade_date),
            "rating": parse_rating(final_trade_decision),
            "final_trade_decision": final_trade_decision,
            "reports": {},
            "plans": {},
        }
        if self.sqlite:
            self.sqlite.append_memory("raw", record, memory_space_id=self.memory_space_id)
            return
        self._append_jsonl(self.raw_path, record)

    def add_lesson(
        self,
        ticker: str,
        trade_date: str,
        lesson: str,
        outcome: Optional[dict] = None,
        source_raw_id: Optional[str] = None,
    ) -> None:
        """Append a distilled lesson after a raw decision has been reviewed."""
        record = {
            "schema": "crypto_lesson_v1",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "symbol": ticker,
            "trade_date": str(trade_date),
            "lesson": lesson.strip(),
            "outcome": outcome or {},
            "source_raw_id": source_raw_id,
        }
        if self.sqlite:
            self.sqlite.append_memory("lesson", record, memory_space_id=self.memory_space_id)
            return
        self._append_jsonl(self.lesson_path, record)

    def get_past_context(self, ticker: str, n_same: int = 5, n_cross: int = 3) -> str:
        """Return prompt context from the selected training memory tiers."""
        parts: List[str] = []
        if "raw" in self.memory_tiers:
            raw_context = self._raw_context(ticker, n_same=n_same, n_cross=n_cross)
            if raw_context:
                parts.append(raw_context)
        if "lesson" in self.memory_tiers:
            lesson_context = self._lesson_context(ticker, n_same=n_same, n_cross=n_cross)
            if lesson_context:
                parts.append(lesson_context)
        if "global" in self.memory_tiers:
            global_context = self._global_context(ticker)
            if global_context:
                parts.append(global_context)
        return "\n\n".join(parts)

    def _lesson_context(self, ticker: str, n_same: int = 5, n_cross: int = 3) -> str:
        lessons = self._load_memory_tier("lesson", [self.lesson_path, self.tiered_lesson_path])
        if not lessons:
            return ""

        same: List[dict] = []
        cross: List[dict] = []
        for item in reversed(lessons):
            if len(same) >= n_same and len(cross) >= n_cross:
                break
            if ticker in self._item_symbols(item) and len(same) < n_same:
                same.append(item)
            elif ticker not in self._item_symbols(item) and len(cross) < n_cross:
                cross.append(item)

        parts: List[str] = []
        if same:
            parts.append(f"Reviewed lessons for {ticker} (most recent first):")
            parts.extend(self._format_lesson(item) for item in same)
        if cross:
            parts.append("Cross-symbol crypto lessons:")
            parts.extend(self._format_lesson(item) for item in cross)
        return "\n\n".join(parts)

    def _raw_context(self, ticker: str, n_same: int = 5, n_cross: int = 3) -> str:
        raw = self._load_memory_tier("raw", [self.raw_path, self.tiered_raw_path])
        if not raw:
            return ""
        same: List[dict] = []
        cross: List[dict] = []
        for item in reversed(raw):
            if len(same) >= n_same and len(cross) >= n_cross:
                break
            symbol = self._item_symbol(item)
            if symbol == ticker and len(same) < n_same:
                same.append(item)
            elif symbol != ticker and len(cross) < n_cross:
                cross.append(item)

        parts: List[str] = []
        if same:
            parts.append(f"Recent raw memory cases for {ticker} (unreviewed; use cautiously):")
            parts.extend(self._format_raw_case(item) for item in same)
        if cross:
            parts.append("Recent cross-symbol raw memory cases (unreviewed):")
            parts.extend(self._format_raw_case(item) for item in cross)
        return "\n\n".join(parts)

    def _global_context(self, ticker: str) -> str:
        lessons = [
            item
            for item in self._load_memory_tier("global", [self.global_path, self.tiered_global_path])
            if item.get("status", "validated") == "validated"
        ]
        if not lessons:
            return ""
        exact = [item for item in lessons if ticker in item.get("coins_tested", []) or self._item_symbol(item) == ticker]
        general = [item for item in lessons if item not in exact]
        ordered = (exact + general)[-self.max_lessons :]
        lines = ["Validated global lessons available to training:"]
        lines.extend(self._format_global_lesson(item) for item in ordered)
        return "\n".join(lines)

    def get_pending_entries(self) -> List[dict]:
        """No implicit third-tier reflection queue in crypto train mode."""
        return []

    def batch_update_with_outcomes(self, updates: List[dict]) -> None:
        """Compatibility no-op; lessons are added explicitly via add_lesson()."""
        return None

    def load_entries(self) -> List[dict]:
        if self.sqlite:
            return self.sqlite.load_memory("raw", memory_space_id=self.memory_space_id)
        return self._read_jsonl(self.raw_path)

    def _load_memory_tier(self, tier: str, paths: List[Path]) -> List[dict]:
        if self.sqlite:
            return self.sqlite.load_memory(tier, memory_space_id=self.memory_space_id)
        return self._read_jsonl_many(paths)

    @staticmethod
    def _item_symbol(item: dict) -> str:
        symbols = CryptoTrainingMemory._item_symbols(item)
        return symbols[0] if symbols else ""

    @staticmethod
    def _item_symbols(item: dict) -> List[str]:
        coins_tested = item.get("coins_tested")
        if isinstance(coins_tested, list):
            return [str(symbol) for symbol in coins_tested if symbol]
        symbol = item.get("symbol") or item.get("coin") or item.get("ticker")
        return [str(symbol)] if symbol else []

    @classmethod
    def _format_raw_case(cls, item: dict) -> str:
        symbol = cls._item_symbol(item) or "UNKNOWN"
        timestamp = item.get("timestamp_utc") or item.get("trade_date") or item.get("date") or "n/a"
        strategy = item.get("strategy") or item.get("rating") or "n/a"
        action = item.get("signal") or item.get("action") or "n/a"
        result = item.get("result") or "n/a"
        pnl = item.get("pnl", item.get("pnl_pct", "n/a"))
        confidence = item.get("confidence", "n/a")
        regime = (item.get("market_context") or {}).get("market_regime", "n/a")
        reason = item.get("reasoning") or item.get("final_trade_decision") or ""
        if len(str(reason)) > 220:
            reason = str(reason)[:220] + "…"
        return (
            f"[{timestamp} | {symbol} | {strategy} {action} | result={result} | "
            f"pnl={pnl} | confidence={confidence} | regime={regime}]\n{reason}"
        )

    @staticmethod
    def _format_global_lesson(item: dict) -> str:
        return (
            f"- {item.get('lesson_id', 'global')}: {item.get('lesson', '')} "
            f"Recommendation: {item.get('recommendation', 'n/a')} "
            f"Confidence={item.get('confidence', 'n/a')} evidence={item.get('evidence_count', 'n/a')}"
        )

    @staticmethod
    def _format_lesson(item: dict) -> str:
        outcome = item.get("outcome") or {}
        if not outcome and ("win_rate" in item or "evidence_count" in item):
            outcome = {"win_rate": item.get("win_rate"), "evidence_count": item.get("evidence_count")}
        outcome_text = ", ".join(f"{k}={v}" for k, v in outcome.items()) or "outcome=n/a"
        return f"[{item.get('trade_date') or item.get('created_at')} | {CryptoTrainingMemory._item_symbol(item)} | {outcome_text}]\n{item.get('lesson', '')}"

    @classmethod
    def _resolve_memory_tiers(cls, cfg: Dict[str, Any], base_dir: Path) -> List[str]:
        value = cfg.get("crypto_training_memory_tiers", cfg.get("crypto_memory_context_tiers"))
        if value is None:
            value = cls._read_dashboard_tiers(base_dir)
        return cls._normalize_tiers(value if value is not None else ["lesson"])

    @staticmethod
    def _normalize_tiers(value: Any) -> List[str]:
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

    @staticmethod
    def _read_dashboard_tiers(base_dir: Path) -> Optional[List[str]]:
        state_path = base_dir / "dashboard_state.json"
        if not state_path.exists():
            return None
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        tiers = state.get("training_memory_tiers")
        return tiers if isinstance(tiers, list) else None

    @staticmethod
    def _append_jsonl(path: Path, record: dict) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _read_jsonl(path: Path) -> List[dict]:
        if not path.exists():
            return []
        items: List[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return items

    @classmethod
    def _read_jsonl_many(cls, paths: List[Path]) -> List[dict]:
        items: List[dict] = []
        seen = set()
        for path in paths:
            for item in cls._read_jsonl(path):
                key = json.dumps(item, ensure_ascii=False, sort_keys=True)
                if key in seen:
                    continue
                seen.add(key)
                items.append(item)
        return items
