import {
  Database, TrendingUp, Newspaper, Users, FileText,
  MessageSquare, Target, Shield, CheckCircle, Loader2,
  AlertCircle, Clock
} from 'lucide-react';
import type { PipelineStep, PipelineStepStatus } from '../../types/pipeline';

interface PipelineOverviewProps {
  steps: PipelineStep[];
  onStepClick?: (step: PipelineStep) => void;
  compact?: boolean;
}

const STEP_ICONS: Record<string, React.ElementType> = {
  data_collection: Database,
  market_analysis: TrendingUp,
  news_analysis: Newspaper,
  social_analysis: Users,
  fundamentals_analysis: FileText,
  investment_debate: MessageSquare,
  trader_decision: Target,
  risk_debate: Shield,
  final_decision: CheckCircle,
};

const STEP_LABELS: Record<string, string> = {
  data_collection: 'Data Collection',
  market_analysis: 'Market Analysis',
  news_analysis: 'News Analysis',
  social_analysis: 'Social Analysis',
  fundamentals_analysis: 'Fundamentals',
  investment_debate: 'Investment Debate',
  trader_decision: 'Trader Decision',
  risk_debate: 'Risk Assessment',
  final_decision: 'Final Decision',
};

const STATUS_STYLES: Record<PipelineStepStatus, { bg: string; border: string; text: string; icon?: React.ElementType }> = {
  pending: {
    bg: 'bg-slate-100 dark:bg-slate-800',
    border: 'border-slate-300 dark:border-slate-600',
    text: 'text-slate-400 dark:text-slate-500',
    icon: Clock
  },
  running: {
    bg: 'bg-blue-50 dark:bg-blue-900/30',
    border: 'border-blue-400 dark:border-blue-500',
    text: 'text-blue-600 dark:text-blue-400',
    icon: Loader2
  },
  completed: {
    bg: 'bg-green-50 dark:bg-green-900/30',
    border: 'border-green-400 dark:border-green-500',
    text: 'text-green-600 dark:text-green-400',
    icon: CheckCircle
  },
  error: {
    bg: 'bg-red-50 dark:bg-red-900/30',
    border: 'border-red-400 dark:border-red-500',
    text: 'text-red-600 dark:text-red-400',
    icon: AlertCircle
  },
};

// Default pipeline steps when no data is available
const DEFAULT_STEPS: PipelineStep[] = [
  { step_number: 1, step_name: 'data_collection', status: 'pending' },
  { step_number: 2, step_name: 'market_analysis', status: 'pending' },
  { step_number: 3, step_name: 'news_analysis', status: 'pending' },
  { step_number: 4, step_name: 'social_analysis', status: 'pending' },
  { step_number: 5, step_name: 'fundamentals_analysis', status: 'pending' },
  { step_number: 6, step_name: 'investment_debate', status: 'pending' },
  { step_number: 7, step_name: 'trader_decision', status: 'pending' },
  { step_number: 8, step_name: 'risk_debate', status: 'pending' },
  { step_number: 9, step_name: 'final_decision', status: 'pending' },
];

export function PipelineOverview({ steps, onStepClick, compact = false }: PipelineOverviewProps) {
  const displaySteps = steps.length > 0 ? steps : DEFAULT_STEPS;

  const completedCount = displaySteps.filter(s => s.status === 'completed').length;
  const totalSteps = displaySteps.length;
  const progress = Math.round((completedCount / totalSteps) * 100);

  if (compact) {
    return (
      <div className="flex items-center gap-1">
        {displaySteps.map((step, index) => {
          const styles = STATUS_STYLES[step.status];
          return (
            <div
              key={step.step_number}
              className={`w-2 h-2 rounded-full ${styles.bg} ${styles.border} border`}
              title={`${STEP_LABELS[step.step_name] || step.step_name}: ${step.status}`}
            />
          );
        })}
        <span className="text-xs text-slate-500 ml-1">{progress}%</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Progress bar */}
      <div className="flex items-center gap-3">
        <div className="flex-1 h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-blue-500 to-green-500 transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
        <span className="text-sm font-medium text-slate-600 dark:text-slate-400">
          {completedCount}/{totalSteps}
        </span>
      </div>

      {/* Pipeline steps */}
      <div className="flex flex-wrap gap-2">
        {displaySteps.map((step, index) => {
          const StepIcon = STEP_ICONS[step.step_name] || Database;
          const styles = STATUS_STYLES[step.status];
          const StatusIcon = styles.icon;
          const label = STEP_LABELS[step.step_name] || step.step_name;

          return (
            <button
              key={step.step_number}
              onClick={() => onStepClick?.(step)}
              className={`
                flex items-center gap-2 px-3 py-2 rounded-lg border-2 transition-all
                ${styles.bg} ${styles.border} ${styles.text}
                hover:scale-105 hover:shadow-md
                ${onStepClick ? 'cursor-pointer' : 'cursor-default'}
              `}
            >
              <div className="relative">
                <StepIcon className="w-4 h-4" />
                {StatusIcon && step.status === 'running' && (
                  <Loader2 className="w-3 h-3 absolute -top-1 -right-1 animate-spin" />
                )}
              </div>
              <span className="text-xs font-medium">{label}</span>
              {step.duration_ms && (
                <span className="text-xs opacity-60">
                  {(step.duration_ms / 1000).toFixed(1)}s
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default PipelineOverview;
