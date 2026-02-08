/**
 * TypeScript types for the analysis pipeline visualization
 */

// Agent types that perform analysis
export type AgentType = 'market' | 'news' | 'social_media' | 'fundamentals';

// Debate types in the system
export type DebateType = 'investment' | 'risk';

// Pipeline step status
export type PipelineStepStatus = 'pending' | 'running' | 'completed' | 'error';

/**
 * Individual agent's analysis report
 */
export interface AgentReport {
  agent_type: AgentType;
  report_content: string;
  data_sources_used: string[];
  created_at?: string;
}

/**
 * Map of agent reports by type
 */
export interface AgentReportsMap {
  market?: AgentReport;
  news?: AgentReport;
  social_media?: AgentReport;
  fundamentals?: AgentReport;
}

/**
 * Debate history for investment or risk debates
 */
export interface DebateHistory {
  debate_type: DebateType;
  // Investment debate fields
  bull_arguments?: string;
  bear_arguments?: string;
  // Risk debate fields
  risky_arguments?: string;
  safe_arguments?: string;
  neutral_arguments?: string;
  // Common fields
  judge_decision?: string;
  full_history?: string;
  created_at?: string;
}

/**
 * Map of debates by type
 */
export interface DebatesMap {
  investment?: DebateHistory;
  risk?: DebateHistory;
}

/**
 * Structured details for a pipeline step (prompt, response, tool calls)
 */
export interface StepDetails {
  system_prompt?: string;
  user_prompt?: string;
  response?: string;
  tool_calls?: Array<{ name: string; args?: string; result_preview?: string }>;
}

/**
 * Single step in the analysis pipeline
 */
export interface PipelineStep {
  step_number: number;
  step_name: string;
  status: PipelineStepStatus;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  output_summary?: string;
  step_details?: StepDetails;
}

/**
 * Log entry for a data source fetch
 */
export interface DataSourceLog {
  source_type: string;
  source_name: string;
  method?: string;
  args?: string;
  data_fetched?: Record<string, unknown> | string;
  fetch_timestamp?: string;
  success: boolean;
  error_message?: string;
}

/**
 * Complete pipeline data for a single stock analysis
 */
export interface FullPipelineData {
  date: string;
  symbol: string;
  agent_reports: AgentReportsMap;
  debates: DebatesMap;
  pipeline_steps: PipelineStep[];
  data_sources: DataSourceLog[];
  status?: 'complete' | 'in_progress' | 'no_data';
}

/**
 * Summary of pipeline for a single stock (used in list views)
 */
export interface PipelineSummary {
  symbol: string;
  pipeline_steps: { step_name: string; status: PipelineStepStatus }[];
  agent_reports_count: number;
  has_debates: boolean;
}

/**
 * API response types
 */
export interface PipelineDataResponse extends FullPipelineData {}

export interface AgentReportsResponse {
  date: string;
  symbol: string;
  reports: AgentReportsMap;
  count: number;
}

export interface DebateHistoryResponse {
  date: string;
  symbol: string;
  debates: DebatesMap;
}

export interface DataSourcesResponse {
  date: string;
  symbol: string;
  data_sources: DataSourceLog[];
  count: number;
}

export interface PipelineSummaryResponse {
  date: string;
  stocks: PipelineSummary[];
  count: number;
}

/**
 * Pipeline step definitions (for UI rendering)
 */
export const PIPELINE_STEPS = [
  { number: 1, name: 'data_collection', label: 'Data Collection', icon: 'Database' },
  { number: 2, name: 'market_analysis', label: 'Market Analysis', icon: 'TrendingUp' },
  { number: 3, name: 'news_analysis', label: 'News Analysis', icon: 'Newspaper' },
  { number: 4, name: 'social_analysis', label: 'Social Analysis', icon: 'Users' },
  { number: 5, name: 'fundamentals_analysis', label: 'Fundamentals', icon: 'FileText' },
  { number: 6, name: 'investment_debate', label: 'Investment Debate', icon: 'MessageSquare' },
  { number: 7, name: 'trader_decision', label: 'Trader Decision', icon: 'Target' },
  { number: 8, name: 'risk_debate', label: 'Risk Assessment', icon: 'Shield' },
  { number: 9, name: 'final_decision', label: 'Final Decision', icon: 'CheckCircle' },
] as const;

