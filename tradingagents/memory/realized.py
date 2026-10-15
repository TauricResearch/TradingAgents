"""Real-portfolio realized-P&L reader, recording, and attribution.

Reads a manually-maintained, broker-independent CSV of the user's real
positions (``config["portfolio"]["path"]``). Each *closed* position's realized
return — the ground truth of the money actually made — is recorded into the
memory log via ``TradingMemoryLog.merge_realized`` and folded into calibration,
where it leads the model's predicted horizon alphas. Open positions (no close
yet) are left alone until their close is filled in.

CSV format (header row required; ``#`` comments and blank lines ignored)::

    ticker,shares,entry_date,entry_price,close_date,close_price,note
    RHM.DE,20,2026-10-09,983.30,,
    RHM.DE,15,2026-10-09,983.30,2026-12-01,950.00,cut first tranche at stop

A row is *closed* when both ``close_date`` and ``close_price`` are present;
otherwise it is an open position. Multiple closed rows on the same
(ticker, entry_date) are aggregated (shares summed, prices weighted-averaged),
so a position opened in tranches on one day records a single realized outcome.
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# A run of digits with optional thousands/decimal separators — the numeric
# core of a cell, ignoring any surrounding currency labels or text.
_NUM_RE = re.compile(r"[-+]?\d[\d.,]*")

# Expected column names (matched case-insensitively, by name).
_COLUMNS = ("ticker", "shares", "entry_date", "entry_price",
            "close_date", "close_price", "note")
_REQUIRED = ("ticker", "shares", "entry_date", "entry_price")


@dataclass
class RealizedTrade:
    """One real position, aggregated per (ticker, entry_date).

    ``close_date``/``close_price`` are empty/zero while the position is open;
    ``is_closed`` is False then and ``realized_return``/``realized_pnl`` must
    not be read.
    """
    ticker: str
    shares: float
    entry_date: str
    entry_price: float
    close_date: str = ""
    close_price: float = 0.0
    note: str = ""

    @property
    def is_closed(self) -> bool:
        return bool(self.close_date) and self.close_price > 0

    @property
    def realized_return(self) -> float:
        """Fraction actually realized: (close - entry) / entry.

        Only meaningful when :attr:`is_closed`.
        """
        return (self.close_price - self.entry_price) / self.entry_price

    @property
    def realized_pnl(self) -> float:
        """Realized P&L in the position's currency: (close - entry) * shares."""
        return (self.close_price - self.entry_price) * self.shares


