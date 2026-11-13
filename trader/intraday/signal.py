"""The hourly signal of the intraday account: one deep-model call per coin (ADR 0006).

``Signaler.run`` asks the deep model which way to hold one coin's swap over the
next 1 to 4 hours, "Long", "Short" or "Flat", with a conviction and a one-line
reason. The model sees the day's multi-agent research (the latest record under
``results_dir``) as the higher-timeframe view, and OKX intraday data as the
lower-timeframe evidence: 24 hours of 15-minute candles, the hourly ATR, the last
price, the funding rate and the open interest. Without a usable last price and ATR
(``rules.usable_quote``) the model is not asked; any other number OKX gets wrong is
left out of the prompt or reads n/a.

It decides nothing else. Position size, stop and kill switch are computed by the
job from the rules (ADR 0003, ADR 0006), so the prompt asks for no price targets
and the answer carries none. It writes no ledger and sends no notification;
that is the job's work.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from trader import rules
from trader.intraday.settings import ATR_BAR, ATR_BARS, SIGNAL_BAR, SIGNAL_HOURS
from trader.intraday.types import SIGNALS, SignalResult
from trader.ledger import Position
from trader.okx import MINUTE_MS, OKX, Bar, FundingRate
from trader.research import build_config
from trader.rules import atr
from trader.settings import Coin, Settings
from tradingagents.llm_clients import create_tier_client

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
REPORT_CHARS = 1500  # each analyst report is cut to this many characters in the prompt
NO_RESEARCH = "No daily research is available yet."

SYSTEM_PROMPT = """\
You are an intraday trader of cryptocurrency perpetual swaps on OKX. Once an hour you are asked
which way to hold one contract over the next 1 to 4 hours: "Long", "Short" or "Flat".

How to weigh the evidence:
- The day's multi-agent research is the higher-timeframe view: a rating and the reports behind
  it. The market data (15-minute candles, hourly ATR, funding rate, open interest) is the
  lower-timeframe evidence; read it against that view.
- A positive funding rate means longs pay shorts at settlement; a negative one, the reverse.
- Changing direction costs about 0.1% of notional per round trip, so keep the current
  direction unless the evidence has changed.
- When the evidence conflicts or shows no edge, choose "Flat".
- Position size and stop are computed by the program from its rules. Give no price targets,
  stops or sizes.

Answer with exactly one JSON object and nothing else:
{"signal": "Long" | "Short" | "Flat", "conviction": 1 | 2 | 3,
 "reason": "<why, in Chinese, at most 80 characters>"}
conviction is 1 (weak), 2 (moderate) or 3 (strong).
"""

_HOUR_MS = 60 * MINUTE_MS
_BAR_UNITS = {"m": MINUTE_MS, "H": _HOUR_MS}
_RECORD_NAME = re.compile(r"^full_states_log_(\d{4}-\d{2}-\d{2})\.json$")


@dataclass(frozen=True)
class Market:
    """What OKX shows for the swap at decision time."""

    last: float
    bars: list[Bar]        # SIGNAL_BAR candles of the last SIGNAL_HOURS hours, oldest first
    atr: float             # ATR over ATR_BARS bars of ATR_BAR
    funding: FundingRate
    open_interest: float   # USD


@dataclass(frozen=True)
class Research:
    """The day's research as the prompt shows it: the decision whole, the reports cut."""

    trade_date: str
    rating: str | None
    decision: str
    market_report: str
    news_report: str
    sentiment_report: str


def load_research(results_dir: Path, coin: str, today: date) -> Research | None:
    """The latest record of ``coin`` under ``results_dir`` whose trade date, read from the
    file name, is at most ``today``; None when there is none or it cannot be read."""
    dated = {}
    for path in results_dir.glob(f"{coin}/**/full_states_log_*.json"):
        match = _RECORD_NAME.match(path.name)
        if match and match.group(1) <= today.isoformat():
            dated[match.group(1)] = path
    if not dated:
        return None
    trade_date = max(dated)
    try:
        record = json.loads(dated[trade_date].read_text(encoding="utf-8"))
    except (OSError, ValueError):  # being written, or not a record
        return None
    if not isinstance(record, dict):
        return None
    return Research(
        trade_date=str(record.get("trade_date") or trade_date),
        rating=record.get("final_rating"),
        decision=str(record.get("final_trade_decision") or ""),
        market_report=_clip(str(record.get("market_report") or "")),
        news_report=_clip(str(record.get("news_report") or "")),
        sentiment_report=_clip(str(record.get("sentiment_report") or "")),
    )


