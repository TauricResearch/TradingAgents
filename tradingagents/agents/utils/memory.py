"""Append-only markdown decision log for TradingAgents."""

from typing import List, Optional
from pathlib import Path
import re
import tempfile
import threading

from tradingagents.agents.utils.rating import parse_rating


class TradingMemoryLog:
    """Append-only markdown log of trading decisions and reflections."""

    # HTML comment: cannot appear in LLM prose output, safe as a hard delimiter
    _SEPARATOR = "\n\n<!-- ENTRY_END -->\n\n"
    # Precompiled patterns — avoids re-compilation on every load_entries() call
    _DECISION_RE = re.compile(r"DECISION:\n(.*?)(?=\nREFLECTION:|\Z)", re.DOTALL)
    _REFLECTION_RE = re.compile(r"REFLECTION:\n(.*?)$", re.DOTALL)
    _path_locks: dict[Path, threading.Lock] = {}
    _path_locks_guard = threading.Lock()

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self._log_path = None
        path = cfg.get("memory_log_path")
        if path:
            self._log_path = Path(path).expanduser()
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
        # Optional cap on resolved entries. None disables rotation.
        self._max_entries = cfg.get("memory_log_max_entries")
        self._entries_cache_mtime_ns: int | None = None
        self._entries_cache: List[dict] | None = None

    # --- Write path (Phase A) ---

    def store_decision(
        self,
        ticker: str,
        trade_date: str,
        final_trade_decision: str,
    ) -> None:
        """Append pending entry at end of propagate(). No LLM call."""
        if not self._log_path:
            return
        with self._path_lock():
            text = ""
            if self._log_path.exists():
                text = self._log_path.read_text(encoding="utf-8")
                for line in text.splitlines():
                    if line.startswith(f"[{trade_date} | {ticker} |") and line.endswith("| pending]"):
                        return
            rating = parse_rating(final_trade_decision)
            tag = f"[{trade_date} | {ticker} | {rating} | pending]"
            entry = f"{tag}\n\nDECISION:\n{final_trade_decision}{self._SEPARATOR}"
            self._atomic_write_text(text + entry)

    # --- Read path (Phase A) ---

    def load_entries(self) -> List[dict]:
        """Parse all entries from log. Returns list of dicts."""
        if not self._log_path or not self._log_path.exists():
            self._invalidate_entries_cache()
            return []

        mtime_ns = self._log_path.stat().st_mtime_ns
        if (
            self._entries_cache is not None
            and self._entries_cache_mtime_ns == mtime_ns
        ):
            return [entry.copy() for entry in self._entries_cache]

        text = self._log_path.read_text(encoding="utf-8")
        raw_entries = [e.strip() for e in text.split(self._SEPARATOR) if e.strip()]
        entries = []
        for raw in raw_entries:
            parsed = self._parse_entry(raw)
            if parsed:
                entries.append(parsed)
        self._entries_cache_mtime_ns = mtime_ns
        self._entries_cache = [entry.copy() for entry in entries]
        return entries

    def get_pending_entries(self) -> List[dict]:
        """Return entries with outcome:pending (for Phase B)."""
        return [e for e in self.load_entries() if e.get("pending")]

    def get_past_context(self, ticker: str, n_same: int = 5, n_cross: int = 3) -> str:
        """Return formatted past context string for agent prompt injection."""
        entries = [e for e in self.load_entries() if not e.get("pending")]
        if not entries:
            return ""

        same: list[dict] = []
        cross: list[dict] = []
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

    # --- Update path (Phase B) ---

    def batch_update_with_outcomes(self, updates: List[dict]) -> None:
        """Apply multiple outcome updates in a single read + atomic write.

        Each element of updates must have keys: ticker, trade_date,
        raw_return, alpha_return, holding_days, reflection.
        """
        if not self._log_path or not self._log_path.exists() or not updates:
            return

        text = self._log_path.read_text(encoding="utf-8")
        blocks = text.split(self._SEPARATOR)

        update_map = {}
        for update in updates:
            key = (update["trade_date"], update["ticker"])
            if key in update_map:
                raise ValueError(
                    f"duplicate outcome update for trade_date={key[0]!r}, ticker={key[1]!r}"
                )
            update_map[key] = update

        new_blocks = []
        for block in blocks:
            stripped = block.strip()
            if not stripped:
                new_blocks.append(block)
                continue

            lines = stripped.splitlines()
            tag_line = lines[0].strip()

            if not (tag_line.startswith("[") and tag_line.endswith("| pending]")):
                new_blocks.append(block)
                continue

            fields = [f.strip() for f in tag_line[1:-1].split("|")]
            if len(fields) < 4:
                new_blocks.append(block)
                continue

            trade_date, ticker, rating = fields[:3]
            upd = update_map.get((trade_date, ticker))
            if upd is None:
                new_blocks.append(block)
                continue

            raw_pct = f"{upd['raw_return']:+.1%}"
            alpha_pct = f"{upd['alpha_return']:+.1%}"
            new_tag = (
                f"[{trade_date} | {ticker} | {rating}"
                f" | {raw_pct} | {alpha_pct} | {upd['holding_days']}d]"
            )
            rest = "\n".join(lines[1:])
            new_blocks.append(
                f"{new_tag}\n\n{rest.lstrip()}\n\nREFLECTION:\n{upd['reflection']}"
            )
            del update_map[(trade_date, ticker)]

        new_blocks = self._apply_rotation(new_blocks)
        new_text = self._SEPARATOR.join(new_blocks)
        self._atomic_write_text(new_text)

    # --- Helpers ---

    def _invalidate_entries_cache(self) -> None:
        self._entries_cache_mtime_ns = None
        self._entries_cache = None

    def _path_lock(self) -> threading.Lock:
        assert self._log_path is not None
        lock_path = self._log_path.resolve()
        with self._path_locks_guard:
            lock = self._path_locks.get(lock_path)
            if lock is None:
                lock = threading.Lock()
                self._path_locks[lock_path] = lock
            return lock

    def _atomic_write_text(self, text: str) -> None:
        """Write the full memory log with an atomic same-directory replace."""
        assert self._log_path is not None
        tmp_name = None
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=self._log_path.parent,
            prefix=f"{self._log_path.name}.",
            suffix=".tmp",
        ) as tmp:
            tmp.write(text)
            tmp_name = tmp.name

        tmp_path = Path(tmp_name)
        try:
            tmp_path.replace(self._log_path)
        finally:
            self._invalidate_entries_cache()
            if tmp_path.exists():
                tmp_path.unlink()

    def _apply_rotation(self, blocks: List[str]) -> List[str]:
        """Drop oldest resolved blocks when their count exceeds max_entries.

        Pending blocks are always kept (they represent unprocessed work).
        Returns ``blocks`` unchanged when rotation is disabled or under cap.
        """
        if not self._max_entries or self._max_entries <= 0:
            return blocks

        # Tag each block with (kept, is_resolved) by parsing tag-line markers.
        decisions = []
        for block in blocks:
            stripped = block.strip()
            if not stripped:
                decisions.append((block, False))
                continue
            tag_line = stripped.splitlines()[0].strip()
            is_resolved = (
                tag_line.startswith("[")
                and tag_line.endswith("]")
                and not tag_line.endswith("| pending]")
            )
            decisions.append((block, is_resolved))

        resolved_count = sum(1 for _, r in decisions if r)
        if resolved_count <= self._max_entries:
            return blocks

        to_drop = resolved_count - self._max_entries
        kept: List[str] = []
        for block, is_resolved in decisions:
            if is_resolved and to_drop > 0:
                to_drop -= 1
                continue
            kept.append(block)
        return kept

    def _parse_entry(self, raw: str) -> Optional[dict]:
        lines = raw.strip().splitlines()
        if not lines:
            return None
        tag_line = lines[0].strip()
        if not (tag_line.startswith("[") and tag_line.endswith("]")):
            return None
        fields = [f.strip() for f in tag_line[1:-1].split("|")]
        if len(fields) < 4:
            return None
        entry = {
            "date": fields[0],
            "ticker": fields[1],
            "rating": fields[2],
            "pending": fields[3] == "pending",
            "raw": fields[3] if fields[3] != "pending" else None,
            "alpha": fields[4] if len(fields) > 4 else None,
            "holding": fields[5] if len(fields) > 5 else None,
        }
        body = "\n".join(lines[1:]).strip()
        decision_match = self._DECISION_RE.search(body)
        reflection_match = self._REFLECTION_RE.search(body)
        entry["decision"] = decision_match.group(1).strip() if decision_match else ""
        entry["reflection"] = reflection_match.group(1).strip() if reflection_match else ""
        return entry

    def _format_full(self, e: dict) -> str:
        raw = e["raw"] or "n/a"
        alpha = e["alpha"] or "n/a"
        holding = e["holding"] or "n/a"
        tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | {raw} | {alpha} | {holding}]"
        parts = [tag, f"DECISION:\n{e['decision']}"]
        if e["reflection"]:
            parts.append(f"REFLECTION:\n{e['reflection']}")
        return "\n\n".join(parts)

    def _format_reflection_only(self, e: dict) -> str:
        tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | {e['raw'] or 'n/a'}]"
        if e["reflection"]:
            return f"{tag}\n{e['reflection']}"
        text = e["decision"][:300]
        suffix = "..." if len(e["decision"]) > 300 else ""
        return f"{tag}\n{text}{suffix}"
