import copy
import unittest
from unittest.mock import patch

import pandas as pd
import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows.a_share import (
    get_balance_sheet,
    get_decision_signal_summary,
    get_company_event_signals,
    get_fundamentals,
    get_market_activity,
    get_stock_data,
)
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.interface import get_vendor, route_to_vendor
from tradingagents.graph.trading_graph import TradingAgentsGraph


@pytest.mark.unit
class AShareSupportTests(unittest.TestCase):
    def setUp(self):
        cfg = copy.deepcopy(default_config.DEFAULT_CONFIG)
        set_config(cfg)

    def test_cn_a_market_region_prefers_akshare_vendor(self):
        set_config({"market_region": "cn_a"})
        self.assertEqual(get_vendor("core_stock_apis", "get_stock_data"), "akshare")
        self.assertEqual(get_vendor("news_data", "get_news"), "akshare")

    def test_route_to_vendor_can_use_a_share_method(self):
        with patch.dict(
            "tradingagents.dataflows.interface.VENDOR_METHODS",
            {"get_stock_data": {"akshare": lambda symbol, start, end: f"{symbol}|{start}|{end}"}},
            clear=False,
        ):
            set_config({"market_region": "cn_a"})
            result = route_to_vendor("get_stock_data", "600519.SH", "2024-03-01", "2024-03-05")

        self.assertEqual(result, "600519.SH|2024-03-01|2024-03-05")

    @patch("tradingagents.dataflows.a_share.ak.stock_zh_a_hist", create=True)
    def test_get_stock_data_formats_a_share_ohlcv(self, mock_hist):
        mock_hist.return_value = pd.DataFrame(
            {
                "日期": ["2024-03-01", "2024-03-04"],
                "股票代码": ["600519", "600519"],
                "开盘": [100.1234, 101.0],
                "收盘": [101.0, 102.0],
                "最高": [102.0, 103.0],
                "最低": [99.0, 100.0],
                "成交量": [1000, 1200],
                "成交额": [1_000_000, 1_200_000],
                "振幅": [3.0, 2.0],
                "涨跌幅": [1.1, 0.9],
                "涨跌额": [1.0, 1.0],
                "换手率": [0.5, 0.6],
            }
        )

        result = get_stock_data("600519", "2024-03-01", "2024-03-04")

        self.assertIn("600519.SH", result)
        self.assertIn("TurnoverPct", result)
        self.assertIn("2024-03-04", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_balance_sheet_by_report_em", create=True)
    def test_get_balance_sheet_selects_key_columns(self, mock_balance):
        mock_balance.return_value = pd.DataFrame(
            {
                "REPORT_DATE": ["2024-09-30"],
                "REPORT_DATE_NAME": ["2024三季报"],
                "TOTAL_ASSETS": [100.0],
                "TOTAL_LIABILITIES": [40.0],
                "TOTAL_PARENT_EQUITY": [60.0],
                "MONETARYFUNDS": [20.0],
                "INVENTORY": [10.0],
                "ACCOUNTS_RECE": [5.0],
                "GOODWILL": [1.0],
            }
        )

        result = get_balance_sheet("600519")
        self.assertIn("TOTAL_ASSETS", result)
        self.assertIn("GOODWILL", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_financial_abstract", create=True)
    @patch("tradingagents.dataflows.a_share.ak.stock_zygc_em", create=True)
    @patch("tradingagents.dataflows.a_share.ak.stock_zyjs_ths", create=True)
    @patch("tradingagents.dataflows.a_share.ak.stock_profile_cninfo", create=True)
    def test_get_fundamentals_builds_multi_section_summary(
        self,
        mock_profile,
        mock_intro,
        mock_business,
        mock_abstract,
    ):
        mock_profile.return_value = pd.DataFrame(
            {
                "公司名称": ["贵州茅台酒股份有限公司"],
                "A股代码": ["600519"],
                "A股简称": ["贵州茅台"],
                "所属行业": ["酒、饮料和精制茶制造业"],
            }
        )
        mock_intro.return_value = pd.DataFrame(
            {
                "股票代码": ["600519"],
                "主营业务": ["白酒生产与销售"],
            }
        )
        mock_business.return_value = pd.DataFrame(
            {
                "股票代码": ["600519"],
                "报告日期": ["2024-09-30"],
                "主营构成": ["茅台酒"],
                "主营收入": [100.0],
            }
        )
        mock_abstract.return_value = pd.DataFrame(
            {
                "选项": ["常用指标", "常用指标"],
                "指标": ["归母净利润", "营业总收入"],
                "20240930": [1.0, 2.0],
            }
        )

        result = get_fundamentals("600519", "2024-10-01")

        self.assertIn("A-share company profile", result)
        self.assertIn("主营业务简介", result)
        self.assertIn("最新关键财务摘要", result)
        self.assertIn("归母净利润", result)

    def test_resolve_benchmark_maps_a_share_suffixes(self):
        mock_graph = type(
            "MockGraph",
            (),
            {
                "config": {
                    "benchmark_ticker": None,
                    "benchmark_map": {
                        ".SH": "000300.SS",
                        ".SZ": "000300.SS",
                        "": "SPY",
                    },
                }
            },
        )()

        self.assertEqual(TradingAgentsGraph._resolve_benchmark(mock_graph, "600519.SH"), "000300.SS")
        self.assertEqual(TradingAgentsGraph._resolve_benchmark(mock_graph, "000001.SZ"), "000300.SS")

    @patch("tradingagents.dataflows.a_share.ak.stock_individual_notice_report", create=True)
    def test_get_company_event_signals_summarizes_categories(self, mock_notice):
        mock_notice.side_effect = [
            pd.DataFrame({"公告日期": ["2024-04-01"], "公告标题": ["签署重大合同"], "公告类型": ["重大事项"], "网址": ["u1"]}),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame({"公告日期": ["2024-04-03"], "公告标题": ["股东减持计划"], "公告类型": ["持股变动"], "网址": ["u2"]}),
        ]

        result = get_company_event_signals("002624.SZ", "2024-04-01", "2024-04-10")

        self.assertIn("重大事项", result)
        self.assertIn("持股变动", result)
        self.assertIn("签署重大合同", result)
        self.assertIn("股东减持计划", result)
        self.assertIn("Event summary", result)
        self.assertIn("tag=contract_order", result)
        self.assertIn("tag=shareholder_change", result)
        self.assertIn("bias=positive", result)
        self.assertIn("bias=negative", result)

    @patch("tradingagents.dataflows.a_share.get_previous_trade_date")
    @patch("tradingagents.dataflows.a_share.ak.stock_margin_detail_szse", create=True)
    @patch("tradingagents.dataflows.a_share.ak.stock_hsgt_individual_em", create=True)
    @patch("tradingagents.dataflows.a_share.ak.stock_individual_fund_flow", create=True)
    def test_get_market_activity_combines_multiple_sources(
        self,
        mock_fund_flow,
        mock_hsgt,
        mock_margin,
        mock_prev_trade_date,
    ):
        mock_prev_trade_date.return_value = "2024-04-01"
        mock_fund_flow.return_value = pd.DataFrame({"日期": ["2024-04-01"], "主力净流入-净额": [123.0]})
        mock_hsgt.return_value = pd.DataFrame({"TRADE_DATE": ["2024-04-01"], "HOLD_SHARES": [456.0]})
        mock_margin.return_value = pd.DataFrame({"证券代码": ["002624"], "融资余额": [789.0]})

        result = get_market_activity("002624.SZ", "2024-04-02")

        self.assertIn("Individual fund flow", result)
        self.assertIn("Northbound holding activity", result)
        self.assertIn("Margin trading detail", result)
        self.assertIn("Signal:", result)

    @patch("tradingagents.dataflows.a_share.get_market_activity")
    @patch("tradingagents.dataflows.a_share.get_company_event_signals")
    def test_get_decision_signal_summary_combines_event_and_activity_reads(
        self,
        mock_events,
        mock_activity,
    ):
        mock_events.return_value = "\n".join(
            [
                "# A-share company event signals for 002624.SZ",
                "bias=positive",
                "tag=contract_order",
                "bias=negative",
                "tag=shareholder_change",
                "tag=financing",
            ]
        )
        mock_activity.return_value = "\n".join(
            [
                "# A-share market activity signals for 002624.SZ",
                "## Individual fund flow",
                "Signal: recent main-fund-flow observations positive=3, negative=1, latest=123.00",
                "## Northbound holding activity",
                "## Margin trading detail",
            ]
        )

        result = get_decision_signal_summary("002624.SZ", "2024-04-01", "2024-04-10", "2024-04-11")

        self.assertIn("A-share decision signal summary for 002624.SZ", result)
        self.assertIn("Event balance over the lookback window: positive=1, negative=1, mixed=0.", result)
        self.assertIn("Recent contract / order announcements may support near-term sentiment.", result)
        self.assertIn("Shareholder reduction related events may pressure supply / sentiment.", result)
        self.assertIn("Northbound holding changes are available", result)
        self.assertIn("Source Digests", result)
