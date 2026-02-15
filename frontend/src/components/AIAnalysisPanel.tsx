import { useState } from 'react';
import { Brain, ChevronDown, ChevronUp, TrendingUp, BarChart2, MessageSquare, AlertTriangle, Target } from 'lucide-react';
import type { Decision } from '../types';

interface AIAnalysisPanelProps {
  analysis: string;
  decision?: Decision | null;
  defaultExpanded?: boolean;
}

interface Section {
  title: string;
  content: string;
  icon: typeof Brain;
}

function parseAnalysis(analysis: string): Section[] {
  const sections: Section[] = [];
  const iconMap: Record<string, typeof Brain> = {
    'Summary': Target,
    'Technical Analysis': BarChart2,
    'Fundamental Analysis': TrendingUp,
    'Sentiment': MessageSquare,
    'Risks': AlertTriangle,
  };

  // Split by markdown headers (##)
  const parts = analysis.split(/^## /gm).filter(Boolean);

  for (const part of parts) {
    const lines = part.trim().split('\n');
    const title = lines[0].trim();
    const content = lines.slice(1).join('\n').trim();

    if (title && content) {
      sections.push({
        title,
        content,
        icon: iconMap[title] || Brain,
      });
    }
  }

  // If no sections found, treat the whole thing as a summary
  if (sections.length === 0 && analysis.trim()) {
    sections.push({
      title: 'Analysis',
      content: analysis.trim(),
      icon: Brain,
    });
  }

  return sections;
}

function AnalysisSection({ section, defaultOpen = true }: { section: Section; defaultOpen?: boolean }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const Icon = section.icon;

  return (
    <div className="border-b border-gray-100 dark:border-slate-700 last:border-0">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-gray-50 dark:hover:bg-slate-700/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />
          <span className="font-medium text-sm text-gray-900 dark:text-gray-100">{section.title}</span>
        </div>
        {isOpen ? (
          <ChevronUp className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        )}
      </button>
      {isOpen && (
        <div className="px-4 pb-3 text-sm text-gray-600 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
          {section.content.split('\n').map((line, i) => {
            // Handle bullet points
            if (line.trim().startsWith('- ')) {
              return (
                <div key={i} className="flex gap-2 mt-1">
                  <span className="text-nifty-500">•</span>
                  <span>{line.trim().substring(2)}</span>
                </div>
              );
            }
            return <p key={i} className={line.trim() ? 'mt-1' : 'mt-2'}>{line}</p>;
          })}
        </div>
      )}
    </div>
  );
}

export default function AIAnalysisPanel({
  analysis,
  decision,
  defaultExpanded = false,
}: AIAnalysisPanelProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const sections = parseAnalysis(analysis);

  const decisionGradient = {
    BUY: 'from-green-500 to-emerald-600',
    SELL: 'from-red-500 to-rose-600',
    HOLD: 'from-amber-500 to-orange-600',
  };

  const gradient = decision ? decisionGradient[decision] : 'from-nifty-500 to-nifty-700';

  return (
    <section className="card overflow-hidden">
      {/* Header with gradient */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={`w-full bg-gradient-to-r ${gradient} p-3 text-white flex items-center justify-between`}
      >
        <div className="flex items-center gap-2">
          <Brain className="w-5 h-5" />
          <span className="font-semibold text-sm">AI Analysis</span>
          <span className="text-xs bg-white/20 px-2 py-0.5 rounded-full">
            {sections.length} {sections.length === 1 ? 'section' : 'sections'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-white/80">
            {isExpanded ? 'Click to collapse' : 'Click to expand'}
          </span>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4" />
          ) : (
            <ChevronDown className="w-4 h-4" />
          )}
        </div>
      </button>

      {/* Content */}
      {isExpanded && (
        <div className="bg-white dark:bg-slate-800">
          {sections.map((section, index) => (
            <AnalysisSection
              key={index}
              section={section}
              defaultOpen={index === 0}
            />
          ))}
        </div>
      )}
    </section>
  );
}
