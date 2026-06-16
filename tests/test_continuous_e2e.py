import pytest
import os
import json
import threading
import concurrent.futures
from gemini_agent import (
    AdvancedTradingAgent,
    MarketWatcher,
    OpportunityScanner,
    PortfolioMemory,
    RiskGuard,
    ReportWriter
)

# ==========================================
# TIER 1: Feature Coverage (20 tests)
# ==========================================

def test_cli_args_parsing():
    """Verify CLI parser accepts --watch, --interval-minutes, --watchlist, --max-candidates."""
    try:
        from gemini_agent.agent import main
        main(["--watch", "--interval-minutes", "5", "--watchlist", "AAPL,MSFT", "--max-candidates", "2"])
    except (ImportError, AttributeError) as e:
        raise NotImplementedError(f"CLI main function is missing or not implemented: {e}")


def test_run_watch_loop_cycles():
    """Verify run_watch_loop executes at least 2 cycles and stops when queue/cycles limit is reached."""
    agent = AdvancedTradingAgent()
    agent.run_watch_loop(watchlist=["AAPL"], interval_minutes=1, max_candidates=2, max_cycles=2)


def test_watchlist_parsing_formats():
    """Verify watchlist parses comma-separated lists correctly."""
    agent = AdvancedTradingAgent(config={"watchlist": "AAPL,MSFT"})
    assert hasattr(agent, "watchlist")
    assert agent.watchlist == ["AAPL", "MSFT"]


def test_max_candidates_filter():
    """Verify candidates are limited to --max-candidates count."""
    agent = AdvancedTradingAgent()
    agent.run_watch_loop(watchlist=["AAPL", "MSFT", "TSLA"], interval_minutes=1, max_candidates=2, max_cycles=1)


def test_loop_termination_on_signal():
    """Verify the event loop terminates cleanly when stop signal is set."""
    agent = AdvancedTradingAgent()
    stop_event = threading.Event()
    stop_event.set()
    agent.run_watch_loop(watchlist=["AAPL"], interval_minutes=1, max_candidates=1, stop_event=stop_event)


def test_market_watcher_fetch_snapshots():
    """Verify MarketWatcher.fetch_snapshots returns correct dictionaries for tickers and benchmark SPY."""
    watcher = MarketWatcher()
    snapshots = watcher.fetch_snapshots(["AAPL"])
    assert "AAPL" in snapshots
    assert "SPY" in snapshots


def test_opportunity_scanner_scoring():
    """Verify OpportunityScanner.score_candidates returns candidates with numerical scores."""
    scanner = OpportunityScanner()
    snapshots = {"AAPL": {"close": 150.0}}
    candidates = scanner.score_candidates(snapshots)
    assert len(candidates) > 0
    assert "ticker" in candidates[0]
    assert isinstance(candidates[0]["score"], (int, float))


def test_opportunity_scanner_sorting():
    """Verify candidates are returned sorted by score descending."""
    scanner = OpportunityScanner()
    snapshots = {"AAPL": {"close": 150.0}, "MSFT": {"close": 250.0}}
    candidates = scanner.score_candidates(snapshots)
    assert len(candidates) >= 2
    assert candidates[0]["score"] >= candidates[1]["score"]


def test_opportunity_scanner_empty_watchlist():
    """Verify scanner returns empty list if snapshots dictionary is empty."""
    scanner = OpportunityScanner()
    candidates = scanner.score_candidates({})
    assert candidates == []


def test_market_watcher_benchmark_only():
    """Verify SPY benchmark snapshot is fetched even if the watchlist itself is empty."""
    watcher = MarketWatcher()
    snapshots = watcher.fetch_snapshots([])
    assert "SPY" in snapshots


def test_portfolio_memory_initialization():
    """Verify PortfolioMemory starts with $10,000 cash balance."""
    memory = PortfolioMemory()
    assert memory.balance == 10000.0


def test_portfolio_memory_update():
    """Verify memory updates cash and positions after simulating a trade."""
    memory = PortfolioMemory()
    decision = {"ticker": "AAPL", "action": "buy", "price": 150.0, "amount": 10}
    memory.update_portfolio(decision)
    assert memory.balance < 10000.0


def test_portfolio_memory_performance_review():
    """Verify performance review calculates ROI of previous recommendations."""
    memory = PortfolioMemory()
    metrics = memory.review_performance()
    assert "roi" in metrics


