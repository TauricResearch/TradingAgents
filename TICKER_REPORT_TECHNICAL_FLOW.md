# Ticker Report Generation Steps

This document explains how this project generates a report for a specific ticker, and why each step is useful.

## 1. Start The CLI Analysis Command

The main user-facing path starts from the `analyze` command in `cli/main.py`.

This command accepts or prompts for the run inputs: ticker, analysis date, output language, selected analysts, research depth, LLM provider, quick model, deep model, save behavior, and display behavior.

Why this is useful: a report is only meaningful if the inputs are explicit. The ticker, date, models, selected analysts, and depth all affect the final recommendation.

## 2. Collect And Normalize User Selections

The CLI collects selections in `get_user_selections()` and validates command-line options before the run starts.

The ticker is normalized before use, and selected analysts are normalized into the fixed project order:

1. `market`
2. `social`
3. `news`
4. `fundamentals`

Why this is useful: normalization prevents inconsistent ticker handling and keeps graph execution deterministic even if the user supplies analysts in a different order.

## 3. Build The Runtime Configuration

`run_analysis()` copies `DEFAULT_CONFIG` and applies the selected runtime options:

- `max_debate_rounds`
- `max_risk_discuss_rounds`
- `quick_think_llm`
- `deep_think_llm`
- `backend_url`
- `llm_provider`
- provider-specific reasoning or thinking settings
- `output_language`
- checkpoint behavior

Why this is useful: the same application can run quick or deep reports without changing code. Configuration controls the cost, speed, and reasoning depth of the analysis.

## 4. Initialize The TradingAgents Graph

`TradingAgentsGraph` is initialized with the selected analysts and runtime config.

During initialization, it creates:

- quick-thinking and deep-thinking LLM clients
- tool nodes for market, social, news, and fundamentals data
- graph setup logic
- propagation logic
- memory logging
- reflection support
- signal processing

Why this is useful: the graph becomes the single orchestrator for the multi-agent workflow, while each agent remains focused on one part of the report.

## 5. Create Data Tool Nodes

The graph creates tool nodes for the data each analyst needs:

- Market analyst: stock price data and technical indicators
- Social analyst: news/social context
- News analyst: company news, global news, and insider transactions
- Fundamentals analyst: fundamentals, balance sheet, cash flow, and income statement data

Why this is useful: agents can ground their reports in retrieved data instead of relying only on model priors.

## 6. Assemble The Agent Workflow

`GraphSetup.setup_graph()` builds the LangGraph workflow.

The graph runs in this broad order:

```text
Selected Analysts
-> Bull Researcher
-> Bear Researcher
-> Research Manager
-> Trader
-> Aggressive Risk Analyst
-> Conservative Risk Analyst
-> Neutral Risk Analyst
-> Portfolio Manager
```

Why this is useful: the final report is built in stages. First it gathers evidence, then it debates the investment case, then it creates a trade plan, then it reviews risk, and finally it produces a portfolio-level decision.

## 7. Create The Initial State

`Propagator.create_initial_state()` creates the starting state for the ticker and trade date.

The initial state includes:

- `company_of_interest`
- `trade_date`
- `past_context`
- empty analyst report fields
- empty investment debate state
- empty risk debate state

Why this is useful: all agents read from and write to a shared structured state. That makes each step's output available to later steps.

## 8. Stream The Graph Execution

The CLI streams `graph.graph.stream(...)` and processes each chunk as it arrives.

For each chunk, the CLI records:

- agent messages
- tool calls
- analyst report sections
- research debate updates
- trader plan updates
- risk debate updates
- portfolio manager decision updates
- agent status changes

Why this is useful: long-running analysis is observable. The user can see which agents are active, which tools are called, and which report sections have been produced.

## 9. Generate Analyst Reports

The selected analyst agents run first.

They fill these state fields when selected:

- `market_report`
- `sentiment_report`
- `news_report`
- `fundamentals_report`

Why this is useful: the system separates technical, sentiment, news, and fundamental perspectives before synthesizing them. This makes the final recommendation easier to audit.

## 10. Run The Research Debate

After the analysts finish, the bull and bear researchers debate the case.

The bull researcher argues the positive case. The bear researcher argues the negative case. The research manager reviews the debate and writes the investment plan.

Why this is useful: forcing opposing viewpoints helps expose weak assumptions, overconfidence, and one-sided reasoning.

## 11. Create The Trader Plan

The trader agent receives the research manager's investment plan and turns it into a concrete trading proposal.

The result is stored in `trader_investment_plan`.

Why this is useful: investment analysis is not enough by itself. The trader step turns the thesis into an actionable plan.

## 12. Run Risk Management

The risk management team reviews the proposed trade from aggressive, conservative, and neutral perspectives.

Their outputs are stored in `risk_debate_state`.

Why this is useful: a trade can have a strong thesis but still be inappropriate because of downside, timing, volatility, concentration, or portfolio risk.

## 13. Produce The Portfolio Manager Decision

The portfolio manager reviews the trade plan and risk debate, then produces the final decision.

The final decision is stored as `final_trade_decision`.

Why this is useful: the final output reflects both opportunity and risk, rather than only the strongest analyst thesis.

## 14. Process The Final Signal

The graph can process the final trade decision through `process_signal()`.

Why this is useful: long narrative decisions are useful for humans, but downstream automation often needs a simpler extracted signal.

## 15. Save The Report

If saving is enabled, `save_report_to_disk()` writes the report artifacts.

It saves section files under an organized folder structure:

```text
1_analysts/
2_research/
3_trading/
4_risk/
5_portfolio/
complete_report.md
complete_report.html
```

Why this is useful: the complete report is easy to read, while each stage is also preserved separately for review, debugging, and auditability.

## 16. Display The Report

If display is enabled, `display_complete_report()` prints the full report to the terminal.

Why this is useful: the user can immediately review the final result without opening saved files.

## 17. Programmatic Graph Path

The programmatic `TradingAgentsGraph.propagate()` path performs a similar graph run but also logs the final state to JSON and stores memory-log decisions for future same-ticker reflection.

Why this is useful: repeated runs for the same ticker can use historical context and later compare prior decisions against observed returns.

