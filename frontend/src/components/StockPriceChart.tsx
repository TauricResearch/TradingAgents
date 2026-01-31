import { useMemo } from 'react';
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
} from 'recharts';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';
import type { PricePoint, Decision } from '../types';

interface PredictionPoint {
  date: string;
  decision: Decision;
  price?: number;
}

interface StockPriceChartProps {
  priceHistory: PricePoint[];
  predictions?: PredictionPoint[];
  symbol: string;
  showArea?: boolean;
}

// Custom tooltip component
const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-lg shadow-lg p-3">
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
          {new Date(label).toLocaleDateString('en-IN', {
            weekday: 'short',
            month: 'short',
            day: 'numeric',
          })}
        </p>
        <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          ₹{data.price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
        </p>
        {data.prediction && (
          <div className={`mt-1 text-xs font-medium flex items-center gap-1 ${
            data.prediction === 'BUY' ? 'text-green-600 dark:text-green-400' :
            data.prediction === 'SELL' ? 'text-red-600 dark:text-red-400' :
            'text-amber-600 dark:text-amber-400'
          }`}>
            {data.prediction === 'BUY' && <TrendingUp className="w-3 h-3" />}
            {data.prediction === 'SELL' && <TrendingDown className="w-3 h-3" />}
            {data.prediction === 'HOLD' && <Minus className="w-3 h-3" />}
            AI: {data.prediction}
          </div>
        )}
      </div>
    );
  }
  return null;
};

// Custom prediction marker component with arrow symbols
const PredictionMarker = (props: any) => {
  const { cx, cy, payload } = props;
  if (!payload?.prediction || cx === undefined || cy === undefined) return null;

  const colors = {
    BUY: { fill: '#22c55e', stroke: '#16a34a' },
    SELL: { fill: '#ef4444', stroke: '#dc2626' },
    HOLD: { fill: '#f59e0b', stroke: '#d97706' },
  };

  const color = colors[payload.prediction as Decision] || colors.HOLD;

  // Render different shapes based on prediction type
  if (payload.prediction === 'BUY') {
    // Up arrow
    return (
      <g>
        <circle cx={cx} cy={cy} r={10} fill={color.fill} fillOpacity={0.2} />
        <path
          d={`M ${cx} ${cy - 6} L ${cx + 5} ${cy + 2} L ${cx + 2} ${cy + 2} L ${cx + 2} ${cy + 6} L ${cx - 2} ${cy + 6} L ${cx - 2} ${cy + 2} L ${cx - 5} ${cy + 2} Z`}
          fill={color.fill}
          stroke={color.stroke}
          strokeWidth={1}
        />
      </g>
    );
  } else if (payload.prediction === 'SELL') {
    // Down arrow
    return (
      <g>
        <circle cx={cx} cy={cy} r={10} fill={color.fill} fillOpacity={0.2} />
        <path
          d={`M ${cx} ${cy + 6} L ${cx + 5} ${cy - 2} L ${cx + 2} ${cy - 2} L ${cx + 2} ${cy - 6} L ${cx - 2} ${cy - 6} L ${cx - 2} ${cy - 2} L ${cx - 5} ${cy - 2} Z`}
          fill={color.fill}
          stroke={color.stroke}
          strokeWidth={1}
        />
      </g>
    );
  } else {
    // Equal/minus sign for HOLD
    return (
      <g>
        <circle cx={cx} cy={cy} r={10} fill={color.fill} fillOpacity={0.2} />
        <rect x={cx - 5} y={cy - 4} width={10} height={2.5} fill={color.fill} rx={1} />
        <rect x={cx - 5} y={cy + 1.5} width={10} height={2.5} fill={color.fill} rx={1} />
      </g>
    );
  }
};

export default function StockPriceChart({
  priceHistory,
  predictions = [],
  symbol,
  showArea = true,
}: StockPriceChartProps) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  // Theme-aware colors
  const gridColor = isDark ? '#475569' : '#e5e7eb';
  const tickColor = isDark ? '#94a3b8' : '#6b7280';

  // Merge price history with predictions
  const chartData = useMemo(() => {
    const predictionMap = new Map(
      predictions.map(p => [p.date, p.decision])
    );

    return priceHistory.map(point => ({
      ...point,
      prediction: predictionMap.get(point.date) || null,
    }));
  }, [priceHistory, predictions]);

  // Calculate price range for Y-axis
  const { minPrice, maxPrice } = useMemo(() => {
    const prices = priceHistory.map(p => p.price);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const padding = (max - min) * 0.1;
    return {
      minPrice: Math.floor(min - padding),
      maxPrice: Math.ceil(max + padding),
    };
  }, [priceHistory]);

  // Calculate overall trend
  const trend = useMemo(() => {
    if (priceHistory.length < 2) return 'flat';
    const first = priceHistory[0].price;
    const last = priceHistory[priceHistory.length - 1].price;
    const change = ((last - first) / first) * 100;
    return change > 0 ? 'up' : change < 0 ? 'down' : 'flat';
  }, [priceHistory]);

  const trendColor = trend === 'up' ? '#22c55e' : trend === 'down' ? '#ef4444' : '#6b7280';
  const gradientId = `gradient-${symbol}`;

  if (priceHistory.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-400 dark:text-gray-500">
        No price data available
      </div>
    );
  }

  // Background color based on theme
  const chartBgColor = isDark ? '#1e293b' : '#ffffff';

  return (
    <div className="w-full" style={{ backgroundColor: chartBgColor }}>
      <ResponsiveContainer width="100%" height={280} minWidth={200} minHeight={200}>
        <ComposedChart
          data={chartData}
          margin={{ top: 20, right: 20, left: 10, bottom: 20 }}
          style={{ backgroundColor: 'transparent' }}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={trendColor} stopOpacity={0.3} />
              <stop offset="95%" stopColor={trendColor} stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid
            strokeDasharray="3 3"
            stroke={gridColor}
            strokeOpacity={0.5}
            vertical={false}
          />

          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: tickColor }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(date) => new Date(date).toLocaleDateString('en-IN', {
              month: 'short',
              day: 'numeric',
            })}
            interval="preserveStartEnd"
            minTickGap={50}
          />

          <YAxis
            domain={[minPrice, maxPrice]}
            tick={{ fontSize: 10, fill: tickColor }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value) => `₹${value}`}
            width={60}
          />

          <Tooltip content={<CustomTooltip />} />

          {showArea && (
            <Area
              type="monotone"
              dataKey="price"
              stroke="transparent"
              fill={`url(#${gradientId})`}
            />
          )}

          <Line
            type="monotone"
            dataKey="price"
            stroke={trendColor}
            strokeWidth={2}
            dot={(props: any) => {
              const { payload, cx, cy } = props;
              if (payload?.prediction && cx !== undefined && cy !== undefined) {
                return <PredictionMarker cx={cx} cy={cy} payload={payload} />;
              }
              return <g />; // Return empty group for non-prediction points
            }}
            activeDot={{ r: 4, fill: trendColor }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex items-center justify-center gap-4 mt-2 text-xs text-gray-500 dark:text-gray-400">
        <div className="flex items-center gap-1.5">
          <TrendingUp className="w-4 h-4 text-green-500" />
          <span>BUY Signal</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Minus className="w-4 h-4 text-amber-500" />
          <span>HOLD Signal</span>
        </div>
        <div className="flex items-center gap-1.5">
          <TrendingDown className="w-4 h-4 text-red-500" />
          <span>SELL Signal</span>
        </div>
      </div>
    </div>
  );
}