def _num(value) -> float | None:
    """Parse a decimal that may carry thousands separators or a currency label.

    Handles ``950.00``, ``1,234.56`` (thousands), ``12,5`` / ``1.234,56``
    (decimal comma) and ``950.00 EUR`` (trailing currency code). Returns
    ``None`` for anything that is not a number (blank, ``n/a``, ``-``, ...) so
    callers can treat it as "not present".
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"n/a", "na", "none", "-", "--"}:
        return None
    m = _NUM_RE.search(s)
    if not m:
        return None
    core = m.group(0)
    if "," in core and "." in core:
        if core.rfind(".") > core.rfind(","):
            core = core.replace(",", "")    # 1,234.56 (US: dot is decimal)
        else:
            core = core.replace(".", "").replace(",", ".")  # 1.234,56 (DE)
    elif "," in core:
        whole, frac = core.split(",", 1)
        if len(frac) <= 2 and len(whole) <= 3:
            core = core.replace(",", ".")   # 12,5 (decimal comma)
        else:
            core = core.replace(",", "")    # 1,234 (thousands)
    try:
        return float(core)
    except ValueError:
        return None


def _read_rows(path: Path) -> list[dict]:
    """The CSV's data rows as dicts keyed by the normalised column names.

    Comments (``#``) and blank lines are dropped before parsing so the first
    remaining line is the header. Raises ``ValueError`` when a required column
    is missing from the header.
    """
    with path.open(encoding="utf-8-sig") as fh:
        raw = fh.read()
    lines = [ln for ln in raw.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    if len(lines) < 2:
        return []  # header only (or an empty file)
    header = [h.strip().lower() for h in next(csv.reader([lines[0]]))]
    col = {h: i for i, h in enumerate(header) if h}
    missing = [c for c in _REQUIRED if c not in col]
    if missing:
        raise ValueError(
            f"portfolio file {path.name} is missing required column(s) "
            f"{', '.join(missing)}; expected header: {','.join(_COLUMNS)}")
    rows = []
    for line in lines[1:]:
        cells = next(csv.reader([line]))
        rec = {name: (cells[col[name]].strip() if name in col and col[name] < len(cells) else "")
               for name in _COLUMNS}
        rows.append(rec)
    return rows


def _parse_position(rec: dict) -> RealizedTrade | None:
    """One CSV row -> a RealizedTrade, or None when it cannot be valued."""
    ticker = rec["ticker"].strip().upper()
    shares = _num(rec["shares"])
    entry_date = rec["entry_date"].strip()
    entry_price = _num(rec["entry_price"])
    close_date = rec["close_date"].strip()
    close_price = _num(rec["close_price"])
    note = rec["note"].strip()
    if not ticker or not entry_date or shares is None or shares <= 0 \
            or entry_price is None or entry_price <= 0:
        logger.warning("portfolio: skipping unvaluable row %s "
                       "(ticker=%s shares=%s entry_date=%s entry_price=%s)",
                       rec, rec["ticker"], rec["shares"], rec["entry_date"], rec["entry_price"])
        return None
    # Closed needs BOTH a close date and a close price; a half-filled close is
    # treated as still open (with a nudge) rather than scored on a stub.
    closed = bool(close_date) and close_price is not None and close_price > 0
    if bool(close_date) != (close_price is not None):
        logger.warning("portfolio: %s has close_date=%r but close_price=%r; keeping it open",
                       ticker, close_date, rec["close_price"])
    cd, cp = "", 0.0
    if closed:
        assert close_price is not None  # `closed` requires a valid close price
        cd, cp = close_date, float(close_price)
    return RealizedTrade(
        ticker=ticker, shares=shares, entry_date=entry_date, entry_price=entry_price,
        close_date=cd, close_price=cp, note=note,
    )


def load_positions(path) -> list[RealizedTrade]:
    """Parse the portfolio CSV into per-position records (open **and** closed).

    Rows that cannot be valued are skipped with a warning. A position is
    closed when both its close date and close price are present; otherwise it
    is open (``is_closed`` False).
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"portfolio file not found: {p}")
    out = []
    for rec in _read_rows(p):
        pos = _parse_position(rec)
        if pos is not None:
            out.append(pos)
    return out


def aggregate_closed(positions: list[RealizedTrade]) -> list[RealizedTrade]:
    """Closed positions only, aggregated per (ticker, entry_date).

    Shares are summed and entry/close prices weighted-averaged by shares, so a
    position opened in several tranches on one day yields a single realized
    outcome. Notes are joined.
    """
    groups: dict[tuple[str, str], list[RealizedTrade]] = {}
    order: list[tuple[str, str]] = []
    for p in positions:
        if not p.is_closed:
            continue
        key = (p.ticker, p.entry_date)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(p)
    out = []
    for key in order:
        rows = groups[key]
        total = sum(r.shares for r in rows)
        w_entry = sum(r.shares * r.entry_price for r in rows) / total
        w_close = sum(r.shares * r.close_price for r in rows) / total
        notes = [r.note for r in rows if r.note]
        out.append(RealizedTrade(
            ticker=key[0], shares=total, entry_date=key[1],
            entry_price=w_entry, close_price=w_close,
            close_date=max(r.close_date for r in rows),
            note="; ".join(notes),
        ))
    return out


def load_realized_trades(path) -> list[RealizedTrade]:
    """The file's closed positions, aggregated per (ticker, entry_date)."""
    return aggregate_closed(load_positions(path))


def record_realized_trades(memory_log, config: dict) -> list[tuple]:
    """Record each closed position's realized return into the memory log.

    Only (ticker, entry_date) pairs that already exist as decisions in the log
    are recorded — realized P&L attributes to a decision the model made, not to
    an unanalysed position. Idempotent: a pair already recorded with the same
    return is left alone. Returns the (ticker, entry_date, realized_return)
    triples (re)recorded this pass.
    """
    port = config.get("portfolio") or {}
    path = port.get("path")
    if not path:
        return []
    try:
        trades = load_realized_trades(path)
    except Exception as exc:
        logger.warning("Reading the real-portfolio file failed: %s", exc)
        return []
    existing = {}
    for e in memory_log.load_entries():
        r = e.get("realized")
        if isinstance(r, dict) and r.get("return") is not None:
            existing[(e["ticker"], e["date"])] = r["return"]
    recorded = []
    for t in trades:
        prev = existing.get((t.ticker, t.entry_date))
        ret = t.realized_return
        if prev is not None and abs(prev - ret) < 1e-9:
            continue  # already recorded
        try:
            if memory_log.merge_realized(t.ticker, t.entry_date, ret,
                                          close_date=t.close_date, note=t.note or None):
                recorded.append((t.ticker, t.entry_date, ret))
        except Exception as exc:
            logger.warning("Recording realized P&L for %s on %s failed: %s",
                           t.ticker, t.entry_date, exc)
    return recorded


