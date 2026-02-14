import { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { X } from 'lucide-react';
import type { ReturnBucket } from '../types';

export interface ReturnDistributionChartProps {
  height?: number;
  className?: string;
  data?: ReturnBucket[];
}

export default function ReturnDistributionChart({ height = 200, className = '', data: propData }: ReturnDistributionChartProps) {
  const [selectedBucket, setSelectedBucket] = useState<{ range: string; stocks: string[] } | null>(null);
  const data = propData || [];

  if (data.every(d => d.count === 0)) {
    return (
      <div className={`flex items-center justify-center text-gray-400 ${className}`} style={{ height }}>
        No distribution data available
      </div>
    );
  }

  // Color gradient from red (negative) to green (positive)
  const getBarColor = (range: string) => {
    if (range.includes('< -3') || range.includes('-3 to -2')) return '#ef4444';
    if (range.includes('-2 to -1')) return '#f87171';
    if (range.includes('-1 to 0')) return '#fca5a5';
    if (range.includes('0 to 1')) return '#86efac';
    if (range.includes('1 to 2')) return '#4ade80';
    if (range.includes('2 to 3') || range.includes('> 3')) return '#22c55e';
    return '#94a3b8';
  };

  const handleBarClick = (data: { range: string; stocks: string[] }) => {
    if (data.stocks.length > 0) {
      setSelectedBucket(data);
    }
  };

  return (
    <div className={className}>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
          <BarChart data={data} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-slate-700" />
            <XAxis
              dataKey="range"
              tick={{ fontSize: 10 }}
              angle={-45}
              textAnchor="end"
              height={60}
              className="text-gray-500 dark:text-gray-400"
            />
            <YAxis
              tick={{ fontSize: 11 }}
              className="text-gray-500 dark:text-gray-400"
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--tooltip-bg, #fff)',
                border: '1px solid var(--tooltip-border, #e5e7eb)',
                borderRadius: '8px',
                fontSize: '12px',
              }}
              formatter={(value) => [`${value} stocks`, 'Count']}
              labelFormatter={(label) => `Return: ${label}`}
            />
            <Bar
              dataKey="count"
              cursor="pointer"
              onClick={(_data, index) => {
                if (typeof index === 'number' && data[index]) {
                  handleBarClick(data[index]);
                }
              }}
              fill="#0ea5e9"
              shape={(props: { x: number; y: number; width: number; height: number; index?: number }) => {
                const { x, y, width, height, index: idx } = props;
                const fill = typeof idx === 'number' ? getBarColor(data[idx]?.range || '') : '#0ea5e9';
                return <rect x={x} y={y} width={width} height={height} fill={fill} rx={2} />;
              }}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Selected bucket modal */}
      {selectedBucket && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setSelectedBucket(null)} />
          <div className="relative bg-white dark:bg-slate-800 rounded-xl shadow-xl max-w-sm w-full p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">
                Stocks with {selectedBucket.range} return
              </h3>
              <button
                onClick={() => setSelectedBucket(null)}
                className="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-700"
              >
                <X className="w-4 h-4 text-gray-500" />
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {selectedBucket.stocks.map(symbol => (
                <span
                  key={symbol}
                  className="px-2 py-1 text-xs font-medium bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-300 rounded"
                >
                  {symbol}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