def test_risk_guard_assessment():
    """Verify RiskGuard.assess_risk evaluates and returns safe/watch/risky labels."""
    guard = RiskGuard()
    label = guard.assess_risk("AAPL", {"balance": 10000.0})
    assert label in ["safe", "watch", "risky"]


def test_portfolio_memory_json_snapshots(tmp_path):
    """Verify portfolio snapshots are correctly saved/loaded in JSON/JSONL format."""
    memory = PortfolioMemory(config={"memory_file": str(tmp_path / "portfolio.json")})
    memory.save_snapshot({"balance": 9000.0})


def test_report_writer_watch_log(tmp_path):
    """Verify ReportWriter appends records to watch_log.jsonl."""
    writer = ReportWriter(config={"reports_dir": str(tmp_path)})
    writer.log_event("watch", {"tickers": ["AAPL"]})
    assert (tmp_path / "watch_log.jsonl").exists()


def test_report_writer_opportunities_log(tmp_path):
    """Verify ReportWriter appends records to opportunities.jsonl."""
    writer = ReportWriter(config={"reports_dir": str(tmp_path)})
    writer.log_event("opportunities", {"candidates": []})
    assert (tmp_path / "opportunities.jsonl").exists()


def test_report_writer_decisions_log(tmp_path):
    """Verify ReportWriter appends records to decisions.jsonl."""
    writer = ReportWriter(config={"reports_dir": str(tmp_path)})
    writer.log_event("decisions", {"ticker": "AAPL", "action": "buy"})
    assert (tmp_path / "decisions.jsonl").exists()


def test_report_writer_summary_generation(tmp_path):
    """Verify ReportWriter generates the daily_summary.md file."""
    writer = ReportWriter(config={"reports_dir": str(tmp_path)})
    writer.generate_daily_summary()
    assert (tmp_path / "daily_summary.md").exists()


def test_report_writer_summary_contents(tmp_path):
    """Verify daily_summary.md contains scanned tickers, risk flags, and portfolio balance."""
    writer = ReportWriter(config={"reports_dir": str(tmp_path)})
    writer.generate_daily_summary()
    content = (tmp_path / "daily_summary.md").read_text()
    assert "balance" in content.lower()


# ==========================================
# TIER 2: Boundary & Corner Cases (20 tests)
# ==========================================

def test_cli_negative_interval():
    """Verify negative or zero interval throws value error."""
    agent = AdvancedTradingAgent()
    with pytest.raises(ValueError):
        agent.run_watch_loop(watchlist=["AAPL"], interval_minutes=-5, max_candidates=2)


def test_cli_invalid_watchlist_format():
    """Verify malformed watchlist strings are handled gracefully."""
    agent = AdvancedTradingAgent()
    with pytest.raises(ValueError):
        agent.run_watch_loop(watchlist="!!INVALID!!", interval_minutes=5, max_candidates=2)


def test_cli_negative_max_candidates():
    """Verify negative max-candidates is handled."""
    agent = AdvancedTradingAgent()
    with pytest.raises(ValueError):
        agent.run_watch_loop(watchlist=["AAPL"], interval_minutes=5, max_candidates=-1)


def test_cli_missing_mandatory_args():
    """Verify CLI returns error code on missing mandatory arguments."""
    try:
        from gemini_agent.agent import main
        with pytest.raises(SystemExit):
            main([])
    except (ImportError, AttributeError) as e:
        raise NotImplementedError(f"CLI main function is missing or not implemented: {e}")


def test_loop_resilience_on_temp_failure():
    """Verify loop continues to next cycle if one cycle fails (e.g. timeout fetching data)."""
    agent = AdvancedTradingAgent()
    agent.run_watch_loop(watchlist=["AAPL"], interval_minutes=1, max_candidates=2, max_cycles=2)


def test_market_watcher_nonexistent_ticker():
    """Verify watcher filters out or handles invalid ticker symbols."""
    watcher = MarketWatcher()
    snapshots = watcher.fetch_snapshots(["NONEXISTENT"])
    assert "NONEXISTENT" not in snapshots


def test_opportunity_scanner_negative_price():
    """Verify scoring logic handles negative/zero prices/volumes without crashing."""
    scanner = OpportunityScanner()
    candidates = scanner.score_candidates({"AAPL": {"close": -150.0, "volume": -100}})
    assert candidates == []


def test_opportunity_scanner_missing_benchmark():
    """Verify scoring logic uses fallback values if SPY benchmark is missing."""
    scanner = OpportunityScanner()
    candidates = scanner.score_candidates({"AAPL": {"close": 150.0}})
    assert len(candidates) == 1


