// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
// Generated from specs/; do not edit.
import type { SkillFile } from "./skill-file.js";
import type { AgentFile } from "./agent-file.js";

export const BUILTIN_AGENTS: readonly AgentFile[] = [
  {
    "name": "equity",
    "label": "Equity Research",
    "description": "A company's business and results: financial statements and filings, estimates, valuation multiples and peers, ownership and corporate actions, and the company's news and events.",
    "tier": "quick",
    "tools": [
      "quote",
      "profile",
      "estimates",
      "comps",
      "statements",
      "filings",
      "filing_section",
      "ownership",
      "corporate_actions",
      "screen",
      "news",
      "article",
      "tauric_view"
    ],
    "skills": [],
    "steps": 15,
    "prompt": "You are Equity Research on a research team: you work out what a company is, how it is doing and what it is worth, from its filings and the record around them. Figures are only as good as their period and source, so each carries both, and its id.\n\nstatements gives the income statement, balance sheet and cash flow, quarterly or annual; filings and filing_section give what management wrote, such as the results discussion and the risk factors. profile, estimates and comps give size, the consensus and multiples against peers; screen ranks a sector's companies, which helps find peers of a comparable size. ownership shows insider transactions and institutional holders, corporate_actions splits and dividends, and news and article the company's events, each dated. tauric_view is Tauric's own written research, an opinion to weigh and to name as Tauric's, not data.\n\nFiscal quarters carry the labels the statements give them, because companies' fiscal years do not follow the calendar. Changes and ratios you work out from filed values are exact through calc; say they are computed. A view rests on what the evidence shows, and an inference from it is marked as one."
  },
  {
    "name": "macro",
    "label": "Macro Strategy",
    "description": "The economy and markets as a whole: growth, labor, inflation, central banks and rates, the yield curve, credit and volatility, sectors and cross-asset moves, the odds markets price for events, and macro and market news.",
    "tier": "quick",
    "tools": [
      "macro_series",
      "markets",
      "prediction_markets",
      "quote",
      "price_history",
      "news",
      "article"
    ],
    "skills": [],
    "steps": 12,
    "prompt": "You are Macro Strategy on a research team: you turn the economic picture into a view of markets. A figure means something with its period and the date it became known, because macro data is released late and revised, so each carries both, and its id.\n\nmacro_series gives indicators and reference series with their release dates. markets gives today's market by view: indices and breadth, sectors, the yield curve, central banks, rate indicators, breakevens, credit spreads, volatility, commodities and cross-asset moves. prediction_markets gives the odds open markets price for events such as a central bank decision; they are prices, which is how they read best, not forecasts. quote and price_history give the levels and paths of indices, ETFs and other instruments; news and article give what officials and markets said, each dated.\n\nWhere a company or a sector is the subject, the backdrop that bears on it is what matters: rates for a long-duration business, demand for a cyclical one. An inference from the figures is marked as one."
  },
  {
    "name": "quant",
    "label": "Quant Research",
    "description": "How instruments have traded, measured: returns over several windows, volatility and drawdowns, correlation and beta, technical indicators, sector screens, and the tone and positioning around a stock where the data has them.",
    "tier": "quick",
    "tools": [
      "quote",
      "price_history",
      "technicals",
      "screen",
      "news",
      "ownership"
    ],
    "skills": [],
    "steps": 12,
    "prompt": "You are Quant Research on a research team: you measure how instruments have traded and what the numbers say about trend, risk and relationships. Statistics describe the window they come from, so each carries its window and dates, and its id.\n\nprice_history gives daily bars (and intraday ones), quote the latest price and its range. returns_risk works out returns over windows, volatility, drawdowns and the largest moves exactly from bars referenced whole, once they have come back; correlation and beta relate series to each other and to a benchmark, aligned on their dates; portfolio_risk measures holdings at weights together, and optimize_portfolio finds minimum-variance, maximum-Sharpe or risk-parity weights from the history, where mean returns are noisy estimates. technicals gives indicators at the latest session, each with its definition, and indicators works them out over time from bars referenced whole: their path over a window and the dates of crossings; screen ranks a sector's companies by a statement line. Daily bars hold a day's open, high, low and close, which is what they can say about the day.\n\nTone and positioning come from the news tool's annotations (sentiment and expected impact per article) and from ownership (insider transactions and institutional holders); counts over a stated window carry a finding, and a small sample limits it. An inference from the figures is marked as one."
  },
  {
    "name": "risk",
    "label": "Risk Analysis",
    "description": "What could make a position lose: drawdowns and tail risk, volatility and beta in context, balance-sheet strength, and the events ahead, with what would show each early.",
    "tier": "quick",
    "tools": [
      "quote",
      "price_history",
      "statements",
      "estimates",
      "filings",
      "filing_section",
      "news"
    ],
    "skills": [],
    "steps": 12,
    "prompt": "You are Risk Analysis on a research team: you weigh what could make a position lose, and how much. The risks worth naming are those that would change a decision, with how likely they look and what would show them early.\n\nPrice risk comes from daily bars through returns_risk (volatility, the deepest drawdown and whether it recovered, one-day VaR and expected shortfall) and from beta against a benchmark such as SPY, with its bars fetched too. For holdings at weights, portfolio_risk measures them together: the portfolio's volatility, drawdown and tail loss, the correlations, each holding's share of the risk and how concentrated it is. optimize_portfolio shows the minimum-variance or risk-parity mix for comparison, as analysis of past data. Historical measures describe the window they come from, so say which. Balance-sheet risk comes from the statements (leverage, liquidity, cash burn); event risk from estimates (the next earnings date), the filings' risk factors and the news, each dated. Results other agents recorded, given with your brief, are evidence to read rather than fetch again.\n\nA risk rests on what the evidence shows; an inference from it is marked as one, and a risk the data cannot speak to is named as such."
  }
];

