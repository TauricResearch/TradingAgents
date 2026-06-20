import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import pytest


def _create_test_db(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE stock_list (code TEXT PRIMARY KEY, name TEXT, industry TEXT);
        INSERT INTO stock_list VALUES ('600519', '贵州茅台', '白酒');
        CREATE TABLE daily_bars (
            ts_code TEXT, trade_date TEXT, open REAL, high REAL,
            low REAL, close REAL, volume REAL,
            PRIMARY KEY (ts_code, trade_date)
        );
        INSERT INTO daily_bars VALUES ('600519','2026-06-15',1500.0,1520.0,1490.0,1510.0,50000);
        INSERT INTO daily_bars VALUES ('600519','2026-06-16',1510.0,1530.0,1500.0,1525.0,55000);
        INSERT INTO daily_bars VALUES ('600519','2026-06-17',1525.0,1540.0,1510.0,1535.0,48000);
        INSERT INTO daily_bars VALUES ('600519','2026-06-18',1535.0,1550.0,1525.0,1540.0,52000);
        INSERT INTO daily_bars VALUES ('600519','2026-06-19',1540.0,1560.0,1530.0,1550.0,60000);
        CREATE TABLE indicators (
            ts_code TEXT, trade_date TEXT, close REAL, volume REAL,
            ma5 REAL, ma10 REAL, rsi6 REAL, macd_hist REAL,
            PRIMARY KEY (ts_code, trade_date)
        );
        INSERT INTO indicators VALUES ('600519','2026-06-15',1510.0,50000,1510.0,1500.0,55.0,1.2);
        INSERT INTO indicators VALUES ('600519','2026-06-19',1550.0,60000,1540.0,1520.0,65.0,2.2);
        CREATE TABLE fundamentals (
            ts_code TEXT, trade_date TEXT, pe REAL, pb REAL, roe REAL,
            PRIMARY KEY (ts_code, trade_date)
        );
        INSERT INTO fundamentals VALUES ('600519','2026-06-19',25.0,8.0,32.0);
    """)
    conn.commit()
    conn.close()


def _create_full_test_db(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE stock_list (code TEXT PRIMARY KEY, name TEXT, industry TEXT);
        INSERT INTO stock_list VALUES ('600519', '贵州茅台', '白酒');

        CREATE TABLE daily_bars (
            ts_code TEXT, trade_date TEXT, open REAL, high REAL,
            low REAL, close REAL, volume REAL,
            PRIMARY KEY (ts_code, trade_date)
        );
        INSERT INTO daily_bars VALUES ('600519','2026-06-15',1500.0,1520.0,1490.0,1510.0,50000);
        INSERT INTO daily_bars VALUES ('600519','2026-06-16',1510.0,1530.0,1500.0,1525.0,55000);
        INSERT INTO daily_bars VALUES ('600519','2026-06-17',1525.0,1540.0,1510.0,1535.0,48000);
        INSERT INTO daily_bars VALUES ('600519','2026-06-18',1535.0,1550.0,1525.0,1540.0,52000);
        INSERT INTO daily_bars VALUES ('600519','2026-06-19',1540.0,1560.0,1530.0,1550.0,60000);

        CREATE TABLE indicators (
            ts_code TEXT, trade_date TEXT, close REAL, volume REAL,
            ma5 REAL, ma10 REAL, ma20 REAL, ma60 REAL,
            vol_ma5 REAL, vol_ma50 REAL, vol_ma60 REAL,
            boll_upper REAL, boll_mid REAL, boll_lower REAL, boll_bandwidth REAL,
            cyc60 REAL, chip_concentration REAL,
            macd_dif REAL, macd_dea REAL, macd_hist REAL,
            kdj_k REAL, kdj_d REAL, kdj_j REAL,
            rsi6 REAL, rsi12 REAL, rsi24 REAL, cci REAL,
            PRIMARY KEY (ts_code, trade_date)
        );
        INSERT INTO indicators VALUES ('600519','2026-06-15',1510.0,50000,1510.0,1500.0,1490.0,1480.0,50000,48000,47000,1520.0,1500.0,1480.0,2.5,1500.0,0.85,1.0,0.5,1.2,55.0,50.0,45.0,55.0,50.0,45.0,100.0);
        INSERT INTO indicators VALUES ('600519','2026-06-19',1550.0,60000,1540.0,1520.0,1510.0,1500.0,55000,50000,49000,1560.0,1540.0,1520.0,2.8,1520.0,0.80,2.0,1.0,2.2,65.0,60.0,55.0,65.0,60.0,55.0,120.0);

        CREATE TABLE fundamentals (
            ts_code TEXT, trade_date TEXT, pe_ttm REAL, pb REAL, roe REAL,
            market_cap REAL, ps_ttm REAL, dividend_yield REAL,
            roa REAL, gross_margin REAL, net_margin REAL,
            revenue_growth REAL, profit_growth REAL, eps_growth REAL, peg REAL,
            debt_ratio REAL,
            PRIMARY KEY (ts_code, trade_date)
        );
        INSERT INTO fundamentals VALUES ('600519','2026-06-19',25.0,8.0,32.0,2.0e11,10.0,0.02,15.0,90.0,50.0,20.0,25.0,18.0,2.0,35.0);

        CREATE TABLE fund_flow (
            ts_code TEXT, trade_date TEXT,
            main_net_inflow REAL, main_net_inflow_pct REAL,
            super_large_net_inflow REAL, super_large_net_inflow_pct REAL,
            large_net_inflow REAL, large_net_inflow_pct REAL,
            is_simulated INTEGER,
            PRIMARY KEY (ts_code, trade_date)
        );
        INSERT INTO fund_flow VALUES ('600519','2026-06-19',1.0e8,0.05,5.0e7,0.03,3.0e7,0.02,0);
        INSERT INTO fund_flow VALUES ('600519','2026-06-18',-5.0e7,-0.02,-2.0e7,-0.01,-1.0e7,-0.005,1);

        CREATE TABLE margin_trading (
            ts_code TEXT, trade_date TEXT,
            margin_balance REAL, margin_buy REAL, margin_repay REAL,
            short_balance REAL, short_sell REAL, short_repay REAL, total_balance REAL,
            PRIMARY KEY (ts_code, trade_date)
        );
        INSERT INTO margin_trading VALUES ('600519','2026-06-19',1.0e10,5.0e8,4.0e8,1.0e6,2.0e5,1.0e5,1.001e10);

        CREATE TABLE dragon_tiger (
            ts_code TEXT, trade_date TEXT,
            close_price REAL, pct_change REAL,
            net_buy_amount REAL, buy_amount REAL, sell_amount REAL,
            turnover_rate REAL, market_cap REAL, reason TEXT,
            PRIMARY KEY (ts_code, trade_date)
        );
        INSERT INTO dragon_tiger VALUES ('600519','2026-06-19',1550.0,2.5,1.0e7,5.0e7,4.0e7,0.01,2.0e11,'日涨幅偏离值达7%');

        CREATE TABLE block_trade (
            ts_code TEXT, trade_date TEXT,
            deal_price REAL, close_price REAL, discount_rate REAL,
            volume REAL, amount REAL,
            buyer_branch TEXT, seller_branch TEXT,
            PRIMARY KEY (ts_code, trade_date)
        );
        INSERT INTO block_trade VALUES ('600519','2026-06-19',1500.0,1550.0,3.2,100000,1.5e8,'中信证券','华泰证券');

        CREATE TABLE sector_fund_flow (
            trade_date TEXT, sector_name TEXT,
            main_net_inflow REAL, main_net_inflow_pct REAL,
            super_large_net_inflow REAL, large_net_inflow REAL,
            medium_net_inflow REAL, small_net_inflow REAL,
            PRIMARY KEY (trade_date, sector_name)
        );
        INSERT INTO sector_fund_flow VALUES ('2026-06-19','白酒',2.0e8,0.03,1.0e8,5.0e7,2.0e7,-1.0e7);

        CREATE TABLE shareholder_count (
            ts_code TEXT, report_date TEXT,
            holder_count INTEGER, holder_count_change_pct REAL, avg_shares_per_holder REAL,
            PRIMARY KEY (ts_code, report_date)
        );
        INSERT INTO shareholder_count VALUES ('600519','2026-06-19',100000,-2.5,5000);
    """)
    conn.commit()
    conn.close()


