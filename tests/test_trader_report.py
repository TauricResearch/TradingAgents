import math

import pytest
import requests

from tests.test_trader_paper import BAD_PRICES, BTC, DAY0, FakeOKX, Market
from trader import report
from trader.ledger import Fill, Ledger, Position
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
    assert text.startswith("日报 · 研判日 01-09\n\n⚠ 熔断中")
    assert "\n\nBTC · Buy\n不调仓 · 无持仓\n\n" in text
    assert "净值 10,000.00 USDT\n今日 +0.00% · 回撤 0.0%" in text
    assert "上限未定（已观察 0/7 天）" in text


def test_daily_report_lays_out_a_paragraph_per_coin_and_says_what_a_rerun_did_to_a_rating(tmp_path):
    eth = Coin("ETH-USD", "ETH-USDT-SWAP", "ETH-USDT")
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.initialize(10_000.0, DAY0)
    ledger.commit(
        positions={BTC.swap: Position(-0.0085, 80_000.0, 81_428.26)}, cash=10_000.0,
        fills=[
            Fill(DAY0, BTC.swap, -0.005, 80_000.0, 0.2, "trade", "2026-01-09"),
            Fill(DAY0 + 1, BTC.swap, -0.0035, 80_100.0, 0.14, "trade", "2026-01-09"),
        ],
    )
    ledger.record_update("2026-01-09", BTC.research, DAY0, "Underweight", "Underweight")
    ledger.record_update("2026-01-09", eth.research, DAY0, "Hold", "Underweight")
    states = {c.research: ("done", "Underweight") for c in (BTC, eth)}
    text = report.daily(Paper(ledger, FakeOKX(), (BTC, eth)), "2026-01-09", states, DAY0 + 2, DAY0, 53.4)
    assert text.split("\n\n")[:3] == [
        "日报 · 研判日 01-09",
        "BTC · Underweight（重跑后不变）\n卖出 0.0085 @ 均价 80,041.18（2 笔）\n持仓 -0.0085 · 止损 81,428.26",
        "ETH · Underweight（重跑前是 Hold）\n不调仓 · 无持仓",
    ]
    assert text.splitlines()[-1] == "AI 费用：今日 $0.00 · 本月 $0.00 / 上限 $53.40"


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
    assert "验证期 +1.00% · 扣 AI 费用后 +1.00%\nAI 费用" in text  # no spot baseline after it
    assert text.splitlines()[-1] == "⚠ 行情暂不可用（OKX）：净值按最近一次标记价计，三币等权现货略去。"


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


def validating(tmp_path):
    """A ledger in its validation period, its baseline bought BTC at 80,000; it holds 0.1
    BTC from 80,000, last marked at 81,000."""
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
    return ledger


def daily_text(ledger, okx):
    states = {BTC.research: ("done", "Hold")}
    return report.daily(Paper(ledger, okx, (BTC,)), "2026-01-09", states, DAY0, DAY0, None)


@pytest.mark.parametrize("price", [price for price, _ in BAD_PRICES])
def test_daily_report_leaves_out_a_baseline_whose_last_price_cannot_be_used(tmp_path, price):
    okx = Market(last=82_000.0)
    okx.prices[BTC.spot] = price
    text = daily_text(validating(tmp_path), okx)
    assert "净值 10,200.00 USDT" in text  # the contract's own last price, 82,000, was usable
    assert "验证期 +2.00% · 扣 AI 费用后 +2.00%\nAI 费用" in text
    assert text.splitlines()[-1] == "⚠ 行情暂不可用（OKX）：三币等权现货略去。"


@pytest.mark.parametrize("price", [price for price, _ in BAD_PRICES])
def test_daily_report_marks_a_contract_whose_last_price_cannot_be_used_at_its_mark(
    tmp_path, price,
):
    okx = Market(last=82_000.0)
    okx.prices[BTC.swap] = price
    text = daily_text(validating(tmp_path), okx)
    assert "净值 10,100.00 USDT" in text  # at the 81,000 mark
    assert "验证期 +1.00% · 扣 AI 费用后 +1.00%\n同期三币等权现货 +2.50%\n" in text  # spot usable
    assert text.splitlines()[-1] == "⚠ 行情暂不可用（OKX）：净值按最近一次标记价计。"


@pytest.mark.parametrize("ref", [price for price, _ in BAD_PRICES])
def test_daily_report_leaves_a_coin_whose_reference_close_cannot_be_used_out_of_the_baseline(
    tmp_path, ref,
):
    # A ledger from before the reference closes were checked (trader.paper._baseline_ref).
    eth = Coin("ETH-USD", "ETH-USDT-SWAP", "ETH-USDT")
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.initialize(10_000.0, DAY0)
    ledger.commit(
        positions={}, cash=10_000.0, snapshots=[(DAY0, 10_000.0)],
        meta={
            "validation_start": DAY0, "baseline_ref": {BTC.research: 80_000.0, eth.research: ref},
        },
    )
    paper = Paper(ledger, FakeOKX(last=82_000.0), (BTC, eth))
    states = {c.research: ("done", "Hold") for c in (BTC, eth)}
    text = report.daily(paper, "2026-01-09", states, DAY0 + DAY_MS, DAY0, None)
    assert "\n同期三币等权现货 +2.50%\n" in text  # BTC alone: 82,000 / 80,000
    assert "行情暂不可用" not in text


@pytest.mark.parametrize("close", [price for price, _ in BAD_PRICES])
@pytest.mark.parametrize(("day", "priced"), [(DAY0 - DAY_MS, []), (DAY0, [10_000.0, 10_200.0])])
def test_the_baselines_leave_out_each_midnight_a_close_that_cannot_be_used_would_price(
    tmp_path, close, day, priced,
):
    okx = FakeOKX()
    okx.daily = [
        Bar(ts, 0, 0, 0, close if ts == day else c)
        for ts, c in zip((DAY0 - DAY_MS, DAY0, DAY0 + DAY_MS), (80_000, 80_800, 81_600), strict=True)
    ]
    paper = Paper(Ledger(tmp_path / "ledger.sqlite"), okx, (BTC,))
    equal, btc = report.baselines(paper, [DAY0, DAY0 + DAY_MS, DAY0 + 2 * DAY_MS], 10_000.0)
    assert equal == btc == pytest.approx(priced)  # BTC alone
