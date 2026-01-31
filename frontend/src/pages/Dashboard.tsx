import { useState, useMemo, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Calendar, RefreshCw, Filter, ChevronRight, TrendingUp, TrendingDown, Minus, History, Search, X, Play, Loader2 } from 'lucide-react';
import TopPicks, { StocksToAvoid } from '../components/TopPicks';
import { DecisionBadge } from '../components/StockCard';
import HowItWorks from '../components/HowItWorks';
import BackgroundSparkline from '../components/BackgroundSparkline';
import { getLatestRecommendation, getBacktestResult } from '../data/recommendations';
import { api } from '../services/api';
import { useSettings } from '../contexts/SettingsContext';
import type { Decision, StockAnalysis } from '../types';

type FilterType = 'ALL' | Decision;

export default function Dashboard() {
  const recommendation = getLatestRecommendation();
  const [filter, setFilter] = useState<FilterType>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const { settings } = useSettings();

  // Bulk analysis state
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState<{
    status: string;
    total: number;
    completed: number;
    failed: number;
    current_symbol: string | null;
  } | null>(null);

  // Check for running analysis on mount
  useEffect(() => {
    const checkAnalysisStatus = async () => {
      try {
        const status = await api.getBulkAnalysisStatus();
        if (status.status === 'running') {
          setIsAnalyzing(true);
          setAnalysisProgress(status);
        }
      } catch (e) {
        console.error('Failed to check analysis status:', e);
      }
    };
    checkAnalysisStatus();
  }, []);

  // Poll for analysis progress
  useEffect(() => {
    if (!isAnalyzing) return;

    const pollInterval = setInterval(async () => {
      try {
        const status = await api.getBulkAnalysisStatus();
        setAnalysisProgress(status);

        if (status.status === 'completed' || status.status === 'idle') {
          setIsAnalyzing(false);
          clearInterval(pollInterval);
          // Refresh the page to show updated data
          window.location.reload();
        }
      } catch (e) {
        console.error('Failed to poll analysis status:', e);
      }
    }, 3000);

    return () => clearInterval(pollInterval);
  }, [isAnalyzing]);

  const handleAnalyzeAll = async () => {
    if (isAnalyzing) return;

    setIsAnalyzing(true);
    setAnalysisProgress({
      status: 'starting',
      total: 50,
      completed: 0,
      failed: 0,
      current_symbol: null
    });

    try {
      // Pass settings from context to the API
      await api.runBulkAnalysis(undefined, {
        deep_think_model: settings.deepThinkModel,
        quick_think_model: settings.quickThinkModel,
        provider: settings.provider,
        api_key: settings.provider === 'anthropic_api' ? settings.anthropicApiKey : undefined,
        max_debate_rounds: settings.maxDebateRounds
      });
    } catch (e) {
      console.error('Failed to start bulk analysis:', e);
      setIsAnalyzing(false);
      setAnalysisProgress(null);
    }
  };

  if (!recommendation) {
    return (
      <div className="min-h-[40vh] flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-10 h-10 text-gray-300 mx-auto mb-3 animate-spin" />
          <h2 className="text-lg font-semibold text-gray-700">Loading recommendations...</h2>
        </div>
      </div>
    );
  }

  const stocks = Object.values(recommendation.analysis);
  const filteredStocks = useMemo(() => {
    let result = filter === 'ALL' ? stocks : stocks.filter(s => s.decision === filter);
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(s =>
        s.symbol.toLowerCase().includes(query) ||
        s.company_name.toLowerCase().includes(query)
      );
    }
    return result;
  }, [stocks, filter, searchQuery]);

  const { buy, sell, hold, total } = recommendation.summary;
  const buyPct = ((buy / total) * 100).toFixed(0);
  const holdPct = ((hold / total) * 100).toFixed(0);
  const sellPct = ((sell / total) * 100).toFixed(0);

  return (
    <div className="space-y-4">
      {/* Compact Header with Stats */}
      <section className="card p-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-display font-bold text-gray-900 dark:text-gray-100">
              Nifty 50 <span className="gradient-text">AI Recommendations</span>
            </h1>
            <div className="flex items-center gap-2 mt-1 text-sm text-gray-500 dark:text-gray-400">
              <Calendar className="w-3.5 h-3.5" />
              <span>{new Date(recommendation.date).toLocaleDateString('en-IN', {
                weekday: 'short',
                month: 'short',
                day: 'numeric',
                year: 'numeric',
              })}</span>
            </div>
          </div>

          {/* Analyze All Button + Inline Stats */}
          <div className="flex items-center gap-3" role="group" aria-label="Summary statistics">
            {/* Analyze All Button */}
            <button
              onClick={handleAnalyzeAll}
              disabled={isAnalyzing}
              className={`
                flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all
                ${isAnalyzing
                  ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 cursor-not-allowed'
                  : 'bg-nifty-600 text-white hover:bg-nifty-700 shadow-sm hover:shadow-md'
                }
              `}
              title={isAnalyzing ? 'Analysis in progress...' : 'Run AI analysis for all 50 stocks'}
            >
              {isAnalyzing ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              {isAnalyzing ? 'Analyzing...' : 'Analyze All'}
            </button>

            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-green-50 dark:bg-green-900/30 rounded-lg cursor-pointer hover:bg-green-100 dark:hover:bg-green-900/50 transition-colors" onClick={() => setFilter('BUY')} title="Click to filter Buy stocks">
              <TrendingUp className="w-4 h-4 text-green-600 dark:text-green-400" aria-hidden="true" />
              <span className="font-bold text-green-700 dark:text-green-400">{buy}</span>
              <span className="text-xs text-green-600 dark:text-green-400">Buy ({buyPct}%)</span>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-50 dark:bg-amber-900/30 rounded-lg cursor-pointer hover:bg-amber-100 dark:hover:bg-amber-900/50 transition-colors" onClick={() => setFilter('HOLD')} title="Click to filter Hold stocks">
              <Minus className="w-4 h-4 text-amber-600 dark:text-amber-400" aria-hidden="true" />
              <span className="font-bold text-amber-700 dark:text-amber-400">{hold}</span>
              <span className="text-xs text-amber-600 dark:text-amber-400">Hold ({holdPct}%)</span>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-red-50 dark:bg-red-900/30 rounded-lg cursor-pointer hover:bg-red-100 dark:hover:bg-red-900/50 transition-colors" onClick={() => setFilter('SELL')} title="Click to filter Sell stocks">
              <TrendingDown className="w-4 h-4 text-red-600 dark:text-red-400" aria-hidden="true" />
              <span className="font-bold text-red-700 dark:text-red-400">{sell}</span>
              <span className="text-xs text-red-600 dark:text-red-400">Sell ({sellPct}%)</span>
            </div>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mt-3">
          <div className="flex h-2 rounded-full overflow-hidden bg-gray-100 dark:bg-slate-700">
            <div className="bg-green-500 transition-all" style={{ width: `${buyPct}%` }} />
            <div className="bg-amber-500 transition-all" style={{ width: `${holdPct}%` }} />
            <div className="bg-red-500 transition-all" style={{ width: `${sellPct}%` }} />
          </div>
        </div>

        {/* Analysis Progress Banner */}
        {isAnalyzing && analysisProgress && (
          <div className="mt-3 p-3 bg-blue-50 dark:bg-blue-900/30 rounded-lg border border-blue-200 dark:border-blue-800">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-blue-600 dark:text-blue-400" />
                <span className="text-sm font-medium text-blue-700 dark:text-blue-300">
                  Analyzing {analysisProgress.current_symbol || 'stocks'}...
                </span>
              </div>
              <span className="text-xs text-blue-600 dark:text-blue-400">
                {analysisProgress.completed + analysisProgress.failed} / {analysisProgress.total} stocks
              </span>
            </div>
            <div className="w-full bg-blue-200 dark:bg-blue-800 rounded-full h-2">
              <div
                className="bg-blue-600 dark:bg-blue-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${((analysisProgress.completed + analysisProgress.failed) / analysisProgress.total) * 100}%` }}
              />
            </div>
            {analysisProgress.failed > 0 && (
              <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                {analysisProgress.failed} failed
              </p>
            )}
          </div>
        )}
      </section>

      {/* How It Works Section */}
      <HowItWorks collapsed={true} />

      {/* Top Picks and Avoid Section - Side by Side Compact */}
      <div className="grid lg:grid-cols-2 gap-4">
        <TopPicks picks={recommendation.top_picks} />
        <StocksToAvoid stocks={recommendation.stocks_to_avoid} />
      </div>

      {/* All Stocks Section with Integrated Filter */}
      <section className="card">
        <div className="p-3 border-b border-gray-100 dark:border-slate-700 bg-gray-50/50 dark:bg-slate-700/50">
          <div className="flex flex-col gap-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-gray-400 dark:text-gray-500" />
                <h2 className="font-semibold text-gray-900 dark:text-gray-100">All {total} Stocks</h2>
              </div>
              <div className="flex gap-1.5" role="group" aria-label="Filter stocks by recommendation">
              <button
                onClick={() => setFilter('ALL')}
                aria-pressed={filter === 'ALL'}
                className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all focus:outline-none focus:ring-2 focus:ring-nifty-500 focus:ring-offset-1 dark:focus:ring-offset-slate-800 ${
                  filter === 'ALL'
                    ? 'bg-nifty-600 text-white shadow-sm'
                    : 'bg-gray-100 dark:bg-slate-600 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-slate-500'
                }`}
              >
                All ({total})
              </button>
              <button
                onClick={() => setFilter('BUY')}
                aria-pressed={filter === 'BUY'}
                className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-1 dark:focus:ring-offset-slate-800 ${
                  filter === 'BUY'
                    ? 'bg-green-600 text-white shadow-sm'
                    : 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900/50'
                }`}
              >
                Buy ({buy})
              </button>
              <button
                onClick={() => setFilter('HOLD')}
                aria-pressed={filter === 'HOLD'}
                className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-1 dark:focus:ring-offset-slate-800 ${
                  filter === 'HOLD'
                    ? 'bg-amber-600 text-white shadow-sm'
                    : 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 hover:bg-amber-100 dark:hover:bg-amber-900/50'
                }`}
              >
                Hold ({hold})
              </button>
              <button
                onClick={() => setFilter('SELL')}
                aria-pressed={filter === 'SELL'}
                className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1 dark:focus:ring-offset-slate-800 ${
                  filter === 'SELL'
                    ? 'bg-red-600 text-white shadow-sm'
                    : 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/50'
                }`}
              >
                Sell ({sell})
              </button>
              </div>
            </div>
            {/* Search Bar */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500" />
              <input
                type="text"
                placeholder="Search by symbol or company name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-9 py-2 text-sm rounded-lg border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-nifty-500 focus:border-transparent"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="p-2 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2 max-h-[400px] overflow-y-auto" role="list" aria-label="Stock recommendations list">
          {filteredStocks.map((stock: StockAnalysis) => {
            const backtest = getBacktestResult(stock.symbol);
            const trend = stock.decision === 'BUY' ? 'up' : stock.decision === 'SELL' ? 'down' : 'flat';
            return (
              <Link
                key={stock.symbol}
                to={`/stock/${stock.symbol}`}
                className="card-hover p-2 group relative overflow-hidden"
                role="listitem"
              >
                {/* Background Chart */}
                {backtest && (
                  <div className="absolute inset-0 opacity-[0.06]">
                    <BackgroundSparkline
                      data={backtest.price_history.slice(-15)}
                      trend={trend}
                    />
                  </div>
                )}

                {/* Content */}
                <div className="relative z-10">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span className="font-semibold text-sm text-gray-900 dark:text-gray-100">{stock.symbol}</span>
                    <DecisionBadge decision={stock.decision} size="small" />
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{stock.company_name}</p>
                </div>
              </Link>
            );
          })}
        </div>

        {filteredStocks.length === 0 && (
          <div className="p-8 text-center">
            <p className="text-gray-500 dark:text-gray-400 text-sm">No stocks match the selected filter.</p>
          </div>
        )}
      </section>

      {/* Compact CTA */}
      <Link
        to="/history"
        className="card flex items-center justify-between p-4 bg-gradient-to-r from-nifty-600 to-nifty-700 text-white hover:from-nifty-700 hover:to-nifty-800 transition-all group focus:outline-none focus:ring-2 focus:ring-nifty-500 focus:ring-offset-2"
        aria-label="View historical stock recommendations"
      >
        <div className="flex items-center gap-3">
          <History className="w-5 h-5" aria-hidden="true" />
          <span className="font-semibold">View Historical Recommendations</span>
        </div>
        <ChevronRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" aria-hidden="true" />
      </Link>
    </div>
  );
}
