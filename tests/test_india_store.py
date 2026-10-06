"""The India database: idempotent writes and point-in-time reads.

An as-of read must see a filing only from the moment it became public, and a
restated period must keep both vintages, the earlier one still served to a read
dated before the restatement. Prices and per-share figures are adjusted only
for actions in force by the read's date. No network.
"""

import re
import shutil
from datetime import date
from pathlib import Path

import pytest

from tradingagents.dataflows.vendors.india import store
from tradingagents.dataflows.vendors.india.sync import Syncer

pytestmark = pytest.mark.unit
FIXTURES = Path(__file__).parent / "fixtures" / "india"
CR = 1e7
ACME = "INE999Z01019"
Q4 = "INTEGRATED_FILING_INDAS_1000001_24042026105714_WEB.xml"
RESTATED = "INTEGRATED_FILING_INDAS_1000009_10052026101500_WEB.xml"  # filed 10 May 2026


class NoNetwork:
    """A client for imports only: stores raw files, never downloads."""

    def __init__(self, raw):
        self.raw, self.requests, self.downloaded = Path(raw), 0, 0

    def store(self, relative, data):
        path = self.raw / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path


@pytest.fixture
def conn(tmp_path):
    c = store.connect(tmp_path / "india.db")
    yield c
    c.close()


@pytest.fixture
def syncer(conn, tmp_path):
    return Syncer(conn, client=NoNetwork(tmp_path / "raw"), today=date(2026, 10, 5))


def restated_q4(folder: Path) -> Path:
    """The Q4 filing as revised on 10 May 2026: quarterly sales 100 crore higher."""
    text = (FIXTURES / Q4).read_text(encoding="utf-8")
    text, n = re.subn(r'(<in-capmkt:RevenueFromOperations contextRef="OneD"[^>]*>)125000000000<',
                      r"\g<1>126000000000<", text)
    assert n == 1
    path = folder / RESTATED
    path.write_text(text, encoding="utf-8")
    return path


def sales(rows, period_type="Q"):
    return [r["value"] for r in rows if r["field"] == "sales" and r["period_type"] == period_type]


# --- Writes -----------------------------------------------------------------------------

def test_importing_twice_stores_each_row_once(syncer, conn, tmp_path):
    shutil.copy(FIXTURES / Q4, tmp_path / Q4)
    first = syncer.import_files([tmp_path / Q4])
    count = conn.execute("SELECT COUNT(*) FROM financials").fetchone()[0]
    assert first.done == 1 and count > 50
    again = syncer.import_files([tmp_path / Q4])
    assert again.skipped == 1 and again.done == 0  # resumable: the log says it is done
    syncer.force = True
    forced = syncer.import_files([tmp_path / Q4])
    assert forced.done == 1
    assert conn.execute("SELECT COUNT(*) FROM financials").fetchone()[0] == count  # an upsert, not a duplicate


def test_the_raw_file_is_kept_for_reparsing(syncer, tmp_path):
    syncer.import_files([FIXTURES / Q4])
    assert (tmp_path / "raw" / "xbrl" / "results" / ACME / Q4).is_file()


def test_securities_upserts_keep_what_a_row_leaves_blank(conn):
    store.upsert_securities(conn, [{"isin": ACME, "nse_symbol": "ACME", "name": "Acme", "industry": "Capital Goods",
                                    "status": "listed"}])
    store.upsert_securities(conn, [{"isin": ACME, "bse_code": "999999", "status": "filing-only"}])
    row = dict(conn.execute("SELECT * FROM securities").fetchone())
    assert (row["nse_symbol"], row["industry"], row["bse_code"], row["status"]) == (
        "ACME", "Capital Goods", "999999", "listed")


def test_shares_outstanding_are_stored_only_when_they_change(conn):
    assert store.record_shares(conn, ACME, "2026-01-01", 100, 10.0, "t")
    assert not store.record_shares(conn, ACME, "2026-01-02", 100, 10.0, "t")
    assert store.record_shares(conn, ACME, "2026-02-01", 200, 5.0, "t")
    assert store.get_shares_outstanding(ACME, as_of="2026-01-31", conn=conn)["shares"] == 100
    assert store.get_shares_outstanding(ACME, conn=conn)["shares"] == 200


# --- Point in time --------------------------------------------------------------------