def build_prompt(
    coin: Coin, now_ms: int, position: Position | None, market: Market, research: Research | None
) -> tuple[str, str]:
    """The system and user messages of one decision.

    The user message lists the instrument, the time, the position, the last price and
    its 1h/4h/24h changes, the hourly ATR, funding, open interest, one row per candle
    (``HH:MM open high low close``, oldest first), then the research: trade date,
    rating, the whole final decision and the three cut reports, or NO_RESEARCH.

    ``market.last`` and ``market.atr`` are a quote ``rules.usable_quote`` takes
    (``Signaler.run`` asks no model otherwise). A funding rate or forecast
    ``rules.usable_rate`` refuses, or an open interest that is not a positive finite
    number, reads n/a; a candle with a price ``rules.usable_prices`` refuses is left
    out of the rows and of the changes, and the candles' header says how many were.
    """
    price = _price_format(market.last)
    symbol = coin.research.split("-")[0]
    usable = [b for b in market.bars if rules.usable_prices(b.open, b.high, b.low, b.close)]
    left_out = len(market.bars) - len(usable)
    market = replace(market, bars=usable)
    lines = [
        f"Instrument: {coin.swap} ({symbol} USDT-margined perpetual)",
        f"Time: {_stamp(now_ms)}",
        f"Current position: {_position_text(position, market.last, symbol, price)}",
        f"Last price: {price(market.last)}",
        "Change: " + ", ".join(
            f"{hours}h {_change(market, now_ms, hours)}" for hours in (1, 4, 24)
        ),
        f"Hourly ATR ({ATR_BARS} bars): {price(market.atr)} "
        f"({market.atr / market.last:.2%} of price)",
        f"Funding rate: {_funding(market.funding)}",
        f"Open interest: {_open_interest(market.open_interest)}",
        "",
        *_candles(market.bars, price, left_out),
        "",
        *_research_text(research),
    ]
    return SYSTEM_PROMPT, "\n".join(lines)


def parse_answer(text: str) -> tuple[str | None, int | None, str, str | None]:
    """signal, conviction, reason and error read from the model's answer.

    The answer is the first JSON object in ``text``, whatever surrounds it (prose, a
    ```json fence). Its signal is matched to SIGNALS regardless of case; no object or
    another signal gives signal None and an "unparsable answer" error. conviction is
    None unless it is 1, 2 or 3; reason is "" when missing.
    """
    answer = _first_object(text)
    if answer is None:
        return None, None, "", f"unparsable answer: {text[:200]}"
    signal = str(answer.get("signal", "")).strip().capitalize()
    error = None if signal in SIGNALS else f"unparsable answer: {text[:200]}"
    try:
        conviction = int(answer.get("conviction"))
    except (TypeError, ValueError):
        conviction = None
    reason = answer.get("reason")
    return (
        signal if error is None else None,
        conviction if conviction in (1, 2, 3) else None,
        "" if reason is None else str(reason),
        error,
    )


