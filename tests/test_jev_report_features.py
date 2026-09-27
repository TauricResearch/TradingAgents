"""Jev report features for learning from settled decisions (docs/jev-use-cases.md, fit 5).

A backtest run leaves its decision log and each cell's saved state. These pin
how the two are joined, how Jev answers become columns, that the cache keeps
repeat runs from asking again, and that the command refuses before spending
anything when the run is too small to learn from.

A fake client stands in for the service: every Score answer puts most weight on
the top level when the document holds ``[up]`` and on the bottom level
otherwise, and every Noul says yes with 0.9 or 0.1 the same way.
"""

from __future__ import annotations

import json
import threading
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from tradingagents import report_features as rf
from tradingagents.decision_log import TradingMemoryLog
from tradingagents.outcome_model import NotEnoughData

# ---------------------------------------------------------------------------
# A fake Jev client
# ---------------------------------------------------------------------------


class FakeJev:
    def __init__(self):
        self.calls = []
        self._lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def system_one(self, state, questions):
        with self._lock:
            self.calls.append((state, tuple(questions)))
        text = next(v["text"] for k, v in state.items() if k != "instrument")
        up = "[up]" in text
        answers = {}
        for qid, q in questions.items():
            if isinstance(q, rf.Score):
                top = len(q.criteria) - 1
                level = top if up else 0
                probs = {str(i): 0.8 if i == level else 0.2 / top for i in range(top + 1)}
                answers[qid] = SimpleNamespace(type="score", probabilities=probs)
            else:
                answers[qid] = SimpleNamespace(type="noul", noul=0.9 if up else 0.1)
        return SimpleNamespace(model="jev-test", answers=answers)


# ---------------------------------------------------------------------------
# A backtest run on disk
# ---------------------------------------------------------------------------


def _decision(rating, text=""):
    return f"**Rating**: {rating}\n\n**Executive Summary**: {text}\n\n**Investment Thesis**: a thesis."


def _state(ticker, day, up, decision, analysts=("market", "sentiment", "news", "fundamentals")):
    mark = "[up]" if up else "[down]"
    state = {"company_of_interest": ticker, "trade_date": day, "final_trade_decision": decision,
             "investment_debate_state": {"history": f"Bull: strong demand {mark}\nBear: risks"},
             "risk_debate_state": {"history": f"Aggressive: go {mark}\nConservative: wait"}}
    for name in ("market", "sentiment", "news", "fundamentals"):
        state[f"{name}_report"] = f"The {name} report on {ticker} {mark}" if name in analysts else ""
    return state


def _write_run(run_dir, cells, analysts=("market", "sentiment", "news", "fundamentals")):
    """``cells`` holds (ticker, date, rating, alpha or None for pending, up, has_state)."""
    log = TradingMemoryLog({"memory_log_path": str(run_dir / "trading_memory.md")})
    updates = []
    for ticker, day, rating, alpha, up, has_state in cells:
        decision = _decision(rating)
        log.store_decision(ticker, day, decision)
        if has_state:
            path = rf.state_path(run_dir, ticker, day)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(_state(ticker, day, up, decision, analysts)), encoding="utf-8")
        if alpha is not None:
            updates.append({"ticker": ticker, "trade_date": day, "raw_return": alpha,
                            "alpha_return": alpha, "holding_days": 5, "reflection": "lesson",
                            "resolution_date": (date.fromisoformat(day) + timedelta(days=7)).isoformat()})
    log.batch_update_with_outcomes(updates)


def _grid(n_days=12, tickers=("NVDA", "AAPL", "MSFT", "AMD")):
    """A sweep where the reports' tone predicts the outcome and the rating does not."""
    cells = []
    for i in range(n_days):
        day = (date(2026, 1, 5) + timedelta(days=7 * i)).isoformat()
        for j, ticker in enumerate(tickers):
            up = (i + j) % 2 == 0
            wrong = (i * 4 + j) % 7 == 0  # a few outcomes go against the tone
            alpha = (0.02 if up != wrong else -0.02) + 0.001 * j
            cells.append((ticker, day, "Buy", alpha, up, True))
    return cells


@pytest.fixture
def jev_config(tmp_path):
    from tradingagents.dataflows.config import set_config
    set_config({"data_cache_dir": str(tmp_path / "cache"), "jev_model": "jev-test-pinned"})


# ---------------------------------------------------------------------------
# Documents and answers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_score_becomes_its_expected_level_and_spread_and_a_noul_its_probability():
    score = next(q for q in rf.QUESTIONS if q.id == "price_trend")
    noul = next(q for q in rf.QUESTIONS if q.id == "overbought")

    assert rf.encode(score, {"probabilities": {"0": 0.0, "1": 0.5, "2": 0.5}}) == {
        "price_trend": pytest.approx(1.5), "price_trend_sd": pytest.approx(0.5)}
    assert rf.encode(noul, {"noul": 0.3}) == {"overbought": 0.3}
    assert score.columns == ("price_trend", "price_trend_sd") and noul.columns == ("overbought",)


