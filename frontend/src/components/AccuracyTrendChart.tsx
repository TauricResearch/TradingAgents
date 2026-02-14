import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

export interface AccuracyTrendPoint {
  date: string;
  overall: number;
  buy: number;
  sell: number;
  hold: number;
}

interface AccuracyTrendChartProps {
  height?: number;
  className?: string;
  data?: AccuracyTrendPoint[];
}

export default function AccuracyTrendChart({ height = 200, className = '', data: propData }: AccuracyTrendChartProps) {
  const data = propData || [];

  if (data.length === 0) {
    return (
      <div className={`flex items-center justify-center text-gray-400 ${className}`} style={{ height }}>
        No accuracy data available
      </div>
    );
  }

  // Format dates for display
  const formattedData = data.map(d => ({
    ...d,
    displayDate: new Date(d.date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' }),
  }));

  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
        <LineChart data={formattedData} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-slate-700" />
          <XAxis
            dataKey="displayDate"
            tick={{ fontSize: 11 }}
            className="text-gray-500 dark:text-gray-400"
          />
          <YAxis
            domain={[0, 100]}
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
            formatter={(value) => [`${value}%`, '']}
            labelFormatter={(label) => `Date: ${label}`}
          />
          <Legend
            wrapperStyle={{ fontSize: '11px' }}
            formatter={(value) => value.charAt(0).toUpperCase() + value.slice(1)}
          />
          <Line
            type="monotone"
            dataKey="overall"
            stroke="#0ea5e9"
            strokeWidth={2}
            dot={{ fill: '#0ea5e9', r: 3 }}
            activeDot={{ r: 5 }}
          />
          <Line
            type="monotone"
            dataKey="buy"
            stroke="#22c55e"
            strokeWidth={1.5}
            dot={{ fill: '#22c55e', r: 2 }}
            strokeDasharray="5 5"
          />
          <Line
            type="monotone"
            dataKey="sell"
            stroke="#ef4444"
            strokeWidth={1.5}
            dot={{ fill: '#ef4444', r: 2 }}
            strokeDasharray="5 5"
          />
          <Line
            type="monotone"
            dataKey="hold"
            stroke="#f59e0b"
            strokeWidth={1.5}
            dot={{ fill: '#f59e0b', r: 2 }}
            strokeDasharray="5 5"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
