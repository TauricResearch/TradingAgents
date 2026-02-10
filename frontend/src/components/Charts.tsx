import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';

interface SummaryChartProps {
  buy: number;
  sell: number;
  hold: number;
}

const COLORS = {
  buy: '#22c55e',
  sell: '#ef4444',
  hold: '#f59e0b',
};

export function SummaryPieChart({ buy, sell, hold }: SummaryChartProps) {
  const data = [
    { name: 'Buy', value: buy, color: COLORS.buy },
    { name: 'Hold', value: hold, color: COLORS.hold },
    { name: 'Sell', value: sell, color: COLORS.sell },
  ];

  return (
    <div style={{ width: '100%', height: '256px' }}>
      <ResponsiveContainer width="100%" height={256} minWidth={0} minHeight={0}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={80}
            paddingAngle={4}
            dataKey="value"
            label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
            labelLine={false}
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              backgroundColor: 'white',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
            }}
            formatter={(value) => [`${value} stocks`, '']}
          />
          <Legend
            verticalAlign="bottom"
            height={36}
            formatter={(value) => <span className="text-sm text-gray-600">{value}</span>}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

interface HistoricalDataPoint {
  date: string;
  buy: number;
  sell: number;
  hold: number;
}

interface HistoricalChartProps {
  data: HistoricalDataPoint[];
}

export function HistoricalBarChart({ data }: HistoricalChartProps) {
  const formattedData = data.map(d => ({
    ...d,
    date: new Date(d.date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' }),
  }));

  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
        <BarChart data={formattedData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 12, fill: '#6b7280' }}
            tickLine={{ stroke: '#e5e7eb' }}
          />
          <YAxis
            tick={{ fontSize: 12, fill: '#6b7280' }}
            tickLine={{ stroke: '#e5e7eb' }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'white',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
            }}
          />
          <Legend
            verticalAlign="top"
            height={36}
            formatter={(value) => <span className="text-sm text-gray-600 capitalize">{value}</span>}
          />
          <Bar dataKey="buy" stackId="a" fill={COLORS.buy} radius={[4, 4, 0, 0]} name="Buy" />
          <Bar dataKey="hold" stackId="a" fill={COLORS.hold} radius={[0, 0, 0, 0]} name="Hold" />
          <Bar dataKey="sell" stackId="a" fill={COLORS.sell} radius={[0, 0, 4, 4]} name="Sell" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

interface StockHistoryEntry {
  date: string;
  decision: string;
}

interface StockHistoryChartProps {
  history: StockHistoryEntry[];
  symbol: string;
}

export function StockHistoryTimeline({ history, symbol }: StockHistoryChartProps) {
  if (history.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        No historical data available for {symbol}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {history.map((entry, idx) => {
        const bgColor = entry.decision === 'BUY' ? 'bg-green-500' :
                        entry.decision === 'SELL' ? 'bg-red-500' : 'bg-amber-500';
        const textColor = entry.decision === 'BUY' ? 'text-green-700' :
                          entry.decision === 'SELL' ? 'text-red-700' : 'text-amber-700';

        return (
          <div key={idx} className="flex items-center gap-4">
            <div className="w-24 text-sm text-gray-500">
              {new Date(entry.date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })}
            </div>
            <div className={`w-3 h-3 rounded-full ${bgColor}`} />
            <div className={`text-sm font-medium ${textColor}`}>
              {entry.decision}
            </div>
          </div>
        );
      })}
    </div>
  );
}

interface DecisionDistributionProps {
  total: number;
  buy: number;
  sell: number;
  hold: number;
}

export function DecisionDistribution({ total, buy, sell, hold }: DecisionDistributionProps) {
  const buyPercent = ((buy / total) * 100).toFixed(1);
  const sellPercent = ((sell / total) * 100).toFixed(1);
  const holdPercent = ((hold / total) * 100).toFixed(1);

  return (
    <div className="space-y-4">
      <div className="flex h-4 rounded-full overflow-hidden bg-gray-100">
        <div
          className="bg-green-500 transition-all duration-500"
          style={{ width: `${(buy / total) * 100}%` }}
          title={`Buy: ${buy} (${buyPercent}%)`}
        />
        <div
          className="bg-amber-500 transition-all duration-500"
          style={{ width: `${(hold / total) * 100}%` }}
          title={`Hold: ${hold} (${holdPercent}%)`}
        />
        <div
          className="bg-red-500 transition-all duration-500"
          style={{ width: `${(sell / total) * 100}%` }}
          title={`Sell: ${sell} (${sellPercent}%)`}
        />
      </div>

      <div className="grid grid-cols-3 gap-4 text-center">
        <div>
          <div className="flex items-center justify-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-green-500" />
            <span className="text-sm font-medium text-gray-700">Buy</span>
          </div>
          <div className="text-2xl font-bold text-green-600">{buy}</div>
          <div className="text-xs text-gray-500">{buyPercent}%</div>
        </div>

        <div>
          <div className="flex items-center justify-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-amber-500" />
            <span className="text-sm font-medium text-gray-700">Hold</span>
          </div>
          <div className="text-2xl font-bold text-amber-600">{hold}</div>
          <div className="text-xs text-gray-500">{holdPercent}%</div>
        </div>

        <div>
          <div className="flex items-center justify-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-red-500" />
            <span className="text-sm font-medium text-gray-700">Sell</span>
          </div>
          <div className="text-2xl font-bold text-red-600">{sell}</div>
          <div className="text-xs text-gray-500">{sellPercent}%</div>
        </div>
      </div>
    </div>
  );
}
