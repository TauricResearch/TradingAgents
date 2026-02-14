import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine } from 'recharts';
import { TrendingUp, TrendingDown } from 'lucide-react';
import type { CumulativeReturnPoint } from '../types';

export interface IndexComparisonChartProps {
  height?: number;
  className?: string;
  data?: CumulativeReturnPoint[];
}

export default function IndexComparisonChart({ height = 220, className = '', data: propData }: IndexComparisonChartProps) {
  const data = propData || [];

  if (data.length === 0) {
    return (
      <div className={`flex items-center justify-center text-gray-400 ${className}`} style={{ height }}>
        No comparison data available
      </div>
    );
  }

  // Format dates for display
  const formattedData = data.map(d => ({
    ...d,
    displayDate: new Date(d.date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' }),
  }));

  const lastPoint = formattedData[formattedData.length - 1];
  const aiReturn = lastPoint?.aiReturn || 0;
  const indexReturn = lastPoint?.indexReturn || 0;
  const outperformance = aiReturn - indexReturn;
  const isOutperforming = outperformance >= 0;

  return (
    <div className={className}>
      {/* Summary Card */}
      <div className="flex items-center justify-between p-3 mb-3 rounded-lg bg-gray-50 dark:bg-slate-700/50">
        <div className="flex items-center gap-2">
          {isOutperforming ? (
            <TrendingUp className="w-5 h-5 text-green-500" />
          ) : (
            <TrendingDown className="w-5 h-5 text-red-500" />
          )}
          <span className="text-sm text-gray-600 dark:text-gray-400">
            AI Strategy {isOutperforming ? 'outperformed' : 'underperformed'} Nifty50 by{' '}
            <span className={`font-bold ${isOutperforming ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
              {Math.abs(outperformance).toFixed(1)}%
            </span>
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1">
            <div className="w-3 h-0.5 bg-nifty-600 rounded" />
            <span className="text-gray-500 dark:text-gray-400">AI: {aiReturn >= 0 ? '+' : ''}{aiReturn.toFixed(1)}%</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-3 h-0.5 bg-amber-500 rounded" />
            <span className="text-gray-500 dark:text-gray-400">Nifty: {indexReturn >= 0 ? '+' : ''}{indexReturn.toFixed(1)}%</span>
          </div>
        </div>
      </div>

      {/* Chart */}
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
          <LineChart data={formattedData} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-slate-700" />
            <XAxis
              dataKey="displayDate"
              tick={{ fontSize: 11 }}
              className="text-gray-500 dark:text-gray-400"
            />
            <YAxis
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => `${v}%`}
              className="text-gray-500 dark:text-gray-400"
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--tooltip-bg, #fff)',
                border: '1px solid var(--tooltip-border, #e5e7eb)',
                borderRadius: '8px',
                fontSize: '12px',
              }}
              formatter={(value) => [`${(value as number).toFixed(1)}%`, '']}
              labelFormatter={(label) => `Date: ${label}`}
            />
            <Legend
              wrapperStyle={{ fontSize: '11px' }}
              formatter={(value) => value === 'aiReturn' ? 'AI Strategy' : 'Nifty50 Index'}
            />
            <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="3 3" />
            <Line
              type="monotone"
              dataKey="aiReturn"
              name="aiReturn"
              stroke="#0ea5e9"
              strokeWidth={2}
              dot={{ fill: '#0ea5e9', r: 3 }}
              activeDot={{ r: 5 }}
            />
            <Line
              type="monotone"
              dataKey="indexReturn"
              name="indexReturn"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={{ fill: '#f59e0b', r: 3 }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
