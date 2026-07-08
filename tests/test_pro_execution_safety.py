"""Kill switch, circuit breaker, and the hash-chained audit log."""

import json
from datetime import date

import pytest

from tradingagents.contracts import RiskLimits
from tradingagents.pro.execution import AuditLog, CircuitBreaker, KillSwitch


class TestKillSwitch:
    def test_engage_latches_and_reset_requires_operator(self):
        switch = KillSwitch()
        assert not switch.engaged
        switch.engage("manual halt: fat-finger risk")
        assert switch.engaged and "fat-finger" in switch.reason
        with pytest.raises(ValueError):
            switch.reset("")
        switch.reset(operator="ajay")
        assert not switch.engaged

    def test_kill_file_engages_from_outside_the_process(self, tmp_path):
        kill_file = tmp_path / "KILL"
        switch = KillSwitch(path=kill_file)
        assert not switch.engaged
        kill_file.write_text("halt")  # operator: touch the file
        assert switch.engaged
        switch.reset(operator="ajay")
        assert not kill_file.exists() and not switch.engaged

    def test_engage_writes_the_kill_file(self, tmp_path):
        kill_file = tmp_path / "KILL"
        KillSwitch(path=kill_file).engage("breaker escalation")
        assert "breaker escalation" in kill_file.read_text()


class TestCircuitBreaker:
    LIMITS = RiskLimits(circuit_breaker_consecutive_losses=3, max_daily_loss_pct=3.0)

    def test_trips_on_consecutive_losses(self):
        breaker = CircuitBreaker(self.LIMITS, equity_base=100_000)
        for _ in range(2):
            breaker.record_trade_result(-100.0)
        assert not breaker.check().tripped
        breaker.record_trade_result(-100.0)
        state = breaker.check()
        assert state.tripped and "3 consecutive losses" in state.reason

    def test_win_resets_the_streak(self):
        breaker = CircuitBreaker(self.LIMITS, equity_base=100_000)
        breaker.record_trade_result(-100.0)
        breaker.record_trade_result(-100.0)
        breaker.record_trade_result(50.0)
        breaker.record_trade_result(-100.0)
        assert not breaker.check().tripped
        assert breaker.consecutive_losses == 1

    def test_trips_on_daily_loss_and_resets_next_day(self):
        breaker = CircuitBreaker(self.LIMITS, equity_base=100_000)
        d1, d2 = date(2026, 7, 7), date(2026, 7, 8)
        breaker.record_trade_result(2000.0, today=d1)  # win keeps streak at 0
        breaker.record_trade_result(-5100.0, today=d1)  # net -3100 > 3% of 100k
        assert breaker.check(today=d1).tripped
        # next trading day: daily counter resets, breaker un-trips
        assert not breaker.check(today=d2).tripped
        assert breaker.daily_pnl == 0.0

    def test_consecutive_loss_trip_survives_day_rollover(self):
        breaker = CircuitBreaker(self.LIMITS, equity_base=100_000)
        d1, d2 = date(2026, 7, 7), date(2026, 7, 8)
        for _ in range(3):
            breaker.record_trade_result(-10.0, today=d1)
        assert breaker.check(today=d1).tripped
        assert breaker.check(today=d2).tripped  # streaks span days
        breaker.reset(operator="ajay")
        assert not breaker.check(today=d2).tripped


class TestAuditLog:
    def test_chain_verifies_and_persists(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        log = AuditLog(path)
        log.append("order_received", {"id": "r1"})
        log.append("order_result", {"id": "r1", "status": "filled"})
        assert log.verify()

        reloaded = AuditLog(path)
        assert len(reloaded) == 2
        assert reloaded.verify()
        assert reloaded.entries[1]["prev_hash"] == reloaded.entries[0]["hash"]

    def test_tampering_breaks_verification(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        log = AuditLog(path)
        log.append("order_received", {"id": "r1"})
        log.append("order_result", {"id": "r1", "status": "filled"})

        lines = path.read_text().splitlines()
        entry = json.loads(lines[0])
        entry["payload"]["id"] = "r2"  # rewrite history
        lines[0] = json.dumps(entry, sort_keys=True)
        path.write_text("\n".join(lines) + "\n")

        assert not AuditLog(path).verify()

    def test_deletion_breaks_verification(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        log = AuditLog(path)
        for i in range(3):
            log.append("event", {"i": i})
        lines = path.read_text().splitlines()
        path.write_text("\n".join([lines[0], lines[2]]) + "\n")
        assert not AuditLog(path).verify()