class _PatchedVendor:
    def __init__(self, db_path):
        self.db_path = db_path

    def __enter__(self):
        self.patcher = patch(
            "tradingagents.dataflows.smartmoney_vendor._DB_PATH", self.db_path
        )
        self.patcher.start()
        return self

    def __exit__(self, *args):
        self.patcher.stop()


@pytest.mark.unit
class ToSmartmoneySymbolTests(unittest.TestCase):
    def test_strips_ss_suffix(self):
        from tradingagents.dataflows.smartmoney_vendor import _to_smartmoney_symbol
        self.assertEqual(_to_smartmoney_symbol("600519.SS"), "600519")


@pytest.mark.unit
class GetConnectionTests(unittest.TestCase):
    @patch("tradingagents.dataflows.smartmoney_vendor._DB_PATH", "/nonexistent/db.db")
    def test_raises_on_missing_db(self):
        from tradingagents.dataflows.smartmoney_vendor import _get_connection
        with self.assertRaises(FileNotFoundError):
            _get_connection()


@pytest.mark.unit
class DfFromSqlTests(unittest.TestCase):
    def test_returns_none_on_error(self):
        from tradingagents.dataflows.smartmoney_vendor import _df_from_sql
        with patch("tradingagents.dataflows.smartmoney_vendor._get_connection") as mock_conn:
            mock_conn.side_effect = Exception("db error")
            self.assertIsNone(_df_from_sql("SELECT 1"))


