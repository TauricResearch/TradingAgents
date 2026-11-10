/**
 * One-line explanations behind the `?` marks, each pointing at the guide section
 * that says more. `text` may use the same `{{name}}` placeholders as the guide.
 */

import type { GuideSectionId } from './guide'

export type HelpKey =
  // top bar
  | 'drawdown'
  | 'processed_to'
  // overview asset card
  | 'equity'
  | 'today_pnl'
  | 'unrealized_total'
  | 'realized'
  | 'cash'
  | 'notional_total'
  | 'total_pnl'
  | 'exposure'
  // validation metrics
  | 'cumulative'
  | 'annualized_net'
  | 'sharpe'
  | 'max_drawdown'
  | 'calmar'
  | 'validation_days'
  // overview panels
  | 'equity_chart'
  | 'performance'
  | 'latest_research'
  | 'rating'
  | 'positions'
  | 'llm_cost'
  | 'budget_cap'
  | 'accuracy'
  | 'settled'
  | 'hit_rate'
  | 'mean_alpha'
  // positions table columns
  | 'side'
  | 'qty'
  | 'entry'
  | 'price'
  | 'notional'
  | 'unrealized'
  | 'unrealized_pct'
  | 'stop'
  | 'stop_distance'
  // research detail sections, in pipeline order
  | 's_market'
  | 's_sentiment'
  | 's_news'
  | 's_fundamentals'
  | 's_debate'
  | 's_plan'
  | 's_trader'
  | 's_risk'
  | 's_decision'
  | 'tokens'
  // history tabs
  | 'fills'
  | 'fill_reason'
  | 'funding'
  | 'attempts'
  | 'events'

export interface HelpEntry {
  text: string
  section: GuideSectionId
}

