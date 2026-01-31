import { HelpCircle, TrendingUp, TrendingDown, Activity, Target } from 'lucide-react';
import { calculateRiskMetrics } from '../data/recommendations';
import { useState } from 'react';

interface RiskMetricsCardProps {
  className?: string;
}

export default function RiskMetricsCard({ className = '' }: RiskMetricsCardProps) {
  const [showTooltip, setShowTooltip] = useState<string | null>(null);
  const metrics = calculateRiskMetrics();

  const tooltips: Record<string, string> = {
    sharpe: 'Sharpe Ratio measures risk-adjusted returns. Higher is better (>1 is good, >2 is excellent).',
    drawdown: 'Maximum Drawdown shows the largest peak-to-trough decline. Lower is better.',
    winloss: 'Win/Loss Ratio compares average winning trade to average losing trade. Higher means bigger wins than losses.',
    winrate: 'Win Rate is the percentage of predictions that were correct.',
  };

  const getColor = (metric: string, value: number) => {
    switch (metric) {
      case 'sharpe':
        return value >= 1 ? 'text-green-600 dark:text-green-400' : value >= 0 ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400';
      case 'drawdown':
        return value <= 5 ? 'text-green-600 dark:text-green-400' : value <= 15 ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400';
      case 'winloss':
        return value >= 1.5 ? 'text-green-600 dark:text-green-400' : value >= 1 ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400';
      case 'winrate':
        return value >= 70 ? 'text-green-600 dark:text-green-400' : value >= 50 ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400';
      default:
        return 'text-gray-700 dark:text-gray-300';
    }
  };

  const cards = [
    {
      id: 'sharpe',
      label: 'Sharpe Ratio',
      value: metrics.sharpeRatio.toFixed(2),
      icon: Activity,
      color: getColor('sharpe', metrics.sharpeRatio),
    },
    {
      id: 'drawdown',
      label: 'Max Drawdown',
      value: `${metrics.maxDrawdown.toFixed(1)}%`,
      icon: TrendingDown,
      color: getColor('drawdown', metrics.maxDrawdown),
    },
    {
      id: 'winloss',
      label: 'Win/Loss Ratio',
      value: metrics.winLossRatio.toFixed(2),
      icon: TrendingUp,
      color: getColor('winloss', metrics.winLossRatio),
    },
    {
      id: 'winrate',
      label: 'Win Rate',
      value: `${metrics.winRate}%`,
      icon: Target,
      color: getColor('winrate', metrics.winRate),
    },
  ];

  return (
    <div className={`grid grid-cols-2 sm:grid-cols-4 gap-3 ${className}`}>
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <div
            key={card.id}
            className="relative p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50 text-center group"
          >
            <div className="flex items-center justify-center gap-1 mb-1">
              <Icon className={`w-4 h-4 ${card.color}`} />
              <span className={`text-xl font-bold ${card.color}`}>{card.value}</span>
            </div>
            <div className="flex items-center justify-center gap-1">
              <span className="text-xs text-gray-500 dark:text-gray-400">{card.label}</span>
              <button
                onClick={() => setShowTooltip(showTooltip === card.id ? null : card.id)}
                className="opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <HelpCircle className="w-3 h-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" />
              </button>
            </div>

            {/* Tooltip */}
            {showTooltip === card.id && (
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 text-xs rounded-lg shadow-lg z-10 w-48">
                {tooltips[card.id]}
                <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900 dark:border-t-gray-100" />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
