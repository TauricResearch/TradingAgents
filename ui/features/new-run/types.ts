export type NewRunFormState = {
  ticker: string
  date: string
  llm_provider: string
  deep_think_llm: string
  quick_think_llm: string
  max_debate_rounds: number
  max_risk_discuss_rounds: number
  enabled_analysts: string[]
}

export const DEFAULT_FORM: NewRunFormState = {
  ticker: '',
  date: '',
  llm_provider: 'openai',
  deep_think_llm: 'gpt-5.2',
  quick_think_llm: 'gpt-5-mini',
  max_debate_rounds: 1,
  max_risk_discuss_rounds: 1,
  enabled_analysts: ['market', 'news', 'fundamentals', 'social'],
}
