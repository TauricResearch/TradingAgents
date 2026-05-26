"""F1 exit-gate smoke test.

Runs the real deepdive on AAPL with all three personas. Requires
DEEPSEEK_API_KEY in the environment. Marked ``integration`` so it does
not run in the default test loop.

Verifies the four exit-gate clauses from §7 F1 of the program design:
1. Three persona runs launched.
2. Per-analyst markdown is written to data/runs/<run_id>/.
3. Both ``runs`` and ``briefs`` rows are recorded in SQLite.
4. The produced brief contains the three structured sections.
"""

import os
import pytest
from pathlib import Path

from tradingagents.persistence.db import connect


pytestmark = pytest.mark.integration


def test_f1_exit_gate_deepdive_aapl(tmp_path, monkeypatch):
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set")

    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))

    from cli.deepdive import run_deepdive
    brief_id = run_deepdive(ticker="AAPL", trade_date="2026-05-25", parallel=True)
    assert brief_id

    conn = connect(str(tmp_path / "iic.db"))

    # Exit-gate clause 1: three persona runs.
    runs = list(conn.execute("SELECT persona_id, status, decision FROM runs"))
    assert len(runs) == 3, f"expected 3 persona runs, got {len(runs)}: {runs}"
    persona_ids = {r["persona_id"] for r in runs}
    assert persona_ids == {"macro", "value", "momentum"}
    assert all(r["status"] == "complete" for r in runs)

    # Exit-gate clause 2: per-analyst markdown on disk.
    for r in conn.execute("SELECT run_id, artifact_dir FROM runs"):
        run_path = tmp_path / "data" / r["artifact_dir"]
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
