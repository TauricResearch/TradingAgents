"""Sync jobs against a fake archive, the polite client, and the CLI.

The fake archive serves the real fixture slices at their real URLs and 404s
everything else, as the archive does on a holiday. The client's throttle,
retries and 403/429 handling run against a fake session and a fake clock.
"""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from typer.testing import CliRunner

import tradingagents.dataflows.config as config_module
from cli.main import app
from tradingagents.dataflows.vendors.india import nse, store, sync
from tradingagents.dataflows.vendors.india.fetch import ArchiveClient, FetchFailed, SourceBlocked

pytestmark = pytest.mark.unit
FIXTURES = Path(__file__).parent / "fixtures" / "india"
OCT1, JUL5 = date(2026, 10, 1), date(2024, 7, 5)


def archive() -> dict[str, bytes]:
    f = lambda name: (FIXTURES / name).read_bytes()  # noqa: E731
    return {
        nse.equity_list_url(): f("EQUITY_L.csv"),
        **{nse.index_url(i): f("ind_nifty50list.csv") for i in nse.INDEX_FILES},
        nse.udiff_bhav_url(OCT1): f("BhavCopy_NSE_CM_0_0_0_20261001_F_0000.csv.zip"),
        nse.mto_url(OCT1): f("MTO_01102026.DAT"),
        nse.cm_bhav_url(JUL5): f("cm05JUL2024bhav.csv.zip"),
        nse.pr_url(OCT1): f("PR011026.zip"),
        nse.pr_url(date(2015, 1, 2)): f("PR020115.zip"),
    }


class FakeArchive(ArchiveClient):
    def __init__(self, raw, files=None, fail=None):
        super().__init__(raw, interval=0, sleep=lambda s: None)
        self.files = archive() if files is None else files
        self.fail = fail
        self.asked: list[str] = []

    def _download(self, url):
        self.asked.append(url)
        self.requests += 1
        if self.fail:
            raise self.fail
        return self.files.get(url)


@pytest.fixture
def conn(tmp_path):
    c = store.connect(tmp_path / "india.db")
    yield c
    c.close()


@pytest.fixture
def make(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "MIN_LISTED", 1)

    def build(**kw):
        return sync.Syncer(conn, client=FakeArchive(tmp_path / "raw", **kw), today=date(2026, 10, 5))
    return build


def test_securities_come_from_the_equity_list_with_industries(make, conn):
    result = make().sync_securities()
    assert result.done == 1
    row = dict(conn.execute("SELECT * FROM securities WHERE nse_symbol='RELIANCE'").fetchone())
    assert row["isin"] == "INE002A01018" and row["status"] == "listed" and row["face_value"] == 10.0
    assert row["industry"] == "Oil Gas & Consumable Fuels"


def test_a_short_equity_list_is_refused_rather_than_unlisting_the_market(make, monkeypatch):
    monkeypatch.setattr(sync, "MIN_LISTED", 1000)
    with pytest.raises(sync.SyncAborted, match="refusing"):
        make().sync_securities()


def test_prices_with_deliveries_and_holidays(make, conn):
    s = make()
    s.sync_securities()
    result = s.sync_prices(date(2026, 9, 28), date(2026, 10, 2))
    assert (result.done, result.missing, result.failed) == (1, 4, 0)
    row = dict(conn.execute("SELECT * FROM prices_daily WHERE isin='INE002A01018'").fetchone())
    assert (row["date"], row["close"], row["volume"], row["deliverable_qty"]) == (
        "2026-10-01", 1167.7, 16771221, 10270423)
    assert row["source"] == "NSE bhavcopy (UDiFF)"
    statuses = dict(conn.execute("SELECT key, status FROM ingest_log WHERE job='prices'").fetchall())
    assert statuses["2026-09-28"] == "missing" and statuses["2026-10-01"] == "ok"


def test_a_sync_resumes_and_force_redoes(make):
    s = make()
    s.sync_prices(date(2026, 9, 30), date(2026, 10, 1))
    again = s.sync_prices(date(2026, 9, 30), date(2026, 10, 1))
    assert again.skipped == 2 and again.done == 0 and s.client.asked.count(nse.udiff_bhav_url(OCT1)) == 1
    s.force = True
    forced = s.sync_prices(date(2026, 9, 30), date(2026, 10, 1))
    assert forced.done == 1  # read again from the raw cache: no second download
    assert s.client.asked.count(nse.udiff_bhav_url(OCT1)) == 1


def test_old_bhavcopies_teach_which_isin_a_symbol_meant(make, conn):
    make().sync_prices(JUL5, JUL5)
    assert store.symbol_map(conn, "2024-07-05")["TCS"] == "INE467B01029"


