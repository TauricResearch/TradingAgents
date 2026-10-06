"""Exports: the stdlib XLSX writer read back with zipfile and an XML parser, the
Company workbook, table exports, CSV's BOM and formula guard, the row cap and
file names."""

from __future__ import annotations

import csv
import io
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime

import pytest

import tradingagents.dataflows.config as config_module
from tests import phase4_db as p4
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors.india import profile as india_profile, store
from tradingagents.screener import engine, export, peers, snapshot, userdb, xlsx

pytestmark = pytest.mark.unit
NS = {"m": xlsx.MAIN, "r": xlsx.REL}


# --- Reading an .xlsx back -------------------------------------------------------------------

class Book:
    """A workbook parsed back: sheet names, cells with their types and styles, panes."""

    def __init__(self, data: bytes):
        self.zip = zipfile.ZipFile(io.BytesIO(data))
        assert self.zip.testzip() is None
        book = ET.fromstring(self.zip.read("xl/workbook.xml"))
        self.names = [s.get("name") for s in book.find("m:sheets", NS)]
        rels = ET.fromstring(self.zip.read("xl/_rels/workbook.xml.rels"))
        targets = {r.get("Id"): r.get("Target") for r in rels}
        self.paths = {s.get("name"): "xl/" + targets[s.get(f"{{{xlsx.REL}}}id")] for s in book.find("m:sheets", NS)}
        strings = ET.fromstring(self.zip.read("xl/sharedStrings.xml"))
        self.strings = ["".join(t.text or "" for t in si.iter(f"{{{xlsx.MAIN}}}t")) for si in strings]
        styles = ET.fromstring(self.zip.read("xl/styles.xml"))
        self.fonts = [f.find("m:b", NS) is not None for f in styles.find("m:fonts", NS)]
        self.xfs = list(styles.find("m:cellXfs", NS))
        types = ET.fromstring(self.zip.read("[Content_Types].xml"))
        self.overrides = {o.get("PartName") for o in types}

    def sheet(self, name):
        return ET.fromstring(self.zip.read(self.paths[name]))

    def cells(self, name) -> dict[str, tuple[str, object, int]]:
        """ref -> (type, value, style index); type is 'n' for numbers, 's' for strings."""
        out = {}
        for c in self.sheet(name).iter(f"{{{xlsx.MAIN}}}c"):
            v = c.find("m:v", NS)
            if v is None:
                continue
            kind = c.get("t", "n")
            value = self.strings[int(v.text)] if kind == "s" else float(v.text) if kind == "n" else v.text
            out[c.get("r")] = (kind, value, int(c.get("s", 0)))
        return out

    def bold(self, style: int) -> bool:
        return self.fonts[int(self.xfs[style].get("fontId"))]

    def quoted(self, style: int) -> bool:
        return self.xfs[style].get("quotePrefix") == "1"

    def pane(self, name):
        return self.sheet(name).find("m:sheetViews/m:sheetView/m:pane", NS)


def test_the_writer_makes_a_valid_package_with_numbers_strings_and_panes():
    data = xlsx.workbook([
        xlsx.Sheet("Prices", [["Symbol", "Close", "Volume"], ["ACME", 101.5, 2000], ["=cmd|' /C calc'!A0", -3.25, None]],
                   freeze_cols=1),
        xlsx.Sheet("Notes", [["Item", "Value"], ["Made", "today"]]),
    ], title="Test")
    book = Book(data)
    assert book.names == ["Prices", "Notes"]
    assert {"/xl/workbook.xml", "/xl/styles.xml", "/xl/sharedStrings.xml", "/xl/worksheets/sheet1.xml",
            "/xl/worksheets/sheet2.xml"} <= book.overrides
    cells = book.cells("Prices")
    assert cells["B2"][:2] == ("n", 101.5) and cells["C2"][:2] == ("n", 2000.0) and cells["B3"][:2] == ("n", -3.25)
    assert cells["A2"][:2] == ("s", "ACME") and "C3" not in cells
    assert all(book.bold(cells[ref][2]) for ref in ("A1", "B1", "C1")) and not book.bold(cells["A2"][2])
    assert cells["A3"][1] == "=cmd|' /C calc'!A0" and book.quoted(cells["A3"][2])  # text, never a formula
    assert not book.quoted(cells["A2"][2])
    assert not list(book.sheet("Prices").iter(f"{{{xlsx.MAIN}}}f"))
    pane = book.pane("Prices")
    assert (pane.get("state"), pane.get("ySplit"), pane.get("xSplit"), pane.get("topLeftCell")) == ("frozen", "1", "1",
                                                                                                    "B2")
    assert book.pane("Notes").get("ySplit") == "1" and book.pane("Notes").get("xSplit") is None


