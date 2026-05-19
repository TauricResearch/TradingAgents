import copy
import unittest
from unittest.mock import patch

import pandas as pd
import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows.a_share import (
    get_balance_sheet,
    get_capital_flow_regime_context,
    get_corporate_action_pressure_context,
    get_decision_signal_summary,
    get_company_event_signals,
    get_fundamentals,
    get_market_activity,
    get_limit_move_sentiment_context,
    get_peer_comparison_context,
    get_relative_strength_context,
    get_sector_rotation_context,
    get_sector_strength_snapshot,
    get_stock_data,
    get_trading_constraint_context,
    get_unusual_trading_activity,
)
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.interface import get_vendor, route_to_vendor
from tradingagents.dataflows.y_finance import get_stock_stats_indicators_window
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
        self.assertIn("Trend:", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_board_concept_cons_em", create=True)
    @patch("tradingagents.dataflows.a_share.ak.stock_board_industry_cons_em", create=True)
    @patch("tradingagents.dataflows.a_share.ak.stock_profile_cninfo", create=True)
    def test_get_sector_rotation_context_summarizes_industry_and_concepts(
        self,
        mock_profile,
        mock_industry_board,
        mock_concept_board,
    ):
        mock_profile.return_value = pd.DataFrame(
            {
                "所属行业": ["消费电子"],
                "所属概念": ["华为概念;AI手机"],
            }
        )
        mock_industry_board.return_value = pd.DataFrame(
            {
                "代码": ["002624", "000001"],
                "名称": ["完美世界", "平安银行"],
                "涨跌幅": [2.0, 1.0],
                "成交额": [100.0, 80.0],
            }
        )
        mock_concept_board.return_value = pd.DataFrame(
            {
                "代码": ["002624", "300750"],
                "名称": ["完美世界", "宁德时代"],
                "涨跌幅": [3.0, 2.0],
                "成交额": [120.0, 110.0],
            }
        )

        result = get_sector_rotation_context("002624.SZ", "2024-04-11")

        self.assertIn("Industry tags", result)
        self.assertIn("消费电子", result)
        self.assertIn("Concept / theme tags", result)
        self.assertIn("华为概念", result)
        self.assertIn("AI手机", result)
        self.assertIn("Industry board sample", result)
        self.assertIn("Concept board sample", result)
        self.assertIn("Rotation takeaways", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_board_concept_name_em", create=True)
    @patch("tradingagents.dataflows.a_share.ak.stock_board_industry_name_em", create=True)
    def test_get_sector_strength_snapshot_ranks_leaders_and_laggards(
        self,
        mock_industry_name,
        mock_concept_name,
    ):
        mock_industry_name.return_value = pd.DataFrame(
            {
                "板块名称": ["消费电子", "银行", "有色金属"],
                "涨跌幅": [3.2, -1.1, 1.4],
            }
        )
        mock_concept_name.return_value = pd.DataFrame(
            {
                "板块名称": ["AI手机", "华为概念", "中特估"],
                "涨跌幅": [4.5, 2.2, -0.8],
            }
        )

        result = get_sector_strength_snapshot("2024-04-11", 2)

        self.assertIn("Industry board strength", result)
        self.assertIn("Concept board strength", result)
        self.assertIn("Top leaders by 涨跌幅", result)
        self.assertIn("Laggards by 涨跌幅", result)
        self.assertIn("消费电子", result)
        self.assertIn("AI手机", result)

    @patch("tradingagents.dataflows.a_share.get_sector_strength_snapshot")
    @patch("tradingagents.dataflows.a_share.get_sector_rotation_context")
    @patch("tradingagents.dataflows.a_share.load_ohlcv")
    @patch("tradingagents.dataflows.a_share._load_hist_df")
    def test_get_relative_strength_context_compares_against_benchmark(
        self,
        mock_hist,
        mock_load_ohlcv,
        mock_sector,
        mock_strength,
    ):
        mock_sector.return_value = "# A-share sector rotation context for 002624.SZ\n## Rotation takeaways"
        mock_strength.return_value = "# A-share sector strength snapshot for 2024-04-11\nSignal: leading boards currently include 消费电子."
        mock_hist.return_value = pd.DataFrame(
            {
                "Date": ["2024-04-01", "2024-04-11"],
                "Close": [10.0, 12.0],
            }
        )
        mock_load_ohlcv.return_value = pd.DataFrame(
            {
                "Date": ["2024-04-01", "2024-04-11"],
                "Close": [100.0, 105.0],
            }
        )

        result = get_relative_strength_context("002624.SZ", "2024-04-11", 20)

        self.assertIn("Stock vs benchmark", result)
        self.assertIn("Benchmark symbol: 000300.SS", result)
        self.assertIn("Relative strength alpha: 15.00%", result)
        self.assertIn("outperforming its market benchmark", result)

    @patch("tradingagents.dataflows.a_share.get_company_event_signals")
    def test_get_corporate_action_pressure_context_scores_supply_and_governance_risk(self, mock_events):
        mock_events.return_value = "\n".join(
            [
                "# A-share company event signals for 002624.SZ",
                "- 2024-04-01 | tag=shareholder_change | bias=negative | 股东减持计划",
                "- 2024-04-02 | tag=lockup | bias=negative | 限售股解禁",
                "- 2024-04-03 | tag=financing | bias=mixed | 定增预案",
                "- 2024-04-04 | tag=risk_warning | bias=negative | 风险提示公告",
                "- 2024-04-05 | tag=buyback | bias=positive | 回购股份公告",
            ]
        )

        result = get_corporate_action_pressure_context("002624.SZ", "2024-04-01", "2024-04-10")

        self.assertIn("Pressure scorecard", result)
        self.assertIn("Supply / dilution pressure: high", result)
        self.assertIn("Governance / legal pressure: medium", result)
        self.assertIn("Positive offset strength: medium", result)
        self.assertIn("减持计划", result)
        self.assertIn("回购股份公告", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_lhb_stock_statistic_em", create=True)
    @patch("tradingagents.dataflows.a_share.ak.stock_lhb_stock_detail_em", create=True)
    @patch("tradingagents.dataflows.a_share.ak.stock_lhb_stock_detail_date_em", create=True)
    @patch("tradingagents.dataflows.a_share.ak.stock_lhb_detail_em", create=True)
    def test_get_unusual_trading_activity_summarizes_lhb_records(
        self,
        mock_lhb_detail,
        mock_lhb_dates,
        mock_lhb_side,
        mock_lhb_stats,
    ):
        mock_lhb_detail.return_value = pd.DataFrame(
            {
                "代码": ["002624"],
                "名称": ["完美世界"],
                "上榜日": ["2024-04-03"],
                "龙虎榜净买额": [1000.0],
                "换手率": [12.0],
                "上榜原因": ["日涨幅偏离值达7%"],
            }
        )
        mock_lhb_dates.return_value = pd.DataFrame({"日期": ["2024-04-03"]})
        mock_lhb_side.return_value = pd.DataFrame(
            {
                "营业部名称": ["机构专用"],
                "买入金额": [800.0],
                "卖出金额": [100.0],
            }
        )
        mock_lhb_stats.return_value = pd.DataFrame(
            {
                "代码": ["002624"],
                "最近上榜日": ["2024-04-03"],
                "上榜次数": [2],
                "龙虎榜净买额": [1200.0],
                "买方机构次数": [1],
                "卖方机构次数": [0],
            }
        )

        result = get_unusual_trading_activity("002624.SZ", "2024-04-01", "2024-04-10")

        self.assertIn("LHB appearances", result)
        self.assertIn("Seat detail snapshot", result)
        self.assertIn("Recent LHB statistics", result)
        self.assertIn("龙虎榜净买额", result)

    @patch("tradingagents.dataflows.a_share.get_previous_trade_date")
    @patch("tradingagents.dataflows.a_share.ak.stock_margin_detail_szse", create=True)
    @patch("tradingagents.dataflows.a_share.ak.stock_hsgt_individual_em", create=True)
    @patch("tradingagents.dataflows.a_share.ak.stock_individual_fund_flow", create=True)
    def test_get_capital_flow_regime_context_summarizes_medium_horizon_flow(
        self,
        mock_fund_flow,
        mock_hsgt,
        mock_margin,
        mock_prev_trade_date,
    ):
        mock_prev_trade_date.return_value = "2024-04-10"
        mock_fund_flow.return_value = pd.DataFrame({"主力净流入-净额": [10.0, 8.0, 5.0, -1.0, 2.0]})
        mock_hsgt.return_value = pd.DataFrame({"HOLD_SHARES": [110.0, 100.0, 95.0]})
        mock_margin.return_value = pd.DataFrame({"证券代码": ["002624"], "融资余额": [88.0], "融券余额": [12.0]})

        result = get_capital_flow_regime_context("002624.SZ", "2024-04-11", 5)

        self.assertIn("Main fund-flow regime", result)
        self.assertIn("Northbound regime", result)
        self.assertIn("Margin regime", result)
        self.assertIn("main-fund-flow regime looks supportive", result)
        self.assertIn("northbound positioning has been building", result)

    @patch("tradingagents.dataflows.a_share.get_sector_rotation_context")
    @patch("tradingagents.dataflows.a_share._load_hist_df")
    @patch("tradingagents.dataflows.a_share.ak.stock_board_concept_cons_em", create=True)
    @patch("tradingagents.dataflows.a_share.ak.stock_board_industry_cons_em", create=True)
    def test_get_peer_comparison_context_summarizes_sampled_peer_returns(
        self,
        mock_industry_cons,
        mock_concept_cons,
        mock_hist,
        mock_sector,
    ):
        mock_sector.return_value = "\n".join(
            [
                "# A-share sector rotation context for 002624.SZ",
                "## Industry board sample: 消费电子",
                "Signal: representative peers in 消费电子: 立讯精密, 歌尔股份, 蓝思科技",
                "## Concept board sample: AI手机",
            ]
        )
        mock_industry_cons.return_value = pd.DataFrame(
            {
                "代码": ["002475", "002241", "300433", "002624"],
                "名称": ["立讯精密", "歌尔股份", "蓝思科技", "完美世界"],
            }
        )
        mock_concept_cons.return_value = pd.DataFrame(
            {
                "代码": ["002475", "002241"],
                "名称": ["立讯精密", "歌尔股份"],
            }
        )

        def hist_side_effect(symbol, start_date, end_date):
            close_map = {
                "002624.SZ": [10.0, 12.0],
                "002475.SZ": [10.0, 10.5],
                "002241.SZ": [10.0, 10.2],
                "300433.SZ": [10.0, 9.8],
            }
            return pd.DataFrame(
                {
                    "Date": ["2024-03-20", "2024-04-11"],
                    "Close": close_map[symbol],
                }
            )

        mock_hist.side_effect = hist_side_effect

        result = get_peer_comparison_context("002624.SZ", "2024-04-11", 20)

        self.assertIn("Peer return comparison", result)
        self.assertIn("立讯精密", result)
        self.assertIn("歌尔股份", result)
        self.assertIn("target outperforms 3 sampled peers and lags 0 sampled peers", result)
        self.assertIn("peer-relative strength looks constructive", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_profile_cninfo", create=True)
    def test_get_trading_constraint_context_detects_st_and_board_limit(self, mock_profile):
        mock_profile.return_value = pd.DataFrame(
            {
                "A股简称": ["*ST广珠"],
                "A股代码": ["600382"],
            }
        )

        result = get_trading_constraint_context("600382.SH", "2024-04-11")

        self.assertIn("Board: Main Board", result)
        self.assertIn("Daily price-limit regime: 10%", result)
        self.assertIn("Special treatment flag: ST / *ST detected", result)
        self.assertIn("tighter 5% daily price limit", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_dt_pool_em", create=True)
    @patch("tradingagents.dataflows.a_share.ak.stock_zt_pool_em", create=True)
    def test_get_limit_move_sentiment_context_reads_hot_tape(self, mock_zt_pool, mock_dt_pool):
        mock_zt_pool.return_value = pd.DataFrame(
            {
                "代码": ["000001", "000002", "000003", "000004", "000005", "000006", "000007", "000008", "000009", "000010"],
                "名称": [f"涨停股{i}" for i in range(10)],
                "所属行业": ["AI"] * 10,
                "涨停原因类别": ["算力"] * 10,
                "连板数": [2] * 10,
            }
        )
        mock_dt_pool.return_value = pd.DataFrame(
            {
                "代码": ["300001"],
                "名称": ["跌停股1"],
                "所属行业": ["地产"],
                "跌停原因": ["业绩承压"],
            }
        )

        result = get_limit_move_sentiment_context("2024-04-11")

        self.assertIn("Limit-up pool", result)
        self.assertIn("Limit-down pool", result)
        self.assertIn("speculative risk appetite looks hot", result)
        self.assertIn("limit-up count=10, limit-down count=1", result)

    @patch("tradingagents.dataflows.a_share.get_limit_move_sentiment_context")
    @patch("tradingagents.dataflows.a_share.get_trading_constraint_context")
    @patch("tradingagents.dataflows.a_share.get_peer_comparison_context")
    @patch("tradingagents.dataflows.a_share.get_capital_flow_regime_context")
    @patch("tradingagents.dataflows.a_share.get_unusual_trading_activity")
    @patch("tradingagents.dataflows.a_share.get_relative_strength_context")
    @patch("tradingagents.dataflows.a_share.get_sector_strength_snapshot")
    @patch("tradingagents.dataflows.a_share.get_market_activity")
    @patch("tradingagents.dataflows.a_share.get_company_event_signals")
    def test_get_decision_signal_summary_combines_event_and_activity_reads(
        self,
        mock_events,
        mock_activity,
        mock_strength,
        mock_relative,
        mock_unusual,
        mock_regime,
        mock_peer,
        mock_constraint,
        mock_limit_move,
    ):
        mock_limit_move.return_value = "# A-share limit-move sentiment context for 2024-04-11"
        mock_constraint.return_value = "# A-share trading constraint context for 002624.SZ"
        mock_peer.return_value = "# A-share peer comparison context for 002624.SZ"
        mock_regime.return_value = "# A-share capital flow regime context for 2024-04-11"
        mock_unusual.return_value = "# A-share unusual trading activity for 2024-04-11"
        mock_relative.return_value = "# A-share relative strength context for 2024-04-11"
        mock_strength.return_value = "# A-share sector strength snapshot for 2024-04-11"
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

    @patch("tradingagents.dataflows.a_share.get_limit_move_sentiment_context")
    @patch("tradingagents.dataflows.a_share.get_trading_constraint_context")
    @patch("tradingagents.dataflows.a_share.get_peer_comparison_context")
    @patch("tradingagents.dataflows.a_share.get_capital_flow_regime_context")
    @patch("tradingagents.dataflows.a_share.get_unusual_trading_activity")
    @patch("tradingagents.dataflows.a_share.get_relative_strength_context")
    @patch("tradingagents.dataflows.a_share.get_sector_strength_snapshot")
    @patch("tradingagents.dataflows.a_share.get_sector_rotation_context")
    @patch("tradingagents.dataflows.a_share.get_market_activity")
    @patch("tradingagents.dataflows.a_share.get_company_event_signals")
    def test_decision_signal_summary_absorbs_sector_rotation_context(
        self,
        mock_events,
        mock_activity,
        mock_sector,
        mock_strength,
        mock_relative,
        mock_unusual,
        mock_regime,
        mock_peer,
        mock_constraint,
        mock_limit_move,
    ):
        mock_limit_move.return_value = "# A-share limit-move sentiment context for 2024-04-11"
        mock_constraint.return_value = "# A-share trading constraint context for 002624.SZ"
        mock_peer.return_value = "# A-share peer comparison context for 002624.SZ"
        mock_regime.return_value = "# A-share capital flow regime context for 2024-04-11"
        mock_unusual.return_value = "# A-share unusual trading activity for 2024-04-11"
        mock_relative.return_value = "# A-share relative strength context for 2024-04-11"
        mock_strength.return_value = "# A-share sector strength snapshot for 2024-04-11"
        mock_events.return_value = "# A-share company event signals for 002624.SZ"
        mock_activity.return_value = "# A-share market activity signals for 002624.SZ"
        mock_sector.return_value = "\n".join(
            [
                "# A-share sector rotation context for 002624.SZ",
                "Signal: 消费电子 board snapshot mean 涨跌幅=1.50 across sampled constituents",
                "## Rotation takeaways",
                "- Primary industry context: 消费电子",
            ]
        )

        result = get_decision_signal_summary("002624.SZ", "2024-04-01", "2024-04-10", "2024-04-11")

        self.assertIn("Sector / concept rotation context is available", result)
        self.assertIn("Board snapshot performance is available", result)

    @patch("tradingagents.dataflows.a_share.get_limit_move_sentiment_context")
    @patch("tradingagents.dataflows.a_share.get_trading_constraint_context")
    @patch("tradingagents.dataflows.a_share.get_peer_comparison_context")
    @patch("tradingagents.dataflows.a_share.get_capital_flow_regime_context")
    @patch("tradingagents.dataflows.a_share.get_unusual_trading_activity")
    @patch("tradingagents.dataflows.a_share.get_relative_strength_context")
    @patch("tradingagents.dataflows.a_share.get_sector_strength_snapshot")
    @patch("tradingagents.dataflows.a_share.get_sector_rotation_context")
    @patch("tradingagents.dataflows.a_share.get_market_activity")
    @patch("tradingagents.dataflows.a_share.get_company_event_signals")
    def test_decision_signal_summary_absorbs_sector_strength_snapshot(
        self,
        mock_events,
        mock_activity,
        mock_sector,
        mock_strength,
        mock_relative,
        mock_unusual,
        mock_regime,
        mock_peer,
        mock_constraint,
        mock_limit_move,
    ):
        mock_limit_move.return_value = "# A-share limit-move sentiment context for 2024-04-11"
        mock_constraint.return_value = "# A-share trading constraint context for 002624.SZ"
        mock_peer.return_value = "# A-share peer comparison context for 002624.SZ"
        mock_regime.return_value = "# A-share capital flow regime context for 2024-04-11"
        mock_unusual.return_value = "# A-share unusual trading activity for 2024-04-11"
        mock_relative.return_value = "# A-share relative strength context for 2024-04-11"
        mock_events.return_value = "# A-share company event signals for 002624.SZ"
        mock_activity.return_value = "# A-share market activity signals for 002624.SZ"
        mock_sector.return_value = "# A-share sector rotation context for 002624.SZ"
        mock_strength.return_value = "\n".join(
            [
                "# A-share sector strength snapshot for 2024-04-11",
                "Signal: leading boards currently include AI手机, 消费电子, 华为概念.",
            ]
        )

        result = get_decision_signal_summary("002624.SZ", "2024-04-01", "2024-04-10", "2024-04-11")

        self.assertIn("Broader board-strength rankings are available", result)

    @patch("tradingagents.dataflows.a_share.get_limit_move_sentiment_context")
    @patch("tradingagents.dataflows.a_share.get_trading_constraint_context")
    @patch("tradingagents.dataflows.a_share.get_peer_comparison_context")
    @patch("tradingagents.dataflows.a_share.get_capital_flow_regime_context")
    @patch("tradingagents.dataflows.a_share.get_unusual_trading_activity")
    @patch("tradingagents.dataflows.a_share.get_relative_strength_context")
    @patch("tradingagents.dataflows.a_share.get_sector_strength_snapshot")
    @patch("tradingagents.dataflows.a_share.get_sector_rotation_context")
    @patch("tradingagents.dataflows.a_share.get_market_activity")
    @patch("tradingagents.dataflows.a_share.get_company_event_signals")
    def test_decision_signal_summary_absorbs_relative_strength_context(
        self,
        mock_events,
        mock_activity,
        mock_sector,
        mock_strength,
        mock_relative,
        mock_unusual,
        mock_regime,
        mock_peer,
        mock_constraint,
        mock_limit_move,
    ):
        mock_limit_move.return_value = "# A-share limit-move sentiment context for 2024-04-11"
        mock_constraint.return_value = "# A-share trading constraint context for 002624.SZ"
        mock_peer.return_value = "# A-share peer comparison context for 002624.SZ"
        mock_regime.return_value = "# A-share capital flow regime context for 2024-04-11"
        mock_unusual.return_value = "# A-share unusual trading activity for 2024-04-11"
        mock_events.return_value = "# A-share company event signals for 002624.SZ"
        mock_activity.return_value = "# A-share market activity signals for 002624.SZ"
        mock_sector.return_value = "# A-share sector rotation context for 002624.SZ"
        mock_strength.return_value = "# A-share sector strength snapshot for 2024-04-11"
        mock_relative.return_value = "\n".join(
            [
                "# A-share relative strength context for 002624.SZ",
                "- Signal: stock is outperforming its market benchmark by a meaningful margin.",
            ]
        )

        result = get_decision_signal_summary("002624.SZ", "2024-04-01", "2024-04-10", "2024-04-11")

        self.assertIn("relative-strength alpha versus the market benchmark is positive", result)

    @patch("tradingagents.dataflows.a_share.get_limit_move_sentiment_context")
    @patch("tradingagents.dataflows.a_share.get_trading_constraint_context")
    @patch("tradingagents.dataflows.a_share.get_peer_comparison_context")
    @patch("tradingagents.dataflows.a_share.get_capital_flow_regime_context")
    @patch("tradingagents.dataflows.a_share.get_unusual_trading_activity")
    @patch("tradingagents.dataflows.a_share.get_corporate_action_pressure_context")
    @patch("tradingagents.dataflows.a_share.get_relative_strength_context")
    @patch("tradingagents.dataflows.a_share.get_sector_strength_snapshot")
    @patch("tradingagents.dataflows.a_share.get_sector_rotation_context")
    @patch("tradingagents.dataflows.a_share.get_market_activity")
    @patch("tradingagents.dataflows.a_share.get_company_event_signals")
    def test_decision_signal_summary_absorbs_corporate_action_pressure_context(
        self,
        mock_events,
        mock_activity,
        mock_sector,
        mock_strength,
        mock_relative,
        mock_pressure,
        mock_unusual,
        mock_regime,
        mock_peer,
        mock_constraint,
        mock_limit_move,
    ):
        mock_limit_move.return_value = "# A-share limit-move sentiment context for 2024-04-11"
        mock_constraint.return_value = "# A-share trading constraint context for 002624.SZ"
        mock_peer.return_value = "# A-share peer comparison context for 002624.SZ"
        mock_regime.return_value = "# A-share capital flow regime context for 2024-04-11"
        mock_unusual.return_value = "# A-share unusual trading activity for 2024-04-11"
        mock_events.return_value = "# A-share company event signals for 002624.SZ"
        mock_activity.return_value = "# A-share market activity signals for 002624.SZ"
        mock_sector.return_value = "# A-share sector rotation context for 002624.SZ"
        mock_strength.return_value = "# A-share sector strength snapshot for 2024-04-11"
        mock_relative.return_value = "# A-share relative strength context for 2024-04-11"
        mock_pressure.return_value = "\n".join(
            [
                "# A-share corporate action pressure context for 002624.SZ",
                "- Supply / dilution pressure: high (score=6)",
                "- Governance / legal pressure: high (score=5)",
                "- Positive offset strength: high (score=5)",
            ]
        )

        result = get_decision_signal_summary("002624.SZ", "2024-04-01", "2024-04-10", "2024-04-11")

        self.assertIn("Corporate-action pressure is elevated", result)
        self.assertIn("elevated governance or legal headline risk", result)
        self.assertIn("Positive corporate-action offsets are strong enough", result)

    @patch("tradingagents.dataflows.a_share.get_limit_move_sentiment_context")
    @patch("tradingagents.dataflows.a_share.get_trading_constraint_context")
    @patch("tradingagents.dataflows.a_share.get_peer_comparison_context")
    @patch("tradingagents.dataflows.a_share.get_capital_flow_regime_context")
    @patch("tradingagents.dataflows.a_share.get_unusual_trading_activity")
    @patch("tradingagents.dataflows.a_share.get_corporate_action_pressure_context")
    @patch("tradingagents.dataflows.a_share.get_relative_strength_context")
    @patch("tradingagents.dataflows.a_share.get_sector_strength_snapshot")
    @patch("tradingagents.dataflows.a_share.get_sector_rotation_context")
    @patch("tradingagents.dataflows.a_share.get_market_activity")
    @patch("tradingagents.dataflows.a_share.get_company_event_signals")
    def test_decision_signal_summary_absorbs_unusual_trading_activity(
        self,
        mock_events,
        mock_activity,
        mock_sector,
        mock_strength,
        mock_relative,
        mock_pressure,
        mock_unusual,
        mock_regime,
        mock_peer,
        mock_constraint,
        mock_limit_move,
    ):
        mock_limit_move.return_value = "# A-share limit-move sentiment context for 2024-04-11"
        mock_constraint.return_value = "# A-share trading constraint context for 002624.SZ"
        mock_peer.return_value = "# A-share peer comparison context for 002624.SZ"
        mock_regime.return_value = "# A-share capital flow regime context for 2024-04-11"
        mock_events.return_value = "# A-share company event signals for 002624.SZ"
        mock_activity.return_value = "# A-share market activity signals for 002624.SZ"
        mock_sector.return_value = "# A-share sector rotation context for 002624.SZ"
        mock_strength.return_value = "# A-share sector strength snapshot for 2024-04-11"
        mock_relative.return_value = "# A-share relative strength context for 2024-04-11"
        mock_pressure.return_value = "# A-share corporate action pressure context for 002624.SZ"
        mock_unusual.return_value = "\n".join(
            [
                "# A-share unusual trading activity for 002624.SZ",
                "## LHB appearances",
                "## Seat detail snapshot (20240403)",
            ]
        )

        result = get_decision_signal_summary("002624.SZ", "2024-04-01", "2024-04-10", "2024-04-11")

        self.assertIn("龙虎榜 / unusual-trading records are available", result)
        self.assertIn("席位明细 is available", result)

    @patch("tradingagents.dataflows.a_share.get_limit_move_sentiment_context")
    @patch("tradingagents.dataflows.a_share.get_trading_constraint_context")
    @patch("tradingagents.dataflows.a_share.get_peer_comparison_context")
    @patch("tradingagents.dataflows.a_share.get_capital_flow_regime_context")
    @patch("tradingagents.dataflows.a_share.get_unusual_trading_activity")
    @patch("tradingagents.dataflows.a_share.get_corporate_action_pressure_context")
    @patch("tradingagents.dataflows.a_share.get_relative_strength_context")
    @patch("tradingagents.dataflows.a_share.get_sector_strength_snapshot")
    @patch("tradingagents.dataflows.a_share.get_sector_rotation_context")
    @patch("tradingagents.dataflows.a_share.get_market_activity")
    @patch("tradingagents.dataflows.a_share.get_company_event_signals")
    def test_decision_signal_summary_absorbs_capital_flow_regime_context(
        self,
        mock_events,
        mock_activity,
        mock_sector,
        mock_strength,
        mock_relative,
        mock_pressure,
        mock_unusual,
        mock_regime,
        mock_peer,
        mock_constraint,
        mock_limit_move,
    ):
        mock_limit_move.return_value = "# A-share limit-move sentiment context for 2024-04-11"
        mock_constraint.return_value = "# A-share trading constraint context for 002624.SZ"
        mock_peer.return_value = "# A-share peer comparison context for 002624.SZ"
        mock_events.return_value = "# A-share company event signals for 002624.SZ"
        mock_activity.return_value = "# A-share market activity signals for 002624.SZ"
        mock_sector.return_value = "# A-share sector rotation context for 002624.SZ"
        mock_strength.return_value = "# A-share sector strength snapshot for 2024-04-11"
        mock_relative.return_value = "# A-share relative strength context for 2024-04-11"
        mock_pressure.return_value = "# A-share corporate action pressure context for 002624.SZ"
        mock_unusual.return_value = "# A-share unusual trading activity for 002624.SZ"
        mock_regime.return_value = "\n".join(
            [
                "# A-share capital flow regime context for 002624.SZ",
                "- Signal: medium-horizon main-fund-flow regime looks supportive.",
                "- Signal: northbound positioning has been building over the sampled window.",
            ]
        )

        result = get_decision_signal_summary("002624.SZ", "2024-04-01", "2024-04-10", "2024-04-11")

        self.assertIn("Medium-horizon main-fund-flow regime looks supportive", result)
        self.assertIn("Northbound positioning has been building over the sampled window", result)

    @patch("tradingagents.dataflows.a_share.get_limit_move_sentiment_context")
    @patch("tradingagents.dataflows.a_share.get_trading_constraint_context")
    @patch("tradingagents.dataflows.a_share.get_peer_comparison_context")
    @patch("tradingagents.dataflows.a_share.get_capital_flow_regime_context")
    @patch("tradingagents.dataflows.a_share.get_unusual_trading_activity")
    @patch("tradingagents.dataflows.a_share.get_corporate_action_pressure_context")
    @patch("tradingagents.dataflows.a_share.get_relative_strength_context")
    @patch("tradingagents.dataflows.a_share.get_sector_strength_snapshot")
    @patch("tradingagents.dataflows.a_share.get_market_activity")
    @patch("tradingagents.dataflows.a_share.get_company_event_signals")
    def test_decision_signal_summary_absorbs_flow_trend_clues(
        self,
        mock_events,
        mock_activity,
        mock_strength,
        mock_relative,
        mock_pressure,
        mock_unusual,
        mock_regime,
        mock_peer,
        mock_constraint,
        mock_limit_move,
    ):
        mock_limit_move.return_value = "# A-share limit-move sentiment context for 2024-04-11"
        mock_constraint.return_value = "# A-share trading constraint context for 002624.SZ"
        mock_peer.return_value = "# A-share peer comparison context for 002624.SZ"
        mock_regime.return_value = "# A-share capital flow regime context for 2024-04-11"
        mock_unusual.return_value = "# A-share unusual trading activity for 2024-04-11"
        mock_pressure.return_value = "# A-share corporate action pressure context for 002624.SZ"
        mock_relative.return_value = "# A-share relative strength context for 2024-04-11"
        mock_strength.return_value = "# A-share sector strength snapshot for 2024-04-11"
        mock_events.return_value = "# A-share company event signals for 002624.SZ"
        mock_activity.return_value = "\n".join(
            [
                "# A-share market activity signals for 002624.SZ",
                "Trend: latest main fund flow=100.00, 1-step delta=20.00 (buying pressure strengthening)",
                "Trend: latest northbound HOLD_SHARES=50.00, 1-step delta=5.00 (northbound accumulation)",
                "Trend: latest 融资余额=80.00, 1-step delta=10.00 (leverage demand increasing)",
            ]
        )

        result = get_decision_signal_summary("002624.SZ", "2024-04-01", "2024-04-10", "2024-04-11")

        self.assertIn("incremental buying pressure", result)
        self.assertIn("institutional confirmation", result)
        self.assertIn("Margin-financing demand is rising", result)

    @patch("tradingagents.dataflows.a_share.get_limit_move_sentiment_context")
    @patch("tradingagents.dataflows.a_share.get_trading_constraint_context")
    @patch("tradingagents.dataflows.a_share.get_peer_comparison_context")
    @patch("tradingagents.dataflows.a_share.get_capital_flow_regime_context")
    @patch("tradingagents.dataflows.a_share.get_unusual_trading_activity")
    @patch("tradingagents.dataflows.a_share.get_corporate_action_pressure_context")
    @patch("tradingagents.dataflows.a_share.get_relative_strength_context")
    @patch("tradingagents.dataflows.a_share.get_sector_strength_snapshot")
    @patch("tradingagents.dataflows.a_share.get_sector_rotation_context")
    @patch("tradingagents.dataflows.a_share.get_market_activity")
    @patch("tradingagents.dataflows.a_share.get_company_event_signals")
    def test_decision_signal_summary_absorbs_peer_comparison_context(
        self,
        mock_events,
        mock_activity,
        mock_sector,
        mock_strength,
        mock_relative,
        mock_pressure,
        mock_unusual,
        mock_regime,
        mock_peer,
        mock_constraint,
        mock_limit_move,
    ):
        mock_limit_move.return_value = "# A-share limit-move sentiment context for 2024-04-11"
        mock_constraint.return_value = "# A-share trading constraint context for 002624.SZ"
        mock_events.return_value = "# A-share company event signals for 002624.SZ"
        mock_activity.return_value = "# A-share market activity signals for 002624.SZ"
        mock_sector.return_value = "# A-share sector rotation context for 002624.SZ"
        mock_strength.return_value = "# A-share sector strength snapshot for 2024-04-11"
        mock_relative.return_value = "# A-share relative strength context for 2024-04-11"
        mock_pressure.return_value = "# A-share corporate action pressure context for 002624.SZ"
        mock_unusual.return_value = "# A-share unusual trading activity for 002624.SZ"
        mock_regime.return_value = "# A-share capital flow regime context for 2024-04-11"
        mock_peer.return_value = "\n".join(
            [
                "# A-share peer comparison context for 002624.SZ",
                "- Signal: peer-relative strength looks constructive.",
            ]
        )

        result = get_decision_signal_summary("002624.SZ", "2024-04-01", "2024-04-10", "2024-04-11")

        self.assertIn("Peer-relative strength is constructive", result)

    @patch("tradingagents.dataflows.a_share.get_limit_move_sentiment_context")
    @patch("tradingagents.dataflows.a_share.get_trading_constraint_context")
    @patch("tradingagents.dataflows.a_share.get_peer_comparison_context")
    @patch("tradingagents.dataflows.a_share.get_capital_flow_regime_context")
    @patch("tradingagents.dataflows.a_share.get_unusual_trading_activity")
    @patch("tradingagents.dataflows.a_share.get_corporate_action_pressure_context")
    @patch("tradingagents.dataflows.a_share.get_relative_strength_context")
    @patch("tradingagents.dataflows.a_share.get_sector_strength_snapshot")
    @patch("tradingagents.dataflows.a_share.get_sector_rotation_context")
    @patch("tradingagents.dataflows.a_share.get_market_activity")
    @patch("tradingagents.dataflows.a_share.get_company_event_signals")
    def test_decision_signal_summary_absorbs_trading_constraint_context(
        self,
        mock_events,
        mock_activity,
        mock_sector,
        mock_strength,
        mock_relative,
        mock_pressure,
        mock_unusual,
        mock_regime,
        mock_peer,
        mock_constraint,
        mock_limit_move,
    ):
        mock_limit_move.return_value = "# A-share limit-move sentiment context for 2024-04-11"
        mock_events.return_value = "# A-share company event signals for 688111.SH"
        mock_activity.return_value = "# A-share market activity signals for 688111.SH"
        mock_sector.return_value = "# A-share sector rotation context for 688111.SH"
        mock_strength.return_value = "# A-share sector strength snapshot for 2024-04-11"
        mock_relative.return_value = "# A-share relative strength context for 688111.SH"
        mock_pressure.return_value = "# A-share corporate action pressure context for 688111.SH"
        mock_unusual.return_value = "# A-share unusual trading activity for 688111.SH"
        mock_regime.return_value = "# A-share capital flow regime context for 2024-04-11"
        mock_peer.return_value = "# A-share peer comparison context for 688111.SH"
        mock_constraint.return_value = "\n".join(
            [
                "# A-share trading constraint context for 688111.SH",
                "- Daily price-limit regime: 20%",
                "- Special treatment flag: ST / *ST detected from the security short name.",
            ]
        )

        result = get_decision_signal_summary("688111.SH", "2024-04-01", "2024-04-10", "2024-04-11")

        self.assertIn("Special-treatment status is present", result)
        self.assertIn("20% daily price-limit regime", result)

    @patch("tradingagents.dataflows.a_share.get_limit_move_sentiment_context")
    @patch("tradingagents.dataflows.a_share.get_trading_constraint_context")
    @patch("tradingagents.dataflows.a_share.get_peer_comparison_context")
    @patch("tradingagents.dataflows.a_share.get_capital_flow_regime_context")
    @patch("tradingagents.dataflows.a_share.get_unusual_trading_activity")
    @patch("tradingagents.dataflows.a_share.get_corporate_action_pressure_context")
    @patch("tradingagents.dataflows.a_share.get_relative_strength_context")
    @patch("tradingagents.dataflows.a_share.get_sector_strength_snapshot")
    @patch("tradingagents.dataflows.a_share.get_sector_rotation_context")
    @patch("tradingagents.dataflows.a_share.get_market_activity")
    @patch("tradingagents.dataflows.a_share.get_company_event_signals")
    def test_decision_signal_summary_absorbs_limit_move_sentiment_context(
        self,
        mock_events,
        mock_activity,
        mock_sector,
        mock_strength,
        mock_relative,
        mock_pressure,
        mock_unusual,
        mock_regime,
        mock_peer,
        mock_constraint,
        mock_limit_move,
    ):
        mock_events.return_value = "# A-share company event signals for 002624.SZ"
        mock_activity.return_value = "# A-share market activity signals for 002624.SZ"
        mock_sector.return_value = "# A-share sector rotation context for 002624.SZ"
        mock_strength.return_value = "# A-share sector strength snapshot for 2024-04-11"
        mock_relative.return_value = "# A-share relative strength context for 002624.SZ"
        mock_pressure.return_value = "# A-share corporate action pressure context for 002624.SZ"
        mock_unusual.return_value = "# A-share unusual trading activity for 002624.SZ"
        mock_regime.return_value = "# A-share capital flow regime context for 2024-04-11"
        mock_peer.return_value = "# A-share peer comparison context for 002624.SZ"
        mock_constraint.return_value = "# A-share trading constraint context for 002624.SZ"
        mock_limit_move.return_value = "\n".join(
            [
                "# A-share limit-move sentiment context for 2024-04-11",
                "- Signal: speculative risk appetite looks hot, with limit-up breadth dominating limit-down stress.",
            ]
        )

        result = get_decision_signal_summary("002624.SZ", "2024-04-01", "2024-04-10", "2024-04-11")

        self.assertIn("涨停 breadth is dominating跌停 stress", result)

    @patch("tradingagents.dataflows.y_finance._get_stock_stats_bulk")
    def test_indicator_window_falls_back_to_latest_available_trading_day(self, mock_bulk):
        mock_bulk.return_value = {
            "2024-04-10": "1.23",
            "2024-04-09": "1.11",
            "__latest_available_date__": "2024-04-10",
        }

        result = get_stock_stats_indicators_window("002624.SS", "macd", "2024-04-11", 2)

        self.assertIn(
            "2024-04-11: 1.23 [fallback from 2024-04-11 to latest available trading day 2024-04-10]",
            result,
        )
        self.assertIn("2024-04-10: 1.23", result)
