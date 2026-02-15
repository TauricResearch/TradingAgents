import { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Calendar, RefreshCw, Filter, ChevronRight, TrendingUp, TrendingDown, Minus, History, Search, X, Play, Loader2, Square, AlertCircle, Terminal } from 'lucide-react';
import TopPicks, { StocksToAvoid } from '../components/TopPicks';
import { DecisionBadge, HoldDaysBadge, RankBadge } from '../components/StockCard';
import TerminalModal from '../components/TerminalModal';
import HowItWorks from '../components/HowItWorks';
import { api } from '../services/api';
import { useSettings } from '../contexts/SettingsContext';
import { useNotification } from '../contexts/NotificationContext';
import { NIFTY_50_STOCKS } from '../types';
import type { Decision, StockAnalysis, DailyRecommendation, NiftyStock } from '../types';

type FilterType = 'ALL' | Decision;

export default function Dashboard() {
  // State for real API data
  const [recommendation, setRecommendation] = useState<DailyRecommendation | null>(null);
  const [isLoadingData, setIsLoadingData] = useState(true);

  // Fetch recommendation from API
  const fetchRecommendation = useCallback(async () => {
    setIsLoadingData(true);
    try {
      const data = await api.getLatestRecommendation();
      if (data && data.analysis && Object.keys(data.analysis).length > 0) {
        setRecommendation(data);
      }
    } catch (error) {
      console.error('Failed to fetch recommendation from API:', error);
    } finally {
      setIsLoadingData(false);
    }
  }, []);

  // Fetch on mount
  useEffect(() => {
    fetchRecommendation();
  }, [fetchRecommendation]);
  const [filter, setFilter] = useState<FilterType>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'rank' | 'symbol'>('rank');
  const { settings } = useSettings();
  const { addNotification } = useNotification();

  // Terminal modal state
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);

  // Track completed count to trigger incremental re-fetch
  const prevCompletedRef = useRef(0);

  // Bulk analysis state — initialize from localStorage for instant display on refresh
  const [isAnalyzing, setIsAnalyzing] = useState(() => {
    try {
      return localStorage.getItem('bulkAnalysisRunning') === 'true';
    } catch { return false; }
  });
  const [isCancelling, setIsCancelling] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState<{
    status: string;
    total: number;
    completed: number;
    failed: number;
    skipped?: number;
    current_symbol: string | null;
    current_symbols: string[];
    results: Record<string, string>;
    parallel_workers?: number;
    stock_progress?: Record<string, { done: number; total: number; current: string | null }>;
  } | null>(() => {
    try {
      const saved = localStorage.getItem('bulkAnalysisProgress');
      return saved ? JSON.parse(saved) : null;
    } catch { return null; }
  });

  // Persist analysis state to localStorage
  const updateAnalysisState = useCallback((analyzing: boolean, progress: typeof analysisProgress) => {
    setIsAnalyzing(analyzing);
    setAnalysisProgress(progress);
    try {
      if (analyzing) {
        localStorage.setItem('bulkAnalysisRunning', 'true');
        if (progress) localStorage.setItem('bulkAnalysisProgress', JSON.stringify(progress));
      } else {
        localStorage.removeItem('bulkAnalysisRunning');
        localStorage.removeItem('bulkAnalysisProgress');
      }
    } catch { /* localStorage unavailable */ }
  }, []);

  // Validate analysis state against backend on mount
  useEffect(() => {
    const checkAnalysisStatus = async () => {
      try {
        const status = await api.getBulkAnalysisStatus();
        if (status.status === 'running') {
          updateAnalysisState(true, status);
        } else if (isAnalyzing) {
          // localStorage said running but backend says otherwise (server restarted)
          updateAnalysisState(false, null);
        }
      } catch (e) {
        console.error('Failed to check analysis status:', e);
      }
    };
    checkAnalysisStatus();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll for analysis progress + incremental re-fetch
  useEffect(() => {
    if (!isAnalyzing) return;

    const pollInterval = setInterval(async () => {
      try {
        const status = await api.getBulkAnalysisStatus();
        // Persist progress to localStorage on every poll
        updateAnalysisState(true, status);

        // Incremental re-fetch: when completed count increases, refresh recommendation data
        const newCompleted = status.completed + (status.skipped || 0);
        if (newCompleted > prevCompletedRef.current) {
          prevCompletedRef.current = newCompleted;
          try {
            const data = await api.getLatestRecommendation();
            if (data && data.analysis && Object.keys(data.analysis).length > 0) {
              setRecommendation(data);
              setIsUsingMockData(false);
            }
          } catch (e) {
            console.warn('Re-fetch during analysis failed:', e);
          }
        }

        if (status.status === 'completed') {
          updateAnalysisState(false, null);
          prevCompletedRef.current = 0;
          clearInterval(pollInterval);
          // Final re-fetch for complete dataset
          fetchRecommendation();
          addNotification({
            type: 'success',
            title: 'Analysis Complete',
            message: `Successfully analyzed ${status.completed} stocks.${status.skipped ? ` ${status.skipped} already analyzed (skipped).` : ''} ${status.failed > 0 ? `${status.failed} failed.` : ''}`,
            duration: 8000,
          });
        } else if (status.status === 'cancelled') {
          updateAnalysisState(false, null);
          prevCompletedRef.current = 0;
          setIsCancelling(false);
          clearInterval(pollInterval);
          fetchRecommendation();
          addNotification({
            type: 'warning',
            title: 'Analysis Cancelled',
            message: `Cancelled after analyzing ${status.completed} stocks.`,
            duration: 5000,
          });
        } else if (status.status === 'idle') {
          updateAnalysisState(false, null);
          prevCompletedRef.current = 0;
          clearInterval(pollInterval);
        }
      } catch (e) {
        console.error('Failed to poll analysis status:', e);
      }
    }, 3000);

    return () => clearInterval(pollInterval);
  }, [isAnalyzing, addNotification, updateAnalysisState, fetchRecommendation]);

  const handleAnalyzeAll = async () => {
    if (isAnalyzing) return;

    const initialProgress = {
      status: 'starting',
      total: 50,
      completed: 0,
      failed: 0,
      current_symbol: null as string | null
    };
    updateAnalysisState(true, initialProgress);

    try {
      // Pass settings from context to the API
      const result = await api.runBulkAnalysis(undefined, {
        deep_think_model: settings.deepThinkModel,
        quick_think_model: settings.quickThinkModel,
        provider: settings.provider,
        api_key: settings.provider === 'anthropic_api' ? settings.anthropicApiKey : undefined,
        max_debate_rounds: settings.maxDebateRounds,
        parallel_workers: settings.parallelWorkers
      });

      // If all stocks already analyzed, exit analyzing mode
      if (result.status === 'completed' || result.total_stocks === 0) {
        updateAnalysisState(false, null);
        addNotification({
          type: 'info',
          title: 'Already Analyzed',
          message: result.skipped
            ? `All ${result.skipped} stocks already analyzed for today.`
            : 'All stocks already analyzed for today.',
          duration: 5000,
        });
        return;
      }

      addNotification({
        type: 'info',
        title: 'Analysis Started',
        message: `Running AI analysis for ${result.total_stocks} stocks${result.skipped ? ` (${result.skipped} already done)` : ''}...`,
        duration: 3000,
      });
    } catch (e) {
      console.error('Failed to start bulk analysis:', e);
      updateAnalysisState(false, null);
      addNotification({
        type: 'error',
        title: 'Analysis Failed',
        message: 'Failed to start bulk analysis. Please try again.',
        duration: 5000,
      });
    }
  };

  const handleCancelAnalysis = async () => {
    if (!isAnalyzing || isCancelling) return;

    setIsCancelling(true);
    try {
      await api.cancelBulkAnalysis();
      addNotification({
        type: 'info',
        title: 'Cancelling...',
        message: 'Stopping analysis after current stocks complete.',
        duration: 3000,
      });
    } catch (e) {
      console.error('Failed to cancel analysis:', e);
      setIsCancelling(false);
      addNotification({
        type: 'error',
        title: 'Cancel Failed',
        message: 'Failed to cancel analysis.',
        duration: 3000,
      });
    }
  };

  // Live state for each stock in the grid
  type StockLiveState = 'completed' | 'analyzing' | 'pending' | 'failed';
  interface StockGridItem {
    symbol: string;
    company_name: string;
    liveState: StockLiveState;
    analysis: StockAnalysis | null;
  }

  // Build unified stock grid: during analysis show all 50, otherwise only analyzed
  const stockGridItems = useMemo((): StockGridItem[] => {
    if (!isAnalyzing || !analysisProgress) {
      // Normal mode: only show analyzed stocks
      return (recommendation ? Object.values(recommendation.analysis) : []).map(s => ({
        symbol: s.symbol,
        company_name: s.company_name,
        liveState: 'completed' as StockLiveState,
        analysis: s,
      }));
    }

    // Analysis mode: show all 50 stocks with live states
    const analysisResults = analysisProgress.results || {};
    const currentSymbols = new Set(analysisProgress.current_symbols || []);
    const analysisMap = recommendation?.analysis || {};

    return NIFTY_50_STOCKS.map((niftyStock: NiftyStock): StockGridItem => {
      const { symbol } = niftyStock;
      const resultStatus = analysisResults[symbol];
      const existingAnalysis = analysisMap[symbol] || null;

      let liveState: StockLiveState;
      if (existingAnalysis) {
        liveState = 'completed';
      } else if (resultStatus === 'completed') {
        liveState = 'completed'; // just completed, data not re-fetched yet
      } else if (resultStatus && resultStatus.startsWith('error')) {
        liveState = 'failed';
      } else if (currentSymbols.has(symbol)) {
        liveState = 'analyzing';
      } else {
        liveState = 'pending';
      }

      return {
        symbol,
        company_name: niftyStock.company_name,
        liveState,
        analysis: existingAnalysis,
      };
    });
  }, [isAnalyzing, analysisProgress, recommendation]);

  // Filter grid items based on filter and search query, then sort
  const filteredItems = useMemo(() => {
    let result = stockGridItems;
    if (filter !== 'ALL') {
      // During analysis, show matching completed + all non-completed (so progress stays visible)
      result = result.filter(item =>
        item.liveState !== 'completed' || item.analysis?.decision === filter
      );
    }
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(item =>
        item.symbol.toLowerCase().includes(query) ||
        item.company_name.toLowerCase().includes(query)
      );
    }
    if (sortBy === 'rank') {
      result = [...result].sort((a, b) => {
        const aRank = a.analysis?.rank ?? Infinity;
        const bRank = b.analysis?.rank ?? Infinity;
        if (aRank !== bRank) return aRank - bRank;
        return a.symbol.localeCompare(b.symbol);
      });
    }
    return result;
  }, [stockGridItems, filter, searchQuery, sortBy]);

  // Show loading state — but also include analysis progress banner if running
  if (isLoadingData || !recommendation) {
    return (
      <div className="space-y-4">
        {isAnalyzing && analysisProgress && (
          <div className="p-3 bg-blue-50 dark:bg-blue-900/30 rounded-lg border border-blue-200 dark:border-blue-800">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-blue-600 dark:text-blue-400" />
                <span className="text-sm font-medium text-blue-700 dark:text-blue-300">
                  {isCancelling ? 'Cancelling...' : `Analyzing ${analysisProgress.current_symbols?.length > 0 ? analysisProgress.current_symbols.join(', ') : analysisProgress.current_symbol || 'stocks'}...`}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-blue-600 dark:text-blue-400">
                  {analysisProgress.completed + analysisProgress.failed} / {analysisProgress.total} stocks
                  {analysisProgress.skipped ? ` (${analysisProgress.skipped} skipped)` : ''}
                </span>
                <button
                  onClick={handleCancelAnalysis}
                  disabled={isCancelling}
                  className={`
                    flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md transition-all
                    ${isCancelling
                      ? 'bg-gray-200 text-gray-500 cursor-not-allowed dark:bg-gray-700 dark:text-gray-400'
                      : 'bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50'
                    }
                  `}
                  title="Cancel analysis"
                >
                  <Square className="w-3 h-3" />
                  {isCancelling ? 'Cancelling...' : 'Cancel'}
                </button>
              </div>
            </div>
            <div className="w-full bg-blue-200 dark:bg-blue-800 rounded-full h-2">
              <div
                className="bg-blue-600 dark:bg-blue-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${analysisProgress.total > 0 ? ((analysisProgress.completed + analysisProgress.failed) / analysisProgress.total) * 100 : 0}%` }}
              />
            </div>
            {analysisProgress.failed > 0 && (
              <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                {analysisProgress.failed} failed
              </p>
            )}
          </div>
        )}
        <div className="min-h-[40vh] flex items-center justify-center">
          <div className="text-center">
            <RefreshCw className="w-10 h-10 text-gray-300 mx-auto mb-3 animate-spin" />
            <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300">Loading recommendations...</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Fetching data from API...</p>
          </div>
        </div>
      </div>
    );
  }

  const { buy, sell, hold, total: analyzedTotal } = recommendation.summary;
  const total = isAnalyzing ? 50 : analyzedTotal;
  const buyPct = total > 0 ? ((buy / total) * 100).toFixed(0) : '0';
  const holdPct = total > 0 ? ((hold / total) * 100).toFixed(0) : '0';
  const sellPct = total > 0 ? ((sell / total) * 100).toFixed(0) : '0';

  return (
    <div className="space-y-4">
      {/* Compact Header with Stats */}
      <section className="card p-5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-display font-bold text-gray-900 dark:text-gray-100 tracking-tight">
              Nifty 50 <span className="gradient-text">AI Recommendations</span>
            </h1>
            <div className="flex items-center gap-2 mt-1.5 text-sm text-gray-500 dark:text-gray-400">
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
          <div className="flex flex-wrap items-center gap-2 sm:gap-3" role="group" aria-label="Summary statistics">
            {/* Analyze All Button */}
            <button
              onClick={handleAnalyzeAll}
              disabled={isAnalyzing}
              className={`
                flex items-center gap-2 px-3 sm:px-4 py-1.5 sm:py-2 rounded-lg text-sm font-semibold transition-all
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
              <span className="hidden sm:inline">{isAnalyzing ? 'Analyzing...' : 'Analyze All'}</span>
              <span className="sm:hidden">{isAnalyzing ? '...' : 'All'}</span>
            </button>

            {/* Terminal Button - View Live Logs */}
            <button
              onClick={() => setIsTerminalOpen(true)}
              className={`
                flex items-center justify-center p-1.5 sm:p-2 rounded-lg text-sm transition-all
                ${isAnalyzing
                  ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 animate-pulse'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600'
                }
              `}
              title="View live analysis terminal"
            >
              <Terminal className="w-4 h-4" />
            </button>

            <div className="flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1 sm:py-1.5 bg-green-50 dark:bg-green-900/30 rounded-lg cursor-pointer hover:bg-green-100 dark:hover:bg-green-900/50 transition-colors" onClick={() => setFilter('BUY')} title="Click to filter Buy stocks">
              <TrendingUp className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-green-600 dark:text-green-400" aria-hidden="true" />
              <span className="font-bold text-sm sm:text-base text-green-700 dark:text-green-400">{buy}</span>
              <span className="text-xs text-green-600 dark:text-green-400 hidden sm:inline">Buy ({buyPct}%)</span>
            </div>
            <div className="flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1 sm:py-1.5 bg-amber-50 dark:bg-amber-900/30 rounded-lg cursor-pointer hover:bg-amber-100 dark:hover:bg-amber-900/50 transition-colors" onClick={() => setFilter('HOLD')} title="Click to filter Hold stocks">
              <Minus className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-amber-600 dark:text-amber-400" aria-hidden="true" />
              <span className="font-bold text-sm sm:text-base text-amber-700 dark:text-amber-400">{hold}</span>
              <span className="text-xs text-amber-600 dark:text-amber-400 hidden sm:inline">Hold ({holdPct}%)</span>
            </div>
            <div className="flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1 sm:py-1.5 bg-red-50 dark:bg-red-900/30 rounded-lg cursor-pointer hover:bg-red-100 dark:hover:bg-red-900/50 transition-colors" onClick={() => setFilter('SELL')} title="Click to filter Sell stocks">
              <TrendingDown className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-red-600 dark:text-red-400" aria-hidden="true" />
              <span className="font-bold text-sm sm:text-base text-red-700 dark:text-red-400">{sell}</span>
              <span className="text-xs text-red-600 dark:text-red-400 hidden sm:inline">Sell ({sellPct}%)</span>
            </div>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mt-4">
          <div className="flex h-1.5 rounded-full overflow-hidden bg-gray-100 dark:bg-slate-700/50">
            <div className="transition-all duration-500 rounded-l-full" style={{ width: `${buyPct}%`, background: 'linear-gradient(90deg, #10b981, #059669)' }} />
            <div className="transition-all duration-500" style={{ width: `${holdPct}%`, background: 'linear-gradient(90deg, #f59e0b, #d97706)' }} />
            <div className="transition-all duration-500 rounded-r-full" style={{ width: `${sellPct}%`, background: 'linear-gradient(90deg, #ef4444, #dc2626)' }} />
          </div>
        </div>

        {/* Analysis Progress Banner */}
        {isAnalyzing && analysisProgress && (
          <div className="mt-3 p-3 bg-blue-50 dark:bg-blue-900/30 rounded-lg border border-blue-200 dark:border-blue-800">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-blue-600 dark:text-blue-400" />
                <span className="text-sm font-medium text-blue-700 dark:text-blue-300">
                  {isCancelling ? 'Cancelling...' : (
                    <>
                      Analyzing{' '}
                      {analysisProgress.current_symbols?.length > 0
                        ? analysisProgress.current_symbols.join(', ')
                        : analysisProgress.current_symbol || 'stocks'}
                      ...
                    </>
                  )}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-blue-600 dark:text-blue-400">
                  {analysisProgress.completed + analysisProgress.failed} / {analysisProgress.total} stocks
                  {analysisProgress.skipped ? ` (${analysisProgress.skipped} skipped)` : ''}
                </span>
                <button
                  onClick={handleCancelAnalysis}
                  disabled={isCancelling}
                  className={`
                    flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md transition-all
                    ${isCancelling
                      ? 'bg-gray-200 text-gray-500 cursor-not-allowed dark:bg-gray-700 dark:text-gray-400'
                      : 'bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50'
                    }
                  `}
                  title="Cancel analysis"
                >
                  <Square className="w-3 h-3" />
                  {isCancelling ? 'Cancelling...' : 'Cancel'}
                </button>
              </div>
            </div>
            <div className="w-full bg-blue-200 dark:bg-blue-800 rounded-full h-2">
              <div
                className="bg-blue-600 dark:bg-blue-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${analysisProgress.total > 0 ? ((analysisProgress.completed + analysisProgress.failed) / analysisProgress.total) * 100 : 0}%` }}
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
        {recommendation.top_picks.length > 0 && (
          <TopPicks picks={recommendation.top_picks} />
        )}
        <StocksToAvoid stocks={recommendation.stocks_to_avoid} />
      </div>

      {/* All Stocks Section with Integrated Filter */}
      <section className="card">
        <div className="p-4 border-b border-gray-100/80 dark:border-slate-700/40">
          <div className="flex flex-col gap-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-gray-400 dark:text-gray-500" />
                <h2 className="font-display font-bold text-gray-900 dark:text-gray-100 text-sm tracking-tight">
                  {isAnalyzing ? `All 50 Stocks (${analysisProgress?.completed || 0} analyzed)` : `All ${total} Stocks`}
                </h2>
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
              <span className="mx-0.5 text-gray-300 dark:text-gray-600">|</span>
              <button
                onClick={() => setSortBy(sortBy === 'rank' ? 'symbol' : 'rank')}
                className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all focus:outline-none focus:ring-2 focus:ring-nifty-500 focus:ring-offset-1 dark:focus:ring-offset-slate-800 ${
                  sortBy === 'rank'
                    ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'
                    : 'bg-gray-100 dark:bg-slate-600 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-slate-500'
                }`}
              >
                {sortBy === 'rank' ? '#Rank' : 'A-Z'}
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
          {filteredItems.map((item) => {
            // COMPLETED with analysis data: clickable link
            if (item.liveState === 'completed' && item.analysis) {
              return (
                <Link
                  key={item.symbol}
                  to={`/stock/${item.symbol}`}
                  className="card-hover p-2 group relative overflow-hidden"
                  role="listitem"
                >
                  <div className="relative z-10">
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <RankBadge rank={item.analysis.rank} size="small" />
                      <span className="font-semibold text-sm text-gray-900 dark:text-gray-100">{item.symbol}</span>
                      <DecisionBadge decision={item.analysis.decision} size="small" />
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{item.company_name}</p>
                    {item.analysis.hold_days != null && item.analysis.hold_days > 0 && item.analysis.decision !== 'SELL' && (
                      <div className="mt-1">
                        <HoldDaysBadge holdDays={item.analysis.hold_days} decision={item.analysis.decision} />
                      </div>
                    )}
                  </div>
                </Link>
              );
            }

            // COMPLETED but data not re-fetched yet (brief transition)
            if (item.liveState === 'completed' && !item.analysis) {
              return (
                <div key={item.symbol} className="p-2 rounded-xl border border-green-200 dark:border-green-800 bg-green-50/30 dark:bg-green-900/10" role="listitem">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span className="font-semibold text-sm text-green-700 dark:text-green-300">{item.symbol}</span>
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-green-100 dark:bg-green-900/50 text-green-600 dark:text-green-400">
                      Done
                    </span>
                  </div>
                  <p className="text-xs text-green-500 dark:text-green-400 truncate">{item.company_name}</p>
                </div>
              );
            }

            // ANALYZING: shimmer effect with step progress
            if (item.liveState === 'analyzing') {
              const progress = analysisProgress?.stock_progress?.[item.symbol];
              const stepsDone = progress?.done ?? 0;
              const stepsTotal = progress?.total ?? 12;
              return (
                <div key={item.symbol} className="p-2 rounded-xl border border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-900/20 overflow-hidden relative" role="listitem">
                  <div className="absolute inset-0 shimmer-effect" />
                  <div className="relative z-10">
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="font-semibold text-sm text-blue-700 dark:text-blue-300">{item.symbol}</span>
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400 gap-0.5">
                        <Loader2 className="w-2.5 h-2.5 animate-spin" />
                        <span className="hidden sm:inline">Analyzing</span>
                      </span>
                    </div>
                    <p className="text-xs text-blue-500 dark:text-blue-400 truncate">{item.company_name}</p>
                    {/* Step progress bar */}
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <div className="flex-1 h-1 bg-blue-200 dark:bg-blue-800 rounded-full overflow-hidden">
                        <div
                          className="h-1 bg-blue-500 dark:bg-blue-400 rounded-full transition-all duration-500"
                          style={{ width: `${stepsTotal > 0 ? (stepsDone / stepsTotal) * 100 : 0}%` }}
                        />
                      </div>
                      <span className="text-[10px] font-mono text-blue-500 dark:text-blue-400 whitespace-nowrap">
                        {stepsDone}/{stepsTotal}
                      </span>
                    </div>
                  </div>
                </div>
              );
            }

            // FAILED: error state
            if (item.liveState === 'failed') {
              return (
                <div key={item.symbol} className="p-2 rounded-xl border border-red-200 dark:border-red-800 bg-red-50/30 dark:bg-red-900/10 opacity-75" role="listitem">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span className="font-semibold text-sm text-red-700 dark:text-red-400">{item.symbol}</span>
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 gap-0.5">
                      <AlertCircle className="w-2.5 h-2.5" />
                      Failed
                    </span>
                  </div>
                  <p className="text-xs text-red-500 dark:text-red-400 truncate">{item.company_name}</p>
                </div>
              );
            }

            // PENDING: grayed out, waiting
            return (
              <div key={item.symbol} className="p-2 rounded-xl border border-gray-200 dark:border-slate-700 bg-gray-50/50 dark:bg-slate-800/50 opacity-50" role="listitem">
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span className="font-semibold text-sm text-gray-400 dark:text-gray-500">{item.symbol}</span>
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 dark:bg-slate-700 text-gray-400 dark:text-gray-500">
                    Queued
                  </span>
                </div>
                <p className="text-xs text-gray-400 dark:text-gray-600 truncate">{item.company_name}</p>
              </div>
            );
          })}
        </div>

        {filteredItems.length === 0 && (
          <div className="p-8 text-center">
            <p className="text-gray-500 dark:text-gray-400 text-sm">No stocks match the selected filter.</p>
          </div>
        )}
      </section>

      {/* Compact CTA */}
      <Link
        to="/history"
        className="flex items-center justify-between p-4 rounded-xl text-white group focus:outline-none focus:ring-2 focus:ring-nifty-500 focus:ring-offset-2 transition-all hover:shadow-lg"
        style={{
          background: 'linear-gradient(135deg, #0284c7, #0369a1)',
          boxShadow: '0 2px 8px rgba(2, 132, 199, 0.25)',
        }}
        aria-label="View historical stock recommendations"
      >
        <div className="flex items-center gap-3">
          <History className="w-5 h-5 opacity-80" aria-hidden="true" />
          <span className="font-display font-bold tracking-tight">View Historical Recommendations</span>
        </div>
        <ChevronRight className="w-5 h-5 group-hover:translate-x-1 transition-transform opacity-80" aria-hidden="true" />
      </Link>

      {/* Terminal Modal */}
      <TerminalModal
        isOpen={isTerminalOpen}
        onClose={() => setIsTerminalOpen(false)}
        isAnalyzing={isAnalyzing}
      />
    </div>
  );
}
