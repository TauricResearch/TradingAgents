"""Tests for akshare_vendor.py — public functions, pure-logic helpers, edge cases,
error paths, regression checks, and end-to-end integration."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

GROUND_TRUTH_PATH = Path(__file__).parent / "fixtures" / "a_share_ground_truth.json"


@pytest.fixture(scope="module")
def ground_truth() -> dict:
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))["stocks"]


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestToYyyymmdd(TestCase):
    def test_basic_conversion(self):
        from tradingagents.dataflows.akshare_vendor import _to_yyyymmdd
        assert _to_yyyymmdd("2026-05-14") == "20260514"

    def test_single_digit_month_day(self):
        from tradingagents.dataflows.akshare_vendor import _to_yyyymmdd
        assert _to_yyyymmdd("2026-01-05") == "20260105"

    def test_leap_year_date(self):
        from tradingagents.dataflows.akshare_vendor import _to_yyyymmdd
        assert _to_yyyymmdd("2024-02-29") == "20240229"


@pytest.mark.unit
class TestYjbbReportDateFor(TestCase):
    def test_may_returns_q1_report(self):
        from tradingagents.dataflows.akshare_vendor import _yjbb_report_date_for
        assert _yjbb_report_date_for("2026-05-14") == "20260331"

    def test_august_returns_q2_report(self):
        from tradingagents.dataflows.akshare_vendor import _yjbb_report_date_for
        assert _yjbb_report_date_for("2026-08-15") == "20260630"

    def test_october_returns_q2_report(self):
        from tradingagents.dataflows.akshare_vendor import _yjbb_report_date_for
        assert _yjbb_report_date_for("2026-10-20") == "20260630"

    def test_november_returns_q3_report(self):
        from tradingagents.dataflows.akshare_vendor import _yjbb_report_date_for
        assert _yjbb_report_date_for("2026-11-01") == "20260930"

    def test_february_returns_prior_year_q3(self):
        from tradingagents.dataflows.akshare_vendor import _yjbb_report_date_for
        assert _yjbb_report_date_for("2026-02-10") == "20250930"

    def test_none_date_uses_current_month(self):
        from tradingagents.dataflows.akshare_vendor import _yjbb_report_date_for
        now = datetime.now()
        result = _yjbb_report_date_for(None)
        y, m = now.year, now.month
        if m >= 11:
            expected = f"{y}0930"
        elif m >= 8:
            expected = f"{y}0630"
        elif m >= 5:
            expected = f"{y}0331"
        else:
            expected = f"{y - 1}0930"
        assert result == expected

    def test_january_returns_prior_year_q3(self):
        from tradingagents.dataflows.akshare_vendor import _yjbb_report_date_for
        assert _yjbb_report_date_for("2026-01-01") == "20250930"


@pytest.mark.unit
class TestSafeCall(TestCase):
    def test_success_returns_result(self):
        from tradingagents.dataflows.akshare_vendor import _safe_call
        func = MagicMock(return_value=42)
        assert _safe_call(func, 1, x=2) == 42
        func.assert_called_once_with(1, x=2)

    def test_exception_returns_none(self):
        from tradingagents.dataflows.akshare_vendor import _safe_call
        func = MagicMock(side_effect=ValueError("boom"))
        result = _safe_call(func)
        assert result is None

    def test_exception_logs_debug(self):
        from tradingagents.dataflows.akshare_vendor import _safe_call
        func = MagicMock(side_effect=RuntimeError("fail"))
        with patch("tradingagents.dataflows.akshare_vendor.logger") as mock_logger:
            result = _safe_call(func)
            assert result is None
            mock_logger.debug.assert_called_once()


@pytest.mark.unit
class TestFormatRowSection(TestCase):
    def test_large_values_use_money_format(self):
        from tradingagents.dataflows.akshare_vendor import _format_row_section
        row = {"TOTAL_ASSETS": 500_000_000_000.0, "NET_PROFIT": 50_000_000_000.0}
        fields = [("TOTAL_ASSETS", "总资产"), ("NET_PROFIT", "净利润")]
        result = _format_row_section(row, fields)
        assert "5000.00亿" in result
        assert "500.00亿" in result

    def test_small_values_use_raw_float(self):
        from tradingagents.dataflows.akshare_vendor import _format_row_section
        row = {"BASIC_EPS": 5.12, "DUMMY": 999.0}
        fields = [("BASIC_EPS", "EPS"), ("DUMMY", "Dummy")]
        result = _format_row_section(row, fields)
        assert "5.1200" in result
        assert "999.0000" in result

    def test_missing_key_skipped(self):
        from tradingagents.dataflows.akshare_vendor import _format_row_section
        result = _format_row_section({"A": 100.0}, [("A", "Item A"), ("B", "Item B")])
        assert "Item A" in result
        assert "Item B" not in result

    def test_none_value_skipped(self):
        from tradingagents.dataflows.akshare_vendor import _format_row_section
        result = _format_row_section({"A": None}, [("A", "Item A")])
        assert "(no fields" in result

    def test_empty_fields_fallback(self):
        from tradingagents.dataflows.akshare_vendor import _format_row_section
        result = _format_row_section({"A": 100.0}, [])
        assert "(no fields" in result


@pytest.mark.unit
class TestBlockTradeStaticReturn(TestCase):
    def test_returns_guided_message(self):
        from tradingagents.dataflows.akshare_vendor import get_block_trade
        result = get_block_trade("600519.SS")
        assert "block-trade" in result or "大宗交易" in result
        assert "akshare" in result


# ---------------------------------------------------------------------------
# get_stock_data
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetStockData(TestCase):
    def setUp(self):
        self.fake_df = pd.DataFrame({
            "日期": ["2026-05-10", "2026-05-13", "2026-05-14"],
            "开盘": [1670.0, 1675.5, 1682.0],
            "收盘": [1680.5, 1681.0, 1683.5],
            "最高": [1690.0, 1685.0, 1690.0],
            "最低": [1665.0, 1670.0, 1678.0],
            "成交量": [120_000, 135_000, 110_000],
        })

    def test_basic_returns_csv_with_header(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_zh_a_hist.return_value = self.fake_df
            result = akshare_vendor.get_stock_data("600519.SS", "2026-05-10", "2026-05-14")
        mock_ak.stock_zh_a_hist.assert_called_once()
        kwargs = mock_ak.stock_zh_a_hist.call_args.kwargs
        assert kwargs["symbol"] == "600519"
        assert kwargs["period"] == "daily"
        assert kwargs["adjust"] == "qfq"
        assert "Stock data for 600519.SS" in result
        assert "1680.5" in result

    def test_empty_df_returns_no_data_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_zh_a_hist.return_value = pd.DataFrame()
            result = akshare_vendor.get_stock_data("600519.SS", "2026-05-10", "2026-05-14")
        assert "No data found" in result

    def test_none_df_returns_no_data_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_zh_a_hist.return_value = None
            result = akshare_vendor.get_stock_data("600519.SS", "2026-05-10", "2026-05-14")
        assert "No data found" in result


# ---------------------------------------------------------------------------
# get_fundamentals
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetFundamentals(TestCase):
    def setUp(self):
        self.info_df = pd.DataFrame({
            "item": ["股票简称", "行业", "总市值", "流通市值", "总股本", "上市时间"],
            "value": ["贵州茅台", "白酒", 2_108_000_000_000.0, 2_100_000_000_000.0, 1_256_000_000, "2001-08-27"],
        })
        self.yjbb_df = pd.DataFrame([{
            "股票代码": "600519",
            "营业总收入-同比增长": 12.5,
            "净利润-同比增长": 15.2,
            "销售毛利率": 91.5,
            "净资产收益率": 18.0,
            "每股收益": 15.78,
            "每股经营现金流量": 14.2,
        }])

    def test_combines_info_and_yjbb(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_individual_info_em.return_value = self.info_df
            mock_ak.stock_yjbb_em.return_value = self.yjbb_df
            result = akshare_vendor.get_fundamentals("600519.SS", "2026-05-14")
        assert "贵州茅台" in result
        assert "白酒" in result
        assert "91.50%" in result
        assert "总市值" in result

    def test_empty_info_uses_yjbb_only(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_individual_info_em.return_value = pd.DataFrame()
            mock_ak.stock_yjbb_em.return_value = self.yjbb_df
            result = akshare_vendor.get_fundamentals("600519.SS", "2026-05-14")
        assert "业绩报表" in result
        assert "12.50%" in result

    def test_empty_yjbb_uses_info_only(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_individual_info_em.return_value = self.info_df
            mock_ak.stock_yjbb_em.return_value = pd.DataFrame()
            result = akshare_vendor.get_fundamentals("600519.SS", "2026-05-14")
        assert "贵州茅台" in result
        assert "营收同比增长" not in result

    def test_both_empty_returns_warning(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_individual_info_em.return_value = pd.DataFrame()
            mock_ak.stock_yjbb_em.return_value = pd.DataFrame()
            result = akshare_vendor.get_fundamentals("600519.SS", "2026-05-14")
        assert "No fundamentals" in result

    def test_yjbb_no_matching_code_skipped(self):
        from tradingagents.dataflows import akshare_vendor
        yjbb_no_match = pd.DataFrame([{"股票代码": "999999", "净利润-同比增长": 5.0}])
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_individual_info_em.return_value = self.info_df
            mock_ak.stock_yjbb_em.return_value = yjbb_no_match
            result = akshare_vendor.get_fundamentals("600519.SS", "2026-05-14")
        assert "贵州茅台" in result
        assert "业绩报表" not in result


# ---------------------------------------------------------------------------
# get_balance_sheet, get_cashflow, get_income_statement
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetBalanceSheet(TestCase):
    def test_basic(self):
        from tradingagents.dataflows import akshare_vendor
        fake_df = pd.DataFrame([{
            "REPORT_DATE": "2026-03-31",
            "TOTAL_ASSETS": 554_600_000_000.0,
            "TOTAL_CURRENT_ASSETS": 442_000_000_000.0,
            "MONETARYFUNDS": 178_000_000_000.0,
            "ACCOUNTS_RECE": 5_000_000.0,
            "INVENTORY": 49_000_000_000.0,
            "FIXED_ASSET": 22_000_000_000.0,
            "TOTAL_LIABILITIES": 102_590_000_000.0,
            "TOTAL_CURRENT_LIAB": 80_000_000_000.0,
            "TOTAL_EQUITY": 452_010_000_000.0,
        }])
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_balance_sheet_by_report_em.return_value = fake_df
            result = akshare_vendor.get_balance_sheet("600519.SS")
        assert "Balance Sheet" in result
        assert "5546.00亿" in result
        assert "1780.00亿" in result
        assert "SH600519" == mock_ak.stock_balance_sheet_by_report_em.call_args.kwargs["symbol"]

    def test_empty_returns_warning(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_balance_sheet_by_report_em.return_value = pd.DataFrame()
            result = akshare_vendor.get_balance_sheet("600519.SS")
        assert "No balance sheet" in result


@pytest.mark.unit
class TestGetCashflow(TestCase):
    def test_basic(self):
        from tradingagents.dataflows import akshare_vendor
        fake_df = pd.DataFrame([{
            "REPORT_DATE": "2026-03-31",
            "NETCASH_OPERATE": 23_000_000_000.0,
            "NETCASH_INVEST": -5_000_000_000.0,
            "NETCASH_FINANCE": -8_000_000_000.0,
            "CCE_ADD": 10_000_000_000.0,
            "END_CCE": 150_000_000_000.0,
        }])
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_cash_flow_sheet_by_report_em.return_value = fake_df
            result = akshare_vendor.get_cashflow("600519.SS")
        assert "Cash Flow" in result
        assert "230.00亿" in result
        assert "-50.00亿" in result
        assert "SH600519" == mock_ak.stock_cash_flow_sheet_by_report_em.call_args.kwargs["symbol"]

    def test_empty_returns_warning(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_cash_flow_sheet_by_report_em.return_value = pd.DataFrame()
            result = akshare_vendor.get_cashflow("600519.SS")
        assert "No cash flow" in result


@pytest.mark.unit
class TestGetIncomeStatement(TestCase):
    def test_basic(self):
        from tradingagents.dataflows import akshare_vendor
        fake_df = pd.DataFrame([{
            "REPORT_DATE": "2026-03-31",
            "TOTAL_OPERATE_INCOME": 41_580_000_000.0,
            "OPERATE_INCOME": 41_580_000_000.0,
            "OPERATE_COST": 4_158_000_000.0,
            "OPERATE_PROFIT": 26_530_000_000.0,
            "TOTAL_PROFIT": 26_400_000_000.0,
            "PARENT_NETPROFIT": 19_840_000_000.0,
            "DEDUCT_PARENT_NETPROFIT": 19_800_000_000.0,
            "BASIC_EPS": 15.78,
            "DILUTED_EPS": 15.77,
        }])
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_profit_sheet_by_report_em.return_value = fake_df
            result = akshare_vendor.get_income_statement("600519.SS")
        assert "Income Statement" in result
        assert "415.80亿" in result
        assert "198.40亿" in result
        assert "15.7800" in result
        assert "akshare" in result.lower()
        assert "SH600519" == mock_ak.stock_profit_sheet_by_report_em.call_args.kwargs["symbol"]

    def test_empty_returns_warning(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_profit_sheet_by_report_em.return_value = pd.DataFrame()
            result = akshare_vendor.get_income_statement("600519.SS")
        assert "No income statement" in result


# ---------------------------------------------------------------------------
# get_indicators
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetIndicators(TestCase):
    def setUp(self):
        self.kline_df = pd.DataFrame({
            "日期": pd.date_range("2026-04-01", periods=30, freq="D"),
            "开盘": [1500.0 + i for i in range(30)],
            "收盘": [1510.0 + i for i in range(30)],
            "最高": [1520.0 + i for i in range(30)],
            "最低": [1490.0 + i for i in range(30)],
            "成交量": [100_000 + i * 1000 for i in range(30)],
        })

    def test_returns_indicator_values(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_zh_a_hist.return_value = self.kline_df
            result = akshare_vendor.get_indicators("600519.SS", "rsi_14", "2026-04-30", look_back_days=20)
        assert "rsi_14" in result.lower()
        assert "600519.SS" in result
        assert mock_ak.stock_zh_a_hist.call_args.kwargs["symbol"] == "600519"

    def test_empty_kline_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_zh_a_hist.return_value = pd.DataFrame()
            result = akshare_vendor.get_indicators("600519.SS", "rsi_14", "2026-04-30", look_back_days=20)
        assert "No K-line data" in result

    def test_none_kline_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_zh_a_hist.return_value = None
            result = akshare_vendor.get_indicators("600519.SS", "rsi_14", "2026-04-30", look_back_days=20)
        assert "No K-line data" in result

    def test_network_error_propagates(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_zh_a_hist.side_effect = ConnectionError("network down")
            with pytest.raises(ConnectionError, match="network down"):
                akshare_vendor.get_indicators("600519.SS", "rsi_14", "2026-04-30", look_back_days=20)


# ---------------------------------------------------------------------------
# get_news
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetNews(TestCase):
    def setUp(self):
        self.news_df = pd.DataFrame([{
            "新闻标题": "贵州茅台业绩超预期",
            "文章来源": "证券时报",
            "新闻内容": "公司发布最新财报...",
            "发布时间": "2026-05-14 08:30:00",
            "新闻链接": "https://example.com/news/1",
        }, {
            "新闻标题": "白酒板块走强",
            "文章来源": "中国证券报",
            "新闻内容": "板块表现强劲...",
            "发布时间": "2026-05-13 10:00:00",
            "新闻链接": "https://example.com/news/2",
        }])

    def test_returns_formatted_news(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_news_em.return_value = self.news_df
            result = akshare_vendor.get_news("600519.SS", "2026-05-10", "2026-05-14")
        assert "贵州茅台业绩超预期" in result
        assert "证券时报" in result
        assert "Published" in result
        assert "Link:" in result

    def test_empty_df_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_news_em.return_value = pd.DataFrame()
            result = akshare_vendor.get_news("600519.SS", "2026-05-10", "2026-05-14")
        assert "No news found" in result

    def test_date_filter_excludes_articles(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_news_em.return_value = self.news_df
            result = akshare_vendor.get_news("600519.SS", "2026-05-01", "2026-05-05")
        assert "No news found" in result

    def test_missing_content_skips_content_line(self):
        from tradingagents.dataflows import akshare_vendor
        df_missing = pd.DataFrame([{
            "新闻标题": "Test Headline",
            "文章来源": "Test",
            "新闻内容": None,
            "发布时间": "2026-05-14 08:30:00",
            "新闻链接": "https://example.com",
        }])
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_news_em.return_value = df_missing
            result = akshare_vendor.get_news("600519.SS", "2026-05-10", "2026-05-15")
        assert "Test Headline" in result


# ---------------------------------------------------------------------------
# get_insider_transactions
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetInsiderTransactions(TestCase):
    def setUp(self):
        self.insider_df = pd.DataFrame([{
            "公告日期": "2026-05-10",
            "变动股东": "控股股东",
            "变动数量": "100,000",
            "交易均价": "1,680.00",
            "剩余股份总数": "500,000,000",
            "变动期间": "2026-05-01~2026-05-10",
            "变动途径": "二级市场买卖",
        }])

    def test_returns_formatted_data(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_shareholder_change_ths.return_value = self.insider_df
            result = akshare_vendor.get_insider_transactions("600519.SS")
        assert "Shareholder Changes" in result
        assert "控股股东" in result
        assert "100,000" in result

    def test_empty_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_shareholder_change_ths.return_value = pd.DataFrame()
            result = akshare_vendor.get_insider_transactions("600519.SS")
        assert "No shareholder change data" in result


# ---------------------------------------------------------------------------
# get_company_announcements
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetCompanyAnnouncements(TestCase):
    def setUp(self):
        self.ann_df = pd.DataFrame([{
            "公告标题": "2026年第一季度报告",
            "公告类型": "定期报告",
            "公告日期": "2026-04-28",
            "网址": "http://example.com/ann",
        }])

    def test_returns_formatted_announcements(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_individual_notice_report.return_value = self.ann_df
            result = akshare_vendor.get_company_announcements("600519.SS", "2026-04-01", "2026-04-30")
        assert "Company Announcements" in result
        assert "第一季度报告" in result
        assert "定期报告" in result
        call_kwargs = mock_ak.stock_individual_notice_report.call_args.kwargs
        assert call_kwargs["security"] == "600519"

    def test_empty_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_individual_notice_report.return_value = pd.DataFrame()
            result = akshare_vendor.get_company_announcements("600519.SS", "2026-04-01", "2026-04-30")
        assert "No company announcements" in result


# ---------------------------------------------------------------------------
# get_fund_flow
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetFundFlow(TestCase):
    def setUp(self):
        self.flow_df = pd.DataFrame([{
            "日期": "2026-05-14",
            "收盘价": 1680.50,
            "涨跌幅": 2.35,
            "主力净流入-净额": 500_000_000.0,
            "主力净流入-净占比": 12.5,
            "超大单净流入-净额": 300_000_000.0,
            "超大单净流入-净占比": 7.5,
            "大单净流入-净额": 200_000_000.0,
            "大单净流入-净占比": 5.0,
            "中单净流入-净额": -100_000_000.0,
            "中单净流入-净占比": -2.5,
            "小单净流入-净额": -400_000_000.0,
            "小单净流入-净占比": -10.0,
        }])

    def test_returns_formatted_flow(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_individual_fund_flow.return_value = self.flow_df
            result = akshare_vendor.get_fund_flow("600519.SS")
        assert "Fund Flow" in result
        assert "Main Force" in result
        assert "Super Large" in result

    def test_empty_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_individual_fund_flow.return_value = pd.DataFrame()
            result = akshare_vendor.get_fund_flow("600519.SS")
        assert "No fund flow data" in result


# ---------------------------------------------------------------------------
# get_northbound_hold
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetNorthboundHold(TestCase):
    def setUp(self):
        self.nb_df = pd.DataFrame([{
            "日期": "2026-05-14",
            "持股数量": 80_000_000,
            "持股市值": 13_500_000_000.0,
            "占流通股比例": 6.5,
            "当日成交净买额": 50_000_000,
        }])

    def test_returns_formatted_data(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_hsgt_individual_em.return_value = self.nb_df
            result = akshare_vendor.get_northbound_hold("600519.SS")
        assert "Northbound" in result
        assert "Stock Connect" in result
        assert "持股数量" in result or "Holding Shares" in result

    def test_empty_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_hsgt_individual_em.return_value = pd.DataFrame()
            result = akshare_vendor.get_northbound_hold("600519.SS")
        assert "No northbound holding data" in result


# ---------------------------------------------------------------------------
# get_restricted_release
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetRestrictedRelease(TestCase):
    def setUp(self):
        self.release_df = pd.DataFrame([{
            "股票代码": "600519",
            "解禁时间": "2026-06-15",
            "限售股类型": "首发原股东限售股份",
            "解禁数量": 10_000_000,
            "实际解禁市值": 16_800_000_000.0,
            "占解禁前流通市值比例": 1.5,
            "解禁前一交易日收盘价": 1680.00,
        }])

    def test_returns_formatted_data(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_restricted_release_detail_em.return_value = self.release_df
            result = akshare_vendor.get_restricted_release("600519.SS", "2026-06-01", "2026-06-30")
        assert "Restricted Share Release" in result
        assert "2026-06-15" in result
        assert "首发原股东限售股份" in result

    def test_no_match_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        df_other = pd.DataFrame([{"股票代码": "999999", "解禁时间": "2026-06-15"}])
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_restricted_release_detail_em.return_value = df_other
            result = akshare_vendor.get_restricted_release("600519.SS", "2026-06-01", "2026-06-30")
        assert "No restricted share release events" in result

    def test_empty_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_restricted_release_detail_em.return_value = pd.DataFrame()
            result = akshare_vendor.get_restricted_release("600519.SS", "2026-06-01", "2026-06-30")
        assert "No restricted share release data" in result


# ---------------------------------------------------------------------------
# get_industry_valuation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetIndustryValuation(TestCase):
    def setUp(self):
        self.info_df = pd.DataFrame({
            "item": ["行业"],
            "value": ["白酒"],
        })
        self.spot_df = pd.DataFrame([{
            "代码": "600519",
            "最新价": 1680.50,
            "市盈率-动态": 25.5,
            "市净率": 6.8,
        }, {
            "代码": "000858",
            "最新价": 150.00,
            "市盈率-动态": 20.0,
            "市净率": 5.0,
        }])
        self.value_df = pd.DataFrame([{
            "PE(TTM)": 24.0,
            "PE(静)": 26.0,
            "PEG值": 1.2,
        }])

    def test_returns_formatted_valuation(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_individual_info_em.return_value = self.info_df
            mock_ak.stock_zh_a_spot_em.return_value = self.spot_df
            mock_ak.stock_value_em.return_value = self.value_df
            result = akshare_vendor.get_industry_valuation("600519.SS")
        assert "Industry Valuation" in result
        assert "白酒" in result
        assert "25.5" in result
        assert "Market Sample Size" in result

    def test_empty_info_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_individual_info_em.return_value = pd.DataFrame()
            result = akshare_vendor.get_industry_valuation("600519.SS")
        assert "No individual info data" in result


# ---------------------------------------------------------------------------
# get_macro_indicators
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetMacroIndicators(TestCase):
    def setUp(self):
        self.macro_df = pd.DataFrame([{
            "月份": "2026-04",
            "制造业-指数": 50.8,
            "制造业-同比增长": 0.5,
            "非制造业-指数": 51.2,
            "非制造业-同比增长": 0.8,
        }])

    def test_pmi(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.macro_china_pmi.return_value = self.macro_df
            result = akshare_vendor.get_macro_indicators("pmi")
        assert "PMI" in result
        assert "50.8" in result

    def test_cpi(self):
        from tradingagents.dataflows import akshare_vendor
        cpi_df = pd.DataFrame([{"月份": "2026-04", "CPI": 100.5}])
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.macro_china_cpi.return_value = cpi_df
            result = akshare_vendor.get_macro_indicators("cpi")
        assert "CPI" in result

    def test_m2(self):
        from tradingagents.dataflows import akshare_vendor
        m2_df = pd.DataFrame([{"月份": "2026-04", "M2": 2_500_000}])
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.macro_china_m2.return_value = m2_df
            result = akshare_vendor.get_macro_indicators("m2")
        assert "M2" in result

    def test_social_finance(self):
        from tradingagents.dataflows import akshare_vendor
        sf_df = pd.DataFrame([{"月份": "2026-04", "社融规模": 500_000}])
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.macro_china_shrzgm.return_value = sf_df
            result = akshare_vendor.get_macro_indicators("social_finance")
        assert "Social Financing" in result

    def test_unsupported_indicator(self):
        from tradingagents.dataflows import akshare_vendor
        result = akshare_vendor.get_macro_indicators("gdp")
        assert "Unsupported" in result

    def test_empty_data_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.macro_china_pmi.return_value = pd.DataFrame()
            result = akshare_vendor.get_macro_indicators("pmi")
        assert "No macro data" in result


# ---------------------------------------------------------------------------
# get_margin_trading
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetMarginTrading(TestCase):
    def setUp(self):
        self.sse_row = {"标的证券代码": "600519", "融资余额": "100亿", "融资买入额": "5亿",
                        "融券余量": "10万", "融券余额": "0.5亿", "融资融券余额": "100.5亿"}

    def test_sse_symbol(self):
        from tradingagents.dataflows import akshare_vendor
        with (
            patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak,
            patch("tradingagents.dataflows.akshare_vendor.to_akshare_symbol",
                  side_effect=lambda s, style: {"bare": "600519", "prefix": "sh"}.get(style, "sh")),
        ):
            mock_ak.tool_trade_date_hist_sina.return_value = pd.DataFrame(
                {"trade_date": ["2026-05-14"]}
            )
            mock_ak.stock_margin_detail_sse.return_value = pd.DataFrame([self.sse_row])
            result = akshare_vendor.get_margin_trading("600519.SS")
        assert "Margin Trading" in result
        assert "融资余额" in result

    def test_szse_symbol(self):
        from tradingagents.dataflows import akshare_vendor
        with (
            patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak,
            patch("tradingagents.dataflows.akshare_vendor.to_akshare_symbol",
                  side_effect=lambda s, style: {"bare": "300454", "prefix": "sz"}.get(style, "sz")),
        ):
            mock_ak.tool_trade_date_hist_sina.return_value = pd.DataFrame(
                {"trade_date": ["2026-05-14"]}
            )
            mock_ak.stock_margin_detail_szse.return_value = pd.DataFrame([{
                "证券代码": "300454", "融资余额": "50亿", "融资买入额": "2亿",
                "融券余量": "5万", "融券余额": "0.2亿", "融资融券余额": "50.2亿",
            }])
            result = akshare_vendor.get_margin_trading("300454.SZ")
        assert "Margin Trading" in result
        assert "融资余额" in result

    def test_unsupported_exchange(self):
        from tradingagents.dataflows import akshare_vendor
        with (
            patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak,
            patch("tradingagents.dataflows.akshare_vendor.to_akshare_symbol",
                  side_effect=lambda s, style: {"bare": "688001", "prefix": "bj"}.get(style, "bj")),
        ):
            mock_ak.tool_trade_date_hist_sina.return_value = pd.DataFrame(
                {"trade_date": ["2026-05-14"]}
            )
            result = akshare_vendor.get_margin_trading("688001.BJ")
        assert "not available" in result

    def test_sse_no_data_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with (
            patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak,
            patch("tradingagents.dataflows.akshare_vendor.to_akshare_symbol",
                  side_effect=lambda s, style: {"bare": "600519", "prefix": "sh"}.get(style, "sh")),
        ):
            mock_ak.tool_trade_date_hist_sina.return_value = pd.DataFrame(
                {"trade_date": ["2026-05-14"]}
            )
            mock_ak.stock_margin_detail_sse.return_value = pd.DataFrame()
            result = akshare_vendor.get_margin_trading("600519.SS")
        assert "No margin-trading data for SSE" in result

    def test_sse_no_matching_code(self):
        from tradingagents.dataflows import akshare_vendor
        with (
            patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak,
            patch("tradingagents.dataflows.akshare_vendor.to_akshare_symbol",
                  side_effect=lambda s, style: {"bare": "600519", "prefix": "sh"}.get(style, "sh")),
        ):
            mock_ak.tool_trade_date_hist_sina.return_value = pd.DataFrame(
                {"trade_date": ["2026-05-14"]}
            )
            mock_ak.stock_margin_detail_sse.return_value = pd.DataFrame([{
                "标的证券代码": "999999", "融资余额": "0",
            }])
            result = akshare_vendor.get_margin_trading("600519.SS")
        assert "No margin-trading data found for 600519.SS" in result


# ---------------------------------------------------------------------------
# get_dragon_tiger
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetDragonTiger(TestCase):
    def test_buy_and_sell_data(self):
        from tradingagents.dataflows import akshare_vendor
        buy_df = pd.DataFrame([{
            "营业部名称": "国泰君安证券",
            "买入金额": "1.5亿",
            "净额": "0.8亿",
        }])
        sell_df = pd.DataFrame([{
            "营业部名称": "中信证券",
            "卖出金额": "1.2亿",
            "净额": "-0.5亿",
        }])
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.tool_trade_date_hist_sina.return_value = pd.DataFrame(
                {"trade_date": ["2026-05-14"]}
            )
            mock_ak.stock_lhb_stock_detail_em.side_effect = [buy_df, sell_df]
            result = akshare_vendor.get_dragon_tiger("600519.SS")
        assert "Dragon Tiger Board" in result
        assert "Buy-side" in result
        assert "Sell-side" in result
        assert "国泰君安" in result
        assert "中信证券" in result

    def test_empty_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.tool_trade_date_hist_sina.return_value = pd.DataFrame(
                {"trade_date": ["2026-05-14"]}
            )
            mock_ak.stock_lhb_stock_detail_em.return_value = pd.DataFrame()
            result = akshare_vendor.get_dragon_tiger("600519.SS")
        assert "No dragon-tiger-board data" in result


# ---------------------------------------------------------------------------
# get_sector_fund_flow
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetSectorFundFlow(TestCase):
    def setUp(self):
        self.sector_df = pd.DataFrame([{
            "日期": "2026-05-14",
            "主力净流入": "50亿",
            "小单净流入": "-10亿",
            "中单净流入": "-20亿",
            "大单净流入": "30亿",
        }])

    def test_returns_formatted_data(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_sector_fund_flow_hist.return_value = self.sector_df
            result = akshare_vendor.get_sector_fund_flow("白酒")
        assert "Sector Fund Flow" in result
        assert "主力净流入" in result

    def test_empty_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_sector_fund_flow_hist.return_value = pd.DataFrame()
            result = akshare_vendor.get_sector_fund_flow("白酒")
        assert "No sector fund-flow data" in result


# ---------------------------------------------------------------------------
# get_shareholder_count
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetShareholderCount(TestCase):
    def setUp(self):
        self.sh_df = pd.DataFrame([{
            "股东户数统计截止日": "2026-03-31",
            "股东户数": "150,000",
            "户均持股市值": "500,000",
            "户均持股数量": "8,000",
        }])

    def test_returns_formatted_data(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_zh_a_gdhs_detail_em.return_value = self.sh_df
            result = akshare_vendor.get_shareholder_count("600519.SS")
        assert "Shareholder Count" in result
        assert "150,000" in result

    def test_empty_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_zh_a_gdhs_detail_em.return_value = pd.DataFrame()
            result = akshare_vendor.get_shareholder_count("600519.SS")
        assert "No shareholder-count data" in result


# ---------------------------------------------------------------------------
# get_pledge_ratio
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetPledgeRatio(TestCase):
    def setUp(self):
        self.pledge_df = pd.DataFrame([{
            "股东名称": "控股股东",
            "质押股份数量": "50,000,000",
            "占所持股份比例": 25.0,
            "占总股本比例": 4.0,
            "质押机构": "工商银行",
            "最新价": 1680.50,
            "预估平仓线": 1176.35,
        }])

    def test_returns_formatted_data(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_gpzy_individual_pledge_ratio_detail_em.return_value = self.pledge_df
            result = akshare_vendor.get_pledge_ratio("600519.SS")
        assert "Pledge Ratio" in result
        assert "控股股东" in result
        assert "预估平仓线" in result

    def test_empty_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_gpzy_individual_pledge_ratio_detail_em.return_value = pd.DataFrame()
            result = akshare_vendor.get_pledge_ratio("600519.SS")
        assert "No pledge-ratio data" in result


# ---------------------------------------------------------------------------
# get_dividend_history
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetDividendHistory(TestCase):
    def setUp(self):
        self.div_df = pd.DataFrame([{
            "报告期": "2025-12-31",
            "分红方案": "10派192.93元",
            "除权除息日": "2026-06-20",
            "股权登记日": "2026-06-19",
            "红股上市日": "",
        }])

    def test_returns_formatted_data(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_fhps_detail_em.return_value = self.div_df
            result = akshare_vendor.get_dividend_history("600519.SS")
        assert "Dividend History" in result
        assert "192.93元" in result or "分红方案" in result

    def test_empty_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_fhps_detail_em.return_value = pd.DataFrame()
            result = akshare_vendor.get_dividend_history("600519.SS")
        assert "No dividend history" in result


# ---------------------------------------------------------------------------
# get_research_reports
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetResearchReports(TestCase):
    def setUp(self):
        self.rr_df = pd.DataFrame([{
            "报告标题": "贵州茅台深度研究",
            "机构名称": "中信证券",
            "分析师": "张三",
            "评级": "买入",
            "目标价": 2000.00,
            "发布日期": "2026-05-10",
        }])

    def test_returns_formatted_data(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_research_report_em.return_value = self.rr_df
            result = akshare_vendor.get_research_reports("600519.SS")
        assert "Research Reports" in result
        assert "贵州茅台深度研究" in result
        assert "中信证券" in result
        assert "2000" in result

    def test_empty_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_research_report_em.return_value = pd.DataFrame()
            result = akshare_vendor.get_research_reports("600519.SS")
        assert "No research reports" in result


# ---------------------------------------------------------------------------
# get_earnings_estimates
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetEarningsEstimates(TestCase):
    def setUp(self):
        self.est_df = pd.DataFrame([{
            "报告期": "2026-12-31",
            "预告类型": "预增",
            "预告内容": "净利润增长约20%",
            "预告原因": "市场需求旺盛",
            "变动下限": 15.0,
            "变动上限": 25.0,
        }])

    def test_returns_formatted_data(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_yjyg_em.return_value = self.est_df
            result = akshare_vendor.get_earnings_estimates("600519.SS")
        assert "Earnings Estimates" in result
        assert "预增" in result
        assert "净利润增长约20%" in result

    def test_empty_returns_message(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_yjyg_em.return_value = pd.DataFrame()
            result = akshare_vendor.get_earnings_estimates("600519.SS")
        assert "No earnings estimate data" in result


# ---------------------------------------------------------------------------
# get_institutional_holdings
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetInstitutionalHoldings(TestCase):
    def setUp(self):
        self.holder_df = pd.DataFrame([{
            "股东名称": "国有资本运营公司",
            "持股数量": 800_000_000,
            "持股比例": 63.5,
        }])

    def test_returns_formatted_data(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_main_stock_holder.return_value = self.holder_df
            result = akshare_vendor.get_institutional_holdings("600519.SS")
        assert "Institutional Holdings" in result
        assert "国有资本运营公司" in result

    def test_empty_holder_shows_fallback(self):
        from tradingagents.dataflows import akshare_vendor
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.stock_main_stock_holder.return_value = pd.DataFrame()
            result = akshare_vendor.get_institutional_holdings("600519.SS")
        assert "No top shareholder data" in result


# ---------------------------------------------------------------------------
# Nearest trade date
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestNearestTradeDate(TestCase):
    def test_returns_formatted_date_from_df(self):
        from tradingagents.dataflows.akshare_vendor import _nearest_trade_date
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.tool_trade_date_hist_sina.return_value = pd.DataFrame(
                {"trade_date": ["2026-05-14", "2026-05-15"]}
            )
            result = _nearest_trade_date()
        assert result == "20260515"

    def test_empty_df_falls_back_to_today(self):
        from tradingagents.dataflows.akshare_vendor import _nearest_trade_date
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.tool_trade_date_hist_sina.return_value = pd.DataFrame()
            result = _nearest_trade_date()
        assert result == datetime.now().strftime("%Y%m%d")

    def test_none_df_falls_back_to_today(self):
        from tradingagents.dataflows.akshare_vendor import _nearest_trade_date
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.tool_trade_date_hist_sina.return_value = None
            result = _nearest_trade_date()
        assert result == datetime.now().strftime("%Y%m%d")

    def test_all_future_dates_falls_back(self):
        from tradingagents.dataflows import akshare_vendor
        future = "2030-01-01"
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.tool_trade_date_hist_sina.return_value = pd.DataFrame(
                {"trade_date": [future]}
            )
            result = akshare_vendor._nearest_trade_date()
        assert result == datetime.now().strftime("%Y%m%d")

    def test_uses_first_column_if_trade_date_missing(self):
        from tradingagents.dataflows.akshare_vendor import _nearest_trade_date
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.tool_trade_date_hist_sina.return_value = pd.DataFrame(
                {"日期": ["2026-05-14"]}
            )
            result = _nearest_trade_date()
        assert result == "20260514"

    def test_yyyymmdd_date_in_yyyy_mm_dd_gets_normalised(self):
        from tradingagents.dataflows.akshare_vendor import _nearest_trade_date
        with patch("tradingagents.dataflows.akshare_vendor.ak") as mock_ak:
            mock_ak.tool_trade_date_hist_sina.return_value = pd.DataFrame(
                {"trade_date": ["2026-05-14"]}
            )
            result = _nearest_trade_date()
        assert result == "20260514"


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------

def _extract_first_yi(text: str, label_pattern: str) -> float | None:
    m = re.search(rf"{label_pattern}.*?([-+]?\d+(?:\.\d+)?)亿", text)
    return float(m.group(1)) if m else None


def _within_tolerance(actual: float, expected: float, tol_pct: float) -> bool:
    if expected == 0:
        return abs(actual) < tol_pct / 100
    return abs(actual - expected) / abs(expected) <= tol_pct / 100


TICKERS_WITH_TOTAL_ASSETS = [
    "300175.SZ",
    "300454.SZ",
    "300562.SZ",
    "300760.SZ",
    "603893.SS",
]


@pytest.mark.integration
class TestAkshareRegression:
    @pytest.mark.parametrize("ticker", TICKERS_WITH_TOTAL_ASSETS)
    def test_balance_sheet_total_assets(self, ticker, ground_truth):
        from tradingagents.dataflows.akshare_vendor import get_balance_sheet

        expected = ground_truth[ticker].get("total_assets_yi")
        assert expected is not None, f"missing total_assets_yi for {ticker}"

        out = get_balance_sheet(ticker)
        actual = _extract_first_yi(out, "总资产")
        assert actual is not None, (
            f"{ticker} 总资产未在输出中找到。\n输出片段:\n{out[:500]}"
        )
        assert _within_tolerance(actual, expected["value"], expected["tolerance_pct"]), (
            f"{ticker} 总资产 {actual}亿 偏离真值 {expected['value']}亿 "
            f"超过 ±{expected['tolerance_pct']}%"
        )

    def test_realtime_snapshot_smoke(self, ground_truth):
        import time

        from tradingagents.dataflows.akshare_realtime import fetch_realtime_snapshot

        critical_tickers = ("603893.SS", "002594.SZ", "300760.SZ", "600900.SS", "000100.SZ")
        failures: list[str] = []
        for i, ticker in enumerate(critical_tickers):
            if i > 0:
                time.sleep(2.0)
            snap = fetch_realtime_snapshot(ticker)
            if snap is None or not snap.get("company_name") or snap.get("market_cap_yi") is None:
                failures.append(ticker)

        if len(failures) == len(critical_tickers):
            pytest.skip(
                "所有 ticker 真值快照失败 — eastmoney 端点疑似限流，跳过该测试。"
                f"failures={failures}"
            )
        assert len(failures) <= 1, (
            f"超过 1 只股票快照失败: {failures}（共 {len(critical_tickers)} 只）"
        )

    def test_routing_uses_akshare_for_a_share(self):
        from tradingagents.dataflows.interface import route_to_vendor

        out = route_to_vendor("get_balance_sheet", "600519.SS")
        assert "akshare" in out.lower() or "东财" in out, (
            "route_to_vendor 没有把 A 股请求路由到 akshare"
        )
