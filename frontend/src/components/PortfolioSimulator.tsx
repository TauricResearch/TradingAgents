import { useState, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { Calculator, ChevronDown, ChevronUp, IndianRupee } from 'lucide-react';
import { getOverallReturnBreakdown } from '../data/recommendations';

interface PortfolioSimulatorProps {
  className?: string;
}

export default function PortfolioSimulator({ className = '' }: PortfolioSimulatorProps) {
  const [startingAmount, setStartingAmount] = useState(100000);
  const [showBreakdown, setShowBreakdown] = useState(false);

  const breakdown = useMemo(() => getOverallReturnBreakdown(), []);

  // Calculate portfolio values over time
  const portfolioData = useMemo(() => {
    let value = startingAmount;
    return breakdown.dailyReturns.map(day => {
      value = value * day.multiplier;
      return {
        date: new Date(day.date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' }),
        value: Math.round(value),
        return: day.return,
        cumulative: day.cumulative,
      };
    });
  }, [breakdown.dailyReturns, startingAmount]);

  const currentValue = portfolioData.length > 0
    ? portfolioData[portfolioData.length - 1].value
    : startingAmount;
  const totalReturn = ((currentValue - startingAmount) / startingAmount) * 100;
  const profitLoss = currentValue - startingAmount;
  const isPositive = profitLoss >= 0;

  const handleAmountChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseInt(e.target.value.replace(/,/g, ''), 10);
    if (!isNaN(value) && value >= 0) {
      setStartingAmount(value);
    }
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(value);
  };

  return (
    <div className={`card p-4 ${className}`}>
      <div className="flex items-center gap-2 mb-4">
        <Calculator className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
        <h2 className="font-semibold text-gray-900 dark:text-gray-100">Portfolio Simulator</h2>
      </div>

      {/* Input Section */}
      <div className="mb-4">
        <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
          Starting Investment
        </label>
        <div className="relative">
          <IndianRupee className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={startingAmount.toLocaleString('en-IN')}
            onChange={handleAmountChange}
            className="w-full pl-9 pr-4 py-2 rounded-lg border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-nifty-500 focus:border-transparent"
          />
        </div>
        <div className="flex gap-2 mt-2">
          {[10000, 50000, 100000, 500000].map(amount => (
            <button
              key={amount}
              onClick={() => setStartingAmount(amount)}
              className={`px-2 py-1 text-xs rounded ${
                startingAmount === amount
                  ? 'bg-nifty-600 text-white'
                  : 'bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-slate-600'
              }`}
            >
              {formatCurrency(amount)}
            </button>
          ))}
        </div>
      </div>

      {/* Results Section */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50">
          <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Current Value</div>
          <div className={`text-xl font-bold ${isPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
            {formatCurrency(currentValue)}
          </div>
        </div>
        <div className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50">
          <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Profit/Loss</div>
          <div className={`text-xl font-bold ${isPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
            {isPositive ? '+' : ''}{formatCurrency(profitLoss)}
            <span className="text-sm ml-1">({isPositive ? '+' : ''}{totalReturn.toFixed(1)}%)</span>
          </div>
        </div>
      </div>

      {/* Chart */}
      {portfolioData.length > 0 && (
        <div className="h-40 mb-4">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={portfolioData} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-slate-700" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10 }}
                className="text-gray-500 dark:text-gray-400"
              />
              <YAxis
                tick={{ fontSize: 10 }}
                tickFormatter={(v) => formatCurrency(v).replace('₹', '')}
                className="text-gray-500 dark:text-gray-400"
                width={60}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--tooltip-bg, #fff)',
                  border: '1px solid var(--tooltip-border, #e5e7eb)',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
                formatter={(value) => [formatCurrency(value as number), 'Value']}
              />
              <ReferenceLine
                y={startingAmount}
                stroke="#94a3b8"
                strokeDasharray="5 5"
                label={{ value: 'Start', fontSize: 10, fill: '#94a3b8' }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke={isPositive ? '#22c55e' : '#ef4444'}
                strokeWidth={2}
                dot={{ fill: isPositive ? '#22c55e' : '#ef4444', r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Daily Breakdown (Collapsible) */}
      <button
        onClick={() => setShowBreakdown(!showBreakdown)}
        className="flex items-center justify-between w-full px-3 py-2 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-slate-700/50 rounded-lg transition-colors"
      >
        <span>Daily Breakdown</span>
        {showBreakdown ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>

      {showBreakdown && (
        <div className="mt-2 border border-gray-200 dark:border-slate-600 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-slate-700">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400">Date</th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 dark:text-gray-400">Return</th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 dark:text-gray-400">Value</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-slate-700">
              {portfolioData.map((day, idx) => (
                <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-slate-700/50">
                  <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{day.date}</td>
                  <td className={`px-3 py-2 text-right font-medium ${
                    day.return >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                  }`}>
                    {day.return >= 0 ? '+' : ''}{day.return.toFixed(1)}%
                  </td>
                  <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">
                    {formatCurrency(day.value)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-3 text-center">
        Simulated returns based on AI recommendation performance. Past performance does not guarantee future results.
      </p>
    </div>
  );
}
