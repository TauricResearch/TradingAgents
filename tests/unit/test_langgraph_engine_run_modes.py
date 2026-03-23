"""
Tests for LangGraphEngine run modes:
  - run_scan
  - run_pipeline
  - run_portfolio
  - run_auto
  - _extract_tickers_from_scan_data (pure unit)
"""
import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

# Ensure project root is on sys.path (works in CI and local)
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from agent_os.backend.services.langgraph_engine import LangGraphEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _collect(agen):
    """Collect all events from an async generator into a list."""
    events = []
    async for evt in agen:
        events.append(evt)
    return events


def _root_chain_end_event(output: dict) -> dict:
    """Build a synthetic root on_chain_end LangGraph v2 event."""
    return {
        "event": "on_chain_end",
        "name": "LangGraph",
        "parent_ids": [],
        "metadata": {},  # no langgraph_node key → root event
        "data": {"output": output},
        "run_id": "test-run-id",
        "tags": [],
    }


# ---------------------------------------------------------------------------
# TestRunScanReportStorage
# ---------------------------------------------------------------------------

class TestRunScanReportStorage(unittest.TestCase):
    """Tests for run_scan report saving behaviour."""

    _FINAL_STATE = {
        "geopolitical_report": "geo report text",
        "market_movers_report": "movers report text",
        "sector_performance_report": "sector report text",
        "industry_deep_dive_report": "industry report text",
        "macro_scan_summary": '{"stocks_to_investigate": ["AAPL"]}',
    }

    def _make_mock_scanner(self, final_state=None):
        """Return a mock ScannerGraph whose graph.astream_events yields one root event."""
        if final_state is None:
            final_state = self._FINAL_STATE

        async def mock_astream(*args, **kwargs):
            yield _root_chain_end_event(final_state)

        mock_graph = MagicMock()
        mock_graph.astream_events = mock_astream
        mock_scanner = MagicMock()
        mock_scanner.graph = mock_graph
        return mock_scanner

    def test_run_scan_saves_md_files(self):
        """run_scan should write .md files for each report key to the market dir."""
        mock_scanner = self._make_mock_scanner()
        fake_dir = MagicMock(spec=Path)
        fake_dir.__truediv__ = lambda self, name: MagicMock(spec=Path, name=name)
        written = {}

        def make_fake_path(name):
            p = MagicMock(spec=Path)
            p.write_text = MagicMock(side_effect=lambda text: written.__setitem__(name, text))
            return p

        fake_dir.__truediv__ = MagicMock(side_effect=make_fake_path)
        fake_dir.mkdir = MagicMock()

        engine = LangGraphEngine()

        with patch("agent_os.backend.services.langgraph_engine.ScannerGraph", return_value=mock_scanner), \
             patch("agent_os.backend.services.langgraph_engine.get_market_dir", return_value=fake_dir), \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"), \
             patch("agent_os.backend.services.langgraph_engine.extract_json", return_value={}):
            mock_rs_cls.return_value.save_scan = MagicMock()
            events = asyncio.run(_collect(engine.run_scan("run1", {"date": "2026-01-01"})))

        # All five report keys should have been written (the path uses f"{key}.md")
        for key in ("geopolitical_report", "market_movers_report", "sector_performance_report",
                    "industry_deep_dive_report", "macro_scan_summary"):
            self.assertIn(f"{key}.md", written, f"Expected write_text called for {key}.md")

    def test_run_scan_saves_report_store_json(self):
        """run_scan should call ReportStore().save_scan with the parsed summary dict."""
        mock_scanner = self._make_mock_scanner()
        parsed = {"stocks_to_investigate": ["AAPL"]}

        engine = LangGraphEngine()

        with patch("agent_os.backend.services.langgraph_engine.ScannerGraph", return_value=mock_scanner), \
             patch("agent_os.backend.services.langgraph_engine.get_market_dir") as mock_gmd, \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"), \
             patch("agent_os.backend.services.langgraph_engine.extract_json", return_value=parsed):
            fake_dir = MagicMock(spec=Path)
            fake_dir.__truediv__ = MagicMock(return_value=MagicMock(spec=Path))
            fake_dir.mkdir = MagicMock()
            mock_gmd.return_value = fake_dir
            mock_store = MagicMock()
            mock_rs_cls.return_value = mock_store

            asyncio.run(_collect(engine.run_scan("run1", {"date": "2026-01-01"})))

        mock_store.save_scan.assert_called_once_with("2026-01-01", parsed)

    def test_run_scan_appends_digest(self):
        """run_scan should call append_to_digest once with scan/Market Scan."""
        mock_scanner = self._make_mock_scanner()
        engine = LangGraphEngine()

        with patch("agent_os.backend.services.langgraph_engine.ScannerGraph", return_value=mock_scanner), \
             patch("agent_os.backend.services.langgraph_engine.get_market_dir") as mock_gmd, \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest") as mock_digest, \
             patch("agent_os.backend.services.langgraph_engine.extract_json", return_value={}):
            fake_dir = MagicMock(spec=Path)
            fake_dir.__truediv__ = MagicMock(return_value=MagicMock(spec=Path))
            fake_dir.mkdir = MagicMock()
            mock_gmd.return_value = fake_dir
            mock_rs_cls.return_value.save_scan = MagicMock()

            asyncio.run(_collect(engine.run_scan("run1", {"date": "2026-01-01"})))

        mock_digest.assert_called_once()
        call_args = mock_digest.call_args[0]
        self.assertEqual(call_args[0], "2026-01-01")
        self.assertEqual(call_args[1], "scan")
        self.assertEqual(call_args[2], "Market Scan")

    def test_run_scan_yields_log_events(self):
        """run_scan should yield at least one log event before and after streaming."""
        mock_scanner = self._make_mock_scanner()
        engine = LangGraphEngine()

        with patch("agent_os.backend.services.langgraph_engine.ScannerGraph", return_value=mock_scanner), \
             patch("agent_os.backend.services.langgraph_engine.get_market_dir") as mock_gmd, \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"), \
             patch("agent_os.backend.services.langgraph_engine.extract_json", return_value={}):
            fake_dir = MagicMock(spec=Path)
            fake_dir.__truediv__ = MagicMock(return_value=MagicMock(spec=Path))
            fake_dir.mkdir = MagicMock()
            mock_gmd.return_value = fake_dir
            mock_rs_cls.return_value.save_scan = MagicMock()

            events = asyncio.run(_collect(engine.run_scan("run1", {"date": "2026-01-01"})))

        log_events = [e for e in events if e.get("type") == "log"]
        self.assertGreaterEqual(len(log_events), 2,
                                "Expected at least one log event before and after streaming")

    def test_run_scan_skips_json_save_on_invalid_json(self):
        """When extract_json raises ValueError, save_scan is NOT called but .md files ARE saved."""
        mock_scanner = self._make_mock_scanner()
        engine = LangGraphEngine()
        written = {}

        def make_fake_path(name):
            p = MagicMock(spec=Path)
            p.write_text = MagicMock(side_effect=lambda text: written.__setitem__(name, text))
            return p

        fake_dir = MagicMock(spec=Path)
        fake_dir.__truediv__ = MagicMock(side_effect=make_fake_path)
        fake_dir.mkdir = MagicMock()

        with patch("agent_os.backend.services.langgraph_engine.ScannerGraph", return_value=mock_scanner), \
             patch("agent_os.backend.services.langgraph_engine.get_market_dir", return_value=fake_dir), \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"), \
             patch("agent_os.backend.services.langgraph_engine.extract_json", side_effect=ValueError("bad json")):
            mock_store = MagicMock()
            mock_rs_cls.return_value = mock_store

            # Should not raise
            events = asyncio.run(_collect(engine.run_scan("run1", {"date": "2026-01-01"})))

        mock_store.save_scan.assert_not_called()
        # .md files should still have been written
        self.assertGreater(len(written), 0, "Expected .md files to be written even when JSON fails")

    def test_run_scan_no_report_if_empty_final_state(self):
        """When astream_events yields no root chain-end event, save_scan and append_to_digest are NOT called."""
        async def mock_astream(*args, **kwargs):
            # no root on_chain_end event
            for _ in ():
                yield {}

        mock_graph = MagicMock()
        mock_graph.astream_events = mock_astream
        mock_scanner = MagicMock()
        mock_scanner.graph = mock_graph

        engine = LangGraphEngine()

        with patch("agent_os.backend.services.langgraph_engine.ScannerGraph", return_value=mock_scanner), \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest") as mock_digest:
            mock_store = MagicMock()
            mock_rs_cls.return_value = mock_store

            asyncio.run(_collect(engine.run_scan("run1", {"date": "2026-01-01"})))

        mock_store.save_scan.assert_not_called()
        mock_digest.assert_not_called()


