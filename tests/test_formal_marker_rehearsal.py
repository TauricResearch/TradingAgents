from __future__ import annotations

import copy
import json

import pytest

from tradingagents.formal_marker_rehearsal import (
    FormalMarkerRehearsalError,
    verify_formal_marker_rehearsal,
)
from tradingagents.outcome_semantics import outcome_semantics_id
from tradingagents.paper_trading import advance_mark
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
)

RUN_ID = "global-event-v2-confirmatory-001"
BUILD_ID = "build_" + "a" * 24
SESSION_DATE = "2026-08-06"
PREVIOUS_DATE = "2026-08-05"
DECISION_DATE = "2026-08-05"


class _MarkerFixtureStore:
    def __init__(self) -> None:
        protocol = GLOBAL_EVENT_V2_PROTOCOL
        tickers = list(protocol["universe"]["symbols"])
        benchmark = protocol["portfolio"]["benchmark"]
        self.config = {
            "engine": "formal-global-v2",
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "tickers": tickers,
            "benchmark": benchmark,
            "cost_bps": protocol["portfolio"]["trading_cost_bps"],
            "slippage_bps": protocol["portfolio"]["slippage_bps"],
            "annual_borrow_bps": 0.0,
            "outcome_semantics_id": outcome_semantics_id(),
        }
        previous_opens = dict.fromkeys(tickers, 100.0)
        current_opens = dict.fromkeys(tickers, 101.0)
        previous_target = {
            "decision_date": "2026-08-04",
            "weights": dict.fromkeys(tickers, 1.0 / len(tickers)),
        }
        current_target = {
            "decision_date": DECISION_DATE,
            "weights": dict.fromkeys(tickers, 1.0 / len(tickers)),
        }
        previous = advance_mark(
            previous=None,
            session_date=PREVIOUS_DATE,
            captured_utc=1_000.0,
            opens=previous_opens,
            benchmark_open=400.0,
            target=previous_target,
            trading_cost_bps=self.config["cost_bps"],
            slippage_bps=self.config["slippage_bps"],
            annual_borrow_bps=0.0,
        )
        asset_returns = dict.fromkeys(tickers, 0.01)
        current = advance_mark(
            previous=previous,
            session_date=SESSION_DATE,
            captured_utc=2_000.0,
            opens=current_opens,
            benchmark_open=404.0,
            target=current_target,
            trading_cost_bps=self.config["cost_bps"],
            slippage_bps=self.config["slippage_bps"],
            annual_borrow_bps=0.0,
            asset_returns=asset_returns,
            benchmark_period_return_override=0.01,
            cash_period_return=0.0001,
        )
        self.current_target = current_target
        self.previous = previous
        self.current = current
        self.strategy_pairs = {
            strategy: (copy.deepcopy(current), copy.deepcopy(previous))
            for strategy in protocol["strategies"]
        }
        symbols = [*tickers, benchmark]
        self.vector = {
            "return_vector_id": "return_vector_" + "b" * 24,
            "from_session": PREVIOUS_DATE,
            "to_session": SESSION_DATE,
            "components": {
                symbol: {"open_return": 0.01} for symbol in symbols
            },
            "cash_component": {"open_return": 0.0001},
        }
        self.batch = {
            "paper_build_id": BUILD_ID,
            "capture_batch_id": "capture_batch_" + "c" * 24,
            "return_vector_id": self.vector["return_vector_id"],
        }

    @staticmethod
    def _row(mark: dict) -> dict:
        row = copy.deepcopy(mark)
        row["weights_json"] = json.dumps(row.pop("weights"), sort_keys=True)
        row["opens_json"] = json.dumps(row.pop("opens"), sort_keys=True)
        return row

    def _rows(self, sql: str, params: dict) -> list[dict]:
        if "JOIN paper_price_capture_batches" in sql:
            return [{"session_date": SESSION_DATE}]
        is_previous = "session_date<:session_date" in sql
        if "paper_strategy_marks" in sql:
            pair = self.strategy_pairs[params["strategy_id"]]
            return [self._row(pair[1] if is_previous else pair[0])]
        if "paper_marks" in sql:
            return [self._row(self.previous if is_previous else self.current)]
        raise AssertionError(sql)

    def run_config(self, run_id: str) -> dict:
        assert run_id == RUN_ID
        return copy.deepcopy(self.config)

    def price_capture_batch(self, run_id: str, session_date: str) -> dict:
        assert (run_id, session_date) == (RUN_ID, SESSION_DATE)
        return copy.deepcopy(self.batch)

    def return_vector_for_session(
        self, run_id: str, session_date: str, symbols: list[str]
    ) -> dict:
        assert (run_id, session_date) == (RUN_ID, SESSION_DATE)
        assert symbols == [*self.config["tickers"], self.config["benchmark"]]
        return copy.deepcopy(self.vector)

    def target_for_entry(self, run_id: str, session_date: str) -> dict:
        assert (run_id, session_date) == (RUN_ID, SESSION_DATE)
        return copy.deepcopy(self.current_target)

    def formal_strategies(self, run_id: str) -> list[str]:
        assert run_id == RUN_ID
        return sorted(GLOBAL_EVENT_V2_PROTOCOL["strategies"])

    def strategy_target_for_entry(
        self, run_id: str, strategy_id: str, session_date: str
    ) -> dict:
        assert run_id == RUN_ID
        assert strategy_id in GLOBAL_EVENT_V2_PROTOCOL["strategies"]
        assert session_date == SESSION_DATE
        return copy.deepcopy(self.current_target)


@pytest.mark.unit
def test_marker_rehearsal_replays_champion_and_all_frozen_strategies():
    receipt = verify_formal_marker_rehearsal(
        _MarkerFixtureStore(),
        run_id=RUN_ID,
        marker_build_id=BUILD_ID,
    )

    assert receipt["ok"] is True
    assert receipt["marks_replayed"] == 9
    assert receipt["strategies_replayed"] == 8
    assert receipt["external_calls"] == 0
    assert [row["strategy_id"] for row in receipt["strategy_mark_ids"]] == list(
        GLOBAL_EVENT_V2_PROTOCOL["strategies"]
    )
    assert receipt["marker_replay_id"].startswith("marker_replay_")


@pytest.mark.unit
def test_marker_rehearsal_rejects_stored_output_drift():
    store = _MarkerFixtureStore()
    store.strategy_pairs["market_only"][0]["nav"] += 0.001

    with pytest.raises(
        FormalMarkerRehearsalError,
        match="differs from deterministic replay",
    ):
        verify_formal_marker_rehearsal(
            store,
            run_id=RUN_ID,
            marker_build_id=BUILD_ID,
            session_date=SESSION_DATE,
        )


@pytest.mark.unit
def test_marker_rehearsal_rejects_foreign_marker_build():
    with pytest.raises(
        FormalMarkerRehearsalError,
        match="same-build return vector",
    ):
        verify_formal_marker_rehearsal(
            _MarkerFixtureStore(),
            run_id=RUN_ID,
            marker_build_id="build_" + "0" * 24,
            session_date=SESSION_DATE,
        )
