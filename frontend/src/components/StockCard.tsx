import { Link } from 'react-router-dom';
import { TrendingUp, TrendingDown, Minus, ChevronRight, Clock } from 'lucide-react';
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
      bg: 'bg-emerald-100 dark:bg-emerald-900/25',
      text: 'text-emerald-700 dark:text-emerald-400',
      border: 'border border-emerald-200/60 dark:border-emerald-800/40',
      icon: TrendingUp,
    },
    SELL: {
      bg: 'bg-red-100 dark:bg-red-900/25',
      text: 'text-red-700 dark:text-red-400',
      border: 'border border-red-200/60 dark:border-red-800/40',
      icon: TrendingDown,
    },
    HOLD: {
      bg: 'bg-amber-100 dark:bg-amber-900/25',
      text: 'text-amber-700 dark:text-amber-400',
      border: 'border border-amber-200/60 dark:border-amber-800/40',
      icon: Minus,
    },
  };

  const entry = config[decision];
  if (!entry) return null;
  const { bg, text, border, icon: Icon } = entry;
  const sizeClasses = size === 'small'
    ? 'px-2 py-0.5 text-[11px] gap-1'
    : 'px-2.5 py-0.5 text-xs gap-1';
  const iconSize = size === 'small' ? 'w-3 h-3' : 'w-3.5 h-3.5';

  return (
    <span className={`inline-flex items-center rounded-full font-semibold tracking-wide ${bg} ${text} ${border} ${sizeClasses}`}>
      <Icon className={iconSize} />
      {decision}
    </span>
  );
}

export function ConfidenceBadge({ confidence }: { confidence?: string }) {
  if (!confidence) return null;

  const colors = {
    HIGH: 'bg-emerald-50 dark:bg-emerald-900/15 text-emerald-700 dark:text-emerald-400 border-emerald-200/60 dark:border-emerald-800/40',
    MEDIUM: 'bg-amber-50 dark:bg-amber-900/15 text-amber-700 dark:text-amber-400 border-amber-200/60 dark:border-amber-800/40',
    LOW: 'bg-gray-50 dark:bg-gray-800/50 text-gray-600 dark:text-gray-400 border-gray-200/60 dark:border-gray-700/40',
  };

  return (
    <span className={`text-[11px] font-medium px-2 py-0.5 rounded-md border ${colors[confidence as keyof typeof colors] || colors.MEDIUM}`}>
      {confidence} Confidence
    </span>
  );
}

export function RiskBadge({ risk }: { risk?: string }) {
  if (!risk) return null;

  const colors = {
    HIGH: 'text-red-600 dark:text-red-400',
    MEDIUM: 'text-amber-600 dark:text-amber-400',
    LOW: 'text-emerald-600 dark:text-emerald-400',
  };

  return (
    <span className={`text-[11px] font-medium ${colors[risk as keyof typeof colors] || colors.MEDIUM}`}>
      {risk} Risk
    </span>
  );
}

export function HoldDaysBadge({ holdDays, decision }: { holdDays?: number | null; decision?: Decision | null }) {
  if (!holdDays || decision === 'SELL') return null;

  const label = holdDays === 1 ? '1 day' : `${holdDays}d`;

  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-md border bg-blue-50 dark:bg-blue-900/15 text-blue-700 dark:text-blue-400 border-blue-200/60 dark:border-blue-800/40">
      <Clock className="w-3 h-3" />
      Hold {label}
    </span>
  );
}

export function RankBadge({ rank, size = 'default' }: { rank?: number | null; size?: 'small' | 'default' }) {
  if (!rank) return null;

  let style: React.CSSProperties;
  let textClass: string;

  if (rank <= 10) {
    style = {
      background: 'linear-gradient(135deg, #fbbf24, #f59e0b)',
      boxShadow: '0 1px 3px rgba(245, 158, 11, 0.25)',
    };
    textClass = 'text-amber-900';
  } else if (rank <= 30) {
    style = {
      background: 'rgba(148, 163, 184, 0.15)',
      border: '1px solid rgba(148, 163, 184, 0.25)',
    };
    textClass = 'text-gray-600 dark:text-gray-300';
  } else {
    style = {
      background: 'rgba(239, 68, 68, 0.1)',
      border: '1px solid rgba(239, 68, 68, 0.2)',
    };
    textClass = 'text-red-600 dark:text-red-400';
  }

  const sizeClasses = size === 'small'
    ? 'w-5 h-5 text-[10px]'
    : 'w-6 h-6 text-xs';

  return (
    <span
      className={`inline-flex items-center justify-center rounded-full font-bold ${textClass} ${sizeClasses} flex-shrink-0 tabular-nums`}
      style={style}
      title={`Rank #${rank} of analyzed stocks`}
    >
      {rank}
    </span>
  );
}

export default function StockCard({ stock, showDetails = true, compact = false }: StockCardProps) {
  if (compact) {
    return (
      <Link
        to={`/stock/${stock.symbol}`}
        className="flex items-center justify-between px-3 py-2.5 hover:bg-gray-50/80 dark:hover:bg-slate-700/30 transition-all group focus:outline-none focus:bg-nifty-50 dark:focus:bg-nifty-900/30 rounded-lg"
        role="listitem"
        aria-label={`${stock.symbol} - ${stock.company_name} - ${stock.decision} recommendation`}
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <RankBadge rank={stock.rank} size="small" />
          <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
            stock.decision === 'BUY' ? 'bg-emerald-500' :
            stock.decision === 'SELL' ? 'bg-red-500' : 'bg-amber-500'
          }`} aria-hidden="true" />
          <span className="font-semibold text-gray-900 dark:text-gray-100 text-sm">{stock.symbol}</span>
          <span className="text-gray-300 dark:text-gray-600 text-xs hidden sm:inline" aria-hidden="true">&middot;</span>
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
          <RankBadge rank={stock.rank} size="small" />
          <h3 className="font-semibold text-gray-900 dark:text-gray-100 truncate text-sm">{stock.symbol}</h3>
          <DecisionBadge decision={stock.decision} />
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{stock.company_name}</p>
        {showDetails && (
          <div className="flex items-center gap-2 mt-1.5">
            <ConfidenceBadge confidence={stock.confidence} />
            <RiskBadge risk={stock.risk} />
            <HoldDaysBadge holdDays={stock.hold_days} decision={stock.decision} />
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
      className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50/80 dark:hover:bg-slate-700/30 transition-all"
    >
      <div className="flex items-center gap-3">
        <RankBadge rank={stock.rank} size="small" />
        <div className={`w-2 h-2 rounded-full ${
          stock.decision === 'BUY' ? 'bg-emerald-500' :
          stock.decision === 'SELL' ? 'bg-red-500' : 'bg-amber-500'
        }`} />
        <div>
          <span className="font-semibold text-gray-900 dark:text-gray-100">{stock.symbol}</span>
          <span className="text-gray-300 dark:text-gray-600 mx-2">&middot;</span>
          <span className="text-sm text-gray-500 dark:text-gray-400">{stock.company_name}</span>
        </div>
      </div>
      <DecisionBadge decision={stock.decision} />
    </Link>
  );
}
