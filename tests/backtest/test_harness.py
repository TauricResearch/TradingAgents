import json
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def conn(tmp_path):
    from tradingagents.persistence.db import connect
    return connect(str(tmp_path / "iic.db"))


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    return str(d)


@pytest.fixture
def fake_graph_runner():
    """Mock graph runner: returns a fresh run_id and a deterministic decision
    per (ticker, persona)."""
    from tradingagents.persistence import store

    class FakeRunner:
        def __init__(self):
            self.invocations = []

        def run(self, *, ticker, trade_date, persona_id, conn):
            run_id = uuid.uuid4().hex
            now = datetime.now(timezone.utc).isoformat()
            store.insert_run(conn, run_id=run_id, ticker=ticker,
                             persona_id=persona_id, started_ts=now,
                             artifact_dir=f"runs/{run_id}")
            decision = {"macro": "BUY", "value": "HOLD", "momentum": "SELL"}.get(
                persona_id, "HOLD"
            )
            store.finalize_run(conn, run_id=run_id, ended_ts=now,
                               status="complete", decision=decision)
            self.invocations.append((ticker, trade_date, persona_id))
            return run_id, decision
    return FakeRunner()


@pytest.fixture
def fake_price_chain():
    """Mock chain returning a 2-bar synthetic series (start, end)."""
    from tradingagents.backtest.prices import Bars, Resolution

    class FakeChain:
        def __init__(self):
            self.calls = []

        def get_bars(self, ticker, start, end, resolution):
            self.calls.append((ticker, start, end, resolution))
            if start == end:
                return Bars(
                    ticker=ticker, resolution=resolution,
                    bars=[(datetime.combine(start, datetime.min.time()), 100.0)],
                    source="fake",
                )
            return Bars(
                ticker=ticker, resolution=resolution,
                bars=[
                    (datetime.combine(start, datetime.min.time()), 100.0),
                    (datetime.combine(end,   datetime.min.time()), 110.0),
                ],
                source="fake",
            )

    return FakeChain()


@pytest.mark.unit
def test_watchlist_open_inserts_backtests_and_backtest_runs(
    conn, data_dir, fake_graph_runner, fake_price_chain
):
    from tradingagents.backtest.harness import BacktestHarness
    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=fake_price_chain)
    backtest_id = h.run_watchlist(
        tickers=["AAPL", "MSFT"],
        personas=["macro", "value"],
        start_date=date(2030, 1, 1),  # future → don't auto-mature
        end_date=date(2030, 1, 31),
    )

    backtests = list(conn.execute("SELECT * FROM backtests WHERE backtest_id=?",
                                    (backtest_id,)))
    assert len(backtests) == 1
    assert backtests[0]["status"] == "open"
    assert json.loads(backtests[0]["universe"]) == ["AAPL", "MSFT"]

    runs = list(conn.execute("SELECT * FROM backtest_runs WHERE backtest_id=?",
                              (backtest_id,)))
    assert len(runs) == 4  # 2 tickers × 2 personas
    for r in runs:
        m = json.loads(r["metrics"])
        assert m["status"] == "open"
        assert m["decision"] in ("BUY", "HOLD", "SELL")
        assert m["entry_price"] == pytest.approx(100.0)
        assert m["entry_date"] == "2030-01-01"
        assert m["scheduled_close_date"] == "2030-01-31"
        assert m["resolution"] == "1d"
        assert m["price_source"] == "fake"


@pytest.mark.unit
def test_watchlist_open_calls_graph_runner_per_ticker_persona(
    conn, data_dir, fake_graph_runner, fake_price_chain
):
    from tradingagents.backtest.harness import BacktestHarness
    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=fake_price_chain)
    h.run_watchlist(tickers=["AAPL", "MSFT"],
                     personas=["macro", "value", "momentum"],
                     start_date=date(2030, 1, 1),
                     end_date=date(2030, 1, 31))
    assert len(fake_graph_runner.invocations) == 6  # 2 × 3
    personas_seen = {p for (_, _, p) in fake_graph_runner.invocations}
    tickers_seen = {t for (t, _, _) in fake_graph_runner.invocations}
    assert personas_seen == {"macro", "value", "momentum"}
    assert tickers_seen == {"AAPL", "MSFT"}


@pytest.mark.unit
def test_watchlist_open_does_not_mature_future_window(
    conn, data_dir, fake_graph_runner, fake_price_chain
):
    """When end_date > today, all backtest_runs stay status=open."""
    from tradingagents.backtest.harness import BacktestHarness
    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=fake_price_chain)
    backtest_id = h.run_watchlist(tickers=["AAPL"], personas=["macro"],
                                    start_date=date(2030, 1, 1),
                                    end_date=date(2030, 1, 31))
    runs = list(conn.execute("SELECT metrics FROM backtest_runs WHERE backtest_id=?",
                              (backtest_id,)))
    for r in runs:
        m = json.loads(r["metrics"])
        assert m["status"] == "open"
        assert "close_date" not in m