@pytest.mark.unit
class DfFromSqlEmptyTests(unittest.TestCase):
    def test_returns_none_on_empty_result(self):
        from tradingagents.dataflows.smartmoney_vendor import _df_from_sql

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE t (x int)")
            conn.close()
            with _PatchedVendor(db_path):
                df = _df_from_sql("SELECT * FROM t WHERE x = 999")
                self.assertIsNotNone(df)
                self.assertTrue(df.empty)
        finally:
            os.unlink(db_path)


@pytest.mark.unit
class GetStockDataTests(unittest.TestCase):
    def test_returns_csv(self):
        from tradingagents.dataflows.smartmoney_vendor import get_stock_data

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_test_db(db_path)
            with _PatchedVendor(db_path):
                result = get_stock_data("600519.SS", "2026-06-15", "2026-06-19")
                self.assertIn("600519", result)
                self.assertIn("Close", result)
        finally:
            os.unlink(db_path)

    def test_raises_on_no_data(self):
        from tradingagents.dataflows.smartmoney_vendor import get_stock_data

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_test_db(db_path)
            with _PatchedVendor(db_path):
                with self.assertRaises(RuntimeError):
                    get_stock_data("999999.SS", "2026-06-15", "2026-06-19")
        finally:
            os.unlink(db_path)


@pytest.mark.unit
class GetFundamentalsTests(unittest.TestCase):
    def test_returns_fundamentals(self):
        from tradingagents.dataflows.smartmoney_vendor import get_fundamentals

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_test_db(db_path)
            with _PatchedVendor(db_path):
                result = get_fundamentals("600519.SS", "2026-06-19")
                self.assertIn("600519", result)
                self.assertIn("贵州茅台", result)
        finally:
            os.unlink(db_path)


@pytest.mark.unit
class GetFundFlowTests(unittest.TestCase):
    def test_returns_fund_flow_data(self):
        from tradingagents.dataflows.smartmoney_vendor import get_fund_flow

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_full_test_db(db_path)
            with _PatchedVendor(db_path):
                result = get_fund_flow("600519.SS")
                self.assertIn("600519", result)
                self.assertIn("Main Force Net Inflow", result)
        finally:
            os.unlink(db_path)

    def test_raises_on_no_data(self):
        from tradingagents.dataflows.smartmoney_vendor import get_fund_flow

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_full_test_db(db_path)
            with _PatchedVendor(db_path):
                with self.assertRaises(RuntimeError):
                    get_fund_flow("999999.SS")
        finally:
            os.unlink(db_path)

    def test_shows_simulated_note(self):
        from tradingagents.dataflows.smartmoney_vendor import get_fund_flow

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            conn.executescript("""
                CREATE TABLE fund_flow (
                    ts_code TEXT, trade_date TEXT,
                    main_net_inflow REAL, main_net_inflow_pct REAL,
                    super_large_net_inflow REAL, super_large_net_inflow_pct REAL,
                    large_net_inflow REAL, large_net_inflow_pct REAL,
                    is_simulated INTEGER,
                    PRIMARY KEY (ts_code, trade_date)
                );
                INSERT INTO fund_flow VALUES ('600519','2026-06-19',1e8,0.05,5e7,0.03,3e7,0.02,1);
            """)
            conn.close()
            with _PatchedVendor(db_path):
                result = get_fund_flow("600519.SS")
                self.assertIn("simulated", result)
        finally:
            os.unlink(db_path)


