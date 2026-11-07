"""The intraday paper market: trades the hourly account toward the targets its signals set.

``IntradayPaper`` replays minutes, marks equity, snapshots midnights, kills on the
drawdown limit and resumes exactly as the daily ``Paper`` does. Only ``execute``
differs: it runs every hour, measures the ATR on closed hourly candles, sizes and
stops with the constants in ``trader.intraday.settings``, flattens on a Flat
signal whatever the rebalance threshold says, and records no execution row (the
job keeps the decided hour in meta instead).
"""

from __future__ import annotations

from datetime import UTC, datetime

from trader import rules
from trader.intraday.settings import (
    ATR_BAR,
    ATR_BARS,
    REBALANCE_THRESHOLD,
    RISK_PER_UNIT,
    STOP_ATR_MULT,
    WEIGHTS,
)
from trader.okx import DAY_MS
from trader.paper import Paper, _move, _stop_alert

HOUR_MS = 3_600_000


class IntradayPaper(Paper):
    def execute(self, signals: dict[str, str | None], now_ms: int) -> list[str]:
        """Trade each contract toward the target its signal sets; return the alerts.

        Call right after ``replay``, once per hour (the job sees to that). ``signals``
        maps research tickers to "Long", "Short", "Flat", or None for a coin whose
        signal failed, which keeps its position. Does nothing while halted.

        The ATR is measured on the ATR_BARS hourly candles closed before this hour.
        A stop crossed since the last closed minute fills now; every other stop
        tightens to STOP_ATR_MULT ATRs from the last price. A Flat signal closes a
        position however small; any other change below REBALANCE_THRESHOLD units
        is skipped. The first execution starts the validation period at this UTC
        day's midnight and fixes the baseline at the spot closes of the day before.
        """
        if self.ledger.get("halted"):
            return []
        cash = self.ledger.get("cash")
        positions = self.ledger.positions()
        hour = now_ms - now_ms % HOUR_MS
        quotes = {}
        for coin in self.watchlist:
            hourly = self.okx.bars(coin.swap, ATR_BAR, hour - (ATR_BARS + 5) * HOUR_MS, hour)
            atr_value = rules.atr(
                [b.high for b in hourly], [b.low for b in hourly], [b.close for b in hourly],
                days=ATR_BARS,
            )
            quotes[coin.swap] = (self.okx.last_price(coin.swap), atr_value)

        alerts, fills = [], []
        for inst, pos in list(positions.items()):
            price, atr_value = quotes[inst]
            if rules.stop_fill(pos.qty, pos.stop, price, price, price) is not None:
                fill_price = rules.slipped(price, -pos.qty)
                pnl = _move(positions, inst, 0.0, fill_price, 0.0, now_ms, "stop", fills)
                cash += pnl
                alerts.append(_stop_alert(inst, pos.qty, fill_price, pnl))
            else:
                candidate = rules.initial_stop(price, pos.qty, atr_value, stop_mult=STOP_ATR_MULT)
                pos.stop = rules.tighten(pos.stop, candidate, pos.qty)

        equity = cash + sum(p.qty * (quotes[i][0] - p.entry) for i, p in positions.items())
        units, currents, targets = {}, {}, {}
        for coin in self.watchlist:
            price, atr_value = quotes[coin.swap]
            pos = positions.get(coin.swap)
            currents[coin.swap] = pos.qty * price if pos else 0.0
            units[coin.swap] = rules.unit_notional(
                equity, atr_value, price, risk=RISK_PER_UNIT, stop_mult=STOP_ATR_MULT
            )
            targets[coin.swap] = rules.target_notional(
                signals.get(coin.research), units[coin.swap], currents[coin.swap], weights=WEIGHTS
            )
        targets = rules.apply_caps(targets, currents, equity)
        trade_date = utc_date(hour)
        for coin in self.watchlist:
            inst = coin.swap
            flatten = signals.get(coin.research) == "Flat" and inst in positions
            if not flatten and not rules.needs_trade(
                targets[inst], currents[inst], units[inst], threshold=REBALANCE_THRESHOLD
            ):
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
            # The validation period starts with this UTC day: the baseline buys at
            # the spot closes of the day before, and equity is marked as it stood.
            day_start = now_ms - now_ms % DAY_MS
            meta["validation_start"] = day_start
            meta["baseline_ref"] = {
                coin.research:
                    self.okx.bars(coin.spot, "1Dutc", day_start - DAY_MS, day_start)[-1].close
                for coin in self.watchlist
            }
            snapshots.append((day_start, equity))
        self.ledger.commit(
            positions=positions, cash=cash, fills=fills, snapshots=snapshots, meta=meta
        )
        return alerts


def utc_date(ms: int) -> str:
    """The UTC date, "YYYY-MM-DD", of a millisecond timestamp."""
    return datetime.fromtimestamp(ms / 1000, UTC).date().isoformat()