/**
 * Agent metadata for UI rendering
 */
export const AGENT_METADATA: Record<AgentType, { label: string; icon: string; color: string; description: string }> = {
  market: {
    label: 'Market Analyst',
    icon: 'TrendingUp',
    color: 'blue',
    description: 'Analyzes technical indicators, price trends, and market patterns'
  },
  news: {
    label: 'News Analyst',
    icon: 'Newspaper',
    color: 'purple',
    description: 'Analyzes company news, macroeconomic trends, and market events'
  },
  social_media: {
    label: 'Social Media Analyst',
    icon: 'Users',
    color: 'pink',
    description: 'Analyzes social sentiment, Reddit discussions, and public perception'
  },
  fundamentals: {
    label: 'Fundamentals Analyst',
    icon: 'FileText',
    color: 'green',
    description: 'Analyzes financial statements, ratios, and company health'
  }
};

/**
 * Debate role metadata for UI rendering
 */
export const DEBATE_ROLES = {
  investment: {
    bull: { label: 'Bull Analyst', color: 'green', icon: 'TrendingUp' },
    bear: { label: 'Bear Analyst', color: 'red', icon: 'TrendingDown' },
    judge: { label: 'Research Manager', color: 'blue', icon: 'Scale' }
  },
  risk: {
    risky: { label: 'Aggressive Analyst', color: 'red', icon: 'Zap' },
    safe: { label: 'Conservative Analyst', color: 'green', icon: 'Shield' },
    neutral: { label: 'Neutral Analyst', color: 'gray', icon: 'Scale' },
    judge: { label: 'Risk Manager', color: 'blue', icon: 'ShieldCheck' }
  }
} as const;

/**
 * Maps each pipeline step to the IDs of steps whose output is forwarded as context.
 * Steps 1-4 are independent (no forwarded context).
 */
export const STEP_INPUT_SOURCES: Record<string, string[]> = {
  market_analyst: [],
  social_analyst: [],
  news_analyst: [],
  fundamentals_analyst: [],
  bull_researcher: ['market_analyst', 'social_analyst', 'news_analyst', 'fundamentals_analyst'],
  bear_researcher: ['market_analyst', 'social_analyst', 'news_analyst', 'fundamentals_analyst'],
  research_manager: ['bull_researcher', 'bear_researcher', 'market_analyst', 'social_analyst', 'news_analyst', 'fundamentals_analyst'],
  trader: ['research_manager', 'market_analyst', 'social_analyst', 'news_analyst', 'fundamentals_analyst'],
  aggressive_analyst: ['trader', 'market_analyst', 'social_analyst', 'news_analyst', 'fundamentals_analyst'],
  conservative_analyst: ['trader', 'market_analyst', 'social_analyst', 'news_analyst', 'fundamentals_analyst'],
  neutral_analyst: ['trader', 'market_analyst', 'social_analyst', 'news_analyst', 'fundamentals_analyst'],
  risk_manager: ['aggressive_analyst', 'conservative_analyst', 'neutral_analyst', 'trader', 'market_analyst', 'social_analyst', 'news_analyst', 'fundamentals_analyst'],
};

// ============================================================
// Flowchart types for the 12-step visual pipeline debug view
// ============================================================

export type FlowchartPhase = 'data_analysis' | 'investment_debate' | 'trading' | 'risk_debate';

export interface FlowchartStepDef {
  number: number;
  id: string;
  label: string;
  icon: string;
  phase: FlowchartPhase;
  phaseLabel: string;
  agentType?: AgentType;
  debateType?: DebateType;
  debateRole?: string;
  color: string;
}

