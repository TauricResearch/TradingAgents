import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Calendar, TrendingUp, TrendingDown, Minus, ChevronRight, BarChart3 } from 'lucide-react';
import { sampleRecommendations } from '../data/recommendations';
import { DecisionBadge } from '../components/StockCard';

export default function History() {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const dates = sampleRecommendations.map(r => r.date);

  const getRecommendation = (date: string) => {
    return sampleRecommendations.find(r => r.date === date);
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <section className="text-center py-8">
        <h1 className="text-4xl font-display font-bold text-gray-900 mb-4">
          Historical <span className="gradient-text">Recommendations</span>
        </h1>
        <p className="text-lg text-gray-600 max-w-2xl mx-auto">
          Browse past AI recommendations and track performance over time.
        </p>
      </section>

      {/* Date Selector */}
      <div className="card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Calendar className="w-5 h-5 text-nifty-600" />
          <h2 className="font-semibold text-gray-900">Select Date</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {dates.map((date) => {
            const rec = getRecommendation(date);
            return (
              <button
                key={date}
                onClick={() => setSelectedDate(selectedDate === date ? null : date)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  selectedDate === date
                    ? 'bg-nifty-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                <div>{new Date(date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })}</div>
                <div className="text-xs opacity-75 mt-0.5">
                  {rec?.summary.buy}B / {rec?.summary.sell}S / {rec?.summary.hold}H
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Selected Date Details */}
      {selectedDate && (
        <div className="card">
          <div className="p-6 border-b border-gray-100">
            <div className="flex items-center justify-between">
              <h2 className="section-title">
                {new Date(selectedDate).toLocaleDateString('en-IN', {
                  weekday: 'long',
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </h2>
              <div className="flex items-center gap-4 text-sm">
                <span className="flex items-center gap-1 text-green-600">
                  <TrendingUp className="w-4 h-4" />
                  {getRecommendation(selectedDate)?.summary.buy} Buy
                </span>
                <span className="flex items-center gap-1 text-red-600">
                  <TrendingDown className="w-4 h-4" />
                  {getRecommendation(selectedDate)?.summary.sell} Sell
                </span>
                <span className="flex items-center gap-1 text-amber-600">
                  <Minus className="w-4 h-4" />
                  {getRecommendation(selectedDate)?.summary.hold} Hold
                </span>
              </div>
            </div>
          </div>

          <div className="divide-y divide-gray-100">
            {Object.values(getRecommendation(selectedDate)?.analysis || {}).map((stock) => (
              <Link
                key={stock.symbol}
                to={`/stock/${stock.symbol}`}
                className="flex items-center justify-between p-4 hover:bg-gray-50 transition-colors group"
              >
                <div>
                  <div className="flex items-center gap-3">
                    <span className="font-semibold text-gray-900">{stock.symbol}</span>
                    <DecisionBadge decision={stock.decision} />
                  </div>
                  <p className="text-sm text-gray-500 mt-1">{stock.company_name}</p>
                </div>
                <ChevronRight className="w-5 h-5 text-gray-400 group-hover:text-nifty-600" />
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid md:grid-cols-3 gap-6">
        <div className="card p-6 text-center">
          <BarChart3 className="w-12 h-12 text-nifty-600 mx-auto mb-4" />
          <h3 className="text-3xl font-bold text-gray-900">{dates.length}</h3>
          <p className="text-gray-600">Days of Analysis</p>
        </div>
        <div className="card p-6 text-center">
          <TrendingUp className="w-12 h-12 text-green-600 mx-auto mb-4" />
          <h3 className="text-3xl font-bold text-gray-900">
            {sampleRecommendations.reduce((acc, r) => acc + r.summary.buy, 0)}
          </h3>
          <p className="text-gray-600">Total Buy Signals</p>
        </div>
        <div className="card p-6 text-center">
          <TrendingDown className="w-12 h-12 text-red-600 mx-auto mb-4" />
          <h3 className="text-3xl font-bold text-gray-900">
            {sampleRecommendations.reduce((acc, r) => acc + r.summary.sell, 0)}
          </h3>
          <p className="text-gray-600">Total Sell Signals</p>
        </div>
      </div>
    </div>
  );
}
