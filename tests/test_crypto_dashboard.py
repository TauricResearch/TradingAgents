from scripts.crypto_dashboard import (
    DashboardStore,
    config_payload,
    compute_bucket_stats,
    memory_context_payload,
    overview_payload,
    paper_deposit_payload,
    paper_force_close_all_payload,
    paper_force_close_payload,
    paper_performance_payload,
    process_lessons_payload,
    promote_global_payload,
    trading_payload,
    _scanner_risk_rejection,
)


def test_dashboard_computes_day_week_month_stats(tmp_path):
    store = DashboardStore(tmp_path)
    store.update_state({"mode": "trade", "trading_enabled": False})
    store_dir = tmp_path / "raw"
    store_dir.mkdir(parents=True, exist_ok=True)
    raw = store_dir / "raw.jsonl"
    raw.write_text(
        "\n".join(
            [
                '{"timestamp_utc":"2026-05-20T10:00:00+00:00","coin":"BTC/USDT","signal":"BUY","result":"WIN","pnl":1.2}',
                '{"timestamp_utc":"2026-05-20T11:00:00+00:00","coin":"BTC/USDT","signal":"SELL","result":"LOSS","pnl":-0.4}',
                '{"timestamp_utc":"2026-05-21T10:00:00+00:00","coin":"ETH/USDT","signal":"BUY","result":"WIN","pnl":0.6}',
            ]
        ),
        encoding="utf-8",
    )

    payload = overview_payload(store)

    assert payload["counts"]["trades"] == 3
    assert payload["counts"]["wins"] == 2
    assert round(payload["counts"]["win_rate"], 4) == 0.6667
    assert "state" not in payload
    assert config_payload(store)["state"]["mode"] == "trade"
    assert payload["symbols"] == ["BTC/USDT", "ETH/USDT"]


def test_compute_bucket_stats_ignores_unclosed_signals():
    rows = [
        {"date_normalized": "2026-05-20", "result_normalized": "WIN", "pnl_normalized": 1.0},
        {"date_normalized": "2026-05-20", "result_normalized": "LOSS", "pnl_normalized": -0.5},
        {"date_normalized": "2026-05-20", "result_normalized": "", "pnl_normalized": None},
    ]

    stats = compute_bucket_stats(rows, "date_normalized")

    assert len(stats) == 1
    assert stats[0]["trades"] == 2
    assert stats[0]["wins"] == 1
    assert stats[0]["losses"] == 1


def test_dashboard_memory_ops_process_and_promote(tmp_path):
    store = DashboardStore(tmp_path)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw = raw_dir / "raw.jsonl"
    raw.write_text(
        "\n".join(
            [
                '{"timestamp_utc":"2026-05-20T10:00:00+00:00","coin":"BTC/USDT","strategy":"breakout","timeframe":"15m","market_context":{"market_regime":"trend_up"},"signal":"BUY","result":"WIN","mode_id":"backtest"}',
                '{"timestamp_utc":"2026-05-20T11:00:00+00:00","coin":"ETH/USDT","strategy":"breakout","timeframe":"15m","market_context":{"market_regime":"trend_up"},"signal":"BUY","result":"WIN","mode_id":"backtest"}',
                '{"timestamp_utc":"2026-05-20T12:00:00+00:00","coin":"SOL/USDT","strategy":"breakout","timeframe":"15m","market_context":{"market_regime":"trend_up"},"signal":"BUY","result":"WIN","mode_id":"backtest"}',
            ]
        ),
        encoding="utf-8",
    )

    processed = process_lessons_payload(store, min_cases=3)
    promoted = promote_global_payload(store, min_cases=3, min_confidence=0.8, min_source_modes=1)

    assert processed["created"] == 1
    assert processed["created_lessons"][0]["coins_tested"] == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    assert promoted["promoted"] == 1
    assert promoted["promoted_lessons"][0]["status"] == "validated"


def test_dashboard_training_memory_tier_state_and_context_preview(tmp_path):
    store = DashboardStore(tmp_path)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "raw.jsonl").write_text(
        '{"timestamp_utc":"2026-05-20T10:00:00+00:00","coin":"BTC/USDT","strategy":"rsi_reversal","signal":"BUY","result":"WIN","pnl":0.5,"reasoning":"dashboard raw preview"}\n',
        encoding="utf-8",
    )

    state = store.update_state({"training_memory_tiers": ["raw", "bad-tier"]})
    payload = memory_context_payload(store, symbol="BTC/USDT")

    assert state["training_memory_tiers"] == ["raw"]
    assert payload["training_memory_tiers"] == ["raw"]
    assert "dashboard raw preview" in payload["context"]


