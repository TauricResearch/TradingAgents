"""Sync jobs: fill the India database from NSE's archives and from saved filings.

Each job walks its keys (a trading day, a file) in order, skips those
``ingest_log`` already has as done unless forced, and logs every key it
touches, so an interrupted run picks up where it stopped. A key that fails is
logged and the run goes on; a host that refuses us, or a network that keeps
failing, stops the run (``SyncAborted``), since every further request would be
refused too.

    securities     EQUITY_L plus NSE's index lists (industry), daily
    prices         a bhavcopy per day (ISIN, OHLC, volume) and MTO (deliveries)
    actions        the PR zip per day: corporate actions and shares issued
    announcements  the same PR zip: announcements and board meetings, for a universe
    import         results and shareholding XBRL saved by hand (NSE's filing
                   pages work only in a browser), from a folder
"""

from __future__ import annotations

import hashlib
import time
import zipfile
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.vendors.india import nse, store
from tradingagents.dataflows.vendors.india.actions import parse_purpose
from tradingagents.dataflows.vendors.india.fetch import ArchiveClient, FetchFailed, SourceBlocked
from tradingagents.dataflows.vendors.india.xbrl import (
    FilingError,
    ResultsFiling,
    ShareholdingFiling,
    filename_stamp,
    parse_filing,
)

UNIVERSES = ("nifty50", "nifty500", "all")
_MAX_CONSECUTIVE_FAILURES = 5
# NSE lists ~2,600 equities; a much shorter list is a broken download, and taking
# it at its word would mark the rest of the market unlisted.
MIN_LISTED = 1000
NSE_ANNOUNCEMENTS = "https://www.nseindia.com/companies-listing/corporate-filings-announcements?symbol={}&tabIndex=equity"

# Announcement kinds, by words in NSE's category (or text, when the file has no
# category), checked in order. Routine notices are not kept at all.
DOCUMENT_KINDS = (
    ("credit_rating", ("credit rating",)),
    ("concall", ("analysts/institutional investor meet", "con. call", "conference call", "earnings call",
                 "concall", "transcript", "audio recording", "video recording")),
    ("investor_presentation", ("investor presentation",)),
    ("annual_report", ("annual report",)),
    ("results", ("financial result",)),
    ("board_meeting", ("outcome of board meeting",)),
)
SKIPPED_ANNOUNCEMENTS = ("trading window", "declaration of nav", "newspaper publication", "share certificate",
                         "regulation 74", "reg. 74", "certificate under sebi (depositories")


class SyncAborted(Exception):
    """A failure no later key would escape: stop and exit non-zero."""


class UnresolvedCompany(FilingError):
    """A filing whose company is not in the securities table (yet)."""


@dataclass
class JobResult:
    job: str
    done: int = 0
    skipped: int = 0
    missing: int = 0
    failed: int = 0
    rows: int = 0
    errors: list[str] = field(default_factory=list)
    elapsed: float = 0.0
    notes: list[str] = field(default_factory=list)

    def fail(self, key: str, error: str) -> None:
        self.failed += 1
        if len(self.errors) < 20:
            self.errors.append(f"{key}: {error}")


class Progress:
    """What a job reports as it goes; the CLI draws it with rich."""

    def start(self, label: str, total: int) -> None:
        pass

    def advance(self, label: str, detail: str = "") -> None:
        pass

    def finish(self, label: str) -> None:
        pass


def inbox_dir() -> Path:
    """Where XBRL files saved by hand are picked up from by default."""
    return Path(get_config()["data_cache_dir"]).expanduser() / "india" / "inbox"


def raw_dir() -> Path:
    return Path(get_config()["data_cache_dir"]).expanduser() / "india" / "raw"


def default_client() -> ArchiveClient:
    config = get_config()
    return ArchiveClient(raw_dir(), interval=float(config.get("india_request_interval") or 1.0),
                         user_agent=config.get("india_user_agent") or None)


def classify_announcement(category: str | None, text: str) -> str | None:
    """A document kind, or None for a routine notice not worth a link."""
    haystack = (category or text).lower()
    if any(s in haystack for s in SKIPPED_ANNOUNCEMENTS):
        return None
    return next((kind for kind, words in DOCUMENT_KINDS if any(w in haystack for w in words)),
                "announcement")


