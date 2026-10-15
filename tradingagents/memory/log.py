"""The memory log: an append-only markdown record of each decision and, once settled, its outcome."""

import contextlib
import json
import re
from pathlib import Path

from tradingagents.agents.rating import parse_rating
from tradingagents.dataflows.files import locked


class TradingMemoryLog:
    """Append-only markdown log of trading decisions and reflections."""

    # HTML comment: cannot appear in LLM prose output, safe as a hard delimiter
    _SEPARATOR = "\n\n<!-- ENTRY_END -->\n\n"
    # Precompiled patterns — avoids re-compilation on every load_entries() call
    # HORIZONS (multi-horizon outcomes) sits between DECISION and REFLECTION.
    # The DECISION regex must stop before it, otherwise the JSON leaks into the
    # decision text; REFLECTION is the final section (greedy to end).
    _DECISION_RE = re.compile(r"DECISION:\n(.*?)(?=\n(?:HORIZONS|REALIZED|REFLECTION_COVERS|REFLECTION):|\Z)", re.DOTALL)
    _REFLECTION_RE = re.compile(r"REFLECTION:\n(.*)\Z", re.DOTALL)
    _HORIZONS_RE = re.compile(r"HORIZONS:\n(.*)")
    _REALIZED_RE = re.compile(r"REALIZED:\n(.*)")
    _REFLECTION_COVERS_RE = re.compile(r"REFLECTION_COVERS:\n(.*)")

    def __init__(self, config: dict = None):
        cfg = config or {}
        self._log_path = None
        path = cfg.get("memory_log_path")
        if path:
            self._log_path = Path(path).expanduser()
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
        # Optional cap on resolved entries. None disables rotation.
        self._max_entries = cfg.get("memory_log_max_entries")

    # --- Write: a run records its decision ---

    def store_decision(
        self,
        ticker: str,
        trade_date: str,
        final_trade_decision: str,
        rating: str | None = None,
    ) -> None:
        """Store the final decision (one entry per ticker+date, latest wins).

        Idempotency: re-running the SAME decision for the same date is a no-op.
        A *different* rating for the same ticker+date is a distinct same-day
        run (e.g. a higher-quality model pass finishing later); it SUPERSEDES
        the earlier still-pending entry so the freshest analysis is the one
        that gets settled and reused. A finalized (resolved) entry is never
        superseded — its outcome is final.
        """
        if not self._log_path:
            return
        rating = rating or parse_rating(final_trade_decision)
        with locked(self._log_path):
            existing = self._log_path.read_text(encoding="utf-8") if self._log_path.exists() else ""
            if existing:
                prefix = f"[{trade_date} | {ticker} |"
                new_entry = self._new_entry(trade_date, ticker, rating, final_trade_decision)
                blocks = existing.split(self._SEPARATOR)
                for i, block in enumerate(blocks):
                    tag_line = block.strip().splitlines()[0].strip() if block.strip() else ""
                    if tag_line.startswith(prefix) and tag_line.endswith("]"):
                        fields = [f.strip() for f in tag_line[1:-1].split("|")]
                        if fields[3] != "pending":
                            return  # finalized outcome — never supersede
                        if len(fields) >= 3 and fields[2] == rating:
                            return  # idempotent re-run of the same decision
                        blocks[i] = new_entry  # different rating, still pending -> supersede
                        self._atomic_write(self._SEPARATOR.join(blocks))
                        return
            self._append_entry(self._new_entry(trade_date, ticker, rating, final_trade_decision))

    def _new_entry(self, trade_date: str, ticker: str, rating: str, decision: str) -> str:
        tag = f"[{trade_date} | {ticker} | {rating} | pending]"
        return f"{tag}\n\nDECISION:\n{decision}"

    def _append_entry(self, entry: str) -> None:
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(entry + self._SEPARATOR)

    def _atomic_write(self, text: str) -> None:
        tmp = self._log_path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self._log_path)

    def settling(self, wait: bool = True):
        """Hold the log for one settlement pass at a time, across threads and processes.

        A pass reads the pending entries, asks the model for a reflection on
        each and writes it; two passes at once would pay for the same
        reflections. A separate lock from the one each write takes. Yields
        whether it is held; with ``wait=False`` another pass is not waited for.
        """
        if not self._log_path:
            return contextlib.nullcontext(True)
        return locked(f"{self._log_path}.settle", wait=wait)

    # --- Read ---

    def load_entries(self) -> list[dict]:
        """Parse all entries from log. Returns list of dicts."""
        if not self._log_path or not self._log_path.exists():
            return []
        text = self._log_path.read_text(encoding="utf-8")
        raw_entries = [e.strip() for e in text.split(self._SEPARATOR) if e.strip()]
        entries = []
        for raw in raw_entries:
            parsed = self._parse_entry(raw)
            if parsed:
                entries.append(parsed)
        return entries

    def get_pending_entries(self) -> list[dict]:
        """Return entries with outcome:pending, for settlement."""
        return [e for e in self.load_entries() if e.get("pending")]

    def get_entries_needing_settlement(self, horizons: list[int]) -> list[dict]:
        """Entries still needing settlement work.

        An entry is included when it is: still pending (the anchor window must
        trade out and finalize); resolved but a configured horizon is not yet
        measured; or resolved and its stored lesson lags the windows measured so
        far (the multi-horizon lesson is refreshed as longer windows close).
        """
        anchor = horizons[0]
        out = []
        for e in self.load_entries():
            hz = e.get("horizons") or {}
            if e.get("pending"):
                out.append(e)
                continue
            scored = {
                h for h, v in hz.items()
                if isinstance(v, dict) and v.get("alpha") is not None
            }
            missing = any(h not in hz for h in horizons)
            stale = (anchor in scored) and bool(scored - set(e.get("reflection_covers") or []))
            if missing or stale:
                out.append(e)
        return out

    def get_past_context(
        self, ticker: str, n_same: int = 5, n_cross: int = 3, as_of: str | None = None
    ) -> str:
        """Return formatted past context string for agent prompt injection.

        When ``as_of`` (yyyy-mm-dd) is given, only lessons whose outcome was
        already known by that date are included — an entry is kept only if it
        stores a resolution date (``resolved:...``) that is on or before
        ``as_of``. This keeps a historical/backtest run from learning from
        outcomes that had not happened yet (#1251). ``as_of=None`` disables the
        filter, so live runs and pre-migration entries are unaffected.
        """
        entries = [e for e in self.load_entries() if not e.get("pending")]
        if as_of is not None:
            entries = [e for e in entries if e.get("resolved") and e["resolved"] <= as_of]
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

    # --- Settle: record a decision's outcome and reflection ---

    def update_with_outcome(
        self,
        ticker: str,
        trade_date: str,
        raw_return: float,
        alpha_return: float,
        holding_days: int,
        reflection: str,
        resolution_date: str | None = None,
    ) -> bool:
        """Replace pending tag and append REFLECTION section using atomic write.

        Returns whether an entry was updated: False when the decision was no
        longer pending (another pass settled it first).

        Finds the first pending entry matching (trade_date, ticker), updates
        its tag with return figures (and the ``resolution_date`` the outcome
        became known), and appends a REFLECTION section.  Uses a temp-file +
        os.replace() so a crash mid-write never corrupts the log.
        """
        if not self._log_path or not self._log_path.exists():
            return False
        with locked(self._log_path):
            text = self._log_path.read_text(encoding="utf-8")
            blocks = text.split(self._SEPARATOR)

            pending_prefix = f"[{trade_date} | {ticker} |"
            raw_pct = f"{raw_return:+.1%}"
            alpha_pct = f"{alpha_return:+.1%}"

            updated = False
            new_blocks = []
            for block in blocks:
                stripped = block.strip()
                if not stripped:
                    new_blocks.append(block)
                    continue

                lines = stripped.splitlines()
                tag_line = lines[0].strip()

                if (
                    not updated
                    and tag_line.startswith(pending_prefix)
                    and tag_line.endswith("| pending]")
                ):
                    fields = [f.strip() for f in tag_line[1:-1].split("|")]
                    rating = fields[2]
                    new_tag = self._resolved_tag(
                        trade_date, ticker, rating, raw_pct, alpha_pct, holding_days, resolution_date
                    )
                    rest = "\n".join(lines[1:])
                    new_blocks.append(
                        f"{new_tag}\n\n{rest.lstrip()}\n\nREFLECTION:\n{reflection}"
                    )
                    updated = True
                else:
                    new_blocks.append(block)

            if not updated:
                return False

            new_blocks = self._apply_rotation(new_blocks)
            new_text = self._SEPARATOR.join(new_blocks)
            tmp_path = self._log_path.with_suffix(".tmp")
            tmp_path.write_text(new_text, encoding="utf-8")
            tmp_path.replace(self._log_path)
            return True

    def merge_horizons(self, ticker: str, trade_date: str,
                       horizon_results: dict[int, tuple],
                       reflection: str | None = None,
                       anchor_days: int | None = None,
                       resolution_date: str | None = None,
                       reflection_covers: list[int] | None = None,
                       realized: dict | None = None) -> bool:
        """Merge scored horizon outcomes into the (date,ticker) entry.

        ``horizon_results`` maps horizon-days -> (raw, alpha, days, resolution).
        When the entry is still pending and the anchor horizon is present, the
        entry is finalised (tag -> resolved, reflection stored). When the entry
        is already resolved, further horizons are simply accumulated. Returns
        True if the log changed.

        ``reflection`` (when given) replaces the stored lesson;
        ``reflection_covers`` (when given) records the windows that lesson was
        written over (None preserves the stored list). ``realized`` (when
        given) records the real-portfolio realized outcome; None preserves the
        stored one. Finalisation requires ``anchor_days`` to be passed
        explicitly (not inferred), so a caller that only adds numbers can never
        accidentally flip an entry's state.
        """
        if not self._log_path or not self._log_path.exists():
            return False
        with locked(self._log_path):
            text = self._log_path.read_text(encoding="utf-8")
            blocks = text.split(self._SEPARATOR)
            prefix = f"[{trade_date} | {ticker} |"
            updated = False
            for i, block in enumerate(blocks):
                if not block.strip():
                    continue
                tag_line = block.strip().splitlines()[0].strip()
                if not (tag_line.startswith(prefix) and tag_line.endswith("]")):
                    continue
                fields = [f.strip() for f in tag_line[1:-1].split("|")]
                rating = fields[2]
                was_pending = fields[3] == "pending"
                body = "\n".join(block.strip().splitlines()[1:])
                resolved_date_m = re.search(r"resolved:(\S+)\]", tag_line)
                legacy = {
                    "holding": (fields[5] if len(fields) > 5 else None),
                    "raw": (fields[3] if fields[3] != "pending" else None),
                    "alpha": (fields[4] if len(fields) > 4 else None),
                    "resolved": resolved_date_m.group(1) if resolved_date_m else None,
                }
                hz = self._parse_horizons(body, legacy)
                for h, r in horizon_results.items():
                    raw, alpha, _days, res = r
                    hz[int(h)] = {"raw": raw, "alpha": alpha, "resolution": res}
                dm = self._DECISION_RE.search(body)
                decision = dm.group(1).strip() if dm else ""
                # Finalise only when the caller names the anchor horizon explicitly.
                anchor = int(anchor_days) if anchor_days is not None else None
                if was_pending and anchor is not None and anchor in hz:
                    a = hz[anchor]
                    raw_s = f"{a['raw']:+.1%}" if isinstance(a["raw"], (int, float)) else "n/a"
                    alpha_s = f"{a['alpha']:+.1%}" if isinstance(a["alpha"], (int, float)) else "n/a"
                    new_tag = self._resolved_tag(trade_date, ticker, rating, raw_s, alpha_s,
                                                 anchor, resolution_date)
                else:
                    new_tag = tag_line
                refl = (reflection or "").strip()
                if not refl:
                    rm = self._REFLECTION_RE.search(body)
                    refl = rm.group(1).strip() if rm else ""
                covers_m = self._REFLECTION_COVERS_RE.search(body)
                covers = (reflection_covers if reflection_covers is not None
                          else self._parse_covers(covers_m.group(1) if covers_m else None))
                realized_m = self._REALIZED_RE.search(body)
                realized_val = (realized if realized is not None
                                else self._parse_realized(realized_m.group(1) if realized_m else None))
                new_block = f"{new_tag}\n\nDECISION:\n{decision}"
                if hz:
                    new_block += ("\n\nHORIZONS:\n"
                                  + json.dumps({str(k): v for k, v in sorted(hz.items())}, ensure_ascii=False))
                if isinstance(realized_val, dict) and realized_val.get("return") is not None:
                    new_block += "\n\nREALIZED:\n" + json.dumps(realized_val, ensure_ascii=False)
                if refl and covers:
                    new_block += "\n\nREFLECTION_COVERS:\n" + ", ".join(str(h) for h in sorted(covers))
                if refl:
                    new_block += "\n\nREFLECTION:\n" + refl
                blocks[i] = new_block
                updated = True
                break
            if not updated:
                return False
            blocks = self._apply_rotation(blocks)
            self._atomic_write(self._SEPARATOR.join(blocks))
        return True

    def merge_realized(self, ticker: str, trade_date: str, realized_return,
                       close_date: str | None = None, note: str | None = None) -> bool:
        """Record the real-portfolio realized outcome for (date, ticker).

        ``realized_return`` is the fraction actually realized when the position
        was closed — the ground truth, preferred over the horizon windows for
        calibration. Stored as a REALIZED block; the entry's tag, horizons and
        reflection are untouched (a still-pending entry is never flipped, since
        no anchor is passed).
        """
        block = {
            "return": float(realized_return) if isinstance(realized_return, (int, float)) else None,
            "close_date": close_date,
            "note": (note or "").strip() or None,
        }
        return self.merge_horizons(
            ticker, trade_date, {}, None,
            anchor_days=None, resolution_date=None,
            reflection_covers=None, realized=block,
        )

    def batch_update_with_outcomes(self, updates: list[dict]) -> None:
        """Apply multiple outcome updates in a single read + atomic write.

        Each element of updates must have keys: ticker, trade_date,
        raw_return, alpha_return, holding_days, reflection.
        """
        if not self._log_path or not self._log_path.exists() or not updates:
            return
        with locked(self._log_path):
            text = self._log_path.read_text(encoding="utf-8")
            blocks = text.split(self._SEPARATOR)

            update_map = {(u["trade_date"], u["ticker"]): u for u in updates}

            new_blocks = []
            for block in blocks:
                stripped = block.strip()
                if not stripped:
                    new_blocks.append(block)
                    continue

                lines = stripped.splitlines()
                tag_line = lines[0].strip()

                matched = False
                for (trade_date, ticker), upd in list(update_map.items()):
                    pending_prefix = f"[{trade_date} | {ticker} |"
                    if tag_line.startswith(pending_prefix) and tag_line.endswith("| pending]"):
                        fields = [f.strip() for f in tag_line[1:-1].split("|")]
                        rating = fields[2]
                        raw_pct = f"{upd['raw_return']:+.1%}"
                        alpha_pct = f"{upd['alpha_return']:+.1%}"
                        new_tag = self._resolved_tag(
                            trade_date, ticker, rating, raw_pct, alpha_pct,
                            upd["holding_days"], upd.get("resolution_date"),
                        )
                        rest = "\n".join(lines[1:])
                        new_blocks.append(
                            f"{new_tag}\n\n{rest.lstrip()}\n\nREFLECTION:\n{upd['reflection']}"
                        )
                        del update_map[(trade_date, ticker)]
                        matched = True
                        break

                if not matched:
                    new_blocks.append(block)

            new_blocks = self._apply_rotation(new_blocks)
            new_text = self._SEPARATOR.join(new_blocks)
            tmp_path = self._log_path.with_suffix(".tmp")
            tmp_path.write_text(new_text, encoding="utf-8")
            tmp_path.replace(self._log_path)

    # --- Helpers ---

    @staticmethod
    def _resolved_tag(
        trade_date, ticker, rating, raw_pct, alpha_pct, holding_days, resolution_date
    ) -> str:
        """Build a resolved entry tag, recording the outcome's known-by date.

        ``resolution_date`` (the date of the last price bar used for the return)
        is the point-in-time cutoff a later run filters on (#1251). Omitted when
        unavailable, keeping the legacy 6-field tag.
        """
        tag = f"[{trade_date} | {ticker} | {rating} | {raw_pct} | {alpha_pct} | {holding_days}d"
        if resolution_date:
            tag += f" | resolved:{resolution_date}"
        return tag + "]"

    def _apply_rotation(self, blocks: list[str]) -> list[str]:
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
        kept: list[str] = []
        for block, is_resolved in decisions:
            if is_resolved and to_drop > 0:
                to_drop -= 1
                continue
            kept.append(block)
        return kept

    @staticmethod
    def _pct_to_frac(s) -> float | None:
        """Parse a stored percent tag ('+3.1%') into a fraction (0.031)."""
        if s is None:
            return None
        t = str(s).strip()
        if t in ("", "n/a", "None", "pending"):
            return None
        t = t.rstrip("%").strip()
        try:
            return float(t) / 100.0
        except ValueError:
            return None

    @staticmethod
    def _parse_covers(body: str | None) -> list[int] | None:
        """Parse a REFLECTION_COVERS line (comma-separated horizon days)."""
        if body is None:
            return None
        vals = []
        for part in str(body).split(","):
            part = part.strip()
            if not part:
                continue
            try:
                vals.append(int(part))
            except ValueError:
                pass
        return vals or None

    @staticmethod
    def _parse_realized(body: str | None) -> dict | None:
        """Parse a REALIZED block (JSON) into the realized-outcome dict."""
        if body is None:
            return None
        try:
            data = json.loads(body.strip())
        except (ValueError, AttributeError, TypeError):
            return None
        if not isinstance(data, dict) or data.get("return") is None:
            return None
        return {"return": data.get("return"),
                "close_date": data.get("close_date"),
                "note": data.get("note")}

    def _parse_horizons(self, body: str, legacy: dict) -> dict[int, dict]:
        """Extract the HORIZONS block; for legacy entries (no block) fall back
        to the single anchor horizon implied by the resolved tag."""
        m = self._HORIZONS_RE.search(body)
        if m:
            try:
                data = json.loads(m.group(1).strip())
                return {int(k): {"raw": v.get("raw"), "alpha": v.get("alpha"),
                                 "resolution": v.get("resolution")}
                        for k, v in data.items()}
            except (ValueError, AttributeError, TypeError):
                return {}
        holding, raw, alpha = legacy.get("holding"), legacy.get("raw"), legacy.get("alpha")
        if holding is not None and raw is not None:
            try:
                hd = int(str(holding).rstrip("d"))
                return {hd: {"raw": self._pct_to_frac(raw),
                             "alpha": self._pct_to_frac(alpha),
                             "resolution": legacy.get("resolved")}}
            except ValueError:
                pass
        return {}

    def _parse_entry(self, raw: str) -> dict | None:
        lines = raw.strip().splitlines()
        if not lines:
            return None
        tag_line = lines[0].strip()
        if not (tag_line.startswith("[") and tag_line.endswith("]")):
            return None
        fields = [f.strip() for f in tag_line[1:-1].split("|")]
        if len(fields) < 4:
            return None
        # Optional trailing "resolved:YYYY-MM-DD" field records when the outcome
        # became known, for point-in-time filtering (#1251).
        resolved = None
        for f in fields[6:]:
            if f.startswith("resolved:"):
                resolved = f[len("resolved:"):].strip()
        entry = {
            "date": fields[0],
            "ticker": fields[1],
            "rating": fields[2],
            "pending": fields[3] == "pending",
            "raw": fields[3] if fields[3] != "pending" else None,
            "alpha": fields[4] if len(fields) > 4 else None,
            "holding": fields[5] if len(fields) > 5 else None,
            "resolved": resolved,
        }
        body = "\n".join(lines[1:]).strip()
        decision_match = self._DECISION_RE.search(body)
        reflection_match = self._REFLECTION_RE.search(body)
        entry["decision"] = decision_match.group(1).strip() if decision_match else ""
        entry["reflection"] = reflection_match.group(1).strip() if reflection_match else ""
        entry["horizons"] = self._parse_horizons(body, entry)
        covers_match = self._REFLECTION_COVERS_RE.search(body)
        entry["reflection_covers"] = self._parse_covers(
            covers_match.group(1) if covers_match else None)
        realized_match = self._REALIZED_RE.search(body)
        entry["realized"] = self._parse_realized(
            realized_match.group(1) if realized_match else None)
        return entry

    def _format_full(self, e: dict) -> str:
        raw = e["raw"] if e["raw"] is not None else "n/a"
        alpha = e["alpha"] if e["alpha"] is not None else "n/a"
        holding = e["holding"] if e["holding"] is not None else "n/a"
        tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | {raw} | {alpha} | {holding}]"
        parts = [tag]
        line = self._horizons_line(e.get("horizons") or {})
        if line:
            parts.append(line)
        realized = e.get("realized")
        if isinstance(realized, dict) and realized.get("return") is not None:
            rpart = f"REALIZED: {realized['return']:+.1%}"
            if realized.get("close_date"):
                rpart += f" (closed {realized['close_date']})"
            if realized.get("note"):
                rpart += f" — {realized['note']}"
            parts.append(rpart)
        parts.append(f"DECISION:\n{e['decision']}")
        if e["reflection"]:
            parts.append(f"REFLECTION:\n{e['reflection']}")
        return "\n\n".join(parts)

    @staticmethod
    def _horizons_line(horizons: dict) -> str:
        """Compact multi-horizon outcome line (omitted when only the anchor
        horizon is present, since the tag already shows it)."""
        if len(horizons) <= 1:
            return ""
        bits = []
        for h in sorted(horizons):
            v = horizons[h] or {}
            raw = v.get("raw"); alpha = v.get("alpha")
            raw_s = f"{raw:+.1%}" if isinstance(raw, (int, float)) else "n/a"
            alpha_s = f"{alpha:+.1%}" if isinstance(alpha, (int, float)) else "n/a"
            bits.append(f"{h}d {raw_s}/α{alpha_s}")
        return "OUTCOMES: " + " · ".join(bits)

    def _format_reflection_only(self, e: dict) -> str:
        tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | {e['raw'] or 'n/a'}]"
        if e["reflection"]:
            return f"{tag}\n{e['reflection']}"
        text = e["decision"][:300]
        suffix = "..." if len(e["decision"]) > 300 else ""
        return f"{tag}\n{text}{suffix}"
