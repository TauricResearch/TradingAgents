"""The daily and mark jobs on live OKX market data, with the research faked.

Run with: .venv/bin/pytest tests/test_trader_integration.py -m integration
"""

from datetime import UTC, datetime

import pytest

from tests.test_trader_jobs import FakeResearcher, Inbox
from trader import jobs, report
from trader.ledger import Ledger
from trader.okx import DAY_MS, MINUTE_MS, OKX
from trader.paper import Paper
from trader.settings import Settings

pytestmark = pytest.mark.integration


def test_daily_then_mark_on_live_market_data(tmp_path):
    settings = Settings(home=tmp_path)
    ledger = Ledger(settings.ledger_path)
    now = datetime.now(UTC)
    now_ms = int(now.timestamp() * 1000)
    ledger.initialize(10_000.0, now_ms)
    paper, inbox = Paper(ledger, OKX()), Inbox()
    researcher = FakeResearcher({"BTC-USD": ["Buy"], "ETH-USD": ["Sell"], "SOL-USD": ["Hold"]})

    jobs.daily(settings, paper, inbox, lambda: researcher, now_fn=lambda: now)
    positions = ledger.positions()
    assert positions["BTC-USDT-SWAP"].qty > 0
    assert positions["ETH-USDT-SWAP"].qty < 0
    assert "SOL-USDT-SWAP" not in positions
    for pos in positions.values():
        assert 0.01 < abs(pos.entry - pos.stop) / pos.entry < 0.5  # 2.5 daily ATRs
    equity = paper.equity({inst: paper.okx.last_price(inst) for inst in positions})
    assert equity == pytest.approx(10_000, rel=0.02)
    assert "模拟盘日报" in inbox.sent[-1]

    # Replay the last 50 hours over these positions: real paging, funding and midnights.
    end = now_ms - now_ms % MINUTE_MS
    ledger.set("processed_to", end - 50 * 60 * MINUTE_MS)
    jobs.mark(settings, paper, inbox, now_fn=lambda: now)
    assert ledger.get("processed_to") >= end - 5 * MINUTE_MS
    day_start = now_ms - now_ms % DAY_MS
    assert day_start - DAY_MS in dict(ledger.equity_series())
    assert "模拟盘绩效" in report.full(paper, settings.memory_log_path)
