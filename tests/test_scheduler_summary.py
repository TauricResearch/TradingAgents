"""Summary-mode dispatch + format for big watchlists in scheduler._process_user.

Pins three behaviors:
  1. SUMMARY_THRESHOLD boundary — N ≤ threshold uses _push_full_report;
     N > threshold uses _push_summary.
  2. _format_summary groups tickers by BUY/SELL/HOLD/Failed in stable
     alphabetical order (so output is reproducible regardless of which
     worker finishes first under concurrency).
  3. Concurrency setting reaches the ThreadPoolExecutor and all submitted
     tickers are processed exactly once.
"""

from unittest.mock import patch

import scheduler


# ────────────────────────────── _format_summary ──────────────────────────────

def test_format_summary_groups_decisions_alphabetically():
    results = [
        {"ticker": "NVDA", "ok": True, "decision": "BUY signal"},
        {"ticker": "AAPL", "ok": True, "decision": "BUY"},
        {"ticker": "MSFT", "ok": True, "decision": "HOLD steady"},
        {"ticker": "ABBV", "ok": True, "decision": "SELL now"},
    ]
    text = scheduler._format_summary("2026-05-07", results, elapsed_sec=120)

    assert "📊 Daily 2026-05-07 · 4 tickers · 2 min" in text
    # BUY group is alphabetical
    assert "🟢 BUY (2)" in text
    buy_line = next(line for line in text.splitlines() if " · " in line and "AAPL" in line)
    assert buy_line.strip() == "AAPL · NVDA"
    assert "🔴 SELL (1)" in text
    assert "🟡 HOLD (1)" in text


def test_format_summary_separates_failed():
    results = [
        {"ticker": "AAPL", "ok": True, "decision": "BUY"},
        {"ticker": "BAD",  "ok": False, "error_msg": "RateLimit: 429 too many"},
        {"ticker": "WORSE", "ok": False, "error_msg": "Timeout: worker hung"},
    ]
    text = scheduler._format_summary("2026-05-07", results, elapsed_sec=300)
    assert "⚠️ Failed (2)" in text
    assert "BAD: RateLimit: 429 too many" in text
    assert "WORSE: Timeout: worker hung" in text
    # Successful one still appears in BUY bucket
    assert "🟢 BUY (1)" in text
    assert "AAPL" in text


def test_format_summary_unclassified_decisions_separate_bucket():
    """Decisions that don't parse to BUY/SELL/HOLD land in the ⚪ bucket so
    they aren't silently dropped."""
    results = [
        {"ticker": "WEIRD", "ok": True, "decision": "no clear signal"},
        {"ticker": "AAPL",  "ok": True, "decision": "BUY"},
    ]
    text = scheduler._format_summary("2026-05-07", results, elapsed_sec=60)
    assert "⚪ Unclassified (1)" in text
    assert "WEIRD" in text
    assert "🟢 BUY (1)" in text


# ───────────────────────── threshold dispatch in _process_user ─────────────────

def _fake_worker_factory(decisions: dict[str, str]):
    """Returns a fake _run_worker that looks up decision by ticker."""
    def _fake(slug, ticker, trade_date, prefs):
        return {"ok": True, "decision": decisions.get(ticker, "BUY")}
    return _fake


def _run_process_user(tickers, decisions, *, threshold=5, concurrency=2):
    prefs = {
        "daily_schedule_enabled": True,
        "telegram_chat_id": "111",
        "tickers": tickers,
        "selected_analysts": ["market"],
    }
    sent: list[tuple[str, str, dict]] = []

    def _capture(chat_id, msg, **kw):
        sent.append((chat_id, msg, kw))
        return True, "ok"

    full_calls: list[str] = []
    def _fake_push_full(chat_id, slug, ticker, trade_date, decision):
        full_calls.append(ticker)

    summary_calls: list[list[dict]] = []
    real_push_summary = scheduler._push_summary
    def _wrapped_summary(chat_id, trade_date, results, *, elapsed_sec):
        summary_calls.append(list(results))
        return real_push_summary(chat_id, trade_date, results,
                                 elapsed_sec=elapsed_sec)

    with patch.object(scheduler, "SUMMARY_THRESHOLD", threshold), \
         patch.object(scheduler, "CONCURRENCY", concurrency), \
         patch.object(scheduler, "_run_worker",
                      side_effect=_fake_worker_factory(decisions)), \
         patch.object(scheduler.ticker_resolver, "resolve_ticker",
                      side_effect=lambda raw: (raw, "ok")), \
         patch.object(scheduler.notify, "send_telegram", side_effect=_capture), \
         patch.object(scheduler, "_push_full_report",
                      side_effect=_fake_push_full), \
         patch.object(scheduler, "_push_summary", side_effect=_wrapped_summary):
        scheduler._process_user("slug", prefs, dry_run=False)

    return {"sent": sent, "full_calls": full_calls,
            "summary_calls": summary_calls}


def test_at_threshold_uses_full_reports_not_summary():
    """5 tickers, threshold=5 → strict `>` means full mode."""
    tickers = ["A", "B", "C", "D", "E"]
    decisions = {t: "BUY" for t in tickers}
    out = _run_process_user(tickers, decisions, threshold=5)
    assert sorted(out["full_calls"]) == sorted(tickers)
    assert out["summary_calls"] == [], \
        "5 tickers must NOT trigger summary mode at threshold=5"


