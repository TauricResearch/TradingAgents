"""Exports: the Company page as an Excel workbook, and any table of stocks as CSV or XLSX.

The Company workbook is built from the same profile the page renders
(``build_company_profile``), so its figures are the page's: one sheet per
section (Summary, Quarters, Profit & Loss, Balance Sheet, Cash Flow, Ratios,
Shareholding, Peers) and a Notes sheet with the sources, the statement basis,
the periods each sheet covers and when the file was made. Figures are numbers,
not text, so formulas work on them; money is in the page's unit (Rs. Crores for
Indian companies), which each sheet's corner cell names.

A table (a screen's results, a watchlist, peers, an industry) exports exactly
the columns and sort the page shows, over the whole result rather than the page
on screen, up to ``MAX_ROWS`` rows; the Notes sheet (XLSX) says when it was cut.

CSV is UTF-8 with a byte-order mark, so Excel reads the rupee sign and names
in any script. A text cell beginning with ``= + - @`` (or a tab or carriage
return) gets a leading apostrophe, so a spreadsheet never runs it as a formula;
the XLSX writer marks the same cells ``quotePrefix`` (see ``xlsx``).
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime

from tradingagents.screener import xlsx
from tradingagents.screener.xlsx import FORMULA_LEAD, Cell, Sheet

MAX_ROWS = 5000
CSV_TYPE = "text/csv; charset=utf-8"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
STATEMENTS = (("Quarters", "quarters"), ("Profit & Loss", "profitLoss"), ("Balance Sheet", "balanceSheet"),
              ("Cash Flow", "cashFlows"), ("Ratios", "ratios"))


def guard(value):
    """A CSV cell that cannot turn into a formula: text starting with ``= + - @``
    (or a tab or carriage return) gets a leading apostrophe. Numbers pass as they are."""
    if isinstance(value, str) and value.startswith(FORMULA_LEAD):
        return "'" + value
    return value


def csv_bytes(header: list, rows: list[list]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow([guard(h) for h in header])
    for row in rows:
        writer.writerow(["" if v is None else guard(v) if isinstance(v, str) else _csv_value(v) for v in row])
    return ("﻿" + out.getvalue()).encode("utf-8")


def _csv_value(value):
    if isinstance(value, float):
        return repr(round(value, 6)) if value == value else ""
    return value


def file_name(stem: str, kind: str, ext: str, day: date | None = None) -> str:
    """``RELIANCE_financials_2026-10-05.xlsx``: letters, digits and ``._-`` only."""
    text = f"{stem}_{kind}_{(day or date.today()).isoformat()}"
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in text)
    while "__" in safe:
        safe = safe.replace("__", "_")
    return f"{safe.strip('._')[:120] or 'export'}.{ext}"


# --- Tables -------------------------------------------------------------------------------

def column_label(column: dict) -> str:
    unit = column.get("unit") or ""
    return f"{column['name']} ({unit})" if unit and unit not in ("score", "count") else column["name"]


WATCHLIST_COLUMNS = (("Note", lambda r: r["item"]["note"] or None),)
HOLDING_COLUMNS = (
    ("Quantity", lambda r: r["item"]["quantity"]), ("Average price (Rs)", lambda r: r["item"]["avgPrice"]),
    ("Invested (Rs)", lambda r: (r.get("position") or {}).get("invested")),
    ("Current value (Rs)", lambda r: (r.get("position") or {}).get("current")),
    ("P&L (Rs)", lambda r: (r.get("position") or {}).get("pnl")),
    ("P&L (%)", lambda r: (r.get("position") or {}).get("pnlPct")),
)


def table_rows(result: dict, extras=()) -> tuple[list[str], list[list]]:
    """The header and rows of a table of stocks (``engine.run``'s layout): the
    symbol, then the columns shown, then ``extras`` (label, function of the row)."""
    columns = result["columns"]
    header = ["Symbol", *(column_label(c) for c in columns), *(label for label, _ in extras)]
    rows = []
    for r in result["rows"][:MAX_ROWS]:
        values = r.get("values") or {}
        rows.append([r.get("symbol"), *(values.get(c["id"]) for c in columns), *(fn(r) for _, fn in extras)])
    return header, rows


def table_workbook(title: str, sheet: str, header: list, rows: list[list], notes: list[tuple[str, object]],
                   created: datetime | None = None) -> bytes:
    created = created or datetime.now()
    data = xlsx.auto_widths(Sheet(sheet, [header, *rows], header_rows=1, freeze_cols=2 if len(header) > 2 else 0))
    data.widths[0] = max(data.widths.get(0, 8), 14)
    info = Sheet("Notes", [["Item", "Value"], *[[k, v] for k, v in notes],
                           ["Generated", created.isoformat(timespec="seconds")]], widths={0: 24, 1: 90})
    return xlsx.workbook([data, info], title=title, created=created)


def table_notes(result: dict, *, what: str, query: str | None = None) -> list[tuple[str, object]]:
    snap = result.get("snapshot") or {}
    total = result.get("total", len(result.get("rows", [])))
    notes = [("Table", what)]
    if query:
        notes.append(("Query", query))
    if snap:
        notes.append(("Snapshot", "live" if snap.get("as_of") == "live" else f"as of {snap.get('as_of')}"))
        notes.append(("Data to", snap.get("data_date")))
    sort = result.get("sort")
    if sort:
        notes.append(("Sorted by", f"{sort['key']} ({'ascending' if sort['dir'] == 'asc' else 'descending'})"))
    notes.append(("Rows", min(total, MAX_ROWS)))
    if total > MAX_ROWS:
        notes.append(("Cut", f"{total:,} rows matched; the export holds the first {MAX_ROWS:,}."))
    notes.append(("Units", "Rs Cr: rupees in crores; %: percent; % pts: percentage points; x: multiple"))
    notes.append(("Source", "The India database's metrics snapshot (NSE archives and imported filings)"))
    return notes


# --- The Company workbook ----------------------------------------------------------------

def _statement_sheet(name: str, table: dict, unit_label: str) -> Sheet:
    periods = table.get("periods") or []
    header = [unit_label, *(("TTM" if p.get("ttm") else p["label"]) for p in periods)]
    rows = [[r["label"], *r["values"]] for r in table.get("rows") or []]
    if not periods:
        rows = [[f"No figures for this section ({table.get('source') or 'no source'})."]]
    return xlsx.auto_widths(Sheet(name, [header, *rows], header_rows=1, freeze_cols=1), maximum=48)


def _coverage(table: dict, noun: str) -> str:
    periods = [p for p in table.get("periods") or [] if not p.get("ttm")]
    if not periods:
        return "none"
    ttm = " plus TTM" if any(p.get("ttm") for p in table.get("periods") or []) else ""
    span = periods[0]["label"] if len(periods) == 1 else f"{periods[0]['label']} to {periods[-1]['label']}"
    return f"{span} ({len(periods)} {noun}{'s' * (len(periods) != 1)}{ttm})"


def _summary_sheet(profile: dict) -> Sheet:
    rows: list[list] = [["Item", "Value", "Unit"],
                        ["Company", profile.get("name"), None], ["Symbol", profile.get("symbol"), None]]
    for label, key in (("Exchange", "exchange"), ("Sector", "sector"), ("Industry", "industry")):
        if profile.get(key):
            rows.append([label, profile[key], None])
    price = profile.get("price") or {}
    if price.get("date"):
        rows.append(["Last close date", price["date"], None])
    currency = profile.get("currency") or ""
    money = "Rs" if currency == "INR" else currency
    for r in profile.get("keyRatios") or []:
        kind, value = r.get("kind"), r.get("value")
        if kind == "range":
            high, low = (value or [None, None])[:2]
            rows += [["52-week high", high, money], ["52-week low", low, money]]
            continue
        unit = {"cap": f"{money} {(r.get('unit') or {}).get('short', '')}".strip(), "price": money,
                "pct": "%"}.get(kind, "x" if r.get("key") == "pe" else "")
        rows.append([r["label"], value, unit or None])
    metrics = profile.get("metrics")
    if metrics:
        rows += [[None], [Cell("All metrics (the screener's figures)", bold=True), Cell("Value", bold=True),
                          Cell("Unit", bold=True)]]
        for group in metrics["groups"]:
            for it in group["items"]:
                if it["value"] is not None:
                    rows.append([it["name"], it["value"], it["unit"] or None])
    return xlsx.auto_widths(Sheet("Summary", rows, header_rows=1, freeze_cols=1), maximum=48)


def _shareholding_sheet(sh: dict | None) -> Sheet:
    if not sh or not sh.get("periods"):
        return Sheet("Shareholding", [["Shareholding"], ["No shareholding pattern in the India database."]])
    header = ["% of shares", *(p["label"] for p in sh["periods"])]
    rows = [[r["label"], *r["values"]] for r in sh["rows"]]
    return xlsx.auto_widths(Sheet("Shareholding", [header, *rows], header_rows=1, freeze_cols=1), maximum=40)


def _peers_sheet(peers: dict | None, note: str | None) -> Sheet:
    if not peers or not peers.get("rows"):
        return Sheet("Peers", [["Peers"], [note or "No peers: the live metrics snapshot has none for this company."]])
    header, rows = table_rows(peers)
    median = ["Median", *(peers.get("median", {}).get(c["id"]) if c["kind"] == "number" else None
                          for c in peers["columns"])]
    sheet = Sheet("Peers", [header, *rows, [Cell(v, bold=True) for v in median]], header_rows=1, freeze_cols=2)
    return xlsx.auto_widths(sheet, maximum=40)


def company_workbook(profile: dict, peers: dict | None = None, peers_note: str | None = None,
                     created: datetime | None = None) -> bytes:
    """The Company page as an ``.xlsx``: its sections as sheets, then the notes."""
    created = created or datetime.now()
    unit = profile.get("unit") or {}
    unit_label = unit.get("label") or "Figures"
    sheets = [_summary_sheet(profile)]
    for name, key in STATEMENTS:
        sheets.append(_statement_sheet(name, profile.get(key) or {}, unit_label))
    sheets.append(_shareholding_sheet(profile.get("shareholding")))
    sheets.append(_peers_sheet(peers, peers_note))
    basis = (profile.get("basis") or {}).get("current")
    filed = any(str((profile.get(key) or {}).get("source") or "").startswith("NSE filings") for _, key in STATEMENTS)
    basis = basis if filed else None  # with no filings imported, the statements are Yahoo's
    source = profile.get("source") or {}
    notes: list[list] = [
        ["Item", "Value"],
        ["Company", f"{profile.get('name')} ({profile.get('symbol')})"],
        ["Generated", created.isoformat(timespec="seconds")],
        ["Source", source.get("name")],
        ["Data fetched", source.get("fetched")],
        ["Basis", f"{basis.title()} (NSE filings)" if basis else "Consolidated (Yahoo Finance reports consolidated "
                                                                    "figures only)"],
        ["Money unit", f"{unit_label}; per-share figures in rupees; ratios in % or times as labelled"],
    ]
    for name, key in STATEMENTS:
        table = profile.get(key) or {}
        noun = "quarter" if key == "quarters" else "year"
        notes.append([f"{name}: periods", _coverage(table, noun)])
        notes.append([f"{name}: source", table.get("source") or "—"])
        if table.get("note"):
            notes.append([f"{name}: note", table["note"]])
    sh = profile.get("shareholding") or {}
    if sh.get("periods"):
        notes.append(["Shareholding: periods", f"{sh['periods'][0]['label']} to {sh['periods'][-1]['label']}"])
        notes.append(["Shareholding: source", sh.get("source")])
    snap = (peers or {}).get("snapshot") or {}
    notes.append(["Peers", f"{peers.get('industry')}: the {len(peers['rows'])} companies nearest in market "
                           f"capitalisation, from the live metrics snapshot (data to {snap.get('data_date')})"
                  if peers and peers.get("rows") else (peers_note or "none")])
    if profile.get("metrics"):
        notes.append(["All metrics", f"The screener's figures, prices to {profile['metrics']['day']}"])
    notes.append(["Note", "Figures as the Company page shows them when the file was made: live, present-day "
                          "data, not cut at any analysis date. Not investment advice."])
    sheets.append(Sheet("Notes", notes, widths={0: 26, 1: 110}))
    return xlsx.workbook(sheets, title=f"{profile.get('name')} financials", created=created)
