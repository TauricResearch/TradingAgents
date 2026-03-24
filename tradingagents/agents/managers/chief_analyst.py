from tradingagents.agents.utils.agent_states import ChiefAnalystReport


def create_chief_analyst(llm):
    """Create the Chief Analyst node — final synthesis step of the pipeline.

    Uses structured output to produce a validated 4-section executive summary.
    Returns {"chief_analyst_report": dict} to be stored in AgentState.
    """
    structured_llm = llm.with_structured_output(ChiefAnalystReport)

    def chief_analyst_node(state) -> dict:
        company = state["company_of_interest"]
        trade_date = state["trade_date"]

        market_report       = state.get("market_report", "")
        sentiment_report    = state.get("sentiment_report", "")
        news_report         = state.get("news_report", "")
        fundamentals_report = state.get("fundamentals_report", "")
        investment_plan     = state.get("investment_plan", "")
        trader_plan         = state.get("trader_investment_plan", "")
        final_decision      = state.get("final_trade_decision", "")

        prompt = f"""You are the Chief Analyst. You have received the outputs of a full multi-agent analysis pipeline for {company} on {trade_date}. Synthesize the key findings into a concise executive summary.

## Market Analysis
{market_report}

## Sentiment Analysis
{sentiment_report}

## News Analysis
{news_report}

## Fundamentals Analysis
{fundamentals_report}

## Research Investment Plan (Bull/Bear synthesis)
{investment_plan}

## Trader's Plan
{trader_plan}

## Risk Judge's Final Decision
{final_decision}

---

Produce a concise executive summary with exactly these four fields:

- verdict: The final trade decision — must be exactly "BUY", "SELL", or "HOLD".
- catalyst: The 1–3 strongest data points driving this verdict (drawn from market, news, or fundamentals). Be specific and concrete.
- execution: A brief summary of the trader's entry/exit strategy. What is the plan?
- tail_risk: The single most significant unmitigated risk identified by the Risk Judge. What could make this trade go wrong?

Be decisive. Be concise. Do not hedge."""

        report: ChiefAnalystReport = structured_llm.invoke(prompt)
        return {"chief_analyst_report": report.model_dump()}

    return chief_analyst_node
