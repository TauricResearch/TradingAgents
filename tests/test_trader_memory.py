from trader.memory import replace_decision
from tradingagents.memory.log import TradingMemoryLog


def log(path):
    return TradingMemoryLog({"memory_log_path": str(path)})


def test_a_reruns_decision_takes_the_place_of_the_pending_one(tmp_path):
    path = tmp_path / "trading_memory.md"
    log(path).store_decision("ETH-USD", "2026-11-13", "ETH, the first run", "Sell")
    log(path).store_decision("BTC-USD", "2026-11-13", "BTC, without the day's candle", "Hold")
    log(path).store_decision("BTC-USD", "2026-11-13", "BTC, the rerun", "Buy")
    assert "BTC, the rerun" not in path.read_text(encoding="utf-8")  # the log keeps a day's first

    assert replace_decision(path, "BTC-USD", "2026-11-13", "BTC, on the full candles", "Buy")
    text = path.read_text(encoding="utf-8")
    assert "without the day's candle" not in text and "BTC, on the full candles" in text
    assert [(e["ticker"], e["rating"]) for e in log(path).get_pending_entries()] == [
        ("ETH-USD", "Sell"), ("BTC-USD", "Buy"),
    ]


def test_without_a_pending_entry_of_the_day_the_log_is_left_alone(tmp_path):
    path = tmp_path / "memory" / "trading_memory.md"
    assert not replace_decision(path, "BTC-USD", "2026-11-13", "BTC", "Buy")  # nor a directory yet
    path.parent.mkdir()
    log(path).store_decision("BTC-USD", "2026-11-12", "BTC, the day before", "Hold")
    log(path).store_decision("BTC-USD", "2026-11-13", "BTC, settled", "Hold")
    assert log(path).update_with_outcome("BTC-USD", "2026-11-13", 0.01, 0.0, 5, "fine")
    before = path.read_text(encoding="utf-8")
    assert not replace_decision(path, "BTC-USD", "2026-11-13", "BTC, the rerun", "Buy")
    assert not replace_decision(path, "ETH-USD", "2026-11-13", "ETH", "Buy")
    assert path.read_text(encoding="utf-8") == before
