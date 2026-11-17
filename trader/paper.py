"""The paper market: replays closed minutes over the account and trades it to targets.

``replay`` walks OKX 1-minute candles on from where the last replay stopped. It
fills stops (at the open when a candle gaps through one), books funding at each
settlement, marks equity at every close, tracks the peak, flattens everything
once the drawdown reaches KILL_DRAWDOWN, and snapshots equity at each UTC
midnight. A candle with a price that is not a positive finite number counts as
missing; a settlement whose rate is not a finite number is not booked.
``execute`` trades between minutes, at the last price.
"""

from __future__ import annotations

from datetime import UTC, datetime

from trader import message, rules
from trader.ledger import Fill, Ledger, Position
from trader.okx import DAY_MS, MINUTE_MS, OKX, REQUEST_ERRORS, Bar
from trader.settings import ATR_DAYS, KILL_DRAWDOWN, STOP_ATR_MULT, WATCHLIST, Coin

STALL_MS = 10 * MINUTE_MS

Quotes = dict[str, tuple[float, float]]  # contract -> (last price, ATR)


class ReplayStalled(RuntimeError):
    """OKX has served no usable closed candle for a held contract in the last STALL_MS."""


class Paper:
    resume_command = "python -m trader resume"  # named in the kill switch's alert

    def __init__(self, ledger: Ledger, okx: OKX, watchlist: tuple[Coin, ...] = WATCHLIST):
        self.ledger = ledger
        self.okx = okx
        self.watchlist = watchlist

    def equity(self, prices: dict[str, float]) -> float:
        """Cash plus the open positions marked at ``prices``, keyed by contract."""
        return self.ledger.get("cash") + sum(
            p.qty * (prices[inst] - p.entry) for inst, p in self.ledger.positions().items()
        )

    def equity_now(self) -> tuple[float, bool]:
        """Equity at OKX's last prices, for a report. A contract OKX gives no usable price
        for (REQUEST_ERRORS, or one ``rules.usable_prices`` refuses) is marked at its last
        mark (meta ``marks``, else its entry), and the flag says so: a report must go out
        even when OKX is down."""
        marks, prices, unavailable = self.ledger.get("marks") or {}, {}, False
        for inst, pos in self.ledger.positions().items():
            try:
                price = self.okx.last_price(inst)
            except REQUEST_ERRORS:
                price = None
            if price is None or not rules.usable_prices(price):
                price, unavailable = marks.get(inst, pos.entry), True
            prices[inst] = price
        return self.equity(prices), unavailable

    def replay(self, now_ms: int) -> list[str]:
        """Replay the minutes closed since the last replay; return the alerts raised."""
        start = self.ledger.get("processed_to")
        end = now_ms - now_ms % MINUTE_MS
        if end <= start:
            return []
        positions = self.ledger.positions()
        cash, peak = self.ledger.get("cash"), self.ledger.get("peak")
        if not positions:  # flat: equity is cash all along
            self.ledger.commit(
                positions={}, cash=cash, snapshots=[(m, cash) for m in _midnights(start, end)],
                meta={"processed_to": end},
            )
            return []

        # From the minute before ``start``, whose close prices funding settled at ``start``.
        # A candle ``rules.usable_prices`` refuses counts as missing: no stop fills at it,
        # no position is marked at it.
        bars, refused = {}, {}
        for inst in positions:
            bars[inst], refused[inst] = {}, []
            for b in self.okx.bars(inst, "1m", start - MINUTE_MS, end):
                if rules.usable_prices(b.open, b.high, b.low, b.close):
                    bars[inst][b.ts] = b
                else:
                    refused[inst].append(b)
        # Equity needs every held contract's close, so replay stops where the
        # shortest candle series does.
        stop_at = min(
            max((ts for ts in series if ts >= start), default=start - MINUTE_MS) + MINUTE_MS
            for series in bars.values()
        )
        if end - stop_at > STALL_MS:
            raise ReplayStalled(
                f"no usable closed 1m candles for {sorted(bars)} since {stop_at}"
            )
        if stop_at <= start:
            return []
        events = sorted(
            (e.ts, inst, e.rate) for inst in positions for e in self.okx.funding(inst, start, stop_at)
        )
        # Without that candle a contract starts at its last mark (meta ``marks``), else
        # its entry, as ``equity_now`` marks it.
        marks = self.ledger.get("marks") or {}
        last_close = {
            inst: series[start - MINUTE_MS].close if start - MINUTE_MS in series
            else marks.get(inst, positions[inst].entry)
            for inst, series in bars.items()
        }
        unusable = []  # an alert a contract, for its refused candles among the minutes replayed
        for inst, series in refused.items():
            replayed = [b for b in series if start <= b.ts < stop_at]
            if replayed:
                unusable.append(_bars_alert(inst, replayed))
        logged = [(now_ms, "bar_unusable", text) for text in unusable]
        halted = self.ledger.get("halted")
        alerts, fills, funding, snapshots = list(unusable), [], [], []
        for t in range(start, stop_at, MINUTE_MS):
            # Funding settles at the start of minute t, on the position held then, unless
            # ``rules.usable_rate`` refuses its rate: that settlement is alerted, not booked.
            while events and events[0][0] <= t:
                ts, inst, rate = events.pop(0)
                if inst not in positions:
                    continue
                if not rules.usable_rate(rate):
                    alerts.append(_funding_alert(inst, ts, rate))
                    logged.append((now_ms, "funding_unusable", alerts[-1]))
                    continue
                amount = rules.funding_payment(positions[inst].qty, last_close[inst], rate)
                cash += amount
                funding.append((ts, inst, rate, amount))
            for inst, pos in list(positions.items()):
                bar = bars[inst].get(t)
                hit = bar and rules.stop_fill(pos.qty, pos.stop, bar.open, bar.high, bar.low)
                if hit:
                    price = rules.slipped(hit, -pos.qty)
                    pnl = _move(positions, inst, 0.0, price, 0.0, t, "stop", fills)
                    cash += pnl
                    alerts.append(message.stopped(inst, -pos.qty, price, pos.entry, pnl))
            for inst, series in bars.items():
                if t in series:
                    last_close[inst] = series[t].close
            equity = cash + sum(p.qty * (last_close[i] - p.entry) for i, p in positions.items())
            peak = max(peak, equity)
            if positions and rules.drawdown(equity, peak) >= KILL_DRAWDOWN:
                for inst, pos in list(positions.items()):
                    price = rules.slipped(last_close[inst], -pos.qty)
                    cash += _move(positions, inst, 0.0, price, 0.0, t + MINUTE_MS, "kill", fills)
                halted = True
                alerts.append(_kill_alert(equity, peak, self.resume_command))
                equity = cash
            if (t + MINUTE_MS) % DAY_MS == 0:
                snapshots.append((t + MINUTE_MS, equity))
        self.ledger.commit(
            positions=positions, cash=cash, fills=fills, funding=funding, snapshots=snapshots,
            meta={
                "peak": peak, "halted": halted, "processed_to": stop_at,
                "marks": self.marks(last_close),
            },
            events=logged,
        )
        return alerts

    def marks(self, latest: dict[str, float]) -> dict[str, float]:
        """Meta ``marks``, the last price each contract was marked at, with ``latest``
        applied: what prices the account when OKX cannot be asked (the daily report)."""
        return {**(self.ledger.get("marks") or {}), **latest}

    def instruments(self, positions: dict[str, Position]) -> list[str]:
        """The contracts an execution quotes: the watchlist's, then any other the
        account still holds (a coin dropped from the watchlist keeps its stop)."""
        swaps = [coin.swap for coin in self.watchlist]
        return swaps + [inst for inst in positions if inst not in swaps]

    def usable(self, quotes: Quotes, when: str) -> tuple[Quotes, list[str]]:
        """``quotes`` without those ``rules.usable_quote`` refuses, and the alert of each
        of those: its contract is not traded ``when``, its stop is not moved, and its
        position is marked as ``held_prices`` says instead."""
        out, alerts = {}, []
        for inst, (price, atr_value) in quotes.items():
            if rules.usable_quote(price, atr_value):
                out[inst] = (price, atr_value)
            else:
                alerts.append(_unusable_alert(inst, price, atr_value, when))
        return out, alerts

    def held_prices(self, positions: dict[str, Position], quotes: Quotes) -> dict[str, float]:
        """The price an execution marks each position at: its quote's, else (``usable``
        refused the quote) its last mark (meta ``marks``), else its entry."""
        marks = self.ledger.get("marks") or {}
        return {
            inst: quotes[inst][0] if inst in quotes else marks.get(inst, pos.entry)
            for inst, pos in positions.items()
        }

    def execute(self, trade_date: str, ratings: dict[str, str | None], now_ms: int) -> list[str]:
        """Trade each contract toward the target its rating sets; return the alerts.

        Call right after ``replay``. ``ratings`` maps research tickers to ratings,
        None for a coin whose research failed. Runs once per trade date, and not
        while halted. A position in a contract no longer on the watchlist is not
        traded; its stop is managed until it closes the position. A contract whose
        quote is not usable (``usable``) sits the trade date out: it is alerted, not
        traded, its stop is not moved, and its position counts at its last mark. The
        first execution starts the validation period, unless ``_baseline_ref`` finds no
        usable spot close of the day before for a coin: that is alerted and left to a
        later trade date.
        """
        if self.ledger.executed(trade_date) or self.ledger.get("halted"):
            return []
        cash = self.ledger.get("cash")
        positions = self.ledger.positions()
        day_start = now_ms - now_ms % DAY_MS
        quotes = {}
        for inst in self.instruments(positions):
            daily = self.okx.bars(inst, "1Dutc", day_start - (ATR_DAYS + 5) * DAY_MS, day_start)
            atr_value = rules.atr(
                [b.high for b in daily], [b.low for b in daily], [b.close for b in daily]
            )
            quotes[inst] = (self.okx.last_price(inst), atr_value)
        quotes, unusable = self.usable(quotes, "今天")

        alerts, fills = list(unusable), []
        # A stop crossed since the last closed minute fills now; every other stop tightens.
        for inst, pos in list(positions.items()):
            if inst not in quotes:
                continue
            price, atr_value = quotes[inst]
            if rules.stop_fill(pos.qty, pos.stop, price, price, price) is not None:
                fill_price = rules.slipped(price, -pos.qty)
                pnl = _move(positions, inst, 0.0, fill_price, 0.0, now_ms, "stop", fills)
                cash += pnl
                alerts.append(message.stopped(inst, -pos.qty, fill_price, pos.entry, pnl))
            else:
                candidate = rules.initial_stop(price, pos.qty, atr_value)
                pos.stop = rules.tighten(pos.stop, candidate, pos.qty)

        prices = self.held_prices(positions, quotes)
        equity = cash + sum(p.qty * (prices[i] - p.entry) for i, p in positions.items())
        units, currents, targets = {}, {}, {}
        for coin in self.watchlist:
            pos = positions.get(coin.swap)
            if coin.swap not in quotes:  # held as it is, toward the gross cap at its mark
                held = pos.qty * prices[coin.swap] if pos else 0.0
                currents[coin.swap] = targets[coin.swap] = held
                continue
            price, atr_value = quotes[coin.swap]
            currents[coin.swap] = pos.qty * price if pos else 0.0
            units[coin.swap] = rules.unit_notional(equity, atr_value, price)
            targets[coin.swap] = rules.target_notional(
                ratings.get(coin.research), units[coin.swap], currents[coin.swap]
            )
        targets = rules.apply_caps(targets, currents, equity)
        for coin in self.watchlist:
            inst = coin.swap
            if inst not in quotes:
                continue
            if not rules.needs_trade(targets[inst], currents[inst], units[inst]):
                continue
            price, atr_value = quotes[inst]
            spec = self.okx.contract_spec(inst)
            new_qty = rules.to_quantity(
                targets[inst], price, spec.contract_value, spec.lot_size, spec.min_size
            )
            old_qty = positions[inst].qty if inst in positions else 0.0
            if new_qty == old_qty:
                continue
            fill_price = rules.slipped(price, new_qty - old_qty)
            cash += _move(
                positions, inst, new_qty, fill_price, atr_value, now_ms, "trade", fills, trade_date
            )

        meta = {"marks": self.marks({inst: price for inst, (price, _) in quotes.items()})}
        snapshots, events = [], [(now_ms, "quote_unusable", text) for text in unusable]
        if self.ledger.get("validation_start") is None:
            # The validation period starts with this trade date: the baseline buys
            # at the closes the research saw, and equity is marked as it stood.
            ref, deferred = _baseline_ref(self.okx, self.watchlist, day_start)
            if deferred:
                alerts.append(deferred)
                events.append((now_ms, "validation_deferred", deferred))
            else:
                meta.update(validation_start=day_start, baseline_ref=ref)
                snapshots.append((day_start, equity))
        self.ledger.commit(
            positions=positions, cash=cash, fills=fills, snapshots=snapshots, meta=meta,
            executed=(trade_date, now_ms), events=events,
        )
        return alerts

    def resume(self, now_ms: int) -> None:
        """Lift a halt. The account is flat, so the peak restarts at its cash."""
        cash = self.ledger.get("cash")
        self.ledger.commit(
            positions=self.ledger.positions(), cash=cash, meta={"halted": False, "peak": cash}
        )
        self.ledger.add_event(now_ms, "resume", f"熔断解除，峰值重置为 {cash:,.2f}")


