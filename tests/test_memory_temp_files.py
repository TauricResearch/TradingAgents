"""Independent memory logs must never share a settlement temporary file."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from tradingagents.memory import TradingMemoryLog


def settle(log, ticker, batch):
    update = {
        "ticker": ticker, "trade_date": "2026-01-01", "raw_return": 0.1,
        "alpha_return": 0.05, "holding_days": 5, "reflection": f"Outcome for {ticker}",
    }
    if batch:
        log.batch_update_with_outcomes([update])
    else:
        assert log.update_with_outcome(**update) is True


@pytest.mark.parametrize("batch", [False, True])
def test_settlement_preserves_a_neighboring_tmp_file(tmp_path, batch):
    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "memory.md")})
    log.store_decision("AAA", "2026-01-01", "Rating: Buy")
    neighbor = tmp_path / "memory.tmp"
    neighbor.write_text("Existing neighboring file", encoding="utf-8")

    settle(log, "AAA", batch)

    assert neighbor.read_text(encoding="utf-8") == "Existing neighboring file"
    assert log.load_entries()[0]["pending"] is False


@pytest.mark.parametrize("batch", [False, True])
def test_differently_suffixed_logs_can_settle_concurrently(tmp_path, monkeypatch, batch):
    logs = [TradingMemoryLog({"memory_log_path": str(tmp_path / name)})
            for name in ("memory.md", "memory.log")]
    for log, ticker in zip(logs, ("AAA", "BBB"), strict=True):
        log.store_decision(ticker, "2026-01-01", "Rating: Buy")
    barrier = Barrier(2)
    write_text = Path.write_text

    def synchronize_temp_writes(path, *args, **kwargs):
        result = write_text(path, *args, **kwargs)
        if path.suffix == ".tmp":
            barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(Path, "write_text", synchronize_temp_writes)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(settle, log, ticker, batch)
                   for log, ticker in zip(logs, ("AAA", "BBB"), strict=True)]
        for future in futures:
            future.result(timeout=15)

    for log, ticker in zip(logs, ("AAA", "BBB"), strict=True):
        entries = log.load_entries()
        assert len(entries) == 1
        assert entries[0]["ticker"] == ticker
        assert entries[0]["reflection"] == f"Outcome for {ticker}"
        assert entries[0]["pending"] is False
    assert list(tmp_path.glob("*.tmp")) == []