def test_dashboard_paper_payload_deposit_and_mark(tmp_path):
    store = DashboardStore(tmp_path)
    deposit = paper_deposit_payload(store, 500)

    assert deposit["paper"]["cash"] == 500
    assert trading_payload(store)["paper"]["total_deposits"] == 500
    assert deposit["paper"]["stats"]["open_positions"] == 0


def test_dashboard_paper_force_close_uses_current_price(tmp_path):
    store = DashboardStore(tmp_path)
    paper_deposit_payload(store, 500)
    order = store.paper_ledger().open_position(
        {
            "symbol": "BTC/USDT",
            "action": "BUY",
            "strategy": "rsi_reversal",
            "entry": 100.0,
            "stop_loss": 98.0,
            "take_profit": 104.0,
            "timestamp_utc": "2026-05-28T00:00:00Z",
        },
        {"action": "BUY", "confidence": 0.8, "reasoning": "test"},
        allocation_pct=0.20,
    )

    payload = paper_force_close_payload(store, order["position"]["id"], exit_price=102.0)

    assert payload["status"] == "closed"
    assert payload["trade"]["exit_reason"] == "MANUAL_CLOSE"
    assert payload["trade"]["result"] == "WIN"
    assert payload["paper"]["stats"]["open_positions"] == 0


def test_dashboard_paper_force_close_all_and_performance(tmp_path, monkeypatch):
    store = DashboardStore(tmp_path)
    monkeypatch.setattr("scripts.crypto_dashboard._fetch_ohlcv", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    paper_deposit_payload(store, 500)
    for symbol, entry, exit_price in [("BTC/USDT", 100.0, 101.0), ("ETH/USDT", 50.0, 49.5)]:
        order = store.paper_ledger().open_position(
            {
                "symbol": symbol,
                "action": "BUY",
                "strategy": "rsi_reversal",
                "entry": entry,
                "stop_loss": entry * 0.98,
                "take_profit": entry * 1.04,
                "timestamp_utc": "2026-05-28T00:00:00Z",
            },
            {"action": "BUY", "confidence": 0.8, "reasoning": "test"},
            allocation_pct=0.20,
        )
        positions = store.paper_ledger().load_positions()
        positions[-1]["last_price"] = exit_price
        store.paper_ledger().save_positions(positions)
        assert order["status"] == "opened"

    payload = paper_force_close_all_payload(store)
    performance = paper_performance_payload(store)

    assert payload["status"] == "closed"
    assert len(payload["closed"]) == 2
    assert payload["paper"]["stats"]["open_positions"] == 0
    assert {row["period"] for row in performance["periods"]} == {"day", "month", "year"}
    assert performance["total"]["deposits"] == 500


def test_scanner_risk_rejection_blocks_recent_loss_patterns():
    state = {
        "scanner_min_reward_risk": 1.20,
        "scanner_max_reversal_rsi": 35,
        "scanner_max_breakout_rsi": 68,
        "scanner_min_momentum_volume_spike": 0.70,
    }

    assert _scanner_risk_rejection(
        {
            "action": "BUY",
            "strategy": "ema_crossover",
            "entry": 100,
            "stop_loss": 99,
            "take_profit": 100.9,
            "rsi": 62,
            "volume_spike": 1.0,
            "market_regime": "trend_up",
        },
        state,
    ) == "reward_risk_below_1.20"

    assert _scanner_risk_rejection(
        {
            "action": "BUY",
            "strategy": "rsi_momentum",
            "entry": 100,
            "stop_loss": 99,
            "take_profit": 102,
            "rsi": 56,
            "volume_spike": 1.0,
            "market_regime": "sideway",
        },
        state,
    ) == "momentum_not_in_trend_up"

    assert _scanner_risk_rejection(
        {
            "action": "BUY",
            "strategy": "breakout",
            "entry": 100,
            "stop_loss": 99,
            "take_profit": 102,
            "rsi": 73,
            "volume_spike": 2.0,
            "market_regime": "trend_up",
        },
        state,
    ) == "breakout_rsi_overheated"

    assert _scanner_risk_rejection(
        {
            "action": "BUY",
            "strategy": "range_bounce",
            "entry": 100,
            "stop_loss": 98,
            "take_profit": 103,
            "rsi": 48,
            "volume_spike": 0.3,
            "market_regime": "trend_up",
        },
        state,
    ) == "sideway_strategy_not_in_sideway"

    assert _scanner_risk_rejection(
        {
            "action": "BUY",
            "strategy": "range_bounce",
            "entry": 100,
            "stop_loss": 98,
            "take_profit": 103,
            "rsi": 48,
            "volume_spike": 0.3,
            "market_regime": "sideway",
        },
        state,
    ) is None