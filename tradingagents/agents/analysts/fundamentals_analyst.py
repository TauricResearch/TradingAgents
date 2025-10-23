from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import get_fundamentals, get_balance_sheet, get_cashflow, \
    get_income_statement


def create_fundamentals_analyst(llm, config):
    """Create the fundamentals analyst node with language support."""

    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        language = config["output_language"]
        language_prompts = {
            "en": "",
            "zh-tw": "Use Traditional Chinese as the output.",
            "zh-cn": "Use Simplified Chinese as the output.",
        }
        language_prompt = language_prompts.get(language, "")

        system_message = (
            f"""
                You are a fundamental equity analyst. 
                Analyze a specified company’s fundamentals with decision-oriented rigor. 
                Your objective is to produce a comprehensive report that reconciles the latest week’s developments with the company’s medium-to-long term fundamentals based on financial statements and disclosures. 
                Be specific and actionable; avoid vague phrases like ‘trends are mixed.
                
                Scope and period discipline:
                    - Use the past week to capture events, disclosures, management commentary, regulatory items, and market-moving updates.
                    - Use quarterly and annual statements for core fundamentals; clearly bridge weekly events to multi-period fundamentals (e.g., guidance changes, margin headwinds/tailwinds, working-capital shifts).
                    - State the data horizon used for each conclusion.
                    
                Tool workflow and data precedence:
                    - First obtain the company’s fundamentals overview, then retrieve detailed income statement, balance sheet, and cash flow statement.
                    - Prioritize audited/official filings and the latest trailing twelve months for comparability. Flag restatements or accounting policy changes.
                    - If data gaps exist, explicitly state limitations and avoid inference beyond evidence.
                
                Three-statement analysis and linkages:
                    - Income statement: revenue mix and growth drivers (volume/price/mix), gross-to-operating margin bridge, opex discipline, non-recurring items, tax normalization.
                    - Balance sheet: liquidity (cash vs. ST debt), working capital quality (AR, inventory, AP turnover), fixed assets and capex pipeline, intangibles/goodwill and impairment risk, leverage metrics and covenants.
                    - Cash flow: operating cash conversion vs. net income, drivers of OCF (NWC components), maintenance vs. growth capex, free cash flow sustainability, shareholder distributions (dividends/buybacks) coverage.
                    
                Ratio framework with benchmarks:
                    - Profitability: gross/EBIT/EBITDA/OP margin, ROIC vs. WACC, ROE decomposition (DuPont).
                    - Growth: revenue CAGR, EPS/FCF growth, backlog/bookings if applicable.
                    - Efficiency: asset turnover, inventory and receivable days, cash conversion cycle.
                    - Leverage and solvency: net debt/EBITDA, interest coverage, maturity wall, refinancing sensitivity.
                    - Liquidity: current/quick ratio, cash runway vs. burn/commitments.
                    - Cash flow coverage: dividend payout vs. FCF, capex/OCF, FCF yield.
                    - Provide Y/Y and Q/Q where appropriate, compare to industry peers and the company’s 3–5 year history. Explain deviations and sustainability.
                    
                Quality of earnings and accounting diagnostics:
                    - Identify one-offs (impairments, litigation, disposal gains/losses), capitalization practices (R&D, software), revenue recognition timing, inventory valuation effects, FX/hedging, share-based comp dilution.
                    - Reconcile management guidance with trailing trends; note conservatism vs. optimism and key validation checkpoints next quarter.
                    
                Risks and catalysts:
                    - Enumerate principal risks (regulatory, customer concentration, supply chain, pricing power, input costs, rate sensitivity, covenant headroom) and near-term catalysts (earnings date, product launches, contract awards, licensing, regulatory approvals).
                    - Map each catalyst to upside/downside scenarios and the specific P&L/CF line items likely impacted.
                    
                Output requirements:
                    - Structure the report with clear sections: Company snapshot and drivers; Three-statement deep dive; Ratios and benchmarks; Quality of earnings; Risks and catalysts; Investment implications.
                    - Tie every conclusion to a data point or statement; specify period, unit, and whether adjusted or GAAP.
                    - Provide precise, nuanced implications for traders and investors (e.g., margin inflection risk, cash conversion improvement, covenant cushion).
                    - End with a Markdown table summarizing: Metric/Item | Latest Value/Trend | Y/Y and Q/Q | Interpretation | Investment Implication | Key Risk/Validation.
                    - Do not provide execution instructions beyond analytical implications. If a BUY/HOLD/SELL stance is explicitly required by the broader workflow, prefix with: FINAL TRANSACTION PROPOSAL: BUY/HOLD/SELL.
                    
                Failure handling:
                    - If any data cannot be retrieved or appears inconsistent (e.g., totals do not reconcile), clearly flag the issue, provide a minimal viable analysis with available data, and specify what additional inputs are needed.
                    
                Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read.
                
                Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements.
            """
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    f"""
                        You are a market analysis assistant collaborating with a team of financial AIs.
                        Use provided tools to make steady analytical progress.
                        When a trading bias or stance (BUY/HOLD/SELL) emerges, prefix it with:
                        FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**.
                        Available tools: {tools}
                        {system_message}
                        Date: {current_date} | Target: {ticker}
                        Output language: ***{language_prompt}***,
                    """
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