@pytest.fixture
def historical_price_chain():
    """Mock chain returning a deterministic 6-bar series for any ticker."""
    from tradingagents.backtest.prices import Bars, Resolution

    class HistoricalChain:
        def __init__(self):
            self.bars_for = {
                ("AAPL", "entry"):    [(datetime(2026, 4, 26), 200.0)],
                ("AAPL", "full"):     [
                    (datetime(2026, 4, 26), 200.0),
                    (datetime(2026, 4, 30), 202.0),
                    (datetime(2026, 5,  5), 198.0),
                    (datetime(2026, 5, 12), 210.0),
                    (datetime(2026, 5, 20), 215.0),
                    (datetime(2026, 5, 26), 220.0),
                ],
                ("SPY",  "entry"):    [(datetime(2026, 4, 26), 500.0)],
                ("SPY",  "full"):     [
                    (datetime(2026, 4, 26), 500.0),
                    (datetime(2026, 4, 30), 501.0),
                    (datetime(2026, 5,  5), 499.0),
                    (datetime(2026, 5, 12), 505.0),
                    (datetime(2026, 5, 20), 507.0),
                    (datetime(2026, 5, 26), 510.0),
                ],
            }

        def get_bars(self, ticker, start, end, resolution):
            kind = "entry" if start == end else "full"
            bars = self.bars_for.get((ticker, kind), [])
            return Bars(ticker=ticker, resolution=resolution, bars=bars,
                        source="historical")

    return HistoricalChain()


@pytest.mark.unit
def test_watchlist_with_past_end_date_matures_inline(
    conn, data_dir, fake_graph_runner, historical_price_chain
):
    """When end_date <= today, all backtest_runs close inline."""
    from tradingagents.backtest.harness import BacktestHarness
    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=historical_price_chain)
    backtest_id = h.run_watchlist(
        tickers=["AAPL"], personas=["macro"],
        start_date=date(2026, 4, 26), end_date=date(2026, 5, 26),
    )

    backtests_row = conn.execute(
        "SELECT * FROM backtests WHERE backtest_id=?", (backtest_id,)
    ).fetchone()
    assert backtests_row["status"] == "closed"

    runs = list(conn.execute(
        "SELECT metrics FROM backtest_runs WHERE backtest_id=?", (backtest_id,)
    ))
    assert len(runs) == 1
    m = json.loads(runs[0]["metrics"])
    assert m["status"] == "closed"
    assert m["close_date"] == "2026-05-26"
    assert m["exit_price"] == pytest.approx(220.0)
    assert m["total_return"] == pytest.approx(0.10, rel=1e-6)
    assert m["benchmark_return"] == pytest.approx((510 - 500) / 500, rel=1e-6)
    assert m["alpha"] == pytest.approx(0.10 - 0.02, rel=1e-6)
    assert isinstance(m["returns"], list) and len(m["returns"]) >= 1
    assert "sharpe" in m and "max_drawdown" in m and "win_rate" in m
    assert m["holding_days_elapsed"] == 30


@pytest.mark.unit
def test_maturation_writes_outcome_log_row(
    conn, data_dir, fake_graph_runner, historical_price_chain
):
    from tradingagents.backtest.harness import BacktestHarness
    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=historical_price_chain)
    h.run_watchlist(tickers=["AAPL"], personas=["macro"],
                     start_date=date(2026, 4, 26), end_date=date(2026, 5, 26))
    rows = list(conn.execute("SELECT * FROM outcome_log"))
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAPL"
    tags = json.loads(rows[0]["tags"])
    assert tags["persona_id"] == "macro"
    assert tags["source"] == "forward_test"


@pytest.mark.unit
def test_maturation_handles_missing_exit_price_as_errored(
    conn, data_dir, fake_graph_runner
):
    """If the price chain raises for the exit fetch, the row is errored,
    not silently zero-returns."""
    from tradingagents.backtest.harness import BacktestHarness
    from tradingagents.backtest.prices import Bars, Resolution

    class FlakyChain:
        def get_bars(self, ticker, start, end, resolution):
            if start == end:  # entry fetch
                return Bars(ticker=ticker, resolution=resolution,
                            bars=[(datetime(2026, 4, 26), 100.0)], source="x")
            raise RuntimeError("exit fetch failed")

    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=FlakyChain())
    backtest_id = h.run_watchlist(
        tickers=["AAPL"], personas=["macro"],
        start_date=date(2026, 4, 26), end_date=date(2026, 5, 26),
    )
    runs = list(conn.execute("SELECT metrics FROM backtest_runs WHERE backtest_id=?",
                              (backtest_id,)))
    m = json.loads(runs[0]["metrics"])
    assert m["status"] == "errored"
    assert "exit" in m["error"].lower() or "fetch" in m["error"].lower()