def _move(
    positions: dict[str, Position], inst: str, new_qty: float, price: float, atr_value: float,
    ts: int, reason: str, fills: list[Fill], trade_date: str | None = None,
    *, stop_mult: float = STOP_ATR_MULT,
) -> float:
    """Move ``inst`` to ``new_qty`` coins at ``price`` (slippage included) and record
    the fill; return the cash it adds, realized PnL less the fee. The stop of the
    position left is ``stop_mult`` ATRs from the fill (``rules.stop_after_trade``),
    the daily account's multiple by default."""
    pos = positions.get(inst)
    old_qty = pos.qty if pos else 0.0
    if old_qty and (new_qty == 0 or (new_qty > 0) != (old_qty > 0)):  # close or flip
        realized, entry = old_qty * (price - pos.entry), price
    elif abs(new_qty) > abs(old_qty):                                   # open or add
        realized = 0.0
        entry = (old_qty * pos.entry + (new_qty - old_qty) * price) / new_qty if pos else price
    else:                                                               # reduce
        realized, entry = (old_qty - new_qty) * (price - pos.entry), pos.entry
    cost = rules.fee((new_qty - old_qty) * price)
    stop = rules.stop_after_trade(
        old_qty, new_qty, pos.stop if pos else None, price, atr_value, stop_mult=stop_mult
    )
    if new_qty:
        positions[inst] = Position(new_qty, entry, stop)
    else:
        del positions[inst]
    fills.append(Fill(ts, inst, round(new_qty - old_qty, 12), price, cost, reason, trade_date))
    return realized - cost


