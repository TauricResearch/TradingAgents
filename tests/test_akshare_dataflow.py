"""Unit tests for AKShare data source module."""

from unittest.mock import patch, MagicMock

import pytest
import pandas as pd

from tradingagents.dataflows.interface import detect_vendor_for_ticker
from tradingagents.dataflows.akshare_data import (
    normalize_akshare_code,
    _is_fund_or_etf,
    _is_hk_ticker,
    _normalize_hk_code,
)


# ---------------------------------------------------------------------------
# 1. normalize_akshare_code tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeAkshareCode:
    """Test normalize_akshare_code() for various ticker formats."""

    def test_sh_suffix(self):
        """600000.SH -> 600000"""
        assert normalize_akshare_code("600000.SH") == "600000"

    def test_sh_prefix(self):
        """SH600000 -> 600000"""
        assert normalize_akshare_code("SH600000") == "600000"

    def test_ss_suffix(self):
        """600000.SS -> 600000"""
        assert normalize_akshare_code("600000.SS") == "600000"

    def test_sz_suffix(self):
        """000001.SZ -> 000001"""
        assert normalize_akshare_code("000001.SZ") == "000001"

    def test_sz_prefix(self):
        """SZ000001 -> 000001"""
        assert normalize_akshare_code("SZ000001") == "000001"

    def test_pure_digits(self):
        """600000 -> 600000 (no change)"""
        assert normalize_akshare_code("600000") == "600000"

    def test_hk_suffix(self):
        """0700.HK -> 0700.HK (not handled by normalize_akshare_code, uses _normalize_hk_code)"""
        # normalize_akshare_code does NOT handle .HK suffix - it falls through
        # HK tickers use _normalize_hk_code instead
        result = _normalize_hk_code("0700.HK")
        assert result == "00700"

    def test_hk_prefix(self):
        """HK0700 -> 00700 (via _normalize_hk_code)"""
        result = _normalize_hk_code("HK0700")
        assert result == "00700"


# ---------------------------------------------------------------------------
# 2. _is_fund_or_etf tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIsFundOrEtf:
    """Test _is_fund_or_etf() detection logic."""

    def test_shanghai_etf_510050(self):
        """510050 -> True (上海 ETF)"""
        assert _is_fund_or_etf("510050") is True

    def test_shanghai_etf_518880(self):
        """518880 -> True (上海 ETF)"""
        assert _is_fund_or_etf("518880") is True

    def test_shenzhen_etf_159915(self):
        """159915 -> True (深圳 ETF)"""
        assert _is_fund_or_etf("159915") is True

    def test_normal_stock_600000(self):
        """600000 -> False (普通股票)"""
        assert _is_fund_or_etf("600000") is False

    def test_normal_stock_000001(self):
        """000001 -> False (普通股票)"""
        assert _is_fund_or_etf("000001") is False

    def test_growth_enterprise_300001(self):
        """300001 -> False (创业板)"""
        assert _is_fund_or_etf("300001") is False


# ---------------------------------------------------------------------------
# 3. detect_vendor_for_ticker (routing) tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectVendorForTicker:
    """Test detect_vendor_for_ticker() now returns 'akshare' for A-share/HK."""

    def test_sh_suffix(self):
        """600000.SH -> akshare"""
        assert detect_vendor_for_ticker("600000.SH") == "akshare"

    def test_sz_suffix(self):
        """000001.SZ -> akshare"""
        assert detect_vendor_for_ticker("000001.SZ") == "akshare"

    def test_sh_prefix(self):
        """SH600000 -> akshare"""
        assert detect_vendor_for_ticker("SH600000") == "akshare"

    def test_pure_digits(self):
        """600000 -> akshare"""
        assert detect_vendor_for_ticker("600000") == "akshare"

    def test_hk_suffix(self):
        """0700.HK -> akshare"""
        assert detect_vendor_for_ticker("0700.HK") == "akshare"

    def test_hk_prefix(self):
        """HK0700 -> akshare"""
        assert detect_vendor_for_ticker("HK0700") == "akshare"

    def test_us_stock_not_routed(self):
        """AAPL -> None (美股不路由)"""
        assert detect_vendor_for_ticker("AAPL") is None

    def test_us_stock_with_dot_not_routed(self):
        """BRK.B -> None"""
        assert detect_vendor_for_ticker("BRK.B") is None


# ---------------------------------------------------------------------------
# 4. get_akshare_stock (mock) tests
# ---------------------------------------------------------------------------


