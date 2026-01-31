import { TrendingUp, TrendingDown, Minus, BarChart2 } from 'lucide-react';

interface SummaryStatsProps {
  total: number;
  buy: number;
  sell: number;
  hold: number;
  date: string;
}

export default function SummaryStats({ total, buy, sell, hold, date }: SummaryStatsProps) {
  const stats = [
    {
      label: 'Total Analyzed',
      value: total,
      icon: BarChart2,
      color: 'text-nifty-600',
      bg: 'bg-nifty-50',
    },
    {
      label: 'Buy',
      value: buy,
      icon: TrendingUp,
      color: 'text-green-600',
      bg: 'bg-green-50',
      percentage: ((buy / total) * 100).toFixed(0),
    },
    {
      label: 'Sell',
      value: sell,
      icon: TrendingDown,
      color: 'text-red-600',
      bg: 'bg-red-50',
      percentage: ((sell / total) * 100).toFixed(0),
    },
    {
      label: 'Hold',
      value: hold,
      icon: Minus,
      color: 'text-amber-600',
      bg: 'bg-amber-50',
      percentage: ((hold / total) * 100).toFixed(0),
    },
  ];

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="section-title">Today's Summary</h2>
        <span className="text-sm text-gray-500">
          {new Date(date).toLocaleDateString('en-IN', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric',
          })}
        </span>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map(({ label, value, icon: Icon, color, bg, percentage }) => (
          <div key={label} className={`${bg} rounded-xl p-4`}>
            <div className="flex items-center justify-between mb-2">
              <Icon className={`w-5 h-5 ${color}`} />
              {percentage && (
                <span className={`text-xs font-medium ${color}`}>{percentage}%</span>
              )}
            </div>
            <p className={`text-2xl font-bold ${color}`}>{value}</p>
            <p className="text-sm text-gray-600">{label}</p>
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div className="mt-6">
        <div className="flex h-3 rounded-full overflow-hidden">
          <div
            className="bg-green-500 transition-all duration-500"
            style={{ width: `${(buy / total) * 100}%` }}
          />
          <div
            className="bg-amber-500 transition-all duration-500"
            style={{ width: `${(hold / total) * 100}%` }}
          />
          <div
            className="bg-red-500 transition-all duration-500"
            style={{ width: `${(sell / total) * 100}%` }}
          />
        </div>
        <div className="flex justify-between mt-2 text-xs text-gray-500">
          <span>Buy ({buy})</span>
          <span>Hold ({hold})</span>
          <span>Sell ({sell})</span>
        </div>
      </div>
    </div>
  );
}
