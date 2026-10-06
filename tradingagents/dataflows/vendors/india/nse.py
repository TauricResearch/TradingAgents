"""NSE's public archive files: where each lives, and how to read it.

Only archives.nseindia.com is used. NSE's JSON APIs and nsearchives.nseindia.com,
which serves the XBRL filings, stall for any client that is not a browser, and the
rules this layer runs under forbid working around that (README, "India data").

    file                          dates            gives
    EQUITY_L.csv                  today            symbol, ISIN, name, series, listing date, face value
    ind_<index>list.csv           today            index constituents with NSE's industry
    cm<DD><MON><YYYY>bhav.csv.zip 2016 - Jul 2024  OHLC, volume, ISIN
    BhavCopy_NSE_CM_..._F_0000    2024 on          the same in the UDiFF layout
    MTO_<DDMMYYYY>.DAT            2010 on          deliverable quantity
    PR<DDMMYY>.zip                2010 on          pd: OHLC by symbol (no ISIN); bc: corporate
                                                   actions; an: announcements; bm: board
                                                   meetings; mcap (2020s): shares issued

Every parser takes the file's bytes and returns plain rows, so tests feed them
fixture slices and nothing here touches the network.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime

ARCHIVES = "https://archives.nseindia.com"
EQUITY_SERIES = frozenset({"EQ", "BE", "BZ", "SM", "ST"})  # equity, trade-for-trade, SME
INDEX_FILES = {"nifty50": "ind_nifty50list.csv", "nifty500": "ind_nifty500list.csv",
               "niftytotalmarket": "ind_niftytotalmarket_list.csv"}
# Bhavcopies with ISINs start in 2016; the old layout stops after 5 July 2024 and
# UDiFF begins with 2024 (both exist for the first half of that year).
CM_FIRST, CM_LAST = date(2016, 1, 1), date(2024, 7, 5)
UDIFF_FIRST = date(2024, 1, 1)


# --- Where files live -----------------------------------------------------------

def equity_list_url() -> str:
    return f"{ARCHIVES}/content/equities/EQUITY_L.csv"


def index_url(index: str) -> str:
    return f"{ARCHIVES}/content/indices/{INDEX_FILES[index]}"


def cm_bhav_url(day: date) -> str:
    mon = day.strftime("%b").upper()
    return f"{ARCHIVES}/content/historical/EQUITIES/{day.year}/{mon}/cm{day:%d}{mon}{day.year}bhav.csv.zip"


def udiff_bhav_url(day: date) -> str:
    return f"{ARCHIVES}/content/cm/BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"


def mto_url(day: date) -> str:
    return f"{ARCHIVES}/archives/equities/mto/MTO_{day:%d%m%Y}.DAT"


def pr_url(day: date) -> str:
    return f"{ARCHIVES}/archives/equities/bhavcopy/pr/PR{day:%d%m%y}.zip"


def cache_name(url: str, day: date | None = None) -> str:
    """Where a download is kept under the raw directory: by source and year for
    dated files, by fetch date for the lists NSE overwrites daily."""
    name = url.rsplit("/", 1)[-1]
    if day is None:
        stem, dot, ext = name.rpartition(".")
        return f"nse/lists/{stem}_{date.today():%Y%m%d}.{ext}"
    kind = ("bhav" if "bhav" in name.lower() else "mto" if name.startswith("MTO")
            else "pr" if name.startswith("PR") else "other")
    return f"nse/{kind}/{day.year}/{name}"


def price_sources(day: date) -> list[tuple[str, str]]:
    """(kind, url) to try for one day's prices, best first."""
    out = []
    if day >= UDIFF_FIRST:
        out.append(("udiff", udiff_bhav_url(day)))
    if CM_FIRST <= day <= CM_LAST:
        out.append(("cm", cm_bhav_url(day)))
    if day < CM_FIRST:
        out.append(("pr", pr_url(day)))
    return out


# --- Rows -------------------------------------------------------------------------

@dataclass
class Security:
    symbol: str
    isin: str
    name: str
    series: str
    listing_date: str | None
    face_value: float | None


@dataclass
class PriceRow:
    symbol: str
    series: str
    isin: str | None  # None in files keyed by symbol only
    day: str
    open: float | None
    high: float | None
    low: float | None
    close: float
    volume: int | None


