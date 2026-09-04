import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
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


def test_lease_owner_mismatch_cannot_renew_release_or_complete(tmp_path):
    path = tmp_path / "state.db"
    owner_a = AutomationState(path)
    owner_b = AutomationState(path)

    assert owner_a.try_acquire_lease("analysis", "owner-a", NOW, 60)
    assert not owner_b.renew_lease("analysis", "owner-b", NOW + timedelta(seconds=30), 60)
    assert not owner_b.release_lease("analysis", "owner-b")
    assert not owner_b.complete_task_run(
        "analysis",
        "owner-b",
        ran_at=NOW,
        completed_at=NOW + timedelta(seconds=30),
    )
    assert owner_a.last_task_run("analysis") is None

    assert owner_a.renew_lease("analysis", "owner-a", NOW + timedelta(seconds=30), 60)
    assert owner_a.complete_task_run(
        "analysis",
        "owner-a",
        ran_at=NOW,
        completed_at=NOW + timedelta(seconds=30),
    )
    assert owner_a.last_task_run("analysis") == NOW
    assert owner_b.try_acquire_lease("analysis", "owner-b", NOW + timedelta(seconds=30), 60)


def test_expired_lease_owner_cannot_renew_or_complete_stale_run(tmp_path):
    path = tmp_path / "state.db"
    state = AutomationState(path)

    assert state.try_acquire_lease("analysis", "owner-a", NOW, 60)
    expired_at = NOW + timedelta(seconds=60)
    assert not state.renew_lease("analysis", "owner-a", expired_at, 60)
    assert not state.complete_task_run(
        "analysis",
        "owner-a",
        ran_at=NOW,
        completed_at=expired_at,
    )
    assert state.last_task_run("analysis") is None


def test_previous_owner_cannot_complete_after_expiry_takeover(tmp_path):
    path = tmp_path / "state.db"
    owner_a = AutomationState(path)
    owner_b = AutomationState(path)

    assert owner_a.try_acquire_lease("analysis", "owner-a", NOW, 60)
    takeover_time = NOW + timedelta(seconds=60)
    assert owner_b.try_acquire_lease("analysis", "owner-b", takeover_time, 60)

    assert not owner_a.complete_task_run(
        "analysis",
        "owner-a",
        ran_at=NOW,
        completed_at=takeover_time,
    )
    assert owner_a.last_task_run("analysis") is None


def test_only_lease_owner_can_release_active_lease(tmp_path):
    path = tmp_path / "state.db"
    owner_a = AutomationState(path)
    owner_b = AutomationState(path)

    assert owner_a.try_acquire_lease("positions", "owner-a", NOW, 60)
    assert not owner_b.release_lease("positions", "owner-b")
    assert owner_a.release_lease("positions", "owner-a")
    assert owner_b.try_acquire_lease("positions", "owner-b", NOW, 60)


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


def test_pending_equity_intent_before_submit_is_unresolved_after_reopen(tmp_path):
    path = tmp_path / "pending-equity.db"
    intent = OrderIntent("AAPL", "buy", Decimal("100.25"), Decimal("600.50"))
    with AutomationState(path) as state:
        state.record_order_intents("cycle-1", NOW, [intent])

    with AutomationState(path) as reopened:
        lookup = reopened.lookup_unresolved_order_intent(intent)

    assert lookup is not None
    assert lookup.client_order_id is None
    assert lookup.ambiguous

    with AutomationState(path) as reopened:
        reopened.update_order_intent("cycle-1", "AAPL", "pending", "later-client-id")

    with AutomationState(path) as reopened:
        lookup = reopened.lookup_unresolved_order_intent(intent)

    assert lookup is not None
    assert lookup.client_order_id == "later-client-id"
    assert not lookup.ambiguous


