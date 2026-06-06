"""F1 exit-gate smoke test.

Runs the real default deepdive on AAPL. Requires DEEPSEEK_API_KEY in the
environment. Marked ``integration`` so it does not run in the default test loop.

Verifies the four exit-gate clauses from §7 F1 of the program design:
1. One balanced default run launched.
2. Per-analyst markdown is written to data/runs/<run_id>/.
3. Both ``runs`` and ``briefs`` rows are recorded in SQLite.
4. The produced brief contains the three structured sections.
"""

import os
import pytest
from datetime import date, timedelta
from pathlib import Path

from tradingagents.persistence.db import connect


pytestmark = pytest.mark.integration


def test_f1_exit_gate_deepdive_aapl(tmp_path):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key or api_key == "placeholder":
        pytest.skip("DEEPSEEK_API_KEY not set (or placeholder from conftest)")

    db_path = str(tmp_path / "iic.db")
    data_dir = str(tmp_path / "data")

    # Use a trade_date well in the past so yfinance / stockstats have real
    # historical OHLCV both before AND after it. The engine fetches a
    # forward-looking window from trade_date; using today's date causes
    # "$AAPL: possibly delisted; no price data found" because the future
    # data doesn't exist yet. 20 trading days is enough buffer.
    trade_date = (date.today() - timedelta(days=30)).isoformat()

    from cli.deepdive import run_deepdive
    try:
        brief_id = run_deepdive(
            ticker="AAPL",
            trade_date=trade_date,
            parallel=True,
            config_overrides={
                "iic_db_path": db_path,
                "iic_data_dir": data_dir,
                "results_dir": str(tmp_path / "results"),
                "data_cache_dir": str(tmp_path / "cache"),
                "memory_log_path": str(tmp_path / "memory" / "trading_memory.md"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        if exc.__class__.__name__ == "APIConnectionError":
            pytest.skip(f"LLM provider network unavailable: {exc}")
        raise
    assert brief_id

    conn = connect(db_path)

    # Exit-gate clause 1: one balanced default run.
    runs = list(conn.execute("SELECT persona_id, status, decision FROM runs"))
    assert len(runs) == 1, f"expected 1 default run, got {len(runs)}: {runs}"
    persona_ids = {r["persona_id"] for r in runs}
    assert persona_ids == {"balanced"}
    assert all(r["status"] == "complete" for r in runs)

    # Exit-gate clause 2: per-analyst markdown on disk.
    for r in conn.execute("SELECT run_id, artifact_dir FROM runs"):
        run_path = Path(data_dir) / r["artifact_dir"]
        assert run_path.exists(), f"missing artifact dir for {r['run_id']}"
        assert (run_path / "meta.json").exists()
        # At least one analyst MD should be present.
        analyst_files = list((run_path / "analysts").glob("*.md"))
        assert analyst_files, f"no analyst markdown in {run_path}"

    # Exit-gate clause 3: briefs row exists.
    brief_row = conn.execute("SELECT * FROM briefs WHERE brief_id = ?",
                             (brief_id,)).fetchone()
    assert brief_row is not None
    assert brief_row["mode"] == "deep_dive"
    assert brief_row["scope"] == "AAPL"

    # Exit-gate clause 4: brief markdown has the three sections.
    brief_path = tmp_path / "data" / brief_row["content_path"]
    assert brief_path.exists()
    text = brief_path.read_text(encoding="utf-8")
    assert "Consensus" in text
    assert "Divergence" in text
    assert "Recommendation" in text
