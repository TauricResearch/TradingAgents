"""Unit tests for the EastMoney direct-HTTP A-share specialty adapters."""

from __future__ import annotations

import pytest

from tradingagents.dataflows import china_specialty_em
from tradingagents.dataflows.china_data import ChinaDataUnavailableError


def test_dragon_tiger_em_parses_records_and_seats(monkeypatch):
    records = [
        {"TRADE_DATE": "2026-07-20", "EXPLANATION": "日涨幅偏离值达7%", "BILLBOARD_NET_AMT": 50000000, "TURNOVERRATE": "3.2"},
    ]
    buy_seats = [{"OPERATEDEPT_NAME": "机构专用", "BUY": 30000000, "SELL": 0, "NET": 30000000}]
    sell_seats = [{"OPERATEDEPT_NAME": "营业部A", "BUY": 0, "SELL": 20000000, "NET": -20000000}]

    def fake_datacenter(report_name, **kwargs):
        if report_name == "RPT_DAILYBILLBOARD_DETAILSNEW":
            return records
        if report_name == "RPT_BILLBOARD_DAILYDETAILSBUY":
            return buy_seats
        if report_name == "RPT_BILLBOARD_DAILYDETAILSSELL":
            return sell_seats
        return []

    monkeypatch.setattr(china_specialty_em, "_eastmoney_datacenter", fake_datacenter)

    report = china_specialty_em.get_a_share_dragon_tiger_em("000001", "2026-07-20")

    assert "Source: eastmoney" in report
    assert "2026-07-20" in report
    assert "机构专用" in report
    assert "TOP5 buy/sell seats" in report


def test_dragon_tiger_em_raises_on_empty(monkeypatch):
    monkeypatch.setattr(china_specialty_em, "_eastmoney_datacenter", lambda *a, **kw: [])
    with pytest.raises(ChinaDataUnavailableError, match="no dragon-tiger records"):
        china_specialty_em.get_a_share_dragon_tiger_em("000001", "2026-07-20")


def test_lockup_releases_em_parses_history_and_upcoming(monkeypatch):
    history = [{"FREE_DATE": "2026-01-15", "FREE_SHARES_TYPE": "定向增发", "FREE_SHARES": 1000, "ABLE_FREE_SHARES": 800, "FREE_RATIO": 0.1}]
    upcoming = [{"FREE_DATE": "2026-08-01", "FREE_SHARES_TYPE": "股权激励", "FREE_SHARES": 500, "ABLE_FREE_SHARES": 500, "FREE_RATIO": 0.05}]

    def fake_datacenter(report_name, **kwargs):
        filter_str = kwargs.get("filter_str", "")
        return upcoming if "FREE_DATE>=" in filter_str else history

    monkeypatch.setattr(china_specialty_em, "_eastmoney_datacenter", fake_datacenter)

    report = china_specialty_em.get_a_share_lockup_releases_em("000001", "2026-07-01", "2026-12-31")

    assert "history" in report
    assert "upcoming" in report
    assert "定向增发" in report
    assert "股权激励" in report


def test_bulk_trades_em_parses_premium(monkeypatch):
    data = [
        {
            "TRADE_DATE": "2026-07-20",
            "DEAL_PRICE": 10.5,
            "CLOSE_PRICE": 10.0,
            "DEAL_VOLUME": 100,
            "DEAL_AMT": 1050,
            "BUYER_NAME": "买方",
            "SELLER_NAME": "卖方",
        }
    ]
    monkeypatch.setattr(china_specialty_em, "_eastmoney_datacenter", lambda *a, **kw: data)

    report = china_specialty_em.get_a_share_bulk_trades_em("000001", "2026-07-01", "2026-07-31")

    assert "Premium %" in report
    assert "买方" in report


def test_shareholder_counts_em_parses(monkeypatch):
    data = [{"END_DATE": "2026-06-30", "HOLDER_NUM": 10000, "HOLDER_NUM_CHANGE": -500, "HOLDER_NUM_RATIO": -4.76, "AVG_HOLD_NUM": 1000}]
    monkeypatch.setattr(china_specialty_em, "_eastmoney_datacenter", lambda *a, **kw: data)

    report = china_specialty_em.get_a_share_shareholder_counts_em("000001")

    assert "Holder Num" in report
    assert "10000" in report


