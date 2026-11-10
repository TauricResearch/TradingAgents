import math

import pytest
import requests

from tests.test_trader_paper import BTC, DAY0, FakeOKX
from trader import report
from trader.ledger import Ledger, Position
from trader.okx import DAY_MS, Bar
from trader.paper import Paper
from trader.settings import Coin


def test_metrics_of_known_series():
    assert report.max_drawdown([100, 120, 90, 130, 117]) == pytest.approx(0.25)
    assert report.annualized([100, 100]) == 0
    assert report.sharpe([100, 101]) is None  # one return
    assert report.sharpe([100, 100, 100]) is None  # no deviation
    # Returns +2% and -1%: mean 0.5%, sample deviation 1.5% * sqrt(2).
    expected = 0.005 / (0.015 * math.sqrt(2)) * math.sqrt(365)
    assert report.sharpe([100, 102, 100.98]) == pytest.approx(expected)
    assert report.performance_line("x", [1.0]) == "x：样本不足"


def test_full_report_nets_llm_spend_and_sets_the_baselines(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.initialize(10_000.0, DAY0)
    ledger.commit(
        positions={}, cash=10_000.0, meta={"validation_start": DAY0},
        snapshots=[(DAY0, 10_000.0), (DAY0 + DAY_MS, 10_100.0), (DAY0 + 2 * DAY_MS, 10_200.0)],
    )
    # $100 spent after the second midnight comes off the third.
    ledger.record_attempt(
        "2026-01-10", BTC.research, DAY0 + DAY_MS + 1, rating="Hold", error=None, cost_usd=100.0
    )
    okx = FakeOKX()
    okx.daily = [Bar(DAY0 + (i - 1) * DAY_MS, 0, 0, 0, c) for i, c in enumerate((80_000, 80_800, 81_600))]
    text = report.full(Paper(ledger, okx, (BTC,)), tmp_path / "no_memory_log.md")
    assert "共 2 天" in text
    assert "策略（扣 LLM 费用）：累计 +1.00%" in text
    assert "三币等权买入持有：累计 +2.00%" in text
    assert "BTC 买入持有：累计 +2.00%" in text
    assert "LLM 费用 $100.00" in text
    assert "还没有结算的评级" in text


def test_daily_report_shows_a_halt_and_the_learning_budget(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.initialize(10_000.0, DAY0)
    ledger.set("halted", True)
    text = report.daily(
        Paper(ledger, FakeOKX(), (BTC,)), "2026-01-09", {BTC.research: ("done", "Buy")},
        DAY0, DAY0, None,
    )
    assert text.splitlines()[1].startswith("⚠ 熔断中")
    assert "BTC：Buy → 不调仓；无持仓" in text
    assert "净值 10,000.00 USDT，今日 +0.00%" in text
    assert "上限未定（已观察 0/7 天）" in text


class DownOKX(FakeOKX):
    """FakeOKX whose ticker endpoint fails like an unreachable host."""

    def last_price(self, inst):
        raise requests.ConnectionError("Host is down")


def test_daily_report_goes_out_at_the_last_marks_when_okx_is_down(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.initialize(10_000.0, DAY0)
    ledger.commit(
        positions={BTC.swap: Position(0.1, 80_000.0, 75_000.0)}, cash=10_000.0,
        snapshots=[(DAY0, 10_000.0)],
        meta={
            "validation_start": DAY0, "baseline_ref": {BTC.research: 80_000.0},
            "marks": {BTC.swap: 81_000.0},
        },
    )
    text = report.daily(
        Paper(ledger, DownOKX(), (BTC,)), "2026-01-09", {BTC.research: ("done", "Buy")},
        DAY0, DAY0, None,
    )
    assert "净值 10,100.00 USDT" in text  # 0.1 BTC from 80,000, marked at the 81,000 mark
    assert "验证期累计 +1.00%，扣 LLM 费用后 +1.00%\n" in text  # no spot baseline after it
    assert text.splitlines()[-1].startswith("⚠ 行情暂不可用（OKX）")


def test_daily_report_marks_a_contract_without_a_mark_at_its_entry(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.initialize(10_000.0, DAY0)
    ledger.commit(positions={BTC.swap: Position(0.1, 80_000.0, 75_000.0)}, cash=10_000.0)
    text = report.daily(
        Paper(ledger, DownOKX(), (BTC,)), "2026-01-09", {BTC.research: ("done", "Hold")},
        DAY0, DAY0, None,
    )
    assert "净值 10,000.00 USDT" in text and "行情暂不可用" in text


def test_daily_report_with_okx_up_says_nothing_about_the_market(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.initialize(10_000.0, DAY0)
    text = report.daily(
        Paper(ledger, FakeOKX(), (BTC,)), "2026-01-09", {BTC.research: ("done", "Hold")},
        DAY0, DAY0, None,
    )
    assert "行情暂不可用" not in text


def test_daily_report_prices_the_baseline_only_for_coins_the_period_started_with(tmp_path):
    eth = Coin("ETH-USD", "ETH-USDT-SWAP", "ETH-USDT")
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.initialize(10_000.0, DAY0)
    ledger.commit(
        positions={}, cash=10_000.0, snapshots=[(DAY0, 10_000.0)],
        meta={"validation_start": DAY0, "baseline_ref": {BTC.research: 80_000.0}},
    )
    paper = Paper(ledger, FakeOKX(last=82_000.0), (BTC, eth))  # ETH joined after the start
    states = {c.research: ("done", "Hold") for c in (BTC, eth)}
    text = report.daily(paper, "2026-01-09", states, DAY0 + DAY_MS, DAY0, None)
    assert "三币等权现货 +2.50%" in text  # BTC alone: 82,000 / 80,000
