import time

import pytest
import requests

from trader import okx
from trader.okx import OKX, Bar, ContractSpec, FundingEvent, FundingRate, OKXError

CANDLES = "/api/v5/market/history-candles"
FUNDING = "/api/v5/public/funding-rate-history"
FUNDING_RATE = "/api/v5/public/funding-rate"
OPEN_INTEREST = "/api/v5/public/open-interest"
T0 = 1_767_225_600_000  # 2026-01-01 00:00 UTC
HOUR_MS = 3_600_000


def minute(i):
    return T0 + i * okx.MINUTE_MS


def settlement(i):
    return T0 + i * 8 * HOUR_MS


def candle(i, confirm="1"):
    """OKX candle row for minute i, with prices offset by i so the rows differ."""
    prices = [str(p + i) for p in (100, 101, 99, 100.5)]
    return [str(minute(i)), *prices, "1", "1", "1", confirm]


def funding_row(ts, realized, rate="0.0001"):
    return {"fundingTime": str(ts), "fundingRate": rate, "realizedRate": realized}


class FakeResponse:
    def __init__(self, body, status_code=200):
        self.body = body
        self.status_code = status_code

    def json(self):
        if isinstance(self.body, str):  # a page, not JSON
            raise ValueError("not JSON")
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


class FakeSession:
    """Serves each page once, keyed by (path, after cursor): a list is the ``data``
    of a successful answer, a dict the whole body, a FakeResponse the answer as is.
    ``failures`` go out first instead, one per call whatever it asks for: an Exception
    is raised, a FakeResponse returned. Records every call."""

    def __init__(self, pages, failures=()):
        self.pages = dict(pages)
        self.failures = list(failures)
        self.calls = []

    def get(self, url, params, timeout):
        assert timeout == 10
        path = url.removeprefix(okx.BASE_URL)
        self.calls.append((path, params))
        if self.failures:
            page = self.failures.pop(0)
        else:
            page = self.pages.pop((path, params.get("after")))
        if isinstance(page, Exception):
            raise page
        if isinstance(page, FakeResponse):
            return page
        body = page if isinstance(page, dict) else {"code": "0", "msg": "", "data": page}
        return FakeResponse(body)


@pytest.fixture
def sleeps(monkeypatch):
    """Records the pauses between pages instead of waiting them out."""
    pauses = []
    monkeypatch.setattr(okx.time, "sleep", pauses.append)
    return pauses


def test_bars_page_back_until_the_start_is_covered(sleeps):
    session = FakeSession({
        (CANDLES, minute(9)): [candle(i) for i in (8, 7, 6)],
        (CANDLES, minute(6)): [candle(i) for i in (5, 4, 3)],
        (CANDLES, minute(3)): [candle(i) for i in (2, 1, 0)],
    })
    bars = OKX(session).bars("BTC-USDT-SWAP", "1m", minute(0), minute(9))
    # Each page's oldest row is the next page's exclusive cursor, so it comes back once.
    assert [b.ts for b in bars] == [minute(i) for i in range(9)]
    assert bars[0] == Bar(ts=minute(0), open=100.0, high=101.0, low=99.0, close=100.5)
    assert [params["after"] for _, params in session.calls] == [minute(9), minute(6), minute(3)]
    assert session.calls[0][1] == {
        "instId": "BTC-USDT-SWAP", "bar": "1m", "limit": 300, "after": minute(9)
    }
    assert sleeps == [okx._PAGE_PAUSE] * 2


def test_bars_keep_only_the_range_oldest_first_without_duplicates(sleeps):
    session = FakeSession({
        (CANDLES, minute(6)): [candle(i) for i in (6, 4, 5)],
        (CANDLES, minute(4)): [candle(i) for i in (4, 3, 2, 1)],
    })
    bars = OKX(session).bars("BTC-USDT", "1m", minute(2), minute(6))
    assert [b.ts for b in bars] == [minute(i) for i in (2, 3, 4, 5)]


def test_bars_drop_the_candle_still_open():
    session = FakeSession({(CANDLES, minute(5)): [candle(2, confirm="0"), candle(1), candle(0)]})
    bars = OKX(session).bars("BTC-USDT-SWAP", "1m", minute(0), minute(5))
    assert [b.ts for b in bars] == [minute(0), minute(1)]


def test_bars_stop_at_an_empty_page(sleeps):
    session = FakeSession({
        (CANDLES, minute(10)): [candle(9), candle(8)],
        (CANDLES, minute(8)): [],
    })
    bars = OKX(session).bars("SOL-USDT-SWAP", "1Dutc", minute(0), minute(10))
    assert [b.ts for b in bars] == [minute(8), minute(9)]
    assert len(session.calls) == 2


