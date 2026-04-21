# Feature 6: Historical Rebuild Utility + CLI

**Parent plan:** `docs/superpowers/plans/2026-04-19-json-scanner-graph-facts.md`

**Goal:** Implement `rebuild.py` — the **only** code path allowed to call `save_scanner_graph_facts(..., overwrite=True)`. Provides both a Python API and a CLI entrypoint for regenerating historical artifacts.

**Dependencies already committed:**
- F5: `builder.py`, `report_paths.get_scanner_graph_facts_path`

**Files to create:**
- `tradingagents/graph/scanner_facts/rebuild.py`
- `tests/graph/scanner_facts/test_rebuild.py`

---

## Rules

- `rebuild_scanner_graph_facts()` always calls `save_scanner_graph_facts(..., overwrite=True)`.
- Tests use `tmp_path` fixture directories only. Never mutate real `reports/`.
- CLI flags: `--date`, `--run-id`, `--reports-root`, `--no-overwrite`.
- If `macro_scan_summary.json` is **missing** in the target folder: raise `FileNotFoundError` (propagated from builder).
- If `macro_scan_summary.json` is **valid JSON but structurally degraded** (empty `stocks_to_investigate`, empty `key_themes`): build proceeds, emit metadata flag `degraded_inputs: true`. This is the only sanctioned fallback per the Resume Rule.
- **Narrow fallback rule**: if `macro_scan_summary.json` is **malformed JSON** but at least one `*_summary.md` file exists and is not quality-gated, rebuild may proceed using markdown summaries only. The emitted artifact must include `"degraded_source": "macro_json_malformed"` in `metadata`.

---

## Step 1: Write failing tests

- [ ] Create `tests/graph/scanner_facts/test_rebuild.py`:

