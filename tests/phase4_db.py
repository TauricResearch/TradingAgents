"""The screener's test database (``tests/screener_db.py``) plus a peer group.

Capital Goods gains twelve companies around GROWCO (about Rs 3,770 Cr): nine
whose market caps sit near it, 800 to 15,000 Cr, and three far from it (20,
300,000 and 500,000 Cr), so the ten nearest by ratio are GROWCO and the nine.
Financial Services gains a second bank beside LENDERBANK, and UNCLASSED has
prices but no industry. Each new stock trades at a flat Rs 100 for the last
thirty weekdays, so its market cap is just its share count times 100.
"""

from __future__ import annotations

from datetime import timedelta

from tests import screener_db as fx
from tradingagents.dataflows.vendors.india import store

CR = fx.CR
NEAR = {"NEAR0800": 800, "NEAR1500": 1500, "NEAR2500": 2500, "NEAR3000": 3000, "NEAR4000": 4000,
        "NEAR5000": 5000, "NEAR6000": 6000, "NEAR9000": 9000, "NEAR15000": 15000}
FAR = {"TINY20": 20, "HUGE300K": 300000, "HUGE500K": 500000}
OTHERBANK, UNCLASSED = "INE000B02018", "INE000U01019"


ISINS = {s: f"INE9{i:02d}C01{i:03d}"[:12] for i, s in enumerate([*NEAR, *FAR])}


def _recent_days(n: int = 30):
    day, out = fx.LAST_PRICE_DAY, []
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day -= timedelta(days=1)
    return sorted(out)


def build(path) -> None:
    fx.build(path)
    conn = store.connect(path)
    rows, prices = [], []
    days = _recent_days()
    for symbol, cap in {**NEAR, **FAR}.items():
        isin = ISINS[symbol]
        rows.append({"isin": isin, "nse_symbol": symbol, "name": f"{symbol.title()} Industries", "series": "EQ",
                     "face_value": 10.0, "industry": "Capital Goods", "status": "listed"})
        store.record_shares(conn, isin, "2024-01-01", int(cap * CR / 100), 10.0, "NSE PR (mcap)")
        prices += [(isin, d.isoformat(), 100.0, 101.0, 99.0, 100.0, 10_000, "EQ", "test") for d in days]
    rows.append({"isin": OTHERBANK, "nse_symbol": "OTHERBANK", "name": "Other Bank Limited", "series": "EQ",
                 "face_value": 10.0, "industry": "Financial Services", "status": "listed"})
    rows.append({"isin": UNCLASSED, "nse_symbol": "UNCLASSED", "name": "Unclassed Limited", "series": "EQ",
                 "face_value": 10.0, "status": "listed"})
    for isin, shares in ((OTHERBANK, 500_000_000), (UNCLASSED, 10_000_000)):
        store.record_shares(conn, isin, "2024-01-01", shares, 10.0, "NSE PR (mcap)")
        prices += [(isin, d.isoformat(), 100.0, 101.0, 99.0, 100.0, 10_000, "EQ", "test") for d in days]
    store.upsert_securities(conn, rows)
    store.upsert_prices(conn, prices)
    conn.commit()
    conn.close()
