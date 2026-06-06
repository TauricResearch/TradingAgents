import pytest

from tradingagents.persistence.db import connect as iic_connect
from tradingagents.persistence import store


def _seed_run_with_cost(conn, run_id, ts, usd, model="deepseek-chat"):
    store.insert_run(
        conn, run_id=run_id, ticker="AAPL", persona_id="macro",
        started_ts=ts, artifact_dir=f"runs/{run_id}",
    )
    store.finalize_run(conn, run_id=run_id, ended_ts=ts,
                       status="ok", decision="BUY", confidence=0.7)
    conn.execute(
        "INSERT INTO costs (run_id, provider, model, in_tokens, out_tokens, usd_estimate) "
        "VALUES (?, 'deepseek', ?, 1000, 500, ?)",
        (run_id, model, usd),
    )
    conn.commit()


@pytest.mark.unit
def test_fetch_daily_cost_trend_groups_by_day_and_model(tmp_path):
    from tradingagents.dashboard.panels.costs import fetch_daily_cost_trend

    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed_run_with_cost(conn, "r1", "2026-05-25T10:00:00+00:00", 0.10, "model-a")
    _seed_run_with_cost(conn, "r2", "2026-05-25T11:00:00+00:00", 0.20, "model-a")
    _seed_run_with_cost(conn, "r3", "2026-05-26T10:00:00+00:00", 0.50, "model-b")

    rows = fetch_daily_cost_trend(conn, days=3650)  # large window so it doesn't filter out test data
    by_key = {(r["day"], r["model"]): r["total_usd"] for r in rows}
    assert by_key[("2026-05-25", "model-a")] == pytest.approx(0.30)
    assert by_key[("2026-05-26", "model-b")] == pytest.approx(0.50)


@pytest.mark.unit
def test_fetch_daily_cost_trend_includes_cache_ratio(tmp_path):
    from tradingagents.dashboard.panels.costs import fetch_daily_cost_trend

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_run(
        conn,
        run_id="r-cache",
        ticker="AAPL",
        persona_id="macro",
        started_ts="2026-05-25T10:00:00+00:00",
        artifact_dir="runs/r-cache",
    )
    store.finalize_run(
        conn,
        run_id="r-cache",
        ended_ts="2026-05-25T10:05:00+00:00",
        status="complete",
        decision="BUY",
        confidence=0.7,
    )
    store.record_cost(
        conn,
        run_id="r-cache",
        provider="deepseek",
        model="deepseek-v4-flash",
        in_tokens=1000,
        out_tokens=100,
        usd_estimate=0.001,
        cache_hit_tokens=750,
        cache_miss_tokens=250,
    )

    rows = fetch_daily_cost_trend(conn, days=3650)
    row = next(r for r in rows if r["model"] == "deepseek-v4-flash")

    assert row["cache_hit_tokens"] == 750
    assert row["cache_miss_tokens"] == 250
    assert row["cache_hit_ratio"] == pytest.approx(0.75)