# Shared mock data
_MOCK_STOCK_DF = pd.DataFrame({
    "日期": ["2024-01-15", "2024-01-16"],
    "开盘": [10.30, 10.50],
    "收盘": [10.40, 10.60],
    "最高": [10.60, 10.80],
    "最低": [10.10, 10.20],
    "成交量": [112340, 123450],
    "成交额": [1156700.0, 1290000.0],
    "振幅": [4.85, 5.66],
    "涨跌幅": [0.97, 1.92],
    "涨跌额": [0.10, 0.20],
    "换手率": [0.56, 0.62],
})


@pytest.mark.unit
class TestGetAkshareStock:
    """Test get_akshare_stock with mocked AKShare API."""

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_normal_stock_returns_csv(self, mock_ak):
        """Test fetching A-share stock data returns CSV."""
        from tradingagents.dataflows.akshare_data import get_akshare_stock

        mock_ak.stock_zh_a_hist.return_value = _MOCK_STOCK_DF.copy()

        result = get_akshare_stock("600000.SH", "2024-01-15", "2024-01-16")

        assert "# Stock data for" in result
        assert "Date,Open,High,Low,Close,Adj Close,Volume" in result
        assert "2024-01-15" in result
        assert "2024-01-16" in result
        mock_ak.stock_zh_a_hist.assert_called_once()

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_etf_uses_fund_etf_hist_em(self, mock_ak):
        """Test ETF data fetching uses fund_etf_hist_em API."""
        from tradingagents.dataflows.akshare_data import get_akshare_stock

        mock_ak.fund_etf_hist_em.return_value = _MOCK_STOCK_DF.copy()

        result = get_akshare_stock("510050", "2024-01-15", "2024-01-16")

        assert "# Stock data for" in result
        assert "Date,Open,High,Low,Close,Adj Close,Volume" in result
        mock_ak.fund_etf_hist_em.assert_called_once()
        mock_ak.stock_zh_a_hist.assert_not_called()

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_hk_stock_uses_stock_hk_hist(self, mock_ak):
        """Test HK stock data fetching uses stock_hk_hist API."""
        from tradingagents.dataflows.akshare_data import get_akshare_stock

        mock_hk_df = pd.DataFrame({
            "日期": ["2024-01-15", "2024-01-16"],
            "开盘": [300.0, 305.0],
            "收盘": [305.0, 310.0],
            "最高": [308.0, 312.0],
            "最低": [298.0, 303.0],
            "成交量": [50000000, 55000000],
            "成交额": [15000000000.0, 17000000000.0],
        })
        mock_ak.stock_hk_hist.return_value = mock_hk_df

        result = get_akshare_stock("0700.HK", "2024-01-15", "2024-01-16")

        assert "# Stock data for" in result
        assert "Date,Open,High,Low,Close,Adj Close,Volume" in result
        mock_ak.stock_hk_hist.assert_called_once()

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_empty_data_returns_message(self, mock_ak):
        """Test empty data returns proper message."""
        from tradingagents.dataflows.akshare_data import get_akshare_stock

        mock_ak.stock_zh_a_hist.return_value = pd.DataFrame()

        result = get_akshare_stock("600000.SH", "2024-01-15", "2024-01-16")

        assert "No stock data found" in result

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_csv_columns_correct(self, mock_ak):
        """Verify CSV output has correct column header."""
        from tradingagents.dataflows.akshare_data import get_akshare_stock

        mock_ak.stock_zh_a_hist.return_value = _MOCK_STOCK_DF.copy()

        result = get_akshare_stock("600000", "2024-01-15", "2024-01-16")

        lines = result.strip().split("\n")
        # Find the header line
        header_line = None
        for line in lines:
            if line.startswith("Date,"):
                header_line = line
                break
        assert header_line == "Date,Open,High,Low,Close,Adj Close,Volume"


