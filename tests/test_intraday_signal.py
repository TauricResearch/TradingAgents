import json
import logging
import re
from datetime import UTC, datetime

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from trader.intraday import signal
from trader.intraday.signal import (
    NO_RESEARCH,
    PROMPT_VERSION,
    Market,
    Research,
    Signaler,
    build_prompt,
    parse_answer,
)
from trader.intraday.types import SignalResult
from trader.ledger import Position
from trader.okx import MINUTE_MS, Bar, FundingRate, OKXError
from trader.research import build_config
from trader.settings import Coin, Settings
from tradingagents.default_config import DEFAULT_CONFIG

BTC = Coin("BTC-USD", "BTC-USDT-SWAP", "BTC-USDT")
NOW = datetime(2026, 11, 7, 12, 3, tzinfo=UTC)
NOW_MS = int(NOW.timestamp() * 1000)
HOUR_MS = 60 * MINUTE_MS
M15 = 15 * MINUTE_MS
USAGE = {"input_tokens": 1200, "output_tokens": 60, "total_tokens": 1260}
ANSWER = '{"signal": "Long", "conviction": 2, "reason": "日线减持，但盘面已企稳反弹"}'
FUNDING = FundingRate(
    rate=0.0001, time=NOW_MS + 4 * HOUR_MS, next_rate=-0.00005, next_time=NOW_MS + 12 * HOUR_MS
)
ROW = re.compile(r"^\d\d:\d\d \d+ \d+ \d+ \d+$", re.MULTILINE)


