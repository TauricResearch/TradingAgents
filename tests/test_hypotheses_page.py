"""Tests for the hypotheses dashboard page data loading."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tradingagents.ui.pages.hypotheses import (
    load_active_hypotheses,
    load_concluded_hypotheses,
    days_until_ready,
)


def test_load_active_hypotheses(tmp_path):
    active = {
        "max_active": 5,
        "hypotheses": [
            {
                "id": "options_flow-test",
                "title": "Test hypothesis",
                "scanner": "options_flow",
                "status": "running",
                "priority": 7,
                "days_elapsed": 5,
                "min_days": 14,
                "created_at": "2026-04-01",
                "picks_log": ["2026-04-01"] * 5,
                "conclusion": None,
            }
        ],
    }
    f = tmp_path / "active.json"
    f.write_text(json.dumps(active))
    result = load_active_hypotheses(str(f))
    assert len(result) == 1
    assert result[0]["id"] == "options_flow-test"


def test_load_active_hypotheses_missing_file(tmp_path):
    result = load_active_hypotheses(str(tmp_path / "missing.json"))
    assert result == []


def test_load_concluded_hypotheses(tmp_path):
    doc = tmp_path / "2026-04-10-options_flow-test.md"
    doc.write_text(
        "# Hypothesis: Test\n\n"
        "**Scanner:** options_flow\n"
        "**Period:** 2026-03-27 → 2026-04-10 (14 days)\n"
        "**Outcome:** accepted ✅\n"
    )
    results = load_concluded_hypotheses(str(tmp_path))
    assert len(results) == 1
    assert results[0]["filename"] == doc.name
    assert results[0]["outcome"] == "accepted ✅"


def test_load_concluded_hypotheses_empty_dir(tmp_path):
    results = load_concluded_hypotheses(str(tmp_path))
    assert results == []


def test_days_until_ready_has_days_left():
    hyp = {"days_elapsed": 5, "min_days": 14}
    assert days_until_ready(hyp) == 9


def test_days_until_ready_past_due():
    hyp = {"days_elapsed": 15, "min_days": 14}
    assert days_until_ready(hyp) == 0