def test_pending_client_order_ids_survive_reopen_for_broker_reconciliation(tmp_path):
    path = tmp_path / "accepted-before-crash.db"
    equity = OrderIntent("AAPL", "buy", Decimal("100.25"), Decimal("600.50"))
    with AutomationState(path) as state:
        state.record_order_intents("cycle-1", NOW, [equity])
        state.update_order_intent("cycle-1", "AAPL", "pending", "equity-client-id")
        state.record_option_intent(
            "cycle-1", NOW, "AAPL261002P00300000", "AAPL", "sell_to_open",
            Decimal("1"), Decimal("3.10"), "option-client-id",
        )

    with AutomationState(path) as reopened:
        equity_lookup = reopened.lookup_unresolved_order_intent(equity)
        option_lookup = reopened.lookup_unresolved_option_intent(
            "AAPL261002P00300000", "sell_to_open", Decimal("1"), Decimal("3.10")
        )

    assert equity_lookup is not None
    assert equity_lookup.client_order_id == "equity-client-id"
    assert not equity_lookup.ambiguous
    assert option_lookup is not None
    assert option_lookup.client_order_id == "option-client-id"
    assert not option_lookup.ambiguous


def test_conflicting_unresolved_client_ids_are_ambiguous_at_state_boundary(tmp_path):
    intent = OrderIntent("AAPL", "buy", Decimal("100.25"), Decimal("600.50"))
    with AutomationState(tmp_path / "ambiguous.db") as state:
        state.record_order_intents("cycle-1", NOW, [intent])
        state.update_order_intent("cycle-1", "AAPL", "pending", "client-one")
        state.record_order_intents("cycle-2", NOW + timedelta(minutes=1), [intent])
        state.update_order_intent("cycle-2", "AAPL", "error", "client-two")

        lookup = state.lookup_unresolved_order_intent(intent)

    assert lookup is not None
    assert lookup.client_order_id is None
    assert lookup.ambiguous


def test_equity_lookup_is_ambiguous_when_matching_rows_mix_missing_and_client_id(tmp_path):
    intent = OrderIntent("AAPL", "buy", Decimal("100.25"), Decimal("600.50"))
    with AutomationState(tmp_path / "mixed-equity-ids.db") as state:
        state.record_order_intents("cycle-1", NOW, [intent])
        state.update_order_intent("cycle-1", "AAPL", "error", "client-one")
        state.record_order_intents("cycle-2", NOW + timedelta(minutes=1), [intent])

        lookup = state.lookup_unresolved_order_intent(intent)

        assert lookup is not None
        assert lookup.client_order_id is None
        assert lookup.ambiguous
        assert state.unresolved_client_order_id(intent) is None


def test_option_lookup_is_ambiguous_when_matching_rows_mix_missing_and_client_id(tmp_path):
    contract = "AAPL261002P00300000"
    with AutomationState(tmp_path / "mixed-option-ids.db") as state:
        state.record_option_intent(
            "cycle-1", NOW, contract, "AAPL", "sell_to_open",
            Decimal("1"), Decimal("3.10"), "client-one",
        )
        state.record_option_intent(
            "cycle-2", NOW + timedelta(minutes=1), contract, "AAPL", "sell_to_open",
            Decimal("1"), Decimal("3.10"), "temporary-client",
        )
        state._connection.execute(
            """
            UPDATE option_order_intents SET client_order_id = ''
            WHERE cycle_id = 'cycle-2' AND contract_symbol = ?
            """,
            (contract,),
        )
        state._connection.commit()

        lookup = state.lookup_unresolved_option_intent(
            contract, "sell_to_open", Decimal("1"), Decimal("3.10")
        )

        assert lookup is not None
        assert lookup.client_order_id is None
        assert lookup.ambiguous
        assert state.unresolved_option_client_order_id(
            contract, "sell_to_open", Decimal("1"), Decimal("3.10")
        ) is None


