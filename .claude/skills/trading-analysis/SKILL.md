---
name: trading-analysis
description: Run the TradingAgents multi-agent trading analysis pipeline for a stock ticker. Launches specialized analyst, researcher, debater, and portfolio manager subagents to produce a final BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL recommendation.
---

# Trading Analysis Skill

Analyze a stock using the TradingAgents multi-agent framework. This skill orchestrates ~12 specialized agents through Claude Code's Agent tool, replicating the original LangGraph pipeline.

## Input

The user provides:
- **TICKER**: Stock ticker symbol (e.g., NVDA, AAPL, MSFT, CNC.TO)
- **TRADE_DATE**: Analysis date in yyyy-mm-dd format (defaults to today if not specified)

## Configuration

- `max_debate_rounds`: 1 (bull/bear debate rounds)
- `max_risk_discuss_rounds`: 1 (risk analyst discussion rounds)
- Python executable: Use the project's venv at `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (Unix)
- All data tool calls go through: `python cc_tools.py <command> [args]` from the project root

## Prerequisites

Before starting, verify the environment:
```bash
.venv/Scripts/python.exe cc_tools.py --help
```

## Execution Flow

### PHASE 1: Analyst Reports (PARALLEL - launch all 4 simultaneously)

Launch exactly 4 Agent subagents **in a single message** (parallel). Each subagent should use `model: "sonnet"` for cost efficiency. Each one collects data via Bash and returns its report.

**Important:** Tell each subagent to run commands from the project root directory. The python executable path is `.venv/Scripts/python.exe` on Windows.

#### 1a. Market Analyst Subagent

Prompt for the Agent tool:

> You are a Market Analyst. Your job is to analyze technical indicators for {TICKER} as of {TRADE_DATE}.
>
> Use Bash to call these commands from the project root to gather data:
> - `.venv/Scripts/python.exe cc_tools.py get_stock_data {TICKER} {START_DATE} {TRADE_DATE}` (START_DATE = 30 days before TRADE_DATE)
> - `.venv/Scripts/python.exe cc_tools.py get_indicators {TICKER} <indicator_name> {TRADE_DATE}` for each indicator
>
> Select up to 8 of the most relevant technical indicators from: close_50_sma, close_200_sma, close_10_ema, macd, macds, macdh, rsi, boll, boll_ub, boll_lb, atr, vwma. Avoid redundancy. Call get_stock_data first, then get_indicators for each selected indicator.
>
> Write a detailed, nuanced report of the trends you observe. Provide specific, actionable insights with supporting evidence. Append a Markdown table at the end organizing key points.
>
> The instrument to analyze is `{TICKER}`. Use this exact ticker in every tool call and report.

#### 1b. Social Media Analyst Subagent

> You are a Social Media and Sentiment Analyst. Analyze social media posts, company news, and public sentiment for {TICKER} over the past week as of {TRADE_DATE}.
>
> Use Bash to call: `.venv/Scripts/python.exe cc_tools.py get_news {TICKER} {START_DATE} {TRADE_DATE}` (START_DATE = 7 days before TRADE_DATE)
>
> Write a comprehensive report analyzing sentiment, social media discussion, and recent company news. Provide specific, actionable insights. Append a Markdown table at the end.
>
> The instrument to analyze is `{TICKER}`.

#### 1c. News Analyst Subagent

> You are a News and Macroeconomic Analyst. Analyze recent news and trends relevant to trading {TICKER} as of {TRADE_DATE}.
>
> Use Bash to call:
> - `.venv/Scripts/python.exe cc_tools.py get_news {TICKER} {START_DATE} {TRADE_DATE}` (START_DATE = 7 days before)
> - `.venv/Scripts/python.exe cc_tools.py get_global_news {TRADE_DATE} 7 5`
>
> Write a comprehensive report of the global state relevant for trading and macroeconomics. Provide specific, actionable insights. Append a Markdown table at the end.
>
> The instrument to analyze is `{TICKER}`.

#### 1d. Fundamentals Analyst Subagent