def _direction_hit(rating, value: float):
    """Did ``value`` land on ``rating``'s expected side? Mirrors calibration's
    ``_hit`` (Buy/Overweight -> up, Sell/Underweight -> down, Hold -> flat)."""
    if value is None:
        return None
    r = (rating or "").strip().lower()
    if r in {"buy", "overweight"}:
        return value > 0
    if r in {"sell", "underweight"}:
        return value < 0
    if r in {"hold", "neutral"}:
        return abs(value) < 0.02
    return None


def attribute_realized(memory_log, config: dict, as_of: str | None = None) -> list[dict]:
    """Join closed real positions with the decisions that opened them.

    Returns one dict per closed position the system analysed, carrying the
    realized return, P&L (currency), the decision's rating, and whether the call
    "hit" (the realized return landed on the rating's expected side). When
    ``config["portfolio"]["benchmark_ticker"]`` is set, the realized alpha
    versus that benchmark over the holding window is included (``None`` on any
    price failure — the figure is then absent, never wrong). ``as_of`` drops
    positions closed after that date, keeping backtests look-ahead clean.
    """
    port = config.get("portfolio") or {}
    path = port.get("path")
    currency = port.get("currency", "EUR")
    if not path:
        return []
    try:
        trades = load_realized_trades(path)
    except Exception as exc:
        logger.warning("Reading the real-portfolio file failed: %s", exc)
        return []
    entries = {(e["ticker"], e["date"]): e for e in memory_log.load_entries()}
    out = []
    for t in trades:
        if as_of and t.close_date and t.close_date > as_of:
            continue
        e = entries.get((t.ticker, t.entry_date))
        if e is None:
            continue  # a real position the model never analysed
        ret = t.realized_return
        item = {
            "ticker": t.ticker, "entry_date": t.entry_date, "close_date": t.close_date,
            "shares": t.shares, "entry_price": t.entry_price, "close_price": t.close_price,
            "return": ret, "pnl": t.realized_pnl, "currency": currency,
            "rating": e.get("rating"), "hit": _direction_hit(e.get("rating"), ret),
            "note": t.note,
        }
        bench = port.get("benchmark_ticker")
        if bench:
            item["alpha"] = _realized_alpha(bench, t.entry_date, t.close_date, ret)
        out.append(item)
    return out


def _realized_alpha(benchmark: str, entry_date: str, close_date: str,
                    ret: float) -> float | None:
    """Realized alpha = realized return minus the benchmark's move over the same
    window. ``None`` on any price fetch failure (offline-safe)."""
    try:
        from tradingagents.memory import settlement
        bench = settlement._by_day(
            settlement.get_closes(benchmark, entry_date, close_date))
        if bench is None or bench.empty or len(bench) < 2:
            return None
        entry_px, exit_px = float(bench.iloc[0]), float(bench.iloc[-1])
        if entry_px <= 0:
            return None
        return ret - (exit_px - entry_px) / entry_px
    except Exception:
        return None


def render_realized_attribution(attributions: list[dict], ticker: str) -> str:
    """A compact line of realized P&L: the analysed ticker, then the book.

    Empty when there is nothing realized, so it is a no-op until the user
    closes a position the system had called.
    """
    if not attributions:
        return ""
    same = [a for a in attributions if a["ticker"] == ticker]
    cross = attributions

    def _fmt(subset: list[dict]) -> str:
        if not subset:
            return ""
        hits = sum(1 for a in subset if a["hit"])
        total = sum(a["pnl"] for a in subset)
        cur = subset[0].get("currency", "")
        head = f"{len(subset)} trade(s), {hits}/{len(subset)} hit, {total:+,.2f} {cur}"
        detail = " | ".join(
            f"{a['entry_date']} {a['return']:+.1%}" + (f" vs {a['alpha']:+.1%}" if a.get("alpha") is not None else "")
            for a in subset)
        return f"{head} ({detail})"

    parts = []
    if same:
        parts.append(f"{ticker}: {_fmt(same)}")
    if len(cross) > len(same):
        parts.append(f"all tickers: {_fmt(cross)}")
    if not parts:
        return ""
    return "REALIZED P&L — " + " | ".join(parts)
