"""
Internationalization (i18n) for the TradingAgents dashboard.

Default language is Chinese (zh). English (en) is selectable via the sidebar
language switcher. The selected language is stored in st.session_state so it
persists across reruns within a session.

Usage:
    from tradingbot.dashboard.i18n import t, language_selector

    st.title(t("app.title"))
    st.metric(t("portfolio.kpi.value"), f"${equity:,.2f}")
"""

from __future__ import annotations

from typing import Any

import streamlit as st


DEFAULT_LANG = "zh"
SUPPORTED_LANGS = ("zh", "en")

_LANG_LABELS = {
    "zh": "中文",
    "en": "English",
}


TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── app.py ────────────────────────────────────────────────────────────
    "app.page_title":          {"zh": "TradingAgents 仪表盘",        "en": "TradingAgents Dashboard"},
    "app.title":               {"zh": "📈 TradingAgents 自动交易仪表盘", "en": "📈 TradingAgents Auto-Trading Dashboard"},
    "app.sidebar.title":       {"zh": "TradingAgents 机器人",          "en": "TradingAgents Bot"},
    "app.sidebar.last_refresh":{"zh": "最近刷新：{time}",              "en": "Last refresh: {time}"},
    "app.sidebar.mode_paper":  {"zh": "模拟",                          "en": "PAPER"},
    "app.sidebar.mode_live":   {"zh": "实盘",                          "en": "LIVE"},
    "app.sidebar.navigate":    {"zh": "导航",                          "en": "Navigate"},
    "app.sidebar.watchlist":   {"zh": "**自选股**",                    "en": "**Watchlist**"},
    "app.sidebar.refresh":     {"zh": "刷新数据",                      "en": "Refresh Data"},
    "app.sidebar.language":    {"zh": "语言",                          "en": "Language"},

    # Navigation pages
    "nav.portfolio":           {"zh": "持仓",                          "en": "Portfolio"},
    "nav.performance":         {"zh": "业绩",                          "en": "Performance"},
    "nav.trades":              {"zh": "交易记录",                       "en": "Trade History"},
    "nav.signals":             {"zh": "智能体推理",                     "en": "Agent Reasoning"},
    "nav.risk":                {"zh": "风险监控",                       "en": "Risk Monitor"},

    # Quick trade panel
    "qt.header":               {"zh": "**手动快速下单**",               "en": "**Quick Trade (Manual)**"},
    "qt.ticker":               {"zh": "股票代码",                       "en": "Ticker"},
    "qt.side":                 {"zh": "方向",                           "en": "Side"},
    "qt.side.buy":             {"zh": "买入",                           "en": "BUY"},
    "qt.side.sell":            {"zh": "卖出",                           "en": "SELL"},
    "qt.qty":                  {"zh": "股数",                           "en": "Shares"},
    "qt.submit":               {"zh": "提交手动订单",                    "en": "Submit Manual Order"},
    "qt.err.no_ticker":        {"zh": "请先输入股票代码。",              "en": "Enter a ticker first."},
    "qt.success":              {"zh": "订单已成交：{qty} 股 @ ${price}", "en": "Order filled: {qty} @ ${price}"},
    "qt.reasoning":            {"zh": "来自仪表盘的手动下单",            "en": "Manual order from dashboard"},

    # ── portfolio_view.py ─────────────────────────────────────────────────
    "pv.subheader":            {"zh": "当前持仓",                       "en": "Open Positions"},
    "pv.kpi.value":            {"zh": "投资组合总值",                    "en": "Portfolio Value"},
    "pv.kpi.cash":             {"zh": "现金",                            "en": "Cash"},
    "pv.kpi.invested":         {"zh": "已投资",                          "en": "Invested"},
    "pv.kpi.unrealised":       {"zh": "未实现盈亏",                       "en": "Unrealised P&L"},
    "pv.empty":                {"zh": "暂无持仓。",                       "en": "No open positions."},
    "pv.col.ticker":           {"zh": "股票代码",                         "en": "Ticker"},
    "pv.col.shares":           {"zh": "股数",                             "en": "Shares"},
    "pv.col.avg_entry":        {"zh": "平均买入价",                       "en": "Avg Entry"},
    "pv.col.current":          {"zh": "当前价",                           "en": "Current"},
    "pv.col.market_value":     {"zh": "市值",                             "en": "Market Value"},
    "pv.col.unrealised":       {"zh": "未实现盈亏",                       "en": "Unrealised P&L"},
    "pv.col.pnl_pct":          {"zh": "盈亏 %",                            "en": "P&L %"},
    "pv.alloc.subheader":      {"zh": "持仓分布",                          "en": "Portfolio Allocation"},
    "pv.alloc.title":          {"zh": "按市值分布",                         "en": "Allocation by Market Value"},
    "pv.alloc.cash":           {"zh": "现金",                              "en": "Cash"},

    # ── performance_view.py ───────────────────────────────────────────────
    "perf.subheader":          {"zh": "业绩",                              "en": "Performance"},
    "perf.kpi.total_return":   {"zh": "总收益",                            "en": "Total Return"},
    "perf.kpi.realised_delta": {"zh": "${pnl} 已实现",                     "en": "${pnl} realised"},
    "perf.kpi.sharpe":         {"zh": "夏普比率",                           "en": "Sharpe Ratio"},
    "perf.kpi.max_dd":         {"zh": "最大回撤",                           "en": "Max Drawdown"},
    "perf.kpi.win_rate":       {"zh": "胜率",                               "en": "Win Rate"},
    "perf.kpi.wl_delta":       {"zh": "{w} 胜 / {l} 负",                    "en": "{w}W / {l}L"},
    "perf.kpi.total_trades":   {"zh": "总交易笔数",                          "en": "Total Trades"},
    "perf.kpi.avg_win":        {"zh": "平均盈利",                            "en": "Avg Win"},
    "perf.kpi.avg_loss":       {"zh": "平均亏损",                            "en": "Avg Loss"},
    "perf.kpi.profit_factor":  {"zh": "盈亏比",                              "en": "Profit Factor"},
    "perf.empty":              {"zh": "暂无历史快照。每个交易日盘后会自动记录快照。", "en": "No historical snapshots yet. Snapshots are taken post-market each trading day."},
    "perf.equity.subheader":   {"zh": "净值曲线",                            "en": "Equity Curve"},
    "perf.equity.total":       {"zh": "总净值",                              "en": "Total Equity"},
    "perf.equity.cash":        {"zh": "现金",                                "en": "Cash"},
    "perf.axis.date":          {"zh": "日期",                                "en": "Date"},
    "perf.axis.value":         {"zh": "金额 ($)",                            "en": "Value ($)"},
    "perf.dd.subheader":       {"zh": "回撤",                                "en": "Drawdown"},
    "perf.dd.name":            {"zh": "回撤 %",                              "en": "Drawdown %"},
    "perf.dd.axis":            {"zh": "回撤 (%)",                            "en": "Drawdown (%)"},
    "perf.daily.subheader":    {"zh": "每日盈亏",                            "en": "Daily P&L"},
    "perf.daily.name":         {"zh": "每日盈亏 ($)",                        "en": "Daily P&L ($)"},
    "perf.daily.axis":         {"zh": "盈亏 ($)",                            "en": "P&L ($)"},

    # ── risk_view.py ──────────────────────────────────────────────────────
    "risk.subheader":          {"zh": "风险监控",                              "en": "Risk Monitor"},
    "risk.cb.header":          {"zh": "#### 熔断器",                           "en": "#### Circuit Breaker"},
    "risk.cb.active":          {"zh": "熔断已触发 — 当日盈亏：{pnl}%（限制：{limit}%）。今日不再开新仓。", "en": "CIRCUIT BREAKER ACTIVE — Daily P&L: {pnl}% (limit: {limit}%). No new buys today."},
    "risk.cb.ok":              {"zh": "熔断器正常 — 当日盈亏：{pnl}%（限制：{limit}%）", "en": "Circuit breaker OK — Daily P&L: {pnl}% (limit: {limit}%)"},
    "risk.cb.no_snapshot":     {"zh": "暂无当日快照 — 熔断器未启用。",            "en": "No intraday snapshot yet — circuit breaker inactive."},
    "risk.exposure.header":    {"zh": "#### 总仓位敞口",                         "en": "#### Total Exposure"},
    "risk.exposure.gauge":     {"zh": "投资比例 (%)",                            "en": "Portfolio Invested (%)"},
    "risk.exposure.cash":      {"zh": "可用现金",                                "en": "Available Cash"},
    "risk.exposure.reserve":   {"zh": "最低储备：${reserve}",                      "en": "Reserve: ${reserve}"},
    "risk.exposure.invested":  {"zh": "已投资金额",                                "en": "Invested Value"},
    "risk.exposure.label":     {"zh": "敞口",                                    "en": "Exposure"},
    "risk.exposure.cap":       {"zh": "{pct}% / {cap}% 上限",                     "en": "{pct}% / {cap}% cap"},
    "risk.exposure.warn_cash": {"zh": "现金 ${cash} 低于最低储备 ${reserve}。",     "en": "Cash ${cash} is below minimum reserve ${reserve}."},
    "risk.conc.header":        {"zh": "#### 单票集中度",                          "en": "#### Position Concentration"},
    "risk.conc.x":             {"zh": "股票代码",                                "en": "Ticker"},
    "risk.conc.y":             {"zh": "占组合比例 (%)",                          "en": "% of Portfolio"},
    "risk.conc.title":         {"zh": "个股仓位 vs {cap}% 单票上限",               "en": "Position Sizes vs {cap}% Single-Position Cap"},
    "risk.conc.over":          {"zh": "超过限制",                                "en": "Over limit"},
    "risk.conc.within":        {"zh": "在限制内",                                "en": "Within limit"},
    "risk.conc.cap_line":      {"zh": "上限 {cap}%",                             "en": "Cap {cap}%"},
    "risk.empty":              {"zh": "暂无持仓 — 无需监控。",                    "en": "No open positions — nothing to monitor."},

    # ── signals_view.py ───────────────────────────────────────────────────
    "sig.subheader":           {"zh": "智能体推理",                              "en": "Agent Reasoning"},
    "sig.caption":             {"zh": "查看每个智能体的完整推理 — 分析师、研究员、风险辩手以及组合经理。可运行实时分析或加载历史记录。", "en": "Inspect the full reasoning of every agent — analysts, researchers, risk debaters, and the portfolio manager. Run a live analysis or load a past one from the bot's logs."},
    "sig.mode.live":           {"zh": "🔴 实时分析",                              "en": "🔴 Live Analysis"},
    "sig.mode.historical":     {"zh": "📁 历史日志",                              "en": "📁 Historical Logs"},
    "sig.mode.label":          {"zh": "模式",                                    "en": "Mode"},
    "sig.live.ticker":         {"zh": "股票代码",                                "en": "Ticker"},
    "sig.live.date":           {"zh": "分析日期",                                "en": "Analysis Date"},
    "sig.live.run":            {"zh": "运行分析",                                "en": "Run Analysis"},
    "sig.live.hint":           {"zh": "输入股票代码与日期后点击 **运行分析**。完整的多智能体流水线将运行，结果会显示在下方 — 不会真实下单。", "en": "Enter a ticker and date, then click **Run Analysis**. The full multi-agent pipeline will run and results will appear below — no trade is executed."},
    "sig.live.no_ticker":      {"zh": "请输入股票代码。",                          "en": "Please enter a ticker symbol."},
    "sig.live.spinner":        {"zh": "正在对 **{ticker}** 于 {date} 运行多智能体分析…", "en": "Running multi-agent analysis for **{ticker}** on {date}…"},
    "sig.live.failed":         {"zh": "分析失败：{err}",                          "en": "Analysis failed: {err}"},
    "sig.hist.empty":          {"zh": "未在 `{dir}` 找到历史分析日志。每次 `run_bot.py` 运行分析时会自动保存完整的智能体日志。这些日志也会在 **交易记录** 页面的每笔交易处直接链接。", "en": "No historical analysis logs found in `{dir}`. Every time `run_bot.py` runs an analysis, a full agent log is saved there automatically. Those same logs are also linked directly in the **Trade History** page per trade."},
    "sig.hist.ticker":         {"zh": "股票代码",                                "en": "Ticker"},
    "sig.hist.date":           {"zh": "分析日期",                                "en": "Analysis Date"},
    "sig.hist.load":           {"zh": "加载",                                    "en": "Load"},
    "sig.hist.hint":           {"zh": "选择股票代码与日期，点击 **加载** 查看智能体推理。", "en": "Select a ticker and date, then click **Load** to view the agents' reasoning."},
    "sig.hist.load_failed":    {"zh": "无法加载日志文件：{err}",                  "en": "Could not load log file: {err}"},

    # Signal header
    "sig.header.signal":       {"zh": "信号 — {ticker} | {date}",                "en": "SIGNAL — {ticker} | {date}"},
    "sig.header.research":     {"zh": "研究裁判",                                "en": "RESEARCH JUDGE"},
    "sig.header.risk":         {"zh": "风险裁判",                                "en": "RISK JUDGE"},

    # Tab labels
    "sig.tab.portfolio_mgr":   {"zh": "🎯 组合经理",                              "en": "🎯 Portfolio Mgr"},
    "sig.tab.market":          {"zh": "📊 行情",                                  "en": "📊 Market"},
    "sig.tab.news":            {"zh": "📰 新闻",                                  "en": "📰 News"},
    "sig.tab.sentiment":       {"zh": "💬 情绪",                                  "en": "💬 Sentiment"},
    "sig.tab.fundamentals":    {"zh": "📈 基本面",                                "en": "📈 Fundamentals"},
    "sig.tab.bull":            {"zh": "🐂 多头",                                  "en": "🐂 Bull"},
    "sig.tab.bear":            {"zh": "🐻 空头",                                  "en": "🐻 Bear"},
    "sig.tab.research_mgr":    {"zh": "⚖️ 研究经理",                              "en": "⚖️ Research Mgr"},
    "sig.tab.trader":          {"zh": "💼 交易员",                                "en": "💼 Trader"},
    "sig.tab.aggressive":      {"zh": "⚡ 激进派",                                "en": "⚡ Aggressive"},
    "sig.tab.neutral":         {"zh": "😐 中性派",                                "en": "😐 Neutral"},
    "sig.tab.conservative":    {"zh": "🛡️ 保守派",                                "en": "🛡️ Conservative"},

    # Section headers
    "sig.sec.pm.title":        {"zh": "组合经理",                                "en": "Portfolio Manager"},
    "sig.sec.pm.desc":         {"zh": "最终决策者。综合所有智能体的输入与风险辩论，给出最终的交易评级。", "en": "Final decision-maker. Synthesises all agent inputs and risk debates into the definitive trading rating."},
    "sig.sec.market.title":    {"zh": "行情分析师",                              "en": "Market Analyst"},
    "sig.sec.market.desc":     {"zh": "分析技术指标（MACD、RSI、布林带、移动均线、ATR、VWMA）来识别交易模式并预测价格走势。", "en": "Analyses technical indicators (MACD, RSI, Bollinger Bands, moving averages, ATR, VWMA) to identify trading patterns and forecast price movements."},
    "sig.sec.news.title":      {"zh": "新闻分析师",                              "en": "News Analyst"},
    "sig.sec.news.desc":       {"zh": "跟踪全球新闻、财报事件和宏观经济指标，解读当前事件可能对股票的影响。", "en": "Monitors global news, earnings events, and macroeconomic indicators, interpreting how current events may affect the stock."},
    "sig.sec.sent.title":      {"zh": "情绪分析师",                              "en": "Sentiment Analyst"},
    "sig.sec.sent.desc":       {"zh": "评估公众情绪与社交媒体信号，衡量短期市场情绪和散户投资者的仓位。", "en": "Assesses public sentiment and social media signals to gauge short-term market mood and retail investor positioning."},
    "sig.sec.fund.title":      {"zh": "基本面分析师",                            "en": "Fundamentals Analyst"},
    "sig.sec.fund.desc":       {"zh": "评估公司财务：资产负债表、利润表、现金流量表及关键比率，以评估内在价值。", "en": "Evaluates company financials: balance sheet, income statement, cash flow, and key ratios to assess intrinsic value."},
    "sig.sec.bull.title":      {"zh": "多头研究员",                              "en": "Bull Researcher"},
    "sig.sec.bull.desc":       {"zh": "基于证据建立最有力的买入论据。提出增长催化剂、低估机会及上涨潜力。", "en": "Builds the strongest possible evidence-based case for buying. Argues growth catalysts, undervaluation, and upside potential."},
    "sig.sec.bear.title":      {"zh": "空头研究员",                              "en": "Bear Researcher"},
    "sig.sec.bear.desc":       {"zh": "提出风险、下行情形以及谨慎或卖出的理由。用最坏情景分析对多头观点进行压力测试。", "en": "Counters with risks, downside scenarios, and reasons for caution or selling. Stress-tests the bull case with worst-case analysis."},
    "sig.sec.rm.title":        {"zh": "研究经理",                                "en": "Research Manager"},
    "sig.sec.rm.desc":         {"zh": "对多空辩论作出裁决，并将完整分析师团队的报告综合为最终投资计划，交给交易员。", "en": "Judges the bull vs bear debate and synthesises the full analyst team's reports into a final investment plan for the Trader."},
    "sig.sec.trader.title":    {"zh": "交易员",                                  "en": "Trader"},
    "sig.sec.trader.desc":     {"zh": "接收研究经理的投资计划，给出具体的 买入 / 持有 / 卖出 方案，包含入场策略、仓位与时间维度。", "en": "Takes the Research Manager's investment plan and produces a specific BUY / HOLD / SELL proposal with entry strategy, sizing, and time horizon."},
    "sig.sec.agg.title":       {"zh": "激进派风险辩手",                          "en": "Aggressive Risk Debater"},
    "sig.sec.agg.desc":        {"zh": "倡导以满仓执行交易，强调上行潜力，反对过度谨慎。", "en": "Advocates for taking the trade at full size, emphasising upside potential and arguing against excessive caution."},
    "sig.sec.neu.title":       {"zh": "中性派风险辩手",                          "en": "Neutral Risk Debater"},
    "sig.sec.neu.desc":        {"zh": "提供平衡评估，权衡激进与保守立场，寻找最优的风险调整后方案。", "en": "Provides a balanced assessment, weighing both the aggressive and conservative positions to find an optimal risk-adjusted approach."},
    "sig.sec.con.title":       {"zh": "保守派风险辩手",                          "en": "Conservative Risk Debater"},
    "sig.sec.con.desc":        {"zh": "强调下行保护、仓位管控纪律，以及不交易或减仓才是正确选择的情形。", "en": "Emphasises downside protection, position sizing discipline, and scenarios where doing nothing or reducing size is the right call."},

    # Content block labels
    "sig.block.final_decision":   {"zh": "最终交易决策",                            "en": "Final Trade Decision"},
    "sig.block.risk_judge":       {"zh": "风险辩论裁判决定",                         "en": "Risk Debate Judge Decision"},
    "sig.block.risk_history":     {"zh": "完整风险辩论记录",                         "en": "Full Risk Debate History"},
    "sig.block.market_report":    {"zh": "行情分析报告",                            "en": "Market Analysis Report"},
    "sig.block.news_report":      {"zh": "新闻分析报告",                            "en": "News Analysis Report"},
    "sig.block.sent_report":      {"zh": "情绪分析报告",                            "en": "Sentiment Analysis Report"},
    "sig.block.fund_report":      {"zh": "基本面分析报告",                          "en": "Fundamentals Analysis Report"},
    "sig.block.bull_arg":         {"zh": "多头观点",                               "en": "Bull Argument"},
    "sig.block.bear_arg":         {"zh": "空头观点",                               "en": "Bear Argument"},
    "sig.block.investment_plan":  {"zh": "投资计划",                               "en": "Investment Plan"},
    "sig.block.judge_invest":     {"zh": "投资辩论裁判决定",                         "en": "Judge Decision (Invest Debate)"},
    "sig.block.invest_history":   {"zh": "完整投资辩论记录",                         "en": "Full Investment Debate History"},
    "sig.block.trader_plan":      {"zh": "交易员的投资方案",                         "en": "Trader's Investment Plan"},
    "sig.block.agg_arg":          {"zh": "激进派风险论点",                          "en": "Aggressive Risk Argument"},
    "sig.block.neu_arg":          {"zh": "中性派风险论点",                          "en": "Neutral Risk Argument"},
    "sig.block.con_arg":          {"zh": "保守派风险论点",                          "en": "Conservative Risk Argument"},
    "sig.block.empty":            {"zh": "本智能体无输出。该次运行可能未包含它。",     "en": "No output recorded for this agent. It may not have been included in this run."},
    "sig.block.chars":            {"zh": "{n} 字",                                "en": "{n} chars"},

    # ── trades_view.py ────────────────────────────────────────────────────
    "tv.subheader":              {"zh": "交易记录",                                "en": "Trade History"},
    "tv.empty":                  {"zh": "暂无交易记录。运行 `python run_bot.py --once` 执行首笔交易。", "en": "No trades recorded yet. Run `python run_bot.py --once` to execute your first trade."},
    "tv.filter.ticker":          {"zh": "按代码筛选",                               "en": "Filter by ticker"},
    "tv.filter.side":            {"zh": "按方向筛选",                               "en": "Filter by side"},
    "tv.filter.all":             {"zh": "全部",                                    "en": "All"},
    "tv.filter.buy":             {"zh": "buy",                                    "en": "buy"},
    "tv.filter.sell":            {"zh": "sell",                                   "en": "sell"},
    "tv.col.date":               {"zh": "日期",                                    "en": "Date"},
    "tv.col.ticker":             {"zh": "股票代码",                                "en": "Ticker"},
    "tv.col.side":                {"zh": "方向",                                   "en": "Side"},
    "tv.col.shares":             {"zh": "股数",                                    "en": "Shares"},
    "tv.col.price":              {"zh": "价格",                                    "en": "Price"},
    "tv.col.value":              {"zh": "金额",                                    "en": "Value"},
    "tv.col.signal":             {"zh": "信号",                                    "en": "Signal"},
    "tv.col.logs":               {"zh": "日志",                                    "en": "Logs"},
    "tv.caption_logs":           {"zh": "**日志 ✅** 表示这笔交易存在完整的 12 智能体推理日志，可在下方查看。每次 `run_bot.py` 运行时会自动保存。", "en": "**Logs ✅** means the full 12-agent reasoning log exists for that trade and is viewable below. Logs are saved automatically every time `run_bot.py` runs."},
    "tv.per_trade.subheader":    {"zh": "每笔交易的智能体推理",                       "en": "Agent Reasoning per Trade"},
    "tv.per_trade.caption":      {"zh": "展开任一交易即可查看 12 个智能体（分析师、研究员、风险辩手、组合经理）在当时做决策时的完整推理。", "en": "Expand any trade to see the full reasoning of all 12 agents — analysts, researchers, risk debaters, and the portfolio manager — exactly as they ran when the bot made that decision."},
    "tv.expander.label":         {"zh": "{log_icon} {date}  |  {side_icon} {side} {ticker}  |  信号：{signal}  |  ${value}", "en": "{log_icon} {date}  |  {side_icon} {side} {ticker}  |  Signal: {signal}  |  ${value}"},
    "tv.side.buy":               {"zh": "买入",                                    "en": "BUY"},
    "tv.side.sell":              {"zh": "卖出",                                    "en": "SELL"},
    "tv.no_log":                 {"zh": "未找到完整智能体日志。仅显示已保存的组合经理决策。机器人运行时会将日志写入 `{path}`。", "en": "Full agent log not found. Showing the stored portfolio manager decision only. Logs are written to `{path}` when the bot runs."},
    "tv.pm_decision":            {"zh": "**组合经理决策**",                          "en": "**Portfolio Manager Decision**"},
    "tv.no_reasoning":           {"zh": "_未保存推理内容。_",                         "en": "_No reasoning stored._"},
    "tv.log_read_failed":        {"zh": "无法读取日志文件：{err}",                    "en": "Could not read log file: {err}"},

    "tv.closed.subheader":       {"zh": "已平仓持仓",                               "en": "Closed Positions"},
    "tv.closed.empty":           {"zh": "暂无已平仓持仓。",                          "en": "No closed positions yet."},
    "tv.closed.col.ticker":      {"zh": "股票代码",                                "en": "Ticker"},
    "tv.closed.col.entry_date":  {"zh": "建仓日期",                                "en": "Entry Date"},
    "tv.closed.col.exit_date":   {"zh": "平仓日期",                                "en": "Exit Date"},
    "tv.closed.col.days":        {"zh": "持有天数",                                "en": "Days Held"},
    "tv.closed.col.entry":       {"zh": "建仓价 $",                                "en": "Entry $"},
    "tv.closed.col.exit":        {"zh": "平仓价 $",                                "en": "Exit $"},
    "tv.closed.col.shares":      {"zh": "股数",                                    "en": "Shares"},
    "tv.closed.col.realised":    {"zh": "已实现盈亏",                               "en": "Realised P&L"},
    "tv.closed.col.pnl_pct":     {"zh": "盈亏 %",                                   "en": "P&L %"},
    "tv.closed.col.entry_sig":   {"zh": "建仓信号",                                "en": "Entry Signal"},
    "tv.closed.col.exit_sig":    {"zh": "平仓信号",                                "en": "Exit Signal"},
}


def get_lang() -> str:
    """Return the current language code, defaulting to Chinese."""
    return st.session_state.get("lang", DEFAULT_LANG)


def set_lang(lang: str) -> None:
    if lang in SUPPORTED_LANGS:
        st.session_state["lang"] = lang


def t(key: str, **fmt: Any) -> str:
    """Translate a key into the active language with optional .format() args."""
    lang = get_lang()
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key  # fail-soft: return key so missing strings are obvious
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, IndexError):
            return text
    return text


def language_selector(*, container=None) -> None:
    """Render the language selector. Call inside the sidebar."""
    target = container if container is not None else st.sidebar
    current = get_lang()
    options = list(SUPPORTED_LANGS)
    index = options.index(current) if current in options else 0
    selected = target.radio(
        t("app.sidebar.language"),
        options=options,
        index=index,
        format_func=lambda code: _LANG_LABELS.get(code, code),
        horizontal=True,
        key="lang_selector",
    )
    if selected != current:
        set_lang(selected)
        st.rerun()