def test_conflicting_option_client_ids_are_ambiguous_and_legacy_lookup_returns_none(tmp_path):
    contract = "AAPL261002P00300000"
    with AutomationState(tmp_path / "conflicting-option-ids.db") as state:
        state.record_option_intent(
            "cycle-1", NOW, contract, "AAPL", "sell_to_open",
            Decimal("1"), Decimal("3.10"), "client-one",
        )
        state.update_option_intent("cycle-1", contract, "error")
        state.record_option_intent(
            "cycle-2", NOW + timedelta(minutes=1), contract, "AAPL", "sell_to_open",
            Decimal("1"), Decimal("3.10"), "client-two",
        )

        lookup = state.lookup_unresolved_option_intent(
            contract, "sell_to_open", Decimal("1"), Decimal("3.10")
        )

        assert lookup is not None
        assert lookup.client_order_id is None
        assert lookup.ambiguous
        assert state.unresolved_option_client_order_id(
            contract, "sell_to_open", Decimal("1"), Decimal("3.10")
        ) is None


@pytest.mark.parametrize("persisted_id", ["", "   "])
def test_blank_client_order_id_is_ambiguous_and_legacy_lookup_returns_none(
    tmp_path, persisted_id
):
    intent = OrderIntent("AAPL", "buy", Decimal("100.25"), Decimal("600.50"))
    with AutomationState(tmp_path / "blank-equity-id.db") as state:
        state.record_order_intents("cycle-1", NOW, [intent])
        state._connection.execute(
            "UPDATE order_intents SET client_order_id = ? WHERE cycle_id = 'cycle-1'",
            (persisted_id,),
        )
        state._connection.commit()

        lookup = state.lookup_unresolved_order_intent(intent)

        assert lookup is not None
        assert lookup.client_order_id is None
        assert lookup.ambiguous
        assert state.unresolved_client_order_id(intent) is None


def test_resolved_reused_client_id_retires_historical_pending_intents(tmp_path):
    equity = OrderIntent("AAPL", "buy", Decimal("100.25"), Decimal("600.50"))
    with AutomationState(tmp_path / "resolved-pending.db") as state:
        state.record_order_intents("cycle-1", NOW, [equity])
        state.update_order_intent("cycle-1", "AAPL", "pending", "equity-id")
        state.record_order_intents("cycle-2", NOW + timedelta(minutes=1), [equity])
        state.mark_order_intent_submitted("cycle-2", "AAPL", "equity-id")

        state.record_option_intent(
            "cycle-1", NOW, "AAPL261002P00300000", "AAPL", "sell_to_open",
            Decimal("1"), Decimal("3.10"), "option-id",
        )
        state.record_option_intent(
            "cycle-2", NOW + timedelta(minutes=1), "AAPL261002P00300000", "AAPL",
            "sell_to_open", Decimal("1"), Decimal("3.10"), "option-id",
        )
        state.update_option_intent(
            "cycle-2", "AAPL261002P00300000", "submitted", "option-id"
        )

        assert state.lookup_unresolved_order_intent(equity) is None
        assert state.lookup_unresolved_option_intent(
            "AAPL261002P00300000", "sell_to_open", Decimal("1"), Decimal("3.10")
        ) is None


def test_wheel_reservation_snapshot_survives_reopen_exactly(tmp_path):
    path = tmp_path / "reservations.db"
    with AutomationState(path) as state:
        state.record_wheel_reservations(
            "cycle-1",
            NOW,
            put_collateral={"AAPL": Decimal("30000.00"), "MSFT": Decimal("12500")},
            covered_shares={"NVDA": Decimal("100"), "AAPL": Decimal("200.0")},
        )

    with AutomationState(path) as reopened:
        snapshot = reopened.latest_wheel_reservations()

    assert snapshot is not None
    assert snapshot.cycle_id == "cycle-1"
    assert snapshot.captured_at == NOW
    assert snapshot.put_collateral == {
        "AAPL": Decimal("30000.00"),
        "MSFT": Decimal("12500"),
    }
    assert snapshot.covered_shares == {
        "AAPL": Decimal("200.0"),
        "NVDA": Decimal("100"),
    }


