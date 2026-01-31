import { useState } from 'react';
import {
  TrendingUp, TrendingDown, Scale, ChevronDown, ChevronUp,
  MessageSquare, Award
} from 'lucide-react';
import type { DebateHistory } from '../../types/pipeline';

interface DebateViewerProps {
  debate?: DebateHistory;
  isLoading?: boolean;
}

export function DebateViewer({ debate, isLoading }: DebateViewerProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<'bull' | 'bear' | 'history'>('history');

  const hasDebate = debate && (debate.bull_arguments || debate.bear_arguments || debate.full_history);

  // Parse debate rounds from full history
  const parseDebateRounds = (history: string) => {
    const rounds: { speaker: string; content: string }[] = [];
    const lines = history.split('\n');

    let currentSpeaker = '';
    let currentContent: string[] = [];

    lines.forEach(line => {
      if (line.startsWith('Bull') || line.startsWith('Bear') || line.startsWith('Judge')) {
        if (currentSpeaker && currentContent.length > 0) {
          rounds.push({
            speaker: currentSpeaker,
            content: currentContent.join('\n')
          });
        }
        currentSpeaker = line.split(':')[0] || line.split(' ')[0];
        currentContent = [line.substring(line.indexOf(':') + 1).trim()];
      } else if (line.trim()) {
        currentContent.push(line);
      }
    });

    if (currentSpeaker && currentContent.length > 0) {
      rounds.push({
        speaker: currentSpeaker,
        content: currentContent.join('\n')
      });
    }

    return rounds;
  };

  const debateRounds = hasDebate && debate.full_history
    ? parseDebateRounds(debate.full_history)
    : [];

  const getSpeakerStyle = (speaker: string) => {
    if (speaker.toLowerCase().includes('bull')) {
      return {
        bg: 'bg-green-50 dark:bg-green-900/20',
        border: 'border-l-green-500',
        icon: TrendingUp,
        color: 'text-green-600 dark:text-green-400'
      };
    } else if (speaker.toLowerCase().includes('bear')) {
      return {
        bg: 'bg-red-50 dark:bg-red-900/20',
        border: 'border-l-red-500',
        icon: TrendingDown,
        color: 'text-red-600 dark:text-red-400'
      };
    } else {
      return {
        bg: 'bg-blue-50 dark:bg-blue-900/20',
        border: 'border-l-blue-500',
        icon: Scale,
        color: 'text-blue-600 dark:text-blue-400'
      };
    }
  };

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between p-4 bg-gradient-to-r from-green-50 via-slate-50 to-red-50 dark:from-green-900/20 dark:via-slate-800 dark:to-red-900/20 cursor-pointer"
        onClick={() => hasDebate && setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3">
          <div className="flex items-center -space-x-2">
            <div className="p-2 bg-green-100 dark:bg-green-900/40 rounded-full border-2 border-white dark:border-slate-800">
              <TrendingUp className="w-4 h-4 text-green-600" />
            </div>
            <div className="p-2 bg-slate-100 dark:bg-slate-700 rounded-full border-2 border-white dark:border-slate-800 z-10">
              <Scale className="w-4 h-4 text-slate-600 dark:text-slate-300" />
            </div>
            <div className="p-2 bg-red-100 dark:bg-red-900/40 rounded-full border-2 border-white dark:border-slate-800">
              <TrendingDown className="w-4 h-4 text-red-600" />
            </div>
          </div>
          <div>
            <h3 className="font-semibold text-slate-800 dark:text-slate-200">
              Investment Debate
            </h3>
            <p className="text-xs text-slate-500">
              Bull vs Bear Analysis with Research Manager Decision
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
          <div className="flex border-b border-slate-200 dark:border-slate-700">
            <button
              onClick={() => setActiveTab('history')}
              className={`flex-1 px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === 'history'
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50 dark:bg-blue-900/20'
                  : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
              }`}
            >
              <MessageSquare className="w-4 h-4 inline mr-2" />
              Full Debate
            </button>
            <button
              onClick={() => setActiveTab('bull')}
              className={`flex-1 px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === 'bull'
                  ? 'text-green-600 border-b-2 border-green-600 bg-green-50 dark:bg-green-900/20'
                  : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
              }`}
            >
              <TrendingUp className="w-4 h-4 inline mr-2" />
              Bull Case
            </button>
            <button
              onClick={() => setActiveTab('bear')}
              className={`flex-1 px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === 'bear'
                  ? 'text-red-600 border-b-2 border-red-600 bg-red-50 dark:bg-red-900/20'
                  : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
              }`}
            >
              <TrendingDown className="w-4 h-4 inline mr-2" />
              Bear Case
            </button>
          </div>

          {/* Content */}
          <div className="p-4 max-h-96 overflow-y-auto">
            {activeTab === 'history' && (
              <div className="space-y-4">
                {debateRounds.length > 0 ? (
                  debateRounds.map((round, idx) => {
                    const style = getSpeakerStyle(round.speaker);
                    const Icon = style.icon;
                    return (
                      <div
                        key={idx}
                        className={`${style.bg} border-l-4 ${style.border} rounded-r-lg p-3`}
                      >
                        <div className="flex items-center gap-2 mb-2">
                          <Icon className={`w-4 h-4 ${style.color}`} />
                          <span className={`font-medium text-sm ${style.color}`}>
                            {round.speaker}
                          </span>
                        </div>
                        <p className="text-sm text-slate-600 dark:text-slate-400 whitespace-pre-wrap">
                          {round.content}
                        </p>
                      </div>
                    );
                  })
                ) : debate.full_history ? (
                  <pre className="text-sm text-slate-600 dark:text-slate-400 whitespace-pre-wrap">
                    {debate.full_history}
                  </pre>
                ) : (
                  <p className="text-slate-500 text-sm">No debate history available</p>
                )}
              </div>
            )}

            {activeTab === 'bull' && (
              <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <TrendingUp className="w-5 h-5 text-green-600" />
                  <span className="font-medium text-green-700 dark:text-green-300">
                    Bull Analyst Arguments
                  </span>
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-400 whitespace-pre-wrap">
                  {debate.bull_arguments || 'No bull arguments recorded'}
                </p>
              </div>
            )}

            {activeTab === 'bear' && (
              <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <TrendingDown className="w-5 h-5 text-red-600" />
                  <span className="font-medium text-red-700 dark:text-red-300">
                    Bear Analyst Arguments
                  </span>
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-400 whitespace-pre-wrap">
                  {debate.bear_arguments || 'No bear arguments recorded'}
                </p>
              </div>
            )}
          </div>

          {/* Judge Decision */}
          {debate.judge_decision && (
            <div className="border-t border-slate-200 dark:border-slate-700 p-4 bg-blue-50 dark:bg-blue-900/20">
              <div className="flex items-start gap-3">
                <Award className="w-5 h-5 text-blue-600 mt-0.5" />
                <div>
                  <h4 className="font-medium text-blue-700 dark:text-blue-300 mb-1">
                    Research Manager Decision
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

export default DebateViewer;