@pytest.mark.unit
class GetMarginTradingTests(unittest.TestCase):
    def test_returns_margin_trading_data(self):
        from tradingagents.dataflows.smartmoney_vendor import get_margin_trading

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_full_test_db(db_path)
            with _PatchedVendor(db_path):
                result = get_margin_trading("600519.SS")
                self.assertIn("融资余额", result)
                self.assertIn("融券余量", result)
        finally:
            os.unlink(db_path)

    def test_raises_on_no_data(self):
        from tradingagents.dataflows.smartmoney_vendor import get_margin_trading

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_full_test_db(db_path)
            with _PatchedVendor(db_path):
                with self.assertRaises(RuntimeError):
                    get_margin_trading("999999.SS")
        finally:
            os.unlink(db_path)


@pytest.mark.unit
class GetDragonTigerTests(unittest.TestCase):
    def test_returns_dragon_tiger_data(self):
        from tradingagents.dataflows.smartmoney_vendor import get_dragon_tiger

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_full_test_db(db_path)
            with _PatchedVendor(db_path):
                result = get_dragon_tiger("600519.SS")
                self.assertIn("龙虎榜", result)
                self.assertIn("日涨幅偏离值达7%", result)
        finally:
            os.unlink(db_path)

    def test_raises_on_no_data(self):
        from tradingagents.dataflows.smartmoney_vendor import get_dragon_tiger

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_full_test_db(db_path)
            with _PatchedVendor(db_path):
                with self.assertRaises(RuntimeError):
                    get_dragon_tiger("999999.SS")
        finally:
            os.unlink(db_path)

    def test_handles_missing_reason_column(self):
        from tradingagents.dataflows.smartmoney_vendor import get_dragon_tiger

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            conn.executescript("""
                CREATE TABLE dragon_tiger (
                    ts_code TEXT, trade_date TEXT,
                    close_price REAL, pct_change REAL,
                    net_buy_amount REAL, buy_amount REAL, sell_amount REAL,
                    turnover_rate REAL, market_cap REAL, reason TEXT,
                    PRIMARY KEY (ts_code, trade_date)
                );
                INSERT INTO dragon_tiger VALUES ('600519','2026-06-19',1550.0,2.5,1e7,5e7,4e7,0.01,2e11,NULL);
            """)
            conn.close()
            with _PatchedVendor(db_path):
                result = get_dragon_tiger("600519.SS")
                self.assertIn("龙虎榜", result)
        finally:
            os.unlink(db_path)


@pytest.mark.unit
class GetBlockTradeTests(unittest.TestCase):
    def test_returns_block_trade_data(self):
        from tradingagents.dataflows.smartmoney_vendor import get_block_trade

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_full_test_db(db_path)
            with _PatchedVendor(db_path):
                result = get_block_trade("600519.SS")
                self.assertIn("大宗交易", result)
                self.assertIn("中信证券", result)
                self.assertIn("华泰证券", result)
        finally:
            os.unlink(db_path)

    def test_raises_on_no_data(self):
        from tradingagents.dataflows.smartmoney_vendor import get_block_trade

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_full_test_db(db_path)
            with _PatchedVendor(db_path):
                with self.assertRaises(RuntimeError):
                    get_block_trade("999999.SS")
        finally:
            os.unlink(db_path)

    def test_handles_null_buyer_seller(self):
        from tradingagents.dataflows.smartmoney_vendor import get_block_trade

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            conn.executescript("""
                CREATE TABLE block_trade (
                    ts_code TEXT, trade_date TEXT,
                    deal_price REAL, close_price REAL, discount_rate REAL,
                    volume REAL, amount REAL,
                    buyer_branch TEXT, seller_branch TEXT,
                    PRIMARY KEY (ts_code, trade_date)
                );
                INSERT INTO block_trade VALUES ('600519','2026-06-19',1500.0,1550.0,3.2,100000,1.5e8,NULL,NULL);
            """)
            conn.close()
            with _PatchedVendor(db_path):
                result = get_block_trade("600519.SS")
                self.assertIn("None", result)
        finally:
            os.unlink(db_path)