def test_empty_wheel_reservation_snapshot_is_distinct_from_no_snapshot(tmp_path):
    path = tmp_path / "empty-reservations.db"
    with AutomationState(path) as state:
        assert state.latest_wheel_reservations() is None
        state.record_wheel_reservations("cycle-empty", NOW, {}, {})

    with AutomationState(path) as reopened:
        snapshot = reopened.latest_wheel_reservations()

    assert snapshot is not None
    assert snapshot.cycle_id == "cycle-empty"
    assert snapshot.captured_at == NOW
    assert snapshot.put_collateral == {}
    assert snapshot.covered_shares == {}


def test_same_key_wheel_reservation_snapshot_is_replaced_completely(tmp_path):
    with AutomationState(tmp_path / "replace-reservations.db") as state:
        state.record_wheel_reservations(
            "cycle-1", NOW, {"AAPL": Decimal("30000")}, {"NVDA": Decimal("100")}
        )
        state.record_wheel_reservations(
            "cycle-1", NOW, {"MSFT": Decimal("25000")}, {}
        )

        snapshot = state.latest_wheel_reservations()

    assert snapshot is not None
    assert snapshot.put_collateral == {"MSFT": Decimal("25000")}
    assert snapshot.covered_shares == {}


def test_invalid_same_key_reservation_replacement_preserves_prior_snapshot(tmp_path):
    with AutomationState(tmp_path / "invalid-replacement.db") as state:
        state.record_wheel_reservations(
            "cycle-1", NOW, {"AAPL": Decimal("30000")}, {"NVDA": Decimal("100")}
        )

        with pytest.raises(ValueError, match="wheel reservation"):
            state.record_wheel_reservations(
                "cycle-1", NOW, {"MSFT": Decimal("NaN")}, {}
            )
        snapshot = state.latest_wheel_reservations()

    assert snapshot is not None
    assert snapshot.put_collateral == {"AAPL": Decimal("30000")}
    assert snapshot.covered_shares == {"NVDA": Decimal("100")}


@pytest.mark.parametrize(
    "put_collateral, covered_shares",
    [
        ({"AAPL": Decimal("-0.01")}, {}),
        ({"AAPL": Decimal("NaN")}, {}),
        ({}, {"AAPL": Decimal("-1")}),
        ({}, {"AAPL": Decimal("Infinity")}),
    ],
)
def test_invalid_wheel_reservation_does_not_partially_record_snapshot(
    tmp_path, put_collateral, covered_shares
):
    with AutomationState(tmp_path / "invalid-reservations.db") as state:
        with pytest.raises(ValueError, match="wheel reservation"):
            state.record_wheel_reservations(
                "cycle-invalid", NOW, put_collateral, covered_shares
            )
        assert state.latest_wheel_reservations() is None


def test_option_intent_round_trip_and_retry_identity(tmp_path):
    with AutomationState(tmp_path / "state.db") as state:
        state.record_option_intent(
            "cycle", NOW, "AAPL261002P00300000", "AAPL", "sell_to_open",
            Decimal("1"), Decimal("3.10"), "wheel-id",
        )
        state.update_option_intent("cycle", "AAPL261002P00300000", "error", "wheel-id")

        assert state.unresolved_option_client_order_id(
            "AAPL261002P00300000", "sell_to_open", Decimal("1"), Decimal("3.10")
        ) == "wheel-id"


def test_daily_option_entry_marker_is_durable(tmp_path):
    path = tmp_path / "state.db"
    with AutomationState(path) as state:
        assert state.last_option_entry_date() is None
        state.mark_option_entry_date(date(2026, 9, 4))

    with AutomationState(path) as state:
        assert state.last_option_entry_date() == date(2026, 9, 4)