def test_pre_2016_prices_come_from_the_pr_file_by_symbol(make, conn):
    s = make()
    s.sync_securities()
    result = s.sync_prices(date(2015, 1, 2), date(2015, 1, 2))
    assert result.done == 1
    sources = {r[0] for r in conn.execute("SELECT source FROM prices_daily WHERE date='2015-01-02'")}
    assert sources == {"NSE PR file"}


def test_corporate_actions_and_shares_from_the_pr_file(make, conn):
    s = make()
    s.sync_securities()
    store.upsert_securities(conn, [{"isin": "INE000X01010", "nse_symbol": "MOLDTKPAC", "face_value": 5.0}])
    result = s.sync_actions(OCT1, OCT1)
    assert result.done == 1
    bonus = dict(conn.execute("SELECT * FROM corporate_actions WHERE isin='INE000X01010'").fetchone())
    assert (bonus["type"], bonus["factor"], bonus["ex_date"], bonus["first_seen"]) == ("bonus", 2.0, "2026-10-09",
                                                                                          "2026-10-01")
    shares = store.get_shares_outstanding("INE144J01027", conn=conn)  # 20MICRONS
    assert shares["shares"] == 35286502


def test_announcements_for_a_universe_only(make, conn):
    s = make()
    store.upsert_securities(conn, [{"isin": "INE000Y01010", "nse_symbol": "MAHICKRA"},
                                   {"isin": "INE000Y01020", "nse_symbol": "MODIRUBBER"}])
    s.sync_announcements(OCT1, OCT1, {"INE000Y01010"}, "test")
    docs = store.get_documents("INE000Y01010", conn=conn)
    assert docs and docs[0]["kind"] == "announcement" and "symbol=MAHICKRA" in docs[0]["url"]
    assert store.get_documents("INE000Y01020", conn=conn) == []


@pytest.mark.parametrize("category, text, kind", [
    ("Credit Rating", "x", "credit_rating"),
    ("Analysts/Institutional Investor Meet/Con. Call Updates", "x", "concall"),
    (None, "Transcript of the earnings call held on", "concall"),
    ("Investor Presentation", "x", "investor_presentation"),
    ("Annual Report", "x", "annual_report"),
    ("Outcome of Board Meeting", "x", "board_meeting"),
    ("Trading Window", "x", None),
    ("Updates", "x", "announcement"),
])
def test_announcements_are_classified(category, text, kind):
    assert sync.classify_announcement(category, text) == kind


def test_a_refusing_host_stops_the_run(make, conn):
    s = make(fail=SourceBlocked("archives.nseindia.com refuses this client"))
    with pytest.raises(sync.SyncAborted, match="refuses"):
        s.sync_prices(OCT1, OCT1)
    assert conn.execute("SELECT status FROM ingest_log WHERE job='prices'").fetchone()[0] == "failed"


def test_one_failed_day_is_logged_and_the_run_goes_on_until_failures_pile_up(make):
    s = make(fail=FetchFailed("timeout"))
    with pytest.raises(sync.SyncAborted, match="in a row"):
        s.sync_prices(date(2026, 9, 1), date(2026, 9, 30))
    s = make(fail=FetchFailed("timeout"))
    result = s.sync_prices(date(2026, 9, 28), date(2026, 9, 29))
    assert result.failed == 2 and len(result.errors) == 2


def test_import_continues_past_a_bad_file_and_logs_it(make, conn, tmp_path):
    folder = tmp_path / "inbox"
    folder.mkdir()
    for f in FIXTURES.glob("*.xml"):
        (folder / f.name).write_bytes(f.read_bytes())
    (folder / "broken.xml").write_text("<not xbrl", encoding="utf-8")
    result = make().import_files([folder])
    assert result.done == 5 and result.failed == 1
    assert "broken.xml" in result.errors[0]


def test_old_format_filings_wait_for_their_company_whatever_the_order(make, conn):
    """INDAS_* sorts before INTEGRATED_* and names its company by symbol only."""
    result = make().import_files([FIXTURES])
    assert result.failed == 0
    assert {r[0] for r in conn.execute("SELECT basis FROM filings WHERE isin='INE999Z01019' AND kind='results'")} == {
        "standalone", "consolidated"}


def test_selectors_filter_imports(make, conn):
    s = make()
    s.import_files([FIXTURES])
    s.force = True
    picked = s.import_files([FIXTURES], kinds={"shareholding"}, isins={"INE999Z01019"}, from_year=2026)
    assert picked.done == 1 and picked.skipped == 4


def test_the_nightly_run_starts_after_each_jobs_last_day(make, conn, tmp_path):
    s = make()
    s.sync_prices(date(2026, 9, 28), date(2026, 10, 1))
    assert s.last_day("prices") == OCT1
    results = s.sync_all(universe="nifty50", inbox=tmp_path / "absent")
    by_job = {r.job: r for r in results}
    assert by_job["prices"].done + by_job["prices"].missing + by_job["prices"].failed == 2  # 2 and 5 October


