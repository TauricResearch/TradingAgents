import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts';
import type { PricePoint } from '../types';

interface SparklineProps {
  data: PricePoint[];
  width?: number;
  height?: number;
  positive?: boolean;
  className?: string;
}

export default function Sparkline({
  data,
  width = 80,
  height = 24,
  positive = true,
  className = '',
}: SparklineProps) {
  if (!data || data.length < 2) {
    return (
      <div
        className={`flex items-center justify-center text-gray-300 dark:text-gray-600 ${className}`}
        style={{ width, height }}
      >
        <span className="text-[10px]">No data</span>
      </div>
    );
  }

  // Normalize data to percentage change from first point for better visual variation
  const basePrice = data[0].price;
  const normalizedData = data.map(point => ({
    ...point,
    normalizedPrice: ((point.price - basePrice) / basePrice) * 100,
  }));

  // Calculate min/max for domain padding
  const prices = normalizedData.map(d => d.normalizedPrice);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const padding = Math.max(Math.abs(maxPrice - minPrice) * 0.15, 0.5);

  const color = positive ? '#22c55e' : '#ef4444';

  return (
    <div className={className} style={{ width, height, minWidth: width, minHeight: height }}>
      <ResponsiveContainer width="100%" height="100%" minWidth={width} minHeight={height}>
        <LineChart data={normalizedData} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <YAxis
            domain={[minPrice - padding, maxPrice + padding]}
            hide
          />
          <Line
            type="monotone"
            dataKey="normalizedPrice"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