@dataclass
class ActionRow:
    symbol: str
    series: str
    name: str
    record_date: str | None
    ex_date: str | None
    purpose: str


@dataclass
class SharesRow:
    symbol: str
    series: str
    face_value: float | None
    issue_size: int | None


@dataclass
class Announcement:
    symbol: str
    company: str
    category: str | None
    text: str


@dataclass
class BoardMeeting:
    symbol: str
    company: str
    meeting_date: str | None
    purpose: str


# --- Parsing helpers ----------------------------------------------------------------

def _num(value) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if text in ("", "-", "NA", "N.A."):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int(value) -> int | None:
    number = _num(value)
    return None if number is None else int(round(number))


_DATE_FORMATS = ("%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y", "%d %b %Y", "%d-%m-%Y", "%d%m%Y", "%d-%b-%y")


def parse_date(value) -> str | None:
    """An ISO date from any of the layouts NSE files use, or None."""
    text = str(value or "").strip()
    if not text or text == "-":
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text.title() if "%b" in fmt else text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _rows(data: bytes) -> list[dict]:
    """CSV rows keyed by upper-cased, stripped header names."""
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header:
        return []
    keys = [h.strip().upper() for h in header]
    return [{k: (v.strip() if isinstance(v, str) else v) for k, v in zip(keys, row, strict=False)}
            for row in reader if any(cell.strip() for cell in row)]


def _zip_member(data: bytes, prefix: str) -> bytes | None:
    """The member of a zip whose name starts with ``prefix`` (any case)."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            if name.lower().startswith(prefix.lower()):
                return archive.read(name)
    return None


def _only_member(data: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(archive.namelist()[0])


# --- Parsers ----------------------------------------------------------------------

def parse_equity_list(data: bytes) -> list[Security]:
    out = []
    for row in _rows(data):
        isin, symbol = row.get("ISIN NUMBER", ""), row.get("SYMBOL", "")
        if isin and symbol:
            out.append(Security(symbol=symbol, isin=isin, name=row.get("NAME OF COMPANY", ""),
                                series=row.get("SERIES", ""), listing_date=parse_date(row.get("DATE OF LISTING")),
                                face_value=_num(row.get("FACE VALUE"))))
    return out


def parse_index_list(data: bytes) -> list[dict]:
    """[{symbol, isin, name, industry}] for an index's constituents."""
    return [{"symbol": r.get("SYMBOL", ""), "isin": r.get("ISIN CODE", ""), "name": r.get("COMPANY NAME", ""),
             "industry": r.get("INDUSTRY") or None}
            for r in _rows(data) if r.get("ISIN CODE")]


def parse_cm_bhav(data: bytes) -> list[PriceRow]:
    out = []
    for r in _rows(_only_member(data)):
        close = _num(r.get("CLOSE"))
        if r.get("SERIES") in EQUITY_SERIES and close is not None:
            out.append(PriceRow(r["SYMBOL"], r["SERIES"], r.get("ISIN") or None, parse_date(r.get("TIMESTAMP")),
                                _num(r.get("OPEN")), _num(r.get("HIGH")), _num(r.get("LOW")), close,
                                _int(r.get("TOTTRDQTY"))))
    return out


def parse_udiff_bhav(data: bytes) -> list[PriceRow]:
    out = []
    for r in _rows(_only_member(data)):
        close = _num(r.get("CLSPRIC"))
        if r.get("SCTYSRS") in EQUITY_SERIES and close is not None:
            out.append(PriceRow(r["TCKRSYMB"], r["SCTYSRS"], r.get("ISIN") or None, parse_date(r.get("TRADDT")),
                                _num(r.get("OPNPRIC")), _num(r.get("HGHPRIC")), _num(r.get("LWPRIC")), close,
                                _int(r.get("TTLTRADGVOL"))))
    return out


def parse_pr_prices(data: bytes, day: date) -> list[PriceRow]:
    """Prices from a PR zip's pd file: keyed by symbol and series, no ISIN."""
    member = _zip_member(data, "pd")
    if member is None:
        return []
    out = []
    for r in _rows(member):
        close = _num(r.get("CLOSE_PRICE"))
        if r.get("SERIES") in EQUITY_SERIES and r.get("SYMBOL") and close is not None:
            out.append(PriceRow(r["SYMBOL"], r["SERIES"], None, day.isoformat(), _num(r.get("OPEN_PRICE")),
                                _num(r.get("HIGH_PRICE")), _num(r.get("LOW_PRICE")), close,
                                _int(r.get("NET_TRDQTY"))))
    return out


