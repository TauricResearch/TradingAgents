import pytest
from tradingagents.dataflows.akshare_data import (
    _normalize_akshare_ticker,
    _is_chinese_name,
)


class TestNormalizeAkshareTicker:
    @pytest.mark.unit
    def test_plain_shanghai_code(self):
        code, exchange = _normalize_akshare_ticker("600000")
        assert code == "600000"
        assert exchange == "shanghai"

    @pytest.mark.unit
    def test_plain_shenzhen_code_starting_0(self):
        code, exchange = _normalize_akshare_ticker("000001")
        assert code == "000001"
        assert exchange == "shenzhen"

    @pytest.mark.unit
    def test_plain_shenzhen_code_starting_3(self):
        code, exchange = _normalize_akshare_ticker("300750")
        assert code == "300750"
        assert exchange == "shenzhen"

    @pytest.mark.unit
    def test_suffixed_shanghai(self):
        code, exchange = _normalize_akshare_ticker("600000.SS")
        assert code == "600000"
        assert exchange == "shanghai"

    @pytest.mark.unit
    def test_suffixed_shenzhen(self):
        code, exchange = _normalize_akshare_ticker("000001.SZ")
        assert code == "000001"
        assert exchange == "shenzhen"

    @pytest.mark.unit
    def test_suffixed_hk(self):
        code, exchange = _normalize_akshare_ticker("0700.HK")
        assert code == "00700"
        assert exchange == "hongkong"

    @pytest.mark.unit
    def test_plain_hk_code(self):
        code, exchange = _normalize_akshare_ticker("00700")
        assert code == "00700"
        assert exchange == "hongkong"

    @pytest.mark.unit
    def test_hk_pads_to_5_digits(self):
        code, exchange = _normalize_akshare_ticker("700.HK")
        assert code == "00700"
        assert exchange == "hongkong"

    @pytest.mark.unit
    def test_star_market_shanghai(self):
        code, exchange = _normalize_akshare_ticker("688001")
        assert code == "688001"
        assert exchange == "shanghai"

    @pytest.mark.unit
    def test_beijing_exchange(self):
        code, exchange = _normalize_akshare_ticker("830799")
        assert code == "830799"
        assert exchange == "shenzhen"


class TestIsChineseName:
    @pytest.mark.unit
    def test_chinese_name_detected(self):
        assert _is_chinese_name("贵州茅台") is True

    @pytest.mark.unit
    def test_english_ticker_not_chinese(self):
        assert _is_chinese_name("600000.SS") is False

    @pytest.mark.unit
    def test_mixed_is_chinese(self):
        assert _is_chinese_name("平安银行") is True


from unittest.mock import patch
import pandas as pd
from tradingagents.dataflows.akshare_data import (
    get_akshare_stock_data,
    get_akshare_fundamentals,
    get_akshare_balance_sheet,
    get_akshare_income_statement,
    get_akshare_cashflow,
    get_akshare_news,
    get_akshare_global_news,
)


class TestAkshareStockData:
    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_returns_csv_for_a_share(self, mock_ak):
        df = pd.DataFrame({
            "日期": ["2024-01-15", "2024-01-16"],
            "开盘": [10.0, 10.5],
            "收盘": [10.3, 10.8],
            "最高": [10.4, 10.9],
            "最低": [9.9, 10.4],
            "成交量": [100000, 120000],
        })
        mock_ak.stock_zh_a_hist.return_value = df

        result = get_akshare_stock_data("600000", "2024-01-01", "2024-01-31")

        assert "Stock data for 600000" in result
        assert "2024-01-15" in result
        mock_ak.stock_zh_a_hist.assert_called_once()

    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_empty_dataframe_returns_error(self, mock_ak):
        mock_ak.stock_zh_a_hist.return_value = pd.DataFrame()

        result = get_akshare_stock_data("000001", "2024-01-01", "2024-01-31")

        assert "No data found" in result

    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_hk_stock_uses_hk_endpoint(self, mock_ak):
        df = pd.DataFrame({
            "日期": ["2024-01-15"],
            "开盘": [300.0], "收盘": [305.0],
            "最高": [306.0], "最低": [299.0], "成交量": [50000],
        })
        mock_ak.stock_hk_hist.return_value = df

        result = get_akshare_stock_data("0700.HK", "2024-01-01", "2024-01-31")

        assert "Stock data for 00700" in result
        mock_ak.stock_hk_hist.assert_called_once()


class TestAkshareFundamentals:
    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_returns_fundamentals_text(self, mock_ak):
        mock_ak.stock_individual_info_em.return_value = pd.DataFrame(
            {"item": ["总市值", "市盈率"], "value": ["1000亿", "15.2"]}
        )

        result = get_akshare_fundamentals("600519", "2024-06-01")

        assert "总市值" in result
        assert "1000亿" in result

    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_empty_fundamentals_returns_error(self, mock_ak):
        mock_ak.stock_individual_info_em.return_value = pd.DataFrame()

        result = get_akshare_fundamentals("000002", "2024-06-01")

        assert "No fundamentals data" in result


class TestAkshareFinancialStatements:
    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_balance_sheet(self, mock_ak):
        mock_ak.stock_balance_sheet_by_report_em.return_value = pd.DataFrame(
            {"项目": ["总资产"], "2023-12-31": ["500亿"]}
        )
        result = get_akshare_balance_sheet("600519", "quarterly", "2024-06-01")
        assert "总资产" in result

    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_income_statement(self, mock_ak):
        mock_ak.stock_profit_sheet_by_report_em.return_value = pd.DataFrame(
            {"项目": ["营业收入"], "2023-12-31": ["100亿"]}
        )
        result = get_akshare_income_statement("600519", "quarterly", "2024-06-01")
        assert "营业收入" in result

    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_cashflow(self, mock_ak):
        mock_ak.stock_cash_flow_sheet_by_report_em.return_value = pd.DataFrame(
            {"项目": ["经营活动现金流"], "2023-12-31": ["20亿"]}
        )
        result = get_akshare_cashflow("600519", "quarterly", "2024-06-01")
        assert "经营活动现金流" in result


class TestAkshareNews:
    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_stock_news(self, mock_ak):
        mock_ak.stock_news_em.return_value = pd.DataFrame({
            "title": ["重大公告"],
            "content": ["内容摘要"],
            "发布时间": ["2024-06-01 10:00:00"],
        })
        result = get_akshare_news("600519", "2024-05-01", "2024-06-30")
        assert "重大公告" in result

    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_global_news(self, mock_ak):
        mock_ak.news_economic_baidu.return_value = pd.DataFrame({
            "title": ["央行降准"], "content": [""], "date": ["2024-06-01"],
        })
        result = get_akshare_global_news("2024-06-01", 7, 10)
        assert "央行降准" in result