def test_limit_up_ladder_em_parses_pool(monkeypatch):
    pool = [
        {
            "c": "000001",
            "n": "平安银行",
            "p": 15000,
            "zdp": 10.0,
            "lbc": 2,
            "fund": 500000000,
            "zbc": 0,
            "hybk": "银行",
            "zttj": {"days": 2, "ct": 2},
        }
    ]
    monkeypatch.setattr(china_specialty_em, "_em_zt_pool", lambda date: pool)

    report = china_specialty_em.get_a_share_limit_up_ladder_em("2026-07-20")

    assert "平安银行" in report
    assert "Source: eastmoney" in report


def test_limit_up_ladder_em_raises_on_empty(monkeypatch):
    monkeypatch.setattr(china_specialty_em, "_em_zt_pool", lambda date: [])
    with pytest.raises(ChinaDataUnavailableError, match="no limit-up pool"):
        china_specialty_em.get_a_share_limit_up_ladder_em("2026-07-20")


def test_daily_dragon_tiger_em_parses(monkeypatch):
    data = [
        {
            "SECURITY_CODE": "000001",
            "SECURITY_NAME_ABBR": "平安银行",
            "EXPLANATION": "日涨幅偏离值",
            "CLOSE_PRICE": 15.0,
            "CHANGE_RATE": 10.0,
            "BILLBOARD_NET_AMT": 50000000,
            "BILLBOARD_BUY_AMT": 80000000,
            "BILLBOARD_SELL_AMT": 30000000,
        }
    ]
    monkeypatch.setattr(china_specialty_em, "_eastmoney_datacenter", lambda *a, **kw: data)

    report = china_specialty_em.get_a_share_daily_dragon_tiger("2026-07-20")

    assert "平安银行" in report
    assert "Net Buy (wan)" in report


def test_specialty_em_rejects_non_a_share():
    with pytest.raises(ChinaDataUnavailableError, match="not recognized as an A-share"):
        china_specialty_em.get_a_share_dragon_tiger_em("AAPL", "2026-07-20")


def test_dragon_tiger_official_parses_szse(monkeypatch):
    class _FakeResp:
        text = ""

        def json(self):
            return [{"data": [{"zqdm": "000001", "zqjc": "平安银行", "cjje": "100000000", "plyy": "日涨幅偏离值"}]}]

    monkeypatch.setattr(china_specialty_em.requests, "get", lambda *a, **kw: _FakeResp())

    report = china_specialty_em.get_a_share_dragon_tiger_official("2026-07-20")

    assert "SZSE" in report
    assert "平安银行" in report


def test_dragon_tiger_official_raises_when_all_empty(monkeypatch):
    class _FakeResp:
        text = ""

        def json(self):
            return []

    monkeypatch.setattr(china_specialty_em.requests, "get", lambda *a, **kw: _FakeResp())

    with pytest.raises(ChinaDataUnavailableError, match="no data"):
        china_specialty_em.get_a_share_dragon_tiger_official("2026-07-20")


def test_break_board_pool_parses(monkeypatch):
    pool = [{"c": "000001", "n": "平安银行", "p": 15000, "ztp": 16500, "zdp": -5.0, "hs": 3.2, "zbc": 2, "zf": 8.5, "zs": -2.1, "hybk": "银行"}]
    monkeypatch.setattr(china_specialty_em, "_em_zt_api", lambda endpoint, sort, date: pool)

    report = china_specialty_em.get_a_share_break_board_pool("2026-07-22")

    assert "平安银行" in report
    assert "break-board" in report


def test_limit_down_pool_parses(monkeypatch):
    pool = [{"c": "000002", "n": "万科A", "p": 9000, "zdp": -10.0, "hs": 2.1, "fund": 100000000, "days": 1, "oc": 0, "hybk": "地产"}]
    monkeypatch.setattr(china_specialty_em, "_em_zt_api", lambda endpoint, sort, date: pool)

    report = china_specialty_em.get_a_share_limit_down_pool("2026-07-22")

    assert "万科A" in report
    assert "limit-down" in report