def _midnights(start: int, end: int) -> list[int]:
    """UTC midnights M with start < M <= end, in milliseconds."""
    return list(range(start - start % DAY_MS + DAY_MS, end + 1, DAY_MS))


def _bars_alert(inst: str, refused: list[Bar]) -> str:
    """The alert of the candles of ``inst`` a replay counted as missing, oldest first."""
    first = refused[0]
    when = datetime.fromtimestamp(first.ts / 1000, UTC).strftime("%m-%d %H:%M")
    return (
        f"K 线不能用：{inst} 有 {len(refused)} 根 1 分钟 K 线按缺失处理，最早一根 {when} UTC "
        f"开 {first.open:,.2f}，高 {first.high:,.2f}，低 {first.low:,.2f}，收 {first.close:,.2f}；"
        "开高低收都要是大于 0 的有限数，这几分钟不判断止损，净值按之前的收盘价算"
    )


def _funding_alert(inst: str, ts: int, rate: float) -> str:
    """The alert of a settlement a replay does not book, ``rules.usable_rate`` refusing
    its rate."""
    when = datetime.fromtimestamp(ts / 1000, UTC).strftime("%m-%d %H:%M")
    return f"资金费率不能用：{inst} {when} UTC 结算的费率是 {rate}，要是有限数；这次资金费不记"