# ---------------------------------------------------------------------------
# 5. get_akshare_indicators (mock) tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetAkshareIndicators:
    """Test get_akshare_indicators with mocked AKShare API."""

    @patch("tradingagents.dataflows.akshare_data.stockstats_wrap")
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_indicator_returns_formatted(self, mock_ak, mock_wrap):
        """Test indicator computation returns formatted output."""
        from tradingagents.dataflows.akshare_data import get_akshare_indicators

        # Build a larger dataframe for indicator calculation
        dates = pd.date_range("2023-01-01", periods=300, freq="B")
        mock_df = pd.DataFrame({
            "日期": dates.strftime("%Y-%m-%d").tolist(),
            "开盘": [10.0 + i * 0.01 for i in range(300)],
            "收盘": [10.1 + i * 0.01 for i in range(300)],
            "最高": [10.2 + i * 0.01 for i in range(300)],
            "最低": [9.9 + i * 0.01 for i in range(300)],
            "成交量": [100000 + i * 100 for i in range(300)],
        })
        mock_ak.stock_zh_a_hist.return_value = mock_df

        # Mock stockstats wrap to return a DataFrame with the indicator column
        mock_ss_df = MagicMock()
        mock_ss_df.__iter__ = MagicMock(return_value=iter([]))
        # Make it behave like a DataFrame with iterrows
        result_rows = []
        for i in range(300):
            result_rows.append({
                "date": dates[i].strftime("%Y-%m-%d"),
                "rsi": 50.0 + i * 0.1 if i > 14 else float("nan"),
            })
        mock_ss_df.iterrows.return_value = iter(
            [(i, pd.Series(row)) for i, row in enumerate(result_rows)]
        )
        mock_ss_df.__getitem__ = MagicMock(return_value=None)  # trigger calculation
        mock_wrap.return_value = mock_ss_df

        result = get_akshare_indicators("600000", "rsi", "2024-01-15", 30)

        assert "rsi" in result.lower()

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_unsupported_indicator_raises(self, mock_ak):
        """Test that unsupported indicator raises ValueError."""
        from tradingagents.dataflows.akshare_data import get_akshare_indicators

        with pytest.raises(ValueError, match="not supported"):
            get_akshare_indicators("600000", "invalid_indicator", "2024-01-15", 30)

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_empty_data_returns_message(self, mock_ak):
        """Test empty data returns proper message."""
        from tradingagents.dataflows.akshare_data import get_akshare_indicators

        mock_ak.stock_zh_a_hist.return_value = pd.DataFrame()

        result = get_akshare_indicators("600000", "rsi", "2024-01-15", 30)

        assert "No stock data found" in result


# ---------------------------------------------------------------------------
# 6. get_akshare_fundamentals (mock) tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetAkshareFundamentals:
    """Test get_akshare_fundamentals with mocked AKShare API."""

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_returns_company_info(self, mock_ak):
        """Test fundamentals output includes company name and industry."""
        from tradingagents.dataflows.akshare_data import get_akshare_fundamentals

        mock_info_df = pd.DataFrame({
            "item": ["股票简称", "公司名称", "行业", "上市时间", "总股本", "流通股"],
            "value": ["浦发银行", "上海浦东发展银行", "银行", "19991110", "293.77亿", "286.24亿"],
        })
        mock_ak.stock_individual_info_em.return_value = mock_info_df

        mock_quote_df = pd.DataFrame({
            "代码": ["600000"],
            "最新价": [7.85],
            "换手率": [0.23],
            "市盈率-动态": [4.56],
            "市净率": [0.42],
            "总市值": [2305.0e8],
            "流通市值": [2246.0e8],
            "60日涨跌幅": [5.23],
            "年初至今涨跌幅": [8.12],
        })
        mock_ak.stock_zh_a_spot_em.return_value = mock_quote_df

        result = get_akshare_fundamentals("600000.SH")

        assert "Company Fundamentals" in result
        assert "浦发银行" in result
        assert "银行" in result
        assert "PE Ratio" in result

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_no_data_returns_message(self, mock_ak):
        """Test handling when no data is available."""
        from tradingagents.dataflows.akshare_data import get_akshare_fundamentals

        mock_ak.stock_individual_info_em.return_value = pd.DataFrame()
        mock_ak.stock_zh_a_spot_em.return_value = pd.DataFrame()

        result = get_akshare_fundamentals("600000")

        assert "No fundamentals data found" in result

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_hk_not_supported(self, mock_ak):
        """Test that HK stock fundamentals returns not supported message."""
        from tradingagents.dataflows.akshare_data import get_akshare_fundamentals

        result = get_akshare_fundamentals("0700.HK")

        assert "not yet supported" in result


