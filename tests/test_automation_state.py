import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tradingagents.allocation import OrderIntent
from tradingagents.automation_state import AutomationState

NOW = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)
NAIVE_NOW = datetime(2026, 8, 11, 14, 0)


def test_cursor_decisions_and_freshness_survive_reopen(tmp_path):
    path = tmp_path / "nested" / "state.db"
    state = AutomationState(path)
    state.advance_batch_index(1)
    state.save_decision("AAPL", "Buy", NOW, "2026-08-11", "/reports/aapl.md")
    state.close()

    with AutomationState(path) as reopened:
        assert reopened.get_batch_index() == 1
        fresh = reopened.fresh_decisions(("AAPL",), NOW + timedelta(minutes=30), 120)
        assert fresh["AAPL"].rating == "Buy"
        assert fresh["AAPL"].analyzed_at == NOW
        assert fresh["AAPL"].analyzed_at.utcoffset() == timedelta(0)
        assert reopened.fresh_decisions(("AAPL",), NOW + timedelta(minutes=120), 120)
        assert reopened.fresh_decisions(("AAPL",), NOW + timedelta(minutes=121), 120) == {}


def test_cycle_lease_allows_only_one_owner_until_expiry(tmp_path):
    path = tmp_path / "state.db"
    owner_a = AutomationState(path)
    owner_b = AutomationState(path)

    assert owner_a.try_acquire_lease("analysis", "owner-a", NOW, 900)
    assert not owner_b.try_acquire_lease("analysis", "owner-b", NOW, 900)
    assert owner_b.try_acquire_lease("analysis", "owner-b", NOW + timedelta(seconds=900), 900)


def test_position_snapshot_preserves_decimal_strings_and_sorted_json(tmp_path):
    path = tmp_path / "state.db"
    state = AutomationState(path)
    state.record_position_snapshot(
        NOW,
        Decimal("10000.01"),
        {"MSFT": Decimal("2.50"), "AAPL": Decimal("500.00")},
    )
    state.close()

    with AutomationState(path) as reopened:
        snapshot = reopened.latest_position_snapshot()

    assert snapshot is not None
    assert snapshot.captured_at == NOW
    assert snapshot.captured_at.utcoffset() == timedelta(0)
    assert snapshot.cash == Decimal("10000.01")
    assert snapshot.positions == {
        "AAPL": Decimal("500.00"),
        "MSFT": Decimal("2.50"),
    }
    with sqlite3.connect(path) as connection:
        cash, positions_json = connection.execute(
            "SELECT cash, positions_json FROM position_snapshots"
        ).fetchone()
    assert cash == "10000.01"
    assert positions_json == json.dumps({"AAPL": "500.00", "MSFT": "2.50"}, sort_keys=True)


def test_order_intents_and_task_times_are_persisted(tmp_path):
    path = tmp_path / "state.db"
    state = AutomationState(path)
    state.record_order_intents(
        "cycle-1",
        NOW,
        [OrderIntent("AAPL", "buy", Decimal("100.25"), Decimal("600.50"))],
    )
    assert state.order_intent_count("cycle-1") == 1
    state.update_order_intent("cycle-1", "AAPL", "submitted", "client-1")
    state.mark_task_run("positions", NOW)
    state.close()

    with AutomationState(path) as reopened:
        assert reopened.order_intent_count("cycle-1") == 1
        assert reopened.last_task_run("positions") == NOW
        assert reopened.last_task_run("positions").utcoffset() == timedelta(0)

    with sqlite3.connect(path) as connection:
        intent = connection.execute(
            """
            SELECT created_at, side, notional, target_notional, status, client_order_id
            FROM order_intents WHERE cycle_id = ? AND symbol = ?
            """,
            ("cycle-1", "AAPL"),
        ).fetchone()
    assert intent == (
        NOW.isoformat(),
        "buy",
        "100.25",
        "600.50",
        "submitted",
        "client-1",
    )


def _acquire_lease_with_naive_now(state):
    state.try_acquire_lease("analysis", "owner-a", NOW, 900)
    return state.try_acquire_lease("analysis", "owner-b", NAIVE_NOW, 900)


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda state: state.save_decision(
                "AAPL", "Buy", NAIVE_NOW, "2026-08-11", "/reports/aapl.md"
            ),
            id="decision",
        ),
        pytest.param(
            lambda state: state.record_position_snapshot(NAIVE_NOW, Decimal("1"), {}),
            id="position-snapshot",
        ),
        pytest.param(
            lambda state: state.record_order_intents(
                "cycle-1",
                NAIVE_NOW,
                [OrderIntent("AAPL", "buy", Decimal("1"), Decimal("1"))],
            ),
            id="order-intents",
        ),
        pytest.param(
            lambda state: state.mark_task_run("positions", NAIVE_NOW),
            id="task-run",
        ),
        pytest.param(
            _acquire_lease_with_naive_now,
            id="lease",
        ),
    ],
)
def test_timestamp_boundaries_reject_naive_datetimes(tmp_path, operation):
    with (
        AutomationState(tmp_path / "state.db") as state,
        pytest.raises(ValueError, match="timezone-aware"),
    ):
        operation(state)
