import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Calendar, TrendingUp, TrendingDown, Minus, ChevronRight, BarChart3, Target, HelpCircle, Activity, Calculator, LineChart, PieChart, Shield } from 'lucide-react';
import { sampleRecommendations, getBacktestResult, calculateAccuracyMetrics, getDateStats, getOverallStats, getReturnBreakdown } from '../data/recommendations';
import { DecisionBadge } from '../components/StockCard';
import Sparkline from '../components/Sparkline';
import AccuracyBadge from '../components/AccuracyBadge';
import AccuracyExplainModal from '../components/AccuracyExplainModal';
import ReturnExplainModal from '../components/ReturnExplainModal';
import OverallReturnModal from '../components/OverallReturnModal';
import AccuracyTrendChart from '../components/AccuracyTrendChart';
import ReturnDistributionChart from '../components/ReturnDistributionChart';
import RiskMetricsCard from '../components/RiskMetricsCard';
import PortfolioSimulator from '../components/PortfolioSimulator';
import IndexComparisonChart from '../components/IndexComparisonChart';
import type { StockAnalysis } from '../types';

export default function History() {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [showAccuracyModal, setShowAccuracyModal] = useState(false);
  const [showReturnModal, setShowReturnModal] = useState(false);
  const [returnModalDate, setReturnModalDate] = useState<string | null>(null);
  const [showOverallModal, setShowOverallModal] = useState(false);

  const dates = sampleRecommendations.map(r => r.date);
  const accuracyMetrics = calculateAccuracyMetrics();
  const overallStats = useMemo(() => getOverallStats(), []);

  // Pre-calculate date stats for all dates
  const dateStatsMap = useMemo(() => {
    const map: Record<string, ReturnType<typeof getDateStats>> = {};
    dates.forEach(date => {
      map[date] = getDateStats(date);
    });
    return map;
  }, [dates]);

  const getRecommendation = (date: string) => {
    return sampleRecommendations.find(r => r.date === date);
  };

  return (
    <div className="space-y-4">
      {/* Compact Header */}
      <section className="card p-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-display font-bold text-gray-900 dark:text-gray-100">
              Historical <span className="gradient-text">Recommendations</span>
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">Browse past AI recommendations with backtest results</p>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-1.5 text-nifty-600 dark:text-nifty-400">
              <BarChart3 className="w-4 h-4" />
              <span className="font-semibold">{dates.length}</span>
              <span className="text-gray-500 dark:text-gray-400">days</span>
            </div>
          </div>
        </div>
      </section>

      {/* Accuracy Metrics */}
      <section className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Target className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
            <h2 className="font-semibold text-gray-900 dark:text-gray-100">Prediction Accuracy</h2>
          </div>
          <button
            onClick={() => setShowAccuracyModal(true)}
            className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 dark:text-gray-400 hover:text-nifty-600 dark:hover:text-nifty-400 hover:bg-gray-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
            title="How is accuracy calculated?"
          >
            <HelpCircle className="w-4 h-4" />
            <span className="hidden sm:inline">How it's calculated</span>
          </button>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="p-3 rounded-lg bg-nifty-50 dark:bg-nifty-900/20 text-center">
            <div className="text-2xl font-bold text-nifty-600 dark:text-nifty-400">
              {(accuracyMetrics.success_rate * 100).toFixed(0)}%
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Overall Accuracy</div>
          </div>
          <div className="p-3 rounded-lg bg-green-50 dark:bg-green-900/20 text-center">
            <div className="text-2xl font-bold text-green-600 dark:text-green-400">
              {(accuracyMetrics.buy_accuracy * 100).toFixed(0)}%
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Buy Accuracy</div>
          </div>
          <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-center">
            <div className="text-2xl font-bold text-red-600 dark:text-red-400">
              {(accuracyMetrics.sell_accuracy * 100).toFixed(0)}%
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Sell Accuracy</div>
          </div>
          <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 text-center">
            <div className="text-2xl font-bold text-amber-600 dark:text-amber-400">
              {(accuracyMetrics.hold_accuracy * 100).toFixed(0)}%
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Hold Accuracy</div>
          </div>
        </div>
        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-2 text-center">
          Based on {accuracyMetrics.total_predictions} predictions tracked over time
        </p>
      </section>

      {/* Accuracy Trend Chart */}
      <section className="card p-4">
        <div className="flex items-center gap-2 mb-3">
          <LineChart className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">Accuracy Trend</h2>
        </div>
        <AccuracyTrendChart height={200} />
        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-2 text-center">
          Prediction accuracy over the past {dates.length} trading days
        </p>
      </section>

      {/* Risk Metrics */}
      <section className="card p-4">
        <div className="flex items-center gap-2 mb-3">
          <Shield className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">Risk Metrics</h2>
        </div>
        <RiskMetricsCard />
        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-2 text-center">
          Risk-adjusted performance metrics for the AI trading strategy
        </p>
      </section>

      {/* Portfolio Simulator */}
      <PortfolioSimulator />

      {/* Date Selector */}
      <div className="card p-4">
        <div className="flex items-center gap-2 mb-3">
          <Calendar className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />
          <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">Select Date</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {dates.map((date) => {
            const rec = getRecommendation(date);
            const stats = dateStatsMap[date];
            const avgReturn = stats?.avgReturn1d ?? 0;
            const isPositive = avgReturn >= 0;

            return (
              <div key={date} className="relative group">
                <button
                  onClick={() => setSelectedDate(selectedDate === date ? null : date)}
                  className={`px-3 py-2 rounded-lg text-xs font-medium transition-all min-w-[90px] ${
                    selectedDate === date
                      ? 'bg-nifty-600 text-white ring-2 ring-nifty-400'
                      : 'bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-slate-600'
                  }`}
                >
                  <div className="font-semibold">{new Date(date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })}</div>
                  <div className={`text-sm font-bold mt-0.5 ${
                    selectedDate === date
                      ? 'text-white'
                      : isPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                  }`}>
                    {isPositive ? '+' : ''}{avgReturn.toFixed(1)}%
                  </div>
                  <div className={`text-[10px] mt-0.5 ${selectedDate === date ? 'text-white/80' : 'opacity-60'}`}>
                    {rec?.summary.buy}B/{rec?.summary.sell}S/{rec?.summary.hold}H
                  </div>
                </button>
                {/* Help button for return explanation */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setReturnModalDate(date);
                    setShowReturnModal(true);
                  }}
                  className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-white dark:bg-slate-600 shadow-sm border border-gray-200 dark:border-slate-500 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                  title="How is this calculated?"
                >
                  <Calculator className="w-2.5 h-2.5 text-gray-500 dark:text-gray-300" />
                </button>
              </div>
            );
          })}

          {/* Overall Summary Card */}
          <div className="relative group">
            <button
              onClick={() => setShowOverallModal(true)}
              className="px-3 py-2 rounded-lg text-xs font-medium min-w-[100px] bg-gradient-to-br from-nifty-500 to-nifty-700 text-white hover:from-nifty-600 hover:to-nifty-800 transition-all text-left"
            >
              <div className="font-semibold flex items-center gap-1">
                <Activity className="w-3 h-3" />
                Overall
              </div>
              <div className="text-sm font-bold mt-0.5">
                {overallStats.avgDailyReturn >= 0 ? '+' : ''}{overallStats.avgDailyReturn.toFixed(1)}%
              </div>
              <div className="text-[10px] mt-0.5 text-white/80">
                {overallStats.overallAccuracy}% accurate
              </div>
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowOverallModal(true);
              }}
              className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-white dark:bg-slate-600 shadow-sm border border-gray-200 dark:border-slate-500 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-gray-100 dark:hover:bg-slate-500"
              title="How is overall return calculated?"
            >
              <HelpCircle className="w-2.5 h-2.5 text-gray-500 dark:text-gray-300" />
            </button>
          </div>
        </div>
      </div>

      {/* Selected Date Details */}
      {selectedDate && (
        <div className="card">
          <div className="p-3 border-b border-gray-100 dark:border-slate-700 bg-gray-50/50 dark:bg-slate-700/50">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <h2 className="font-semibold text-gray-900 dark:text-gray-100">
                {new Date(selectedDate).toLocaleDateString('en-IN', {
                  weekday: 'short',
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </h2>
              <div className="flex items-center gap-3 text-xs">
                <span className="flex items-center gap-1 text-green-600 dark:text-green-400">
                  <TrendingUp className="w-3 h-3" />
                  {getRecommendation(selectedDate)?.summary.buy} Buy
                </span>
                <span className="flex items-center gap-1 text-red-600 dark:text-red-400">
                  <TrendingDown className="w-3 h-3" />
                  {getRecommendation(selectedDate)?.summary.sell} Sell
                </span>
                <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                  <Minus className="w-3 h-3" />
                  {getRecommendation(selectedDate)?.summary.hold} Hold
                </span>
              </div>
            </div>
          </div>

          <div className="divide-y divide-gray-50 dark:divide-slate-700 max-h-[60vh] sm:max-h-[400px] overflow-y-auto">
            {Object.values(getRecommendation(selectedDate)?.analysis || {}).map((stock: StockAnalysis) => {
              const backtest = getBacktestResult(stock.symbol);
              // Use next-day return for the display
              const nextDayReturn = backtest?.actual_return_1d ?? 0;
              const isPositive = nextDayReturn >= 0;

              return (
                <Link
                  key={stock.symbol}
                  to={`/stock/${stock.symbol}`}
                  className="flex items-center justify-between px-3 py-2 hover:bg-gray-50 dark:hover:bg-slate-700/50 transition-colors group"
                >
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    <span className="font-medium text-gray-900 dark:text-gray-100 text-sm">{stock.symbol}</span>
                    <span className="text-xs text-gray-500 dark:text-gray-400 hidden sm:inline truncate">{stock.company_name}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    {/* Sparkline */}
                    {backtest && (
                      <Sparkline
                        data={backtest.price_history}
                        width={60}
                        height={24}
                        positive={isPositive}
                      />
                    )}
                    {/* Next-Day Return Badge */}
                    {backtest && (
                      <AccuracyBadge
                        correct={backtest.prediction_correct}
                        returnPercent={nextDayReturn}
                        size="small"
                      />
                    )}
                    <DecisionBadge decision={stock.decision} size="small" />
                    <ChevronRight className="w-4 h-4 text-gray-300 dark:text-gray-600 group-hover:text-nifty-600 dark:group-hover:text-nifty-400" />
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* Performance Summary Cards */}
      <div className="card p-4">
        <div className="flex items-center gap-2 mb-3">
          <Activity className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />
          <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">Performance Summary</h2>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50 text-center">
            <div className="text-xl font-bold text-nifty-600 dark:text-nifty-400">{overallStats.totalDays}</div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Days Tracked</div>
          </div>
          <div className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50 text-center">
            <div className={`text-xl font-bold ${overallStats.avgDailyReturn >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
              {overallStats.avgDailyReturn >= 0 ? '+' : ''}{overallStats.avgDailyReturn.toFixed(1)}%
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Avg Next-Day Return</div>
          </div>
          <div className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50 text-center">
            <div className="text-xl font-bold text-green-600 dark:text-green-400">
              {sampleRecommendations.reduce((acc, r) => acc + r.summary.buy, 0)}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Buy Signals</div>
          </div>
          <div className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50 text-center">
            <div className="text-xl font-bold text-red-600 dark:text-red-400">
              {sampleRecommendations.reduce((acc, r) => acc + r.summary.sell, 0)}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Sell Signals</div>
          </div>
        </div>
        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-3 text-center">
          Next-day return = Price change on the trading day after recommendation
        </p>
      </div>

      {/* AI vs Nifty50 Index Comparison */}
      <section className="card p-4">
        <div className="flex items-center gap-2 mb-3">
          <BarChart3 className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">AI Strategy vs Nifty50 Index</h2>
        </div>
        <IndexComparisonChart height={220} />
        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-2 text-center">
          Comparison of cumulative returns between AI strategy and Nifty50 index
        </p>
      </section>

      {/* Return Distribution */}
      <section className="card p-4">
        <div className="flex items-center gap-2 mb-3">
          <PieChart className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">Return Distribution</h2>
        </div>
        <ReturnDistributionChart height={200} />
        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-2 text-center">
          Distribution of next-day returns across all predictions. Click bars to see stocks.
        </p>
      </section>

      {/* Accuracy Explanation Modal */}
      <AccuracyExplainModal
        isOpen={showAccuracyModal}
        onClose={() => setShowAccuracyModal(false)}
        metrics={accuracyMetrics}
      />

      {/* Return Calculation Modal */}
      <ReturnExplainModal
        isOpen={showReturnModal}
        onClose={() => setShowReturnModal(false)}
        breakdown={returnModalDate ? getReturnBreakdown(returnModalDate) : null}
        date={returnModalDate || ''}
      />

      {/* Overall Return Modal */}
      <OverallReturnModal
        isOpen={showOverallModal}
        onClose={() => setShowOverallModal(false)}
      />
    </div>
  );
}