@pytest.mark.unit
def test_every_question_reads_a_known_document_through_its_own_state_key():
    for q in rf.QUESTIONS:
        doc = rf.DOCUMENTS[q.document]
        assert f"`{doc.key}`" in q.question.instructions, q.id
    assert len({q.id for q in rf.QUESTIONS}) == len(rf.QUESTIONS)


@pytest.mark.unit
def test_the_documents_are_the_reports_the_debates_and_the_decision_without_its_claim_check():
    decision = (_decision("Buy") + "\n\n**Claim Check**: 3 statements read...\n"
                "- Contradicted: \"x\"\n\n**Rating after claim check**: REVIEW (...)")
    state = _state("NVDA", "2026-01-05", True, decision, analysts=("market", "news"))

    texts = rf.document_texts(state)

    assert set(texts) == {"market", "news", "research_debate", "risk_debate", "decision"}
    assert "Claim Check" not in texts["decision"] and texts["decision"].startswith("**Rating**: Buy")
    assert rf.document_state("NVDA", "research_debate", "t") == {
        "instrument": {"ticker": "NVDA"},
        "debate": {"kind": rf.DOCUMENTS["research_debate"].title, "text": "t"}}


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_settled_decisions_are_joined_to_their_saved_state(tmp_path):
    _write_run(tmp_path, [
        ("NVDA", "2026-01-05", "Buy", 0.013, True, True),
        ("NVDA", "2026-01-12", "Sell", None, False, True),     # pending
        ("AAPL", "2026-01-05", "Hold", -0.004, False, False),  # no saved state
    ])

    loaded = rf.load_decisions(tmp_path / "trading_memory.md", tmp_path)

    assert (loaded.pending, loaded.no_state, loaded.unscorable) == (1, 1, 0)
    [d] = loaded.decisions
    assert (d.ticker, d.date, d.rating, d.pm_rating) == ("NVDA", "2026-01-05", "Buy", "Buy")
    assert d.alpha == pytest.approx(0.013) and d.resolved == "2026-01-12"
    assert "decision" in d.documents and "market" in d.documents
    assert "1 pending" in loaded.describe() and "1 settled without a saved state" in loaded.describe()


@pytest.mark.unit
def test_a_decision_sent_to_review_keeps_the_portfolio_managers_own_rating(tmp_path, jev_config):
    reviewed = (_decision("Overweight") + "\n\n**Claim Check**: ...\n\n"
                "**Rating after claim check**: REVIEW (the Portfolio Manager rated Overweight; ...)")
    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "trading_memory.md")})
    log.store_decision("NVDA", "2026-01-05", reviewed)
    log.batch_update_with_outcomes([{"ticker": "NVDA", "trade_date": "2026-01-05",
                                     "raw_return": 0.01, "alpha_return": 0.01, "holding_days": 5,
                                     "reflection": "r", "resolution_date": "2026-01-12"}])
    path = rf.state_path(tmp_path, "NVDA", "2026-01-05")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_state("NVDA", "2026-01-05", True, reviewed)), encoding="utf-8")

    [d] = rf.load_decisions(tmp_path / "trading_memory.md", tmp_path).decisions
    row = rf.extract_features(FakeJev(), [d]).rows[0]

    assert (d.rating, d.pm_rating) == ("REVIEW", "Overweight")
    assert (row["rating"], row["review"]) == (0.5, 1.0)


# ---------------------------------------------------------------------------
# Extraction and the cache
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_one_request_per_document_and_none_again_once_cached(tmp_path, jev_config):
    _write_run(tmp_path, _grid(n_days=2, tickers=("NVDA",)))
    decisions = rf.load_decisions(tmp_path / "trading_memory.md", tmp_path).decisions
    cache_path = tmp_path / "cache.json"

    client = FakeJev()
    first = rf.extract_features(client, decisions, cache=rf.AnswerCache(cache_path))
    assert first.requests == len(client.calls) == 2 * len(rf.DOCUMENTS)
    assert first.models == {"jev-test"}
    by_doc = {}
    for state, ids in client.calls:
        by_doc.setdefault(next(k for k in state if k != "instrument"), set()).update(ids)
    assert by_doc["debate"] == {"bull_bear_balance", "risk_debate_asymmetry"}

    again = FakeJev()
    second = rf.extract_features(again, decisions, cache=rf.AnswerCache(cache_path))
    assert again.calls == [] and second.requests == 0
    assert second.rows == first.rows

    up = first.rows[0]  # the first day's NVDA cell has an [up] tone
    assert up["price_trend"] == pytest.approx(0.8 * 4 + 0.05 * (0 + 1 + 2 + 3))
    assert up["overbought"] == 0.9 and first.rows[1]["overbought"] == 0.1