def test_above_threshold_switches_to_summary():
    """6 tickers, threshold=5 → summary mode, no per-ticker full report."""
    tickers = ["A", "B", "C", "D", "E", "F"]
    decisions = {"A": "BUY", "B": "BUY", "C": "SELL",
                 "D": "HOLD", "E": "HOLD", "F": "HOLD"}
    out = _run_process_user(tickers, decisions, threshold=5)
    assert out["full_calls"] == [], \
        "summary mode must skip per-ticker full reports"
    assert len(out["summary_calls"]) == 1
    summary_results = out["summary_calls"][0]
    assert sorted(r["ticker"] for r in summary_results) == sorted(tickers)
    # The actual telegram message should be a single send
    telegram_msgs = [m for _, m, _ in out["sent"]]
    assert len(telegram_msgs) == 1, \
        f"summary mode should send exactly one telegram message, got {len(telegram_msgs)}"
    msg = telegram_msgs[0]
    assert "🟢 BUY (2)" in msg
    assert "🔴 SELL (1)" in msg
    assert "🟡 HOLD (3)" in msg


def test_unresolvable_tickers_dont_count_toward_threshold():
    """If 3 of 8 raw entries fail to resolve, the 5 resolved should run as
    full reports, not summary. Otherwise users get summarized for nothing."""
    raw = ["A", "B", "C", "D", "E", "BOGUS1", "BOGUS2", "BOGUS3"]
    decisions = {t: "BUY" for t in ("A", "B", "C", "D", "E")}

    def _resolver(raw_in):
        if raw_in.startswith("BOGUS"):
            return ("", "no match")
        return (raw_in, "ok")

    prefs = {
        "daily_schedule_enabled": True,
        "telegram_chat_id": "111",
        "tickers": raw,
        "selected_analysts": ["market"],
    }
    full_calls: list[str] = []
    summary_calls: list[list[dict]] = []
    sent: list[str] = []

    with patch.object(scheduler, "SUMMARY_THRESHOLD", 5), \
         patch.object(scheduler, "CONCURRENCY", 2), \
         patch.object(scheduler, "_run_worker",
                      side_effect=_fake_worker_factory(decisions)), \
         patch.object(scheduler.ticker_resolver, "resolve_ticker",
                      side_effect=_resolver), \
         patch.object(scheduler.notify, "send_telegram",
                      side_effect=lambda c, m, **kw: (sent.append(m), (True, "ok"))[1]), \
         patch.object(scheduler, "_push_full_report",
                      side_effect=lambda c, s, t, d, dec: full_calls.append(t)), \
         patch.object(scheduler, "_push_summary",
                      side_effect=lambda c, td, r, **kw: summary_calls.append(list(r))):
        scheduler._process_user("slug", prefs, dry_run=False)

    assert sorted(full_calls) == ["A", "B", "C", "D", "E"]
    assert summary_calls == [], \
        "5 resolved tickers (8 raw) should be full mode, not summary"


# ───────────────────────────── concurrency ─────────────────────────────────

def test_concurrency_processes_each_ticker_exactly_once():
    """Smoke test: with CONCURRENCY=4 and 12 tickers, each ticker hits
    _run_worker exactly once. Catches obvious dispatch bugs in the
    ThreadPoolExecutor wiring."""
    tickers = [f"T{i}" for i in range(12)]
    decisions = {t: "HOLD" for t in tickers}

    seen: list[str] = []
    lock_seen = []  # collected via thread-safe append

    def _fake_worker(slug, ticker, trade_date, prefs):
        seen.append(ticker)
        return {"ok": True, "decision": "HOLD"}

    prefs = {
        "daily_schedule_enabled": True,
        "telegram_chat_id": "111",
        "tickers": tickers,
        "selected_analysts": ["market"],
    }
    with patch.object(scheduler, "SUMMARY_THRESHOLD", 5), \
         patch.object(scheduler, "CONCURRENCY", 4), \
         patch.object(scheduler, "_run_worker", side_effect=_fake_worker), \
         patch.object(scheduler.ticker_resolver, "resolve_ticker",
                      side_effect=lambda r: (r, "ok")), \
         patch.object(scheduler.notify, "send_telegram",
                      side_effect=lambda c, m, **kw: (True, "ok")):
        scheduler._process_user("slug", prefs, dry_run=False)

    assert sorted(seen) == sorted(tickers), \
        f"every ticker must be dispatched once; got {seen}"


# ───────────────────────────── telegram failure logging ─────────────────────

def test_send_logs_failures(capsys):
    """Pinning behavior: when notify.send_telegram returns (False, detail),
    scheduler._send must log it. Without this, push failures look like
    success in journalctl."""
    with patch.object(scheduler.notify, "send_telegram",
                      return_value=(False, "HTTP 403: chat not found")):
        ok = scheduler._send("999", "hello")
    assert ok is False
    captured = capsys.readouterr().out
    assert "telegram send failed" in captured
    assert "999" in captured
    assert "HTTP 403" in captured