def test_a_page_no_older_than_its_cursor_raises_instead_of_looping(sleeps):
    session = FakeSession({(CANDLES, minute(5)): [candle(6), candle(5)]})
    with pytest.raises(OKXError, match=f"{CANDLES} .* page after {minute(5)} has no older row"):
        OKX(session).bars("BTC-USDT-SWAP", "1m", minute(0), minute(5))
    assert len(session.calls) == 1
    assert sleeps == []


def test_a_non_zero_code_raises_with_code_and_message():
    msg = "Instrument ID, Instrument ID code, or Spread ID doesn't exist."
    session = FakeSession({(CANDLES, minute(5)): {"code": "51001", "msg": msg, "data": []}})
    with pytest.raises(OKXError, match=f"code 51001: {msg}"):
        OKX(session).bars("FOO-USDT-SWAP", "1m", minute(0), minute(5))


def test_a_400_with_an_okx_code_raises_with_code_and_message(sleeps):
    body = {"code": "51001", "msg": "Instrument ID does not exist", "data": []}
    session = FakeSession({("/api/v5/market/ticker", None): FakeResponse(body, status_code=400)})
    with pytest.raises(OKXError, match="code 51001: Instrument ID does not exist"):
        OKX(session).last_price("FOO-USDT")
    assert len(session.calls) == 1
    assert sleeps == []


def test_a_non_json_answer_raises_its_http_error():
    page = FakeResponse("<html>403 Forbidden</html>", status_code=403)
    session = FakeSession({("/api/v5/market/ticker", None): page})
    with pytest.raises(requests.HTTPError, match="403"):
        OKX(session).last_price("BTC-USDT")


def test_a_timeout_and_a_429_are_retried_after_a_pause(sleeps):
    session = FakeSession(
        {(CANDLES, minute(2)): [candle(1), candle(0)]},
        failures=[requests.Timeout(), FakeResponse("Too Many Requests", status_code=429)],
    )
    bars = OKX(session).bars("BTC-USDT-SWAP", "1m", minute(0), minute(2))
    assert [b.ts for b in bars] == [minute(0), minute(1)]
    assert [params["after"] for _, params in session.calls] == [minute(2)] * 3
    assert sleeps == list(okx._RETRY_PAUSES)


def test_the_third_failure_in_a_row_is_raised_as_is(sleeps):
    last = requests.ConnectionError("still down")
    failures = [requests.Timeout(), FakeResponse("Bad Gateway", status_code=502), last]
    session = FakeSession({}, failures=failures)
    with pytest.raises(requests.ConnectionError) as raised:
        OKX(session).last_price("BTC-USDT")
    assert raised.value is last
    assert len(session.calls) == 3
    assert sleeps == list(okx._RETRY_PAUSES)


def test_funding_pages_back_by_funding_time(sleeps):
    session = FakeSession({
        (FUNDING, settlement(6)): [funding_row(settlement(i), "0.0001") for i in (5, 4, 3)],
        (FUNDING, settlement(3)): [funding_row(settlement(i), "0.0001") for i in (2, 1, 0)],
    })
    events = OKX(session).funding("BTC-USDT-SWAP", settlement(1), settlement(6))
    assert [e.ts for e in events] == [settlement(i) for i in range(1, 6)]
    assert session.calls[0][1] == {"instId": "BTC-USDT-SWAP", "limit": 400, "after": settlement(6)}
    assert sleeps == [okx._PAGE_PAUSE]


def test_funding_takes_the_realized_rate_and_falls_back_to_the_funding_rate():
    session = FakeSession({(FUNDING, settlement(2)): [
        funding_row(settlement(1), "", rate="0.0003"),
        funding_row(settlement(0), "-0.0002", rate="0.0001"),
    ]})
    events = OKX(session).funding("ETH-USDT-SWAP", settlement(0), settlement(2))
    assert events == [FundingEvent(settlement(0), -0.0002), FundingEvent(settlement(1), 0.0003)]


def test_contract_spec_reads_ctval_lotsz_minsz_and_ticksz():
    row = {"instId": "TEST-USDT-SWAP", "ctVal": "0.1", "lotSz": "0.01", "minSz": "0.05", "tickSz": "0.1"}
    session = FakeSession({("/api/v5/public/instruments", None): [row]})
    spec = OKX(session).contract_spec("TEST-USDT-SWAP")
    assert spec == ContractSpec(contract_value=0.1, lot_size=0.01, min_size=0.05, tick_size=0.1)
    assert session.calls[0][1] == {"instType": "SWAP", "instId": "TEST-USDT-SWAP"}


def test_contract_spec_without_a_tick_size_reads_zero():
    row = {"instId": "TEST-USDT-SWAP", "ctVal": "0.1", "lotSz": "0.01", "minSz": "0.05"}
    session = FakeSession({("/api/v5/public/instruments", None): [row]})
    assert OKX(session).contract_spec("TEST-USDT-SWAP").tick_size == 0.0


