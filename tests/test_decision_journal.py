from datetime import date, datetime, timezone

import pytest

from tradingagents.research_platform.agent_contracts import (
    TradeDirection,
    TradeHorizon,
    TradeSignal,
)
from tradingagents.research_platform.data_contracts import DataProvenance, PriceBar
from tradingagents.research_platform.decision_journal import (
    DecisionJournalStatus,
    JsonDecisionJournal,
    build_journal_views,
    create_journal_entry,
    review_journal_entry,
)


def _bar(day: date, close: float, *, available_on: date | None = None) -> PriceBar:
    return PriceBar(
        symbol="NVDA",
        date=day,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=100,
        currency="USD",
        provenance=DataProvenance(
            provider="fixture",
            as_of_date=available_on or day,
            retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    )


def _signal(direction: TradeDirection = TradeDirection.BUY) -> TradeSignal:
    return TradeSignal(
        symbol="NVDA",
        as_of_date=date(2026, 1, 5),
        direction=direction,
        horizon=TradeHorizon.MEDIUM,
        confidence=0.7,
        rationale="Fixture decision.",
        proposed_position_pct=0.05,
        invalidation_triggers=["Thesis invalidated."],
    )


def test_journal_snapshots_signal_and_records_a_local_price_review(tmp_path):
    entry = create_journal_entry(
        symbol="nvda",
        research_run_id="run-1",
        signal=_signal(),
        review_due_date=date(2026, 1, 10),
        price_bars=[_bar(date(2026, 1, 3), 95), _bar(date(2026, 1, 5), 100)],
        recorded_at=datetime(2026, 1, 5, 12, tzinfo=timezone.utc),
    )
    journal = JsonDecisionJournal(tmp_path)
    journal.add_entry(entry)

    reviewed = review_journal_entry(
        entry,
        reviewed_on=date(2026, 1, 12),
        price_bars=[_bar(date(2026, 1, 5), 100), _bar(date(2026, 1, 12), 110)],
        note="Thesis playing out.",
        recorded_at=datetime(2026, 1, 12, 12, tzinfo=timezone.utc),
    )
    journal.replace_entry(reviewed)

    stored = journal.get_entry(entry.entry_id)
    assert stored is not None
    assert journal.find_for_run("NVDA", "run-1") == stored
    assert stored.symbol == "NVDA"
    assert stored.entry_price == 100
    assert stored.review is not None
    assert stored.review.review_price == 110
    assert stored.review.market_return_pct == pytest.approx(0.1)
    assert stored.review.directional_return_pct == pytest.approx(0.1)
    assert stored.review.note == "Thesis playing out."


def test_journal_respects_price_availability_and_marks_due_entries():
    entry = create_journal_entry(
        symbol="NVDA",
        research_run_id="run-2",
        signal=_signal(TradeDirection.SELL),
        review_due_date=date(2026, 1, 8),
        price_bars=[
            _bar(date(2026, 1, 5), 100),
            _bar(date(2026, 1, 6), 120, available_on=date(2026, 1, 9)),
        ],
    )

    views = build_journal_views(
        [entry],
        price_bars=[
            _bar(date(2026, 1, 5), 100),
            _bar(date(2026, 1, 6), 120, available_on=date(2026, 1, 9)),
        ],
        as_of_date=date(2026, 1, 8),
    )

    assert views[0].status == DecisionJournalStatus.DUE
    assert views[0].latest_available_price == 100
    assert views[0].market_return_pct == 0
    assert views[0].directional_return_pct == 0


def test_journal_rejects_price_less_decisions_and_duplicate_reviews():
    with pytest.raises(ValueError, match="no locally available price"):
        create_journal_entry(
            symbol="NVDA",
            research_run_id="run-3",
            signal=_signal(),
            review_due_date=date(2026, 1, 8),
            price_bars=[],
        )

    entry = create_journal_entry(
        symbol="NVDA",
        research_run_id="run-3",
        signal=_signal(),
        review_due_date=date(2026, 1, 8),
        price_bars=[_bar(date(2026, 1, 5), 100)],
    )
    reviewed = review_journal_entry(
        entry,
        reviewed_on=date(2026, 1, 8),
        price_bars=[_bar(date(2026, 1, 8), 105)],
    )
    with pytest.raises(ValueError, match="already been reviewed"):
        review_journal_entry(
            reviewed,
            reviewed_on=date(2026, 1, 9),
            price_bars=[_bar(date(2026, 1, 9), 110)],
        )