def test_sheet_names_are_made_acceptable():
    assert xlsx.sheet_names(["Profit & Loss", "a/b:c", "x" * 40, "Notes", "notes"]) == [
        "Profit & Loss", "a b c", "x" * 31, "Notes", "notes (2)"]
    assert xlsx.column_letter(0) == "A" and xlsx.column_letter(25) == "Z" and xlsx.column_letter(26) == "AA"
    assert xlsx.clean_text("a\x00b\x1fc\td") == "abc\td"


# --- CSV ------------------------------------------------------------------------------------

def test_csv_has_a_bom_and_guards_formulas():
    data = export.csv_bytes(["Symbol", "Name", "Close"],
                            [["ACME.NS", "=HYPERLINK(\"http://x\")", 101.5], ["B.NS", "+1", -2.0],
                             ["C.NS", "-sell", None], ["D.NS", "@SUM(A1)", 3], ["E.NS", "\tTab", 0.1]])
    assert data.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    assert rows[0] == ["Symbol", "Name", "Close"]
    assert [r[1] for r in rows[1:]] == ["'=HYPERLINK(\"http://x\")", "'+1", "'-sell", "'@SUM(A1)", "'\tTab"]
    assert [r[2] for r in rows[1:]] == ["101.5", "-2.0", "", "3", "0.1"]  # numbers are not escaped
    assert "₹".encode() in export.csv_bytes(["Price (₹)"], [])


def test_file_names_are_safe():
    assert export.file_name("RELIANCE", "financials", "xlsx", date(2026, 10, 5)) == "RELIANCE_financials_2026-10-05.xlsx"
    assert export.file_name("screen_High ROCE / low P/E", "results", "csv", date(2026, 10, 5)) == \
        "screen_High_ROCE_low_P_E_results_2026-10-05.csv"
    assert export.file_name("../../etc/passwd", "x", "csv", date(2026, 10, 5)) == "etc_passwd_x_2026-10-05.csv"
    assert not export.file_name("..", "x", "csv").startswith(".")


# --- Tables ---------------------------------------------------------------------------------

@pytest.fixture
def india(tmp_path):
    path = tmp_path / "india.db"
    p4.build(path)
    conn = store.connect(path)
    snapshot.build_snapshot(conn)
    config_module._config["india_db_path"] = str(path)
    yield conn
    conn.close()


@pytest.fixture
def user(tmp_path):
    conn = userdb.connect(tmp_path / "user.db")
    yield conn
    conn.close()


def test_a_screen_exports_its_columns_and_sort_over_every_page(india, user):
    result = engine.run("Market Capitalization > 100", columns=["pe", "roce"], sort={"key": "current_price",
                                                                                         "dir": "asc"},
                        page_size=export.MAX_ROWS, max_page_size=export.MAX_ROWS, user_conn=user, india_conn=india)
    header, rows = export.table_rows(result)
    assert header == ["Symbol", "Name", "Current price (Rs)", "Market Capitalization (Rs Cr)",
                      "Price to earnings (x)", "Return on capital employed (%)"]
    assert len(rows) == result["total"] == 14  # every match, in one file
    prices = [r[2] for r in rows]
    assert prices == sorted(prices)
    book = Book(export.table_workbook("Screen", "Stocks", header, rows, export.table_notes(result, what="Screen",
                                                                                          query="x")))
    cells = book.cells("Stocks")
    assert cells["C2"][0] == "n" and cells["D2"][0] == "n" and cells["A2"][0] == "s"
    assert book.names == ["Stocks", "Notes"] and book.pane("Stocks").get("ySplit") == "1"