def test_last_price_reads_last_from_the_ticker():
    session = FakeSession({("/api/v5/market/ticker", None): [{"instId": "SOL-USDT", "last": "152.37"}]})
    assert OKX(session).last_price("SOL-USDT") == 152.37
    assert session.calls[0][1] == {"instId": "SOL-USDT"}


def test_contract_spec_of_an_unlisted_swap_raises_with_its_name():
    session = FakeSession({("/api/v5/public/instruments", None): []})
    with pytest.raises(OKXError, match="FOO-USDT-SWAP"):
        OKX(session).contract_spec("FOO-USDT-SWAP")


def test_last_price_of_an_unlisted_instrument_raises_with_its_name():
    session = FakeSession({("/api/v5/market/ticker", None): []})
    with pytest.raises(OKXError, match="FOO-USDT"):
        OKX(session).last_price("FOO-USDT")


def test_funding_rate_reads_the_current_rate_and_the_forecast():
    row = {
        "instId": "BTC-USDT-SWAP", "fundingRate": "0.0001", "nextFundingRate": "-0.00005",
        "fundingTime": str(settlement(1)), "nextFundingTime": str(settlement(2)),
    }
    session = FakeSession({(FUNDING_RATE, None): [row]})
    rate = OKX(session).funding_rate("BTC-USDT-SWAP")
    assert rate == FundingRate(
        rate=0.0001, time=settlement(1), next_rate=-0.00005, next_time=settlement(2)
    )
    assert session.calls == [(FUNDING_RATE, {"instId": "BTC-USDT-SWAP"})]


def test_funding_rate_without_a_forecast_has_none():
    row = {
        "fundingRate": "0.0002", "nextFundingRate": "",
        "fundingTime": str(settlement(1)), "nextFundingTime": str(settlement(2)),
    }
    session = FakeSession({(FUNDING_RATE, None): [row]})
    rate = OKX(session).funding_rate("ETH-USDT-SWAP")
    assert rate == FundingRate(0.0002, settlement(1), None, settlement(2))


def test_funding_rate_of_an_unlisted_swap_raises_with_its_name():
    session = FakeSession({(FUNDING_RATE, None): []})
    with pytest.raises(OKXError, match="FOO-USDT-SWAP"):
        OKX(session).funding_rate("FOO-USDT-SWAP")


def test_open_interest_reads_oiusd():
    row = {"instId": "SOL-USDT-SWAP", "oi": "1000", "oiCcy": "1000000", "oiUsd": "152370000.5"}
    session = FakeSession({(OPEN_INTEREST, None): [row]})
    assert OKX(session).open_interest("SOL-USDT-SWAP") == 152_370_000.5
    assert session.calls == [(OPEN_INTEREST, {"instType": "SWAP", "instId": "SOL-USDT-SWAP"})]


def test_open_interest_of_an_unlisted_swap_raises_with_its_name():
    session = FakeSession({(OPEN_INTEREST, None): []})
    with pytest.raises(OKXError, match="FOO-USDT-SWAP"):
        OKX(session).open_interest("FOO-USDT-SWAP")


@pytest.mark.integration
def test_live_btc_funding_rate_and_open_interest():
    client = OKX()
    rate = client.funding_rate("BTC-USDT-SWAP")
    assert abs(rate.rate) < 0.01
    assert rate.next_rate is None or abs(rate.next_rate) < 0.01
    # fundingTime may lag the clock by seconds while a settlement is processing.
    assert rate.time < rate.next_time
    assert rate.next_time > time.time() * 1000
    assert client.open_interest("BTC-USDT-SWAP") > 1_000_000  # USD


@pytest.mark.integration
def test_live_btc_minutes_and_funding():
    client = OKX()
    # 400 minutes that closed at least a minute ago, which takes two pages.
    end = (int(time.time() * 1000) // okx.MINUTE_MS - 1) * okx.MINUTE_MS
    start = end - 400 * okx.MINUTE_MS
    bars = client.bars("BTC-USDT-SWAP", "1m", start, end)
    assert [b.ts for b in bars] == list(range(start, end, okx.MINUTE_MS))
    assert all(1_000 < b.low <= min(b.open, b.close) <= max(b.open, b.close) <= b.high < 1_000_000
               for b in bars)
    # The last three full UTC days settle at 00:00, 08:00 and 16:00.
    day_end = int(time.time() * 1000) // okx.DAY_MS * okx.DAY_MS
    day_start = day_end - 3 * okx.DAY_MS
    events = client.funding("BTC-USDT-SWAP", day_start, day_end)
    assert [e.ts for e in events] == list(range(day_start, day_end, 8 * HOUR_MS))
    assert all(abs(e.rate) < 0.01 for e in events)