class Syncer:
    def __init__(self, conn, client: ArchiveClient | None = None, progress: Progress | None = None,
                 force: bool = False, today: date | None = None):
        self.conn = conn
        self.client = client or default_client()
        self.progress = progress or Progress()
        self.force = force
        self.today = today or date.today()

    # --- Selection -------------------------------------------------------------------
    def universe(self, symbols: Iterable[str] | None = None, universe: str | None = None) -> set[str] | None:
        """ISINs to work on: the given symbols, an index's constituents, or None for all."""
        if symbols:
            isins, unknown = set(), []
            for s in symbols:
                hit = store.resolve(s, self.conn)
                (isins.add(hit["isin"]) if hit else unknown.append(s))
            if unknown:
                raise SyncAborted(f"not in the securities table: {', '.join(unknown)} "
                                  "(run `tradingagents india sync-securities` first, or check the spelling)")
            return isins
        if universe in (None, "all"):
            return None
        if universe not in nse.INDEX_FILES:
            raise SyncAborted(f"unknown universe {universe!r}; use one of {', '.join(UNIVERSES)}")
        url = nse.index_url(universe)
        data = self._fetch_list(url)
        members = nse.parse_index_list(data)
        store.upsert_securities(self.conn, ({"isin": m["isin"], "nse_symbol": m["symbol"], "name": m["name"],
                                             "industry": m["industry"]} for m in members))
        self.conn.commit()
        return {m["isin"] for m in members}

    def _fetch_list(self, url: str) -> bytes:
        try:
            data = self.client.get(url, nse.cache_name(url))
        except SourceBlocked as exc:
            raise SyncAborted(str(exc)) from exc
        except FetchFailed as exc:
            raise SyncAborted(f"could not fetch {url}: {exc}") from exc
        if data is None:
            raise SyncAborted(f"{url} is not on NSE's archive any more; its address may have changed")
        return data

    # --- Securities ----------------------------------------------------------------------
    def sync_securities(self) -> JobResult:
        result, began = JobResult("securities"), time.monotonic()
        self.progress.start("securities", 1 + len(nse.INDEX_FILES))
        listed = nse.parse_equity_list(self._fetch_list(nse.equity_list_url()))
        self.progress.advance("securities", "EQUITY_L")
        if len(listed) < MIN_LISTED:
            raise SyncAborted(f"NSE's equity list has {len(listed)} rows; refusing to mark the rest unlisted")
        before = {r[0] for r in self.conn.execute("SELECT isin FROM securities WHERE status='listed'")}
        result.rows += store.upsert_securities(self.conn, (
            {"isin": s.isin, "nse_symbol": s.symbol, "name": s.name, "series": s.series,
             "face_value": s.face_value, "listing_date": s.listing_date, "status": "listed"} for s in listed))
        gone = before - {s.isin for s in listed}
        self.conn.executemany("UPDATE securities SET status='unlisted' WHERE isin=?", [(i,) for i in gone])
        industries = 0
        for index in ("niftytotalmarket", "nifty500", "nifty50"):
            for m in nse.parse_index_list(self._fetch_list(nse.index_url(index))):
                if m["industry"]:
                    self.conn.execute("UPDATE securities SET industry=? WHERE isin=?", (m["industry"], m["isin"]))
                    industries += 1
            self.progress.advance("securities", index)
        store.log(self.conn, "securities", self.today.isoformat(), "ok", rows=result.rows,
                  detail=f"{len(listed)} listed, {len(gone)} no longer listed, industry for {industries}")
        self.conn.commit()
        result.done = 1
        result.notes.append(f"{len(listed)} listed securities; {len(gone)} dropped off the list")
        self.progress.finish("securities")
        result.elapsed = time.monotonic() - began
        return result

    # --- Days ---------------------------------------------------------------------------
    def _days(self, job: str, start: date, end: date, work) -> JobResult:
        result, began = JobResult(job), time.monotonic()
        days = store.trading_days(start, min(end, self.today))
        self.progress.start(job, len(days))
        consecutive = 0
        for day in days:
            key = day.isoformat()
            if not self.force and store.is_done(self.conn, job, key):
                result.skipped += 1
                self.progress.advance(job, key)
                continue
            try:
                rows, detail = work(day)
            except SourceBlocked as exc:
                store.log(self.conn, job, key, "failed", error=str(exc))
                self.conn.commit()
                raise SyncAborted(str(exc)) from exc
            except FetchFailed as exc:
                consecutive += 1
                store.log(self.conn, job, key, "failed", error=str(exc))
                result.fail(key, str(exc))
                if consecutive >= _MAX_CONSECUTIVE_FAILURES:
                    self.conn.commit()
                    raise SyncAborted(f"{consecutive} downloads in a row failed; last: {exc}") from exc
            except (zipfile.BadZipFile, ValueError, KeyError, IndexError) as exc:
                consecutive = 0
                store.log(self.conn, job, key, "failed", error=f"unreadable: {type(exc).__name__}: {exc}")
                result.fail(key, f"unreadable file ({exc})")
            else:
                consecutive = 0
                if rows is None:
                    store.log(self.conn, job, key, "missing", detail=detail or "no file (holiday)")
                    result.missing += 1
                else:
                    store.log(self.conn, job, key, "ok", rows=rows, detail=detail)
                    result.done += 1
                    result.rows += rows
            self.conn.commit()
            self.progress.advance(job, key)
        self.progress.finish(job)
        result.elapsed = time.monotonic() - began
        return result

    def sync_prices(self, start: date, end: date) -> JobResult:
        return self._days("prices", start, end, self._prices_day)

    def _prices_day(self, day: date) -> tuple[int | None, str]:
        rows, kind = None, None
        for kind, url in nse.price_sources(day):
            data = self.client.get(url, nse.cache_name(url, day))
            if data is not None:
                rows = nse.parse_prices(kind, data, day)
                break
        if rows is None:
            return None, "no bhavcopy (holiday)"
        if kind == "pr":
            mapping = store.symbol_map(self.conn, day.isoformat())
            for r in rows:
                r.isin = mapping.get(r.symbol)
        else:
            store.upsert_symbol_history(self.conn, ((r.symbol, r.isin, r.day) for r in rows
                                                    if r.isin and r.series == "EQ"))
        priced = [r for r in rows if r.isin and r.isin.startswith("IN")]
        source = {"cm": "NSE bhavcopy", "udiff": "NSE bhavcopy (UDiFF)", "pr": "NSE PR file"}[kind]
        store.upsert_prices(self.conn, ((r.isin, day.isoformat(), r.open, r.high, r.low, r.close, r.volume,
                                         r.series, source) for r in priced))
        delivered = 0
        mto_url = nse.mto_url(day)
        try:
            mto = self.client.get(mto_url, nse.cache_name(mto_url, day))
        except FetchFailed:
            mto = None  # prices without deliveries beat no prices; a re-run with --force fills them
        if mto is not None:
            deliveries = nse.parse_mto(mto)
            pairs = [(r.isin, deliveries[(r.symbol, r.series)]) for r in priced if (r.symbol, r.series) in deliveries]
            store.set_deliveries(self.conn, day.isoformat(), pairs)
            delivered = len(pairs)
        unmapped = len(rows) - len(priced)
        return len(priced), f"{kind}: {len(priced)} priced, {delivered} with deliveries, {unmapped} unmapped"

    def _pr(self, day: date) -> bytes | None:
        url = nse.pr_url(day)
        return self.client.get(url, nse.cache_name(url, day))

    def sync_actions(self, start: date, end: date) -> JobResult:
        return self._days("actions", start, end, self._actions_day)

    def _actions_day(self, day: date) -> tuple[int | None, str]:
        data = self._pr(day)
        if data is None:
            return None, "no PR file (holiday)"
        key = day.isoformat()
        mapping = store.symbol_map(self.conn, key)
        face = {r[0]: r[1] for r in self.conn.execute("SELECT isin, face_value FROM securities")}
        stored, unmapped = 0, Counter()
        for row in nse.parse_pr_actions(data):
            isin = mapping.get(row.symbol)
            if isin is None:
                unmapped[row.symbol] += 1
                continue
            if row.ex_date is None:
                continue
            for action in parse_purpose(row.purpose, face.get(isin)):
                store.upsert_action(self.conn, isin=isin, ex_date=row.ex_date, type=action.type,
                                    details=row.purpose, ratio_num=action.ratio_num, ratio_den=action.ratio_den,
                                    amount=action.amount, factor=action.factor, record_date=row.record_date,
                                    symbol=row.symbol, series=row.series, seen=key)
                stored += 1
        changes = 0
        for row in nse.parse_pr_shares(data):
            isin = mapping.get(row.symbol)
            if isin and row.issue_size:
                changes += store.record_shares(self.conn, isin, key, row.issue_size, row.face_value, "NSE PR (mcap)")
        return stored + changes, f"{stored} actions, {changes} share-count changes, {sum(unmapped.values())} unmapped"

    def sync_announcements(self, start: date, end: date, isins: set[str] | None, label: str) -> JobResult:
        return self._days(f"announcements:{label}", start, end, lambda day: self._announcements_day(day, isins))

    def _announcements_day(self, day: date, isins: set[str] | None) -> tuple[int | None, str]:
        data = self._pr(day)
        if data is None:
            return None, "no PR file (holiday)"
        key = day.isoformat()
        mapping = store.symbol_map(self.conn, key)
        docs = []
        for a in nse.parse_pr_announcements(data):
            isin = mapping.get(a.symbol)
            if isin is None or (isins is not None and isin not in isins):
                continue
            kind = classify_announcement(a.category, a.text)
            if kind is None:
                continue
            title = f"{a.category}: {a.text}" if a.category else a.text
            docs.append((isin, key, kind, title[:400], NSE_ANNOUNCEMENTS.format(quote(a.symbol)), "NSE announcements"))
        for m in nse.parse_pr_board_meetings(data):
            isin = mapping.get(m.symbol)
            if isin is None or (isins is not None and isin not in isins):
                continue
            when = f" on {m.meeting_date}" if m.meeting_date else ""
            docs.append((isin, key, "board_meeting", f"Board meeting{when}: {m.purpose}"[:400],
                         NSE_ANNOUNCEMENTS.format(quote(m.symbol)), "NSE board meetings"))
        return store.upsert_documents(self.conn, docs), f"{len(docs)} kept"

    # --- Filings saved by hand -----------------------------------------------------------
    def import_files(self, paths: Iterable[str | Path], *, kinds: set[str] | None = None,
                     isins: set[str] | None = None, from_year: int | None = None,
                     filed_at: str | None = None) -> JobResult:
        """Import results and shareholding XBRL files (or folders of them). A filing
        that names its company only by symbol (the old results format has no ISIN)
        waits for a second pass, so a filing that does carry the ISIN can introduce
        the company first, whatever order the files sort in."""
        result, began = JobResult("import"), time.monotonic()
        files = sorted({f for p in paths for f in _xml_files(Path(p))})
        self.progress.start("import", len(files))
        waiting = []
        for path in files:
            if self._import_one(path, result, kinds, isins, from_year, filed_at, defer=True) == "deferred":
                waiting.append(path)
            else:
                self.progress.advance("import", path.name)
        for path in waiting:
            self._import_one(path, result, kinds, isins, from_year, filed_at, defer=False)
            self.progress.advance("import", path.name)
        self.progress.finish("import")
        result.elapsed = time.monotonic() - began
        return result

    def _import_one(self, path: Path, result: JobResult, kinds, isins, from_year, filed_at, *, defer: bool) -> str:
        try:
            data = path.read_bytes()
        except OSError as exc:
            result.fail(path.name, str(exc))
            return "failed"
        key = f"{path.stem}:{hashlib.sha1(data).hexdigest()[:12]}"
        if not self.force and store.is_done(self.conn, "import", key):
            result.skipped += 1
            return "skipped"
        try:
            filing = parse_filing(data, path.name, filed_at)
            kind = "results" if isinstance(filing, ResultsFiling) else "shareholding"
            period_end = filing.period_end if kind == "results" else filing.quarter_end
            if (kinds and kind not in kinds) or (from_year and int(period_end[:4]) < from_year):
                result.skipped += 1
                return "skipped"
            isin = self._filing_isin(filing)
            if isins is not None and isin not in isins:
                result.skipped += 1
                return "skipped"
            rows = self._store_filing(filing, kind, isin, path.name, data)
        except UnresolvedCompany as exc:
            if defer:
                return "deferred"
            store.log(self.conn, "import", key, "failed", error=str(exc), detail=str(path))
            result.fail(path.name, str(exc))
            outcome = "failed"
        except FilingError as exc:
            store.log(self.conn, "import", key, "failed", error=str(exc), detail=str(path))
            result.fail(path.name, str(exc))
            outcome = "failed"
        else:
            store.log(self.conn, "import", key, "ok", rows=rows, detail=f"{kind} {isin} {period_end}")
            result.done += 1
            result.rows += rows
            outcome = "ok"
        self.conn.commit()
        return outcome

    def _filing_isin(self, filing: ResultsFiling | ShareholdingFiling) -> str:
        if filing.isin and filing.isin.startswith("IN") and len(filing.isin) == 12:
            return filing.isin
        for candidate in (filing.symbol, f"{filing.scrip_code}.BO" if filing.scrip_code else None):
            if candidate and (hit := store.resolve(candidate, self.conn)):
                return hit["isin"]
        raise UnresolvedCompany(f"the filing has no ISIN and its symbol {filing.symbol!r} is not in the "
                                "securities table; run `tradingagents india sync-securities` first")

    def _store_filing(self, filing, kind: str, isin: str, name: str, data: bytes) -> int:
        raw = self.client.store(f"xbrl/{kind}/{isin}/{name}", data)
        nse_named = filename_stamp(name) is not None
        source = "NSE XBRL filing" if nse_named else "XBRL filing"
        store.upsert_securities(self.conn, [{
            "isin": isin, "nse_symbol": filing.symbol if filing.symbol and filing.symbol != "NOTLISTED" else None,
            "bse_code": filing.scrip_code, "name": filing.name, "status": "filing-only"}])
        if kind == "results":
            store.upsert_filing(self.conn, filing_id=filing.filing_id, isin=isin, kind=kind, format=filing.format,
                                basis=filing.basis, period_end=filing.period_end, filed_at=filing.filed_at,
                                filed_at_basis=filing.filed_at_basis, symbol=filing.symbol,
                                scrip_code=filing.scrip_code, taxonomy=filing.taxonomy, url=filing.url,
                                raw_path=str(raw), source=source)
            rows = store.upsert_financials(self.conn, isin=isin, basis=filing.basis, filing_id=filing.filing_id,
                                           filed_at=filing.filed_at, source=source, rows=filing.rows)
            store.record_unknown_tags(self.conn, filing.unknown, filing.format, filing.filing_id)
            title = f"{filing.basis.title()} results, period ended {filing.period_end}"
            store.upsert_documents(self.conn, [(isin, filing.filed_at[:10], "results", title, filing.url, source)])
            return rows
        store.upsert_filing(self.conn, filing_id=filing.filing_id, isin=isin, kind=kind, format="shp", basis=None,
                            period_end=filing.quarter_end, filed_at=filing.filed_at,
                            filed_at_basis=filing.filed_at_basis, symbol=filing.symbol,
                            scrip_code=filing.scrip_code, taxonomy=filing.taxonomy, url=filing.url,
                            raw_path=str(raw), source=source)
        store.upsert_shareholding(self.conn, isin=isin, quarter_end=filing.quarter_end, filed_at=filing.filed_at,
                                  values=filing.values, filing_id=filing.filing_id, source=source)
        store.upsert_documents(self.conn, [(isin, filing.filed_at[:10], "shareholding",
                                            f"Shareholding pattern, {filing.quarter_end}", filing.url, source)])
        return 1

    # --- The nightly run ---------------------------------------------------------------
    def last_day(self, job: str) -> date | None:
        row = self.conn.execute("SELECT MAX(key) FROM ingest_log WHERE job=? AND status IN ('ok','missing')",
                                (job,)).fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None

    def sync_all(self, *, universe: str = "nifty500", inbox: Path | None = None,
                 first_run_days: int = 365) -> list[JobResult]:
        """Everything new since the last run: securities, then prices, actions and
        announcements from the day after each job's last day (a year back on a
        first run), then any filings waiting in the inbox."""
        results = [self.sync_securities()]
        fallback = self.today - timedelta(days=first_run_days)
        for job, run in (("prices", self.sync_prices), ("actions", self.sync_actions)):
            last = self.last_day(job)
            results.append(run(last + timedelta(days=1) if last else fallback, self.today))
        isins = self.universe(universe=universe)
        label = universe or "all"
        last = self.last_day(f"announcements:{label}")
        results.append(self.sync_announcements(last + timedelta(days=1) if last else fallback, self.today,
                                               isins, label))
        folder = inbox or inbox_dir()
        if folder.is_dir():
            results.append(self.import_files([folder]))
        return results


def _xml_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() == ".xml" else []
    if path.is_dir():
        return [p for p in path.rglob("*") if p.is_file() and p.suffix.lower() == ".xml"]
    return []