class Signaler:
    """Asks the deep model once per coin and hour; ``run`` never raises.

    The model is ``create_tier_client(build_config(settings), "deep").get_llm()`` unless
    ``llm`` is given; its tokens are priced at settings.price_deep. The research is
    read from ``results_dir``, settings.home / "logs" by default; ``now_fn`` gives the
    UTC time that bounds the research's trade date.
    """

    def __init__(
        self,
        settings: Settings,
        okx: OKX,
        llm=None,
        results_dir: Path | None = None,
        now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        config = build_config(settings)
        self.okx = okx
        self.llm = llm if llm is not None else create_tier_client(config, "deep").get_llm()
        self.model = config["deep_think_llm"]
        self.price = settings.price_deep
        self.results_dir = results_dir or settings.home / "logs"
        self.now_fn = now_fn

    def fingerprint(self) -> dict:
        """Model and prompt version; a change of either starts a new validation period."""
        return {"model": self.model, "prompt": PROMPT_VERSION}

    def run(self, coin: Coin, now_ms: int, position: Position | None = None) -> SignalResult:
        """The signal for ``coin`` at ``now_ms``, holding ``position`` (None when flat).

        Reads the research, fetches the market data, asks the model once and parses the
        answer. Without a usable last price and hourly ATR (``rules.usable_quote``) it
        asks no model: signal None, and the error says why. Any exception, from OKX or
        the model, becomes signal None with ``error`` set; an answer without a usable
        signal keeps the tokens it cost.
        """
        try:
            research = load_research(self.results_dir, coin.research, self.now_fn().date())
            market = self._market(coin, now_ms)
            if not rules.usable_quote(market.last, market.atr):
                return SignalResult(None, None, "", _unusable_quote(market))
            system, user = build_prompt(coin, now_ms, position, market, research)
            answer = self.llm.invoke([SystemMessage(system), HumanMessage(user)])
            tokens_in, tokens_out, cost = self._usage(answer)
            signal, conviction, reason, error = parse_answer(_text(answer))
        except Exception as exc:
            logger.exception("intraday signal of %s failed", coin.research)
            return SignalResult(None, None, "", f"{type(exc).__name__}: {exc}"[:500])
        return SignalResult(signal, conviction, reason, error, tokens_in, tokens_out, cost)

    def _market(self, coin: Coin, now_ms: int) -> Market:
        """SIGNAL_HOURS of SIGNAL_BAR candles up to ``now_ms``, the ATR of the ATR_BAR candles
        closed by the hour, and the swap's last price, funding and open interest."""
        hour = now_ms - now_ms % _HOUR_MS
        hourly = self.okx.bars(coin.swap, ATR_BAR, hour - (ATR_BARS + 5) * _HOUR_MS, hour)
        return Market(
            last=self.okx.last_price(coin.swap),
            bars=self.okx.bars(coin.swap, SIGNAL_BAR, now_ms - SIGNAL_HOURS * _HOUR_MS, now_ms),
            atr=atr(
                [b.high for b in hourly], [b.low for b in hourly], [b.close for b in hourly],
                days=ATR_BARS,
            ),
            funding=self.okx.funding_rate(coin.swap),
            open_interest=self.okx.open_interest(coin.swap),
        )

    def _usage(self, answer) -> tuple[int, int, float | None]:
        """Tokens of the answer's usage_metadata and their cost at the deep price; zero
        tokens and no cost without usage, no cost without a price."""
        usage = getattr(answer, "usage_metadata", None)
        if not usage:
            return 0, 0, None
        tokens_in = int(usage.get("input_tokens", 0))
        tokens_out = int(usage.get("output_tokens", 0))
        if self.price is None:
            return tokens_in, tokens_out, None
        cost = (tokens_in * self.price[0] + tokens_out * self.price[1]) / 1_000_000
        return tokens_in, tokens_out, cost


def _clip(text: str) -> str:
    return text if len(text) <= REPORT_CHARS else text[:REPORT_CHARS] + "…"


def _bar_ms(bar: str) -> int:
    """Length of an OKX intraday bar size such as "15m" or "1H" in milliseconds."""
    return int(bar[:-1]) * _BAR_UNITS[bar[-1]]


def _stamp(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d %H:%M UTC")


def _price_format(last: float) -> Callable[[float], str]:
    """Formats prices with about six significant digits: whole dollars for BTC, cents for ETH."""
    decimals = max(0, 5 - math.floor(math.log10(last))) if last > 0 else 2
    return lambda p: f"{p:.{decimals}f}"


def _unusable_quote(market: Market) -> str:
    """The error of a decision the model is not asked for, ``rules.usable_quote``
    refusing the last price or the hourly ATR."""
    return (
        f"unusable quote: last price {market.last}, hourly ATR {market.atr}; both must be "
        "positive finite numbers, so the model was not asked"
    )


def _funding(funding: FundingRate) -> str:
    """The current rate and the side that pays it, when it settles, and the forecast; a
    rate ``rules.usable_rate`` refuses reads n/a, with no side."""
    current = (
        f"{funding.rate:+.4%} ({_who_pays(funding.rate)})"
        if rules.usable_rate(funding.rate) else "n/a"
    )
    return (
        f"current {current}, settles {_stamp(funding.time)}; "
        f"next period forecast {_forecast(funding)}"
    )


def _forecast(funding: FundingRate) -> str:
    """The forecast rate and when it settles; "n/a" when OKX gives no forecast, or one
    ``rules.usable_rate`` refuses."""
    if funding.next_rate is None or not rules.usable_rate(funding.next_rate):
        return "n/a"
    return f"{funding.next_rate:+.4%} (settles {_stamp(funding.next_time)})"


def _who_pays(rate: float) -> str:
    if rate == 0:
        return "neither side pays"
    return "longs pay shorts" if rate > 0 else "shorts pay longs"


def _open_interest(usd: float) -> str:
    """Open interest in millions of USD; n/a unless it is a positive finite number."""
    return f"{usd / 1e6:,.1f}M USD" if math.isfinite(usd) and usd > 0 else "n/a"


def _position_text(position: Position | None, last: float, symbol: str, price) -> str:
    if position is None or position.qty == 0:
        return "flat"
    side = 1 if position.qty > 0 else -1
    pnl = (last / position.entry - 1) * side
    stop = "none" if position.stop is None else price(position.stop)
    return (
        f"{'long' if side > 0 else 'short'} {abs(position.qty):g} {symbol}, "
        f"average entry {price(position.entry)}, stop {stop}, unrealized {pnl:+.2%}"
    )


def _change(market: Market, now_ms: int, hours: int) -> str:
    """Change of the last price against the price ``hours`` ago: the close of the last
    candle closed by then, else the open of the oldest candle; "n/a" without candles."""
    if not market.bars:
        return "n/a"
    then = now_ms - hours * _HOUR_MS
    closed = [b for b in market.bars if b.ts + _bar_ms(SIGNAL_BAR) <= then]
    reference = closed[-1].close if closed else market.bars[0].open
    return f"{market.last / reference - 1:+.2%}"


def _candles(bars: list[Bar], price, left_out: int) -> list[str]:
    """The header and one row per candle; the header says how many candles were
    ``left_out`` for prices that cannot be used."""
    note = f", {left_out} with unusable prices left out" if left_out else ""
    if not bars:
        return [f"{SIGNAL_BAR} candles of the last {SIGNAL_HOURS} hours: none{note}"]
    span = f"from {_stamp(bars[0].ts)} to {_stamp(bars[-1].ts + _bar_ms(SIGNAL_BAR))}"
    header = (
        f"{SIGNAL_BAR} candles of the last {SIGNAL_HOURS} hours, {span}{note}, oldest first "
        "(time open high low close):"
    )
    rows = [
        f"{datetime.fromtimestamp(b.ts / 1000, UTC):%H:%M} "
        f"{price(b.open)} {price(b.high)} {price(b.low)} {price(b.close)}"
        for b in bars
    ]
    return [header, *rows]


def _research_text(research: Research | None) -> list[str]:
    if research is None:
        return [f"Daily research: {NO_RESEARCH}"]
    return [
        f"Daily multi-agent research for trade date {research.trade_date}, "
        f"rating: {research.rating or 'none'}",
        "",
        "Final trade decision:",
        research.decision,
        "",
        "Market report:",
        research.market_report,
        "",
        "News report:",
        research.news_report,
        "",
        "Sentiment report:",
        research.sentiment_report,
    ]


def _first_object(text: str) -> dict | None:
    """The first JSON object in ``text``, whatever surrounds it; None when there is none."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _text(answer) -> str:
    """The text of a model answer: ``content`` as a string, or its text blocks joined."""
    content = answer.content
    if isinstance(content, str):
        return content
    return "".join(
        block if isinstance(block, str) else str(block.get("text", ""))
        for block in content
        if isinstance(block, str) or block.get("type") == "text"
    )
