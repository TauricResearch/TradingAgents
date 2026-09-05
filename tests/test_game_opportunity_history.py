from datetime import date, datetime, timezone

from tradingagents.research_platform.artifact_store import JsonArtifactStore
from tradingagents.research_platform.game_opportunity import (
    GameOpportunityFactor,
    GameOpportunityFactorStatus,
    GameOpportunityLevel,
    GameOpportunitySnapshot,
)
from tradingagents.research_platform.game_opportunity_history import (
    GameOpportunityEventType,
    JsonGameOpportunityHistory,
    build_game_opportunity_history_view,
    compare_game_opportunities,
    record_game_opportunity_board,
)


def _snapshot(
    as_of: date,
    *,
    score: int = 7,
    level: GameOpportunityLevel = GameOpportunityLevel.WATCH,
    approval_score: int = 2,
    approval_count: int = 1,
) -> GameOpportunitySnapshot:
    return GameOpportunitySnapshot(
        symbol="002602",
        company_name="Century Huatong",
        as_of_date=as_of,
        available=True,
        level=level,
        score=score,
        max_score=12,
        factors=[
            GameOpportunityFactor(
                factor_id="approvals",
                label="Official approvals",
                available=True,
                score=approval_score,
                max_score=3,
                status=(
                    GameOpportunityFactorStatus.SUPPORTIVE
                    if approval_score == 3
                    else GameOpportunityFactorStatus.MIXED
                ),
                detail="Fixture approvals.",
                observed_as_of=as_of,
                metrics={"approvals_365d": approval_count},
            )
        ],
    )


def test_history_overwrites_same_day_and_keeps_newest_first(tmp_path):
    history = JsonGameOpportunityHistory(tmp_path)
    first = _snapshot(date(2026, 7, 11), score=6)
    current = _snapshot(date(2026, 7, 12), score=7)
    corrected = _snapshot(date(2026, 7, 12), score=8)

    history.save(first)
    history.save(current)
    history.save(corrected)

    records = history.list("002602")
    assert [(item.as_of_date, item.score) for item in records] == [
        (date(2026, 7, 12), 8),
        (date(2026, 7, 11), 6),
    ]


def test_first_observation_creates_only_a_baseline_event():
    events = compare_game_opportunities(None, _snapshot(date(2026, 7, 12)))

    assert [item.event_type for item in events] == [
        GameOpportunityEventType.BASELINE_CREATED
    ]


def test_level_score_factor_and_new_approval_changes_are_explicit():
    previous = _snapshot(date(2026, 7, 11), score=7, approval_score=2, approval_count=1)
    current = _snapshot(
        date(2026, 7, 12),
        score=9,
        level=GameOpportunityLevel.HIGH_ATTENTION,
        approval_score=3,
        approval_count=2,
    )

    events = compare_game_opportunities(previous, current)

    assert {item.event_type for item in events} == {
        GameOpportunityEventType.LEVEL_CHANGED,
        GameOpportunityEventType.SCORE_CHANGED,
        GameOpportunityEventType.FACTOR_CHANGED,
        GameOpportunityEventType.NEW_APPROVAL,
    }
    assert len({item.event_id for item in events}) == len(events)


def test_new_approval_is_detected_even_when_factor_is_already_at_maximum():
    previous = _snapshot(date(2026, 7, 11), score=8, approval_score=3, approval_count=2)
    current = _snapshot(date(2026, 7, 12), score=8, approval_score=3, approval_count=3)

    events = compare_game_opportunities(previous, current)

    assert [item.event_type for item in events] == [GameOpportunityEventType.NEW_APPROVAL]


def test_history_view_compares_the_latest_two_snapshots(tmp_path):
    history = JsonGameOpportunityHistory(tmp_path)
    history.save(_snapshot(date(2026, 7, 11), score=7))
    history.save(
        _snapshot(
            date(2026, 7, 12),
            score=9,
            level=GameOpportunityLevel.HIGH_ATTENTION,
        )
    )

    view = build_game_opportunity_history_view(history, "002602")

    assert [item.as_of_date for item in view.snapshots] == [
        date(2026, 7, 12),
        date(2026, 7, 11),
    ]
    assert {item.event_type for item in view.latest_events} >= {
        GameOpportunityEventType.LEVEL_CHANGED,
        GameOpportunityEventType.SCORE_CHANGED,
    }

def test_recording_same_day_is_idempotent(tmp_path, monkeypatch):
    snapshot = _snapshot(date(2026, 7, 12))
    monkeypatch.setattr(
        "tradingagents.research_platform.game_opportunity_history.build_game_opportunity_board",
        lambda store, as_of_date=None: [snapshot],
    )
    store = JsonArtifactStore(tmp_path)
    recorded_at = datetime(2026, 7, 12, 8, tzinfo=timezone.utc)

    first = record_game_opportunity_board(
        store, as_of_date=date(2026, 7, 12), recorded_at=recorded_at
    )
    second = record_game_opportunity_board(
        store, as_of_date=date(2026, 7, 12), recorded_at=recorded_at
    )

    assert first.event_count == 1
    assert second.event_count == 0
    assert len(JsonGameOpportunityHistory(tmp_path).list("002602")) == 1
