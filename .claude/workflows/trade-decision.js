export const meta = {
  name: 'trade-decision',
  description:
    'Run the full TradingAgents multi-agent pipeline (analysts -> bull/bear debate -> trader -> risk debate -> portfolio manager) and return a 5-tier Buy/Overweight/Hold/Underweight/Sell decision. Data comes from the tradingagents-data MCP server; all reasoning is done by Claude (subscription), so there is no LLM API spend.',
  phases: [
    { title: 'Resolve', detail: 'Resolve the real instrument identity to anchor every agent' },
    { title: 'Analysts', detail: 'Run the selected analysts in parallel' },
    { title: 'Debate', detail: 'Bull/bear debate, then the Research Manager judges' },
    { title: 'Trade', detail: 'Trader turns the plan into a transaction proposal' },
    { title: 'Risk', detail: 'Aggressive/conservative/neutral risk debate' },
    { title: 'Decision', detail: 'Portfolio Manager delivers the final rating' },
  ],
}

// --------------------------------------------------------------------------- //
// Inputs (from the /trade slash command via Workflow args)
// --------------------------------------------------------------------------- //
const a = args || {}
const ticker = String(a.ticker || '').trim()
if (!ticker) throw new Error('trade-decision requires args.ticker (e.g. "NVDA").')

const tradeDate = String(a.trade_date || a.date || '').trim()
if (!tradeDate) {
  throw new Error('trade-decision requires args.trade_date in yyyy-mm-dd (the /trade command supplies today by default).')
}

const ALL_ANALYSTS = ['market', 'social', 'news', 'fundamentals']
const analysts =
  Array.isArray(a.analysts) && a.analysts.length ? a.analysts.map((s) => String(s).toLowerCase()) : ALL_ANALYSTS
const debateRounds = Number.isFinite(a.debate_rounds) ? a.debate_rounds : 1
const riskRounds = Number.isFinite(a.risk_rounds) ? a.risk_rounds : 1
const assetType = String(a.asset_type || 'stock').trim() || 'stock'
const pastContext = String(a.past_context || '').trim() // optional reflection/memory injected by /trade

log(`TradingAgents: ${ticker} @ ${tradeDate} | analysts=[${analysts.join(',')}] | debate=${debateRounds} risk=${riskRounds}`)

// --------------------------------------------------------------------------- //
// Structured-output schemas (mirror tradingagents/agents/schemas.py)
// --------------------------------------------------------------------------- //
const RESEARCH_PLAN_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['recommendation', 'rationale', 'strategic_actions'],
  properties: {
    recommendation: { type: 'string', enum: ['Buy', 'Overweight', 'Hold', 'Underweight', 'Sell'] },
    rationale: { type: 'string' },
    strategic_actions: { type: 'string' },
  },
}

const TRADER_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['action', 'reasoning'],
  properties: {
    action: { type: 'string', enum: ['Buy', 'Hold', 'Sell'] },
    reasoning: { type: 'string' },
    entry_price: { type: ['number', 'null'] },
    stop_loss: { type: ['number', 'null'] },
    position_sizing: { type: ['string', 'null'] },
  },
}

const PM_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['rating', 'executive_summary', 'investment_thesis'],
  properties: {
    rating: { type: 'string', enum: ['Buy', 'Overweight', 'Hold', 'Underweight', 'Sell'] },
    executive_summary: { type: 'string' },
    investment_thesis: { type: 'string' },
    price_target: { type: ['number', 'null'] },
    time_horizon: { type: ['string', 'null'] },
  },
}

// --------------------------------------------------------------------------- //
// Phase: Resolve instrument identity once, anchor every downstream agent.
// --------------------------------------------------------------------------- //
phase('Resolve')
const instrumentContext = (
  await agent(
    `Call the \`resolve_instrument\` tool from the tradingagents-data MCP server with ticker="${ticker}" and asset_type="${assetType}". ` +
      `Return ONLY the exact context string the tool returns — no preamble, no commentary, no quotes.`,
    { label: `resolve:${ticker}`, phase: 'Resolve' },
  )
).trim()

const dateLine = `The current trading date is ${tradeDate}.`
const anchor = `${instrumentContext}\n${dateLine}`

