from tradingagents.execution import PaperTradingLedger


def test_paper_trading_deposit_open_close_and_raw_memory(tmp_path):
    ledger = PaperTradingLedger(tmp_path)
    ledger.deposit(1000)

    signal = {
        "symbol": "SOL/USDT",
        "action": "BUY",
        "strategy": "rsi_reversal",
        "entry": 100.0,
        "stop_loss": 98.0,
        "take_profit": 104.0,
        "market_regime": "trend_down",
        "rsi": 25.0,
        "volume_spike": 1.2,
        "strength": 0.7,
        "timestamp_utc": "2026-05-23T00:00:00Z",
    }
    order = ledger.open_position(signal, {"symbol": "SOL/USDT", "action": "BUY", "confidence": 0.8, "reasoning": "paper test"}, allocation_pct=0.1)

    assert order["status"] == "opened"
    assert ledger.portfolio()["stats"]["open_positions"] == 1

    closed = ledger.check_exits({"SOL/USDT": {"high": 105.0, "low": 99.0, "close": 104.0}}, timestamp_utc="2026-05-23T01:00:00Z")

    assert len(closed) == 1
    assert closed[0]["result"] == "WIN"
    assert round(closed[0]["pnl"], 4) == 4.0
    portfolio = ledger.portfolio()
    assert portfolio["stats"]["open_positions"] == 0
    assert portfolio["stats"]["wins"] == 1
    assert portfolio["cash"] == 1004.0
    assert (tmp_path / "raw" / "raw.jsonl").exists()


def test_paper_trading_time_exit_closes_stale_position(tmp_path):
    ledger = PaperTradingLedger(tmp_path)
    ledger.deposit(1000)

    signal = {
        "symbol": "NEAR/USDT",
        "action": "BUY",
        "strategy": "ema_crossover",
        "entry": 2.4,
        "stop_loss": 2.3,
        "take_profit": 2.7,
        "timestamp_utc": "2026-05-23T00:00:00Z",
    }
    order = ledger.open_position(
        signal,
        {"symbol": "NEAR/USDT", "action": "BUY", "confidence": 0.7},
        allocation_pct=0.1,
        opened_at="2026-05-23T00:00:00Z",
    )

    assert order["status"] == "opened"
    closed = ledger.check_exits(
        {"NEAR/USDT": {"high": 2.45, "low": 2.35, "close": 2.42}},
        timestamp_utc="2026-05-24T01:00:00Z",
        max_hold_hours=24,
    )

    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "TIME_EXIT"
    assert closed[0]["exit_price"] == 2.42
    assert ledger.portfolio()["stats"]["open_positions"] == 0


def test_paper_trading_breakeven_and_trailing_stop(tmp_path):
    ledger = PaperTradingLedger(tmp_path)
    ledger.deposit(1000)

    signal = {
        "symbol": "BTC/USDT",
        "action": "BUY",
        "strategy": "rsi_reversal",
        "entry": 100.0,
        "stop_loss": 98.0,
        "take_profit": 104.0,
        "timestamp_utc": "2026-05-23T00:00:00Z",
    }
    order = ledger.open_position(
        signal,
        {"symbol": "BTC/USDT", "action": "BUY", "confidence": 0.7},
        allocation_pct=0.1,
        opened_at="2026-05-23T00:00:00Z",
    )

    assert order["status"] == "opened"

    closed = ledger.check_exits(
        {"BTC/USDT": {"high": 101.0, "low": 101.0, "close": 101.0}},
        timestamp_utc="2026-05-23T00:30:00Z",
        breakeven_trigger_pct=0.6,
        trailing_stop_pct=0.5,
    )
    assert closed == []
    position = ledger.load_positions()[0]
    assert position["breakeven_armed"] is True
    assert position["trailing_armed"] is True
    assert position["stop_loss"] == 100.495

    closed = ledger.check_exits(
        {"BTC/USDT": {"high": 100.5, "low": 100.49, "close": 100.49}},
        timestamp_utc="2026-05-23T00:45:00Z",
        breakeven_trigger_pct=0.6,
        trailing_stop_pct=0.5,
    )

    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "TRAILING_STOP"
    assert closed[0]["result"] == "WIN"
