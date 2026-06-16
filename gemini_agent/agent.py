import json
import os
import sys
import time
import argparse
from datetime import datetime

from langchain_core.messages import HumanMessage
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.llm_clients import create_llm_client

from .watcher import MarketWatcher, OpportunityScanner
from .memory import PortfolioMemory, RiskGuard
from .reporter import ReportWriter

class AdvancedTradingAgent:
    def __init__(self, config=None):
        self.config = DEFAULT_CONFIG.copy()
        if config:
            self.config.update(config)
            
        self.market_watcher = MarketWatcher(curr_date=self.config.get("date") or self.config.get("curr_date"))
        self.opportunity_scanner = OpportunityScanner(config=self.config)
        self.portfolio_memory = PortfolioMemory(config=self.config)
        self.report_writer = ReportWriter(config=self.config)
        self.risk_guard = RiskGuard(config=self.config)
        
        deep_client = create_llm_client(
            provider=self.config.get("llm_provider", "mock"),
            model=self.config.get("deep_think_llm", "mock-think"),
            base_url=self.config.get("backend_url"),
        )
        self.llm = deep_client.get_llm()
        self.ta_graph = TradingAgentsGraph(debug=False, config=self.config)

    def select_top_stocks(self, portfolio: dict) -> list[str]:
        prompt = (
            f"Given the following portfolio: {json.dumps(portfolio)}\n\n"
            "Select exactly 1 stock ticker (e.g. AAPL) that you are most interested in analyzing based on this portfolio.\n"
            "Return ONLY a valid JSON list of 1 string (e.g. [\"AAPL\"]). Do not include any other text."
        )
        response = self.llm.invoke([HumanMessage(content=prompt)])
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
            
        try:
            stocks = json.loads(content)
            if isinstance(stocks, list) and len(stocks) == 1:
                return stocks
        except Exception as e:
            print(f"Error parsing JSON: {e}, Content: {content}")
        
        return ["AAPL"]

    def run(self, portfolio: dict, trade_date: str = None):
        if trade_date is None:
            trade_date = datetime.now().strftime("%Y-%m-%d")
            
        print(f"================================================")
        print(f"Step 1: Selecting 1 stock based on portfolio...")
        print(f"================================================")
        selected_stocks = self.select_top_stocks(portfolio)
        print(f"Selected stocks: {selected_stocks}")
        
        decisions = {}
        for stock in selected_stocks:
            print(f"\n================================================")
            print(f"Step 2: Analyzing {stock} via TradingAgentsGraph...")
            print(f"================================================")
            try:
                final_state, decision = self.ta_graph.propagate(stock, trade_date)
                decisions[stock] = final_state.get("final_trade_decision", str(decision))
                print(f"Successfully analyzed {stock}.")
            except Exception as e:
                print(f"Error analyzing {stock}: {e}")
                decisions[stock] = f"Error: {e}"
                
        print(f"\n================================================")
        print("Step 3: Making final decision based on analyses...")
        print(f"================================================")
        
        history_file = os.path.join(self.config["results_dir"], "advanced_agent_history.json")
        past_history = []
        if os.path.exists(history_file):
            try:
                with open(history_file, "r") as f:
                    past_history = json.load(f)
            except Exception as e:
                print(f"Could not load history: {e}")
                
        final_prompt = (
            f"Here is the user's portfolio: {json.dumps(portfolio)}\n\n"
        )
        if past_history:
            final_prompt += f"Here are your past decisions for context:\n{json.dumps(past_history[-3:], indent=2)}\n\n"
            
        final_prompt += (
            f"Here are the detailed analyses and decisions for the selected stock:\n"
            f"{json.dumps(decisions, indent=2)}\n\n"
            "Based on the portfolio, past decisions (if any), and these detailed analyses, make a final, comprehensive decision on what to do with the money. "
            "Detail your allocation strategy, which stocks to buy/sell/hold, and explain your reasoning clearly."
        )
        
        final_decision_response = self.llm.invoke([HumanMessage(content=final_prompt)])
        final_decision = final_decision_response.content
        
        new_entry = {
            "date": trade_date,
            "portfolio": portfolio,
            "selected_stocks": selected_stocks,
            "final_decision": final_decision
        }
        past_history.append(new_entry)
        os.makedirs(self.config["results_dir"], exist_ok=True)
        try:
            with open(history_file, "w") as f:
                json.dump(past_history, f, indent=2)
        except Exception as e:
            print(f"Could not save history: {e}")
        
        print("\n================ FINAL DECISION ================\n")
        print(final_decision)
        print("\n================================================\n")
        
        return final_decision

    def run_watch_loop(self, watchlist=None, interval_minutes=None, max_candidates=None, stop_event=None, max_cycles=None, once=False):
        watchlist = watchlist if watchlist is not None else self.config.get("watchlist", [])
        interval_minutes = interval_minutes if interval_minutes is not None else self.config.get("interval_minutes", 1)
        max_candidates = max_candidates if max_candidates is not None else self.config.get("max_candidates", 1)
        
        interval_seconds = interval_minutes * 60
        cycle = 0
        
        while True:
            if max_cycles is not None and cycle >= max_cycles:
                break
            if stop_event is not None and stop_event.is_set():
                break
                
            start_time = time.time()
            
            try:
                # 1. Fetch snapshots
                snapshots = self.market_watcher.fetch_snapshots(watchlist)
                
                # 2. Score candidates
                candidates = self.opportunity_scanner.score_candidates(snapshots)
                selected_candidates = candidates[:max_candidates]
                
                # 3. Process each candidate with ticker-level exception isolation
                for candidate in selected_candidates:
                    ticker = candidate["ticker"]
                    try:
                        risk_status = self.risk_guard.assess_risk(ticker, self.portfolio_memory.load_memory())
                        
                        final_state, decision = self.ta_graph.propagate(ticker, self.market_watcher.curr_date)
                        
                        decision_dict = {
                            "ticker": ticker,
                            "decision": final_state.get("final_trade_decision", str(decision)),
                            "date": self.market_watcher.curr_date
                        }
                        self.portfolio_memory.update_portfolio(decision_dict)
                        
                        self.report_writer.log_event("ticker_analysis_success", {
                            "ticker": ticker,
                            "decision": decision_dict["decision"]
                        })
                    except Exception as ticker_err:
                        self.report_writer.log_event("ticker_analysis_failed", {
                            "ticker": ticker,
                            "error": str(ticker_err)
                        })
            except KeyboardInterrupt:
                self.report_writer.log_event("loop_terminated", {"reason": "KeyboardInterrupt"})
                break
            except Exception as cycle_err:
                self.report_writer.log_event("cycle_failed", {"error": str(cycle_err)})
                if once:
                    raise cycle_err
                    
            cycle += 1
            if once:
                break
                
            # Anti-drift dynamic sleeping
            elapsed = time.time() - start_time
            sleep_time = max(0.0, interval_seconds - elapsed)
            
            if stop_event is not None:
                slept = 0.0
                while slept < sleep_time:
                    if stop_event.is_set():
                        break
                    time.sleep(min(0.1, sleep_time - slept))
                    slept += 0.1
            else:
                time.sleep(sleep_time)

