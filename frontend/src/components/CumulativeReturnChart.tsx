import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import type { CumulativeReturnPoint } from '../types';

interface CumulativeReturnChartProps {
  height?: number;
  className?: string;
  data?: CumulativeReturnPoint[];
}

export default function CumulativeReturnChart({ height = 160, className = '', data: propData }: CumulativeReturnChartProps) {
  const data = propData || [];

  if (data.length === 0) {
    return (
      <div className={`flex items-center justify-center text-gray-400 ${className}`} style={{ height }}>
        No data available
      </div>
    );
  }

  // Format dates for display
  const formattedData = data.map(d => ({
    ...d,
    displayDate: new Date(d.date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' }),
  }));

  const lastPoint = formattedData[formattedData.length - 1];
  const isPositive = lastPoint.aiReturn >= 0;

  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
        <AreaChart data={formattedData} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
          <defs>
            <linearGradient id="cumulativeGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={isPositive ? '#22c55e' : '#ef4444'} stopOpacity={0.3} />
              <stop offset="95%" stopColor={isPositive ? '#22c55e' : '#ef4444'} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-slate-700" />
          <XAxis
            dataKey="displayDate"
            tick={{ fontSize: 10 }}
            className="text-gray-500 dark:text-gray-400"
          />
          <YAxis
            tick={{ fontSize: 10 }}
            tickFormatter={(v) => `${v}%`}
            className="text-gray-500 dark:text-gray-400"
            width={40}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--tooltip-bg, #fff)',
              border: '1px solid var(--tooltip-border, #e5e7eb)',
              borderRadius: '8px',
              fontSize: '12px',
            }}
            formatter={(value) => [`${(value as number).toFixed(1)}%`, 'Return']}
            labelFormatter={(label) => `Date: ${label}`}
          />
          <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="3 3" />
          <Area
            type="monotone"
            dataKey="aiReturn"
            stroke={isPositive ? '#22c55e' : '#ef4444'}
            strokeWidth={2}
            fill="url(#cumulativeGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