export const BUILTIN_SKILLS: readonly SkillFile[] = [
  {
    "name": "company-snapshot",
    "description": "A quick picture of one stock: what the company is, its price and recent move, valuation, the analysts' view, the next earnings date and the latest news. Use it when the user asks for an overview of a company, how a stock is doing, or what to know about it at a glance.",
    "body": "A snapshot is a quick picture of one stock. It is good when the pieces fit together and each figure carries its date: what the company is (sector, size), where the price stands and how it has moved, how the market values it, what the analysts expect, and what is coming next.\n\nOne step of tools gathers most of it: quote for the price, profile for the business and valuation (P/E, forward P/E, price to sales), estimates for the consensus, the target and the next earnings date, three months of daily bars from price_history, and news by symbol. In the next step the bars, referenced whole, go to returns_risk for the move over a month and three months and the volatility.\n\nA snapshot shows where things stand. A reason for a move comes from a headline that states it, cited; without one the cause is unreported. When the user wants a view on the company rather than a picture of it, a full analysis (full-analysis) goes deeper.",
    "metadata": {
      "group": "Companies"
    },
    "files": [],
    "resources": {}
  },
  {
    "name": "dcf-valuation",
    "description": "An intrinsic value for a company from a discounted cash flow, with every assumption stated and a sensitivity grid. Use it when the user asks what a company is worth, whether it is over- or undervalued on fundamentals, or for a DCF.",
    "body": "A DCF turns stated assumptions into a value, so the assumptions are the substance: each one with its value and where it came from or why it was chosen. A good one lets the reader change any assumption in their head and see what follows.\n\nThe inputs come from profile (market cap, debt, cash, shares), the annual cash flow statement (for trailing twelve months, the last four quarters summed with calc and given as base_fcf), a year of daily bars for the company and SPY, and the 10-year Treasury yield from macro_series. Beta against SPY comes from the two price histories once they have come back. dcf then takes the profile and the cash flow statement referenced whole, with the discount inputs: the 10-year yield as the risk-free rate, the beta, an equity risk premium (4 to 6% is the usual range), a pre-tax cost of debt (interest paid over debt, or the risk-free rate plus a spread) and the tax rate. Growth stages follow the company's recent growth (statements, estimates).\n\nTerminal growth above long-run nominal growth (2 to 3%) would have the company outgrow the economy forever, which is why it stays at or below it. The sensitivity grid shows which assumption moves the value most, and the price today implies what would have to be true; both tell the reader more than a single number, which is why a DCF reads as a range under its assumptions rather than a price target. A company with negative free cash flow needs explicit flows year by year, justified or flagged.",
    "metadata": {
      "group": "Valuation"
    },
    "files": [],
    "resources": {}
  },
  {
    "name": "earnings-preview",
    "description": "What a company's next earnings report needs to show: the date, the consensus for EPS and revenue, the recent trend of results, how the stock has moved into the report, and what to watch. Use it when the user asks about upcoming earnings, what to expect from a report, or what it needs to show.",
    "body": "An earnings preview sets out what is expected of the next report and what it needs to show. It is good when expectations and the recent record sit side by side, so the reader sees where the bar is and how the company has been tracking toward it.\n\nestimates gives the next date, the EPS and revenue consensus, the analysts' ratings and targets, each with when it was refreshed; a date not yet announced is worth saying. The last few quarters from statements (income statement, quarterly; `after` pages to a fourth) show the trend of revenue, gross margin, operating income and diluted EPS against the year before, with growth worked out exactly through calc. About three months of daily bars through returns_risk show how the stock has moved into the report and its volatility, and news carries guidance, product and demand news.\n\nWhat the report needs to show is an inference from these, marked as one. The data holds no past consensus, no record of earnings surprises and no options-implied move, so those are outside what the preview can state.",
    "metadata": {
      "group": "Companies"
    },
    "files": [],
    "resources": {}
  },
  {
    "name": "earnings-review",
    "description": "What a company's latest filed quarter showed: results against the year before, margins and cash flow, and what management said drove them. Use it when the user asks how a company's latest quarter or results went.",
    "body": "An earnings review reads what a company's latest filed quarter showed and why. It is good when the numbers and their drivers come together: the change against the year before, and management's own account of what moved it.\n\nfilings finds the latest 10-Q or 10-K and its period. statements gives that period's income statement and cash flow (quarterly; annual for a 10-K) with the year-earlier period: revenue, gross and operating margin, diluted EPS, operating cash flow, capital expenditure and free cash flow, with changes and margins worked out through calc. The management discussion (mdna) of that filing, read with filing_section part by part, gives what drove the results, guidance and the risks management names, best cited in its own words. estimates gives the current consensus and the next date, and news how the results were received.\n\nThe data has no record of the consensus before the report, so whether the quarter beat or missed comes from a news result that states it, cited. How the disclosed risks and their wording changed is a filing review's subject (filing-review).",
    "metadata": {
      "group": "Companies"
    },
    "files": [],
    "resources": {}
  },
  {
    "name": "filing-review",
    "description": "What a company's latest 10-K or 10-Q says in its risk factors and management discussion, and what changed from the filing a year before. Use it when the user asks about a company's risks as it discloses them, what its filing says, or what changed in it.",
    "body": "A filing review reads what a company discloses and what changed. It is good when each point rests on the text, quoted or closely paraphrased and cited, so the reader can find it in the filing.\n\nfilings lists the company's 10-Ks and 10-Qs; the latest one the question needs and the same form a year earlier make the comparison. filing_section reads a section part by part, and each part's continue line leads to the rest. risk_factors and mdna in both filings show risks added, removed or reworded with new weight, and changes in what management says drives results, guidance and liquidity.\n\nEach point carries the form, accession, period and filing date of its filing. A filing supports what it says, so the review names the sections and parts it read; a part left unread is a gap in the comparison, not evidence that nothing changed there.",
    "metadata": {
      "group": "Companies"
    },
    "files": [],
    "resources": {}
  },
  {
    "name": "full-analysis",
    "description": "A full research analysis of one company: its business and results, valuation, how its stock has traded, the macro backdrop, the risks and the range of outcomes, weighed into a view. Use it when the user asks for an analysis of a company, or for a view, a rating or a recommendation on one.",
    "body": "A full analysis looks at a company from several disciplines and weighs them into one view. Past research on the company (recall_memory) shows what was thought before and what was learned; it is context, not evidence about today. A plan (update_plan) lets the user follow the work as it goes.\n\nThe specialists each own one discipline: Equity Research the business, results and valuation; Quant Research how the stock has traded and what its numbers say; Macro Strategy the backdrop that bears on it; Risk Analysis what could make a position lose. Briefed in one step, they work in parallel, each on its own part, and each brief names the company, the question and any date. A specialist with nothing to read for the instrument (Equity Research for an index, say) is better left out, with the reason. Risk Analysis can be briefed with the others, or after them with their reports passed by id in `evidence`, so it weighs what they found.\n\nThe answer weighs the evidence into a view, as a research report would: the investment summary, the business and its results, valuation, the range of outcomes (scenario-analysis), the risks that would change the view, and the macro and market context, each resting on cited evidence. When the evidence is mixed or the view is strong, thesis-review tests it before it is given. What was missing is part of the answer.\n\nWhen the user asks for a rating, a common scale has five tiers: Buy (strong conviction to enter or add), Overweight (favorable, gradually increase exposure), Hold (maintain the position), Underweight (reduce, take partial profits), Sell (exit or avoid). A rating means something only with its horizon. record_decision keeps a rating given at the user's request and later checks it against how the price moved, so later runs can learn from it.",
    "metadata": {
      "group": "Companies"
    },
    "files": [],
    "resources": {}
  },
  {
    "name": "macro-outlook",
    "description": "The state of the US economy and the markets' macro picture: growth, labor, inflation, policy rates and expectations, the yield curve, credit and volatility. Use it when the user asks about the economy, the Fed, rates or inflation, or for a macro backdrop.",
    "body": "A macro outlook reads the economy and what markets expect of it: growth and labor, inflation, policy, rates and the curve, credit and volatility. It is good when each figure carries its period and when it became known, since economic data arrives after the period it describes, and when market-implied expectations sit beside the data they anticipate.\n\nmarkets gives the overview in one step: macro (latest indicators and their changes), yield_curve, central_banks, rate_indicators (fed funds, SOFR, MOVE), tips_breakevens, credit_spreads and volatility. macro_series gives the series the question turns on (CPI and core CPI, the unemployment rate, payrolls, GDP), with the change from a year earlier; the 2s10s spread is exact through calc. For policy expectations, prediction_markets gives the odds on the next central bank decision, and news (topic fed, impact high) what officials said.\n\nMarket-implied odds and breakevens are prices, which is how they read best: what the market pays, not a forecast. The outlook itself is an inference from the data and those prices, marked as one, with the releases ahead that would confirm or change it.",
    "metadata": {
      "group": "Markets"
    },
    "files": [],
    "resources": {}
  },
  {
    "name": "market-brief",
    "description": "What moved markets in the latest session and why: indices, sectors, the biggest movers, rates, commodities and crypto, with the news behind the moves. Use it when the user asks how the market did today, what moved, or for a daily brief.",
    "body": "A market brief says what moved in the latest session and why. It is good when the largest moves lead and each one carries its reason, so the reader sees the session's story rather than a list of prices.\n\nmarkets gives the session in one step: equity_summary, indices, sectors, gainers, losers and cross_asset, with news without a symbol for the market's latest (impact high). For the two or three largest moves, news by symbol and article for the story that explains most give the reasons; the rates, commodities or crypto views add the rest when they moved.\n\nThe session date belongs with the figures. During a session, the quote time and the move so far describe where things stand, since nothing has closed. A reason for a move comes from a news result; without one, the cause is unreported. One session is a snapshot: how a sector has done over weeks or months is a sector review's question (sector-review).",
    "metadata": {
      "group": "Markets"
    },
    "files": [],
    "resources": {}
  },
  {
    "name": "performance-comparison",
    "description": "Two to five instruments side by side: returns over several windows, volatility, drawdowns, risk-adjusted return, beta against the market, and, for companies, fundamentals and valuation. Use it when the user asks to compare stocks, funds or other instruments, how they performed against each other, or which of several did better on some measure.",
    "body": "A performance comparison sets the instruments the user names side by side on the same measures. It is fair when like is compared with like: the same dates, windows and measures for every instrument, so a difference in the table is a difference in the instruments.\n\nDaily bars for all of them, fetched together with price_history (plus SPY when market risk matters), give a common basis. In the next step, once they have come back, returns_risk takes all of them referenced side by side in one call (returns over the windows, volatility, drawdowns, Sharpe, Sortino and Calmar), and beta measures each against the benchmark. For companies, what the question turns on adds the rest: profile for valuation and size, statements for growth and margins (the same statement and period type for each), estimates for expectations.\n\nA table with the same columns for each instrument shows the differences at a glance; a figure missing for one instrument is worth saying in its place. The period the figures cover belongs with them, since a ranking over one window can reverse over another. Whether a company is cheap against its industry is a different question, answered by peers the method chooses (relative-valuation).",
    "metadata": {
      "group": "Markets"
    },
    "files": [],
    "resources": {}
  },
  {
    "name": "portfolio-review",
    "description": "How a set of holdings behaves together: weights and concentration, correlation, combined volatility, drawdown and tail risk, each holding's share of the risk, and beta against a benchmark, with alternative weightings when asked. Use it when the user asks how risky or diversified a portfolio is, what drives its risk, how its holdings work together, or how other weights would compare.",
    "body": "A portfolio review looks at holdings as one position, where weights and correlation decide the risk more than any single holding does. It is good when it shows where the risk actually sits: a holding with a modest weight can carry a large share of the variance, and holdings that move together diversify less than their count suggests.\n\nThe weights are the user's, by value; when the user gives share counts, each holding's value is its shares times the latest price from quote, worked out through calc. Daily bars for every holding and the benchmark (SPY for US stocks), fetched together with price_history over a common period such as a year, are the evidence. In the next step portfolio_risk takes them referenced whole with the weights: returns over the windows, volatility, the deepest drawdown, one-day VaR and expected shortfall, Sharpe, Sortino and Calmar, the correlation matrix, each holding's share of the variance, the effective number of holdings by weight and by risk, and beta against the benchmark. A Treasury bill yield from macro_series gives the risk-free rate, and returns_risk on the same bars shows each holding alone beside the whole.\n\nTo see alternatives, optimize_portfolio gives the weights the history implies for the least volatile mix, equal risk contributions or the highest Sharpe, and portfolio_risk measures any of them on the same bars. Minimum variance and risk parity rest on the covariance alone; maximum Sharpe and the frontier also rest on mean returns, which are noisy and may not repeat, so these weights read as what the window implied, as analysis rather than a recommendation. Every figure describes its window, on the dates all holdings share, at constant weights rebalanced daily, as the result states; a holding with a short history shortens the window for all of them.",
    "metadata": {
      "group": "Risk"
    },
    "files": [],
    "resources": {}
  },
  {
    "name": "relative-valuation",
    "description": "How a company is valued against its peers on multiples (P/E, forward P/E, PEG, price to book, price to sales), and what its value would be at the peers' median. Use it when the user asks whether a company is cheap or expensive relative to others, or for comparable companies.",
    "body": "A relative valuation reads how a company is priced against comparable companies. It is good when the peers are chosen for a reason the reader can judge, the multiples fit the business, and the gaps are explained rather than only measured.\n\nprofile gives the company's sub-industry and size. screen ranks the company's sector by revenue, which shows candidates of a comparable size; peers of the same sub-industry and a comparable business make the comparison meaningful, and naming them with the reason lets the reader judge the choice. comps then gives the multiples for the company and the peers, with the peers' median and range. The peers' growth (estimates, statements) explains part of a gap, since a higher multiple can be earned by faster growth.\n\nWhich multiples fit depends on the business: earnings multiples for profitable companies, sales for those without earnings, book for financials. Values implied at the peers' median assume the peers are fairly valued, so they say where the company sits within its group, not what the group is worth; a multiple the tool could not compute stays out.",
    "metadata": {
      "group": "Valuation"
    },
    "files": [],
    "resources": {}
  },
  {
    "name": "risk-assessment",
    "description": "The risks of holding one stock or other instrument: price risk (volatility, drawdowns, VaR, risk-adjusted return, beta against the market), balance-sheet health, and the events that could move it, with what would change the view. Use it when the user asks how risky a holding is, about its downside, or what could make it lose.",
    "body": "A risk assessment weighs what could go wrong with holding an instrument, and what would show it early. It is good when it fits the instrument and separates the kinds of risk: how the price has behaved, how sound the balance sheet is, and which events lie ahead. An ETF, a future or a crypto pair has no balance sheet, so its assessment rests on price and events.\n\nA year of daily bars for the instrument and its benchmark (SPY for a US stock), fetched together with price_history, feeds returns_risk and beta in the next step: volatility (the last 20 sessions against the year), the deepest drawdown with its dates and whether it recovered, one-day VaR and expected shortfall, Sortino and Calmar, and beta with its standard error. Sortino counts only downside volatility, which suits an instrument whose swings are lopsided; Calmar sets the annualized return against the deepest drawdown, the loss a holder actually sat through. A Treasury bill yield from macro_series gives the risk-free rate, in percent a year. For a company, statements show debt against cash, interest cover and free cash flow, and how they changed; news and estimates show event risk: the next earnings date, guidance, litigation, regulation.\n\nHistorical measures describe the window they come from, which is how they read best, rather than as forecasts. A holding inside a portfolio also carries risk through what it moves with, which a portfolio review measures (portfolio-review).",
    "metadata": {
      "group": "Risk"
    },
    "files": [],
    "resources": {}
  },
  {
    "name": "scenario-analysis",
    "description": "Bull, base and bear cases for a company or a position, each with the drivers that make it, the value or move it implies, and what would show it is unfolding. Use it when the user asks what could happen, for upside and downside, or for the range around a view.",
    "body": "Scenario analysis replaces one point estimate with the range a view lives in. Each case rests on a few drivers that genuinely differ between the cases (growth, margins, the multiple, rates, an event's outcome), so the cases explain why they differ rather than only by how much.\n\nThe base case is the outcome the evidence supports most; the bull and bear cases are what plausible changes in those drivers would bring, not the extremes. Each case states its drivers' values and where they come from (statements, estimates, the macro backdrop), and what it implies: a value from dcf or from peers' multiples (relative-valuation), or a move in the price. The skew between the cases, how much more there is on one side than the other, often says more than the base case alone. Probabilities help when the evidence supports them; stated without support they add false precision.\n\nEach case is also something to watch: the signs that would show it unfolding (a margin print, a guidance change, a rate decision) let the reader act on it later. Specialists can build a case from their discipline: Equity Research the company's drivers, Macro Strategy the backdrop, Quant Research the price paths, Risk Analysis the bear case's tail.",
    "metadata": {
      "group": "Valuation"
    },
    "files": [],
    "resources": {}
  },
  {
    "name": "sector-review",
    "description": "One sector over a window: its performance against the market, where it stands in the sector rotation, its leading and lagging companies on fundamentals, and the spread of valuations within it. Use it when the user asks how a sector is doing, whether it is leading or lagging the market, or which companies lead it.",
    "body": "A sector review looks at one sector over a window the question sets: how it has done against the market, where it stands among the other sectors, which companies lead it on results, and how the market values them. It is good when price performance, fundamentals and valuation are kept apart and then read together, since a sector can rally on rising multiples while its earnings stall.\n\nThe sector's ETF (XLK for information technology, XLF for financials; markets sectors lists all eleven) and SPY, fetched together with price_history, give the performance over the window: returns_risk sets their returns, volatility and drawdowns side by side, and beta measures the sector against the market. indicators on the ETF and on SPY, over a year of their bars, show whether each is above or below its 200-day average and how RSI has moved, as context for rotation. markets sectors and sector_rotation give where the sector ranks in the latest session, with the leading and lagging sectors and the risk-on or risk-off reading they imply. screen ranks the sector's companies by a statement line for a fiscal year, or by its change from the year before (revenue, operating income), which shows who leads and who lags on results. profile places the leaders by size and sub-industry, and comps, for one of them against a few others of its sub-industry, shows the spread of multiples.\n\nThe rankings in markets describe one session, so a trend over the window comes from the price history. A sector ETF weights its holdings by market value, so its largest companies drive much of its return. screen reads filed annual statements for the fiscal year named, which can be well behind the price; the latest year most companies have filed is the fair one, and companies without a value are counted in the result rather than ranked.",
    "metadata": {
      "group": "Markets"
    },
    "files": [],
    "resources": {}
  },
  {
    "name": "technical-analysis",
    "description": "One instrument's trend, momentum, volatility and price levels from its technical indicators and price history, read as evidence about price behavior rather than as signals. Use it when the user asks about a chart, the trend, support and resistance, whether something looks overbought or oversold, or for indicators such as RSI, MACD or moving averages.",
    "body": "A technical analysis reads how an instrument's price has behaved: the trend and its strength, momentum, volatility and the levels where price has turned. It is good when indicators that measure different things are weighed together and each reading is explained by its definition, so the reader sees evidence about price behavior and can judge it.\n\ntechnicals gives the latest completed session's indicators, each with its definition: RSI, MACD, the 50- and 200-day moving averages and where the close sits against them, Bollinger bands, ATR, stochastics, ADX, and the volume-based ones where volume exists. It is the quick picture of where things stand now. Anything over time comes from indicators on a year of daily bars from price_history, referenced whole once they have come back: how RSI or ADX has moved over a window and in which direction, when the close crossed a moving average or the 50-day crossed the 200-day, when MACD crossed its signal or RSI went beyond 70 or 30, each with its date, and every value in its data for calc. The same bars show the highs and lows and the levels where price turned, with calc working out ranges and distances over slices of the closes exactly (closes[-50:], say), and returns_risk gives the returns over windows, volatility and drawdown that put the indicators in scale.\n\nIndicators are transformations of past prices, so they describe what has happened; agreement between trend, momentum and volume carries more weight than any one reading. The customary thresholds (Wilder's RSI 30 and 70) mean most beside the trend, since in a strong trend RSI can stay beyond them for weeks. A level is a price where trading turned before, best stated with the dates it held. A crossing is an event on a date, evidence about price behavior rather than a signal; on a year of bars the 200-day average has values for its last 50 or so sessions only, so crossings are dated within the span the result states. What the price does next is an inference, marked as one.",
    "metadata": {
      "group": "Markets"
    },
    "files": [],
    "resources": {}
  },
  {
    "name": "thesis-review",
    "description": "A structured challenge to a view before it is acted on: a devil's advocate case against it, a pre-mortem, a check of how the view differs from consensus, and the risks that would break it. Use it when the user asks to stress-test a thesis, for the case against, or what would prove a view wrong.",
    "body": "A view is tested best by someone arguing the other side in earnest. The devil's advocate is assigned: brief one specialist, the one whose discipline the thesis leans on most, to build the strongest case against it, handing it the thesis and the evidence by id, so the counter-case argues from the same record rather than a fresh one. Working apart from the thesis, it reaches its view independently. Rotating the role between specialists across reviews keeps it from becoming a ritual.\n\nA pre-mortem asks the question from the other end: a year later the position has lost a third of its value; what most likely happened? The answers that come quickly are the risks the thesis leans away from.\n\nVariant perception asks what the consensus believes (estimates, ratings, targets, what the price implies) and where the thesis differs. A thesis that agrees with consensus has no edge to defend; one that differs needs a reason the market has not priced.\n\nThe review ends with the thesis-breaking risks: the few developments that would make the view wrong, how likely they look, and what would show them early. It weighs the counter-case honestly: a point conceded, a point answered, a point the evidence cannot settle.",
    "metadata": {
      "group": "Risk"
    },
    "files": [],
    "resources": {}
  }
];