export const HELP: Record<HelpKey, HelpEntry> = {
  drawdown: {
    text: `净值从历史峰值回落的幅度；回撤达到 {{kill_drawdown_pct}} 时触发熔断，全部平仓并停止交易。`,
    section: 'risk',
  },
  processed_to: {
    text: `账本回放到的最后时间点，每小时更新一次；数值明显偏早说明后台任务可能暂停了。`,
    section: 'daily-cycle',
  },
  equity: {
    text: `账户总资产（净值，USDT）= 现金 + 所有仓位按现价标记的浮动盈亏；注释里的本金是开户时的初始资金。`,
    section: 'overview-page',
  },
  today_pnl: {
    text: `今天到现在赚了还是亏了：实时总资产减去今天 UTC 零点（北京时间 08:00）的净值快照，含成交、手续费和资金费，不含 AI 研判费用；零点快照由整点任务写入，还没写时以上一个快照为起点并注明。`,
    section: 'overview-page',
  },
  unrealized_total: {
    text: `所有未平仓位按现价计算的浮动盈亏之和；只要有一个合约拿不到报价就显示“—”，不给出会误导的部分合计。`,
    section: 'overview-page',
  },
  realized: {
    text: `已经落袋的盈亏 = 现金 − 本金：历史上每次平仓、减仓的盈亏，扣掉手续费，再加上收付的资金费。`,
    section: 'overview-page',
  },
  cash: {
    text: `账户现金（USDT）：本金加上已实现盈亏。模拟账户不冻结保证金，持仓的浮动盈亏单独计在总资产里。`,
    section: 'overview-page',
  },
  notional_total: {
    text: `所有持仓的名义价值之和（数量 × 现价）；杠杆 = 名义 ÷ 总资产，大于 1 表示合约追踪的资产超过了账户本身。`,
    section: 'perps',
  },
  total_pnl: {
    text: `开户以来的总盈亏 = 总资产 − 本金，即已实现 + 未实现；百分比按本金计。验证期的策略指标在净值曲线下方。`,
    section: 'overview-page',
  },
  exposure: {
    text: `各合约名义价值占全部持仓的比例，绿为多头、红为空头；一眼看出资金压在哪个币、哪个方向。`,
    section: 'overview-page',
  },
  cumulative: {
    text: `从验证期第一天起，净值的累计涨跌幅（百分比）。`,
    section: 'overview-page',
  },
  annualized_net: {
    text: `扣除 AI 研判费用后的年化收益率；验证期天数很少时，这个数字会很极端，不具参考价值。`,
    section: 'overview-page',
  },
  sharpe: {
    text: `年化收益除以年化波动率（按 365 天、无风险利率 0）；衡量每单位风险换来多少收益，越高越好，样本不足时无意义。`,
    section: 'overview-page',
  },
  max_drawdown: {
    text: `验证期内净值从历史峰值到最低点的最大跌幅，衡量经历过的最深亏损坑有多深。`,
    section: 'overview-page',
  },
  calmar: {
    text: `年化收益除以最大回撤；衡量每单位下行风险换来的年化收益，越高越好，样本不足时无意义。`,
    section: 'overview-page',
  },
  validation_days: {
    text: `验证期已运行的天数；计划跑 4–8 周后评估策略是否有效。换模型或版本升级会重置计时。`,
    section: 'validation',
  },
  equity_chart: {
    text: `三条净值曲线：策略（扣 AI 费用）、{{coins}} 等权买入持有、BTC 买入持有；从验证期第二天起显示。`,
    section: 'overview-page',
  },
  performance: {
    text: `策略与两个对照组合的累计收益、年化、Sharpe、最大回撤、年化/回撤对比；样本少时数字没有统计意义。`,
    section: 'validation',
  },
  latest_research: {
    text: `每个币最新一次研判的评级、当日成交摘要和 AI 费用；点击可进入完整的研判流程详情。`,
    section: 'research',
  },
  rating: {
    text: `AI 对这枚币方向的判断，分 Buy / Overweight / Hold / Underweight / Sell 五档；是观点，不是交易指令，实际仓位由代码按规则计算。`,
    section: 'sizing',
  },
  positions: {
    text: `当前所有未平仓位的明细：合约、方向、数量、均价、现价、名义价值、浮动盈亏、止损价和距止损百分比。`,
    section: 'overview-page',
  },
  llm_cost: {
    text: `AI 研判费用：今日和本月累计；月度上限在观察满 {{budget_learning_days}} 天后自动设定，超过后本月暂停研判。`,
    section: 'overview-page',
  },
  budget_cap: {
    text: `月度 AI 费用上限 = 日均费用 × 30 × {{budget_headroom}}，观察满 {{budget_learning_days}} 天后自动设定；超过则本月不再研判，下月自动恢复。`,
    section: 'overview-page',
  },
  accuracy: {
    text: `已结算评级的命中率和平均 alpha，衡量评级预测方向准不准；不等于策略整体赚钱。`,
    section: 'validation',
  },
  settled: {
    text: `已结算：{{holding_days}} 天后已算出 alpha；待结算：还在等待期内；未评分：REVIEW 或研判失败，无法结算。`,
    section: 'validation',
  },
  hit_rate: {
    text: `这档评级结算后 alpha 为正的比例；越高说明这档评级的方向判断越准确。`,
    section: 'validation',
  },
  mean_alpha: {
    text: `这档评级结算后相对 {{benchmark}}（持有现金）的平均超额收益；正值说明评级有预测价值。`,
    section: 'validation',
  },
  side: {
    text: `持仓方向：多（Long，看涨，价格涨则盈利）或空（Short，看跌，价格跌则盈利）。`,
    section: 'perps',
  },
  qty: {
    text: `持有的合约数量，以币为单位；乘以现价即为名义价值。`,
    section: 'overview-page',
  },
  entry: {
    text: `建仓时的加权平均成交价格；浮动盈亏以此为基准计算。`,
    section: 'overview-page',
  },
  price: {
    text: `该合约当前市场最新价，每 60 秒随页面刷新。`,
    section: 'overview-page',
  },
  notional: {
    text: `持仓数量 × 现价，合约追踪的名义资产总值；可以超过账户净值（即有杠杆）。`,
    section: 'perps',
  },
  unrealized: {
    text: `按现价计算、尚未平仓的浮动盈亏；平仓后转为已实现盈亏并计入现金。`,
    section: 'overview-page',
  },
  unrealized_pct: {
    text: `浮动盈亏相对开仓时仓位价值（数量 × 开仓均价）的百分比，已按方向折算：空头在价格下跌时为正。`,
    section: 'overview-page',
  },
  stop: {
    text: `触发自动平仓的价格：多头在入场价下方 {{stop_atr_mult}} 倍 ATR，每天研判后只收紧不放松；跳空按开盘价成交。`,
    section: 'risk',
  },
  stop_distance: {
    text: `现价距止损价的百分比距离；越小说明止损越近，若触及则自动平仓。`,
    section: 'risk',
  },
  s_market: {
    text: `市场分析师的报告：价格走势、均线、MACD、RSI、布林带、ATR 等技术指标的分析解读。`,
    section: 'research-page',
  },
  s_sentiment: {
    text: `社媒情绪分析师的报告：Reddit、StockTwits 等平台上关于这枚币的讨论热度和情绪倾向。`,
    section: 'research-page',
  },
  s_news: {
    text: `新闻分析师的报告：币圈相关新闻、全球宏观新闻，以及美联储 CPI、利率、失业率等宏观数据解读。`,
    section: 'research-page',
  },
  s_fundamentals: {
    text: `基本面分析；加密货币没有公司财报，此节始终为空，界面中已隐藏。`,
    section: 'research-page',
  },
  s_debate: {
    text: `看涨研究员与看跌研究员的辩论原文，可以看到双方最核心的论据和分歧所在。`,
    section: 'research-page',
  },
  s_plan: {
    text: `研究经理综合多空辩论后给出的方向建议，供交易员据此制定具体操作方案。`,
    section: 'research-page',
  },
  s_trader: {
    text: `交易员根据研究经理建议写出的具体操作方案；其中的价格目标只是文字，实际止损由代码按 ATR 规则计算。`,
    section: 'research-page',
  },
  s_risk: {
    text: `激进、保守、中立三位风险分析师对交易方案的评估意见，从不同角度审视方案的风险。`,
    section: 'research-page',
  },
  s_decision: {
    text: `组合经理综合全部分析后给出的最终评级（Buy / Overweight / Hold / Underweight / Sell），或无法识别时记为 REVIEW。`,
    section: 'research-page',
  },
  tokens: {
    text: `本次研判消耗的 token 数量（输入 / 输出）和对应的美元费用；多次尝试分别记录。`,
    section: 'history-page',
  },
  fills: {
    text: `所有成交记录：时间、合约、方向、数量、成交价、手续费，按时间倒序排列。`,
    section: 'history-page',
  },
  fill_reason: {
    text: `成交原因：调仓（按评级主动调整）、止损（触达止损价自动平仓）、熔断（回撤超 {{kill_drawdown_pct}} 全部平仓）。`,
    section: 'history-page',
  },
  funding: {
    text: `永续合约资金费结算记录：每 8 小时一次，正值为收入（空头付给多头），负值为支出（多头付给空头）。`,
    section: 'perps',
  },
  attempts: {
    text: `每次研判尝试的记录：评级或错误原因、token 用量和费用；每个币每天最多尝试 {{max_attempts}} 次。`,
    section: 'history-page',
  },
  events: {
    text: `影响验证期连续性的重要事件：熔断解除、模型或版本变化（会重置验证期计时）等。`,
    section: 'history-page',
  },
}