# ---------------------------------------------------------------------------
# TestRunPipelineReportStorage
# ---------------------------------------------------------------------------

class TestRunPipelineReportStorage(unittest.TestCase):
    """Tests for run_pipeline report saving behaviour."""

    _FINAL_STATE = {
        "final_trade_decision": "BUY AAPL",
        "trader_investment_plan": "invest 10%",
        "market_report": "market is bullish",
    }

    def _make_mock_graph_wrapper(self, final_state=None):
        if final_state is None:
            final_state = self._FINAL_STATE

        async def mock_astream(*args, **kwargs):
            yield _root_chain_end_event(final_state)

        mock_graph = MagicMock()
        mock_graph.astream_events = mock_astream

        mock_propagator = MagicMock()
        mock_propagator.create_initial_state = MagicMock(return_value={"ticker": "AAPL", "date": "2026-01-01"})
        mock_propagator.max_recur_limit = 100

        mock_wrapper = MagicMock()
        mock_wrapper.graph = mock_graph
        mock_wrapper.propagator = mock_propagator
        return mock_wrapper

    def test_run_pipeline_saves_analysis_json(self):
        """run_pipeline should call ReportStore().save_analysis with correct args."""
        mock_wrapper = self._make_mock_graph_wrapper()
        engine = LangGraphEngine()

        with patch("agent_os.backend.services.langgraph_engine.TradingAgentsGraph", return_value=mock_wrapper), \
             patch("agent_os.backend.services.langgraph_engine.get_ticker_dir") as mock_gtd, \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"), \
             patch.object(LangGraphEngine, "_write_complete_report_md"):
            fake_dir = MagicMock(spec=Path)
            fake_dir.mkdir = MagicMock()
            mock_gtd.return_value = fake_dir
            mock_store = MagicMock()
            mock_rs_cls.return_value = mock_store

            asyncio.run(_collect(engine.run_pipeline("run1", {"ticker": "AAPL", "date": "2026-01-01"})))

        mock_store.save_analysis.assert_called_once_with("2026-01-01", "AAPL", self._FINAL_STATE)

    def test_run_pipeline_writes_complete_report_md(self):
        """run_pipeline should call _write_complete_report_md."""
        mock_wrapper = self._make_mock_graph_wrapper()
        engine = LangGraphEngine()

        with patch("agent_os.backend.services.langgraph_engine.TradingAgentsGraph", return_value=mock_wrapper), \
             patch("agent_os.backend.services.langgraph_engine.get_ticker_dir") as mock_gtd, \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"), \
             patch.object(LangGraphEngine, "_write_complete_report_md") as mock_write_md:
            fake_dir = MagicMock(spec=Path)
            fake_dir.mkdir = MagicMock()
            mock_gtd.return_value = fake_dir
            mock_rs_cls.return_value.save_analysis = MagicMock()

            asyncio.run(_collect(engine.run_pipeline("run1", {"ticker": "AAPL", "date": "2026-01-01"})))

        mock_write_md.assert_called_once()

    def test_run_pipeline_appends_digest(self):
        """run_pipeline should call append_to_digest with analyze/ticker."""
        mock_wrapper = self._make_mock_graph_wrapper()
        engine = LangGraphEngine()

        with patch("agent_os.backend.services.langgraph_engine.TradingAgentsGraph", return_value=mock_wrapper), \
             patch("agent_os.backend.services.langgraph_engine.get_ticker_dir") as mock_gtd, \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest") as mock_digest, \
             patch.object(LangGraphEngine, "_write_complete_report_md"):
            fake_dir = MagicMock(spec=Path)
            fake_dir.mkdir = MagicMock()
            mock_gtd.return_value = fake_dir
            mock_rs_cls.return_value.save_analysis = MagicMock()

            asyncio.run(_collect(engine.run_pipeline("run1", {"ticker": "AAPL", "date": "2026-01-01"})))

        mock_digest.assert_called_once()
        call_args = mock_digest.call_args[0]
        self.assertEqual(call_args[0], "2026-01-01")
        self.assertEqual(call_args[1], "analyze")
        self.assertEqual(call_args[2], "AAPL")

    def test_run_pipeline_yields_log_events(self):
        """run_pipeline should yield at least one log event."""
        mock_wrapper = self._make_mock_graph_wrapper()
        engine = LangGraphEngine()

        with patch("agent_os.backend.services.langgraph_engine.TradingAgentsGraph", return_value=mock_wrapper), \
             patch("agent_os.backend.services.langgraph_engine.get_ticker_dir") as mock_gtd, \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"), \
             patch.object(LangGraphEngine, "_write_complete_report_md"):
            fake_dir = MagicMock(spec=Path)
            fake_dir.mkdir = MagicMock()
            mock_gtd.return_value = fake_dir
            mock_rs_cls.return_value.save_analysis = MagicMock()

            events = asyncio.run(_collect(engine.run_pipeline("run1", {"ticker": "AAPL", "date": "2026-01-01"})))

        log_events = [e for e in events if e.get("type") == "log"]
        self.assertGreaterEqual(len(log_events), 1)

    def test_run_pipeline_skips_save_if_empty_final_state(self):
        """When no root chain-end event is emitted, no saves should be called."""
        async def mock_astream(*args, **kwargs):
            for _ in ():
                yield {}

        mock_graph = MagicMock()
        mock_graph.astream_events = mock_astream
        mock_propagator = MagicMock()
        mock_propagator.create_initial_state = MagicMock(return_value={})
        mock_propagator.max_recur_limit = 100
        mock_wrapper = MagicMock()
        mock_wrapper.graph = mock_graph
        mock_wrapper.propagator = mock_propagator

        engine = LangGraphEngine()

        with patch("agent_os.backend.services.langgraph_engine.TradingAgentsGraph", return_value=mock_wrapper), \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest") as mock_digest:
            mock_store = MagicMock()
            mock_rs_cls.return_value = mock_store

            asyncio.run(_collect(engine.run_pipeline("run1", {"ticker": "AAPL", "date": "2026-01-01"})))

        mock_store.save_analysis.assert_not_called()
        mock_digest.assert_not_called()