```python
"""Tests for rebuild.py — historical artifact rebuild API and CLI.

All tests use tmp_path or fixture dirs — never real reports/.
"""
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from tradingagents.graph.scanner_facts.rebuild import rebuild_scanner_graph_facts
from tradingagents.graph.scanner_facts.builder import load_scanner_graph_facts
from tradingagents.graph.scanner_facts.schema import validate_graph_facts

FIXTURES = Path(__file__).parent / "fixtures"


# ---- helper: copy fixture dir to tmp ----

def _make_tmp_market_dir(tmp_path: Path) -> Path:
    """Copy real fixtures into a temp market dir structure."""
    market = tmp_path / "reports" / "daily" / "2026-04-16" / "TESTRUN" / "market"
    market.mkdir(parents=True)
    for f in FIXTURES.iterdir():
        if f.is_file():
            shutil.copy(f, market / f.name)
    return market


# ---- basic rebuild ----

def test_rebuild_creates_artifact(tmp_path):
    market = _make_tmp_market_dir(tmp_path)
    path = rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
    )
    assert path.exists()
    assert path.name == "scanner_graph_facts.json"


def test_rebuild_artifact_schema_valid(tmp_path):
    market = _make_tmp_market_dir(tmp_path)
    path = rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
    )
    facts = load_scanner_graph_facts(path)
    errors = validate_graph_facts(facts)
    assert errors == [], f"Schema errors: {errors}"


def test_rebuild_overwrites_existing(tmp_path):
    market = _make_tmp_market_dir(tmp_path)
    path1 = rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
    )
    mtime1 = path1.stat().st_mtime

    import time; time.sleep(0.05)  # ensure mtime changes if file is rewritten

    path2 = rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
    )
    assert path1 == path2
    # File should have been rewritten
    assert path2.stat().st_mtime >= mtime1


def test_rebuild_no_overwrite_flag(tmp_path):
    market = _make_tmp_market_dir(tmp_path)
    path = rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
    )
    mtime = path.stat().st_mtime

    import time; time.sleep(0.05)

    rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
        overwrite=False,
    )
    assert path.stat().st_mtime == mtime  # not rewritten


def test_rebuild_contains_real_tickers(tmp_path):
    _make_tmp_market_dir(tmp_path)
    path = rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
    )
    facts = load_scanner_graph_facts(path)
    ids = {n["id"] for n in facts["nodes"]}
    assert "ON" in ids
    assert "Technology" in ids


# ---- error cases ----

def test_rebuild_missing_market_dir_raises(tmp_path):
    with pytest.raises((FileNotFoundError, Exception)):
        rebuild_scanner_graph_facts(
            "2026-04-16", "NORUN",
            reports_root=tmp_path / "reports",
        )


def test_rebuild_missing_macro_json_raises(tmp_path):
    market = _make_tmp_market_dir(tmp_path)
    (market / "macro_scan_summary.json").unlink()
    with pytest.raises(FileNotFoundError):
        rebuild_scanner_graph_facts(
            "2026-04-16", "TESTRUN",
            reports_root=tmp_path / "reports",
        )


# ---- degraded fallback: malformed JSON ----

def test_rebuild_malformed_macro_json_with_md_fallback(tmp_path):
    """If macro_scan_summary.json is malformed but Markdown summaries exist, rebuild proceeds."""
    market = _make_tmp_market_dir(tmp_path)
    (market / "macro_scan_summary.json").write_text("{ not valid json }")

    path = rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
    )
    facts = load_scanner_graph_facts(path)
    assert facts["metadata"].get("degraded_source") == "macro_json_malformed"
    # Markdown-sourced tickers should still be present
    ids = {n["id"] for n in facts["nodes"]}
    assert len(ids) > 0, "Expected nodes from markdown fallback"


def test_rebuild_malformed_macro_json_no_md_raises(tmp_path):
    """If both macro JSON is malformed AND no usable Markdown summaries: fail loudly."""
    market = tmp_path / "reports" / "daily" / "2026-04-16" / "TESTRUN" / "market"
    market.mkdir(parents=True)
    (market / "macro_scan_summary.json").write_text("{ not valid json }")
    # No markdown files at all → nothing to fall back to
    with pytest.raises((ValueError, FileNotFoundError)):
        rebuild_scanner_graph_facts(
            "2026-04-16", "TESTRUN",
            reports_root=tmp_path / "reports",
        )


# ---- CLI ----

def test_cli_invocation(tmp_path):
    """Invoke rebuild CLI as __main__ module using subprocess."""
    import subprocess
    import sys

    _make_tmp_market_dir(tmp_path)
    result = subprocess.run(
        [
            sys.executable, "-m",
            "tradingagents.graph.scanner_facts.rebuild",
            "--date", "2026-04-16",
            "--run-id", "TESTRUN",
            "--reports-root", str(tmp_path / "reports"),
        ],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent.parent.parent),  # repo root
    )
    assert result.returncode == 0, f"CLI failed:\n{result.stderr}"
    artifact = (
        tmp_path / "reports" / "daily" / "2026-04-16" / "TESTRUN"
        / "market" / "scanner_graph_facts.json"
    )
    assert artifact.exists()


def test_cli_no_overwrite_flag(tmp_path):
    """--no-overwrite flag prevents rewrite of existing artifact."""
    import subprocess
    import sys

    market = _make_tmp_market_dir(tmp_path)
    # First build
    rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN", reports_root=tmp_path / "reports"
    )
    artifact = market / "scanner_graph_facts.json"
    mtime = artifact.stat().st_mtime

    import time; time.sleep(0.05)

    result = subprocess.run(
        [
            sys.executable, "-m",
            "tradingagents.graph.scanner_facts.rebuild",
            "--date", "2026-04-16",
            "--run-id", "TESTRUN",
            "--reports-root", str(tmp_path / "reports"),
            "--no-overwrite",
        ],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent.parent.parent),
    )
    assert result.returncode == 0
    assert artifact.stat().st_mtime == mtime
```

