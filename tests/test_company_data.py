"""Company dossier arithmetic: Borsa Istanbul's year-to-date filings, TTM, the
point-in-time filter and KAP's embedded record. All offline."""
from __future__ import annotations

import json

import pytest

from tradingagents.dataflows import company_data
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors import bist


def _table(ends, values):
    return {"columns": [e[:7].replace("-", "/") for e in ends], "period_ends": ends,
            "months": [int(e[5:7]) for e in ends],
            "rows": [{"code": "3C", "label": "Satış Gelirleri", "label_en": "Net Sales", "level": 0, "values": values}]}


@pytest.mark.unit
def test_single_quarters_are_differences_of_year_to_date_filings():
    t = _table(["2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31"], [690.0, 408.0, 176.0, 1100.0])
    out = bist.discrete_quarters(t)
    # Q3 = 9M - 6M, Q2 = 6M - 3M, Q1 as filed; Q4 2025 has no 9M 2025 here, so it stays empty
    assert out["rows"][0]["values"] == [282.0, 232.0, 176.0, None]


@pytest.mark.unit
def test_ttm_from_year_to_date_adds_last_year_and_drops_the_same_period_a_year_ago():
    cum = {"2026-06-30": {"revenue": 585.0}, "2025-06-30": {"revenue": 408.0}}
    annual = {"2025-12-31": {"revenue": 1188.0}}
    out, end = company_data.ttm(cum, annual)
    assert end == "2026-06-30"
    assert out["revenue"] == pytest.approx(585.0 + 1188.0 - 408.0)


@pytest.mark.unit
def test_ttm_at_a_fiscal_year_end_is_the_year():
    out, end = company_data.ttm({"2025-12-31": {"revenue": 1188.0}}, {})
    assert (out["revenue"], end) == (1188.0, "2025-12-31")


@pytest.mark.unit
def test_a_past_run_sees_only_periods_whose_filing_deadline_had_passed():
    t = _table(["2025-06-30", "2025-03-31", "2024-12-31"], [1.0, 2.0, 3.0])
    # 2025-06-01: Q1 (61 days) not yet due by the 70-day rule, FY2024 (152 days) due
    out = bist.withhold_unfiled(t, "2025-06-01", quarterly=True)
    assert out["period_ends"] == ["2024-12-31"]
    assert out["rows"][0]["values"] == [3.0]


@pytest.mark.unit
def test_kap_record_is_read_by_item_key():
    record = {"itemObject": {"itemKey": "kpy41_acc5_sermayede_dogrudan", "value": [
        {"shareholder": "TÜRKİYE VARLIK FONU", "ratioInCapital": "49,12", "votingRightRatio": "49,12", "shareInCapital": "677.884.848,57"},
        {"shareholder": "TOPLAM", "ratioInCapital": "100"}]}}
    text = json.dumps(record, ensure_ascii=False)
    # Next.js pushes the page data as JSON-string chunks; a record may straddle two of them
    html = "".join(f"<script>self.__next_f.push([1,{json.dumps(part)}])</script>" for part in (text[:40], text[40:]))
    items = bist._kap_items(html)
    assert items["kpy41_acc5_sermayede_dogrudan"]["value"][0]["shareholder"] == "TÜRKİYE VARLIK FONU"
    assert bist._kap_items(text)["kpy41_acc5_sermayede_dogrudan"]["value"][1]["shareholder"] == "TOPLAM"
    assert bist._tr_num("677.884.848,57") == pytest.approx(677884848.57)
    assert bist._tr_num("49,12") == pytest.approx(49.12)


@pytest.mark.unit
def test_non_equities_are_refused_and_suffixes_decide_the_market():
    with pytest.raises(ValueError):
        company_data.market_of("EURUSD=X")
    with pytest.raises(ValueError):
        company_data.market_of("BTC-USD")
    assert company_data.market_of("THYAO.IS") == "BIST"
    assert company_data.resolve("thyao.e") == ("THYAO.IS", "BIST")
    assert company_data.market_of("7203.T") == "OTHER"


@pytest.mark.unit
def test_bist_router_entry_points_decline_other_markets():
    for fn in (bist.get_balance_sheet, bist.get_income_statement, bist.get_cashflow):
        with pytest.raises(NoMarketDataError):
            fn("AAPL", "annual", None)


@pytest.mark.unit
def test_bank_ratios_skip_industrial_lines():
    annual = {"2025-12-31": {"net": 50.0, "equity": 250.0, "assets": 2500.0, "loans": 900.0, "deposits": 1000.0},
              "2024-12-31": {"net": 40.0, "equity": 200.0, "assets": 2000.0, "loans": 700.0, "deposits": 900.0}}
    hist = company_data.ratio_history(annual, bank=True)
    labels = [r["label"] for r in hist["rows"]]
    assert "Kredi / mevduat (x)" in labels and not any(lbl.startswith("Brüt") for lbl in labels)
    roe = next(r for r in hist["rows"] if r["label"].startswith("Özkaynak"))
    assert roe["values"][0] == pytest.approx(20.0)
