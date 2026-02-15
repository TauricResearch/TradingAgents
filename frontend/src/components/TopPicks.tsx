import { Link } from 'react-router-dom';
import { Trophy, AlertTriangle, TrendingUp, TrendingDown, ChevronRight } from 'lucide-react';
import type { TopPick, StockToAvoid } from '../types';
import { RankBadge } from './StockCard';

interface TopPicksProps {
  picks: TopPick[];
}

export default function TopPicks({ picks }: TopPicksProps) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2.5 mb-3">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #fbbf24, #f59e0b)', boxShadow: '0 2px 6px rgba(245,158,11,0.25)' }}>
          <Trophy className="w-3.5 h-3.5 text-amber-900" />
        </div>
        <div>
          <h2 className="font-display font-bold text-gray-900 dark:text-gray-100 text-sm tracking-tight">Top Picks</h2>
          <p className="text-[11px] text-gray-500 dark:text-gray-400">Best ranked stocks today</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {picks.map((pick, index) => {
          return (
            <Link
              key={pick.symbol}
              to={`/stock/${pick.symbol}`}
              className="group relative overflow-hidden rounded-xl border border-emerald-200/50 dark:border-emerald-800/30 p-3 transition-all hover:border-emerald-300 dark:hover:border-emerald-700/50"
              style={{
                background: index === 0
                  ? 'linear-gradient(135deg, rgba(16,185,129,0.06), rgba(5,150,105,0.03))'
                  : 'linear-gradient(135deg, rgba(16,185,129,0.04), rgba(5,150,105,0.01))',
              }}
            >
              <div className="relative z-10">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <RankBadge rank={pick.rank} size="small" />
                    <span className="font-bold text-gray-900 dark:text-gray-100 text-sm">{pick.symbol}</span>
                  </div>
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold text-white" style={{ background: 'linear-gradient(135deg, #10b981, #059669)' }}>
                    <TrendingUp className="w-3 h-3" />
                    BUY
                  </span>
                </div>
                <p className="text-[11px] text-gray-600 dark:text-gray-400 line-clamp-2 mb-2 leading-relaxed">{pick.reason?.replace(/\*\*/g, '').replace(/\*/g, '')}</p>
                <div className="flex items-center justify-between">
                  <span className={`text-[11px] px-2 py-0.5 rounded-md font-medium border ${
                    pick.risk_level === 'LOW' ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400 border-emerald-200/50 dark:border-emerald-800/30' :
                    pick.risk_level === 'HIGH' ? 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border-red-200/50 dark:border-red-800/30' :
                    'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-amber-200/50 dark:border-amber-800/30'
                  }`}>
                    {pick.risk_level} Risk
                  </span>
                  <ChevronRight className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors" />
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

interface StocksToAvoidProps {
  stocks: StockToAvoid[];
}

export function StocksToAvoid({ stocks }: StocksToAvoidProps) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2.5 mb-3">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center bg-red-100 dark:bg-red-900/25">
          <AlertTriangle className="w-3.5 h-3.5 text-red-600 dark:text-red-400" />
        </div>
        <div>
          <h2 className="font-display font-bold text-gray-900 dark:text-gray-100 text-sm tracking-tight">Stocks to Avoid</h2>
          <p className="text-[11px] text-gray-500 dark:text-gray-400">Lowest ranked stocks today</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {stocks.map((stock) => {
          return (
            <Link
              key={stock.symbol}
              to={`/stock/${stock.symbol}`}
              className="group relative overflow-hidden rounded-xl border border-red-200/40 dark:border-red-800/25 p-3 transition-all hover:border-red-300 dark:hover:border-red-700/40"
              style={{ background: 'linear-gradient(135deg, rgba(239,68,68,0.04), rgba(220,38,38,0.01))' }}
            >
              <div className="relative z-10">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-bold text-gray-900 dark:text-gray-100 text-sm">{stock.symbol}</span>
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold text-white" style={{ background: 'linear-gradient(135deg, #ef4444, #dc2626)' }}>
                    <TrendingDown className="w-3 h-3" />
                    SELL
                  </span>
                </div>
                <p className="text-[11px] text-gray-600 dark:text-gray-400 line-clamp-2 mb-2 leading-relaxed">{stock.reason?.replace(/\*\*/g, '').replace(/\*/g, '')}</p>
                <ChevronRight className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 group-hover:text-red-600 dark:group-hover:text-red-400 transition-colors" />
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