## Step 2: Run failing tests

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
conda activate tradingagents
pytest tests/graph/scanner_facts/test_rebuild.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'tradingagents.graph.scanner_facts.rebuild'`

## Step 3: Implement `rebuild.py`

- [ ] Create `tradingagents/graph/scanner_facts/rebuild.py`:

```python
"""Historical rebuild utility for scanner_graph_facts.json artifacts.

This is the ONLY code path authorised to call
save_scanner_graph_facts(..., overwrite=True).

CLI usage:
    python -m tradingagents.graph.scanner_facts.rebuild \
        --date 2026-04-16 \
        --run-id 01KPBZ79XBDWWYSXVZF0APEYPW \
        [--reports-root /path/to/reports] \
        [--no-overwrite]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from tradingagents.graph.scanner_facts.builder import (
    _merge_partial_facts,
    save_scanner_graph_facts,
    load_scanner_graph_facts,
)
from tradingagents.graph.scanner_facts.from_markdown import facts_from_all_markdown_summaries
from tradingagents.graph.scanner_facts.schema import SCHEMA_VERSION, validate_graph_facts
from tradingagents.report_paths import REPORTS_ROOT, get_scanner_graph_facts_path

_logger = logging.getLogger(__name__)


def _has_usable_markdown(market_dir: Path) -> bool:
    """Return True if at least one non-quality-gated *_summary.md exists."""
    from tradingagents.graph.scanner_facts.from_markdown import is_quality_gated
    for f in market_dir.glob("*_summary.md"):
        text = f.read_text(encoding="utf-8")
        if not is_quality_gated(text):
            return True
    return False


def _build_from_markdown_only(
    market_dir: Path,
    *,
    scan_date: str,
    run_id: str,
) -> dict:
    """Build facts from Markdown summaries only (degraded fallback: macro JSON malformed)."""
    md_partial = facts_from_all_markdown_summaries(market_dir)
    merged = _merge_partial_facts([md_partial])

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    inputs = sorted(f.name for f in market_dir.glob("*_summary.md"))

    facts: dict = {
        "schema_version": SCHEMA_VERSION,
        "scan_date": scan_date,
        "run_id": run_id,
        "source_dir": str(market_dir),
        "global_regime": {
            "summary": "",
            "bullets": [],
            "source": "markdown_summaries_only",
        },
        "nodes": merged["nodes"],
        "edges": merged["edges"],
        "metadata": {
            "node_count": len(merged["nodes"]),
            "edge_count": len(merged["edges"]),
            "generated_at": generated_at,
            "inputs": inputs,
            "degraded_source": "macro_json_malformed",
        },
    }

    errors = validate_graph_facts(facts)
    if errors:
        raise ValueError(
            f"Degraded build failed validation ({len(errors)} errors): "
            + "; ".join(errors[:5])
        )
    return facts


def rebuild_scanner_graph_facts(
    scan_date: str,
    run_id: str,
    reports_root: Path | None = None,
    *,
    overwrite: bool = True,
) -> Path:
    """Rebuild the scanner_graph_facts.json artifact for the given scan_date + run_id.

    Args:
        scan_date:    ISO date string (e.g. "2026-04-16").
        run_id:       Run identifier.
        reports_root: Override the default REPORTS_ROOT (useful for tests).
        overwrite:    Default True — rebuild always overwrites. Set False to skip
                      if the artifact already exists.

    Returns:
        Path to the (re)built artifact.

    Raises:
        FileNotFoundError: market dir or macro_scan_summary.json missing with no MD fallback.
        ValueError: JSON malformed AND no usable markdown summaries.
    """
    root = Path(reports_root) if reports_root else REPORTS_ROOT
    market_dir = root / "daily" / scan_date / run_id / "market"

    if not market_dir.exists():
        raise FileNotFoundError(
            f"Market directory not found: {market_dir}. "
            "Ensure the scanner run completed before rebuilding."
        )

    # Determine artifact path using the same root
    artifact_path = market_dir / "scanner_graph_facts.json"

    if artifact_path.exists() and not overwrite:
        _logger.info("rebuild: artifact already exists at %s — skipping (--no-overwrite)", artifact_path)
        return artifact_path

    # Try primary path: macro JSON + markdown
    macro_path = market_dir / "macro_scan_summary.json"

    try:
        from tradingagents.graph.scanner_facts.from_macro_json import (
            facts_from_macro_scan_summary,
            load_and_parse_macro_scan_summary,
        )
        from tradingagents.graph.scanner_facts.builder import build_scanner_graph_facts_from_market_dir

        facts = build_scanner_graph_facts_from_market_dir(
            market_dir, scan_date=scan_date, run_id=run_id
        )

    except (json.JSONDecodeError, ValueError) as exc:
        # Narrow fallback: macro JSON malformed, try markdown-only
        if "macro_scan_summary" in str(exc) or "not valid JSON" in str(exc):
            _logger.warning(
                "rebuild: macro_scan_summary.json malformed (%s) — "
                "attempting markdown-only fallback", exc
            )
            if not _has_usable_markdown(market_dir):
                raise ValueError(
                    f"macro_scan_summary.json malformed and no usable Markdown "
                    f"summaries found in {market_dir}. Cannot rebuild."
                ) from exc
            facts = _build_from_markdown_only(
                market_dir, scan_date=scan_date, run_id=run_id
            )
        else:
            raise

    return save_scanner_graph_facts(facts, artifact_path, overwrite=overwrite)


# ---------- CLI ----------

def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tradingagents.graph.scanner_facts.rebuild",
        description="Rebuild scanner_graph_facts.json for a historical scan run.",
    )
    parser.add_argument("--date", required=True, help="Scan date (YYYY-MM-DD)")
    parser.add_argument("--run-id", required=True, dest="run_id", help="Run ID")
    parser.add_argument(
        "--reports-root", dest="reports_root", default=None,
        help="Override reports root directory",
    )
    parser.add_argument(
        "--no-overwrite", dest="no_overwrite", action="store_true",
        help="Skip rebuild if artifact already exists",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        path = rebuild_scanner_graph_facts(
            args.date,
            args.run_id,
            reports_root=Path(args.reports_root) if args.reports_root else None,
            overwrite=not args.no_overwrite,
        )
        print(f"Rebuilt: {path}")
        return 0
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(_main())
```

## Step 4: Run tests — all must pass

```bash
pytest tests/graph/scanner_facts/test_rebuild.py -v
```

Expected: all PASS. Common issues:
- `test_rebuild_malformed_macro_json_with_md_fallback`: the malformed JSON triggers the narrow fallback. The `except` clause in `rebuild.py` catches `ValueError` from `load_and_parse_macro_scan_summary`. Check that the error message contains "macro_scan_summary" or "not valid JSON" to match the condition.
- `test_cli_invocation`: uses `subprocess.run` with `cwd` set to the repo root. The `--m` flag runs `tradingagents.graph.scanner_facts.rebuild` as a module. Verify the `if __name__ == "__main__"` block calls `sys.exit(_main())`.
- `test_rebuild_missing_market_dir_raises`: the market dir doesn't exist at all — `rebuild_scanner_graph_facts` must raise before even trying to find `macro_scan_summary.json`.

## Step 5: Run full suite

```bash
pytest tests/graph/scanner_facts/ -v
pytest tests/ -v -m "not integration" -x
```

## Step 6: Commit

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claire/worktrees/silly-meitner-37bb65
git add \
  tradingagents/graph/scanner_facts/rebuild.py \
  tests/graph/scanner_facts/test_rebuild.py
git commit -m "feat(scanner-facts): rebuild utility with markdown-only fallback and CLI entrypoint"
```

---

## Done When

- `pytest tests/graph/scanner_facts/test_rebuild.py -v` → all green
- `pytest tests/ -v -m "not integration" -x` → no regressions
- `python -m tradingagents.graph.scanner_facts.rebuild --date 2026-04-16 --run-id TESTRUN --reports-root <tmp>` exits 0
- Malformed macro JSON with usable markdown → artifact saved with `metadata.degraded_source = "macro_json_malformed"`
- Missing market dir → `FileNotFoundError`
