from pathlib import Path


def test_save_and_list_per_ticker(tmp_path: Path):
    from tradingagents.dataflows.user_research import (
        _save,
        list_research,
    )
    user_root = tmp_path / "user42"
    saved = _save(
        file_bytes=b"# my note",
        summary_md="**summary**",
        ticker="AAPL",
        user_root=user_root,
        original_filename="goldman.md",
        run_id=None,
    )
    assert saved["path"].endswith(".md")
    assert (user_root / "research" / "AAPL").exists()
    listed = list_research(user_root, "AAPL")
    assert len(listed) == 1
    assert listed[0]["filename"] == "goldman.md"
    assert listed[0]["summary"] == "**summary**"


def test_dedupes_by_content_hash(tmp_path: Path):
    from tradingagents.dataflows.user_research import _save, list_research
    user_root = tmp_path / "user42"
    _save(b"identical bytes", "s1", "AAPL", user_root, "a.md", None)
    _save(b"identical bytes", "s2", "AAPL", user_root, "b.md", None)
    listed = list_research(user_root, "AAPL")
    assert len(listed) == 1, "second upload with same content should de-duplicate"


def test_delete_research(tmp_path: Path):
    from tradingagents.dataflows.user_research import (
        _save, list_research, delete_research,
    )
    user_root = tmp_path / "user42"
    saved = _save(b"hello", "summary", "AAPL", user_root, "n.md", None)
    delete_research(user_root, "AAPL", saved["hash"])
    assert list_research(user_root, "AAPL") == []


def test_per_run_storage_lives_under_shared(tmp_path: Path):
    from tradingagents.dataflows.user_research import _save
    user_root = tmp_path / "user42"
    saved = _save(b"once", "s", None, user_root, "tmp.txt", run_id="run-1")
    assert "_shared_for_run" in saved["path"]
    assert "run-1" in saved["path"]


def test_clear_run_dir(tmp_path: Path):
    from tradingagents.dataflows.user_research import _save, clear_run_dir
    user_root = tmp_path / "user42"
    _save(b"x", "s", None, user_root, "t.txt", run_id="run-1")
    clear_run_dir(user_root, "run-1")
    assert not (user_root / "research" / "_shared_for_run" / "run-1").exists()


def test_list_research_unknown_ticker_returns_empty(tmp_path: Path):
    from tradingagents.dataflows.user_research import list_research
    assert list_research(tmp_path / "user42", "ZZZ") == []


def test_dedupe_return_dict_reflects_persisted_first_upload(tmp_path):
    from tradingagents.dataflows.user_research import _save, list_research
    user_root = tmp_path / "user42"
    first = _save(b"identical bytes", "first_summary", "AAPL", user_root, "first.md", None)
    second = _save(b"identical bytes", "second_summary", "AAPL", user_root, "second.md", None)
    assert first["deduped"] is False
    assert second["deduped"] is True
    # Second call's return must reflect what's actually on disk (the first upload).
    assert second["filename"] == "first.md"
    assert second["summary"] == "first_summary"
    # And list_research agrees.
    listed = list_research(user_root, "AAPL")
    assert len(listed) == 1
    assert listed[0]["filename"] == "first.md"


def test_delete_research_rejects_path_injection_digest(tmp_path):
    from tradingagents.dataflows.user_research import _save, delete_research, list_research
    user_root = tmp_path / "user42"
    saved = _save(b"hello", "summary", "AAPL", user_root, "n.md", None)
    # Try a malicious "digest" — must be rejected silently.
    delete_research(user_root, "AAPL", "../../etc/passwd")
    delete_research(user_root, "AAPL", "*")
    # Original entry should still be intact.
    listed = list_research(user_root, "AAPL")
    assert len(listed) == 1
    assert listed[0]["hash"] == saved["hash"]