@pytest.mark.unit
class GetSectorFundFlowTests(unittest.TestCase):
    def test_returns_sector_fund_flow_data(self):
        from tradingagents.dataflows.smartmoney_vendor import get_sector_fund_flow

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_full_test_db(db_path)
            with _PatchedVendor(db_path):
                result = get_sector_fund_flow("白酒")
                self.assertIn("白酒", result)
                self.assertIn("Sector Fund Flow", result)
        finally:
            os.unlink(db_path)

    def test_raises_on_no_data(self):
        from tradingagents.dataflows.smartmoney_vendor import get_sector_fund_flow

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_full_test_db(db_path)
            with _PatchedVendor(db_path):
                with self.assertRaises(RuntimeError):
                    get_sector_fund_flow("Nonexistent Sector")
        finally:
            os.unlink(db_path)


@pytest.mark.unit
class GetShareholderCountTests(unittest.TestCase):
    def test_returns_shareholder_count_data(self):
        from tradingagents.dataflows.smartmoney_vendor import get_shareholder_count

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_full_test_db(db_path)
            with _PatchedVendor(db_path):
                result = get_shareholder_count("600519.SS")
                self.assertIn("股东户数", result)
                self.assertIn("100,000", result)
        finally:
            os.unlink(db_path)

    def test_raises_on_no_data(self):
        from tradingagents.dataflows.smartmoney_vendor import get_shareholder_count

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_full_test_db(db_path)
            with _PatchedVendor(db_path):
                with self.assertRaises(RuntimeError):
                    get_shareholder_count("999999.SS")
        finally:
            os.unlink(db_path)


@pytest.mark.unit
class RuntimeErrorStubsTests(unittest.TestCase):
    def test_get_insider_transactions_raises(self):
        from tradingagents.dataflows.smartmoney_vendor import get_insider_transactions
        with self.assertRaises(RuntimeError) as ctx:
            get_insider_transactions("600519.SS")
        self.assertIn("Insider transactions", str(ctx.exception))

    def test_get_company_announcements_raises(self):
        from tradingagents.dataflows.smartmoney_vendor import get_company_announcements
        with self.assertRaises(RuntimeError) as ctx:
            get_company_announcements("600519.SS", "2026-06-01", "2026-06-19")
        self.assertIn("Company announcements", str(ctx.exception))

    def test_get_restricted_release_raises(self):
        from tradingagents.dataflows.smartmoney_vendor import get_restricted_release
        with self.assertRaises(RuntimeError) as ctx:
            get_restricted_release("600519.SS")
        self.assertIn("Restricted release", str(ctx.exception))

    def test_get_institutional_holdings_raises(self):
        from tradingagents.dataflows.smartmoney_vendor import get_institutional_holdings
        with self.assertRaises(RuntimeError) as ctx:
            get_institutional_holdings("600519.SS")
        self.assertIn("Institutional holdings", str(ctx.exception))

    def test_get_northbound_hold_raises(self):
        from tradingagents.dataflows.smartmoney_vendor import get_northbound_hold
        with self.assertRaises(RuntimeError) as ctx:
            get_northbound_hold("600519.SS")
        self.assertIn("Northbound holdings", str(ctx.exception))

    def test_get_industry_valuation_raises(self):
        from tradingagents.dataflows.smartmoney_vendor import get_industry_valuation
        with self.assertRaises(RuntimeError) as ctx:
            get_industry_valuation("600519.SS")
        self.assertIn("Industry valuation", str(ctx.exception))

    def test_get_news_raises(self):
        from tradingagents.dataflows.smartmoney_vendor import get_news
        with self.assertRaises(RuntimeError) as ctx:
            get_news("600519.SS", "2026-01-01", "2026-06-19")
        self.assertIn("News not available", str(ctx.exception))

    def test_get_earnings_estimates_raises(self):
        from tradingagents.dataflows.smartmoney_vendor import get_earnings_estimates
        with self.assertRaises(RuntimeError) as ctx:
            get_earnings_estimates("600519.SS")
        self.assertIn("Earnings estimates", str(ctx.exception))

    def test_get_macro_indicators_raises(self):
        from tradingagents.dataflows.smartmoney_vendor import get_macro_indicators
        with self.assertRaises(RuntimeError) as ctx:
            get_macro_indicators()
        self.assertIn("Macro indicators", str(ctx.exception))

    def test_get_balance_sheet_raises(self):
        from tradingagents.dataflows.smartmoney_vendor import get_balance_sheet
        with self.assertRaises(RuntimeError) as ctx:
            get_balance_sheet("600519.SS")
        self.assertIn("Balance sheet", str(ctx.exception))

    def test_get_cashflow_raises(self):
        from tradingagents.dataflows.smartmoney_vendor import get_cashflow
        with self.assertRaises(RuntimeError) as ctx:
            get_cashflow("600519.SS")
        self.assertIn("Cashflow statement", str(ctx.exception))

    def test_get_income_statement_raises(self):
        from tradingagents.dataflows.smartmoney_vendor import get_income_statement
        with self.assertRaises(RuntimeError) as ctx:
            get_income_statement("600519.SS")
        self.assertIn("Income statement", str(ctx.exception))