@pytest.fixture
def seeded_brief(conn, fake_graph_runner):
    """Insert a brief with three runs (one per persona) for AAPL."""
    from tradingagents.persistence import store
    run_ids = []
    for persona_id in ("macro", "value", "momentum"):
        rid, _ = fake_graph_runner.run(
            ticker="AAPL", trade_date="2026-04-26",
            persona_id=persona_id, conn=conn,
        )
        run_ids.append(rid)

    brief_id = uuid.uuid4().hex
    store.insert_brief(conn,
        brief_id=brief_id, mode="deep_dive", scope="AAPL",
        generated_ts="2026-04-26T12:00:00+00:00",
        content_path=f"briefs/{brief_id}.md",
        run_ids=run_ids,
    )
    return brief_id, run_ids


@pytest.mark.unit
def test_brief_scoped_opens_one_run_per_brief_run_id(
    conn, data_dir, fake_graph_runner, historical_price_chain, seeded_brief
):
    brief_id, expected_run_ids = seeded_brief
    fake_graph_runner.invocations.clear()  # ensure brief-scoped doesn't re-invoke

    from tradingagents.backtest.harness import BacktestHarness
    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=historical_price_chain)
    backtest_id = h.run_brief_scoped(brief_id=brief_id)

    # No fresh graph runs.
    assert fake_graph_runner.invocations == []

    bt_row = conn.execute("SELECT * FROM backtests WHERE backtest_id=?",
                           (backtest_id,)).fetchone()
    assert bt_row["triggered_by_brief_id"] == brief_id
    assert json.loads(bt_row["universe"]) == ["AAPL"]

    runs = list(conn.execute("SELECT * FROM backtest_runs WHERE backtest_id=?",
                              (backtest_id,)))
    assert len(runs) == 3
    seen_run_ids = {json.loads(r["metrics"])["run_id"] for r in runs}
    assert seen_run_ids == set(expected_run_ids)


@pytest.mark.unit
def test_brief_scoped_entry_date_matches_brief_generated_ts(
    conn, data_dir, fake_graph_runner, historical_price_chain, seeded_brief
):
    brief_id, _ = seeded_brief
    from tradingagents.backtest.harness import BacktestHarness
    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=historical_price_chain)
    backtest_id = h.run_brief_scoped(brief_id=brief_id)
    runs = list(conn.execute("SELECT metrics FROM backtest_runs WHERE backtest_id=?",
                              (backtest_id,)))
    for r in runs:
        m = json.loads(r["metrics"])
        assert m["entry_date"] == "2026-04-26"
        assert m["scheduled_close_date"] == "2026-05-26"


@pytest.mark.unit
def test_open_falls_back_to_lookback_when_start_date_has_no_bar(
    conn, data_dir, fake_graph_runner
):
    """When start_date is a non-trading day (e.g. Sunday), the harness
    must look back to find the most recent close. Otherwise yfinance
    returning empty bars on weekends would error every forward test."""
    from tradingagents.backtest.harness import BacktestHarness
    from tradingagents.backtest.prices import Bars, Resolution

    SUNDAY = date(2026, 4, 26)  # actual Sunday in the exit-gate window
    FRIDAY_CLOSE = 213.45

    class WeekendChain:
        """yfinance-like: empty on a single-Sunday query, populated weekday
        bars otherwise. The harness must use look-back to find a price."""
        def get_bars(self, ticker, start, end, resolution):
            if start == end == SUNDAY:
                return Bars(ticker=ticker, resolution=resolution,
                             bars=[], source="weekend_chain")
            bars = []
            d = start
            while d <= end:
                if d.weekday() < 5:  # Mon-Fri only
                    price = FRIDAY_CLOSE if d == date(2026, 4, 24) else 215.0
                    bars.append((datetime(d.year, d.month, d.day), price))
                d += timedelta(days=1)
            return Bars(ticker=ticker, resolution=resolution, bars=bars,
                         source="weekend_chain")

    h = BacktestHarness(
        conn=conn, data_dir=data_dir,
        graph_runner=fake_graph_runner, price_chain=WeekendChain(),
    )
    # end_date in the future so the row stays `open` (we want to inspect
    # the entry_price specifically, not maturation).
    backtest_id = h.run_watchlist(
        tickers=["AAPL"], personas=["macro"],
        start_date=SUNDAY,
        end_date=date(2099, 1, 1),
    )
    runs = list(conn.execute(
        "SELECT metrics FROM backtest_runs WHERE backtest_id=?", (backtest_id,)
    ))
    m = json.loads(runs[0]["metrics"])
    assert m["status"] == "open", f"expected open, got {m}"
    assert m["entry_price"] == pytest.approx(FRIDAY_CLOSE)