# ---------------------------------------------------------------------------
# TestRunPortfolioReportLoading
# ---------------------------------------------------------------------------

class TestRunPortfolioReportLoading(unittest.TestCase):
    """Tests for run_portfolio loading scan and ticker analyses from disk."""

    def _make_mock_portfolio_graph(self):
        async def mock_astream(*args, **kwargs):
            yield _root_chain_end_event({"portfolio_decision": "hold"})

        mock_graph = MagicMock()
        mock_graph.astream_events = mock_astream
        mock_pg = MagicMock()
        mock_pg.graph = mock_graph
        return mock_pg

    def test_run_portfolio_loads_scan_from_report_store(self):
        """run_portfolio should call load_scan and pass result as scan_summary."""
        mock_pg = self._make_mock_portfolio_graph()
        engine = LangGraphEngine()
        captured_state = {}

        async def mock_astream(initial_state, *args, **kwargs):
            captured_state.update(initial_state)
            yield _root_chain_end_event({})

        mock_pg.graph.astream_events = mock_astream

        scan_data = {"watchlist": ["AAPL"]}
        fake_daily_dir = MagicMock(spec=Path)
        fake_daily_dir.exists.return_value = True
        fake_daily_dir.iterdir.return_value = []

        with patch("agent_os.backend.services.langgraph_engine.PortfolioGraph", return_value=mock_pg), \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("tradingagents.report_paths.get_daily_dir", return_value=fake_daily_dir):
            mock_store = MagicMock()
            mock_store.load_scan.return_value = scan_data
            mock_store.load_analysis.return_value = None
            mock_rs_cls.return_value = mock_store

            asyncio.run(_collect(engine.run_portfolio("run1", {"date": "2026-01-01", "portfolio_id": "p1"})))

        self.assertEqual(captured_state.get("scan_summary"), scan_data)

    def test_run_portfolio_loads_ticker_analyses_from_daily_dir(self):
        """run_portfolio should load analyses for AAPL and TSLA (excluding market/portfolio dirs)."""
        mock_pg = self._make_mock_portfolio_graph()
        engine = LangGraphEngine()
        captured_state = {}

        async def mock_astream(initial_state, *args, **kwargs):
            captured_state.update(initial_state)
            yield _root_chain_end_event({})

        mock_pg.graph.astream_events = mock_astream

        # Build fake directory entries for AAPL, TSLA, market, portfolio
        def make_dir_mock(name, is_dir=True):
            d = MagicMock(spec=Path)
            d.name = name
            d.is_dir.return_value = is_dir
            return d

        fake_tickers = [
            make_dir_mock("AAPL"),
            make_dir_mock("TSLA"),
            make_dir_mock("market"),
            make_dir_mock("portfolio"),
        ]
        fake_daily_dir = MagicMock(spec=Path)
        fake_daily_dir.exists.return_value = True
        fake_daily_dir.iterdir.return_value = fake_tickers

        aapl_analysis = {"final_trade_decision": "BUY"}
        tsla_analysis = {"final_trade_decision": "SELL"}

        def load_analysis_side_effect(date, ticker):
            return {"AAPL": aapl_analysis, "TSLA": tsla_analysis}.get(ticker)

        with patch("agent_os.backend.services.langgraph_engine.PortfolioGraph", return_value=mock_pg), \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("tradingagents.report_paths.get_daily_dir", return_value=fake_daily_dir):
            mock_store = MagicMock()
            mock_store.load_scan.return_value = {}
            mock_store.load_analysis.side_effect = load_analysis_side_effect
            mock_rs_cls.return_value = mock_store

            asyncio.run(_collect(engine.run_portfolio("run1", {"date": "2026-01-01", "portfolio_id": "p1"})))

        ticker_analyses = captured_state.get("ticker_analyses", {})
        self.assertIn("AAPL", ticker_analyses)
        self.assertIn("TSLA", ticker_analyses)
        self.assertEqual(ticker_analyses["AAPL"], aapl_analysis)
        self.assertEqual(ticker_analyses["TSLA"], tsla_analysis)

    def test_run_portfolio_skips_market_and_portfolio_dirs(self):
        """load_analysis should NOT be called for dirs named 'market' or 'portfolio'."""
        mock_pg = self._make_mock_portfolio_graph()
        engine = LangGraphEngine()

        def make_dir_mock(name):
            d = MagicMock(spec=Path)
            d.name = name
            d.is_dir.return_value = True
            return d

        fake_tickers = [make_dir_mock("market"), make_dir_mock("portfolio")]
        fake_daily_dir = MagicMock(spec=Path)
        fake_daily_dir.exists.return_value = True
        fake_daily_dir.iterdir.return_value = fake_tickers

        with patch("agent_os.backend.services.langgraph_engine.PortfolioGraph", return_value=mock_pg), \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("tradingagents.report_paths.get_daily_dir", return_value=fake_daily_dir):
            mock_store = MagicMock()
            mock_store.load_scan.return_value = {}
            mock_rs_cls.return_value = mock_store

            asyncio.run(_collect(engine.run_portfolio("run1", {"date": "2026-01-01", "portfolio_id": "p1"})))

        mock_store.load_analysis.assert_not_called()

    def test_run_portfolio_yields_loaded_tickers_log(self):
        """run_portfolio should yield a log event listing the loaded tickers."""
        mock_pg = self._make_mock_portfolio_graph()
        engine = LangGraphEngine()

        def make_dir_mock(name):
            d = MagicMock(spec=Path)
            d.name = name
            d.is_dir.return_value = True
            return d

        fake_daily_dir = MagicMock(spec=Path)
        fake_daily_dir.exists.return_value = True
        fake_daily_dir.iterdir.return_value = [make_dir_mock("AAPL")]

        with patch("agent_os.backend.services.langgraph_engine.PortfolioGraph", return_value=mock_pg), \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("tradingagents.report_paths.get_daily_dir", return_value=fake_daily_dir):
            mock_store = MagicMock()
            mock_store.load_scan.return_value = {}
            mock_store.load_analysis.return_value = {"final_trade_decision": "BUY"}
            mock_rs_cls.return_value = mock_store

            events = asyncio.run(_collect(engine.run_portfolio("run1", {"date": "2026-01-01", "portfolio_id": "p1"})))

        log_messages = [e.get("message", "") for e in events if e.get("type") == "log"]
        # At least one log message should mention "AAPL"
        self.assertTrue(
            any("AAPL" in msg for msg in log_messages),
            f"Expected a log event mentioning AAPL. Got: {log_messages}",
        )

    def test_run_portfolio_handles_missing_daily_dir(self):
        """When daily_dir does not exist, ticker_analyses should be empty and no exception raised."""
        mock_pg = self._make_mock_portfolio_graph()
        engine = LangGraphEngine()
        captured_state = {}

        async def mock_astream(initial_state, *args, **kwargs):
            captured_state.update(initial_state)
            yield _root_chain_end_event({})

        mock_pg.graph.astream_events = mock_astream

        fake_daily_dir = MagicMock(spec=Path)
        fake_daily_dir.exists.return_value = False

        with patch("agent_os.backend.services.langgraph_engine.PortfolioGraph", return_value=mock_pg), \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("tradingagents.report_paths.get_daily_dir", return_value=fake_daily_dir):
            mock_store = MagicMock()
            mock_store.load_scan.return_value = {}
            mock_rs_cls.return_value = mock_store

            # Should not raise
            events = asyncio.run(_collect(engine.run_portfolio("run1", {"date": "2026-01-01", "portfolio_id": "p1"})))

        self.assertEqual(captured_state.get("ticker_analyses"), {})
        mock_store.load_analysis.assert_not_called()


