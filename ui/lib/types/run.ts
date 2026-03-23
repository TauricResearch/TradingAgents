export type AgentStep =
  | 'market_analyst'
  | 'news_analyst'
  | 'fundamentals_analyst'
  | 'social_analyst'
  | 'bull_researcher'
  | 'bear_researcher'
  | 'research_manager'
  | 'trader'
  | 'aggressive_analyst'
  | 'conservative_analyst'
  | 'neutral_analyst'
  | 'risk_judge'

export const AGENT_STEPS: AgentStep[] = [
  'market_analyst', 'news_analyst', 'fundamentals_analyst', 'social_analyst',
  'bull_researcher', 'bear_researcher', 'research_manager',
  'trader',
  'aggressive_analyst', 'conservative_analyst', 'neutral_analyst', 'risk_judge',
]

export const AGENT_STEP_LABELS: Record<AgentStep, string> = {
  market_analyst:       'Market',
  news_analyst:         'News',
  fundamentals_analyst: 'Fundamentals',
  social_analyst:       'Social',
  bull_researcher:      'Bull Researcher',
  bear_researcher:      'Bear Researcher',
  research_manager:     'Research Manager',
  trader:               'Trader',
  aggressive_analyst:   'Aggressive',
  conservative_analyst: 'Conservative',
  neutral_analyst:      'Neutral',
  risk_judge:           'Risk Judge',
}

export const STEP_PHASE: Record<AgentStep, 'analysts' | 'researchers' | 'trader' | 'risk'> = {
  market_analyst:       'analysts',
  news_analyst:         'analysts',
  fundamentals_analyst: 'analysts',
  social_analyst:       'analysts',
  bull_researcher:      'researchers',
  bear_researcher:      'researchers',
  research_manager:     'researchers',
  trader:               'trader',
  aggressive_analyst:   'risk',
  conservative_analyst: 'risk',
  neutral_analyst:      'risk',
  risk_judge:           'risk',
}

export type RunStatus = 'queued' | 'running' | 'complete' | 'error'

export type RunConfig = {
  ticker: string
  date: string
  llm_provider: string
  deep_think_llm: string
  quick_think_llm: string
  max_debate_rounds: number
  max_risk_discuss_rounds: number
  enabled_analysts?: string[]
}

export type RunSummary = {
  id: string
  ticker: string
  date: string
  status: RunStatus
  decision: 'BUY' | 'SELL' | 'HOLD' | null
  created_at: string
}
