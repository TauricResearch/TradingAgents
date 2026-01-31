import { useState } from 'react';
import {
  TrendingUp, Newspaper, Users, FileText,
  ChevronDown, ChevronUp, Database, Clock, CheckCircle
} from 'lucide-react';
import type { AgentReport, AgentType } from '../../types/pipeline';
import { AGENT_METADATA } from '../../types/pipeline';

interface AgentReportCardProps {
  agentType: AgentType;
  report?: AgentReport;
  isLoading?: boolean;
}

const AGENT_ICONS: Record<AgentType, React.ElementType> = {
  market: TrendingUp,
  news: Newspaper,
  social_media: Users,
  fundamentals: FileText,
};

const AGENT_COLORS: Record<AgentType, { bg: string; border: string; text: string; accent: string }> = {
  market: {
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    border: 'border-blue-200 dark:border-blue-800',
    text: 'text-blue-700 dark:text-blue-300',
    accent: 'bg-blue-500'
  },
  news: {
    bg: 'bg-purple-50 dark:bg-purple-900/20',
    border: 'border-purple-200 dark:border-purple-800',
    text: 'text-purple-700 dark:text-purple-300',
    accent: 'bg-purple-500'
  },
  social_media: {
    bg: 'bg-pink-50 dark:bg-pink-900/20',
    border: 'border-pink-200 dark:border-pink-800',
    text: 'text-pink-700 dark:text-pink-300',
    accent: 'bg-pink-500'
  },
  fundamentals: {
    bg: 'bg-green-50 dark:bg-green-900/20',
    border: 'border-green-200 dark:border-green-800',
    text: 'text-green-700 dark:text-green-300',
    accent: 'bg-green-500'
  },
};

export function AgentReportCard({ agentType, report, isLoading }: AgentReportCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const Icon = AGENT_ICONS[agentType];
  const colors = AGENT_COLORS[agentType];
  const metadata = AGENT_METADATA[agentType];
  const hasReport = report && report.report_content;

  // Parse markdown-like content into sections
  const parseContent = (content: string) => {
    const lines = content.split('\n');
    const sections: { title: string; content: string[] }[] = [];
    let currentSection: { title: string; content: string[] } | null = null;

    lines.forEach(line => {
      if (line.startsWith('##') || line.startsWith('**')) {
        if (currentSection) {
          sections.push(currentSection);
        }
        currentSection = {
          title: line.replace(/^#+\s*/, '').replace(/\*\*/g, ''),
          content: []
        };
      } else if (currentSection && line.trim()) {
        currentSection.content.push(line);
      }
    });

    if (currentSection) {
      sections.push(currentSection);
    }

    return sections;
  };

  const sections = hasReport ? parseContent(report.report_content) : [];
  const previewText = hasReport
    ? report.report_content.slice(0, 200).replace(/[#*]/g, '') + '...'
    : 'No analysis available';

  return (
    <div className={`rounded-xl border ${colors.border} ${colors.bg} overflow-hidden`}>
      {/* Header */}
      <div
        className={`flex items-center justify-between p-4 cursor-pointer hover:opacity-90 transition-opacity`}
        onClick={() => hasReport && setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${colors.accent} bg-opacity-20`}>
            <Icon className={`w-5 h-5 ${colors.text}`} />
          </div>
          <div>
            <h3 className={`font-semibold ${colors.text}`}>{metadata.label}</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {metadata.description}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {hasReport ? (
            <CheckCircle className="w-4 h-4 text-green-500" />
          ) : isLoading ? (
            <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin opacity-50" />
          ) : (
            <Clock className="w-4 h-4 text-slate-400" />
          )}

          {hasReport && (
            isExpanded ? (
              <ChevronUp className="w-5 h-5 text-slate-400" />
            ) : (
              <ChevronDown className="w-5 h-5 text-slate-400" />
            )
          )}
        </div>
      </div>

      {/* Preview (collapsed) */}
      {!isExpanded && hasReport && (
        <div className="px-4 pb-4">
          <p className="text-sm text-slate-600 dark:text-slate-400 line-clamp-2">
            {previewText}
          </p>
        </div>
      )}

      {/* Expanded content */}
      {isExpanded && hasReport && (
        <div className="border-t border-slate-200 dark:border-slate-700">
          {/* Data sources */}
          {report.data_sources_used && report.data_sources_used.length > 0 && (
            <div className="px-4 py-2 bg-slate-100 dark:bg-slate-800/50 flex items-center gap-2 flex-wrap">
              <Database className="w-3 h-3 text-slate-400" />
              <span className="text-xs text-slate-500">Sources:</span>
              {report.data_sources_used.map((source, idx) => (
                <span
                  key={idx}
                  className="px-2 py-0.5 bg-slate-200 dark:bg-slate-700 rounded text-xs text-slate-600 dark:text-slate-300"
                >
                  {source}
                </span>
              ))}
            </div>
          )}

          {/* Report content */}
          <div className="p-4 space-y-4 max-h-96 overflow-y-auto">
            {sections.length > 0 ? (
              sections.map((section, idx) => (
                <div key={idx} className="space-y-1">
                  <h4 className="font-medium text-sm text-slate-700 dark:text-slate-300">
                    {section.title}
                  </h4>
                  <div className="text-sm text-slate-600 dark:text-slate-400 space-y-1">
                    {section.content.map((line, lineIdx) => (
                      <p key={lineIdx}>{line}</p>
                    ))}
                  </div>
                </div>
              ))
            ) : (
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <pre className="whitespace-pre-wrap text-sm text-slate-600 dark:text-slate-400">
                  {report.report_content}
                </pre>
              </div>
            )}
          </div>

          {/* Timestamp */}
          {report.created_at && (
            <div className="px-4 py-2 border-t border-slate-200 dark:border-slate-700 flex items-center gap-2">
              <Clock className="w-3 h-3 text-slate-400" />
              <span className="text-xs text-slate-500">
                Generated: {new Date(report.created_at).toLocaleString()}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default AgentReportCard;
