import { Link } from 'react-router-dom';
import { TrendingUp, TrendingDown, Minus, ChevronRight } from 'lucide-react';
import type { StockAnalysis, Decision } from '../types';

interface StockCardProps {
  stock: StockAnalysis;
  showDetails?: boolean;
  compact?: boolean;
}

export function DecisionBadge({ decision, size = 'default' }: { decision: Decision | null; size?: 'small' | 'default' }) {
  if (!decision) return null;

  const config = {
    BUY: {
      bg: 'bg-green-100 dark:bg-green-900/30',
      text: 'text-green-800 dark:text-green-400',
      icon: TrendingUp,
    },
    SELL: {
      bg: 'bg-red-100 dark:bg-red-900/30',
      text: 'text-red-800 dark:text-red-400',
      icon: TrendingDown,
    },
    HOLD: {
      bg: 'bg-amber-100 dark:bg-amber-900/30',
      text: 'text-amber-800 dark:text-amber-400',
      icon: Minus,
    },
  };

  const { bg, text, icon: Icon } = config[decision];
  const sizeClasses = size === 'small'
    ? 'px-2 py-0.5 text-xs gap-1'
    : 'px-2.5 py-0.5 text-xs gap-1';
  const iconSize = size === 'small' ? 'w-3 h-3' : 'w-3.5 h-3.5';

  return (
    <span className={`inline-flex items-center rounded-full font-semibold ${bg} ${text} ${sizeClasses}`}>
      <Icon className={iconSize} />
      {decision}
    </span>
  );
}

export function ConfidenceBadge({ confidence }: { confidence?: string }) {
  if (!confidence) return null;

  const colors = {
    HIGH: 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 border-green-200 dark:border-green-800',
    MEDIUM: 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800',
    LOW: 'bg-gray-50 dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600',
  };

  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${colors[confidence as keyof typeof colors] || colors.MEDIUM}`}>
      {confidence} Confidence
    </span>
  );
}

export function RiskBadge({ risk }: { risk?: string }) {
  if (!risk) return null;

  const colors = {
    HIGH: 'text-red-600 dark:text-red-400',
    MEDIUM: 'text-amber-600 dark:text-amber-400',
    LOW: 'text-green-600 dark:text-green-400',
  };

  return (
    <span className={`text-xs ${colors[risk as keyof typeof colors] || colors.MEDIUM}`}>
      {risk} Risk
    </span>
  );
}

export default function StockCard({ stock, showDetails = true, compact = false }: StockCardProps) {
  if (compact) {
    return (
      <Link
        to={`/stock/${stock.symbol}`}
        className="flex items-center justify-between px-3 py-2 hover:bg-gray-50 dark:hover:bg-slate-700/50 transition-colors group focus:outline-none focus:bg-nifty-50 dark:focus:bg-nifty-900/30"
        role="listitem"
        aria-label={`${stock.symbol} - ${stock.company_name} - ${stock.decision} recommendation`}
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
            stock.decision === 'BUY' ? 'bg-green-500' :
            stock.decision === 'SELL' ? 'bg-red-500' : 'bg-amber-500'
          }`} aria-hidden="true" />
          <span className="font-medium text-gray-900 dark:text-gray-100 text-sm">{stock.symbol}</span>
          <span className="text-gray-400 dark:text-gray-500 text-xs hidden sm:inline" aria-hidden="true">·</span>
          <span className="text-xs text-gray-500 dark:text-gray-400 truncate hidden sm:inline">{stock.company_name}</span>
        </div>
        <div className="flex items-center gap-2">
          <DecisionBadge decision={stock.decision} />
          <ChevronRight className="w-4 h-4 text-gray-300 dark:text-gray-600 group-hover:text-nifty-600 dark:group-hover:text-nifty-400 transition-colors" aria-hidden="true" />
        </div>
      </Link>
    );
  }

  return (
    <Link
      to={`/stock/${stock.symbol}`}
      className="card-hover p-3 flex items-center justify-between group"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100 truncate text-sm">{stock.symbol}</h3>
          <DecisionBadge decision={stock.decision} />
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{stock.company_name}</p>
        {showDetails && (
          <div className="flex items-center gap-2 mt-1.5">
            <ConfidenceBadge confidence={stock.confidence} />
            <RiskBadge risk={stock.risk} />
          </div>
        )}
      </div>
      <ChevronRight className="w-4 h-4 text-gray-400 dark:text-gray-500 group-hover:text-nifty-600 dark:group-hover:text-nifty-400 transition-colors flex-shrink-0" />
    </Link>
  );
}

export function StockCardCompact({ stock }: { stock: StockAnalysis }) {
  return (
    <Link
      to={`/stock/${stock.symbol}`}
      className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-slate-700/50 transition-colors"
    >
      <div className="flex items-center gap-3">
        <div className={`w-2 h-2 rounded-full ${
          stock.decision === 'BUY' ? 'bg-green-500' :
          stock.decision === 'SELL' ? 'bg-red-500' : 'bg-amber-500'
        }`} />
        <div>
          <span className="font-medium text-gray-900 dark:text-gray-100">{stock.symbol}</span>
          <span className="text-gray-400 dark:text-gray-500 mx-2">·</span>
          <span className="text-sm text-gray-500 dark:text-gray-400">{stock.company_name}</span>
        </div>
      </div>
      <DecisionBadge decision={stock.decision} />
    </Link>
  );
}
