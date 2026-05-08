# Portfolio Snapshot — 2026-05-07

**Date:** 2026-05-07
**Status:** User-provided, unverified against live data
**Purpose:** Input for trade calculator — account balances, positions, risk parameters

---

## Cash / Liquid Accounts (IG)

| Account | Balance | Currency | Platform | IG Account ID | Notes |
|---------|---------|----------|----------|---------------|-------|
| Spread Bet | £511.64 | GBP | IG | Z6B1MT | Demo account for test trading |
| ISA | £20,868.50 | GBP | IG | Z6B1MS | 3.75% AER |
| Share Dealing | £9,834.95 | GBP | IG | Z6B1MS | Profit: £419.46 |
| **IG Total** | **£31,215.09** | | | | |

---

## External Accounts (Locked / Not IG)

| Account | Balance | Currency | Type | Notes |
|---------|---------|----------|------|-------|
| AJBell SIPP | £108,221.44 | GBP | SIPP | Policy: ABQPMDS |
| Aviva Cash | £134,761.89 | GBP | Company Pension | Policy: AV2238306-001 |
| NS&I | £15,875.00 | GBP | Premium Bonds | Winnings tax-free |
| Utmost EWA | £34,171.21 | GBP | Pension? | |
| Utmost MSA | £2,697.82 | GBP | Pension? | |
| **External Total** | **£295,727.36** | | | **Not available for IG trading** |

---

## Share Dealing Positions (IG Share Dealing)

| Ticker | Shares | Value | Currency | Exchange | Custody |
|--------|--------|-------|----------|----------|---------|
| thyssenkrupp AG (TKA.DE) | 115 | ~£1,050 | EUR | XETRA | IG Share Dealing |
| Tkms AG & Co KGaA (TKMS.DE) | 5 | ~£340 | EUR | XETRA | IG Share Dealing |
| **Total Share Dealing** | | **~£1,390** | | | |

---

## Platform Summary

| Platform | Type | Cash | Positions | Total Exposure | Tradeable? |
|----------|------|------|-----------|----------------|------------|
| IG — Spread Bet | Demo | £511.64 | — | £511.64 | ✅ Test trades |
| IG — ISA | ISA | £20,868.50 | — | £20,868.50 | ✅ Real trades |
| IG — Share Dealing | Share Dealing | £9,834.95 | TKA.DE, TKMS.DE | ~£11,225 | ✅ Real trades |
| AJBell | SIPP | £108,221.44 | — | £108,221.44 | ❌ Locked until 55 |
| Aviva | Pension | £134,761.89 | — | £134,761.89 | ❌ Employer-matched |
| NS&I | Cash | £15,875.00 | — | £15,875.00 | ❌ Premium bonds only |
| Utmost | Pension? | £36,869.03 | — | £36,869.03 | ❌ Likely locked |

---

## Trade Calculator Defaults

| Parameter | Spread Bet | ISA | Share Dealing |
|-----------|-----------|-----|---------------|
| Account balance | £511.64 | £20,868.50 | £9,834.95 |
| Risk per trade (2%) | £10.23 | £417.37 | £196.70 |
| Min stop distance | 8 pts (FTSE) | 1 pt (AAPL) | 1 pt (AAPL) |
| Margin factor | 5% (FTSE) | 20% (AAPL) | 20% (AAPL) |

**Spread bet demo is tight.** £10.23 risk limits us to:
- Low-priced indices (FTSE at £5/point = 2pt stop)
- Low stake sizes
- Test trades only

**ISA is the primary trading account.** £417 risk per trade is workable for most instruments.

**Share Dealing has existing positions.** New trades from £9,834 cash. 20% margin on AAPL = ~£200 margin per £1,000 notional.
