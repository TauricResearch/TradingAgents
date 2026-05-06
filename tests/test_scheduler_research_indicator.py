"""Header indicator for user-uploaded research notes in scheduler._push_full_report.

Pins the count formula in scheduler.py so LLM-emitted `## ` headers inside a
summary body don't inflate the per-run note count. The count anchor is the
literal upload separator `\\n\\n---\\n\\n`, which webui._assemble_user_research
controls.
"""

from unittest.mock import patch


def _run_and_capture(state):
    """Invoke scheduler._push_full_report against a stub state and return the
    list of (chat_id, msg, kwargs) recorded by send_telegram.

    Range-stats is forced to skip via a broad-except path.
    """
    import scheduler

    sent: list[tuple[str, str, dict]] = []

    def _capture(chat_id, msg, **kw):
        sent.append((chat_id, msg, kw))
        return True, "ok"

    with patch("scheduler.notify.send_telegram", side_effect=_capture), \
         patch("scheduler.compute_range_stats", side_effect=Exception("skip")), \
         patch("scheduler._load_full_state", return_value=state):
        scheduler._push_full_report(
            chat_id="123",
            slug="anyslug",
            ticker="AAPL",
            trade_date="2026-05-06",
            decision="BUY",
        )
    return sent


def test_no_research_no_indicator():
    """No `user_research_report` key → header omits the research-notes line."""
    state = {"final_trade_decision": "BUY"}
    sent = _run_and_capture(state)
    assert sent, "expected at least one message (the header)"
    header = sent[0][1]
    assert "user-uploaded research" not in header, \
        f"header should not advertise research notes when none exist: {header!r}"


def test_one_note_singular():
    """A single upload (no separator) → singular `note`, count = 1."""
    state = {
        "user_research_report": "## a.pdf (uploaded 2026-05-06)\nbody",
    }
    sent = _run_and_capture(state)
    header = sent[0][1]
    assert "📎 Used 1 user-uploaded research note" in header, \
        f"expected singular indicator in header: {header!r}"
    # Sanity: must NOT be plural.
    assert "research notes" not in header, \
        f"singular case should not contain plural form: {header!r}"


def test_two_notes_plural():
    """Two uploads joined by the upload separator → plural `notes`, count = 2."""
    state = {
        "user_research_report": (
            "## a.pdf (uploaded 2026-05-06)\nbodyA"
            "\n\n---\n\n"
            "## b.pdf (uploaded 2026-05-06)\nbodyB"
        ),
    }
    sent = _run_and_capture(state)
    header = sent[0][1]
    assert "📎 Used 2 user-uploaded research notes" in header, \
        f"expected plural indicator with count=2 in header: {header!r}"


def test_summary_with_inner_headers_does_not_inflate_count():
    """Regression for Fix 1: LLM-emitted `## ` headers in the summary body must
    not inflate the count. One upload → count = 1 even with multiple `## `
    headers inside the body.
    """
    state = {
        "user_research_report": (
            "## a.pdf (uploaded 2026-05-06)\n"
            "## Bottom line\nfoo\n"
            "## Key thesis\nbar"
        ),
    }
    sent = _run_and_capture(state)
    header = sent[0][1]
    assert "📎 Used 1 user-uploaded research note" in header, \
        f"inner `## ` headers must not inflate count; expected 1 note: {header!r}"
    # Hard guard against the old buggy count of 3.
    assert "Used 3 user-uploaded" not in header, \
        f"count must not reflect summary body headers: {header!r}"