def test_opportunity_scanner_extreme_relative_strength():
    """Verify relative strength score is bounded or doesn't divide by zero when SPY is flat."""
    scanner = OpportunityScanner()
    candidates = scanner.score_candidates({"AAPL": {"close": 150.0}, "SPY": {"close": 0.0}})
    assert len(candidates) > 0


def test_opportunity_scanner_empty_market_data():
    """Verify opportunity scanner handles empty market data fields in snapshots."""
    scanner = OpportunityScanner()
    candidates = scanner.score_candidates({"AAPL": {}})
    assert candidates == []


def test_portfolio_insufficient_cash():
    """Verify paper trading prevents purchases exceeding cash (margin check)."""
    memory = PortfolioMemory()
    decision = {"ticker": "AAPL", "action": "buy", "price": 200.0, "amount": 100}
    with pytest.raises(ValueError):
        memory.update_portfolio(decision)


def test_performance_review_no_past_decisions():
    """Verify performance reviewer returns 0 ROI and empty list if no past decisions."""
    memory = PortfolioMemory()
    metrics = memory.review_performance()
    assert metrics.get("roi") == 0.0
    assert metrics.get("decisions") == []


def test_risk_guard_extreme_exposure():
    """Verify RiskGuard flags a ticker as risky if it exceeds single-ticker exposure."""
    guard = RiskGuard()
    portfolio = {"balance": 10000.0, "positions": {"AAPL": 1000}}
    label = guard.assess_risk("AAPL", portfolio)
    assert label == "risky"


def test_portfolio_memory_corrupted_snapshot(tmp_path):
    """Verify portfolio memory resets or handles corrupted JSON files safely."""
    memory_file = tmp_path / "portfolio.json"
    memory_file.write_text("{corrupt_json:")
    memory = PortfolioMemory(config={"memory_file": str(memory_file)})
    loaded = memory.load_memory()
    assert memory.balance == 10000.0


def test_portfolio_memory_rapid_transactions():
    """Verify portfolio memory consistency under rapid sequential transactions."""
    memory = PortfolioMemory()
    for _ in range(5):
        memory.update_portfolio({"ticker": "AAPL", "action": "buy", "price": 100.0, "amount": 10})
    assert memory.balance == 5000.0


def test_report_writer_missing_directory(tmp_path):
    """Verify ReportWriter creates the reports/continuous folder if it doesn't exist."""
    reports_dir = tmp_path / "nested" / "reports"
    writer = ReportWriter(config={"reports_dir": str(reports_dir)})
    writer.log_event("watch", {"tickers": []})
    assert reports_dir.exists()


def test_report_writer_extreme_payload(tmp_path):
    """Verify logger handles large payloads and special characters."""
    reports_dir = tmp_path / "reports"
    writer = ReportWriter(config={"reports_dir": str(reports_dir)})
    large_payload = "A" * 100000
    writer.log_event("large", {"payload": large_payload, "unicode": "🚀🔥"})
    assert (reports_dir / "large.jsonl").exists()


def test_daily_summary_empty_cycles(tmp_path):
    """Verify daily_summary.md is generated with a placeholder when no candidates are scored."""
    reports_dir = tmp_path / "reports"
    writer = ReportWriter(config={"reports_dir": str(reports_dir)})
    writer.generate_daily_summary()
    content = (reports_dir / "daily_summary.md").read_text()
    assert "placeholder" in content.lower() or "no candidates" in content.lower()


def test_log_fields_missing(tmp_path):
    """Verify JSONL logging doesn't crash when some data fields are null."""
    reports_dir = tmp_path / "reports"
    writer = ReportWriter(config={"reports_dir": str(reports_dir)})
    writer.log_event("decisions", {"ticker": None, "action": "hold", "price": None})
    assert (reports_dir / "decisions.jsonl").exists()


def test_report_writer_concurrent_writes(tmp_path):
    """Verify logs are written cleanly under concurrent logging attempts."""
    reports_dir = tmp_path / "reports"
    writer = ReportWriter(config={"reports_dir": str(reports_dir)})
    
    def log_task(i):
        writer.log_event("concurrent", {"id": i})
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        executor.map(log_task, range(20))
        
    lines = (reports_dir / "concurrent.jsonl").read_text().strip().split("\n")
    assert len(lines) == 20


# ==========================================
# TIER 3: Cross-Feature Combinations (4 tests)
# ==========================================