export const FLOWCHART_STEPS: FlowchartStepDef[] = [
  { number: 1,  id: 'market_analyst',       label: 'Market Analyst',       icon: 'TrendingUp',   phase: 'data_analysis',      phaseLabel: 'Data & Analysis',    agentType: 'market',       color: 'blue' },
  { number: 2,  id: 'social_analyst',       label: 'Social Media Analyst', icon: 'Users',         phase: 'data_analysis',      phaseLabel: 'Data & Analysis',    agentType: 'social_media', color: 'pink' },
  { number: 3,  id: 'news_analyst',         label: 'News Analyst',         icon: 'Newspaper',     phase: 'data_analysis',      phaseLabel: 'Data & Analysis',    agentType: 'news',         color: 'purple' },
  { number: 4,  id: 'fundamentals_analyst', label: 'Fundamentals Analyst', icon: 'FileText',      phase: 'data_analysis',      phaseLabel: 'Data & Analysis',    agentType: 'fundamentals', color: 'emerald' },
  { number: 5,  id: 'bull_researcher',      label: 'Bull Researcher',      icon: 'TrendingUp',   phase: 'investment_debate',  phaseLabel: 'Investment Debate',  debateType: 'investment', debateRole: 'bull',    color: 'green' },
  { number: 6,  id: 'bear_researcher',      label: 'Bear Researcher',      icon: 'TrendingDown',  phase: 'investment_debate',  phaseLabel: 'Investment Debate',  debateType: 'investment', debateRole: 'bear',    color: 'red' },
  { number: 7,  id: 'research_manager',     label: 'Research Manager',     icon: 'Scale',         phase: 'investment_debate',  phaseLabel: 'Investment Debate',  debateType: 'investment', debateRole: 'judge',   color: 'violet' },
  { number: 8,  id: 'trader',               label: 'Trader',               icon: 'Target',        phase: 'trading',            phaseLabel: 'Trading',            color: 'amber' },
  { number: 9,  id: 'aggressive_analyst',   label: 'Aggressive Analyst',   icon: 'Zap',           phase: 'risk_debate',        phaseLabel: 'Risk Debate',        debateType: 'risk', debateRole: 'risky',        color: 'orange' },
  { number: 10, id: 'conservative_analyst', label: 'Conservative Analyst', icon: 'Shield',        phase: 'risk_debate',        phaseLabel: 'Risk Debate',        debateType: 'risk', debateRole: 'safe',         color: 'sky' },
  { number: 11, id: 'neutral_analyst',      label: 'Neutral Analyst',      icon: 'Scale',         phase: 'risk_debate',        phaseLabel: 'Risk Debate',        debateType: 'risk', debateRole: 'neutral',      color: 'slate' },
  { number: 12, id: 'risk_manager',         label: 'Risk Manager',         icon: 'ShieldCheck',   phase: 'risk_debate',        phaseLabel: 'Risk Debate',        debateType: 'risk', debateRole: 'judge',        color: 'indigo' },
];

export interface FlowchartNodeData extends FlowchartStepDef {
  status: PipelineStepStatus;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  output_summary?: string;
  step_details?: StepDetails;
  agentReport?: AgentReport;
  debateContent?: string;
}

/** Phase metadata for UI rendering */
export const PHASE_META: Record<FlowchartPhase, { label: string; number: number; color: string; borderColor: string; bgColor: string; textColor: string }> = {
  data_analysis:      { label: 'Data & Analysis',    number: 1, color: 'blue',   borderColor: 'border-l-blue-500',   bgColor: 'bg-blue-500/5',   textColor: 'text-blue-600 dark:text-blue-400' },
  investment_debate:  { label: 'Investment Debate',  number: 2, color: 'violet', borderColor: 'border-l-violet-500', bgColor: 'bg-violet-500/5', textColor: 'text-violet-600 dark:text-violet-400' },
  trading:            { label: 'Trading',            number: 3, color: 'amber',  borderColor: 'border-l-amber-500',  bgColor: 'bg-amber-500/5',  textColor: 'text-amber-600 dark:text-amber-400' },
  risk_debate:        { label: 'Risk Assessment',    number: 4, color: 'red',    borderColor: 'border-l-red-500',    bgColor: 'bg-red-500/5',    textColor: 'text-red-600 dark:text-red-400' },
};