# --- The client -------------------------------------------------------------------------

class Session:
    def __init__(self, script):
        self.script, self.headers, self.calls = list(script), {}, []

    def get(self, url, timeout):
        self.calls.append(url)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        status, body, headers = item if len(item) == 3 else (*item, {})
        return SimpleNamespace(status_code=status, content=body, headers=headers)


def client(tmp_path, script, **kw):
    clock = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        clock[0] += s
    c = ArchiveClient(tmp_path, interval=1.0, session=Session(script), sleep=sleep, clock=lambda: clock[0], **kw)
    return c, slept


def test_requests_are_throttled_per_host_and_identify_the_caller(tmp_path):
    c, slept = client(tmp_path, [(200, b"a"), (200, b"b")])
    c.get("https://archives.nseindia.com/a.csv", "a.csv")
    c.get("https://archives.nseindia.com/b.csv", "b.csv")
    assert slept == [1.0]
    assert c.session.headers["User-Agent"].startswith("TradingAgents/")


def test_a_cached_file_is_never_fetched_again(tmp_path):
    c, _ = client(tmp_path, [(200, b"data")])
    assert c.get("https://archives.nseindia.com/a.csv", "nse/a.csv") == b"data"
    assert c.get("https://archives.nseindia.com/a.csv", "nse/a.csv") == b"data"
    assert len(c.session.calls) == 1 and (tmp_path / "nse" / "a.csv").read_bytes() == b"data"


def test_404_is_a_missing_file(tmp_path):
    c, _ = client(tmp_path, [(404, b"")])
    assert c.get("https://archives.nseindia.com/x", "x") is None


def test_403_is_missing_when_the_host_still_serves_others(tmp_path):
    c, _ = client(tmp_path, [(403, b"Access Denied"), (200, b"equity list")])
    assert c.get("https://archives.nseindia.com/old.zip", "old.zip") is None


def test_403_everywhere_means_the_host_refuses_us(tmp_path):
    c, _ = client(tmp_path, [(403, b"Access Denied"), (403, b"Access Denied")])
    with pytest.raises(SourceBlocked):
        c.get("https://archives.nseindia.com/x", "x")


def test_429_waits_as_told_then_gives_up(tmp_path):
    c, slept = client(tmp_path, [(429, b"", {"Retry-After": "7"}), (200, b"ok")])
    assert c.get("https://archives.nseindia.com/x", "x") == b"ok" and 7.0 in slept
    c, _ = client(tmp_path, [(429, b"", {"Retry-After": "3600"})])
    with pytest.raises(SourceBlocked):
        c.get("https://archives.nseindia.com/y", "y")


def test_timeouts_and_server_errors_are_retried_with_growing_pauses(tmp_path):
    c, slept = client(tmp_path, [requests.Timeout(), (503, b""), (200, b"ok")])
    assert c.get("https://archives.nseindia.com/x", "x") == b"ok"
    assert [s for s in slept if s >= 2] == [2.0, 4.0]
    c, _ = client(tmp_path, [requests.ConnectionError()] * 3)
    with pytest.raises(FetchFailed):
        c.get("https://archives.nseindia.com/z", "z")


def test_cache_paths_cannot_escape_the_raw_directory(tmp_path):
    c, _ = client(tmp_path, [])
    with pytest.raises(ValueError):
        c.path("../../outside.txt")


# --- The CLI ------------------------------------------------------------------------------

@pytest.fixture
def cli_db(tmp_path):
    config_module._config["india_db_path"] = str(tmp_path / "cli" / "india.db")
    config_module._config["data_cache_dir"] = str(tmp_path / "cache")
    return tmp_path / "cli" / "india.db"


def test_status_before_any_sync(cli_db):
    out = CliRunner().invoke(app, ["india", "status"])
    assert out.exit_code == 0 and "No India database" in out.output


def test_import_then_status(cli_db):
    runner = CliRunner()
    out = runner.invoke(app, ["india", "import", str(FIXTURES)])
    assert out.exit_code == 0, out.output
    out = runner.invoke(app, ["india", "status"])
    assert out.exit_code == 0 and "financials" in out.output and "SomeNewlyIntroducedMetric" in out.output


def test_a_bad_date_is_a_usage_error(cli_db):
    out = CliRunner().invoke(app, ["india", "sync-prices", "--from", "June"])
    assert out.exit_code == 2


def test_a_missing_inbox_exits_non_zero_with_the_reason(cli_db, tmp_path):
    out = CliRunner().invoke(app, ["india", "sync-results", "--dir", str(tmp_path / "nowhere")])
    assert out.exit_code == 1 and "NSE serves them to browsers only" in out.output.replace("\n", " ")