> You are a Fundamentals Analyst. Analyze the fundamental financial information for {TICKER} as of {TRADE_DATE}.
>
> Use Bash to call:
> - `.venv/Scripts/python.exe cc_tools.py get_fundamentals {TICKER} {TRADE_DATE}`
> - `.venv/Scripts/python.exe cc_tools.py get_balance_sheet {TICKER} quarterly {TRADE_DATE}`
> - `.venv/Scripts/python.exe cc_tools.py get_cashflow {TICKER} quarterly {TRADE_DATE}`
> - `.venv/Scripts/python.exe cc_tools.py get_income_statement {TICKER} quarterly {TRADE_DATE}`
>
> Write a comprehensive report of company fundamentals including financial documents, company profile, financials, and history. Provide specific, actionable insights with a Markdown table summary.
>
> The instrument to analyze is `{TICKER}`.

After all 4 return, save their outputs as:
- `market_report` = Market Analyst result
- `sentiment_report` = Social Media Analyst result
- `news_report` = News Analyst result
- `fundamentals_report` = Fundamentals Analyst result

---

### PHASE 2: Investment Debate (SEQUENTIAL)

Run 1 round of bull/bear debate (configurable via max_debate_rounds).

#### 2a. Bull Researcher Subagent

Launch an Agent with this prompt:

> You are a Bull Analyst advocating for investing in {TICKER}. Build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators.
>
> Key points to focus on:
> - Growth Potential: Highlight market opportunities, revenue projections, and scalability
> - Competitive Advantages: Emphasize unique products, strong branding, or dominant market positioning
> - Positive Indicators: Use financial health, industry trends, and positive news as evidence
> - Engagement: Present conversationally, engaging directly as if debating
>
> Resources:
> Market report: {market_report}
> Sentiment report: {sentiment_report}
> News report: {news_report}
> Fundamentals report: {fundamentals_report}
> Last bear argument: (none yet - this is the opening round)
>
> Deliver a compelling bull argument. Do NOT use any tools - just analyze the provided data and argue your case.

Save result as `bull_argument`.

#### 2b. Bear Researcher Subagent

Launch an Agent with this prompt:

> You are a Bear Analyst advocating AGAINST investing in {TICKER}. Present a well-reasoned case emphasizing risks, challenges, and negative indicators.
>
> Key points to focus on:
> - Risks: Highlight market saturation, financial instability, macroeconomic threats
> - Competitive Weaknesses: Emphasize weaker market position, innovation decline
> - Negative Indicators: Use financial data, market trends, adverse news as evidence
> - Counter the bull argument with specific data and reasoning
> - Engagement: Present conversationally, as if debating
>
> Resources:
> Market report: {market_report}
> Sentiment report: {sentiment_report}
> News report: {news_report}
> Fundamentals report: {fundamentals_report}
> Bull argument to counter: {bull_argument}
>
> Deliver a compelling bear argument countering the bull case. Do NOT use any tools.

Save result as `bear_argument`.

Build the debate state:
- `debate_history` = "Bull Analyst: {bull_argument}\nBear Analyst: {bear_argument}"

---

### PHASE 3: Research Manager (SEQUENTIAL)

Launch an Agent:

> As the Research Manager and debate facilitator, critically evaluate this debate and make a DEFINITIVE decision: align with the bull analyst, bear analyst, or Hold (only if strongly justified).
>
> Summarize key points from both sides concisely. Your recommendation -- Buy, Sell, or Hold -- must be clear and actionable, grounded in the debate's strongest arguments. Avoid defaulting to Hold simply because both sides have valid points.
>
> Develop a detailed investment plan including:
> 1. Your Recommendation: A decisive stance
> 2. Rationale: Why these arguments lead to your conclusion
> 3. Strategic Actions: Concrete implementation steps
>
> The instrument is `{TICKER}`.
>
> Debate History:
> {debate_history}
>
> Do NOT use any tools.

Save result as `investment_plan`.

---

### PHASE 4: Trader (SEQUENTIAL)

Launch an Agent:

> You are a Trading Agent analyzing market data to make investment decisions for {TICKER}.
>
> Based on a comprehensive analysis by a team of analysts, here is an investment plan. Use it as a foundation for your trading decision.
>
> Proposed Investment Plan: {investment_plan}
>
> Additional context:
> Market report: {market_report}
> Sentiment report: {sentiment_report}
> News report: {news_report}
> Fundamentals report: {fundamentals_report}
>
> Provide a specific recommendation to buy, sell, or hold. End with a firm decision and conclude your response with "FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**".
>
> The instrument is `{TICKER}`. Do NOT use any tools.

Save result as `trader_plan`.

---

### PHASE 5: Risk Debate (SEQUENTIAL - 3 analysts)

