/** Station agents and how reports hand off between them. */

export const AGENT_DEFS = [
  {
    id: 'market',
    label: 'Market Analyst',
    short: 'Market',
    accent: '#2ee6d6',
    section: 'market_report',
    analyst: 'market',
  },
  {
    id: 'social',
    label: 'Sentiment Analyst',
    short: 'Social',
    accent: '#c084fc',
    section: 'sentiment_report',
    analyst: 'social',
  },
  {
    id: 'news',
    label: 'News Analyst',
    short: 'News',
    accent: '#fbbf24',
    section: 'news_report',
    analyst: 'news',
  },
  {
    id: 'fundamentals',
    label: 'Fundamentals Analyst',
    short: 'Fundamentals',
    accent: '#34d399',
    section: 'fundamentals_report',
    analyst: 'fundamentals',
  },
  {
    id: 'research',
    label: 'Research Team',
    short: 'Research',
    accent: '#60a5fa',
    section: 'investment_plan',
  },
  {
    id: 'trader',
    label: 'Trader',
    short: 'Trader',
    accent: '#fb923c',
    section: 'trader_investment_plan',
  },
  {
    id: 'portfolio',
    label: 'Portfolio Manager',
    short: 'Portfolio',
    accent: '#19c39c',
    section: 'final_trade_decision',
  },
]

export const HANDOFF = {
  market_report: 'research',
  sentiment_report: 'research',
  news_report: 'research',
  fundamentals_report: 'research',
  investment_plan: 'trader',
  trader_investment_plan: 'portfolio',
}

export function agentBySection(key) {
  return AGENT_DEFS.find((a) => a.section === key) || null
}

export function visibleAgents(selectedAnalysts) {
  const pick = selectedAnalysts && selectedAnalysts.length ? selectedAnalysts : null
  return AGENT_DEFS.filter((a) => !a.analyst || !pick || pick.includes(a.analyst))
}

export const STATUS_LABEL = {
  idle: 'Idle',
  processing: 'Processing',
  walking: 'Delivering',
  sending: 'Sending',
  receiving: 'Receiving',
  done: 'Done',
}
