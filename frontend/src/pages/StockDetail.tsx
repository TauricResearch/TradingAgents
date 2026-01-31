import { useParams, Link } from 'react-router-dom';
import { useMemo, useState, useEffect } from 'react';
import {
  ArrowLeft, Building2, TrendingUp, TrendingDown, Minus, AlertTriangle,
  Calendar, Activity, LineChart, Database, MessageSquare, FileText, Layers,
  RefreshCw, Play, Loader2
} from 'lucide-react';
import { NIFTY_50_STOCKS } from '../types';
import { sampleRecommendations, getStockHistory, getExtendedPriceHistory, getPredictionPointsWithPrices, getRawAnalysis } from '../data/recommendations';
import { DecisionBadge, ConfidenceBadge, RiskBadge } from '../components/StockCard';
import AIAnalysisPanel from '../components/AIAnalysisPanel';
import StockPriceChart from '../components/StockPriceChart';
import {
  PipelineOverview,
  AgentReportCard,
  DebateViewer,
  RiskDebateViewer,
  DataSourcesPanel
} from '../components/pipeline';
import { api } from '../services/api';
import type { FullPipelineData, AgentType } from '../types/pipeline';

type TabType = 'overview' | 'pipeline' | 'debates' | 'data';

export default function StockDetail() {
  const { symbol } = useParams<{ symbol: string }>();
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [pipelineData, setPipelineData] = useState<FullPipelineData | null>(null);
  const [isLoadingPipeline, setIsLoadingPipeline] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);

  // Analysis state
  const [isAnalysisRunning, setIsAnalysisRunning] = useState(false);
  const [analysisStatus, setAnalysisStatus] = useState<string | null>(null);
  const [analysisProgress, setAnalysisProgress] = useState<string | null>(null);

  const stock = NIFTY_50_STOCKS.find(s => s.symbol === symbol);
  const latestRecommendation = sampleRecommendations[0];
  const analysis = latestRecommendation?.analysis[symbol || ''];
  const history = symbol ? getStockHistory(symbol) : [];

  // Get price history and prediction points for the chart
  const priceHistory = useMemo(() => {
    return symbol ? getExtendedPriceHistory(symbol, 60) : [];
  }, [symbol]);

  const predictionPoints = useMemo(() => {
    return symbol && priceHistory.length > 0
      ? getPredictionPointsWithPrices(symbol, priceHistory)
      : [];
  }, [symbol, priceHistory]);

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

    try {
      // Trigger analysis
      await api.runAnalysis(symbol, latestRecommendation.date);
      setAnalysisStatus('running');

      // Poll for status
      const pollInterval = setInterval(async () => {
        try {
          const status = await api.getAnalysisStatus(symbol);
          setAnalysisProgress(status.progress || 'Processing...');

          if (status.status === 'completed') {
            clearInterval(pollInterval);
            setIsAnalysisRunning(false);
            setAnalysisStatus('completed');
            setAnalysisProgress(`✓ Analysis complete: ${status.decision || 'Done'}`);
            // Refresh data to show results
            await fetchPipelineData(true);
            setTimeout(() => {
              setAnalysisProgress(null);
              setAnalysisStatus(null);
            }, 5000);
          } else if (status.status === 'error') {
            clearInterval(pollInterval);
            setIsAnalysisRunning(false);
            setAnalysisStatus('error');
            setAnalysisProgress(`✗ Error: ${status.error}`);
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
          <div className="p-3 flex items-center gap-4 bg-gray-50/50 dark:bg-slate-700/50">
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500 dark:text-gray-400">Decision:</span>
              <DecisionBadge decision={analysis.decision} size="small" />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500 dark:text-gray-400">Confidence:</span>
              <ConfidenceBadge confidence={analysis.confidence} />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500 dark:text-gray-400">Risk:</span>
              <RiskBadge risk={analysis.risk} />
            </div>
          </div>
        )}
      </section>

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
                flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap
                ${isActive
                  ? 'bg-nifty-600 text-white shadow-md'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-slate-700'
                }
              `}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}

        {/* Action Buttons - Show on non-overview tabs */}
        {activeTab !== 'overview' && (
          <div className="ml-auto flex items-center gap-2">
            {lastRefresh && (
              <span className="text-xs text-gray-400 dark:text-gray-500">
                Updated: {lastRefresh}
              </span>
            )}

            {/* Run Analysis Button */}
            <button
              onClick={handleRunAnalysis}
              disabled={isAnalysisRunning || isRefreshing || isLoadingPipeline}
              className={`
                flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all
                ${isAnalysisRunning
                  ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                  : 'bg-nifty-600 text-white hover:bg-nifty-700'
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

            {/* Refresh Button */}
            <button
              onClick={handleRefresh}
              disabled={isRefreshing || isLoadingPipeline || isAnalysisRunning}
              className={`
                flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all
                text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-slate-700
                disabled:opacity-50 disabled:cursor-not-allowed
              `}
              title="Refresh pipeline data"
            >
              <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
              {isRefreshing ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>
        )}
      </div>

      {/* Analysis Progress Banner */}
      {analysisProgress && (
        <div className={`p-3 rounded-lg text-sm font-medium flex items-center gap-2 ${
          analysisStatus === 'completed'
            ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
            : analysisStatus === 'error'
            ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
            : 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300'
        }`}>
          {isAnalysisRunning && <Loader2 className="w-4 h-4 animate-spin" />}
          {analysisProgress}
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
          {priceHistory.length > 0 && (
            <section className="card overflow-hidden">
              <div className="p-3 border-b border-gray-100 dark:border-slate-700 bg-gray-50/50 dark:bg-slate-800/50">
                <div className="flex items-center gap-2">
                  <LineChart className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />
                  <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">Price History & AI Predictions</h2>
                </div>
              </div>
              <div className="p-4 bg-white dark:bg-slate-800">
                <StockPriceChart
                  priceHistory={priceHistory}
                  predictions={predictionPoints}
                  symbol={symbol || ''}
                />
              </div>
            </section>
          )}

          {/* AI Analysis Panel */}
          {analysis && getRawAnalysis(symbol || '') && (
            <AIAnalysisPanel
              analysis={getRawAnalysis(symbol || '') || ''}
              decision={analysis.decision}
            />
          )}

          {/* Compact Stats Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div className="card p-2.5 text-center">
              <div className="text-lg font-bold text-gray-900 dark:text-gray-100">{history.length}</div>
              <div className="text-[10px] text-gray-500 dark:text-gray-400">Analyses</div>
            </div>
            <div className="card p-2.5 text-center">
              <div className="text-lg font-bold text-green-600 dark:text-green-400">
                {history.filter((h: { decision: string }) => h.decision === 'BUY').length}
              </div>
              <div className="text-[10px] text-gray-500 dark:text-gray-400">Buy</div>
            </div>
            <div className="card p-2.5 text-center">
              <div className="text-lg font-bold text-amber-600 dark:text-amber-400">
                {history.filter((h: { decision: string }) => h.decision === 'HOLD').length}
              </div>
              <div className="text-[10px] text-gray-500 dark:text-gray-400">Hold</div>
            </div>
            <div className="card p-2.5 text-center">
              <div className="text-lg font-bold text-red-600 dark:text-red-400">
                {history.filter((h: { decision: string }) => h.decision === 'SELL').length}
              </div>
              <div className="text-[10px] text-gray-500 dark:text-gray-400">Sell</div>
            </div>
          </div>

          {/* Analysis History */}
          <section className="card">
            <div className="p-3 border-b border-gray-100 dark:border-slate-700 bg-gray-50/50 dark:bg-slate-700/50">
              <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">Recommendation History</h2>
            </div>

            {history.length > 0 ? (
              <div className="divide-y divide-gray-50 dark:divide-slate-700 max-h-[250px] overflow-y-auto">
                {history.map((entry, idx) => (
                  <div key={idx} className="px-3 py-2 flex items-center justify-between">
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {new Date(entry.date).toLocaleDateString('en-IN', {
                        weekday: 'short',
                        month: 'short',
                        day: 'numeric',
                      })}
                    </div>
                    <DecisionBadge decision={entry.decision} size="small" />
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-6 text-center">
                <Calendar className="w-8 h-8 text-gray-300 dark:text-gray-600 mx-auto mb-2" />
                <p className="text-sm text-gray-500 dark:text-gray-400">No history yet</p>
              </div>
            )}
          </section>
        </>
      )}

      {activeTab === 'pipeline' && (
        <div className="space-y-4">
          {/* Pipeline Overview */}
          <section className="card p-4">
            <div className="flex items-center gap-2 mb-4">
              <Layers className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
              <h2 className="font-semibold text-gray-900 dark:text-gray-100">Analysis Pipeline</h2>
            </div>
            <PipelineOverview
              steps={pipelineData?.pipeline_steps || []}
              onStepClick={(step) => console.log('Step clicked:', step)}
            />
          </section>

          {/* Agent Reports Grid */}
          <section className="card p-4">
            <div className="flex items-center gap-2 mb-4">
              <FileText className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
              <h2 className="font-semibold text-gray-900 dark:text-gray-100">Agent Reports</h2>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {(['market', 'news', 'social_media', 'fundamentals'] as AgentType[]).map(agentType => (
                <AgentReportCard
                  key={agentType}
                  agentType={agentType}
                  report={pipelineData?.agent_reports?.[agentType]}
                  isLoading={isLoadingPipeline}
                />
              ))}
            </div>
          </section>
        </div>
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
                    {latestRecommendation.top_picks.find(p => p.symbol === symbol)?.reason}
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
                    {latestRecommendation.stocks_to_avoid.find(s => s.symbol === symbol)?.reason}
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