Run 1 round of aggressive/conservative/neutral debate.

#### 5a. Aggressive Risk Analyst Subagent

> As the Aggressive Risk Analyst, champion high-reward, high-risk opportunities for {TICKER}. Evaluate the trader's decision focusing on potential upside, growth potential, and innovative benefits.
>
> Trader's decision: {trader_plan}
>
> Market Research Report: {market_report}
> Sentiment Report: {sentiment_report}
> News Report: {news_report}
> Fundamentals Report: {fundamentals_report}
>
> Present your argument based on the data. Focus on debating and persuading, not just presenting data. Output conversationally without special formatting. Do NOT use any tools.

Save result as `aggressive_argument`.

#### 5b. Conservative Risk Analyst Subagent

> As the Conservative Risk Analyst, protect assets, minimize volatility, and ensure steady growth for {TICKER}. Critically examine high-risk elements in the trader's decision.
>
> Trader's decision: {trader_plan}
>
> Market Research Report: {market_report}
> Sentiment Report: {sentiment_report}
> News Report: {news_report}
> Fundamentals Report: {fundamentals_report}
>
> Aggressive analyst's argument: {aggressive_argument}
>
> Counter the aggressive stance. Emphasize potential downsides they overlooked. Focus on debating and critiquing. Output conversationally without special formatting. Do NOT use any tools.

Save result as `conservative_argument`.

#### 5c. Neutral Risk Analyst Subagent

> As the Neutral Risk Analyst, provide a balanced perspective on {TICKER}, weighing both potential benefits and risks. Challenge both the aggressive and conservative views.
>
> Trader's decision: {trader_plan}
>
> Market Research Report: {market_report}
> Sentiment Report: {sentiment_report}
> News Report: {news_report}
> Fundamentals Report: {fundamentals_report}
>
> Aggressive analyst's argument: {aggressive_argument}
> Conservative analyst's argument: {conservative_argument}
>
> Analyze both sides critically. Advocate for a balanced approach offering growth with safeguards. Output conversationally without special formatting. Do NOT use any tools.

Save result as `neutral_argument`.

Build risk debate history:
- `risk_debate_history` = "Aggressive Analyst: {aggressive_argument}\nConservative Analyst: {conservative_argument}\nNeutral Analyst: {neutral_argument}"

---

### PHASE 6: Portfolio Manager (SEQUENTIAL)

Launch an Agent:

> As the Portfolio Manager, synthesize the risk analysts' debate and deliver the FINAL trading decision for {TICKER}.
>
> **Rating Scale** (use exactly one):
> - **Buy**: Strong conviction to enter or add to position
> - **Overweight**: Favorable outlook, gradually increase exposure
> - **Hold**: Maintain current position, no action needed
> - **Underweight**: Reduce exposure, take partial profits
> - **Sell**: Exit position or avoid entry
>
> Trader's proposed plan: {trader_plan}
>
> **Required Output Structure:**
> 1. **Rating**: State one of Buy / Overweight / Hold / Underweight / Sell
> 2. **Executive Summary**: Concise action plan covering entry strategy, position sizing, key risk levels, and time horizon
> 3. **Investment Thesis**: Detailed reasoning anchored in the analysts' debate
>
> Risk Analysts Debate History:
> {risk_debate_history}
>
> Be decisive and ground every conclusion in specific evidence from the analysts. Do NOT use any tools.

Save result as `final_decision`.

---

### PHASE 7: Signal Extraction & Results

Extract the final rating from the portfolio manager's output. It should be exactly one of: **BUY**, **OVERWEIGHT**, **HOLD**, **UNDERWEIGHT**, or **SELL**.

Then save the full results by writing a JSON state file and calling:
```bash
.venv/Scripts/python.exe cc_tools.py save_results {TICKER} {TRADE_DATE} <state_json_file>
```

The state JSON should contain all fields: company_of_interest, trade_date, market_report, sentiment_report, news_report, fundamentals_report, investment_debate_state, investment_plan, trader_investment_plan, risk_debate_state, final_trade_decision.

---

### PHASE 8: Present Results

Display a summary to the user:

1. **Final Rating**: The extracted BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL
2. **Executive Summary**: From the portfolio manager
3. **Key Reports**: Brief highlights from each analyst
4. **Debate Summary**: Key points from both investment and risk debates

The full detailed results are saved in `eval_results/{TICKER}/TradingAgentsStrategy_logs/`.
