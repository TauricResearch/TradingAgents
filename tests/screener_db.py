"""A small India database for the screener's tests, written row by row (no XBRL).

GROWCO     a manufacturer: six fiscal years (FY2021-FY2026) growing 10% a year,
           five quarters to June 2026, balance sheets and cash flows each year,
           a 2:1 split (face value 10 -> 5) on 2 June 2025, three dividends,
           five shareholding patterns, and daily prices from September 2020.
           FY2025's sales are restated by a later filing (20 November 2025).
LENDERBANK a bank (banking results format): FY2025 and FY2026, prices.
NODATA     listed, with no prices, filings or shareholding at all.

Every figure is in rupees as the filings store them; ``CR`` converts crores.
"""

from __future__ import annotations

from datetime import date, timedelta

from tradingagents.dataflows.vendors.india import store

CR = 1e7
GROWCO, BANK, NODATA = "INE000G01016", "INE000L01011", "INE000N01014"
FY_SALES = {2021: 1000.0, 2022: 1100.0, 2023: 1210.0, 2024: 1331.0, 2025: 1464.1, 2026: 1610.51}
QUARTER_SALES = {"2025-06-30": 380.0, "2025-09-30": 395.0, "2025-12-31": 410.0, "2026-03-31": 425.51,
                 "2026-06-30": 440.0}
RESTATED_FY2025_SALES = 1469.1
SPLIT_DAY = "2025-06-02"
LAST_PRICE_DAY = date(2026, 10, 2)


def income(sales_cr: float, shares: float, face_value: float) -> dict:
    """An income statement in the shape the XBRL import stores (rupees)."""
    s = sales_cr * CR
    pbt = 0.21 * s
    net = 0.75 * pbt
    return {"sales": s, "total_expenses": 0.80 * s, "depreciation": 0.03 * s, "interest": 0.01 * s,
            "other_income": 0.02 * s, "pbt": pbt, "tax": 0.25 * pbt, "net_profit": net, "net_income": net,
            "eps": net / shares, "cogs": 0.50 * s, "face_value": face_value}


def balance(sales_cr: float) -> dict:
    s = sales_cr * CR
    return {"share_capital": 100 * CR, "equity": 0.6 * s, "total_debt": 50 * CR, "total_assets": 1.2 * s,
            "current_assets": 0.5 * s, "current_liabilities": 0.25 * s, "cash": 0.05 * s, "receivables": 0.1 * s,
            "inventory": 0.08 * s, "payables": 0.06 * s, "net_ppe": 0.4 * s}


def cashflow(sales_cr: float) -> dict:
    s = sales_cr * CR
    return {"operating": 0.18 * s, "investing": -0.08 * s, "financing": -0.05 * s, "capex": 0.06 * s,
            "free_cash_flow": 0.12 * s}


def _file(conn, isin, filing_id, filed_at, rows, fmt="indas", period_end=None):
    store.upsert_filing(conn, filing_id=filing_id, isin=isin, kind="results", format=fmt, basis="consolidated",
                        period_end=period_end or rows[0][0], filed_at=filed_at, filed_at_basis="test", symbol=None,
                        scrip_code=None, taxonomy="test", url=None, raw_path=None, source="test")
    store.upsert_financials(conn, isin=isin, basis="consolidated", filing_id=filing_id, filed_at=filed_at,
                            source="test", rows=rows)


def _rows(end: str, kind: str, start: str | None, fields: dict) -> list[tuple]:
    unit = {"eps": "INR/share", "face_value": "INR/share"}
    return [(end, kind, start, k, float(v), unit.get(k, "INR")) for k, v in fields.items()]


def _weekdays(start: date, end: date):
    day = start
    while day <= end:
        if day.weekday() < 5:
            yield day
        day += timedelta(days=1)


