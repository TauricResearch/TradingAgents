import { useState } from 'react';
import { ChevronDown, ChevronUp, Database, BarChart2, MessageSquare, Sparkles, Brain, TrendingUp, Shield } from 'lucide-react';

interface HowItWorksProps {
  collapsed?: boolean;
}

const agents = [
  {
    name: 'Market Data',
    icon: Database,
    color: 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400',
    description: 'Real-time price data, volume, and market indicators from NSE',
  },
  {
    name: 'Technical Analyst',
    icon: BarChart2,
    color: 'bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400',
    description: 'RSI, MACD, moving averages, and chart pattern analysis',
  },
  {
    name: 'Fundamental Analyst',
    icon: TrendingUp,
    color: 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400',
    description: 'Earnings, P/E ratios, revenue growth, and financial health',
  },
  {
    name: 'Sentiment Analyst',
    icon: MessageSquare,
    color: 'bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400',
    description: 'News sentiment, social media trends, and analyst ratings',
  },
  {
    name: 'Risk Manager',
    icon: Shield,
    color: 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400',
    description: 'Volatility assessment, sector risk, and position sizing',
  },
  {
    name: 'AI Debate',
    icon: Brain,
    color: 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400',
    description: 'Agents debate and challenge each other to reach consensus',
  },
];

export default function HowItWorks({ collapsed = true }: HowItWorksProps) {
  const [isExpanded, setIsExpanded] = useState(!collapsed);

  return (
    <section className="card overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white"
      >
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5" />
          <span className="font-semibold text-sm">Powered by AI Agents</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-white/80">
            {isExpanded ? 'Hide details' : 'Learn how it works'}
          </span>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4" />
          ) : (
            <ChevronDown className="w-4 h-4" />
          )}
        </div>
      </button>

      {isExpanded && (
        <div className="p-4 bg-white dark:bg-slate-800">
          {/* Flow diagram */}
          <div className="flex items-center justify-center gap-2 mb-4 text-xs text-gray-500 dark:text-gray-400">
            <span className="px-2 py-1 bg-gray-100 dark:bg-slate-700 rounded">Data</span>
            <span>→</span>
            <span className="px-2 py-1 bg-gray-100 dark:bg-slate-700 rounded">Analysis</span>
            <span>→</span>
            <span className="px-2 py-1 bg-gray-100 dark:bg-slate-700 rounded">Debate</span>
            <span>→</span>
            <span className="px-2 py-1 bg-nifty-100 dark:bg-nifty-900/30 rounded text-nifty-700 dark:text-nifty-400 font-medium">Decision</span>
          </div>

          {/* Agents grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {agents.map((agent) => {
              const Icon = agent.icon;
              return (
                <div
                  key={agent.name}
                  className="p-2.5 rounded-lg border border-gray-100 dark:border-slate-700 hover:border-gray-200 dark:hover:border-slate-600 transition-colors"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <div className={`p-1.5 rounded-md ${agent.color}`}>
                      <Icon className="w-3.5 h-3.5" />
                    </div>
                    <span className="font-medium text-xs text-gray-900 dark:text-gray-100">{agent.name}</span>
                  </div>
                  <p className="text-[10px] text-gray-500 dark:text-gray-400 leading-relaxed">
                    {agent.description}
                  </p>
                </div>
              );
            })}
          </div>

          {/* Disclaimer */}
          <p className="text-[10px] text-gray-400 dark:text-gray-500 text-center mt-3">
            Multiple AI agents analyze each stock independently, then debate to reach a consensus recommendation.
          </p>
        </div>
      )}
    </section>
  );
}

// Simpler badge version for inline use
export function AIAgentBadge({ type }: { type: 'technical' | 'fundamental' | 'sentiment' | 'risk' | 'debate' }) {
  const config = {
    technical: { icon: BarChart2, label: 'Technical', color: 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400' },
    fundamental: { icon: TrendingUp, label: 'Fundamental', color: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400' },
    sentiment: { icon: MessageSquare, label: 'Sentiment', color: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400' },
    risk: { icon: Shield, label: 'Risk', color: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400' },
    debate: { icon: Brain, label: 'Debate', color: 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400' },
  };

  const { icon: Icon, label, color } = config[type];

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      <Icon className="w-3 h-3" />
      {label}
    </span>
  );
}
