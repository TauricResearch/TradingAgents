"""The paper market: replays closed minutes over the account and trades it to targets.

``replay`` walks OKX 1-minute candles on from where the last replay stopped. It
fills stops (at the open when a candle gaps through one), books funding at each
settlement, marks equity at every close, tracks the peak, flattens everything
once the drawdown reaches KILL_DRAWDOWN, and snapshots equity at each UTC
midnight. ``execute`` trades between minutes, at the last price.
"""

from __future__ import annotations

from trader import rules
from trader.ledger import Fill, Ledger, Position
from trader.okx import DAY_MS, MINUTE_MS, OKX
from trader.settings import ATR_DAYS, KILL_DRAWDOWN, WATCHLIST, Coin

STALL_MS = 10 * MINUTE_MS


class ReplayStalled(RuntimeError):
    """OKX has served no closed candle for a held contract in the last STALL_MS."""


class Paper:
    def __init__(self, ledger: Ledger, okx: OKX, watchlist: tuple[Coin, ...] = WATCHLIST):
        self.ledger = ledger
        self.okx = okx
        self.watchlist = watchlist

    def equity(self, prices: dict[str, float]) -> float:
        """Cash plus the open positions marked at ``prices``, keyed by contract."""
        return self.ledger.get("cash") + sum(
            p.qty * (prices[inst] - p.entry) for inst, p in self.ledger.positions().items()
        )

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

        # The candle before ``start`` seeds the close that prices funding settled at ``start``.
        bars = {
            inst: {b.ts: b for b in self.okx.bars(inst, "1m", start - MINUTE_MS, end)}
            for inst in positions
        }
        # Equity needs every held contract's close, so replay stops where the
        # shortest candle series does.
        stop_at = min(
            max((ts for ts in series if ts >= start), default=start - MINUTE_MS) + MINUTE_MS
            for series in bars.values()
        )
        if end - stop_at > STALL_MS:
            raise ReplayStalled(f"no closed 1m candles for {sorted(bars)} since {stop_at}")
        if stop_at <= start:
            return []
        events = sorted(
            (e.ts, inst, e.rate) for inst in positions for e in self.okx.funding(inst, start, stop_at)
        )
        last_close = {
            inst: series[start - MINUTE_MS].close if start - MINUTE_MS in series
            else positions[inst].entry
            for inst, series in bars.items()
        }
        halted = self.ledger.get("halted")
        alerts, fills, funding, snapshots = [], [], [], []
        for t in range(start, stop_at, MINUTE_MS):
            # Funding settles at the start of minute t, on the position held then.
            while events and events[0][0] <= t:
                ts, inst, rate = events.pop(0)
                if inst in positions:
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
                    alerts.append(_stop_alert(inst, pos.qty, price, pnl))
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
                alerts.append(_kill_alert(equity, peak))
                equity = cash
            if (t + MINUTE_MS) % DAY_MS == 0:
                snapshots.append((t + MINUTE_MS, equity))
        self.ledger.commit(
            positions=positions, cash=cash, fills=fills, funding=funding, snapshots=snapshots,
            meta={"peak": peak, "halted": halted, "processed_to": stop_at},
        )
        return alerts

    def execute(self, trade_date: str, ratings: dict[str, str | None], now_ms: int) -> list[str]:
        """Trade each contract toward the target its rating sets; return the alerts.

        Call right after ``replay``. ``ratings`` maps research tickers to ratings,
        None for a coin whose research failed. Runs once per trade date, and not
        while halted.
        """
        if self.ledger.executed(trade_date) or self.ledger.get("halted"):
            return []
        cash = self.ledger.get("cash")
        positions = self.ledger.positions()
        day_start = now_ms - now_ms % DAY_MS
        quotes = {}
        for coin in self.watchlist:
            daily = self.okx.bars(
                coin.swap, "1Dutc", day_start - (ATR_DAYS + 5) * DAY_MS, day_start
            )
            atr_value = rules.atr(
                [b.high for b in daily], [b.low for b in daily], [b.close for b in daily]
            )
            quotes[coin.swap] = (self.okx.last_price(coin.swap), atr_value)

        alerts, fills = [], []
        # A stop crossed since the last closed minute fills now; every other stop tightens.
        for inst, pos in list(positions.items()):
            price, atr_value = quotes[inst]
            if rules.stop_fill(pos.qty, pos.stop, price, price, price) is not None:
                fill_price = rules.slipped(price, -pos.qty)
                pnl = _move(positions, inst, 0.0, fill_price, 0.0, now_ms, "stop", fills)
                cash += pnl
                alerts.append(_stop_alert(inst, pos.qty, fill_price, pnl))
            else:
                candidate = rules.initial_stop(price, pos.qty, atr_value)
                pos.stop = rules.tighten(pos.stop, candidate, pos.qty)

        equity = cash + sum(p.qty * (quotes[i][0] - p.entry) for i, p in positions.items())
        units, currents, targets = {}, {}, {}
        for coin in self.watchlist:
            price, atr_value = quotes[coin.swap]
            pos = positions.get(coin.swap)
            currents[coin.swap] = pos.qty * price if pos else 0.0
            units[coin.swap] = rules.unit_notional(equity, atr_value, price)
            targets[coin.swap] = rules.target_notional(
                ratings.get(coin.research), units[coin.swap], currents[coin.swap]
            )
        targets = rules.apply_caps(targets, currents, equity)
        for coin in self.watchlist:
            inst = coin.swap
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

        meta, snapshots = {}, []
        if self.ledger.get("validation_start") is None:
            # The validation period starts with this trade date: the baseline buys
            # at the closes the research saw, and equity is marked as it stood.
            meta["validation_start"] = day_start
            meta["baseline_ref"] = {
                coin.research:
                    self.okx.bars(coin.spot, "1Dutc", day_start - DAY_MS, day_start)[-1].close
                for coin in self.watchlist
            }
            snapshots.append((day_start, equity))
        self.ledger.commit(
            positions=positions, cash=cash, fills=fills, snapshots=snapshots, meta=meta,
            executed=(trade_date, now_ms),
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
) -> float:
    """Move ``inst`` to ``new_qty`` coins at ``price`` (slippage included) and record
    the fill; return the cash it adds, realized PnL less the fee."""
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
    stop = rules.stop_after_trade(old_qty, new_qty, pos.stop if pos else None, price, atr_value)
    if new_qty:
        positions[inst] = Position(new_qty, entry, stop)
    else:
        del positions[inst]
    fills.append(Fill(ts, inst, round(new_qty - old_qty, 12), price, cost, reason, trade_date))
    return realized - cost


def _midnights(start: int, end: int) -> list[int]:
    """UTC midnights M with start < M <= end, in milliseconds."""
    return list(range(start - start % DAY_MS + DAY_MS, end + 1, DAY_MS))


def _stop_alert(inst: str, qty: float, price: float, pnl: float) -> str:
    return f"止损：{inst} {qty:+g} 在 {price:,.2f} 平仓，盈亏 {pnl:+,.2f} USDT"


def _kill_alert(equity: float, peak: float) -> str:
    return (
        f"熔断：净值 {equity:,.2f} 比峰值 {peak:,.2f} 回撤 {rules.drawdown(equity, peak):.1%}，"
        "已全部平仓并停止交易。确认后运行 python -m trader resume 恢复。"
    )