def build(path) -> None:
    conn = store.connect(path)
    store.upsert_securities(conn, [
        {"isin": GROWCO, "nse_symbol": "GROWCO", "name": "Grow Co Limited", "series": "EQ", "face_value": 5.0,
         "industry": "Capital Goods", "status": "listed"},
        {"isin": BANK, "nse_symbol": "LENDERBANK", "name": "Lender Bank Limited", "series": "EQ",
         "face_value": 10.0, "industry": "Financial Services", "status": "listed"},
        {"isin": NODATA, "nse_symbol": "NODATA", "name": "No Data Limited", "series": "EQ", "face_value": 1.0,
         "status": "listed"},
    ])

    # GROWCO's fiscal years: results, the year-end balance sheet and cash flows, in one filing.
    for year, sales in FY_SALES.items():
        end = f"{year}-03-31"
        before_split = f"{year}-05-20" < SPLIT_DAY
        shares, fv = (1e8, 10.0) if before_split else (2e8, 5.0)
        rows = (_rows(end, "A", f"{year - 1}-04-01", {**income(sales, shares, fv), **cashflow(sales)})
                + _rows(end, "I", None, balance(sales)))
        _file(conn, GROWCO, f"GROWCO-FY{year}", f"{year}-05-20T16:00:00", rows)
    restated = income(RESTATED_FY2025_SALES, 1e8, 10.0)
    _file(conn, GROWCO, "GROWCO-FY2025-R", "2025-11-20T10:00:00",
          _rows("2025-03-31", "A", "2024-04-01", {"sales": restated["sales"]}))
    for end, sales in QUARTER_SALES.items():
        d = date.fromisoformat(end)
        filed = (d + timedelta(days=45)).isoformat() + "T18:00:00"
        start = (d.replace(day=1) - timedelta(days=62)).replace(day=1).isoformat()
        shares = 1e8 if filed[:10] < SPLIT_DAY else 2e8
        fields = {k: v for k, v in income(sales, shares, 5.0).items() if k != "face_value"}
        _file(conn, GROWCO, f"GROWCO-Q{end}", filed, _rows(end, "Q", start, fields))

    # The bank: banking format, two years.
    for year, (nii, net, equity, assets) in {2025: (8000.0, 2000.0, 15000.0, 200000.0),
                                            2026: (9000.0, 2400.0, 17000.0, 230000.0)}.items():
        end = f"{year}-03-31"
        p = {"interest_income": 2 * nii * CR, "interest": nii * CR, "net_interest_income": nii * CR,
             "sales": 1.4 * nii * CR, "pbt": net * CR / 0.75, "tax": net * CR / 3, "net_profit": net * CR,
             "net_income": net * CR, "eps": net * CR / 1e9}
        b = {"share_capital": 1000 * CR, "equity": equity * CR, "total_assets": assets * CR,
             "total_debt": 20000 * CR, "deposits": 150000 * CR}
        _file(conn, BANK, f"BANK-FY{year}", f"{year}-04-25T15:00:00",
              _rows(end, "A", f"{year - 1}-04-01", p) + _rows(end, "I", None, b), fmt="banking")

    # Prices: GROWCO's adjusted close rises 0.04% a day; before the split it traded at twice that.
    prices = []
    for i, day in enumerate(_weekdays(date(2020, 9, 1), LAST_PRICE_DAY)):
        base = 100 * 1.0004 ** i
        raw = 2 if day.isoformat() < SPLIT_DAY else 1
        prices.append((GROWCO, day.isoformat(), base * raw, base * raw * 1.01, base * raw * 0.99, base * raw,
                       int(100_000 * (2 / raw)), "EQ", "test"))
        prices.append((BANK, day.isoformat(), 500.0, 505.0, 495.0, 500.0 + (i % 7), 50_000, "EQ", "test"))
    store.upsert_prices(conn, prices)
    store.upsert_action(conn, isin=GROWCO, ex_date=SPLIT_DAY, type="split", details="FV SPLT FRM RS 10 TO RS 5",
                        ratio_num=10, ratio_den=5, factor=2.0, seen="2025-05-20")
    for ex, amount in (("2025-02-03", 4.0), ("2025-11-03", 3.0), ("2026-08-03", 2.5)):
        store.upsert_action(conn, isin=GROWCO, ex_date=ex, type="dividend", details=f"DIV - RS {amount} PER SH",
                            amount=amount, seen=ex)
    store.record_shares(conn, GROWCO, "2024-01-01", 100_000_000, 10.0, "NSE PR (mcap)")
    store.record_shares(conn, GROWCO, SPLIT_DAY, 200_000_000, 5.0, "NSE PR (mcap)")
    store.record_shares(conn, BANK, "2024-01-01", 1_000_000_000, 10.0, "NSE PR (mcap)")
    for day in _weekdays(date(2024, 1, 1), LAST_PRICE_DAY):
        store.log(conn, "actions", day.isoformat(), "ok", rows=0)

    for qe, promoter, fii, dii, holders, pledged in (
            ("2025-06-30", 50.0, 20.0, 10.0, 100_000, 1.0), ("2025-09-30", 50.5, 19.5, 10.5, 105_000, 1.0),
            ("2025-12-31", 51.0, 19.5, 11.0, 110_000, 0.8), ("2026-03-31", 51.5, 19.0, 11.5, 115_000, 0.6),
            ("2026-06-30", 52.0, 19.0, 12.0, 120_000, 0.5)):
        filed = (date.fromisoformat(qe) + timedelta(days=20)).isoformat() + "T12:00:00"
        store.upsert_shareholding(conn, isin=GROWCO, quarter_end=qe, filed_at=filed, filing_id=f"SHP-{qe}",
                                  source="test", values={
                                      "promoter_pct": promoter, "fii_pct": fii, "dii_pct": dii, "govt_pct": 0.0,
                                      "public_pct": 100 - promoter - fii - dii, "others_pct": 0.0,
                                      "num_shareholders": holders, "total_shares": 200_000_000,
                                      "pledged_pct": pledged, "encumbered_pct": pledged})
    conn.commit()
    conn.close()
