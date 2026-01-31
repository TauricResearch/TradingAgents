import { useState } from 'react';
import {
  Zap, Shield, Scale, ChevronDown, ChevronUp,
  ShieldCheck, AlertTriangle
} from 'lucide-react';
import type { DebateHistory } from '../../types/pipeline';

interface RiskDebateViewerProps {
  debate?: DebateHistory;
  isLoading?: boolean;
}

export function RiskDebateViewer({ debate, isLoading }: RiskDebateViewerProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<'all' | 'risky' | 'safe' | 'neutral'>('all');

  const hasDebate = debate && (
    debate.risky_arguments ||
    debate.safe_arguments ||
    debate.neutral_arguments ||
    debate.full_history
  );

  const ROLE_STYLES = {
    risky: {
      bg: 'bg-red-50 dark:bg-red-900/20',
      border: 'border-l-red-500',
      icon: Zap,
      color: 'text-red-600 dark:text-red-400',
      label: 'Aggressive Analyst'
    },
    safe: {
      bg: 'bg-green-50 dark:bg-green-900/20',
      border: 'border-l-green-500',
      icon: Shield,
      color: 'text-green-600 dark:text-green-400',
      label: 'Conservative Analyst'
    },
    neutral: {
      bg: 'bg-slate-50 dark:bg-slate-800/50',
      border: 'border-l-slate-500',
      icon: Scale,
      color: 'text-slate-600 dark:text-slate-400',
      label: 'Neutral Analyst'
    }
  };

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between p-4 bg-gradient-to-r from-red-50 via-slate-50 to-green-50 dark:from-red-900/20 dark:via-slate-800 dark:to-green-900/20 cursor-pointer"
        onClick={() => hasDebate && setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3">
          <div className="flex items-center -space-x-2">
            <div className="p-2 bg-red-100 dark:bg-red-900/40 rounded-full border-2 border-white dark:border-slate-800">
              <Zap className="w-4 h-4 text-red-600" />
            </div>
            <div className="p-2 bg-slate-100 dark:bg-slate-700 rounded-full border-2 border-white dark:border-slate-800 z-10">
              <Scale className="w-4 h-4 text-slate-600 dark:text-slate-300" />
            </div>
            <div className="p-2 bg-green-100 dark:bg-green-900/40 rounded-full border-2 border-white dark:border-slate-800">
              <Shield className="w-4 h-4 text-green-600" />
            </div>
          </div>
          <div>
            <h3 className="font-semibold text-slate-800 dark:text-slate-200">
              Risk Assessment Debate
            </h3>
            <p className="text-xs text-slate-500">
              Aggressive vs Conservative vs Neutral with Risk Manager Decision
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {hasDebate ? (
            <span className="px-2 py-1 bg-green-100 dark:bg-green-900/40 rounded text-xs text-green-700 dark:text-green-300">
              Complete
            </span>
          ) : isLoading ? (
            <div className="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
          ) : (
            <span className="px-2 py-1 bg-slate-100 dark:bg-slate-800 rounded text-xs text-slate-500">
              No Data
            </span>
          )}
          {hasDebate && (
            isExpanded ? <ChevronUp className="w-5 h-5 text-slate-400" /> : <ChevronDown className="w-5 h-5 text-slate-400" />
          )}
        </div>
      </div>

      {/* Expanded content */}
      {isExpanded && hasDebate && (
        <div className="border-t border-slate-200 dark:border-slate-700">
          {/* Tabs */}
          <div className="flex border-b border-slate-200 dark:border-slate-700 overflow-x-auto">
            <button
              onClick={() => setActiveTab('all')}
              className={`flex-1 min-w-fit px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === 'all'
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50 dark:bg-blue-900/20'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              All Views
            </button>
            <button
              onClick={() => setActiveTab('risky')}
              className={`flex-1 min-w-fit px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === 'risky'
                  ? 'text-red-600 border-b-2 border-red-600 bg-red-50 dark:bg-red-900/20'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              <Zap className="w-4 h-4 inline mr-1" />
              Aggressive
            </button>
            <button
              onClick={() => setActiveTab('neutral')}
              className={`flex-1 min-w-fit px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === 'neutral'
                  ? 'text-slate-600 border-b-2 border-slate-600 bg-slate-50 dark:bg-slate-900/20'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              <Scale className="w-4 h-4 inline mr-1" />
              Neutral
            </button>
            <button
              onClick={() => setActiveTab('safe')}
              className={`flex-1 min-w-fit px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === 'safe'
                  ? 'text-green-600 border-b-2 border-green-600 bg-green-50 dark:bg-green-900/20'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              <Shield className="w-4 h-4 inline mr-1" />
              Conservative
            </button>
          </div>

          {/* Content */}
          <div className="p-4 max-h-96 overflow-y-auto">
            {activeTab === 'all' && (
              <div className="grid gap-4 md:grid-cols-3">
                {/* Aggressive */}
                <div className={`${ROLE_STYLES.risky.bg} rounded-lg p-3 border-l-4 ${ROLE_STYLES.risky.border}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <Zap className={`w-4 h-4 ${ROLE_STYLES.risky.color}`} />
                    <span className={`font-medium text-sm ${ROLE_STYLES.risky.color}`}>
                      {ROLE_STYLES.risky.label}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-6">
                    {debate.risky_arguments || 'No arguments recorded'}
                  </p>
                </div>

                {/* Neutral */}
                <div className={`${ROLE_STYLES.neutral.bg} rounded-lg p-3 border-l-4 ${ROLE_STYLES.neutral.border}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <Scale className={`w-4 h-4 ${ROLE_STYLES.neutral.color}`} />
                    <span className={`font-medium text-sm ${ROLE_STYLES.neutral.color}`}>
                      {ROLE_STYLES.neutral.label}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-6">
                    {debate.neutral_arguments || 'No arguments recorded'}
                  </p>
                </div>

                {/* Conservative */}
                <div className={`${ROLE_STYLES.safe.bg} rounded-lg p-3 border-l-4 ${ROLE_STYLES.safe.border}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <Shield className={`w-4 h-4 ${ROLE_STYLES.safe.color}`} />
                    <span className={`font-medium text-sm ${ROLE_STYLES.safe.color}`}>
                      {ROLE_STYLES.safe.label}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-6">
                    {debate.safe_arguments || 'No arguments recorded'}
                  </p>
                </div>
              </div>
            )}

            {activeTab === 'risky' && (
              <div className={`${ROLE_STYLES.risky.bg} rounded-lg p-4`}>
                <div className="flex items-center gap-2 mb-3">
                  <Zap className={`w-5 h-5 ${ROLE_STYLES.risky.color}`} />
                  <span className={`font-medium ${ROLE_STYLES.risky.color}`}>
                    {ROLE_STYLES.risky.label}
                  </span>
                  <AlertTriangle className="w-4 h-4 text-amber-500 ml-auto" />
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-400 whitespace-pre-wrap">
                  {debate.risky_arguments || 'No aggressive arguments recorded'}
                </p>
              </div>
            )}

            {activeTab === 'neutral' && (
              <div className={`${ROLE_STYLES.neutral.bg} rounded-lg p-4`}>
                <div className="flex items-center gap-2 mb-3">
                  <Scale className={`w-5 h-5 ${ROLE_STYLES.neutral.color}`} />
                  <span className={`font-medium ${ROLE_STYLES.neutral.color}`}>
                    {ROLE_STYLES.neutral.label}
                  </span>
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-400 whitespace-pre-wrap">
                  {debate.neutral_arguments || 'No neutral arguments recorded'}
                </p>
              </div>
            )}

            {activeTab === 'safe' && (
              <div className={`${ROLE_STYLES.safe.bg} rounded-lg p-4`}>
                <div className="flex items-center gap-2 mb-3">
                  <Shield className={`w-5 h-5 ${ROLE_STYLES.safe.color}`} />
                  <span className={`font-medium ${ROLE_STYLES.safe.color}`}>
                    {ROLE_STYLES.safe.label}
                  </span>
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-400 whitespace-pre-wrap">
                  {debate.safe_arguments || 'No conservative arguments recorded'}
                </p>
              </div>
            )}
          </div>

          {/* Risk Manager Decision */}
          {debate.judge_decision && (
            <div className="border-t border-slate-200 dark:border-slate-700 p-4 bg-blue-50 dark:bg-blue-900/20">
              <div className="flex items-start gap-3">
                <ShieldCheck className="w-5 h-5 text-blue-600 mt-0.5" />
                <div>
                  <h4 className="font-medium text-blue-700 dark:text-blue-300 mb-1">
                    Risk Manager Decision
                  </h4>
                  <p className="text-sm text-slate-600 dark:text-slate-400 whitespace-pre-wrap">
                    {debate.judge_decision}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default RiskDebateViewer;