// --------------------------------------------------------------------------- //
// Phase: Analysts (parallel). Each calls the MCP data tools and returns a report.
// --------------------------------------------------------------------------- //
phase('Analysts')
const ANALYST_SPECS = [
  { key: 'market', agentType: 'market-analyst', label: 'market' },
  { key: 'social', agentType: 'sentiment-analyst', label: 'sentiment' },
  { key: 'news', agentType: 'news-analyst', label: 'news' },
  { key: 'fundamentals', agentType: 'fundamentals-analyst', label: 'fundamentals' },
].filter((s) => analysts.includes(s.key))

const analystOutputs = await parallel(
  ANALYST_SPECS.map((s) => () =>
    agent(
      `${anchor}\n\nProduce your report now for ticker ${ticker}. Use the exact ticker in every tool call.`,
      { agentType: s.agentType, label: s.label, phase: 'Analysts' },
    ),
  ),
)

const reports = {}
ANALYST_SPECS.forEach((s, i) => {
  reports[s.key] = analystOutputs[i] || '(no report produced)'
})

const reportsBlock = [
  `### Market research report\n${reports.market || 'N/A (analyst not selected)'}`,
  `### Social media sentiment report\n${reports.social || 'N/A (analyst not selected)'}`,
  `### News / world affairs report\n${reports.news || 'N/A (analyst not selected)'}`,
  `### Fundamentals report\n${reports.fundamentals || 'N/A (analyst not selected)'}`,
].join('\n\n')

// --------------------------------------------------------------------------- //
// Phase: Bull/Bear debate, then Research Manager judges.
// Mirrors conditional_logic: bull first, 2 * debate_rounds total turns.
// --------------------------------------------------------------------------- //
phase('Debate')
let debateHistory = ''
let lastDebateArg = ''
const totalDebateTurns = 2 * debateRounds
for (let i = 0; i < totalDebateTurns; i++) {
  const isBull = i % 2 === 0
  const role = isBull ? 'bull-researcher' : 'bear-researcher'
  const oppLabel = isBull ? "bear's last argument" : "bull's last argument"
  const roundNo = Math.floor(i / 2) + 1
  const out = await agent(
    `${anchor}\n\nResources (analyst reports):\n${reportsBlock}\n\n` +
      `Conversation history of the debate so far:\n${debateHistory || '(none yet)'}\n\n` +
      `The ${oppLabel}:\n${lastDebateArg || '(none yet — open the case)'}\n\nDeliver your argument now.`,
    { agentType: role, label: `${isBull ? 'bull' : 'bear'}:r${roundNo}`, phase: 'Debate' },
  )
  const tagged = `${isBull ? 'Bull' : 'Bear'} Analyst: ${out}`
  debateHistory += `\n${tagged}`
  lastDebateArg = tagged
}

const planObj = await agent(
  `${instrumentContext}\n\nEvaluate this debate and deliver a clear, actionable investment plan for the trader.\n\n` +
    `Debate History:\n${debateHistory}`,
  { agentType: 'research-manager', label: 'research-manager', phase: 'Debate', schema: RESEARCH_PLAN_SCHEMA },
)
const investmentPlan = [
  `**Recommendation**: ${planObj.recommendation}`,
  '',
  `**Rationale**: ${planObj.rationale}`,
  '',
  `**Strategic Actions**: ${planObj.strategic_actions}`,
].join('\n')

// --------------------------------------------------------------------------- //
// Phase: Trader turns the plan into a concrete transaction proposal.
// --------------------------------------------------------------------------- //
phase('Trade')
const traderObj = await agent(
  `${anchor}\n\nHere is the investment plan tailored for ${ticker}:\n\n${investmentPlan}\n\n` +
    `Analyst reports for reference:\n${reportsBlock}\n\nMake your transaction decision now.`,
  { agentType: 'trader', label: 'trader', phase: 'Trade', schema: TRADER_SCHEMA },
)
const traderPlanParts = [`**Action**: ${traderObj.action}`, '', `**Reasoning**: ${traderObj.reasoning}`]
if (traderObj.entry_price !== null && traderObj.entry_price !== undefined)
  traderPlanParts.push('', `**Entry Price**: ${traderObj.entry_price}`)