def test_an_as_of_read_before_the_filing_does_not_see_it(syncer, conn):
    syncer.import_files([FIXTURES / Q4])  # public 24 Apr 2026 at 22:57:14
    assert store.get_financials(ACME, as_of="2026-04-23", conn=conn) == []
    assert store.get_financials(ACME, as_of="2026-04-24T22:00:00", conn=conn) == []
    assert sales(store.get_financials(ACME, as_of="2026-04-24T22:57:14", conn=conn)) == [12500 * CR]
    assert sales(store.get_financials(ACME, as_of="2026-04-24", conn=conn)) == [12500 * CR]  # a date: its whole day
    assert sales(store.get_financials(ACME, conn=conn)) == [12500 * CR]  # live: the latest


def test_a_restatement_keeps_both_vintages(syncer, conn, tmp_path):
    syncer.import_files([FIXTURES / Q4, restated_q4(tmp_path)])
    stored = conn.execute("""SELECT value, filed_at FROM financials WHERE isin=? AND field='sales'
                             AND period_type='Q' ORDER BY filed_at""", (ACME,)).fetchall()
    assert [tuple(r) for r in stored] == [(12500 * CR, "2026-04-24T22:57:14"), (12600 * CR, "2026-05-10T22:15:00")]
    assert sales(store.get_financials(ACME, conn=conn)) == [12600 * CR]
    assert sales(store.get_financials(ACME, as_of="2026-05-09", conn=conn)) == [12500 * CR]
    assert sales(store.get_financials(ACME, as_of="2026-05-10", conn=conn)) == [12600 * CR]
    # A field the revision did not change still reads from the latest filing that has it.
    pbt = [r for r in store.get_financials(ACME, conn=conn) if r["field"] == "pbt" and r["period_type"] == "Q"]
    assert pbt[0]["value"] == 2300 * CR


def test_basis_and_period_filters(syncer, conn):
    syncer.import_files([FIXTURES])
    consolidated = store.get_financials(ACME, basis="consolidated", period_types=["A"], fields=["sales"], conn=conn)
    assert [(r["period_end"], r["value"]) for r in consolidated] == [("2026-03-31", 47000 * CR)]
    standalone = store.get_financials(ACME, basis="standalone", period_types=["Q"], fields=["sales"], conn=conn)
    assert [(r["period_end"], r["value"]) for r in standalone] == [("2024-12-31", 11000 * CR)]


def test_shareholding_as_of(syncer, conn):
    syncer.import_files([FIXTURES])
    assert [r["quarter_end"] for r in store.get_shareholding(ACME, conn=conn)] == ["2021-09-30", "2026-06-30"]
    assert [r["quarter_end"] for r in store.get_shareholding(ACME, as_of="2026-07-16", conn=conn)] == [
        "2021-09-30", "2026-06-30"]
    assert [r["quarter_end"] for r in store.get_shareholding(ACME, as_of="2026-07-15", conn=conn)] == ["2021-09-30"]
    assert store.get_shareholding(ACME, as_of="2021-10-20", conn=conn) == []


def test_documents_as_of(syncer, conn):
    syncer.import_files([FIXTURES])
    kinds = {d["kind"] for d in store.get_documents(ACME, as_of="2025-12-31", conn=conn)}
    assert kinds == {"results", "shareholding"}
    assert all(d["date"] <= "2025-12-31" for d in store.get_documents(ACME, as_of="2025-12-31", conn=conn))


def test_cutoff_reads_a_date_as_its_whole_day_and_refuses_nonsense():
    assert store.cutoff("2026-04-24") == "2026-04-24T23:59:59"
    assert store.cutoff("2026-04-24 10:00") == "2026-04-24T10:00:00"
    assert store.cutoff(date(2026, 4, 24)) == "2026-04-24T23:59:59"
    assert store.cutoff(None) is None
    with pytest.raises(ValueError):
        store.cutoff("2026-13-45")


# --- Adjustment for corporate actions ----------------------------------------------------

def prices(conn):
    days = ["2026-01-29", "2026-01-30", "2026-02-02", "2026-02-27", "2026-03-02", "2026-03-03"]
    closes = [1000.0, 1010.0, 505.0, 510.0, 102.0, 103.0]
    store.upsert_prices(conn, [(ACME, d, c, c, c, c, 1000, "EQ", "test") for d, c in zip(days, closes, strict=True)])
    store.upsert_action(conn, isin=ACME, ex_date="2026-02-02", type="bonus", details="BONUS 1:1", ratio_num=1,
                        ratio_den=1, factor=2.0, seen="2026-01-20")
    store.upsert_action(conn, isin=ACME, ex_date="2026-03-02", type="split", details="FVSPLT FRM RS 10 TO RS 2",
                        ratio_num=10, ratio_den=2, factor=5.0, seen="2026-02-15")
    store.upsert_action(conn, isin=ACME, ex_date="2026-02-27", type="dividend", details="DIV - RS 5 PER SH",
                        amount=5.0, seen="2026-02-10")