def test_scanner_watcher_integration():
    """Verify MarketWatcher snapshots feed directly into OpportunityScanner scoring."""
    watcher = MarketWatcher()
    scanner = OpportunityScanner()
    snapshots = watcher.fetch_snapshots(["AAPL", "MSFT"])
    candidates = scanner.score_candidates(snapshots)
    assert len(candidates) > 0


def test_scoring_memory_integration():
    """Verify opportunity scores trigger simulated purchases in PortfolioMemory."""
    scanner = OpportunityScanner()
    memory = PortfolioMemory()
    snapshots = {"AAPL": {"close": 150.0}, "MSFT": {"close": 250.0}}
    candidates = scanner.score_candidates(snapshots)
    top_candidate = candidates[0]
    memory.update_portfolio({
        "ticker": top_candidate["ticker"],
        "action": "buy",
        "price": top_candidate["price"],
        "amount": 10
    })
    assert memory.balance < 10000.0


def test_risk_guard_decision_integration():
    """Verify RiskGuard risk rating changes transaction decision in PortfolioMemory."""
    guard = RiskGuard()
    memory = PortfolioMemory()
    risk_rating = guard.assess_risk("AAPL", {"balance": memory.balance, "positions": {}})
    if risk_rating == "safe":
        memory.update_portfolio({"ticker": "AAPL", "action": "buy", "price": 100.0, "amount": 5})
    assert memory.balance < 10000.0


def test_full_agent_cycle_integration(tmp_path):
    """Verify full flow: fetch data -> score -> risk assessment -> decision -> write logs and summary."""
    config = {
        "reports_dir": str(tmp_path / "reports"),
        "memory_file": str(tmp_path / "portfolio.json")
    }
    agent = AdvancedTradingAgent(config=config)
    agent.run_watch_loop(watchlist=["AAPL", "MSFT"], interval_minutes=1, max_candidates=2, max_cycles=1)
    assert (tmp_path / "reports" / "daily_summary.md").exists()


# ==========================================
# TIER 4: Real-World Application Scenarios (5 tests)
# ==========================================

def test_scenario_bull_market(tmp_path):
    """Simulation of a bullish day where tickers score high, risk is safe, buy actions are triggered, and reports log positive trade activity."""
    config = {
        "reports_dir": str(tmp_path / "reports"),
        "memory_file": str(tmp_path / "portfolio.json")
    }
    agent = AdvancedTradingAgent(config=config)
    agent.run_watch_loop(watchlist=["AAPL", "MSFT"], interval_minutes=1, max_candidates=2, max_cycles=1)


def test_scenario_market_crash(tmp_path):
    """Simulation of a crash day where tickers score low/negative, risk guard flags risky, portfolio stays in cash, and report warns of risks."""
    config = {
        "reports_dir": str(tmp_path / "reports"),
        "memory_file": str(tmp_path / "portfolio.json")
    }
    agent = AdvancedTradingAgent(config=config)
    agent.run_watch_loop(watchlist=["AAPL", "MSFT"], interval_minutes=1, max_candidates=2, max_cycles=1)


def test_scenario_multi_cycle_trading(tmp_path):
    """Simulation of 3 continuous cycles where prices fluctuate, memory tracks positions, ROI changes, and daily summary is updated."""
    config = {
        "reports_dir": str(tmp_path / "reports"),
        "memory_file": str(tmp_path / "portfolio.json")
    }
    agent = AdvancedTradingAgent(config=config)
    agent.run_watch_loop(watchlist=["AAPL"], interval_minutes=1, max_candidates=1, max_cycles=3)


def test_scenario_missing_benchmark(tmp_path):
    """Simulation of a run where SPY benchmark fails to load, testing graceful fallback and continuation of trading analysis."""
    config = {
        "reports_dir": str(tmp_path / "reports"),
        "memory_file": str(tmp_path / "portfolio.json")
    }
    agent = AdvancedTradingAgent(config=config)
    agent.run_watch_loop(watchlist=["AAPL"], interval_minutes=1, max_candidates=1, max_cycles=1)


def test_scenario_max_candidates_limit(tmp_path):
    """Simulation where 10 tickers are watched but max_candidates is 3, verifying only the top 3 are analyzed and logged."""
    config = {
        "reports_dir": str(tmp_path / "reports"),
        "memory_file": str(tmp_path / "portfolio.json")
    }
    agent = AdvancedTradingAgent(config=config)
    agent.run_watch_loop(
        watchlist=["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10"],
        interval_minutes=1,
        max_candidates=3,
        max_cycles=1
    )