def test_the_row_cap_cuts_and_says_so(india, user, monkeypatch):
    monkeypatch.setattr(export, "MAX_ROWS", 3)
    result = engine.run("Market Capitalization > 100", page_size=200, user_conn=user, india_conn=india)
    _, rows = export.table_rows(result)
    assert len(rows) == 3
    notes = dict(export.table_notes(result, what="Screen"))
    assert notes["Rows"] == 3 and "14 rows matched" in notes["Cut"]


# --- The Company workbook --------------------------------------------------------------------

@pytest.fixture
def company(india, monkeypatch):
    def no_yahoo(symbol):
        raise NoMarketDataError(symbol)
    monkeypatch.setattr(india_profile.yahoo, "fetch_company_data", no_yahoo)
    monkeypatch.setattr(india_profile, "_CACHE", {})
    return india_profile.build_company_profile("GROWCO.NS")


def test_the_company_workbook_has_every_section_as_numbers(company, india, user):
    found = peers.peers("GROWCO.NS", user_conn=user, india_conn=india)
    book = Book(export.company_workbook(company, found, created=datetime(2026, 10, 5, 21, 0)))
    assert book.names == ["Summary", "Quarters", "Profit & Loss", "Balance Sheet", "Cash Flow", "Ratios",
                          "Shareholding", "Peers", "Notes"]
    pl = book.cells("Profit & Loss")
    assert pl["A1"][1] == "Rs. Crores" and book.bold(pl["A1"][2])  # the unit, in the corner
    table = company["profitLoss"]
    sales = next(r for r in table["rows"] if r["key"] == "sales")
    row = 2 + table["rows"].index(sales)
    assert pl[f"A{row}"][1] == sales["label"]
    last = xlsx.column_letter(len(table["periods"]))
    assert pl[f"{last}{row}"] == ("n", sales["values"][-1], pl[f"{last}{row}"][2])  # the page's figure, a number
    assert book.pane("Profit & Loss").get("ySplit") == "1" and book.pane("Profit & Loss").get("xSplit") == "1"
    quarters = book.cells("Quarters")
    assert [quarters[f"{xlsx.column_letter(i + 1)}1"][1] for i in range(len(company["quarters"]["periods"]))] == [
        p["label"] for p in company["quarters"]["periods"]]
    sh = book.cells("Shareholding")
    assert sh["A2"][1] == "Promoters" and sh["F2"][:2] == ("n", 52.0)
    peer_cells = book.cells("Peers")
    assert peer_cells["A1"][1] == "Symbol" and len({k[1:] for k in peer_cells}) == 1 + 10 + 1  # header, 10, median
    summary = book.cells("Summary")
    labels = {v[1] for k, v in summary.items() if k.startswith("A")}
    assert {"Company", "Market Cap", "Current Price", "52-week high"} <= labels
    notes = {book.cells("Notes")[f"A{i}"][1]: book.cells("Notes").get(f"B{i}", (None, None))[1]
             for i in range(2, 40) if f"A{i}" in book.cells("Notes")}
    assert notes["Generated"] == "2026-10-05T21:00:00"
    assert notes["Basis"] == "Consolidated (NSE filings)"
    assert notes["Profit & Loss: periods"] == "Mar 2021 to Mar 2026 (6 years plus TTM)"
    assert "nearest in market capitalisation" in notes["Peers"]


def test_without_peers_the_sheet_says_why(company):
    book = Book(export.company_workbook(company, None, "Peers come from the live snapshot. Build it with: x"))
    assert book.cells("Peers")["A2"][1].startswith("Peers come from the live snapshot")
