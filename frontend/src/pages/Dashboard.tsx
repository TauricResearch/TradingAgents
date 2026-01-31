import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Calendar, RefreshCw, Filter, ChevronRight, PieChart } from 'lucide-react';
import SummaryStats from '../components/SummaryStats';
import TopPicks, { StocksToAvoid } from '../components/TopPicks';
import StockCard from '../components/StockCard';
import { SummaryPieChart } from '../components/Charts';
import { getLatestRecommendation } from '../data/recommendations';
import type { Decision } from '../types';

type FilterType = 'ALL' | Decision;

export default function Dashboard() {
  const recommendation = getLatestRecommendation();
  const [filter, setFilter] = useState<FilterType>('ALL');

  if (!recommendation) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-12 h-12 text-gray-300 mx-auto mb-4 animate-spin" />
          <h2 className="text-xl font-semibold text-gray-700">Loading recommendations...</h2>
        </div>
      </div>
    );
  }

  const stocks = Object.values(recommendation.analysis);
  const filteredStocks = filter === 'ALL'
    ? stocks
    : stocks.filter(s => s.decision === filter);

  const filterButtons: { label: string; value: FilterType; count: number }[] = [
    { label: 'All', value: 'ALL', count: stocks.length },
    { label: 'Buy', value: 'BUY', count: recommendation.summary.buy },
    { label: 'Sell', value: 'SELL', count: recommendation.summary.sell },
    { label: 'Hold', value: 'HOLD', count: recommendation.summary.hold },
  ];

  return (
    <div className="space-y-8">
      {/* Hero Section */}
      <section className="text-center py-8">
        <h1 className="text-4xl md:text-5xl font-display font-bold text-gray-900 mb-4">
          Nifty 50 <span className="gradient-text">AI Recommendations</span>
        </h1>
        <p className="text-lg text-gray-600 max-w-2xl mx-auto">
          AI-powered daily stock analysis for all Nifty 50 stocks. Get actionable buy, sell, and hold recommendations.
        </p>
        <div className="flex items-center justify-center gap-2 mt-4 text-sm text-gray-500">
          <Calendar className="w-4 h-4" />
          <span>Last updated: {new Date(recommendation.date).toLocaleDateString('en-IN', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric',
          })}</span>
        </div>
      </section>

      {/* Summary Stats */}
      <SummaryStats
        total={recommendation.summary.total}
        buy={recommendation.summary.buy}
        sell={recommendation.summary.sell}
        hold={recommendation.summary.hold}
        date={recommendation.date}
      />

      {/* Chart and Stats Section */}
      <div className="grid lg:grid-cols-2 gap-6">
        <div className="card p-6">
          <div className="flex items-center gap-2 mb-4">
            <PieChart className="w-5 h-5 text-nifty-600" />
            <h2 className="section-title text-lg">Decision Distribution</h2>
          </div>
          <SummaryPieChart
            buy={recommendation.summary.buy}
            sell={recommendation.summary.sell}
            hold={recommendation.summary.hold}
          />
        </div>

        <div className="card p-6">
          <h2 className="section-title text-lg mb-4">Quick Analysis</h2>
          <div className="space-y-4">
            <div className="p-4 bg-green-50 rounded-lg">
              <div className="flex justify-between items-center mb-2">
                <span className="font-medium text-green-800">Bullish Signals</span>
                <span className="text-2xl font-bold text-green-600">{recommendation.summary.buy}</span>
              </div>
              <p className="text-sm text-green-700">
                {((recommendation.summary.buy / recommendation.summary.total) * 100).toFixed(0)}% of stocks show buying opportunities
              </p>
            </div>
            <div className="p-4 bg-amber-50 rounded-lg">
              <div className="flex justify-between items-center mb-2">
                <span className="font-medium text-amber-800">Neutral Position</span>
                <span className="text-2xl font-bold text-amber-600">{recommendation.summary.hold}</span>
              </div>
              <p className="text-sm text-amber-700">
                {((recommendation.summary.hold / recommendation.summary.total) * 100).toFixed(0)}% of stocks recommend holding
              </p>
            </div>
            <div className="p-4 bg-red-50 rounded-lg">
              <div className="flex justify-between items-center mb-2">
                <span className="font-medium text-red-800">Bearish Signals</span>
                <span className="text-2xl font-bold text-red-600">{recommendation.summary.sell}</span>
              </div>
              <p className="text-sm text-red-700">
                {((recommendation.summary.sell / recommendation.summary.total) * 100).toFixed(0)}% of stocks suggest selling
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Top Picks and Avoid Section */}
      <div className="grid lg:grid-cols-2 gap-6">
        <TopPicks picks={recommendation.top_picks} />
        <StocksToAvoid stocks={recommendation.stocks_to_avoid} />
      </div>

      {/* All Stocks Section */}
      <section className="card">
        <div className="p-6 border-b border-gray-100">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <Filter className="w-5 h-5 text-gray-400" />
              <h2 className="section-title">All Stocks</h2>
            </div>
            <div className="flex gap-2">
              {filterButtons.map(({ label, value, count }) => (
                <button
                  key={value}
                  onClick={() => setFilter(value)}
                  className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                    filter === value
                      ? 'bg-nifty-600 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {label} ({count})
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="divide-y divide-gray-100">
          {filteredStocks.map((stock) => (
            <StockCard key={stock.symbol} stock={stock} />
          ))}
        </div>

        {filteredStocks.length === 0 && (
          <div className="p-12 text-center">
            <p className="text-gray-500">No stocks match the selected filter.</p>
          </div>
        )}
      </section>

      {/* CTA Section */}
      <section className="card bg-gradient-to-r from-nifty-600 to-nifty-800 text-white p-8">
        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
          <div>
            <h2 className="text-2xl font-display font-bold mb-2">
              Track Historical Recommendations
            </h2>
            <p className="text-nifty-100">
              View past recommendations and track how our AI predictions performed over time.
            </p>
          </div>
          <Link
            to="/history"
            className="inline-flex items-center gap-2 bg-white text-nifty-700 px-6 py-3 rounded-lg font-semibold hover:bg-nifty-50 transition-colors"
          >
            View History
            <ChevronRight className="w-5 h-5" />
          </Link>
        </div>
      </section>
    </div>
  );
}
