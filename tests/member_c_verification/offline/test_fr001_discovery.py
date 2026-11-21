"""SEL-TA-FR-001 — Discover and select a portfolio file.

Fit: with eligible a.json/b.json plus a nested JSON, a symlink and a text file,
exactly a/b appear once in sorted order; selecting b passes only b to
validation; empty/missing/unreadable directories follow their declared branch;
cancelling dispatches zero LLM calls; one invalid selection does not default.

Enforcing design: runapi/input_service.PortfolioInputService.discover (INV-01).
"""

from __future__ import annotations

import os

import pytest

from tradingagents.runapi.input_service import DirectoryReadError, PortfolioInputService

pytestmark = pytest.mark.unit


# TC-FR001-a: only regular direct-child .json files, sorted, symlinks excluded.
def test_tc_fr001_a_discover_lists_only_regular_json_sorted(tmp_path):
    (tmp_path / "b.json").write_text('{"positions": []}')
    (tmp_path / "a.json").write_text('{"positions": []}')
    (tmp_path / "notes.txt").write_text("not a portfolio")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "c.json").write_text('{"positions": []}')
    try:
        os.symlink(tmp_path / "a.json", tmp_path / "link.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")

    names = [path.name for path in PortfolioInputService(tmp_path).discover()]

    assert names == ["a.json", "b.json"]  # sorted, no nested, no txt, no symlink


# TC-FR001-b: a missing directory is empty, not an error.
def test_tc_fr001_b_missing_directory_is_empty(tmp_path):
    assert PortfolioInputService(tmp_path / "does-not-exist").discover() == []


# TC-FR001-c: an empty directory returns no candidates.
def test_tc_fr001_c_empty_directory_is_empty(tmp_path):
    assert PortfolioInputService(tmp_path).discover() == []


# TC-FR001-d: an unreadable directory raises a distinguishable read error,
# never described as an empty directory.
def test_tc_fr001_d_unreadable_directory_raises(tmp_path, monkeypatch):
    service = PortfolioInputService(tmp_path)

    def boom(_path):
        raise PermissionError("denied")

    monkeypatch.setattr(os, "scandir", boom)
    with pytest.raises(DirectoryReadError):
        service.discover()


# TC-FR001-e: selecting b validates only b (no default, no nearest-match).
def test_tc_fr001_e_selecting_b_validates_only_b(tmp_path):
    service = PortfolioInputService(tmp_path)
    (tmp_path / "a.json").write_text('{"positions": [{"ticker": "AAA", "quantity": 1}]}')
    (tmp_path / "b.json").write_text('{"positions": [{"ticker": "BBB", "quantity": 2}]}')

    loaded = service.read_file(tmp_path / "b.json")

    assert [p.ticker for p in loaded.context.positions] == ["BBB"]
    assert loaded.basename == "b.json"
