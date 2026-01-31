import { Link } from 'react-router-dom';
import { Trophy, AlertTriangle, TrendingUp, TrendingDown } from 'lucide-react';
import type { TopPick, StockToAvoid } from '../types';
import BackgroundSparkline from './BackgroundSparkline';
import { getBacktestResult } from '../data/recommendations';

interface TopPicksProps {
  picks: TopPick[];
}

export default function TopPicks({ picks }: TopPicksProps) {
  const medals = ['🥇', '🥈', '🥉'];

  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-3">
        <Trophy className="w-5 h-5 text-amber-500" />
        <h2 className="font-semibold text-gray-900 dark:text-gray-100">Top Picks</h2>
        <span className="text-xs text-gray-500 dark:text-gray-400">({picks.length})</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {picks.map((pick, index) => {
          const backtest = getBacktestResult(pick.symbol);
          return (
            <Link
              key={pick.symbol}
              to={`/stock/${pick.symbol}`}
              className="card-hover p-3 group bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 border-green-200 dark:border-green-800 relative overflow-hidden"
            >
              {/* Background Chart */}
              {backtest && (
                <div className="absolute inset-0 opacity-[0.08]">
                  <BackgroundSparkline
                    data={backtest.price_history}
                    trend="up"
                  />
                </div>
              )}

              {/* Content */}
              <div className="relative z-10">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{medals[index]}</span>
                    <span className="font-bold text-gray-900 dark:text-gray-100">{pick.symbol}</span>
                  </div>
                  <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-500 text-white text-xs font-medium">
                    <TrendingUp className="w-3 h-3" />
                    BUY
                  </div>
                </div>
                <p className="text-xs text-gray-600 dark:text-gray-400 line-clamp-2 mb-2">{pick.reason}</p>
                <div className="flex items-center justify-between">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    pick.risk_level === 'LOW' ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400' :
                    pick.risk_level === 'HIGH' ? 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400' :
                    'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400'
                  }`}>
                    {pick.risk_level} Risk
                  </span>
                  <span className="text-xs text-green-600 dark:text-green-400 font-medium group-hover:underline">View →</span>
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
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle className="w-5 h-5 text-red-500" />
        <h2 className="font-semibold text-gray-900 dark:text-gray-100">Stocks to Avoid</h2>
        <span className="text-xs text-gray-500 dark:text-gray-400">({stocks.length})</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {stocks.map((stock) => {
          const backtest = getBacktestResult(stock.symbol);
          return (
            <Link
              key={stock.symbol}
              to={`/stock/${stock.symbol}`}
              className="card-hover p-3 group bg-gradient-to-br from-red-50 to-rose-50 dark:from-red-900/20 dark:to-rose-900/20 border-red-200 dark:border-red-800 relative overflow-hidden"
            >
              {/* Background Chart */}
              {backtest && (
                <div className="absolute inset-0 opacity-[0.08]">
                  <BackgroundSparkline
                    data={backtest.price_history}
                    trend="down"
                  />
                </div>
              )}

              {/* Content */}
              <div className="relative z-10">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-bold text-gray-900 dark:text-gray-100">{stock.symbol}</span>
                  <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-500 text-white text-xs font-medium">
                    <TrendingDown className="w-3 h-3" />
                    SELL
                  </div>
                </div>
                <p className="text-xs text-gray-600 dark:text-gray-400 line-clamp-2 mb-2">{stock.reason}</p>
                <span className="text-xs text-red-600 dark:text-red-400 font-medium group-hover:underline">View →</span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