if (traderObj.stop_loss !== null && traderObj.stop_loss !== undefined)
  traderPlanParts.push('', `**Stop Loss**: ${traderObj.stop_loss}`)
if (traderObj.position_sizing) traderPlanParts.push('', `**Position Sizing**: ${traderObj.position_sizing}`)
traderPlanParts.push('', `FINAL TRANSACTION PROPOSAL: **${String(traderObj.action).toUpperCase()}**`)
const traderPlan = traderPlanParts.join('\n')

// --------------------------------------------------------------------------- //
// Phase: Risk debate (aggressive -> conservative -> neutral), 3 * risk_rounds turns.
// --------------------------------------------------------------------------- //
phase('Risk')
const RISK_ORDER = [
  { agentType: 'risk-aggressive', name: 'Aggressive' },
  { agentType: 'risk-conservative', name: 'Conservative' },
  { agentType: 'risk-neutral', name: 'Neutral' },
]
let riskHistory = ''
let lastAgg = ''
let lastCon = ''
let lastNeu = ''
const totalRiskTurns = 3 * riskRounds
for (let i = 0; i < totalRiskTurns; i++) {
  const role = RISK_ORDER[i % 3]
  const roundNo = Math.floor(i / 3) + 1
  const out = await agent(
    `${anchor}\n\nAnalyst reports:\n${reportsBlock}\n\nThe trader's decision:\n${traderPlan}\n\n` +
      `Current conversation history:\n${riskHistory || '(none yet)'}\n\n` +
      `Last aggressive argument: ${lastAgg || '(none)'}\n` +
      `Last conservative argument: ${lastCon || '(none)'}\n` +
      `Last neutral argument: ${lastNeu || '(none)'}\n\nDeliver your argument now.`,
    { agentType: role.agentType, label: `${role.name.toLowerCase()}:r${roundNo}`, phase: 'Risk' },
  )
  const tagged = `${role.name} Analyst: ${out}`
  riskHistory += `\n${tagged}`
  if (role.name === 'Aggressive') lastAgg = tagged
  else if (role.name === 'Conservative') lastCon = tagged
  else lastNeu = tagged
}

// --------------------------------------------------------------------------- //
// Phase: Portfolio Manager delivers the final 5-tier decision.
// --------------------------------------------------------------------------- //
phase('Decision')
const lessonsBlock = pastContext ? `Lessons from prior decisions and outcomes:\n${pastContext}\n\n` : ''
const pmObj = await agent(
  `${instrumentContext}\n\nSynthesize the risk analysts' debate and deliver the final trading decision.\n\n` +
    `Research Manager's investment plan:\n${investmentPlan}\n\n` +
    `Trader's transaction proposal:\n${traderPlan}\n\n` +
    `${lessonsBlock}Risk Analysts Debate History:\n${riskHistory}`,
  { agentType: 'portfolio-manager', label: 'portfolio-manager', phase: 'Decision', schema: PM_SCHEMA },
)
const finalDecisionParts = [
  `**Rating**: ${pmObj.rating}`,
  '',
  `**Executive Summary**: ${pmObj.executive_summary}`,
  '',
  `**Investment Thesis**: ${pmObj.investment_thesis}`,
]
if (pmObj.price_target !== null && pmObj.price_target !== undefined)
  finalDecisionParts.push('', `**Price Target**: ${pmObj.price_target}`)
if (pmObj.time_horizon) finalDecisionParts.push('', `**Time Horizon**: ${pmObj.time_horizon}`)
const finalTradeDecision = finalDecisionParts.join('\n')

log(`Decision for ${ticker} @ ${tradeDate}: ${pmObj.rating}`)

// The orchestrating /trade command persists this result to
// ~/.tradingagents/logs and the decision log after the workflow returns.
return {
  ticker,
  trade_date: tradeDate,
  asset_type: assetType,
  analysts,
  decision: pmObj.rating,
  final_trade_decision: finalTradeDecision,
  reports,
  investment_plan: investmentPlan,
  trader_investment_plan: traderPlan,
  investment_debate: debateHistory.trim(),
  risk_debate: riskHistory.trim(),
}
