import { Link } from 'react-router-dom';
import { TrendingUp, TrendingDown, Minus, ChevronRight } from 'lucide-react';
import type { StockAnalysis, Decision } from '../types';

interface StockCardProps {
  stock: StockAnalysis;
  showDetails?: boolean;
}

export function DecisionBadge({ decision }: { decision: Decision | null }) {
  if (!decision) return null;

  const config = {
    BUY: {
      bg: 'bg-green-100',
      text: 'text-green-800',
      icon: TrendingUp,
    },
    SELL: {
      bg: 'bg-red-100',
      text: 'text-red-800',
      icon: TrendingDown,
    },
    HOLD: {
      bg: 'bg-amber-100',
      text: 'text-amber-800',
      icon: Minus,
    },
  };

  const { bg, text, icon: Icon } = config[decision];

  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold ${bg} ${text}`}>
      <Icon className="w-4 h-4" />
      {decision}
    </span>
  );
}

export function ConfidenceBadge({ confidence }: { confidence?: string }) {
  if (!confidence) return null;

  const colors = {
    HIGH: 'bg-green-50 text-green-700 border-green-200',
    MEDIUM: 'bg-amber-50 text-amber-700 border-amber-200',
    LOW: 'bg-gray-50 text-gray-700 border-gray-200',
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
    HIGH: 'text-red-600',
    MEDIUM: 'text-amber-600',
    LOW: 'text-green-600',
  };

  return (
    <span className={`text-xs ${colors[risk as keyof typeof colors] || colors.MEDIUM}`}>
      {risk} Risk
    </span>
  );
}

export default function StockCard({ stock, showDetails = true }: StockCardProps) {
  return (
    <Link
      to={`/stock/${stock.symbol}`}
      className="card-hover p-4 flex items-center justify-between group"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-3 mb-1">
          <h3 className="font-semibold text-gray-900 truncate">{stock.symbol}</h3>
          <DecisionBadge decision={stock.decision} />
        </div>
        <p className="text-sm text-gray-500 truncate">{stock.company_name}</p>
        {showDetails && (
          <div className="flex items-center gap-3 mt-2">
            <ConfidenceBadge confidence={stock.confidence} />
            <RiskBadge risk={stock.risk} />
          </div>
        )}
      </div>
      <ChevronRight className="w-5 h-5 text-gray-400 group-hover:text-nifty-600 transition-colors flex-shrink-0" />
    </Link>
  );
}

export function StockCardCompact({ stock }: { stock: StockAnalysis }) {
  return (
    <Link
      to={`/stock/${stock.symbol}`}
      className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 transition-colors"
    >
      <div className="flex items-center gap-3">
        <div className={`w-2 h-2 rounded-full ${
          stock.decision === 'BUY' ? 'bg-green-500' :
          stock.decision === 'SELL' ? 'bg-red-500' : 'bg-amber-500'
        }`} />
        <div>
          <span className="font-medium text-gray-900">{stock.symbol}</span>
          <span className="text-gray-400 mx-2">·</span>
          <span className="text-sm text-gray-500">{stock.company_name}</span>
        </div>
      </div>
      <DecisionBadge decision={stock.decision} />
    </Link>
  );
}
