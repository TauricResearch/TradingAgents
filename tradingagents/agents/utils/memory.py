"""Append-only JSON decision log for TradingAgents.

Format: newline-delimited JSON objects (one per entry), separated by the
ENTRY_SEP sentinel so the file can be split without a full JSON parser.
Each entry is a flat dict with a ``version`` field for forward-compatibility.

Backward compatibility: if an existing file uses the old markdown format
(entries delimited by ``<!-- ENTRY_END -->``), it is automatically migrated
to the new JSON format on the first read.
"""

import json
import re
from pathlib import Path
from typing import List, Optional

from tradingagents.agents.utils.rating import parse_rating

# Sentinel that separates entries.  Cannot appear in valid JSON.
_ENTRY_SEP = "\n<!-- ENTRY_END -->\n"

# Current entry schema version.
_VERSION = 1

# Patterns used only during markdown migration.
_MD_DECISION_RE = re.compile(r"DECISION:\n(.*?)(?=\nREFLECTION:|\Z)", re.DOTALL)
_MD_REFLECTION_RE = re.compile(r"REFLECTION:\n(.*?)$", re.DOTALL)


class TradingMemoryLog:
    """Append-only JSON log of trading decisions and reflections."""

    def __init__(self, config: dict = None):
        cfg = config or {}
        self._log_path: Optional[Path] = None
        path = cfg.get("memory_log_path")
        if path:
            self._log_path = Path(path).expanduser()
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._max_entries: Optional[int] = cfg.get("memory_log_max_entries")

    # ------------------------------------------------------------------ #
    # Write (Phase A)                                                      #
    # ------------------------------------------------------------------ #

    def store_decision(
        self,
        ticker: str,
        trade_date: str,
        final_trade_decision: str,
    ) -> None:
        """Append a pending entry.  Idempotent — skips if already present."""
        if not self._log_path:
            return
        entries = self.load_entries()
        for e in entries:
            if e["date"] == trade_date and e["ticker"] == ticker and e["pending"]:
                return
        rating = parse_rating(final_trade_decision)
        entry = {
            "version": _VERSION,
            "date": trade_date,
            "ticker": ticker,
            "rating": rating,
            "pending": True,
            "raw_return": None,
            "alpha_return": None,
            "holding_days": None,
            "decision": final_trade_decision,
            "reflection": "",
        }
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + _ENTRY_SEP)

    # ------------------------------------------------------------------ #
    # Read (Phase A)                                                       #
    # ------------------------------------------------------------------ #

    def load_entries(self) -> List[dict]:
        """Return all entries, auto-migrating from markdown if needed."""
        if not self._log_path or not self._log_path.exists():
            return []
        text = self._log_path.read_text(encoding="utf-8")
        if not text.strip():
            return []
        # Detect old markdown format: entries start with a tag like "[date |"
        if self._is_markdown_format(text):
            entries = self._migrate_markdown(text)
            self._rewrite(entries)
            return entries
        return self._parse_json_text(text)

    def get_pending_entries(self) -> List[dict]:
        return [e for e in self.load_entries() if e.get("pending")]

    def get_past_context(self, ticker: str, n_same: int = 5, n_cross: int = 3) -> str:
        """Return formatted past context string for agent prompt injection."""
        entries = [e for e in self.load_entries() if not e.get("pending")]
        if not entries:
            return ""

        same, cross = [], []
        for e in reversed(entries):
            if len(same) >= n_same and len(cross) >= n_cross:
                break
            if e["ticker"] == ticker and len(same) < n_same:
                same.append(e)
            elif e["ticker"] != ticker and len(cross) < n_cross:
                cross.append(e)

        if not same and not cross:
            return ""

        parts = []
        if same:
            parts.append(f"Past analyses of {ticker} (most recent first):")
            parts.extend(self._format_full(e) for e in same)
        if cross:
            parts.append("Recent cross-ticker lessons:")
            parts.extend(self._format_reflection_only(e) for e in cross)
        return "\n\n".join(parts)

    # ------------------------------------------------------------------ #
    # Update (Phase B)                                                     #
    # ------------------------------------------------------------------ #

    def update_with_outcome(
        self,
        ticker: str,
        trade_date: str,
        raw_return: float,
        alpha_return: float,
        holding_days: int,
        reflection: str,
    ) -> None:
        """Update the first pending entry matching (trade_date, ticker)."""
        self.batch_update_with_outcomes([{
            "ticker": ticker,
            "trade_date": trade_date,
            "raw_return": raw_return,
            "alpha_return": alpha_return,
            "holding_days": holding_days,
            "reflection": reflection,
        }])

    def batch_update_with_outcomes(self, updates: List[dict]) -> None:
        """Apply multiple outcome updates in a single atomic read + write."""
        if not self._log_path or not self._log_path.exists() or not updates:
            return

        entries = self.load_entries()
        update_map = {(u["trade_date"], u["ticker"]): u for u in updates}

        for entry in entries:
            key = (entry["date"], entry["ticker"])
            if entry.get("pending") and key in update_map:
                upd = update_map.pop(key)
                entry["pending"] = False
                entry["raw_return"] = upd["raw_return"]
                entry["alpha_return"] = upd["alpha_return"]
                entry["holding_days"] = upd["holding_days"]
                entry["reflection"] = upd["reflection"]

        entries = self._apply_rotation(entries)
        self._rewrite(entries)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _rewrite(self, entries: List[dict]) -> None:
        """Atomically replace the log file with the given entries."""
        if not self._log_path:
            return
        text = _ENTRY_SEP.join(json.dumps(e) for e in entries)
        if text:
            text += _ENTRY_SEP
        tmp = self._log_path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self._log_path)

    def _apply_rotation(self, entries: List[dict]) -> List[dict]:
        """Drop oldest resolved entries when their count exceeds max_entries."""
        if not self._max_entries or self._max_entries <= 0:
            return entries
        resolved = [e for e in entries if not e.get("pending")]
        if len(resolved) <= self._max_entries:
            return entries
        to_drop = len(resolved) - self._max_entries
        kept, dropped = [], 0
        for e in entries:
            if not e.get("pending") and dropped < to_drop:
                dropped += 1
                continue
            kept.append(e)
        return kept

    @staticmethod
    def _parse_json_text(text: str) -> List[dict]:
        entries = []
        for chunk in text.split(_ENTRY_SEP):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                entries.append(json.loads(chunk))
            except json.JSONDecodeError:
                pass  # Skip corrupted entries rather than crashing.
        return entries

    @staticmethod
    def _is_markdown_format(text: str) -> bool:
        """Return True if the text looks like the old markdown log format."""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped.startswith("[") and "|" in stripped
        return False

    @staticmethod
    def _migrate_markdown(text: str) -> List[dict]:
        """Parse the old markdown format and return a list of JSON-ready entry dicts."""
        entries = []
        # Old separator was <!-- ENTRY_END --> (potentially with surrounding newlines).
        raw_blocks = re.split(r"\s*<!--\s*ENTRY_END\s*-->\s*", text)
        for raw in raw_blocks:
            raw = raw.strip()
            if not raw:
                continue
            lines = raw.splitlines()
            tag_line = lines[0].strip()
            if not (tag_line.startswith("[") and tag_line.endswith("]")):
                continue
            fields = [f.strip() for f in tag_line[1:-1].split("|")]
            if len(fields) < 4:
                continue
            pending = fields[3] == "pending"
            body = "\n".join(lines[1:]).strip()
            decision_m = _MD_DECISION_RE.search(body)
            reflection_m = _MD_REFLECTION_RE.search(body)
            entry = {
                "version": _VERSION,
                "date": fields[0],
                "ticker": fields[1],
                "rating": fields[2],
                "pending": pending,
                "raw_return": None if pending else _pct_to_float(fields[3]),
                "alpha_return": None if pending or len(fields) < 5 else _pct_to_float(fields[4]),
                "holding_days": None if pending or len(fields) < 6 else _days_to_int(fields[5]),
                "decision": decision_m.group(1).strip() if decision_m else "",
                "reflection": reflection_m.group(1).strip() if reflection_m else "",
            }
            entries.append(entry)
        return entries

    @staticmethod
    def _format_full(e: dict) -> str:
        raw = f"{e['raw_return']:+.1%}" if e.get("raw_return") is not None else "n/a"
        alpha = f"{e['alpha_return']:+.1%}" if e.get("alpha_return") is not None else "n/a"
        holding = f"{e['holding_days']}d" if e.get("holding_days") is not None else "n/a"
        tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | {raw} | {alpha} | {holding}]"
        parts = [tag, f"DECISION:\n{e['decision']}"]
        if e.get("reflection"):
            parts.append(f"REFLECTION:\n{e['reflection']}")
        return "\n\n".join(parts)

    @staticmethod
    def _format_reflection_only(e: dict) -> str:
        raw = f"{e['raw_return']:+.1%}" if e.get("raw_return") is not None else "n/a"
        tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | {raw}]"
        if e.get("reflection"):
            return f"{tag}\n{e['reflection']}"
        text = e.get("decision", "")
        suffix = "..." if len(text) > 300 else ""
        return f"{tag}\n{text[:300]}{suffix}"


def _pct_to_float(s: str) -> Optional[float]:
    """Convert '+12.3%' → 0.123.  Returns None on parse failure."""
    try:
        return float(s.strip().rstrip("%")) / 100
    except (ValueError, AttributeError):
        return None


def _days_to_int(s: str) -> Optional[int]:
    """Convert '5d' → 5.  Returns None on parse failure."""
    try:
        return int(s.strip().rstrip("d"))
    except (ValueError, AttributeError):
        return None
