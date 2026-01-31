import { Link } from 'react-router-dom';
import { Trophy, TrendingUp, AlertTriangle, ChevronRight } from 'lucide-react';
import type { TopPick, StockToAvoid } from '../types';

interface TopPicksProps {
  picks: TopPick[];
}

export default function TopPicks({ picks }: TopPicksProps) {
  const medals = ['🥇', '🥈', '🥉'];
  const bgColors = [
    'bg-gradient-to-br from-amber-50 to-yellow-50 border-amber-200',
    'bg-gradient-to-br from-gray-50 to-slate-50 border-gray-200',
    'bg-gradient-to-br from-orange-50 to-amber-50 border-orange-200',
  ];

  return (
    <div className="card p-6">
      <div className="flex items-center gap-2 mb-6">
        <Trophy className="w-6 h-6 text-amber-500" />
        <h2 className="section-title">Top Picks</h2>
      </div>

      <div className="grid gap-4">
        {picks.map((pick, index) => (
          <Link
            key={pick.symbol}
            to={`/stock/${pick.symbol}`}
            className={`block p-4 rounded-xl border-2 ${bgColors[index]} hover:shadow-md transition-all group`}
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-3">
                <span className="text-2xl">{medals[index]}</span>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-lg text-gray-900">{pick.symbol}</h3>
                    <span className="badge-buy">
                      <TrendingUp className="w-3 h-3 mr-1" />
                      {pick.decision}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600">{pick.company_name}</p>
                </div>
              </div>
              <ChevronRight className="w-5 h-5 text-gray-400 group-hover:text-nifty-600 transition-colors" />
            </div>
            <p className="text-sm text-gray-700 mt-3 leading-relaxed">{pick.reason}</p>
            <div className="mt-3 flex items-center gap-2">
              <span className={`text-xs px-2 py-1 rounded-full ${
                pick.risk_level === 'LOW' ? 'bg-green-100 text-green-700' :
                pick.risk_level === 'HIGH' ? 'bg-red-100 text-red-700' :
                'bg-amber-100 text-amber-700'
              }`}>
                {pick.risk_level} Risk
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

interface StocksToAvoidProps {
  stocks: StockToAvoid[];
}

export function StocksToAvoid({ stocks }: StocksToAvoidProps) {
  return (
    <div className="card p-6">
      <div className="flex items-center gap-2 mb-6">
        <AlertTriangle className="w-6 h-6 text-red-500" />
        <h2 className="section-title">Stocks to Avoid</h2>
      </div>

      <div className="space-y-3">
        {stocks.map((stock) => (
          <Link
            key={stock.symbol}
            to={`/stock/${stock.symbol}`}
            className="block p-4 rounded-lg bg-red-50 border border-red-100 hover:bg-red-100 transition-colors group"
          >
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <span className="font-bold text-red-800">{stock.symbol}</span>
                <span className="badge-sell text-xs">SELL</span>
              </div>
              <ChevronRight className="w-4 h-4 text-red-400 group-hover:text-red-600" />
            </div>
            <p className="text-sm text-red-700">{stock.reason}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