def parse_prices(kind: str, data: bytes, day: date) -> list[PriceRow]:
    return {"cm": parse_cm_bhav, "udiff": parse_udiff_bhav}[kind](data) if kind != "pr" \
        else parse_pr_prices(data, day)


def parse_mto(data: bytes) -> dict[tuple[str, str], int]:
    """{(symbol, series): deliverable quantity} from a security-wise delivery file."""
    out = {}
    for line in data.decode("latin-1").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 6 and parts[0] == "20" and parts[3] in EQUITY_SERIES:
            deliverable = _int(parts[5])
            if deliverable is not None:
                out[(parts[2], parts[3])] = deliverable
    return out


def parse_pr_actions(data: bytes) -> list[ActionRow]:
    member = _zip_member(data, "bc")
    if member is None:
        return []
    return [ActionRow(r.get("SYMBOL", ""), r.get("SERIES", ""), r.get("SECURITY", ""),
                      parse_date(r.get("RECORD_DT")), parse_date(r.get("EX_DT")), " ".join(r.get("PURPOSE", "").split()))
            for r in _rows(member) if r.get("SERIES") in EQUITY_SERIES and r.get("PURPOSE")]


def parse_pr_shares(data: bytes) -> list[SharesRow]:
    """Shares issued by symbol, from the mcap file of newer PR zips."""
    member = _zip_member(data, "mcap")
    if member is None:
        return []
    return [SharesRow(r.get("SYMBOL", ""), r.get("SERIES", ""), _num(r.get("FACE VALUE(RS.)")),
                      _int(r.get("ISSUE SIZE")))
            for r in _rows(member) if r.get("SERIES") in EQUITY_SERIES and r.get("SYMBOL")]


_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9&\-_.]*")


def _company_and_symbol(left: str) -> tuple[str, str] | None:
    words = left.split()
    if len(words) >= 2 and _SYMBOL.fullmatch(words[-1]):
        return " ".join(words[:-1]), words[-1]
    return None


def parse_pr_announcements(data: bytes) -> list[Announcement]:
    """The day's announcements from a PR zip's an file. Layouts vary by year:
    ``Company SYMBOL : Category SYMBOL : text``, ``Company SYMBOL : Category-XBRL
    text``, and (2015) the category spliced into the text, where only the text is
    kept. A line that does not start an entry continues the one before it."""
    member = _zip_member(data, "an")
    if member is None:
        return []
    out: list[Announcement] = []
    for line in member.decode("latin-1").splitlines()[1:]:
        if not line.strip():
            continue
        left, sep, right = line.partition(" : ")
        who = _company_and_symbol(left) if sep else None
        if who is None:
            if out:
                out[-1].text = f"{out[-1].text} {line.strip()}".strip()
            continue
        company, symbol = who
        category, text = None, right.strip()
        marker = f" {symbol} : "
        if marker in f" {right}":
            category, _, text = f" {right}".partition(marker)
            category = category.strip() or None
        elif "-XBRL " in right:
            category, _, text = right.partition("-XBRL ")
            category = category.strip() or None
        out.append(Announcement(symbol, company, category, text.strip()))
    return out


def parse_pr_board_meetings(data: bytes) -> list[BoardMeeting]:
    member = _zip_member(data, "bm")
    if member is None:
        return []
    out: list[BoardMeeting] = []
    for line in member.decode("latin-1").splitlines()[1:]:
        if not line.strip():
            continue
        left, sep, right = line.partition(" : ")
        who = _company_and_symbol(left) if sep else None
        if who is None:
            if out:
                out[-1].purpose = f"{out[-1].purpose} {line.strip()}".strip()
            continue
        # "24-OCT-2026 : Financial Results ...", or in 2015 "29-Jan-2015 :TResults..." and
        # "21-Jan-2015 ToResults..." with the separator missing or glued on.
        first = right.split()[0] if right.split() else ""
        meeting = parse_date(first) or parse_date(first[:11])
        purpose = right[len(first):] if parse_date(first) else right[11:] if meeting else right
        out.append(BoardMeeting(who[1], who[0], meeting, " ".join(purpose.lstrip(" :").split())))
    return out