def test_prices_are_adjusted_for_splits_and_bonuses_not_dividends(conn):
    prices(conn)
    rows = store.get_prices(ACME, conn=conn)
    assert [r["close"] for r in rows] == [100.0, 101.0, 101.0, 102.0, 102.0, 103.0]
    assert [r["volume"] for r in rows] == [10000, 10000, 5000, 5000, 1000, 1000]
    raw = store.get_prices(ACME, adjusted=False, conn=conn)
    assert [r["close"] for r in raw][:2] == [1000.0, 1010.0]


def test_an_as_of_read_adjusts_only_for_actions_in_force_then(conn):
    prices(conn)
    rows = store.get_prices(ACME, as_of="2026-02-28", conn=conn)
    assert [r["date"] for r in rows][-1] == "2026-02-27"  # nothing after the read's date
    assert [r["close"] for r in rows] == [500.0, 505.0, 505.0, 510.0]  # the bonus, not the later split


def test_rights_are_adjusted_from_the_close_before_the_ex_date(conn):
    store.upsert_prices(conn, [(ACME, "2026-05-04", 100, 100, 100, 100.0, 1, "EQ", "t"),
                               (ACME, "2026-05-05", 96, 96, 96, 96.0, 1, "EQ", "t")])
    store.upsert_action(conn, isin=ACME, ex_date="2026-05-05", type="rights", details="RGHTS 1:4 @ RS 80/-",
                        ratio_num=1, ratio_den=4, amount=80.0, seen="2026-04-20")
    rows = store.get_prices(ACME, conn=conn)
    assert rows[0]["close"] == pytest.approx(96.0)


def test_eps_is_adjusted_only_for_actions_after_it_was_filed(conn):
    prices(conn)
    events = store.adjustment_events(ACME, conn=conn)
    assert store.per_share_factor("2026-01-15T20:00:00", events) == 10.0  # filed before the bonus and the split
    assert store.per_share_factor("2026-02-10T20:00:00", events) == 5.0  # restated for the bonus already
    assert store.per_share_factor("2026-04-24T20:00:00", events) == 1.0


def test_actions_are_known_from_the_day_nse_first_listed_them(conn):
    prices(conn)
    assert [a["type"] for a in store.get_corporate_actions(ACME, as_of="2026-02-12", conn=conn)] == [
        "bonus", "dividend"]


def test_a_symbol_maps_to_the_isin_it_had_on_the_day(conn):
    store.upsert_symbol_history(conn, [("OLDNAME", "INE000A01001", "2016-01-01"),
                                       ("OLDNAME", "INE000A01001", "2019-05-31"),
                                       ("OLDNAME", "INE111B01001", "2023-01-02"),
                                       ("OLDNAME", "INE111B01001", "2026-10-01")])
    assert store.symbol_map(conn, "2018-03-01")["OLDNAME"] == "INE000A01001"
    assert store.symbol_map(conn, "2015-06-01")["OLDNAME"] == "INE000A01001"  # nearest sighting
    assert store.symbol_map(conn, "2024-03-01")["OLDNAME"] == "INE111B01001"


def test_resolve_accepts_isins_nse_and_bse_symbols(syncer, conn):
    syncer.import_files([FIXTURES])
    for name in ("ACME", "acme.ns", "ACME.BO", "999999.BO", ACME):
        assert store.resolve(name, conn)["isin"] == ACME, name
    assert store.resolve("NOSUCH.NS", conn) is None


def test_status_counts_rows_and_unknown_tags(syncer, conn):
    syncer.import_files([FIXTURES])
    s = store.status(conn)
    assert s["counts"]["filings"] == 5 and s["companies_with_results"] == 2
    assert ("SomeNewlyIntroducedMetric", "indas", 1) in s["unknown_tags"]


def test_open_existing_does_not_create_a_database(tmp_path):
    assert store.open_existing(tmp_path / "absent.db") is None
    assert not (tmp_path / "absent.db").exists()