/**
 * Map backend FullPipelineData (9 grouped steps) to 12 individual FlowchartNodeData entries.
 * When the backend provides 12 granular steps, they map directly by step name.
 */
export function mapPipelineToFlowchart(data: FullPipelineData | null): FlowchartNodeData[] {
  if (!data) {
    return FLOWCHART_STEPS.map(step => ({ ...step, status: 'pending' as PipelineStepStatus }));
  }

  const stepsByName: Record<string, PipelineStep> = {};
  for (const ps of data.pipeline_steps || []) {
    stepsByName[ps.step_name] = ps;
  }

  // Mapping from flowchart step id to possible backend step names
  const STEP_NAME_MAP: Record<string, string[]> = {
    market_analyst:       ['market_analyst', 'market_analysis'],
    social_analyst:       ['social_analyst', 'social_analysis', 'social_media_analyst'],
    news_analyst:         ['news_analyst', 'news_analysis'],
    fundamentals_analyst: ['fundamentals_analyst', 'fundamental_analysis', 'fundamentals_analysis'],
    bull_researcher:      ['bull_researcher', 'bull_research', 'investment_debate'],
    bear_researcher:      ['bear_researcher', 'bear_research', 'investment_debate'],
    research_manager:     ['research_manager', 'investment_debate'],
    trader:               ['trader', 'trader_decision'],
    aggressive_analyst:   ['aggressive_analyst', 'aggressive_analysis', 'risk_debate'],
    conservative_analyst: ['conservative_analyst', 'conservative_analysis', 'risk_debate'],
    neutral_analyst:      ['neutral_analyst', 'neutral_analysis', 'risk_debate'],
    risk_manager:         ['risk_manager', 'final_decision'],
  };

  return FLOWCHART_STEPS.map(step => {
    // Find matching backend step
    const candidates = STEP_NAME_MAP[step.id] || [step.id];
    let matchedStep: PipelineStep | undefined;
    for (const name of candidates) {
      if (stepsByName[name]) {
        matchedStep = stepsByName[name];
        break;
      }
    }

    // Get linked content
    let agentReport: AgentReport | undefined;
    if (step.agentType && data.agent_reports) {
      agentReport = data.agent_reports[step.agentType];
    }

    let debateContent: string | undefined;
    if (step.debateType && step.debateRole && data.debates) {
      const debate = data.debates[step.debateType];
      if (debate) {
        if (step.debateRole === 'bull') debateContent = debate.bull_arguments;
        else if (step.debateRole === 'bear') debateContent = debate.bear_arguments;
        else if (step.debateRole === 'risky') debateContent = debate.risky_arguments;
        else if (step.debateRole === 'safe') debateContent = debate.safe_arguments;
        else if (step.debateRole === 'neutral') debateContent = debate.neutral_arguments;
        else if (step.debateRole === 'judge') debateContent = debate.judge_decision;
      }
    }

    return {
      ...step,
      status: matchedStep?.status || 'pending',
      started_at: matchedStep?.started_at,
      completed_at: matchedStep?.completed_at,
      duration_ms: matchedStep?.duration_ms,
      output_summary: matchedStep?.output_summary,
      step_details: matchedStep?.step_details,
      agentReport,
      debateContent,
    };
  });
}

/**
 * Get human-readable labels for a step's input sources.
 */
export function getInputSourceLabels(stepId: string): { id: string; label: string }[] {
  const sources = STEP_INPUT_SOURCES[stepId] || [];
  return sources.map(id => {
    const step = FLOWCHART_STEPS.find(s => s.id === id);
    return { id, label: step?.label || id };
  });
}
