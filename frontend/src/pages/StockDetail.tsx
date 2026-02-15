import { useParams, Link } from 'react-router-dom';
import { useMemo, useState, useEffect, useCallback } from 'react';
import {
  ArrowLeft, Building2, TrendingUp, TrendingDown, Minus, AlertTriangle,
  Calendar, Activity, LineChart, Database, MessageSquare, Layers,
  RefreshCw, Play, Loader2, CheckCircle, XCircle, Target, BarChart3, Square
} from 'lucide-react';
import { NIFTY_50_STOCKS } from '../types';
import type { DailyRecommendation, StockAnalysis } from '../types';
import { DecisionBadge, ConfidenceBadge, RiskBadge, HoldDaysBadge, RankBadge } from '../components/StockCard';
import AIAnalysisPanel from '../components/AIAnalysisPanel';
import StockPriceChart from '../components/StockPriceChart';
import {
  PipelineFlowchart,
  DebateViewer,
  RiskDebateViewer,
  DataSourcesPanel
} from '../components/pipeline';
import { api } from '../services/api';
import { useSettings } from '../contexts/SettingsContext';
import type { FullPipelineData, PipelineStep, PipelineStepStatus } from '../types/pipeline';

// Type for real backtest data from API
interface BacktestResult {
  date: string;
  decision: string;
  return1d: number | null;
  return1w: number | null;
  returnAtHold: number | null;
  holdDays: number | null;
  primaryReturn: number | null;  // return_at_hold ?? return_1d
  predictionCorrect: boolean | null;
  rank?: number | null;
  isLoading?: boolean;
}

// Type for prediction stats calculated from real data
interface PredictionStats {
  totalPredictions: number;
  correctPredictions: number;
  accuracy: number;
  avgReturn: number;
  buyAccuracy: number;
  sellAccuracy: number;
  holdAccuracy: number;
}

type TabType = 'overview' | 'pipeline' | 'debates' | 'data';