def test_disappearing_short_option_requires_two_stable_settlement_snapshots(tmp_path):
    with AutomationState(tmp_path / "state.db") as state:
        state.observe_wheel_phase("AAPL", "short_put", "put-contract", NOW)
        state.observe_wheel_phase(
            "AAPL", "empty", "cash=70000|shares=0", NOW + timedelta(minutes=15)
        )
        assert state.wheel_phase("AAPL") == "settling"

        state.observe_wheel_phase(
            "AAPL", "empty", "cash=70000|shares=0", NOW + timedelta(minutes=30)
        )
        assert state.wheel_phase("AAPL") == "put_ready"


def test_settlement_changed_or_too_soon_snapshot_resets_stability(tmp_path):
    with AutomationState(tmp_path / "state.db") as state:
        state.observe_wheel_phase("AAPL", "short_call", "call-contract", NOW)
        state.observe_wheel_phase("AAPL", "empty", "cash=1|shares=0", NOW)
        state.observe_wheel_phase(
            "AAPL", "empty", "cash=1|shares=0", NOW + timedelta(minutes=14)
        )
        state.observe_wheel_phase(
            "AAPL", "empty", "cash=1|shares=0", NOW + timedelta(minutes=15)
        )
        assert state.wheel_phase("AAPL") == "settling"

        state.observe_wheel_phase(
            "AAPL", "empty", "cash=2|shares=0", NOW + timedelta(minutes=30)
        )
        assert state.wheel_phase("AAPL") == "settling"
        state.observe_wheel_phase(
            "AAPL", "empty", "cash=2|shares=0", NOW + timedelta(minutes=45)
        )
        assert state.wheel_phase("AAPL") == "put_ready"


def test_long_shares_phase_replaces_short_option_immediately(tmp_path):
    with AutomationState(tmp_path / "state.db") as state:
        state.observe_wheel_phase("AAPL", "short_put", "put-contract", NOW)
        state.observe_wheel_phase(
            "AAPL", "long_shares", "cash=1|shares=100", NOW + timedelta(minutes=1)
        )
        assert state.wheel_phase("AAPL") == "long_shares"


@pytest.mark.parametrize("status", ["", "unknown", "pending; DROP TABLE option_order_intents"])
def test_option_intent_status_validation_fails_closed(tmp_path, status):
    with (
        AutomationState(tmp_path / "state.db") as state,
        pytest.raises(ValueError, match="option intent status"),
    ):
        state.update_option_intent("cycle", "AAPL261002P00300000", status, "wheel-id")


@pytest.mark.parametrize(
    "quantity, limit_price",
    [(Decimal("0"), Decimal("3.10")), (Decimal("1"), Decimal("0"))],
)
def test_option_intent_rejects_nonpositive_trade_values(tmp_path, quantity, limit_price):
    with AutomationState(tmp_path / "state.db") as state, pytest.raises(ValueError):
        state.record_option_intent(
            "cycle", NOW, "AAPL261002P00300000", "AAPL", "sell_to_open",
            quantity, limit_price, "wheel-id",
        )


def _acquire_lease_with_naive_now(state):
    state.try_acquire_lease("analysis", "owner-a", NOW, 900)
    return state.try_acquire_lease("analysis", "owner-b", NAIVE_NOW, 900)


def _load_fresh_decision_with_naive_now(state):
    state.save_decision("AAPL", "Buy", NOW, "2026-08-11", "/reports/aapl.md")
    return state.fresh_decisions(("AAPL",), NAIVE_NOW, 120)


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
        pytest.param(
            _load_fresh_decision_with_naive_now,
            id="fresh-decisions",
        ),
        pytest.param(
            lambda state: state.fresh_decisions((), NAIVE_NOW, 120),
            id="fresh-decisions-empty",
        ),
    ],
)
def test_timestamp_boundaries_reject_naive_datetimes(tmp_path, operation):
    with (
        AutomationState(tmp_path / "state.db") as state,
        pytest.raises(ValueError, match="timezone-aware"),
    ):
        operation(state)