def main(args=None):
    if args is None:
        args = sys.argv[1:]
        
    parser = argparse.ArgumentParser(description="Advanced Trading Agent CLI")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval-minutes", type=int, default=1)
    parser.add_argument("--watchlist", nargs="+", default=[])
    parser.add_argument("--max-candidates", type=int, default=1)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--date", type=str)
    
    parsed = parser.parse_args(args)
    
    watchlist = []
    for item in parsed.watchlist:
        watchlist.extend([t.strip() for t in item.split(",") if t.strip()])
        
    config = {
        "watchlist": watchlist,
        "max_candidates": parsed.max_candidates,
        "interval_minutes": parsed.interval_minutes,
        "date": parsed.date
    }
    
    agent = AdvancedTradingAgent(config=config)
    
    if parsed.watch or parsed.once:
        agent.run_watch_loop(
            watchlist=watchlist,
            interval_minutes=parsed.interval_minutes,
            max_candidates=parsed.max_candidates,
            once=parsed.once
        )
    else:
        portfolio = agent.portfolio_memory.load_memory()
        if not portfolio or not portfolio.get("past_decisions"):
            portfolio = {
                "cash_usd": 50000.0,
                "positions": {
                    "AAPL": 100,
                    "TSLA": 50,
                    "GOOGL": 20
                },
                "risk_tolerance": "moderate"
            }
        agent.run(portfolio, parsed.date)

if __name__ == "__main__":
    main()