export default function StockDetail() {
  const { symbol } = useParams<{ symbol: string }>();
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [pipelineData, setPipelineData] = useState<FullPipelineData | null>(null);
  const [isLoadingPipeline, setIsLoadingPipeline] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);
  const { settings } = useSettings();

  // Analysis state
  const [isAnalysisRunning, setIsAnalysisRunning] = useState(false);
  const [analysisStatus, setAnalysisStatus] = useState<string | null>(null);
  const [analysisProgress, setAnalysisProgress] = useState<string | null>(null);
  const [analysisSteps, setAnalysisSteps] = useState<{ completed: number; total: number } | null>(null);

  const stock = NIFTY_50_STOCKS.find(s => s.symbol === symbol);

  // API-first loading for recommendation data
  const [latestRecommendation, setLatestRecommendation] = useState<DailyRecommendation | null>(null);
  const [analysis, setAnalysis] = useState<StockAnalysis | undefined>(undefined);
  const [history, setHistory] = useState<Array<{ date: string; decision: string; confidence?: string; risk?: string; hold_days?: number | null; rank?: number | null }>>([]);
  // Fetch recommendation and stock history from API
  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch latest recommendation from API
        const rec = await api.getLatestRecommendation();
        if (rec && rec.analysis && Object.keys(rec.analysis).length > 0) {
          setLatestRecommendation(rec);
          setAnalysis(rec.analysis[symbol || '']);
        }
      } catch (err) {
        console.error('Failed to fetch recommendation:', err);
      }

      try {
        // Fetch stock history from API
        const historyData = await api.getStockHistory(symbol || '');
        if (historyData && historyData.history && historyData.history.length > 0) {
          setHistory(historyData.history);
        }
      } catch (err) {
        console.error('Failed to fetch stock history:', err);
      }

    };

    fetchData();
  }, [symbol]);

  // State for real backtest data from API
  const [backtestResults, setBacktestResults] = useState<BacktestResult[]>([]);
  const [isLoadingBacktest, setIsLoadingBacktest] = useState(false);

  // Fetch real backtest data for all history entries
  const fetchBacktestData = useCallback(async () => {
    if (!symbol || history.length === 0) return;

    setIsLoadingBacktest(true);

    const results: BacktestResult[] = [];

    for (const entry of history) {
      try {
        const backtest = await api.getBacktestResult(entry.date, symbol);

        if (backtest.available) {
          // Use hold-period return when available (BUY/HOLD with hold_days), else 1-day return
          const primaryReturn = backtest.return_at_hold ?? backtest.actual_return_1d ?? null;
          let predictionCorrect: boolean | null = null;
          if (primaryReturn !== undefined && primaryReturn !== null) {
            if (entry.decision === 'BUY' || entry.decision === 'HOLD') {
              predictionCorrect = primaryReturn > 0;
            } else if (entry.decision === 'SELL') {
              predictionCorrect = primaryReturn < 0;
            }
          }

          results.push({
            date: entry.date,
            decision: entry.decision,
            return1d: backtest.actual_return_1d ?? null,
            return1w: backtest.actual_return_1w ?? null,
            returnAtHold: backtest.return_at_hold ?? null,
            holdDays: backtest.hold_days ?? null,
            primaryReturn,
            predictionCorrect,
            rank: entry.rank,
          });
        } else {
          // No backtest data available for this date
          results.push({
            date: entry.date,
            decision: entry.decision,
            return1d: null,
            return1w: null,
            returnAtHold: null,
            holdDays: null,
            primaryReturn: null,
            predictionCorrect: null,
            rank: entry.rank,
          });
        }
      } catch (err) {
        console.error(`Failed to fetch backtest for ${entry.date}:`, err);
        results.push({
          date: entry.date,
          decision: entry.decision,
          return1d: null,
          return1w: null,
          returnAtHold: null,
          holdDays: null,
          primaryReturn: null,
          predictionCorrect: null,
          rank: entry.rank,
        });
      }
    }

    setBacktestResults(results);
    setIsLoadingBacktest(false);
  }, [symbol, history]);

  // Fetch backtest data when symbol changes
  useEffect(() => {
    fetchBacktestData();
  }, [fetchBacktestData]);

  // Calculate prediction stats from real backtest data
  const predictionStats = useMemo((): PredictionStats | null => {
    if (backtestResults.length === 0) return null;

    const resultsWithData = backtestResults.filter(r => r.primaryReturn !== null);
    if (resultsWithData.length === 0) return null;

    let correct = 0;
    let totalReturn = 0;
    let buyTotal = 0, buyCorrect = 0;
    let sellTotal = 0, sellCorrect = 0;
    let holdTotal = 0, holdCorrect = 0;

    for (const result of resultsWithData) {
      if (result.primaryReturn !== null) {
        totalReturn += result.primaryReturn;
      }
      if (result.predictionCorrect !== null) {
        if (result.predictionCorrect) correct++;

        if (result.decision === 'BUY') {
          buyTotal++;
          if (result.predictionCorrect) buyCorrect++;
        } else if (result.decision === 'SELL') {
          sellTotal++;
          if (result.predictionCorrect) sellCorrect++;
        } else {
          holdTotal++;
          if (result.predictionCorrect) holdCorrect++;
        }
      }
    }

    const totalWithResult = resultsWithData.filter(r => r.predictionCorrect !== null).length;

    return {
      totalPredictions: resultsWithData.length,
      correctPredictions: correct,
      accuracy: totalWithResult > 0 ? Math.round((correct / totalWithResult) * 100) : 0,
      avgReturn: resultsWithData.length > 0 ? Math.round((totalReturn / resultsWithData.length) * 10) / 10 : 0,
      buyAccuracy: buyTotal > 0 ? Math.round((buyCorrect / buyTotal) * 100) : 0,
      sellAccuracy: sellTotal > 0 ? Math.round((sellCorrect / sellTotal) * 100) : 0,
      holdAccuracy: holdTotal > 0 ? Math.round((holdCorrect / holdTotal) * 100) : 0,
    };
  }, [backtestResults]);

  // Real price history from API
  const [realPriceHistory, setRealPriceHistory] = useState<Array<{ date: string; price: number }>>([]);
  const [isLoadingPrices, setIsLoadingPrices] = useState(false);

  // Fetch real price history from yfinance via backend
  useEffect(() => {
    if (!symbol) return;

    const fetchPrices = async () => {
      setIsLoadingPrices(true);
      try {
        const data = await api.getStockPriceHistory(symbol, 90);
        if (data.prices && data.prices.length > 0) {
          setRealPriceHistory(data.prices);
        }
      } catch (err) {
        console.error('Failed to fetch price history:', err);
      } finally {
        setIsLoadingPrices(false);
      }
    };

    fetchPrices();
  }, [symbol]);

  // Build prediction points from real history data (API-sourced dates + decisions)
  const predictionPoints = useMemo(() => {
    if (history.length === 0 || realPriceHistory.length === 0) return [];

    const priceDateMap = new Map(realPriceHistory.map(p => [p.date, p.price]));
    const MAX_DATE_TOLERANCE_MS = 4 * 24 * 60 * 60 * 1000; // 4 days max (handles weekends/holidays)

    return history
      .map(entry => {
        // Find exact date match first
        const price = priceDateMap.get(entry.date);
        if (price !== undefined) {
          return { date: entry.date, decision: entry.decision as 'BUY' | 'SELL' | 'HOLD', price };
        }

        // Find closest date within tolerance (skip if prediction date is outside price range)
        const entryTime = new Date(entry.date).getTime();
        let closestPoint: { date: string; price: number } | null = null;
        let closestDiff = Infinity;
        for (const p of realPriceHistory) {
          const diff = Math.abs(new Date(p.date).getTime() - entryTime);
          if (diff < closestDiff) {
            closestDiff = diff;
            closestPoint = p;
          }
        }

        if (closestPoint && closestDiff <= MAX_DATE_TOLERANCE_MS) {
          return { date: closestPoint.date, decision: entry.decision as 'BUY' | 'SELL' | 'HOLD', price: closestPoint.price };
        }

        return null; // Prediction date too far from any price data — skip
      })
      .filter((p): p is NonNullable<typeof p> => p !== null);
  }, [history, realPriceHistory]);

  // Function to fetch pipeline data
  const fetchPipelineData = async (forceRefresh = false) => {
    if (!symbol || !latestRecommendation?.date) return;

    if (forceRefresh) {
      setIsRefreshing(true);
    } else {
      setIsLoadingPipeline(true);
    }

    try {
      const data = await api.getPipelineData(latestRecommendation.date, symbol, forceRefresh);
      setPipelineData(data);
      if (forceRefresh) {
        setLastRefresh(new Date().toLocaleTimeString());
        const hasData = data.pipeline_steps?.length > 0 || Object.keys(data.agent_reports || {}).length > 0;
        setRefreshMessage(hasData ? `✓ Data refreshed for ${symbol}` : `No pipeline data found for ${symbol}`);
        setTimeout(() => setRefreshMessage(null), 3000);
      }
      console.log('Pipeline data fetched:', data);
    } catch (error) {
      console.error('Failed to fetch pipeline data:', error);
      if (forceRefresh) {
        setRefreshMessage(`✗ Failed to refresh: ${error}`);
        setTimeout(() => setRefreshMessage(null), 3000);
      }
      // Set empty pipeline data structure
      setPipelineData({
        date: latestRecommendation.date,
        symbol: symbol,
        agent_reports: {},
        debates: {},
        pipeline_steps: [],
        data_sources: [],
        status: 'no_data'
      });
    } finally {
      setIsLoadingPipeline(false);
      setIsRefreshing(false);
    }
  };

  // Fetch pipeline data when tab changes or symbol changes
  useEffect(() => {
    if (activeTab === 'overview') return; // Don't fetch for overview tab
    fetchPipelineData();
  }, [symbol, latestRecommendation?.date, activeTab]);

  // Refresh handler
  const handleRefresh = async () => {
    console.log('Refresh button clicked - fetching fresh data...');
    await fetchPipelineData(true);
    console.log('Refresh complete - data updated');
  };

  // Run Analysis handler
  const handleRunAnalysis = async () => {
    if (!symbol || !latestRecommendation?.date) return;

    setIsAnalysisRunning(true);
    setAnalysisStatus('starting');
    setAnalysisProgress('Starting analysis...');

    // Auto-switch to pipeline tab so user sees live progress
    setActiveTab('pipeline');

    // Step ordering for pipeline visualization
    const STEP_ORDER = [
      'market_analyst', 'social_media_analyst', 'news_analyst', 'fundamentals_analyst',
      'bull_researcher', 'bear_researcher', 'research_manager', 'trader',
      'aggressive_analyst', 'conservative_analyst', 'neutral_analyst', 'risk_manager',
    ];

    // Initialize pipeline data with all-pending steps
    setPipelineData({
      date: latestRecommendation.date,
      symbol: symbol,
      agent_reports: {},
      debates: {},
      pipeline_steps: STEP_ORDER.map((name, idx) => ({
        step_number: idx + 1,
        step_name: name,
        status: 'pending' as PipelineStepStatus,
      })),
      data_sources: [],
      status: 'in_progress',
    });

    try {
      // Trigger analysis with settings from context
      await api.runAnalysis(symbol, latestRecommendation.date, {
        deep_think_model: settings.deepThinkModel,
        quick_think_model: settings.quickThinkModel,
        provider: settings.provider,
        api_key: settings.provider === 'anthropic_api' ? settings.anthropicApiKey : undefined,
        max_debate_rounds: settings.maxDebateRounds
      });
      setAnalysisStatus('running');

      // Track poll count for periodic full data refresh
      let pollCount = 0;

      // Poll for status
      const pollInterval = setInterval(async () => {
        try {
          const status = await api.getAnalysisStatus(symbol);
          setAnalysisProgress(status.progress || 'Processing...');

          // Update step counts for progress indicator
          if (status.steps_completed !== undefined && status.steps_total !== undefined) {
            setAnalysisSteps({ completed: status.steps_completed, total: status.steps_total });
          }

          // Build live pipeline data from status response
          if (status.pipeline_steps) {
            const livePipelineSteps: PipelineStep[] = STEP_ORDER.map((stepName, idx) => {
              const stepData = status.pipeline_steps?.[stepName];
              return {
                step_number: idx + 1,
                step_name: stepName,
                status: (stepData?.status as PipelineStepStatus) || 'pending',
                duration_ms: stepData?.duration_ms,
              };
            });

            // Update pipeline data with live step statuses
            setPipelineData(prev => ({
              date: latestRecommendation?.date || prev?.date || '',
              symbol: symbol || prev?.symbol || '',
              agent_reports: prev?.agent_reports || {},
              debates: prev?.debates || {},
              pipeline_steps: livePipelineSteps,
              data_sources: prev?.data_sources || [],
              status: 'in_progress',
            }));
          }

          // Every 5th poll (~10s), fetch full pipeline data for agent reports/debates
          pollCount++;
          if (pollCount % 5 === 0) {
            try {
              const fullData = await api.getPipelineData(latestRecommendation.date, symbol, true);
              if (fullData && (fullData.agent_reports || fullData.debates)) {
                setPipelineData(prev => ({
                  ...prev!,
                  agent_reports: fullData.agent_reports || prev?.agent_reports || {},
                  debates: fullData.debates || prev?.debates || {},
                  data_sources: fullData.data_sources || prev?.data_sources || [],
                  // Keep live step statuses if available, otherwise use fetched
                  pipeline_steps: prev?.pipeline_steps?.some(s => s.status === 'running')
                    ? prev!.pipeline_steps
                    : fullData.pipeline_steps || prev?.pipeline_steps || [],
                }));
              }
            } catch { /* ignore full data refresh errors during analysis */ }
          }

          if (status.status === 'completed') {
            clearInterval(pollInterval);
            setIsAnalysisRunning(false);
            setAnalysisStatus('completed');
            setAnalysisProgress(`Analysis complete: ${status.decision || 'Done'}`);
            // Refresh recommendation and pipeline data to show final results
            try {
              const rec = await api.getLatestRecommendation();
              if (rec && rec.analysis && Object.keys(rec.analysis).length > 0) {
                setLatestRecommendation(rec);
                setAnalysis(rec.analysis[symbol || '']);
              }
              const historyData = await api.getStockHistory(symbol || '');
              if (historyData?.history?.length > 0) {
                setHistory(historyData.history);
              }
            } catch { /* ignore refresh errors */ }
            await fetchPipelineData(true);
            fetchBacktestData();
            setTimeout(() => {
              setAnalysisProgress(null);
              setAnalysisStatus(null);
              setAnalysisSteps(null);
            }, 5000);
          } else if (status.status === 'error') {
            clearInterval(pollInterval);
            setIsAnalysisRunning(false);
            setAnalysisStatus('error');
            setAnalysisProgress(`Error: ${status.error}`);
          } else if (status.status === 'cancelled') {
            clearInterval(pollInterval);
            setIsAnalysisRunning(false);
            setAnalysisStatus('cancelled');
            setAnalysisProgress('Analysis cancelled');
            setTimeout(() => {
              setAnalysisProgress(null);
              setAnalysisStatus(null);
              setAnalysisSteps(null);
            }, 3000);
          }
        } catch (err) {
          console.error('Failed to poll analysis status:', err);
        }
      }, 2000); // Poll every 2 seconds

      // Cleanup after 10 minutes max
      setTimeout(() => clearInterval(pollInterval), 600000);

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      console.error('Failed to start analysis:', errorMessage, error);
      setIsAnalysisRunning(false);
      setAnalysisStatus('error');
      // More helpful error message
      if (errorMessage.includes('Failed to fetch') || errorMessage.includes('NetworkError')) {
        setAnalysisProgress(`✗ Network error: Cannot connect to backend at localhost:8000. Please check if the server is running.`);
      } else {
        setAnalysisProgress(`✗ Failed to start analysis: ${errorMessage}`);
      }
    }
  };

  // Cancel Analysis handler
  const handleCancelAnalysis = async () => {
    if (!symbol) return;

    try {
      await api.cancelAnalysis(symbol);
      setIsAnalysisRunning(false);
      setAnalysisStatus('cancelled');
      setAnalysisProgress('Analysis cancelled');
      setTimeout(() => {
        setAnalysisProgress(null);
        setAnalysisStatus(null);
        setAnalysisSteps(null);
      }, 3000);
    } catch (error) {
      console.error('Failed to cancel analysis:', error);
    }
  };

  if (!stock) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="w-12 h-12 text-amber-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-200 mb-2">Stock Not Found</h2>
          <p className="text-gray-500 dark:text-gray-400 mb-4">The stock "{symbol}" was not found in Nifty 50.</p>
          <Link to="/" className="btn-primary">
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  const decisionIcon = {
    BUY: TrendingUp,
    SELL: TrendingDown,
    HOLD: Minus,
  };

  const decisionColor = {
    BUY: 'from-green-500 to-green-600',
    SELL: 'from-red-500 to-red-600',
    HOLD: 'from-amber-500 to-amber-600',
  };

  const DecisionIcon = analysis?.decision ? decisionIcon[analysis.decision] : Activity;
  const bgGradient = analysis?.decision ? decisionColor[analysis.decision] : 'from-gray-500 to-gray-600';

  const TABS = [
    { id: 'overview' as const, label: 'Overview', icon: LineChart },
    { id: 'pipeline' as const, label: 'Analysis Pipeline', icon: Layers },
    { id: 'debates' as const, label: 'Debates', icon: MessageSquare },
    { id: 'data' as const, label: 'Data Sources', icon: Database },
  ];

  return (
    <div className="space-y-4">
      {/* Back Button */}
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-nifty-600 dark:hover:text-nifty-400 transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        Back to Dashboard
      </Link>

      {/* Compact Stock Header */}
      <section className="card overflow-hidden">
        <div className={`bg-gradient-to-r ${bgGradient} p-4 text-white`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div>
                <div className="flex items-center gap-2">
                  {analysis?.rank && (
                    <span className="inline-flex items-center justify-center w-7 h-7 rounded-full text-sm font-bold bg-white/20 text-white" title={`Rank #${analysis.rank}`}>
                      #{analysis.rank}
                    </span>
                  )}
                  <h1 className="text-2xl font-display font-bold">{stock.symbol}</h1>
                  {analysis?.decision && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-white/20">
                      <DecisionIcon className="w-3 h-3" />
                      {analysis.decision}
                    </span>
                  )}
                </div>
                <p className="text-white/90 text-sm">{stock.company_name}</p>
              </div>
            </div>
            <div className="text-right text-xs">
              <div className="flex items-center gap-1.5 text-white/80">
                <Building2 className="w-3 h-3" />
                <span>{stock.sector || 'N/A'}</span>
              </div>
              <div className="flex items-center gap-1.5 text-white/70 mt-1">
                <Calendar className="w-3 h-3" />
                {latestRecommendation?.date ? new Date(latestRecommendation.date).toLocaleDateString('en-IN', {
                  month: 'short',
                  day: 'numeric',
                }) : 'N/A'}
              </div>
            </div>
          </div>
        </div>

        {/* Analysis Details - Inline */}
        {analysis && (
          <div className="p-2 sm:p-3 flex flex-wrap items-center gap-2 sm:gap-4 bg-gray-50/50 dark:bg-slate-700/50">
            <div className="flex items-center gap-1.5 sm:gap-2">
              <span className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400">Decision:</span>
              <DecisionBadge decision={analysis.decision} size="small" />
            </div>
            <div className="flex items-center gap-1.5 sm:gap-2">
              <span className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400">Confidence:</span>
              <ConfidenceBadge confidence={analysis.confidence} />
            </div>
            <div className="flex items-center gap-1.5 sm:gap-2">
              <span className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400">Risk:</span>
              <RiskBadge risk={analysis.risk} />
            </div>
            {analysis.hold_days && analysis.decision !== 'SELL' && (
              <div className="flex items-center gap-1.5 sm:gap-2">
                <span className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400">Hold:</span>
                <HoldDaysBadge holdDays={analysis.hold_days} decision={analysis.decision} />
              </div>
            )}
            {analysis.rank && (
              <div className="flex items-center gap-1.5 sm:gap-2">
                <span className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400">Rank:</span>
                <RankBadge rank={analysis.rank} />
              </div>
            )}
          </div>
        )}
      </section>

      {/* Action Buttons Row - Always visible */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Run Analysis Button */}
        <button
          onClick={handleRunAnalysis}
          disabled={isAnalysisRunning || isRefreshing || isLoadingPipeline}
          className={`
            flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all
            ${isAnalysisRunning
              ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
              : 'bg-nifty-600 text-white hover:bg-nifty-700 shadow-sm'
            }
            disabled:opacity-50 disabled:cursor-not-allowed
          `}
          title="Run AI analysis for this stock"
        >
          {isAnalysisRunning ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          {isAnalysisRunning ? 'Analyzing...' : 'Run Analysis'}
        </button>

        {/* Cancel Analysis Button - only shown when analysis is running */}
        {isAnalysisRunning && (
          <button
            onClick={handleCancelAnalysis}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/50"
            title="Cancel running analysis"
          >
            <Square className="w-3.5 h-3.5 fill-current" />
            Cancel
          </button>
        )}

        {/* Refresh Button */}
        <button
          onClick={handleRefresh}
          disabled={isRefreshing || isLoadingPipeline || isAnalysisRunning}
          className={`
            flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all
            bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-slate-600
            disabled:opacity-50 disabled:cursor-not-allowed
          `}
          title="Refresh pipeline data"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          {isRefreshing ? 'Refreshing...' : 'Refresh'}
        </button>

        {lastRefresh && (
          <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">
            Updated: {lastRefresh}
          </span>
        )}
      </div>

      {/* Tab Navigation */}
      <div className="card p-1 flex gap-1 overflow-x-auto">
        {TABS.map(tab => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                flex items-center gap-2 px-3 sm:px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap
                ${isActive
                  ? 'bg-nifty-600 text-white shadow-md'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-slate-700'
                }
              `}
            >
              <Icon className="w-4 h-4" />
              <span className="hidden sm:inline">{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Analysis Progress Banner */}
      {analysisProgress && (
        <div className={`rounded-lg overflow-hidden ${
          analysisStatus === 'completed'
            ? 'bg-green-100 dark:bg-green-900/30'
            : analysisStatus === 'error'
            ? 'bg-red-100 dark:bg-red-900/30'
            : analysisStatus === 'cancelled'
            ? 'bg-amber-100 dark:bg-amber-900/30'
            : 'bg-blue-100 dark:bg-blue-900/30'
        }`}>
          <div className={`p-3 text-sm font-medium flex items-center gap-2 ${
            analysisStatus === 'completed'
              ? 'text-green-800 dark:text-green-300'
              : analysisStatus === 'error'
              ? 'text-red-800 dark:text-red-300'
              : analysisStatus === 'cancelled'
              ? 'text-amber-800 dark:text-amber-300'
              : 'text-blue-800 dark:text-blue-300'
          }`}>
            {isAnalysisRunning && <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" />}
            <span className="flex-1">{analysisProgress}</span>
            {analysisSteps && (
              <span className="text-xs opacity-75 flex-shrink-0">
                {analysisSteps.completed}/{analysisSteps.total}
              </span>
            )}
          </div>
          {/* Step progress bar */}
          {analysisSteps && isAnalysisRunning && (
            <div className="px-3 pb-2">
              <div className="h-1.5 bg-blue-200/50 dark:bg-blue-800/30 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 dark:bg-blue-400 rounded-full transition-all duration-700 ease-out"
                  style={{ width: `${Math.round((analysisSteps.completed / analysisSteps.total) * 100)}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Refresh Notification */}
      {refreshMessage && !analysisProgress && (
        <div className={`p-3 rounded-lg text-sm font-medium ${
          refreshMessage.startsWith('✓')
            ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
            : refreshMessage.startsWith('✗')
            ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
            : 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300'
        }`}>
          {refreshMessage}
        </div>
      )}

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <>
          {/* Price Chart with Predictions */}
          <section className="card overflow-hidden">
            <div className="p-3 border-b border-gray-100 dark:border-slate-700 bg-gray-50/50 dark:bg-slate-800/50">
              <div className="flex items-center gap-2">
                <LineChart className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />
                <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">Price History & AI Predictions</h2>
                <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">
                  {realPriceHistory.length > 0 ? `${realPriceHistory.length} trading days` : ''}
                </span>
              </div>
            </div>
            <div className="p-4 bg-white dark:bg-slate-800">
              {isLoadingPrices ? (
                <div className="h-64 flex items-center justify-center text-gray-400 dark:text-gray-500">
                  <Loader2 className="w-5 h-5 animate-spin mr-2" />
                  Loading price data...
                </div>
              ) : realPriceHistory.length > 0 ? (
                <StockPriceChart
                  priceHistory={realPriceHistory}
                  predictions={predictionPoints}
                  symbol={symbol || ''}
                />
              ) : (
                <div className="h-64 flex items-center justify-center text-gray-400 dark:text-gray-500">
                  No price data available
                </div>
              )}
            </div>
          </section>

          {/* AI Analysis Panel */}
          {analysis?.raw_analysis && (
            <AIAnalysisPanel
              analysis={analysis.raw_analysis}
              decision={analysis.decision}
            />
          )}

          {/* Prediction Accuracy Stats */}
          {predictionStats && (
            <section className="card overflow-hidden">
              <div className="p-3 border-b border-gray-100 dark:border-slate-700 bg-gradient-to-r from-nifty-50 to-blue-50 dark:from-slate-800 dark:to-slate-700">
                <div className="flex items-center gap-2">
                  <Target className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />
                  <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">Prediction Accuracy</h2>
                </div>
              </div>
              <div className="p-4">
                {/* Main accuracy meter */}
                <div className="flex items-center gap-4 mb-4">
                  <div className="relative w-20 h-20 flex-shrink-0">
                    <svg className="w-20 h-20 transform -rotate-90">
                      <circle
                        cx="40"
                        cy="40"
                        r="36"
                        stroke="currentColor"
                        strokeWidth="8"
                        fill="transparent"
                        className="text-gray-200 dark:text-slate-700"
                      />
                      <circle
                        cx="40"
                        cy="40"
                        r="36"
                        stroke="currentColor"
                        strokeWidth="8"
                        fill="transparent"
                        strokeDasharray={`${(predictionStats.accuracy / 100) * 226} 226`}
                        className={predictionStats.accuracy >= 70 ? 'text-green-500' : predictionStats.accuracy >= 50 ? 'text-amber-500' : 'text-red-500'}
                        strokeLinecap="round"
                      />
                    </svg>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <span className={`text-lg font-bold ${predictionStats.accuracy >= 70 ? 'text-green-600 dark:text-green-400' : predictionStats.accuracy >= 50 ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400'}`}>
                        {predictionStats.accuracy}%
                      </span>
                    </div>
                  </div>
                  <div className="flex-1">
                    <div className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {predictionStats.correctPredictions} of {predictionStats.totalPredictions} predictions correct
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      Avg. 1-day return: <span className={predictionStats.avgReturn >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                        {predictionStats.avgReturn >= 0 ? '+' : ''}{predictionStats.avgReturn}%
                      </span>
                    </div>
                  </div>
                </div>

                {/* Accuracy by decision type */}
                <div className="grid grid-cols-3 gap-2">
                  <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-2 text-center">
                    <div className="text-xs text-green-600 dark:text-green-400 font-medium mb-0.5">BUY</div>
                    <div className="text-sm font-bold text-green-700 dark:text-green-300">{predictionStats.buyAccuracy}%</div>
                  </div>
                  <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-2 text-center">
                    <div className="text-xs text-amber-600 dark:text-amber-400 font-medium mb-0.5">HOLD</div>
                    <div className="text-sm font-bold text-amber-700 dark:text-amber-300">{predictionStats.holdAccuracy}%</div>
                  </div>
                  <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-2 text-center">
                    <div className="text-xs text-red-600 dark:text-red-400 font-medium mb-0.5">SELL</div>
                    <div className="text-sm font-bold text-red-700 dark:text-red-300">{predictionStats.sellAccuracy}%</div>
                  </div>
                </div>
              </div>
            </section>
          )}

          {/* Quick Stats Grid */}
          <div className="grid grid-cols-4 gap-2">
            <div className="card p-2.5 text-center bg-gradient-to-br from-gray-50 to-gray-100 dark:from-slate-800 dark:to-slate-700">
              <div className="text-lg font-bold text-gray-900 dark:text-gray-100">{history.length}</div>
              <div className="text-[10px] text-gray-500 dark:text-gray-400">Total</div>
            </div>
            <div className="card p-2.5 text-center bg-gradient-to-br from-green-50 to-green-100/50 dark:from-green-900/20 dark:to-green-900/10">
              <div className="text-lg font-bold text-green-600 dark:text-green-400">
                {history.filter((h: { decision: string }) => h.decision === 'BUY').length}
              </div>
              <div className="text-[10px] text-green-600 dark:text-green-400">Buy</div>
            </div>
            <div className="card p-2.5 text-center bg-gradient-to-br from-amber-50 to-amber-100/50 dark:from-amber-900/20 dark:to-amber-900/10">
              <div className="text-lg font-bold text-amber-600 dark:text-amber-400">
                {history.filter((h: { decision: string }) => h.decision === 'HOLD').length}
              </div>
              <div className="text-[10px] text-amber-600 dark:text-amber-400">Hold</div>
            </div>
            <div className="card p-2.5 text-center bg-gradient-to-br from-red-50 to-red-100/50 dark:from-red-900/20 dark:to-red-900/10">
              <div className="text-lg font-bold text-red-600 dark:text-red-400">
                {history.filter((h: { decision: string }) => h.decision === 'SELL').length}
              </div>
              <div className="text-[10px] text-red-600 dark:text-red-400">Sell</div>
            </div>
          </div>

          {/* Recommendation History with Real Outcomes */}
          <section className="card overflow-hidden">
            <div className="p-3 border-b border-gray-100 dark:border-slate-700 bg-gradient-to-r from-gray-50 to-slate-50 dark:from-slate-800 dark:to-slate-700">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />
                  <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">Recommendation History</h2>
                  {isLoadingBacktest && (
                    <Loader2 className="w-3 h-3 animate-spin text-nifty-500" />
                  )}
                </div>
                <span className="text-[10px] text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-slate-600 px-2 py-0.5 rounded-full">
                  Actual Returns (Hold Period)
                </span>
              </div>
            </div>

            {isLoadingBacktest ? (
              <div className="p-8 text-center">
                <Loader2 className="w-8 h-8 text-nifty-500 animate-spin mx-auto mb-3" />
                <p className="text-sm text-gray-500 dark:text-gray-400">Fetching real market data...</p>
              </div>
            ) : backtestResults.length > 0 ? (
              <div className="divide-y divide-gray-100 dark:divide-slate-700 max-h-[320px] overflow-y-auto">
                {backtestResults.map((entry, idx) => (
                  <div key={idx} className="px-3 py-2.5 flex items-center gap-3 hover:bg-gray-50 dark:hover:bg-slate-700/50 transition-colors">
                    {/* Date */}
                    <div className="w-16 flex-shrink-0">
                      <div className="text-xs font-medium text-gray-700 dark:text-gray-300">
                        {new Date(entry.date).toLocaleDateString('en-IN', {
                          day: 'numeric',
                          month: 'short',
                        })}
                      </div>
                      <div className="text-[10px] text-gray-400 dark:text-gray-500">
                        {new Date(entry.date).toLocaleDateString('en-IN', { weekday: 'short' })}
                      </div>
                    </div>

                    {/* Rank + Decision Badge + Hold Days */}
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <RankBadge rank={entry.rank} size="small" />
                      <DecisionBadge decision={entry.decision as 'BUY' | 'SELL' | 'HOLD'} size="small" />
                      {entry.holdDays && entry.decision !== 'SELL' && (
                        <span className="text-[10px] text-blue-600 dark:text-blue-400 font-medium">{entry.holdDays}d</span>
                      )}
                    </div>

                    {/* Outcome - Hold Period Return */}
                    {entry.primaryReturn !== null ? (
                      <>
                        <div className="flex-1 flex items-center gap-2">
                          <div className={`text-sm font-semibold ${
                            entry.primaryReturn >= 0
                              ? 'text-green-600 dark:text-green-400'
                              : 'text-red-600 dark:text-red-400'
                          }`}>
                            {entry.primaryReturn >= 0 ? '+' : ''}{entry.primaryReturn.toFixed(1)}%
                          </div>
                          <div className="text-[10px] text-gray-400 dark:text-gray-500">
                            {entry.holdDays && entry.holdDays > 0 ? `${entry.holdDays}d` : '1d'}
                          </div>
                        </div>

                        {/* Prediction Result Icon */}
                        <div className="flex-shrink-0">
                          {entry.predictionCorrect !== null ? (
                            entry.predictionCorrect ? (
                              <div className="flex items-center gap-1 px-2 py-0.5 bg-green-100 dark:bg-green-900/30 rounded-full">
                                <CheckCircle className="w-3 h-3 text-green-600 dark:text-green-400" />
                                <span className="text-[10px] font-medium text-green-700 dark:text-green-400">Correct</span>
                              </div>
                            ) : (
                              <div className="flex items-center gap-1 px-2 py-0.5 bg-red-100 dark:bg-red-900/30 rounded-full">
                                <XCircle className="w-3 h-3 text-red-600 dark:text-red-400" />
                                <span className="text-[10px] font-medium text-red-700 dark:text-red-400">Wrong</span>
                              </div>
                            )
                          ) : (
                            <span className="text-[10px] text-gray-400">N/A</span>
                          )}
                        </div>
                      </>
                    ) : (
                      <div className="flex-1 text-xs text-gray-400 dark:text-gray-500 italic">
                        Awaiting market data...
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : history.length > 0 ? (
              <div className="p-8 text-center">
                <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto mb-3" />
                <p className="text-sm text-gray-500 dark:text-gray-400">Unable to fetch real market data</p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Check if backend service is running</p>
              </div>
            ) : (
              <div className="p-8 text-center">
                <Calendar className="w-10 h-10 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
                <p className="text-sm text-gray-500 dark:text-gray-400">No recommendation history yet</p>
              </div>
            )}
          </section>
        </>
      )}

      {activeTab === 'pipeline' && (
        <PipelineFlowchart
          pipelineData={pipelineData}
          isAnalyzing={isAnalysisRunning}
          isLoading={isLoadingPipeline}
        />
      )}

      {activeTab === 'debates' && (
        <div className="space-y-4">
          {/* Investment Debate */}
          <DebateViewer
            debate={pipelineData?.debates?.investment}
            isLoading={isLoadingPipeline}
          />

          {/* Risk Debate */}
          <RiskDebateViewer
            debate={pipelineData?.debates?.risk}
            isLoading={isLoadingPipeline}
          />
        </div>
      )}

      {activeTab === 'data' && (
        <div className="space-y-4">
          <DataSourcesPanel
            dataSources={pipelineData?.data_sources || []}
            isLoading={isLoadingPipeline}
          />

          {/* No data message */}
          {!isLoadingPipeline && (!pipelineData?.data_sources || pipelineData.data_sources.length === 0) && (
            <div className="card p-8 text-center">
              <Database className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">
                No Data Source Logs Available
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Data source logs will appear here when the analysis pipeline runs.
                This includes information about market data, news, and fundamental data fetched.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Top Pick / Avoid Status - Compact (visible on all tabs) */}
      {latestRecommendation && (
        <>
          {latestRecommendation.top_picks.some(p => p.symbol === symbol) && (
            <section className="card p-3 bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800">
              <div className="flex items-center gap-3">
                <TrendingUp className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0" />
                <div>
                  <span className="font-semibold text-green-800 dark:text-green-300 text-sm">Top Pick: </span>
                  <span className="text-sm text-green-700 dark:text-green-400">
                    {latestRecommendation.top_picks.find(p => p.symbol === symbol)?.reason?.replace(/\*\*/g, '').replace(/\*/g, '')}
                  </span>
                </div>
              </div>
            </section>
          )}

          {latestRecommendation.stocks_to_avoid.some(s => s.symbol === symbol) && (
            <section className="card p-3 bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800">
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0" />
                <div>
                  <span className="font-semibold text-red-800 dark:text-red-300 text-sm">Avoid: </span>
                  <span className="text-sm text-red-700 dark:text-red-400">
                    {latestRecommendation.stocks_to_avoid.find(s => s.symbol === symbol)?.reason?.replace(/\*\*/g, '').replace(/\*/g, '')}
                  </span>
                </div>
              </div>
            </section>
          )}
        </>
      )}

      {/* Compact Disclaimer */}
      <p className="text-[10px] text-gray-400 dark:text-gray-500 text-center">
        AI-generated recommendation for educational purposes only. Not financial advice.
      </p>
    </div>
  );
}