def test_prev_limit_up_pool_parses(monkeypatch):
    pool = [{"c": "000003", "n": "示例股", "p": 10000, "zdp": 5.0, "hs": 4.0, "zf": 6.0, "zs": 1.5, "ylbc": 2, "hybk": "科技"}]
    monkeypatch.setattr(china_specialty_em, "_em_zt_api", lambda endpoint, sort, date: pool)

    report = china_specialty_em.get_a_share_prev_limit_up_pool("2026-07-22")

    assert "示例股" in report
    assert "previous-day limit-up" in report


def test_break_board_pool_raises_on_empty(monkeypatch):
    monkeypatch.setattr(china_specialty_em, "_em_zt_api", lambda endpoint, sort, date: [])
    with pytest.raises(ChinaDataUnavailableError, match="no break-board pool"):
        china_specialty_em.get_a_share_break_board_pool("2026-07-22")


def test_research_reports_parses(monkeypatch):
    payload = {
        "data": [
            {
                "publishDate": "2026-07-20",
                "orgSName": "中信",
                "title": "买入评级",
                "emRatingName": "买入",
                "predictThisYearEps": 2.5,
                "predictNextYearEps": 3.0,
                "indvInduName": "银行",
            }
        ],
        "TotalPage": 1,
    }
    monkeypatch.setattr(china_specialty_em, "em_get", lambda *a, **kw: payload)

    report = china_specialty_em.get_a_share_research_reports("000001")

    assert "中信" in report
    assert "买入" in report
    assert "Source: eastmoney" in report


def test_research_reports_raises_on_empty(monkeypatch):
    monkeypatch.setattr(china_specialty_em, "em_get", lambda *a, **kw: {"data": [], "TotalPage": 1})
    with pytest.raises(ChinaDataUnavailableError, match="no research reports"):
        china_specialty_em.get_a_share_research_reports("000001")


def test_eps_forecast_parses(monkeypatch):
    html = '<html><body><table><tr><th>年度</th><th>每股收益均值</th></tr><tr><td>2026</td><td>2.5</td></tr></table></body></html>'

    class _FakeResp:
        text = html
        encoding = "gbk"

    monkeypatch.setattr(china_specialty_em.requests, "get", lambda *a, **kw: _FakeResp())

    report = china_specialty_em.get_a_share_eps_forecast("000001")

    assert "2026" in report
    assert "Source: ths" in report


def test_eps_forecast_rejects_non_a_share():
    with pytest.raises(ChinaDataUnavailableError, match="not recognized as an A-share"):
        china_specialty_em.get_a_share_eps_forecast("AAPL")


def test_industry_ranking_parses(monkeypatch):
    payload = {
        "data": {
            "diff": [
                {"f14": "银行", "f3": 2.5, "f12": "BK0448", "f104": 30, "f105": 10, "f140": "平安银行", "f136": 5.0},
                {"f14": "地产", "f3": -1.0, "f12": "BK0451", "f104": 5, "f105": 50, "f140": "万科A", "f136": -2.0},
            ]
        }
    }
    monkeypatch.setattr(china_specialty_em, "em_get", lambda *a, **kw: payload)

    report = china_specialty_em.get_a_share_industry_ranking()

    assert "银行" in report
    assert "Source: eastmoney" in report


def test_industry_ranking_raises_on_empty(monkeypatch):
    monkeypatch.setattr(china_specialty_em, "em_get", lambda *a, **kw: {"data": {"diff": []}})
    with pytest.raises(ChinaDataUnavailableError, match="no industry-board"):
        china_specialty_em.get_a_share_industry_ranking()


def test_concept_blocks_parses(monkeypatch):
    payload = {
        "data": {
            "diff": {
                "1": {"f14": "白酒", "f12": "BK0477", "f3": 3.0, "f128": "贵州茅台"},
                "2": {"f14": "食品饮料", "f12": "BK0438", "f3": 2.0, "f128": "五粮液"},
            }
        }
    }
    monkeypatch.setattr(china_specialty_em, "em_get", lambda *a, **kw: payload)

    report = china_specialty_em.get_a_share_concept_blocks("600519")

    assert "白酒" in report
    assert "贵州茅台" in report


def test_concept_blocks_rejects_non_a_share():
    with pytest.raises(ChinaDataUnavailableError, match="not recognized as an A-share"):
        china_specialty_em.get_a_share_concept_blocks("AAPL")