# ---------------------------------------------------------------------------
# 7. get_akshare_balance_sheet / cashflow / income_statement (mock) tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetAkshareFinancials:
    """Test financial statement functions with mocked AKShare API."""

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_balance_sheet_returns_csv(self, mock_ak):
        """Test balance sheet returns CSV format."""
        from tradingagents.dataflows.akshare_data import get_akshare_balance_sheet

        mock_df = pd.DataFrame({
            "REPORT_DATE": ["2024-03-31", "2023-12-31", "2023-09-30", "2023-06-30"],
            "TOTAL_ASSETS": [1e12, 9.8e11, 9.5e11, 9.2e11],
            "TOTAL_LIABILITIES": [9e11, 8.8e11, 8.5e11, 8.2e11],
            "TOTAL_EQUITY": [1e11, 1e11, 1e11, 1e11],
        })
        mock_ak.stock_balance_sheet_by_report_em.return_value = mock_df

        result = get_akshare_balance_sheet("600000.SH")

        assert "# Balance Sheet data for 600000" in result
        assert "TOTAL_ASSETS" in result

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_cashflow_returns_csv(self, mock_ak):
        """Test cash flow statement returns CSV format."""
        from tradingagents.dataflows.akshare_data import get_akshare_cashflow

        mock_df = pd.DataFrame({
            "REPORT_DATE": ["2024-03-31", "2023-12-31"],
            "OPERATE_CASH_FLOW": [5e9, 20e9],
            "INVEST_CASH_FLOW": [-3e9, -10e9],
            "FINANCE_CASH_FLOW": [-1e9, -5e9],
        })
        mock_ak.stock_cash_flow_sheet_by_report_em.return_value = mock_df

        result = get_akshare_cashflow("600000.SH")

        assert "# Cash Flow data for 600000" in result
        assert "OPERATE_CASH_FLOW" in result

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_income_statement_returns_csv(self, mock_ak):
        """Test income statement returns CSV format."""
        from tradingagents.dataflows.akshare_data import get_akshare_income_statement

        mock_df = pd.DataFrame({
            "REPORT_DATE": ["2024-03-31", "2023-12-31"],
            "TOTAL_OPERATE_INCOME": [50e9, 200e9],
            "OPERATE_PROFIT": [20e9, 80e9],
            "TOTAL_PROFIT": [18e9, 75e9],
            "NETPROFIT": [15e9, 60e9],
        })
        mock_ak.stock_profit_sheet_by_report_em.return_value = mock_df

        result = get_akshare_income_statement("600000.SH")

        assert "# Income Statement data for 600000" in result
        assert "TOTAL_OPERATE_INCOME" in result

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_balance_sheet_empty(self, mock_ak):
        """Test balance sheet with empty data."""
        from tradingagents.dataflows.akshare_data import get_akshare_balance_sheet

        mock_ak.stock_balance_sheet_by_report_em.return_value = pd.DataFrame()

        result = get_akshare_balance_sheet("600000")

        assert "No balance sheet data found" in result

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_hk_financials_not_supported(self, mock_ak):
        """Test that HK stock financials return not supported."""
        from tradingagents.dataflows.akshare_data import (
            get_akshare_balance_sheet,
            get_akshare_cashflow,
            get_akshare_income_statement,
        )

        assert "not yet supported" in get_akshare_balance_sheet("0700.HK")
        assert "not yet supported" in get_akshare_cashflow("0700.HK")
        assert "not yet supported" in get_akshare_income_statement("0700.HK")


# ---------------------------------------------------------------------------
# 8. get_akshare_insider_transactions (mock) tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetAkshareInsiderTransactions:
    """Test get_akshare_insider_transactions with mocked AKShare API."""

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_returns_formatted_output(self, mock_ak):
        """Test insider transactions returns formatted CSV output."""
        from tradingagents.dataflows.akshare_data import get_akshare_insider_transactions

        mock_df = pd.DataFrame({
            "变动日期": ["2024-01-10", "2024-01-05"],
            "变动人": ["张三", "李四"],
            "变动股数": [50000, -30000],
            "变动方向": ["增持", "减持"],
            "变动均价": [10.50, 10.80],
            "变动原因": ["竞价交易", "竞价交易"],
        })
        mock_ak.stock_hold_management_detail_em.return_value = mock_df

        result = get_akshare_insider_transactions("600000.SH")

        assert "# Insider Transactions data for 600000" in result
        assert "Date,Holder Name,Change Volume,Change Type,Price,Change Reason" in result
        assert "张三" in result
        assert "增持" in result

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_empty_data(self, mock_ak):
        """Test empty insider transactions data."""
        from tradingagents.dataflows.akshare_data import get_akshare_insider_transactions

        mock_ak.stock_hold_management_detail_em.return_value = pd.DataFrame()

        result = get_akshare_insider_transactions("600000")

        assert "No insider transactions data found" in result

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_hk_not_supported(self, mock_ak):
        """Test that HK insider transactions returns not supported."""
        from tradingagents.dataflows.akshare_data import get_akshare_insider_transactions

        result = get_akshare_insider_transactions("0700.HK")

        assert "not yet supported" in result

    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_api_exception_graceful(self, mock_ak):
        """Test graceful handling when API raises exception."""
        from tradingagents.dataflows.akshare_data import get_akshare_insider_transactions

        mock_ak.stock_hold_management_detail_em.side_effect = Exception("API error")

        result = get_akshare_insider_transactions("600000")

        assert "not available" in result or "Error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
