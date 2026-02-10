import { AreaChart, Area, ResponsiveContainer, YAxis } from 'recharts';
import type { PricePoint } from '../types';

interface BackgroundSparklineProps {
  data: PricePoint[];
  trend: 'up' | 'down' | 'flat';
  className?: string;
}

export default function BackgroundSparkline({
  data,
  trend,
  className = '',
}: BackgroundSparklineProps) {
  if (!data || data.length < 2) {
    return null;
  }

  // Normalize data to percentage change from first point
  const basePrice = data[0].price;
  const normalizedData = data.map(point => ({
    ...point,
    normalizedPrice: ((point.price - basePrice) / basePrice) * 100,
  }));

  // Calculate min/max for domain padding
  const prices = normalizedData.map(d => d.normalizedPrice);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const padding = Math.max(Math.abs(maxPrice - minPrice) * 0.2, 1);

  // Colors based on trend
  const colors = {
    up: { stroke: '#22c55e', fill: '#22c55e' },
    down: { stroke: '#ef4444', fill: '#ef4444' },
    flat: { stroke: '#94a3b8', fill: '#94a3b8' },
  };

  const { stroke, fill } = colors[trend];

  return (
    <div className={`w-full h-full ${className}`} style={{ filter: 'blur(1px)' }}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
        <AreaChart data={normalizedData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
          <YAxis domain={[minPrice - padding, maxPrice + padding]} hide />
          <defs>
            <linearGradient id={`gradient-${trend}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={fill} stopOpacity={0.4} />
              <stop offset="100%" stopColor={fill} stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="normalizedPrice"
            stroke={stroke}
            strokeWidth={1}
            fill={`url(#gradient-${trend})`}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