# ---------------------------------------------------------------------------
# TestRunAutoTickerSource
# ---------------------------------------------------------------------------

class TestRunAutoTickerSource(unittest.TestCase):
    """Tests for run_auto ticker sourcing and phase coordination."""

    def _make_noop_scanner(self):
        """Scanner that yields nothing significant."""
        async def mock_astream(*args, **kwargs):
            yield _root_chain_end_event({"macro_scan_summary": "{}"})

        mock_graph = MagicMock()
        mock_graph.astream_events = mock_astream
        mock_scanner = MagicMock()
        mock_scanner.graph = mock_graph
        return mock_scanner

    def _make_noop_graph_wrapper(self):
        async def mock_astream(*args, **kwargs):
            yield _root_chain_end_event({"final_trade_decision": "BUY"})

        mock_graph = MagicMock()
        mock_graph.astream_events = mock_astream
        mock_propagator = MagicMock()
        mock_propagator.create_initial_state = MagicMock(return_value={})
        mock_propagator.max_recur_limit = 100
        mock_wrapper = MagicMock()
        mock_wrapper.graph = mock_graph
        mock_wrapper.propagator = mock_propagator
        return mock_wrapper

    def _make_noop_portfolio_graph(self):
        async def mock_astream(*args, **kwargs):
            yield _root_chain_end_event({})

        mock_graph = MagicMock()
        mock_graph.astream_events = mock_astream
        mock_pg = MagicMock()
        mock_pg.graph = mock_graph
        return mock_pg

    def test_run_auto_gets_tickers_from_scan_report(self):
        """run_auto should run pipeline for AAPL and TSLA from the scan report."""
        scan_data = {"stocks_to_investigate": ["AAPL", "TSLA"]}
        pipeline_calls = []

        engine = LangGraphEngine()
        original_run_pipeline = engine.run_pipeline

        async def fake_run_pipeline(run_id, params):
            pipeline_calls.append(params.get("ticker"))
            for _ in ():
                yield {}

        engine.run_pipeline = fake_run_pipeline

        with patch("agent_os.backend.services.langgraph_engine.ScannerGraph",
                   return_value=self._make_noop_scanner()), \
             patch("agent_os.backend.services.langgraph_engine.PortfolioGraph",
                   return_value=self._make_noop_portfolio_graph()), \
             patch("agent_os.backend.services.langgraph_engine.get_market_dir") as mock_gmd, \
             patch("agent_os.backend.services.langgraph_engine.get_ticker_dir"), \
             patch("tradingagents.report_paths.get_daily_dir") as mock_gdd, \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"), \
             patch("agent_os.backend.services.langgraph_engine.extract_json", return_value=scan_data):
            # Set up fake dirs
            fake_mdir = MagicMock(spec=Path)
            fake_mdir.__truediv__ = MagicMock(return_value=MagicMock(spec=Path))
            fake_mdir.mkdir = MagicMock()
            mock_gmd.return_value = fake_mdir
            fake_daily = MagicMock(spec=Path)
            fake_daily.exists.return_value = False
            mock_gdd.return_value = fake_daily

            mock_store = MagicMock()
            mock_store.load_scan.return_value = scan_data
            mock_rs_cls.return_value = mock_store

            asyncio.run(_collect(engine.run_auto("auto1", {"date": "2026-01-01"})))

        self.assertIn("AAPL", pipeline_calls)
        self.assertIn("TSLA", pipeline_calls)

    def test_run_auto_does_not_use_ticker_from_params(self):
        """Even if params contains ticker='GOOG', auto run should use tickers from scan report."""
        scan_data = {"stocks_to_investigate": ["AAPL"]}
        pipeline_calls = []

        engine = LangGraphEngine()

        async def fake_run_pipeline(run_id, params):
            pipeline_calls.append(params.get("ticker"))
            for _ in ():
                yield {}

        engine.run_pipeline = fake_run_pipeline

        with patch("agent_os.backend.services.langgraph_engine.ScannerGraph",
                   return_value=self._make_noop_scanner()), \
             patch("agent_os.backend.services.langgraph_engine.PortfolioGraph",
                   return_value=self._make_noop_portfolio_graph()), \
             patch("agent_os.backend.services.langgraph_engine.get_market_dir") as mock_gmd, \
             patch("tradingagents.report_paths.get_daily_dir") as mock_gdd, \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"), \
             patch("agent_os.backend.services.langgraph_engine.extract_json", return_value=scan_data):
            fake_mdir = MagicMock(spec=Path)
            fake_mdir.__truediv__ = MagicMock(return_value=MagicMock(spec=Path))
            fake_mdir.mkdir = MagicMock()
            mock_gmd.return_value = fake_mdir
            fake_daily = MagicMock(spec=Path)
            fake_daily.exists.return_value = False
            mock_gdd.return_value = fake_daily

            mock_store = MagicMock()
            mock_store.load_scan.return_value = scan_data
            mock_rs_cls.return_value = mock_store

            asyncio.run(_collect(engine.run_auto("auto1", {"date": "2026-01-01", "ticker": "GOOG"})))

        self.assertNotIn("GOOG", pipeline_calls,
                         "run_pipeline should NOT be called with the ticker from params")

    def test_run_auto_skips_pipeline_if_no_tickers(self):
        """When scan report has no tickers, run_pipeline is NOT called but run_portfolio IS called."""
        pipeline_calls = []
        portfolio_called = []

        engine = LangGraphEngine()

        async def fake_run_pipeline(run_id, params):
            pipeline_calls.append(params.get("ticker"))
            for _ in ():
                yield {}

        async def fake_run_portfolio(run_id, params):
            portfolio_called.append(True)
            for _ in ():
                yield {}

        engine.run_pipeline = fake_run_pipeline
        engine.run_portfolio = fake_run_portfolio

        with patch("agent_os.backend.services.langgraph_engine.ScannerGraph",
                   return_value=self._make_noop_scanner()), \
             patch("agent_os.backend.services.langgraph_engine.get_market_dir") as mock_gmd, \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"), \
             patch("agent_os.backend.services.langgraph_engine.extract_json", return_value={}):
            fake_mdir = MagicMock(spec=Path)
            fake_mdir.__truediv__ = MagicMock(return_value=MagicMock(spec=Path))
            fake_mdir.mkdir = MagicMock()
            mock_gmd.return_value = fake_mdir

            mock_store = MagicMock()
            mock_store.load_scan.return_value = {}
            mock_rs_cls.return_value = mock_store

            asyncio.run(_collect(engine.run_auto("auto1", {"date": "2026-01-01"})))

        self.assertEqual(pipeline_calls, [], "run_pipeline should not be called when no tickers")
        self.assertTrue(portfolio_called, "run_portfolio should still be called")

    def test_run_auto_passes_portfolio_params_without_ticker(self):
        """run_portfolio should receive params including portfolio_id but NOT ticker."""
        portfolio_params_received = []

        engine = LangGraphEngine()

        async def fake_run_pipeline(run_id, params):
            for _ in ():
                yield {}

        async def fake_run_portfolio(run_id, params):
            portfolio_params_received.append(params)
            for _ in ():
                yield {}

        engine.run_pipeline = fake_run_pipeline
        engine.run_portfolio = fake_run_portfolio

        with patch("agent_os.backend.services.langgraph_engine.ScannerGraph",
                   return_value=self._make_noop_scanner()), \
             patch("agent_os.backend.services.langgraph_engine.get_market_dir") as mock_gmd, \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"), \
             patch("agent_os.backend.services.langgraph_engine.extract_json", return_value={}):
            fake_mdir = MagicMock(spec=Path)
            fake_mdir.__truediv__ = MagicMock(return_value=MagicMock(spec=Path))
            fake_mdir.mkdir = MagicMock()
            mock_gmd.return_value = fake_mdir

            mock_store = MagicMock()
            mock_store.load_scan.return_value = {}
            mock_rs_cls.return_value = mock_store

            params = {"ticker": "GOOG", "portfolio_id": "my_portfolio", "date": "2026-01-01"}
            asyncio.run(_collect(engine.run_auto("auto1", params)))

        self.assertEqual(len(portfolio_params_received), 1)
        received = portfolio_params_received[0]
        self.assertIn("portfolio_id", received)
        self.assertNotIn("ticker", received)

    def test_run_auto_yields_phase_log_events(self):
        """run_auto should yield log events mentioning Phase 1/3, Phase 2/3, Phase 3/3."""
        engine = LangGraphEngine()

        async def fake_run_pipeline(run_id, params):
            for _ in ():
                yield {}

        async def fake_run_portfolio(run_id, params):
            for _ in ():
                yield {}

        engine.run_pipeline = fake_run_pipeline
        engine.run_portfolio = fake_run_portfolio

        with patch("agent_os.backend.services.langgraph_engine.ScannerGraph",
                   return_value=self._make_noop_scanner()), \
             patch("agent_os.backend.services.langgraph_engine.get_market_dir") as mock_gmd, \
             patch("agent_os.backend.services.langgraph_engine.ReportStore") as mock_rs_cls, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"), \
             patch("agent_os.backend.services.langgraph_engine.extract_json", return_value={}):
            fake_mdir = MagicMock(spec=Path)
            fake_mdir.__truediv__ = MagicMock(return_value=MagicMock(spec=Path))
            fake_mdir.mkdir = MagicMock()
            mock_gmd.return_value = fake_mdir

            mock_store = MagicMock()
            mock_store.load_scan.return_value = {}
            mock_rs_cls.return_value = mock_store

            events = asyncio.run(_collect(engine.run_auto("auto1", {"date": "2026-01-01"})))

        log_messages = [e.get("message", "") for e in events if e.get("type") == "log"]
        self.assertTrue(any("Phase 1/3" in m or "1/3" in m for m in log_messages),
                        f"Expected Phase 1/3 log. Got: {log_messages}")
        self.assertTrue(any("Phase 2/3" in m or "2/3" in m for m in log_messages),
                        f"Expected Phase 2/3 log. Got: {log_messages}")
        self.assertTrue(any("Phase 3/3" in m or "3/3" in m for m in log_messages),
                        f"Expected Phase 3/3 log. Got: {log_messages}")