@pytest.mark.unit
class GetIndicatorsTests(unittest.TestCase):
    def test_unknown_indicator_raises(self):
        from tradingagents.dataflows.smartmoney_vendor import get_indicators

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_full_test_db(db_path)
            with _PatchedVendor(db_path):
                with self.assertRaises(RuntimeError):
                    get_indicators("600519.SS", "zzz_not_an_indicator", "2026-06-19", 5)
        finally:
            os.unlink(db_path)

    def test_no_ohlcv_data_raises(self):
        from tradingagents.dataflows.smartmoney_vendor import get_indicators

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_full_test_db(db_path)
            with _PatchedVendor(db_path):
                with self.assertRaises(RuntimeError):
                    get_indicators("999999.SS", "rsi6", "2026-06-19", 5)
        finally:
            os.unlink(db_path)

    def test_precomputed_indicator_returns_values(self):
        from tradingagents.dataflows.smartmoney_vendor import get_indicators

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_full_test_db(db_path)
            with _PatchedVendor(db_path):
                result = get_indicators("600519.SS", "ma5", "2026-06-19", 5)
                self.assertIn("ma5", result)
                self.assertIn("600519", result)
        finally:
            os.unlink(db_path)

    def test_precomputed_indicator_no_indicator_table(self):
        from tradingagents.dataflows.smartmoney_vendor import get_indicators

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            conn.executescript("""
                CREATE TABLE daily_bars (
                    ts_code TEXT, trade_date TEXT, open REAL, high REAL,
                    low REAL, close REAL, volume REAL,
                    PRIMARY KEY (ts_code, trade_date)
                );
                INSERT INTO daily_bars VALUES ('600519','2026-06-15',1500.0,1520.0,1490.0,1510.0,50000);
                INSERT INTO daily_bars VALUES ('600519','2026-06-16',1510.0,1530.0,1500.0,1525.0,55000);
                INSERT INTO daily_bars VALUES ('600519','2026-06-17',1525.0,1540.0,1510.0,1535.0,48000);
                INSERT INTO daily_bars VALUES ('600519','2026-06-18',1535.0,1550.0,1525.0,1540.0,52000);
                INSERT INTO daily_bars VALUES ('600519','2026-06-19',1540.0,1560.0,1530.0,1550.0,60000);
            """)
            conn.close()
            with _PatchedVendor(db_path):
                with self.assertRaises(RuntimeError):
                    get_indicators("600519.SS", "rsi6", "2026-06-19", 5)
        finally:
            os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()