@pytest.mark.unit
def test_a_new_question_is_the_only_one_asked(tmp_path, jev_config):
    _write_run(tmp_path, _grid(n_days=2, tickers=("NVDA",)))
    decisions = rf.load_decisions(tmp_path / "trading_memory.md", tmp_path).decisions
    cache = rf.AnswerCache(tmp_path / "cache.json")
    rf.extract_features(FakeJev(), decisions, cache=cache)

    extra = rf.FeatureQuestion("guidance_raised", "news", rf._noul(
        "Does `report` say `instrument` raised its guidance?", true="Yes.", false="No."))
    client = FakeJev()
    result = rf.extract_features(client, decisions, (*rf.QUESTIONS, extra), cache=cache)

    assert [ids for _, ids in client.calls] == [("guidance_raised",)] * 2
    assert "guidance_raised" in result.rows[0]


@pytest.mark.unit
def test_a_missing_report_leaves_its_columns_out(tmp_path, jev_config):
    _write_run(tmp_path, _grid(n_days=1, tickers=("NVDA",)), analysts=("market",))
    decisions = rf.load_decisions(tmp_path / "trading_memory.md", tmp_path).decisions

    row = rf.extract_features(FakeJev(), decisions).rows[0]

    assert "price_trend" in row and "news_tone" not in row and "fundamentals_trend" not in row


@pytest.mark.unit
def test_answers_paid_for_before_a_failure_are_kept(tmp_path, jev_config):
    _write_run(tmp_path, _grid(n_days=1, tickers=("NVDA",)))
    decisions = rf.load_decisions(tmp_path / "trading_memory.md", tmp_path).decisions
    cache_path = tmp_path / "cache.json"

    class Failing(FakeJev):
        def system_one(self, state, questions):
            if "debate" in state:
                raise RuntimeError("service down")
            return super().system_one(state, questions)

    with pytest.raises(RuntimeError, match="service down"):
        rf.extract_features(Failing(), decisions, cache=rf.AnswerCache(cache_path))
    assert cache_path.exists() and json.loads(cache_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The whole run
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_learning_scores_the_reports_against_the_rating_and_writes_the_table(tmp_path, jev_config):
    _write_run(tmp_path, _grid())

    result = rf.learn_from_run(tmp_path, client=FakeJev())

    ev = result.evaluation
    assert ev.decisions == 48 and ev.dates == 12
    assert ev.model("rating + Jev features").holdout_loss < ev.model("rating").holdout_loss
    assert {q.id for q in ev.questions} == {q.id for q in rf.QUESTIONS}
    header = result.table_path.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header[:6] == ["ticker", "date", "resolved", "logged_rating", "pm_rating", "alpha"]
    assert {"rating", "review", "price_trend", "price_trend_sd", "overbought"} <= set(header)
    assert result.requests == 48 * len(rf.DOCUMENTS)


@pytest.mark.unit
def test_a_small_run_is_refused_before_any_jev_request(tmp_path, jev_config):
    _write_run(tmp_path, _grid(n_days=3))
    client = FakeJev()

    with pytest.raises(NotEnoughData, match="This run has 12 settled decisions"):
        rf.learn_from_run(tmp_path, client=client)
    assert client.calls == []


@pytest.mark.unit
def test_without_jev_learning_says_what_it_needs(tmp_path, jev_config):
    _write_run(tmp_path, _grid())  # conftest removes TYPESAFE_API_KEY
    with pytest.raises(rf.JevUnavailable, match="TYPESAFE_API_KEY"):
        rf.learn_from_run(tmp_path)


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_learn_command_prints_the_evaluation(tmp_path, monkeypatch, jev_config):
    import cli.main as m

    run_dir = tmp_path / "backtest" / "sweep1"
    _write_run(run_dir, _grid())
    monkeypatch.setitem(m.DEFAULT_CONFIG, "results_dir", str(tmp_path))
    monkeypatch.setattr(rf, "jev_client", lambda: FakeJev())

    result = CliRunner().invoke(m.app, ["learn", "sweep1"])

    assert result.exit_code == 0, result.output
    assert "rating + Jev features" in result.output
    assert "Jev requests sent: 336" in result.output
    assert "report_features.csv" in result.output


@pytest.mark.unit
@pytest.mark.parametrize("run_id, expected", [
    ("missing", "No backtest log"),
    ("../escape", "not allowed"),
])
def test_the_learn_command_refuses_a_run_it_cannot_read(tmp_path, monkeypatch, run_id, expected):
    import cli.main as m

    monkeypatch.setitem(m.DEFAULT_CONFIG, "results_dir", str(tmp_path))
    result = CliRunner().invoke(m.app, ["learn", run_id])

    assert result.exit_code == 1
    assert expected in result.output


@pytest.mark.unit
def test_the_learn_command_says_how_many_decisions_it_needs(tmp_path, monkeypatch, jev_config):
    import cli.main as m

    _write_run(tmp_path / "backtest" / "small", _grid(n_days=2))
    monkeypatch.setitem(m.DEFAULT_CONFIG, "results_dir", str(tmp_path))

    result = CliRunner().invoke(m.app, ["learn", "small"])

    assert result.exit_code == 1
    assert "at least 40 settled decisions" in result.output