# ---------------------------------------------------------------------------
# TestExtractTickersFromScanData
# ---------------------------------------------------------------------------

class TestExtractTickersFromScanData(unittest.TestCase):
    """Pure unit tests for _extract_tickers_from_scan_data (no async needed)."""

    def setUp(self):
        self.engine = LangGraphEngine()

    def test_list_of_strings(self):
        scan = {"stocks_to_investigate": ["AAPL", "tsla"]}
        self.assertEqual(self.engine._extract_tickers_from_scan_data(scan), ["AAPL", "TSLA"])

    def test_list_of_dicts_with_ticker_key(self):
        scan = {"stocks_to_investigate": [{"ticker": "AAPL"}, {"ticker": "MSFT"}]}
        self.assertEqual(self.engine._extract_tickers_from_scan_data(scan), ["AAPL", "MSFT"])

    def test_list_of_dicts_with_symbol_key(self):
        scan = {"stocks_to_investigate": [{"symbol": "nvda"}]}
        self.assertEqual(self.engine._extract_tickers_from_scan_data(scan), ["NVDA"])

    def test_watchlist_fallback(self):
        scan = {"watchlist": ["GOOG"]}
        self.assertEqual(self.engine._extract_tickers_from_scan_data(scan), ["GOOG"])

    def test_deduplication(self):
        scan = {"stocks_to_investigate": ["AAPL", "aapl", "AAPL"]}
        result = self.engine._extract_tickers_from_scan_data(scan)
        self.assertEqual(result, ["AAPL"])

    def test_empty_or_none(self):
        self.assertEqual(self.engine._extract_tickers_from_scan_data(None), [])
        self.assertEqual(self.engine._extract_tickers_from_scan_data({}), [])
        self.assertEqual(self.engine._extract_tickers_from_scan_data({"stocks_to_investigate": []}), [])

    def test_mixed_types_skipped(self):
        """Items that are not str or dict should be silently skipped."""
        scan = {"stocks_to_investigate": ["AAPL", 42, None, ["nested"], {"ticker": "MSFT"}]}
        result = self.engine._extract_tickers_from_scan_data(scan)
        self.assertIn("AAPL", result)
        self.assertIn("MSFT", result)
        # Non-string/non-dict items should not produce entries
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
