import asyncio
from tradingagents.portfolio.report_store import ReportStore
from agent_os.backend.services.report_helpers import normalize_scan_summary

async def main():
    store = ReportStore(run_id='01KQ05XQ07FCBTNSEFJN6EZCNY')
    date = '2026-04-24'
    scan_summary = normalize_scan_summary(store.load_scan(date) or {})
    
    ticker_analyses = {"equity:AMD": {"analysis_status": "completed", "final_trade_decision": "buy"}}
    scan_summary["ticker_analyses"] = ticker_analyses

    initial_state = {
        "portfolio_id": "baacb7eb-08b5-4a98-9cf6-206b2245c3c7",
        "analysis_date": date,
        "prices": {},
        "scan_summary": scan_summary,
        "ticker_analyses": ticker_analyses,
        "messages": [],
    }
    
    from tradingagents.agents.portfolio.macro_summary_agent import create_macro_summary_agent
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda
    
    def fake_invoke(*args, **kwargs):
        return AIMessage(content="FAKE MACRO BRIEF\nMACRO REGIME: risk-on\n")
        
    llm = RunnableLambda(fake_invoke)
            
    node = create_macro_summary_agent(llm, None)
    res = node(initial_state)
    print("Node result macro_brief:", res.get("macro_brief"))

if __name__ == "__main__":
    asyncio.run(main())
