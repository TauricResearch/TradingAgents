import pandas as pd

from tradingagents.dataflows.config import set_config
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.memory import CryptoMemoryStore, MemoryProcessor, TradeMemory
from tradingagents.scanner import FastCryptoScanner


def _sample_ohlcv(rows=90):
    dates = pd.date_range("2026-01-01", periods=rows, freq="15min", tz="UTC")
    close = [100 + i * 0.1 for i in range(rows)]
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": [value + 1 for value in close],
            "Low": [value - 1 for value in close],
            "Close": close,
            "Volume": [100 + (i % 5) * 10 for i in range(rows)],
        }
    )


def _reward_risk(signal):
    risk = signal.entry - signal.stop_loss
    reward = signal.take_profit - signal.entry
    return reward / risk


def test_scanner_enrich_indicators_are_not_all_nan():
    try:
        scanner = FastCryptoScanner({"scanner_min_strength": 0.0})
        enriched = scanner._enrich(_sample_ohlcv()).dropna()
    finally:
        set_config(DEFAULT_CONFIG.copy())

    assert not enriched.empty
    assert enriched["rsi"].notna().any()
    assert enriched["atr"].notna().any()
    assert enriched["close_10_ema"].notna().any()
    assert enriched["close_50_sma"].notna().any()


def test_scanner_defaults_to_conservative_high_win_rate_filters():
    try:
        scanner = FastCryptoScanner()
    finally:
        set_config(DEFAULT_CONFIG.copy())

    assert scanner.enable_breakout is False
    assert scanner.enable_ema_crossover is False
    assert scanner.enable_rsi_momentum is False
    assert scanner.enable_trend_pullback is False
    assert scanner.enable_liquidity_sweep is True
    assert scanner.enable_range_bounce is True
    assert scanner.enable_bb_reversion is True
    assert scanner.enable_orderflow is False
    assert scanner.enable_regime_flip is False
    assert scanner.enable_ensemble is True
    assert scanner.ensemble_min_votes == 3
    assert scanner.reversal_buy_regimes == {"trend_down", "sideway"}
    assert scanner.reversal_sell_regimes == set()
    assert scanner.min_strength == 0.65
    assert scanner.rsi_oversold == 35


def test_scanner_emits_sideway_range_bounce_signal():
    try:
        dates = pd.date_range("2026-01-01", periods=70, freq="1h", tz="UTC")
        enriched = pd.DataFrame(
            {
                "Date": dates,
                "Open": [100.0] * 70,
                "High": [105.0] * 70,
                "Low": [95.0] * 70,
                "Close": [100.0] * 70,
                "Volume": [100.0] * 70,
                "atr": [2.0] * 70,
                "rsi": [50.0] * 70,
                "close_10_ema": [100.0] * 70,
                "close_50_sma": [100.0] * 70,
                "volume_spike": [0.40] * 70,
            }
        )
        enriched.loc[68, "Close"] = 96.5
        enriched.loc[69, ["Open", "Close", "rsi"]] = [96.6, 97.0, 48.0]
        scanner = FastCryptoScanner({"scanner_min_strength": 0.0, "scanner_enable_ensemble": False})

        candidates = scanner.scan_all_strategies("NEAR/USDT", enriched)
    finally:
        set_config(DEFAULT_CONFIG.copy())

    assert any(candidate.strategy == "range_bounce" and candidate.market_regime == "sideway" for candidate in candidates)


def test_sideway_range_bounce_tp_is_not_capped_below_min_reward_risk():
    try:
        dates = pd.date_range("2026-01-01", periods=70, freq="1h", tz="UTC")
        enriched = pd.DataFrame(
            {
                "Date": dates,
                "Open": [101.0] * 70,
                "High": [103.2] * 70,
                "Low": [100.0] * 70,
                "Close": [101.0] * 70,
                "Volume": [100.0] * 70,
                "atr": [2.0] * 70,
                "rsi": [50.0] * 70,
                "close_10_ema": [101.0] * 70,
                "close_50_sma": [101.0] * 70,
                "volume_spike": [0.40] * 70,
            }
        )
        enriched.loc[69, ["Open", "Close", "rsi"]] = [101.0, 101.11, 48.0]
        scanner = FastCryptoScanner(
            {"scanner_min_strength": 0.0, "scanner_enable_ensemble": False, "scanner_min_reward_risk": 1.20}
        )

        candidates = scanner.scan_all_strategies("NEAR/USDT", enriched)
    finally:
        set_config(DEFAULT_CONFIG.copy())

    signal = next(candidate for candidate in candidates if candidate.strategy == "range_bounce")
    assert _reward_risk(signal) >= 1.20
    assert signal.take_profit > 103.2


def test_trade_memory_reads_only_global_tier(tmp_path):
    store = CryptoMemoryStore(tmp_path)
    store.append_raw({"coin": "BTC/USDT", "lesson": "raw must not be used"})
    store.append_lesson({"lesson_id": "lesson_1", "lesson": "draft must not be used"})
    store.append_global(
        {
            "lesson_id": "global_1",
            "lesson": "Validated low-volume breakouts fail often.",
            "recommendation": "Avoid breakout unless volume confirms.",
            "confidence": 0.86,
            "evidence_count": 47,
            "coins_tested": ["BTC/USDT"],
        }
    )

    context = TradeMemory(store).get_global_context("BTC/USDT")

    assert "Validated low-volume" in context
    assert "raw must not" not in context
    assert "draft must not" not in context


def test_memory_processor_creates_draft_lessons(tmp_path):
    store = CryptoMemoryStore(tmp_path)
    for i in range(5):
        store.append_raw(
            {
                "strategy": "breakout",
                "timeframe": "15m",
                "signal": "BUY",
                "mode_id": "td1",
                "result": "LOSS",
                "market_context": {"market_regime": "sideway"},
            }
        )

    created = MemoryProcessor(store, min_cases=5).process()

    assert len(created) == 1
    assert created[0]["memory_tier"] == "lesson"
    assert created[0]["status"] == "draft"