def _baseline_ref(
    okx: OKX, watchlist: tuple[Coin, ...], day_start: int,
) -> tuple[dict[str, float], str | None]:
    """Meta ``baseline_ref`` of a validation period starting at ``day_start``: each
    coin's spot close of the day before, which the baseline buys it at; and None, or the
    alert that the period does not start yet when a coin has no such close
    ``rules.usable_prices`` takes. A later execution tries again, so that the baseline
    holds every coin, as ``report.baselines`` and the dashboard price it."""
    ref, problems = {}, []
    for coin in watchlist:
        bars = okx.bars(coin.spot, "1Dutc", day_start - DAY_MS, day_start)
        if not bars:
            problems.append(f"{coin.spot} 还没有这根日线")
        elif not rules.usable_prices(bars[-1].close):
            problems.append(f"{coin.spot} 的收盘价 {bars[-1].close:,.2f} 不能用（要是大于 0 的有限数）")
        else:
            ref[coin.research] = bars[-1].close
    if not problems:
        return ref, None
    day = datetime.fromtimestamp((day_start - DAY_MS) / 1000, UTC).strftime("%Y-%m-%d")
    return ref, (
        f"验证期推迟开始：对照组合按 {day} 的现货日线收盘价买入，{'，'.join(problems)}；"
        "这次照常交易，下次执行再试"
    )


def _unusable_alert(inst: str, price: float, atr_value: float, when: str) -> str:
    """The alert of a quote ``rules.usable_quote`` refuses; ``when`` is the round its
    contract sits out."""
    return (
        f"报价不能用：{inst} 现价 {price:,.2f}，ATR {atr_value:,.2f}，都要是大于 0 的有限数；"
        f"这个币{when}不交易，止损也不按它调整"
    )


def _kill_alert(equity: float, peak: float, resume: str) -> str:
    """The kill switch's alert, naming ``resume``, the command that lifts it."""
    return (
        f"熔断：净值 {equity:,.2f} 比峰值 {peak:,.2f} 回撤 {rules.drawdown(equity, peak):.1%}，"
        f"已全部平仓并停止交易。确认后运行 {resume} 恢复。"
    )