class FakeLLM:
    """Answers every call with ``reply`` (a string gets USAGE attached); raises ``error``
    instead when given. Records the messages of each call."""

    def __init__(self, reply=ANSWER, error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        if isinstance(self.reply, AIMessage):
            return self.reply
        return AIMessage(content=self.reply, usage_metadata=dict(USAGE))


class FakeOKX:
    """Regular candles of any bar size, closed by the range's end: the 15-minute closes
    rise 10 a candle from 100,000, the hourly candles all range 99,750-100,250 (ATR 500).
    ``error`` is raised by last_price instead of answering."""

    def __init__(self, last=100_000.0, funding=FUNDING, open_interest=2.5e9, error=None):
        self.last = last
        self.funding = funding
        self.oi = open_interest
        self.error = error
        self.calls = []

    def bars(self, inst, bar, start_ms, end_ms):
        self.calls.append(("bars", inst, bar, start_ms, end_ms))
        step = {"15m": M15, "1H": HOUR_MS}[bar]
        first = -(-start_ms // step) * step
        out = []
        for i, ts in enumerate(range(first, end_ms - step + 1, step)):
            if bar == "15m":
                close = 100_000 + 10 * i
                out.append(Bar(ts, close - 10, close + 5, close - 15, close))
            else:
                out.append(Bar(ts, 100_000, 100_250, 99_750, 100_000))
        return out

    def last_price(self, inst):
        self.calls.append(("last_price", inst))
        if self.error is not None:
            raise self.error
        return self.last

    def funding_rate(self, inst):
        self.calls.append(("funding_rate", inst))
        return self.funding

    def open_interest(self, inst):
        self.calls.append(("open_interest", inst))
        return self.oi


def write_record(logs, coin, trade_date, **fields):
    """A research record as the graph writes it, under the coin's strategy directory."""
    path = logs / coin / "TradingAgentsStrategy_logs" / f"full_states_log_{trade_date}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "trade_date": trade_date,
        "final_rating": "Underweight",
        "final_trade_decision": "最终决定：减持。",
        "market_report": "市场报告",
        "news_report": "新闻报告",
        "sentiment_report": "情绪报告",
        **fields,
    }
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def logs(tmp_path):
    logs = tmp_path / "logs"
    write_record(logs, "BTC-USD", "2026-11-06")
    return logs


def signaler(tmp_path, llm=None, okx=None, price=(15.0, 75.0)):
    settings = Settings(home=tmp_path, price_deep=price)
    return Signaler(
        settings, okx or FakeOKX(), llm=llm or FakeLLM(), results_dir=tmp_path / "logs",
        now_fn=lambda: NOW,
    )


def user_message(llm):
    (messages,) = llm.calls
    assert [type(m) for m in messages] == [SystemMessage, HumanMessage]
    return messages[1].content


# -- run: data, prompt, result -------------------------------------------------


def test_run_asks_the_model_with_the_research_and_the_market(tmp_path, logs):
    llm, okx = FakeLLM(), FakeOKX()
    result = signaler(tmp_path, llm, okx).run(BTC, NOW_MS, Position(-0.05, 102_000.0, 104_500.0))
    assert result == SignalResult(
        "Long", 2, "日线减持，但盘面已企稳反弹", None, 1200, 60, pytest.approx(0.0225)
    )
    user = user_message(llm)
    assert "Instrument: BTC-USDT-SWAP (BTC USDT-margined perpetual)" in user
    assert "Time: 2026-11-07 12:03 UTC" in user
    assert ("Current position: short 0.05 BTC, average entry 102000, stop 104500, "
            "unrealized +1.96%") in user
    assert "Last price: 100000" in user
    assert "Hourly ATR (14 bars): 500 (0.50% of price)" in user
    assert ("Funding rate: current +0.0100% (longs pay shorts), settles 2026-11-07 16:03 UTC; "
            "next period forecast -0.0050% (settles 2026-11-08 00:03 UTC)") in user
    assert "Open interest: 2,500.0M USD" in user
    assert "rating: Underweight" in user
    assert "最终决定：减持。" in user
    assert all(report in user for report in ("市场报告", "新闻报告", "情绪报告"))
    # 24 hours of 15-minute candles closed by 12:03: 11-06 12:15 through 11-07 11:45.
    rows = ROW.findall(user)
    assert len(rows) == 95
    assert rows[0].startswith("12:15 ") and rows[-1].startswith("11:45 ")
    assert "from 2026-11-06 12:15 UTC to 2026-11-07 12:00 UTC" in user


def test_run_fetches_the_candles_the_atr_needs_and_the_swap_data(tmp_path, logs):
    okx = FakeOKX()
    signaler(tmp_path, okx=okx).run(BTC, NOW_MS)
    hour = NOW_MS - 3 * MINUTE_MS
    assert okx.calls == [
        ("bars", "BTC-USDT-SWAP", "1H", hour - 19 * HOUR_MS, hour),
        ("last_price", "BTC-USDT-SWAP"),
        ("bars", "BTC-USDT-SWAP", "15m", NOW_MS - 24 * HOUR_MS, NOW_MS),
        ("funding_rate", "BTC-USDT-SWAP"),
        ("open_interest", "BTC-USDT-SWAP"),
    ]


def test_a_flat_account_is_told_so(tmp_path, logs):
    llm = FakeLLM()
    signaler(tmp_path, llm).run(BTC, NOW_MS)
    assert "Current position: flat" in user_message(llm)
    llm = FakeLLM()
    signaler(tmp_path, llm).run(BTC, NOW_MS, Position(0.0, 0.0, None))
    assert "Current position: flat" in user_message(llm)


def test_without_research_the_prompt_says_so(tmp_path):
    llm = FakeLLM()
    result = signaler(tmp_path, llm).run(BTC, NOW_MS)
    assert result.signal == "Long" and result.error is None
    assert f"Daily research: {NO_RESEARCH}" in user_message(llm)
    assert "rating" not in user_message(llm)


def test_the_latest_record_up_to_today_is_used(tmp_path, logs):
    write_record(logs, "BTC-USD", "2026-11-04", final_rating="Buy")
    write_record(logs, "BTC-USD", "2026-11-07", final_rating="Sell")  # today, by now_fn
    write_record(logs, "BTC-USD", "2026-11-09", final_rating="Hold")  # a future date
    write_record(logs, "ETH-USD", "2026-11-08", final_rating="Hold")  # another coin
    llm = FakeLLM()
    signaler(tmp_path, llm).run(BTC, NOW_MS)
    assert "trade date 2026-11-07, rating: Sell" in user_message(llm)


def test_reports_are_cut_and_the_decision_is_whole(tmp_path, logs):
    write_record(
        logs, "BTC-USD", "2026-11-06", final_trade_decision="乙" * 2000,
        market_report="甲" * 2000, news_report="丙" * 1500, sentiment_report=None,
    )
    llm = FakeLLM()
    signaler(tmp_path, llm).run(BTC, NOW_MS)
    user = user_message(llm)
    assert "甲" * 1500 + "…" in user and "甲" * 1501 not in user
    assert "丙" * 1500 + "\n" in user and "丙…" not in user
    assert "乙" * 2000 in user
    assert user.endswith("Sentiment report:\n")  # a missing report is shown empty


def test_a_record_that_cannot_be_read_counts_as_no_research(tmp_path, logs):
    write_record(logs, "BTC-USD", "2026-11-06").write_text("{not json", encoding="utf-8")
    llm = FakeLLM()
    signaler(tmp_path, llm).run(BTC, NOW_MS)
    assert NO_RESEARCH in user_message(llm)


def test_a_record_without_a_rating_shows_none(tmp_path, logs):
    write_record(logs, "BTC-USD", "2026-11-06", final_rating=None)
    llm = FakeLLM()
    signaler(tmp_path, llm).run(BTC, NOW_MS)
    assert "rating: none" in user_message(llm)


# -- prompt pieces -------------------------------------------------------------


def _market(last, bars, atr=412.3456):
    return Market(last, bars, atr, FUNDING, 2_625_395_188.25)


def test_changes_compare_the_last_price_with_the_last_close_before_the_horizon():
    # Six candles ending at 12:03; the 1h horizon (11:03) has one candle closed by then,
    # the 4h and 24h horizons have none and fall back to the oldest candle's open.
    bars = [Bar(NOW_MS - (6 - i) * M15, 100_000, 100_100, 99_900, 100_000) for i in range(6)]
    bars[0] = Bar(bars[0].ts, 98_000, 99_100, 97_900, 99_000)
    bars[1] = Bar(bars[1].ts, 99_000, 100_100, 98_900, 100_020)
    _, user = build_prompt(BTC, NOW_MS, None, _market(101_000.0, bars), None)
    assert "Change: 1h +0.98%, 4h +3.06%, 24h +3.06%" in user
    assert ROW.findall(user)[0] == "10:33 98000 99100 97900 99000"


def test_prices_take_the_precision_the_coin_needs():
    sol = Coin("SOL-USD", "SOL-USDT-SWAP", "SOL-USDT")
    bars = [Bar(NOW_MS - M15, 152.1, 152.9, 151.8, 152.37)]
    _, user = build_prompt(sol, NOW_MS, Position(10, 150.0, None), _market(152.37, bars, 1.2), None)
    assert "Last price: 152.370" in user
    assert ("Current position: long 10 SOL, average entry 150.000, stop none, "
            "unrealized +1.58%") in user
    assert "Hourly ATR (14 bars): 1.200 (0.79% of price)" in user
    assert "11:48 152.100 152.900 151.800 152.370" in user


def test_a_prompt_without_candles_still_builds():
    _, user = build_prompt(BTC, NOW_MS, None, _market(100_000.0, []), None)
    assert "Change: 1h n/a, 4h n/a, 24h n/a" in user
    assert "15m candles of the last 24 hours: none" in user


def test_funding_without_a_forecast_and_negative_rates_are_described():
    funding = FundingRate(-0.0002, NOW_MS + HOUR_MS, None, NOW_MS + 9 * HOUR_MS)
    market = Market(100_000.0, [], 400.0, funding, 1e9)
    _, user = build_prompt(BTC, NOW_MS, None, market, None)
    assert ("Funding rate: current -0.0200% (shorts pay longs), settles 2026-11-07 13:03 UTC; "
            "next period forecast n/a") in user


def test_the_research_section_lists_date_rating_decision_and_reports():
    research = Research("2026-11-06", "Overweight", "决定", "市场", "新闻", "情绪")
    _, user = build_prompt(BTC, NOW_MS, None, _market(100_000.0, []), research)
    assert user.endswith(
        "Daily multi-agent research for trade date 2026-11-06, rating: Overweight\n\n"
        "Final trade decision:\n决定\n\nMarket report:\n市场\n\nNews report:\n新闻\n\n"
        "Sentiment report:\n情绪"
    )


def test_the_system_prompt_asks_for_one_json_object_and_no_targets():
    system, _ = build_prompt(BTC, NOW_MS, None, _market(100_000.0, []), None)
    assert '"Long", "Short" or "Flat"' in system
    assert "exactly one JSON object" in system
    assert "Give no price targets" in system


# -- parsing the answer --------------------------------------------------------


@pytest.mark.parametrize("text", [
    ANSWER,
    f"```json\n{ANSWER}\n```",
    f"Here is my decision:\n{ANSWER}\nGood luck.",
    "{not json} " + ANSWER,
])
def test_the_first_json_object_is_read_whatever_surrounds_it(text):
    assert parse_answer(text) == ("Long", 2, "日线减持，但盘面已企稳反弹", None)


@pytest.mark.parametrize(
    "raw, expected", [("long", "Long"), ("FLAT", "Flat"), (" short ", "Short")]
)
def test_the_signal_is_matched_regardless_of_case(raw, expected):
    assert parse_answer(json.dumps({"signal": raw, "conviction": 1}))[0] == expected


@pytest.mark.parametrize("text", [
    "I cannot decide.",
    '{"signal": "Buy", "conviction": 2, "reason": "x"}',
    '{"conviction": 2}',
    "[1, 2, 3]",
])
def test_an_answer_without_a_usable_signal_is_an_error(text):
    sig, conviction, _, error = parse_answer(text)
    assert sig is None
    assert error == f"unparsable answer: {text[:200]}"


def test_the_unparsable_answer_is_cut_to_200_characters():
    assert parse_answer("x" * 500)[3] == "unparsable answer: " + "x" * 200


@pytest.mark.parametrize("raw, expected", [
    (3, 3), ("2", 2), (2.7, 2), (0, None), (4, None), ("high", None), (None, None),
])
def test_conviction_is_an_int_from_1_to_3_or_none(raw, expected):
    assert parse_answer(json.dumps({"signal": "Flat", "conviction": raw}))[1] == expected


def test_a_missing_reason_is_empty_and_another_type_is_made_a_string():
    assert parse_answer('{"signal": "Flat"}') == ("Flat", None, "", None)
    assert parse_answer('{"signal": "Flat", "reason": 42}')[2] == "42"


def test_text_blocks_of_a_list_content_are_joined(tmp_path, logs):
    reply = AIMessage(
        content=[{"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": ANSWER}],
        usage_metadata=dict(USAGE),
    )
    result = signaler(tmp_path, FakeLLM(reply)).run(BTC, NOW_MS)
    assert (result.signal, result.conviction, result.tokens_in) == ("Long", 2, 1200)


def test_an_unparsable_answer_keeps_the_tokens_it_cost(tmp_path, logs):
    result = signaler(tmp_path, FakeLLM("I cannot decide.")).run(BTC, NOW_MS)
    assert result == SignalResult(
        None, None, "", "unparsable answer: I cannot decide.", 1200, 60, pytest.approx(0.0225)
    )


# -- failures never raise ------------------------------------------------------


def test_a_model_error_becomes_an_error_result(tmp_path, logs, caplog):
    with caplog.at_level(logging.ERROR, logger="trader.intraday.signal"):
        result = signaler(tmp_path, FakeLLM(error=TimeoutError("x" * 1000))).run(BTC, NOW_MS)
    assert result.signal is None and result.conviction is None and result.reason == ""
    assert len(result.error) == 500 and result.error.startswith("TimeoutError: xxx")
    assert (result.tokens_in, result.tokens_out, result.cost_usd) == (0, 0, None)
    assert "intraday signal of BTC-USD failed" in caplog.text


def test_an_okx_error_becomes_an_error_result_before_the_model_is_asked(tmp_path, logs):
    llm = FakeLLM()
    okx = FakeOKX(error=OKXError("OKX has no ticker for BTC-USDT-SWAP"))
    result = signaler(tmp_path, llm, okx).run(BTC, NOW_MS)
    assert result == SignalResult(None, None, "", "OKXError: OKX has no ticker for BTC-USDT-SWAP")
    assert llm.calls == []


def test_too_few_hourly_candles_for_the_atr_is_an_error(tmp_path, logs):
    class ShortOKX(FakeOKX):
        def bars(self, inst, bar, start_ms, end_ms):
            return super().bars(inst, bar, start_ms, end_ms)[:5]

    result = signaler(tmp_path, okx=ShortOKX()).run(BTC, NOW_MS)
    assert result.signal is None and result.error.startswith("ValueError: ATR over 14 days")


# -- usage, cost, fingerprint --------------------------------------------------


def test_cost_is_the_deep_price_of_the_tokens(tmp_path, logs):
    result = signaler(tmp_path, price=(1.0, 10.0)).run(BTC, NOW_MS)
    assert (result.tokens_in, result.tokens_out) == (1200, 60)
    assert result.cost_usd == pytest.approx((1200 * 1.0 + 60 * 10.0) / 1_000_000)


def test_cost_is_unknown_without_a_price_or_without_usage(tmp_path, logs):
    result = signaler(tmp_path, price=None).run(BTC, NOW_MS)
    assert (result.tokens_in, result.tokens_out, result.cost_usd) == (1200, 60, None)
    result = signaler(tmp_path, FakeLLM(AIMessage(content=ANSWER))).run(BTC, NOW_MS)
    assert result.signal == "Long"
    assert (result.tokens_in, result.tokens_out, result.cost_usd) == (0, 0, None)


def test_fingerprint_names_the_deep_model_and_the_prompt_version(tmp_path, monkeypatch):
    assert signaler(tmp_path).fingerprint() == {
        "model": DEFAULT_CONFIG["deep_think_llm"], "prompt": PROMPT_VERSION
    }
    monkeypatch.setitem(DEFAULT_CONFIG, "deep_think_llm", "some-deep-model")
    assert signaler(tmp_path).fingerprint() == {"model": "some-deep-model", "prompt": "v1"}


def test_the_default_model_is_the_deep_tier_client_over_the_trader_config(tmp_path, monkeypatch):
    built = {}

    class FakeClient:
        def __init__(self, config, tier):
            built.update(config=config, tier=tier)

        def get_llm(self):
            return "the deep llm"

    monkeypatch.setattr(signal, "create_tier_client", FakeClient)
    settings = Settings(home=tmp_path)
    made = Signaler(settings, FakeOKX())  # the two positional arguments the job uses
    assert made.llm == "the deep llm"
    assert built == {"config": build_config(settings), "tier": "deep"}
    assert made.results_dir == tmp_path / "logs"
    assert made.price is None
