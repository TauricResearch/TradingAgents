import { useState, useMemo, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Calendar, TrendingUp, TrendingDown, Minus, ChevronRight, BarChart3, Target, HelpCircle, Activity, Calculator, LineChart, PieChart, Shield, Filter, Loader2, AlertCircle } from 'lucide-react';
import { sampleRecommendations, getBacktestResult as getStaticBacktestResult, calculateAccuracyMetrics as calculateStaticAccuracyMetrics, getDateStats as getStaticDateStats, getOverallStats as getStaticOverallStats, getReturnBreakdown as getStaticReturnBreakdown } from '../data/recommendations';
import type { ReturnBreakdown } from '../data/recommendations';
import { DecisionBadge, HoldDaysBadge } from '../components/StockCard';
import Sparkline from '../components/Sparkline';
import AccuracyBadge from '../components/AccuracyBadge';
import AccuracyExplainModal from '../components/AccuracyExplainModal';
import ReturnExplainModal from '../components/ReturnExplainModal';
import OverallReturnModal, { type OverallReturnBreakdown } from '../components/OverallReturnModal';
import AccuracyTrendChart, { type AccuracyTrendPoint } from '../components/AccuracyTrendChart';
import ReturnDistributionChart from '../components/ReturnDistributionChart';
import RiskMetricsCard from '../components/RiskMetricsCard';
import PortfolioSimulator, { type InvestmentMode } from '../components/PortfolioSimulator';
import IndexComparisonChart from '../components/IndexComparisonChart';
import InfoModal from '../components/InfoModal';
import { api } from '../services/api';
import type { StockAnalysis, DailyRecommendation, RiskMetrics, ReturnBucket, CumulativeReturnPoint } from '../types';

// Type for real backtest data
interface RealBacktestData {
  symbol: string;
  decision: string;
  return1d: number | null;
  return1w: number | null;
  returnAtHold: number | null;
  holdDays: number | null;
  primaryReturn: number | null;  // return_at_hold ?? return_1d
  predictionCorrect: boolean | null;
  priceHistory?: Array<{ date: string; price: number }>;
}

// Helper for consistent positive/negative color classes
function getValueColorClass(value: number): string {
  return value >= 0
    ? 'text-green-600 dark:text-green-400'
    : 'text-red-600 dark:text-red-400';
}

// Investment Mode Toggle Component for reuse
function InvestmentModeToggle({
  mode,
  onChange,
  size = 'sm'
}: {
  mode: InvestmentMode;
  onChange: (mode: InvestmentMode) => void;
  size?: 'sm' | 'md';
}) {
  const sizeClasses = size === 'sm'
    ? 'px-2 py-1 text-[10px]'
    : 'px-3 py-1.5 text-xs';

  return (
    <div className="flex items-center gap-1 bg-gray-100 dark:bg-slate-700 rounded-lg p-0.5">
      <button
        onClick={() => onChange('all50')}
        className={`${sizeClasses} font-medium rounded-md transition-all ${
          mode === 'all50'
            ? 'bg-white dark:bg-slate-600 text-nifty-600 dark:text-nifty-400 shadow-sm'
            : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
        }`}
      >
        All 50
      </button>
      <button
        onClick={() => onChange('topPicks')}
        className={`${sizeClasses} font-medium rounded-md transition-all ${
          mode === 'topPicks'
            ? 'bg-white dark:bg-slate-600 text-nifty-600 dark:text-nifty-400 shadow-sm'
            : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
        }`}
      >
        Top Picks
      </button>
    </div>
  );
}

// Pulsing skeleton bar for loading states
function SkeletonBar({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse bg-gray-200 dark:bg-slate-700 rounded ${className}`} />;
}

// Loading overlay for chart sections
function SectionLoader({ message = 'Calculating backtest results...' }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 gap-2">
      <Loader2 className="w-6 h-6 text-nifty-500 animate-spin" />
      <span className="text-xs text-gray-500 dark:text-gray-400">{message}</span>
    </div>
  );
}

export default function History() {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [showAccuracyModal, setShowAccuracyModal] = useState(false);
  const [showReturnModal, setShowReturnModal] = useState(false);
  const [returnModalDate, setReturnModalDate] = useState<string | null>(null);
  const [showOverallModal, setShowOverallModal] = useState(false);

  // Investment mode for Select Date section
  const [dateFilterMode, setDateFilterMode] = useState<InvestmentMode>('all50');
  // Investment mode for Performance Summary
  const [summaryMode, setSummaryMode] = useState<InvestmentMode>('all50');
  // Investment mode for Index Comparison Chart
  const [indexChartMode, setIndexChartMode] = useState<InvestmentMode>('all50');
  // Investment mode for Return Distribution Chart
  const [distributionMode, setDistributionMode] = useState<InvestmentMode>('all50');

  // Performance Summary modal state - single state instead of 4 booleans
  type SummaryModalType = 'daysTracked' | 'avgReturn' | 'buySignals' | 'sellSignals' | null;
  const [activeSummaryModal, setActiveSummaryModal] = useState<SummaryModalType>(null);

  // State for real backtest data
  const [realBacktestData, setRealBacktestData] = useState<Record<string, RealBacktestData>>({});
  const [isLoadingBacktest, setIsLoadingBacktest] = useState(false);

  // State for real recommendations from API
  const [recommendations, setRecommendations] = useState<DailyRecommendation[]>(sampleRecommendations);
  const [isLoadingRecommendations, setIsLoadingRecommendations] = useState(true);
  const [isUsingMockData, setIsUsingMockData] = useState(false);

  // State for accuracy trend data (calculated from real backtest API)
  const [accuracyTrendData, setAccuracyTrendData] = useState<AccuracyTrendPoint[]>([]);
  const [isLoadingAccuracyTrend, setIsLoadingAccuracyTrend] = useState(false);

  // State for risk metrics (calculated from real backtest API)
  const [realRiskMetrics, setRealRiskMetrics] = useState<RiskMetrics | undefined>(undefined);
  const [isLoadingRiskMetrics, setIsLoadingRiskMetrics] = useState(false);

  // State for return distribution (calculated from real backtest API)
  const [realReturnDistribution, setRealReturnDistribution] = useState<ReturnBucket[] | undefined>(undefined);
  const [isLoadingReturnDistribution, setIsLoadingReturnDistribution] = useState(false);

  // State for cumulative returns / index comparison (calculated from real backtest API)
  const [realCumulativeReturns, setRealCumulativeReturns] = useState<CumulativeReturnPoint[] | undefined>(undefined);
  const [isLoadingCumulativeReturns, setIsLoadingCumulativeReturns] = useState(false);

  // State for overall return breakdown (calculated from real backtest API)
  const [realOverallBreakdown, setRealOverallBreakdown] = useState<OverallReturnBreakdown | undefined>(undefined);

  // State for Top Picks mode data
  const [topPicksCumulativeReturns, setTopPicksCumulativeReturns] = useState<CumulativeReturnPoint[] | undefined>(undefined);
  const [topPicksReturnDistribution, setTopPicksReturnDistribution] = useState<ReturnBucket[] | undefined>(undefined);

  // State for real Nifty50 index prices
  const [nifty50Prices, setNifty50Prices] = useState<Record<string, number>>({});

  // State for per-date weighted returns (for dateStatsMap)
  const [realDateReturns, setRealDateReturns] = useState<Record<string, number>>({});

  // State for all backtest data by date and symbol (for PortfolioSimulator)
  const [allBacktestData, setAllBacktestData] = useState<Record<string, Record<string, number>>>({});

  // Fetch real recommendations from API
  useEffect(() => {
    const fetchRecommendations = async () => {
      setIsLoadingRecommendations(true);
      try {
        const data = await api.getAllRecommendations();
        if (data && data.recommendations && data.recommendations.length > 0) {
          setRecommendations(data.recommendations);
          setIsUsingMockData(false);
        } else {
          // API returned empty data, use mock
          setRecommendations(sampleRecommendations);
          setIsUsingMockData(true);
        }
      } catch (error) {
        console.error('Failed to fetch recommendations from API:', error);
        // Fall back to mock data
        setRecommendations(sampleRecommendations);
        setIsUsingMockData(true);
      } finally {
        setIsLoadingRecommendations(false);
      }
    };
    fetchRecommendations();
  }, []);

  // Batch-fetch all backtest results per date (used by both accuracy trend and chart data)
  const [batchBacktestByDate, setBatchBacktestByDate] = useState<
    Record<string, Record<string, { return_1d?: number; return_1w?: number; return_1m?: number; return_at_hold?: number; hold_days?: number; prediction_correct?: boolean; decision: string }>>
  >({});
  const [isBatchLoading, setIsBatchLoading] = useState(false);

  useEffect(() => {
    const fetchBatchBacktest = async () => {
      if (recommendations.length === 0) return;
      setIsBatchLoading(true);

      const sortedDates = [...recommendations]
        .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
        .map(r => r.date);

      const batchData: typeof batchBacktestByDate = {};

      // Trigger batch calculation for all dates in parallel, then fetch results
      await Promise.all(sortedDates.map(async (date) => {
        try {
          // First try to get existing results
          let response = await api.getBacktestResultsForDate(date);

          // If no results, trigger calculation and wait
          if (!response.results || response.results.length === 0) {
            try {
              await api.calculateBacktest(date);
              // Wait a bit for calculation, then re-fetch
              await new Promise(r => setTimeout(r, 5000));
              response = await api.getBacktestResultsForDate(date);
            } catch {
              // Calculation may already be running
            }
          }

          if (response.results && response.results.length > 0) {
            batchData[date] = {};
            for (const r of response.results) {
              batchData[date][r.symbol] = {
                return_1d: r.return_1d,
                return_1w: r.return_1w,
                return_1m: r.return_1m,
                return_at_hold: r.return_at_hold,
                hold_days: r.hold_days,
                prediction_correct: r.prediction_correct,
                decision: r.decision,
              };
            }
          }
        } catch (err) {
          console.warn(`Failed to fetch batch backtest for ${date}:`, err);
        }
      }));

      setBatchBacktestByDate(batchData);
      setIsBatchLoading(false);
    };

    if (!isUsingMockData && !isLoadingRecommendations) {
      fetchBatchBacktest();
    }
  }, [recommendations, isUsingMockData, isLoadingRecommendations]);

  // Compute accuracy trend from batch backtest data
  useEffect(() => {
    if (isBatchLoading || Object.keys(batchBacktestByDate).length === 0) return;

    setIsLoadingAccuracyTrend(true);
    const trendData: AccuracyTrendPoint[] = [];

    const sortedDates = [...recommendations]
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
      .map(r => r.date);

    for (const date of sortedDates) {
      const rec = recommendations.find(r => r.date === date);
      const dateBacktest = batchBacktestByDate[date];
      if (!rec || !dateBacktest) continue;

      let totalBuy = 0, correctBuy = 0;
      let totalSell = 0, correctSell = 0;
      let totalHold = 0, correctHold = 0;

      for (const symbol of Object.keys(rec.analysis)) {
        const stockAnalysis = rec.analysis[symbol];
        const bt = dateBacktest[symbol];
        const primaryRet = bt?.return_at_hold ?? bt?.return_1d;
        if (!stockAnalysis?.decision || primaryRet === undefined || primaryRet === null) continue;

        const predictionCorrect = (stockAnalysis.decision === 'BUY' || stockAnalysis.decision === 'HOLD')
          ? primaryRet > 0
          : primaryRet < 0;

        if (stockAnalysis.decision === 'BUY') { totalBuy++; if (predictionCorrect) correctBuy++; }
        else if (stockAnalysis.decision === 'SELL') { totalSell++; if (predictionCorrect) correctSell++; }
        else { totalHold++; if (predictionCorrect) correctHold++; }
      }

      const totalPredictions = totalBuy + totalSell + totalHold;
      const totalCorrect = correctBuy + correctSell + correctHold;

      trendData.push({
        date,
        overall: totalPredictions > 0 ? Math.round((totalCorrect / totalPredictions) * 100) : 0,
        buy: totalBuy > 0 ? Math.round((correctBuy / totalBuy) * 100) : 0,
        sell: totalSell > 0 ? Math.round((correctSell / totalSell) * 100) : 0,
        hold: totalHold > 0 ? Math.round((correctHold / totalHold) * 100) : 0,
      });
    }

    setAccuracyTrendData(trendData);
    setIsLoadingAccuracyTrend(false);
  }, [batchBacktestByDate, isBatchLoading, recommendations]);

  // Compute all chart data from batch backtest results (no individual API calls)
  useEffect(() => {
    const computeAllChartData = async () => {
      if (recommendations.length === 0 || isBatchLoading || Object.keys(batchBacktestByDate).length === 0) return;

      setIsLoadingRiskMetrics(true);
      setIsLoadingReturnDistribution(true);
      setIsLoadingCumulativeReturns(true);

      // Sort dates chronologically
      const sortedDates = [...recommendations]
        .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
        .map(r => r.date);

      // Data collection for risk metrics calculation
      const dailyReturns: number[] = [];
      let wins = 0;
      let losses = 0;
      let totalWinReturn = 0;
      let totalLossReturn = 0;
      let totalCorrect = 0;
      let totalPredictions = 0;

      // Data for return distribution (latest date only)
      const returnBuckets: ReturnBucket[] = [
        { range: '< -3%', min: -Infinity, max: -3, count: 0, stocks: [] },
        { range: '-3% to -2%', min: -3, max: -2, count: 0, stocks: [] },
        { range: '-2% to -1%', min: -2, max: -1, count: 0, stocks: [] },
        { range: '-1% to 0%', min: -1, max: 0, count: 0, stocks: [] },
        { range: '0% to 1%', min: 0, max: 1, count: 0, stocks: [] },
        { range: '1% to 2%', min: 1, max: 2, count: 0, stocks: [] },
        { range: '2% to 3%', min: 2, max: 3, count: 0, stocks: [] },
        { range: '> 3%', min: 3, max: Infinity, count: 0, stocks: [] },
      ];

      // Data for cumulative returns
      const cumulativeData: CumulativeReturnPoint[] = [];
      let aiMultiplier = 1;
      let indexMultiplier = 1;

      // Fetch real Nifty50 index data
      let niftyPrices: Record<string, number> = {};
      try {
        const niftyData = await api.getNifty50History();
        if (niftyData.prices && Object.keys(niftyData.prices).length > 0) {
          niftyPrices = niftyData.prices;
          setNifty50Prices(niftyPrices);
        }
      } catch (err) {
        console.warn('Failed to fetch Nifty50 index data');
      }

      // Precompute Nifty daily returns from prices
      const sortedNiftyDates = Object.keys(niftyPrices).sort();
      const niftyDailyReturns: Record<string, number> = {};
      for (let i = 1; i < sortedNiftyDates.length; i++) {
        const prevPrice = niftyPrices[sortedNiftyDates[i - 1]];
        const currPrice = niftyPrices[sortedNiftyDates[i]];
        niftyDailyReturns[sortedNiftyDates[i]] = ((currPrice - prevPrice) / prevPrice) * 100;
      }

      // Helper to get Nifty return for a date (exact or closest match)
      const getNiftyReturn = (date: string): number => {
        if (niftyDailyReturns[date] !== undefined) return niftyDailyReturns[date];
        const closestDate = sortedNiftyDates.find(d => d >= date) || sortedNiftyDates[sortedNiftyDates.length - 1];
        return (closestDate && niftyDailyReturns[closestDate] !== undefined) ? niftyDailyReturns[closestDate] : 0;
      };

      // Track per-date returns for dateStatsMap
      const dateReturnsMap: Record<string, number> = {};
      // Track all backtest results for PortfolioSimulator
      const allBacktest: Record<string, Record<string, number>> = {};
      // Track which date last had valid return data (for return distribution)
      let latestDateWithData: string | null = null;

      // Process each date using batch data (no individual API calls)
      for (const date of sortedDates) {
        const rec = recommendations.find(r => r.date === date);
        const dateBacktest = batchBacktestByDate[date];
        if (!rec || !dateBacktest) continue;

        let dateCorrectCount = 0;
        let dateTotalCount = 0;
        let dateCorrectReturn = 0;
        let dateIncorrectReturn = 0;

        for (const symbol of Object.keys(rec.analysis)) {
          const stockAnalysis = rec.analysis[symbol];
          const bt = dateBacktest[symbol];
          const primaryRet = bt?.return_at_hold ?? bt?.return_1d;
          if (!stockAnalysis?.decision || primaryRet === undefined || primaryRet === null) continue;

          // Store for PortfolioSimulator
          if (!allBacktest[date]) allBacktest[date] = {};
          allBacktest[date][symbol] = primaryRet;

          const predictionCorrect = (stockAnalysis.decision === 'BUY' || stockAnalysis.decision === 'HOLD')
            ? primaryRet > 0
            : primaryRet < 0;

          totalPredictions++;
          if (predictionCorrect) {
            totalCorrect++;
            dateCorrectCount++;
            if (stockAnalysis.decision === 'BUY' || stockAnalysis.decision === 'HOLD') {
              dateCorrectReturn += primaryRet;
            } else {
              dateCorrectReturn += Math.abs(primaryRet);
            }
          } else {
            if (stockAnalysis.decision === 'BUY' || stockAnalysis.decision === 'HOLD') {
              dateIncorrectReturn += primaryRet;
            } else {
              dateIncorrectReturn += -Math.abs(primaryRet);
            }
          }
          dateTotalCount++;
        }

        if (dateTotalCount > 0) latestDateWithData = date;

        // Calculate weighted daily return for this date
        if (dateTotalCount > 0) {
          const correctAvg = dateCorrectCount > 0 ? dateCorrectReturn / dateCorrectCount : 0;
          const incorrectAvg = (dateTotalCount - dateCorrectCount) > 0
            ? dateIncorrectReturn / (dateTotalCount - dateCorrectCount) : 0;
          const weightedReturn = (correctAvg * (dateCorrectCount / dateTotalCount))
            + (incorrectAvg * ((dateTotalCount - dateCorrectCount) / dateTotalCount));

          dailyReturns.push(weightedReturn);
          dateReturnsMap[date] = Math.round(weightedReturn * 10) / 10;

          if (weightedReturn > 0) { wins++; totalWinReturn += weightedReturn; }
          else if (weightedReturn < 0) { losses++; totalLossReturn += Math.abs(weightedReturn); }

          aiMultiplier *= (1 + weightedReturn / 100);
          const indexDailyReturn = getNiftyReturn(date);
          indexMultiplier *= (1 + indexDailyReturn / 100);

          cumulativeData.push({
            date,
            value: Math.round(aiMultiplier * 10000) / 100,
            aiReturn: Math.round((aiMultiplier - 1) * 1000) / 10,
            indexReturn: Math.round((indexMultiplier - 1) * 1000) / 10,
          });
        }
      }

      // Populate return distribution using the latest date with actual data
      if (latestDateWithData) {
        const rec = recommendations.find(r => r.date === latestDateWithData);
        const dateBacktest = batchBacktestByDate[latestDateWithData];
        if (rec && dateBacktest) {
          for (const symbol of Object.keys(rec.analysis)) {
            const bt = dateBacktest[symbol];
            const retVal = bt?.return_at_hold ?? bt?.return_1d;
            if (retVal === undefined || retVal === null) continue;
            for (const bucket of returnBuckets) {
              if (retVal >= bucket.min && retVal < bucket.max) {
                bucket.count++;
                bucket.stocks.push(symbol);
                break;
              }
            }
          }
        }
      }

      // Calculate risk metrics
      if (dailyReturns.length > 0) {
        const mean = dailyReturns.reduce((a, b) => a + b, 0) / dailyReturns.length;
        const variance = dailyReturns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / dailyReturns.length;
        const volatility = Math.sqrt(variance);
        const riskFreeRate = 0.02;
        const sharpeRatio = volatility > 0 ? (mean - riskFreeRate) / volatility : 0;

        let peak = 100, maxDrawdown = 0, maxDrawdownTrough = 100, maxDrawdownPeak = 100, currentValue = 100;
        for (const ret of dailyReturns) {
          currentValue = currentValue * (1 + ret / 100);
          if (currentValue > peak) peak = currentValue;
          const drawdown = ((peak - currentValue) / peak) * 100;
          if (drawdown > maxDrawdown) { maxDrawdown = drawdown; maxDrawdownPeak = peak; maxDrawdownTrough = currentValue; }
        }

        const avgWin = wins > 0 ? totalWinReturn / wins : 0;
        const avgLoss = losses > 0 ? totalLossReturn / losses : 1;

        setRealRiskMetrics({
          sharpeRatio: Math.round(sharpeRatio * 100) / 100,
          maxDrawdown: Math.round(maxDrawdown * 10) / 10,
          winLossRatio: Math.round((avgLoss > 0 ? avgWin / avgLoss : avgWin) * 100) / 100,
          winRate: Math.round(totalPredictions > 0 ? (totalCorrect / totalPredictions) * 100 : 0),
          volatility: Math.round(volatility * 100) / 100,
          totalTrades: totalPredictions,
          meanReturn: Math.round(mean * 100) / 100,
          riskFreeRate,
          winningTrades: wins,
          losingTrades: losses,
          avgWinReturn: Math.round(avgWin * 100) / 100,
          avgLossReturn: Math.round(avgLoss * 100) / 100,
          peakValue: Math.round(maxDrawdownPeak * 100) / 100,
          troughValue: Math.round(maxDrawdownTrough * 100) / 100,
        });
      }

      setRealReturnDistribution(returnBuckets);
      setRealCumulativeReturns(cumulativeData);

      // Calculate overall return breakdown
      if (cumulativeData.length > 0) {
        const breakdownDailyReturns: { date: string; return: number; multiplier: number; cumulative: number }[] = [];
        let cumulativeMultiplier = 1;

        for (let i = 0; i < cumulativeData.length; i++) {
          const point = cumulativeData[i];
          const dailyReturn = i === 0
            ? point.aiReturn
            : Math.round((((1 + point.aiReturn / 100) / (1 + cumulativeData[i - 1].aiReturn / 100)) - 1) * 1000) / 10;
          const dailyMultiplier = 1 + dailyReturn / 100;
          cumulativeMultiplier *= dailyMultiplier;
          breakdownDailyReturns.push({
            date: point.date, return: dailyReturn,
            multiplier: Math.round(dailyMultiplier * 10000) / 10000,
            cumulative: Math.round((cumulativeMultiplier - 1) * 1000) / 10,
          });
        }

        const finalMultiplier = 1 + cumulativeData[cumulativeData.length - 1].aiReturn / 100;
        setRealOverallBreakdown({
          dailyReturns: breakdownDailyReturns,
          finalMultiplier: Math.round(finalMultiplier * 10000) / 10000,
          finalReturn: Math.round((finalMultiplier - 1) * 1000) / 10,
          formula: '',
        });
      }

      // Calculate Top Picks data
      const topPicksCumulative: CumulativeReturnPoint[] = [];
      const topPicksDistribution: ReturnBucket[] = [
        { range: '< -3%', min: -Infinity, max: -3, count: 0, stocks: [] },
        { range: '-3% to -2%', min: -3, max: -2, count: 0, stocks: [] },
        { range: '-2% to -1%', min: -2, max: -1, count: 0, stocks: [] },
        { range: '-1% to 0%', min: -1, max: 0, count: 0, stocks: [] },
        { range: '0% to 1%', min: 0, max: 1, count: 0, stocks: [] },
        { range: '1% to 2%', min: 1, max: 2, count: 0, stocks: [] },
        { range: '2% to 3%', min: 2, max: 3, count: 0, stocks: [] },
        { range: '> 3%', min: 3, max: Infinity, count: 0, stocks: [] },
      ];
      let topPicksMultiplier = 1;
      let topPicksIndexMultiplier = 1;

      let latestTopPicksDateWithData: string | null = null;

      for (const date of sortedDates) {
        const rec = recommendations.find(r => r.date === date);
        const dateBacktest = batchBacktestByDate[date];
        if (!rec || !rec.top_picks || !dateBacktest) continue;

        let dateReturn = 0;
        let dateCount = 0;

        for (const pick of rec.top_picks) {
          const bt = dateBacktest[pick.symbol];
          const retVal = bt?.return_at_hold ?? bt?.return_1d;
          if (retVal !== undefined && retVal !== null) {
            dateReturn += retVal;
            dateCount++;
          }
        }

        if (dateCount > 0) latestTopPicksDateWithData = date;

        if (dateCount > 0) {
          const avgReturn = dateReturn / dateCount;
          topPicksMultiplier *= (1 + avgReturn / 100);
          const indexDailyReturn = getNiftyReturn(date);
          topPicksIndexMultiplier *= (1 + indexDailyReturn / 100);
          topPicksCumulative.push({
            date,
            value: Math.round(topPicksMultiplier * 10000) / 100,
            aiReturn: Math.round((topPicksMultiplier - 1) * 1000) / 10,
            indexReturn: Math.round((topPicksIndexMultiplier - 1) * 1000) / 10,
          });
        }
      }

      // Populate top picks distribution from latest date with data
      if (latestTopPicksDateWithData) {
        const rec = recommendations.find(r => r.date === latestTopPicksDateWithData);
        const dateBacktest = batchBacktestByDate[latestTopPicksDateWithData];
        if (rec && dateBacktest) {
          for (const pick of rec.top_picks) {
            const bt = dateBacktest[pick.symbol];
            const retVal = bt?.return_at_hold ?? bt?.return_1d;
            if (retVal !== undefined && retVal !== null) {
              for (const bucket of topPicksDistribution) {
                if (retVal >= bucket.min && retVal < bucket.max) {
                  bucket.count++;
                  bucket.stocks.push(pick.symbol);
                  break;
                }
              }
            }
          }
        }
      }

      setTopPicksCumulativeReturns(topPicksCumulative);
      setTopPicksReturnDistribution(topPicksDistribution);
      setRealDateReturns(dateReturnsMap);
      setAllBacktestData(allBacktest);

      setIsLoadingRiskMetrics(false);
      setIsLoadingReturnDistribution(false);
      setIsLoadingCumulativeReturns(false);
    };

    if (!isUsingMockData && !isLoadingRecommendations) {
      computeAllChartData();
    }
  }, [batchBacktestByDate, isBatchLoading, recommendations, isUsingMockData, isLoadingRecommendations]);

  const dates = recommendations.map(r => r.date);

  // API-first accuracy metrics with mock fallback
  const [apiAccuracyMetrics, setApiAccuracyMetrics] = useState<{
    overall_accuracy: number;
    total_predictions: number;
    correct_predictions: number;
    by_decision: Record<string, { accuracy: number; total: number; correct: number }>;
  } | null>(null);

  useEffect(() => {
    if (isUsingMockData) return;
    const fetchAccuracy = async () => {
      try {
        const metrics = await api.getAccuracyMetrics();
        if (metrics && metrics.total_predictions > 0) {
          setApiAccuracyMetrics(metrics);
        }
      } catch {
        // Will use mock fallback
      }
    };
    fetchAccuracy();
  }, [isUsingMockData]);

  // Convert API or static accuracy to consistent format
  const accuracyMetrics = useMemo(() => {
    if (apiAccuracyMetrics && apiAccuracyMetrics.total_predictions > 0) {
      return {
        total_predictions: apiAccuracyMetrics.total_predictions,
        correct_predictions: apiAccuracyMetrics.correct_predictions,
        success_rate: apiAccuracyMetrics.overall_accuracy / 100,
        buy_accuracy: (apiAccuracyMetrics.by_decision?.BUY?.accuracy || 0) / 100,
        sell_accuracy: (apiAccuracyMetrics.by_decision?.SELL?.accuracy || 0) / 100,
        hold_accuracy: (apiAccuracyMetrics.by_decision?.HOLD?.accuracy || 0) / 100,
      };
    }
    // Only fall back to mock when actually using mock data
    if (isUsingMockData) {
      return calculateStaticAccuracyMetrics();
    }
    // Real data mode but no backtest predictions available yet
    return {
      total_predictions: 0,
      correct_predictions: 0,
      success_rate: 0,
      buy_accuracy: 0,
      sell_accuracy: 0,
      hold_accuracy: 0,
    };
  }, [apiAccuracyMetrics, isUsingMockData]);

  // Compute overall stats from real recommendations data (or fallback to static)
  const overallStats = useMemo(() => {
    if (!isUsingMockData && recommendations.length > 0) {
      // Calculate from real cumulative returns data if available
      if (realCumulativeReturns && realCumulativeReturns.length > 0) {
        const lastPoint = realCumulativeReturns[realCumulativeReturns.length - 1];
        return {
          totalDays: recommendations.length,
          totalPredictions: accuracyMetrics.total_predictions,
          avgDailyReturn: Math.round((lastPoint.aiReturn / realCumulativeReturns.length) * 10) / 10,
          avgMonthlyReturn: 0,
          overallAccuracy: Math.round(accuracyMetrics.success_rate * 100),
          bestDay: null,
          worstDay: null,
        };
      }
      // Real data mode but no backtest data available - show zeros, not mock
      return {
        totalDays: recommendations.length,
        totalPredictions: 0,
        avgDailyReturn: 0,
        avgMonthlyReturn: 0,
        overallAccuracy: 0,
        bestDay: null,
        worstDay: null,
      };
    }
    return getStaticOverallStats();
  }, [isUsingMockData, recommendations, realCumulativeReturns, accuracyMetrics]);

  // Fetch real backtest data for selected date
  const fetchBacktestForDate = useCallback(async (date: string) => {
    const rec = recommendations.find(r => r.date === date);
    if (!rec) return;

    setIsLoadingBacktest(true);
    const newData: Record<string, RealBacktestData> = {};

    const stocks = Object.values(rec.analysis);
    for (const stock of stocks) {
      if (!stock.symbol || !stock.decision) continue;

      try {
        const backtest = await api.getBacktestResult(date, stock.symbol);

        if (backtest.available) {
          // Use hold-period return when available, fall back to 1-day
          const primaryReturn = backtest.return_at_hold ?? backtest.actual_return_1d ?? null;
          let predictionCorrect: boolean | null = null;
          if (primaryReturn !== null) {
            if (stock.decision === 'BUY' || stock.decision === 'HOLD') {
              predictionCorrect = primaryReturn > 0;
            } else if (stock.decision === 'SELL') {
              predictionCorrect = primaryReturn < 0;
            }
          }

          newData[stock.symbol] = {
            symbol: stock.symbol,
            decision: stock.decision,
            return1d: backtest.actual_return_1d ?? null,
            return1w: backtest.actual_return_1w ?? null,
            returnAtHold: backtest.return_at_hold ?? null,
            holdDays: backtest.hold_days ?? null,
            primaryReturn,
            predictionCorrect,
            priceHistory: backtest.price_history,
          };
        }
      } catch (err) {
        console.error(`Failed to fetch backtest for ${stock.symbol}:`, err);
      }
    }

    setRealBacktestData(prev => ({ ...prev, ...newData }));
    setIsLoadingBacktest(false);
  }, [recommendations]);

  // Fetch backtest data when date is selected
  useEffect(() => {
    if (selectedDate) {
      fetchBacktestForDate(selectedDate);
    }
  }, [selectedDate, fetchBacktestForDate]);

  // Calculate stats based on mode
  const filteredStats = useMemo(() => {
    if (summaryMode === 'all50') {
      // Consolidate three reduce calls into one
      const signalTotals = recommendations.reduce(
        (acc, r) => ({
          buy: acc.buy + r.summary.buy,
          sell: acc.sell + r.summary.sell,
          hold: acc.hold + r.summary.hold,
        }),
        { buy: 0, sell: 0, hold: 0 }
      );
      return {
        totalDays: dates.length,
        avgDailyReturn: overallStats.avgDailyReturn,
        buySignals: signalTotals.buy,
        sellSignals: signalTotals.sell,
        holdSignals: signalTotals.hold,
      };
    }

    // Top Picks mode - calculate stats from real data or static fallback
    const topPicksData = recommendations.flatMap(rec =>
      rec.top_picks.map(pick => {
        // Try real backtest data first
        const realData = realBacktestData[pick.symbol];
        const primaryRet = realData?.primaryReturn ?? realData?.return1d;
        if (primaryRet !== null && primaryRet !== undefined) {
          return primaryRet;
        }
        // Only fall back to mock when actually using mock data
        return isUsingMockData ? getStaticBacktestResult(pick.symbol)?.actual_return_1d : undefined;
      })
    ).filter((r): r is number => r !== undefined);

    return {
      totalDays: dates.length,
      avgDailyReturn: topPicksData.length > 0
        ? topPicksData.reduce((sum, r) => sum + r, 0) / topPicksData.length
        : 0,
      buySignals: recommendations.reduce((acc, r) => acc + r.top_picks.length, 0),
      sellSignals: 0, // Top picks are always BUY recommendations
      holdSignals: 0,
    };
  }, [summaryMode, dates.length, overallStats.avgDailyReturn, recommendations]);

  // Pre-calculate date stats: from real recommendations data (counts) and real backtest returns
  const dateStatsMap = useMemo(() => {
    return Object.fromEntries(dates.map(date => {
      const rec = recommendations.find(r => r.date === date);
      if (rec && !isUsingMockData) {
        // Use real recommendation data for counts and real backtest returns
        const stocks = Object.values(rec.analysis);
        return [date, {
          date,
          avgReturn1d: realDateReturns[date] ?? 0,
          avgReturn1m: 0,
          totalStocks: stocks.length,
          correctPredictions: 0,
          accuracy: 0,
          buyCount: rec.summary.buy,
          sellCount: rec.summary.sell,
          holdCount: rec.summary.hold,
        }];
      }
      return [date, getStaticDateStats(date)];
    }));
  }, [dates, recommendations, isUsingMockData, realDateReturns]);

  const getRecommendation = (date: string) => {
    return recommendations.find(r => r.date === date);
  };

  // Filter stocks based on mode for display
  const getFilteredStocks = (date: string) => {
    const rec = getRecommendation(date);
    if (!rec) return [];

    if (dateFilterMode === 'topPicks') {
      return rec.top_picks.map(pick => rec.analysis[pick.symbol]).filter(Boolean);
    }
    return Object.values(rec.analysis);
  };

  // Build ReturnBreakdown from real batch backtest data for the modal
  const buildReturnBreakdown = useCallback((date: string): ReturnBreakdown | null => {
    const rec = recommendations.find(r => r.date === date);
    const dateBacktest = batchBacktestByDate[date];
    if (!rec || !dateBacktest) return null;

    const correctStocks: { symbol: string; decision: string; return1d: number }[] = [];
    const incorrectStocks: { symbol: string; decision: string; return1d: number }[] = [];
    let correctTotal = 0;
    let incorrectTotal = 0;

    for (const symbol of Object.keys(rec.analysis)) {
      const stockAnalysis = rec.analysis[symbol];
      const bt = dateBacktest[symbol];
      const retVal = bt?.return_at_hold ?? bt?.return_1d;
      if (!stockAnalysis?.decision || retVal === undefined || retVal === null) continue;

      const isCorrect = (stockAnalysis.decision === 'BUY' || stockAnalysis.decision === 'HOLD')
        ? retVal > 0
        : retVal < 0;

      const entry = { symbol, decision: stockAnalysis.decision, return1d: retVal };
      if (isCorrect) {
        correctStocks.push(entry);
        correctTotal += (stockAnalysis.decision === 'BUY' || stockAnalysis.decision === 'HOLD') ? retVal : Math.abs(retVal);
      } else {
        incorrectStocks.push(entry);
        incorrectTotal += (stockAnalysis.decision === 'BUY' || stockAnalysis.decision === 'HOLD') ? retVal : -Math.abs(retVal);
      }
    }

    const totalCount = correctStocks.length + incorrectStocks.length;
    if (totalCount === 0) return null;

    const correctAvg = correctStocks.length > 0 ? correctTotal / correctStocks.length : 0;
    const incorrectAvg = incorrectStocks.length > 0 ? incorrectTotal / incorrectStocks.length : 0;
    const correctWeight = correctStocks.length / totalCount;
    const incorrectWeight = incorrectStocks.length / totalCount;
    const weightedReturn = (correctAvg * correctWeight) + (incorrectAvg * incorrectWeight);

    // Sort stocks by return magnitude
    correctStocks.sort((a, b) => Math.abs(b.return1d) - Math.abs(a.return1d));
    incorrectStocks.sort((a, b) => Math.abs(b.return1d) - Math.abs(a.return1d));

    return {
      correctPredictions: {
        count: correctStocks.length,
        totalReturn: correctTotal,
        avgReturn: correctAvg,
        stocks: correctStocks.slice(0, 5),
      },
      incorrectPredictions: {
        count: incorrectStocks.length,
        totalReturn: incorrectTotal,
        avgReturn: incorrectAvg,
        stocks: incorrectStocks.slice(0, 5),
      },
      weightedReturn: Math.round(weightedReturn * 10) / 10,
      formula: `(${correctAvg.toFixed(2)}% × ${correctStocks.length}/${totalCount}) + (${incorrectAvg.toFixed(2)}% × ${incorrectStocks.length}/${totalCount}) = ${weightedReturn.toFixed(2)}%`,
    };
  }, [recommendations, batchBacktestByDate]);

  // Whether any backtest data is still loading (for skeleton states)
  const isBacktestDataLoading = isBatchLoading || (!isUsingMockData && !isLoadingRecommendations && Object.keys(batchBacktestByDate).length === 0);

  // Show loading state
  if (isLoadingRecommendations) {
    return (
      <div className="min-h-[40vh] flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-10 h-10 text-nifty-500 mx-auto mb-3 animate-spin" />
          <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300">Loading historical data...</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Fetching recommendations from API...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Mock Data Indicator */}
      {isUsingMockData && (
        <div className="flex items-center gap-2 px-4 py-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
          <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0" />
          <span className="text-sm text-amber-700 dark:text-amber-300">
            Using demo data. Start the backend server and run analysis for real AI recommendations.
          </span>
        </div>
      )}

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
            {isBacktestDataLoading && (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-nifty-500" />
            )}
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
        {isBacktestDataLoading ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {['nifty', 'green', 'red', 'amber'].map(color => (
              <div key={color} className={`p-3 rounded-lg bg-${color === 'nifty' ? 'nifty-50 dark:bg-nifty-900/20' : `${color}-50 dark:bg-${color}-900/20`} text-center`}>
                <SkeletonBar className="h-7 w-16 mx-auto mb-1" />
                <SkeletonBar className="h-3 w-20 mx-auto" />
              </div>
            ))}
          </div>
        ) : (
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
        )}
        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-2 text-center">
          {isBacktestDataLoading
            ? 'Fetching backtest data from market...'
            : `Based on ${accuracyMetrics.total_predictions} predictions tracked over time`
          }
        </p>
      </section>

      {/* Accuracy Trend Chart */}
      <section className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <LineChart className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
            <h2 className="font-semibold text-gray-900 dark:text-gray-100">Accuracy Trend</h2>
          </div>
          {isLoadingAccuracyTrend && (
            <div className="flex items-center gap-1.5 text-xs text-gray-500">
              <Loader2 className="w-3 h-3 animate-spin" />
              <span>Loading real data...</span>
            </div>
          )}
        </div>
        {isBacktestDataLoading && !isUsingMockData ? (
          <SectionLoader message="Computing accuracy trend from backtest data..." />
        ) : (
          <>
            <AccuracyTrendChart
              height={200}
              data={isUsingMockData
                ? (accuracyTrendData.length > 0 ? accuracyTrendData : undefined)
                : accuracyTrendData
              }
            />
            <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-2 text-center">
              {accuracyTrendData.length > 0 ? (
                <>Prediction accuracy from real backtest data over {accuracyTrendData.length} trading days</>
              ) : isUsingMockData ? (
                <>Demo data - Start backend for real accuracy tracking</>
              ) : (
                <>Prediction accuracy over the past {dates.length} trading days</>
              )}
            </p>
          </>
        )}
      </section>

      {/* Risk Metrics */}
      <section className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
            <h2 className="font-semibold text-gray-900 dark:text-gray-100">Risk Metrics</h2>
          </div>
          {isLoadingRiskMetrics && (
            <div className="flex items-center gap-1.5 text-xs text-gray-500">
              <Loader2 className="w-3 h-3 animate-spin" />
              <span>Loading real data...</span>
            </div>
          )}
        </div>
        {isBacktestDataLoading && !isUsingMockData ? (
          <SectionLoader message="Computing risk metrics from backtest data..." />
        ) : (
          <>
            <RiskMetricsCard metrics={!isUsingMockData && !realRiskMetrics ? {
              sharpeRatio: 0, maxDrawdown: 0, winLossRatio: 0, winRate: 0,
              volatility: 0, totalTrades: 0,
            } : realRiskMetrics} />
            <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-2 text-center">
              {realRiskMetrics ? (
                <>Risk-adjusted performance from real backtest data ({realRiskMetrics.totalTrades} trades)</>
              ) : isUsingMockData ? (
                <>Demo data - Start backend for real risk metrics</>
              ) : (
                <>Risk-adjusted performance metrics for the AI trading strategy</>
              )}
            </p>
          </>
        )}
      </section>

      {/* Portfolio Simulator */}
      <PortfolioSimulator
        recommendations={recommendations}
        isUsingMockData={isUsingMockData}
        nifty50Prices={nifty50Prices}
        allBacktestData={allBacktestData}
      />

      {/* Date Selector with Mode Toggle */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />
            <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">Select Date</h2>
          </div>
          <div className="flex items-center gap-2">
            <Filter className="w-3.5 h-3.5 text-gray-400" />
            <InvestmentModeToggle mode={dateFilterMode} onChange={setDateFilterMode} />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {dates.map((date) => {
            const rec = getRecommendation(date);
            const stats = dateStatsMap[date];
            const avgReturn = stats?.avgReturn1d ?? 0;
            const hasBacktestData = !isUsingMockData ? (realDateReturns[date] !== undefined) : true;
            const isPositive = avgReturn >= 0;

            // Calculate filtered summary for this date
            const filteredSummary = dateFilterMode === 'topPicks'
              ? { buy: rec?.top_picks.length || 0, sell: 0, hold: 0 }
              : rec?.summary || { buy: 0, sell: 0, hold: 0 };

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
                  {!hasBacktestData && isBacktestDataLoading ? (
                    <div className={`text-sm font-bold mt-0.5 ${selectedDate === date ? 'text-white/60' : 'text-gray-400 dark:text-gray-500'}`}>
                      <span className="inline-block w-8 h-4 animate-pulse bg-gray-300 dark:bg-slate-600 rounded" />
                    </div>
                  ) : !hasBacktestData ? (
                    <div className={`text-sm mt-0.5 ${selectedDate === date ? 'text-white/60' : 'text-gray-400 dark:text-gray-500'}`}>
                      Pending
                    </div>
                  ) : (
                    <div className={`text-sm font-bold mt-0.5 ${
                      selectedDate === date ? 'text-white' : getValueColorClass(avgReturn)
                    }`}>
                      {isPositive ? '+' : ''}{avgReturn.toFixed(1)}%
                    </div>
                  )}
                  <div className={`text-[10px] mt-0.5 ${selectedDate === date ? 'text-white/80' : 'opacity-60'}`}>
                    {filteredSummary.buy}B/{filteredSummary.sell}S/{filteredSummary.hold}H
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
              <div className="flex items-center gap-3">
                <h2 className="font-semibold text-gray-900 dark:text-gray-100">
                  {new Date(selectedDate).toLocaleDateString('en-IN', {
                    weekday: 'short',
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                  })}
                </h2>
                <InvestmentModeToggle mode={dateFilterMode} onChange={setDateFilterMode} />
              </div>
              <div className="flex items-center gap-3 text-xs">
                {dateFilterMode === 'all50' ? (
                  <>
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
                  </>
                ) : (
                  <span className="flex items-center gap-1 text-green-600 dark:text-green-400">
                    <TrendingUp className="w-3 h-3" />
                    {getRecommendation(selectedDate)?.top_picks.length} Top Picks (BUY)
                  </span>
                )}
              </div>
            </div>
          </div>

          {isLoadingBacktest ? (
            <div className="p-6 text-center">
              <Loader2 className="w-6 h-6 text-nifty-500 animate-spin mx-auto mb-2" />
              <p className="text-sm text-gray-500 dark:text-gray-400">Fetching real market data...</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-50 dark:divide-slate-700 max-h-[60vh] sm:max-h-[400px] overflow-y-auto">
              {getFilteredStocks(selectedDate).map((stock: StockAnalysis) => {
                const realData = realBacktestData[stock.symbol];

                let nextDayReturn: number | null;
                let priceHistory: Array<{ date: string; price: number }> | undefined;
                let predictionCorrect: boolean | null = null;

                if (!isUsingMockData) {
                  // Real data mode: use hold-period return when available
                  nextDayReturn = realData?.primaryReturn ?? realData?.return1d ?? null;
                  priceHistory = realData?.priceHistory;
                  if (realData?.predictionCorrect !== undefined) {
                    predictionCorrect = realData.predictionCorrect;
                  }
                } else {
                  // Mock data mode: use real if available, fall back to mock
                  const mockBacktest = getStaticBacktestResult(stock.symbol);
                  nextDayReturn = realData?.primaryReturn ?? realData?.return1d ?? mockBacktest?.actual_return_1d ?? 0;
                  priceHistory = realData?.priceHistory ?? mockBacktest?.price_history;
                  if (realData?.predictionCorrect !== undefined) {
                    predictionCorrect = realData.predictionCorrect;
                  } else if (mockBacktest && stock.decision) {
                    if (stock.decision === 'BUY' || stock.decision === 'HOLD') {
                      predictionCorrect = nextDayReturn > 0;
                    } else if (stock.decision === 'SELL') {
                      predictionCorrect = nextDayReturn < 0;
                    }
                  }
                }
                const isPositive = (nextDayReturn ?? 0) >= 0;

                return (
                  <Link
                    key={stock.symbol}
                    to={`/stock/${stock.symbol}`}
                    className="flex items-center justify-between px-3 py-2 hover:bg-gray-50 dark:hover:bg-slate-700/50 transition-colors group"
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <span className="font-medium text-gray-900 dark:text-gray-100 text-sm">{stock.symbol}</span>
                      <span className="text-xs text-gray-500 dark:text-gray-400 hidden sm:inline truncate">{stock.company_name}</span>
                      {realData && (
                        <span className="text-[9px] px-1 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded">
                          Real
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      <DecisionBadge decision={stock.decision} size="small" />
                      <HoldDaysBadge holdDays={stock.hold_days} decision={stock.decision} />
                      {nextDayReturn !== null && (
                        <span className={`text-xs font-medium tabular-nums ${getValueColorClass(nextDayReturn)}`} title={realData?.holdDays ? `${realData.holdDays}d return` : '1d return'}>
                          {nextDayReturn >= 0 ? '+' : ''}{nextDayReturn.toFixed(1)}%
                          {realData?.holdDays && <span className="text-[9px] opacity-60 ml-0.5">/{realData.holdDays}d</span>}
                        </span>
                      )}
                      {predictionCorrect !== null && (
                        <AccuracyBadge
                          correct={predictionCorrect}
                          returnPercent={nextDayReturn}
                          size="small"
                        />
                      )}
                      {priceHistory && (
                        <Sparkline
                          data={priceHistory}
                          width={60}
                          height={24}
                          positive={isPositive}
                        />
                      )}
                      <ChevronRight className="w-4 h-4 text-gray-300 dark:text-gray-600 group-hover:text-nifty-600 dark:group-hover:text-nifty-400" />
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Performance Summary Cards with Mode Toggle */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />
            <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">Performance Summary</h2>
          </div>
          <InvestmentModeToggle mode={summaryMode} onChange={setSummaryMode} />
        </div>
        {isBacktestDataLoading && !isUsingMockData ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50 text-center">
                <SkeletonBar className="h-6 w-12 mx-auto mb-1" />
                <SkeletonBar className="h-3 w-20 mx-auto" />
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div
              className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50 text-center cursor-pointer hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors"
              onClick={() => setActiveSummaryModal('daysTracked')}
            >
              <div className="text-xl font-bold text-nifty-600 dark:text-nifty-400">{filteredStats.totalDays}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center justify-center gap-1">
                Days Tracked <HelpCircle className="w-3 h-3" />
              </div>
            </div>
            <div
              className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50 text-center cursor-pointer hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors"
              onClick={() => setActiveSummaryModal('avgReturn')}
            >
              <div className={`text-xl font-bold ${getValueColorClass(filteredStats.avgDailyReturn)}`}>
                {filteredStats.avgDailyReturn >= 0 ? '+' : ''}{filteredStats.avgDailyReturn.toFixed(1)}%
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center justify-center gap-1">
                Avg Return <HelpCircle className="w-3 h-3" />
              </div>
            </div>
            <div
              className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50 text-center cursor-pointer hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors"
              onClick={() => setActiveSummaryModal('buySignals')}
            >
              <div className="text-xl font-bold text-green-600 dark:text-green-400">
                {filteredStats.buySignals}
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center justify-center gap-1">
                {summaryMode === 'topPicks' ? 'Top Pick Signals' : 'Buy Signals'} <HelpCircle className="w-3 h-3" />
              </div>
            </div>
            <div
              className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50 text-center cursor-pointer hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors"
              onClick={() => setActiveSummaryModal('sellSignals')}
            >
              <div className="text-xl font-bold text-red-600 dark:text-red-400">
                {filteredStats.sellSignals}
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center justify-center gap-1">
                Sell Signals <HelpCircle className="w-3 h-3" />
              </div>
            </div>
          </div>
        )}
        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-3 text-center">
          {isBacktestDataLoading && !isUsingMockData
            ? 'Loading performance data from market...'
            : summaryMode === 'topPicks'
              ? 'Performance based on Top Picks recommendations only (3 stocks per day)'
              : 'Returns measured over hold period (or 1-day when no hold period specified)'
          }
        </p>
      </div>

      {/* AI vs Nifty50 Index Comparison */}
      <section className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
            <h2 className="font-semibold text-gray-900 dark:text-gray-100">AI Strategy vs Nifty50 Index</h2>
          </div>
          <div className="flex items-center gap-2">
            {isLoadingCumulativeReturns && (
              <div className="flex items-center gap-1.5 text-xs text-gray-500">
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>Loading...</span>
              </div>
            )}
            <InvestmentModeToggle mode={indexChartMode} onChange={setIndexChartMode} />
          </div>
        </div>
        {isBacktestDataLoading && !isUsingMockData ? (
          <SectionLoader message="Computing cumulative returns vs Nifty50 index..." />
        ) : (
          <>
            <IndexComparisonChart
              height={220}
              data={isUsingMockData
                ? undefined
                : (indexChartMode === 'topPicks' ? topPicksCumulativeReturns : realCumulativeReturns) ?? []
              }
            />
            <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-2 text-center">
              {(indexChartMode === 'topPicks' ? topPicksCumulativeReturns : realCumulativeReturns)?.length ? (
                <>
                  Cumulative returns for {indexChartMode === 'topPicks' ? 'Top Picks' : 'All 50 stocks'} over{' '}
                  {(indexChartMode === 'topPicks' ? topPicksCumulativeReturns : realCumulativeReturns)?.length} trading days
                </>
              ) : isUsingMockData ? (
                <>Demo data - Start backend for real performance comparison</>
              ) : (
                <>Comparison of cumulative returns between AI strategy and Nifty50 index</>
              )}
            </p>
          </>
        )}
      </section>

      {/* Return Distribution */}
      <section className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <PieChart className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
            <h2 className="font-semibold text-gray-900 dark:text-gray-100">Return Distribution</h2>
          </div>
          <div className="flex items-center gap-2">
            {isLoadingReturnDistribution && (
              <div className="flex items-center gap-1.5 text-xs text-gray-500">
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>Loading...</span>
              </div>
            )}
            <InvestmentModeToggle mode={distributionMode} onChange={setDistributionMode} />
          </div>
        </div>
        {isBacktestDataLoading && !isUsingMockData ? (
          <SectionLoader message="Computing return distribution from backtest data..." />
        ) : (
          <>
            <ReturnDistributionChart
              height={200}
              data={isUsingMockData
                ? undefined
                : (distributionMode === 'topPicks' ? topPicksReturnDistribution : realReturnDistribution) ?? []
              }
            />
            <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-2 text-center">
              {(distributionMode === 'topPicks' ? topPicksReturnDistribution : realReturnDistribution) ? (
                <>Distribution of {distributionMode === 'topPicks' ? 'Top Picks' : 'all 50 stocks'} hold-period returns. Click bars to see stocks.</>
              ) : isUsingMockData ? (
                <>Demo data - Start backend for real return distribution</>
              ) : (
                <>Distribution of hold-period returns across all predictions. Click bars to see stocks.</>
              )}
            </p>
          </>
        )}
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
        breakdown={returnModalDate ? (isUsingMockData ? getStaticReturnBreakdown(returnModalDate) : buildReturnBreakdown(returnModalDate)) : null}
        date={returnModalDate || ''}
      />

      {/* Overall Return Modal */}
      <OverallReturnModal
        isOpen={showOverallModal}
        onClose={() => setShowOverallModal(false)}
        breakdown={realOverallBreakdown}
        cumulativeData={realCumulativeReturns}
      />

      {/* Performance Summary Modals */}
      <InfoModal
        isOpen={activeSummaryModal === 'daysTracked'}
        onClose={() => setActiveSummaryModal(null)}
        title="Days Tracked"
        icon={<Calendar className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />}
      >
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
          <p><strong>Days Tracked</strong> shows the total number of trading days where AI recommendations have been recorded and analyzed.</p>
          <div className="p-3 bg-nifty-50 dark:bg-nifty-900/20 rounded-lg">
            <div className="font-semibold text-nifty-800 dark:text-nifty-200 mb-1">Current Count:</div>
            <div className="text-2xl font-bold text-nifty-600 dark:text-nifty-400">{filteredStats.totalDays} days</div>
          </div>
          <p className="text-xs text-gray-500">Each day includes analysis for {summaryMode === 'topPicks' ? '3 top picks' : 'all 50 Nifty stocks'}.</p>
        </div>
      </InfoModal>

      <InfoModal
        isOpen={activeSummaryModal === 'avgReturn'}
        onClose={() => setActiveSummaryModal(null)}
        title="Average Return"
        icon={<TrendingUp className="w-5 h-5 text-green-600 dark:text-green-400" />}
      >
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
          <p><strong>Average Return</strong> measures the mean percentage price change over each stock's recommended hold period.</p>
          <div className="p-3 bg-gray-100 dark:bg-slate-700 rounded-lg">
            <div className="font-semibold mb-1">How it's calculated:</div>
            <ol className="text-xs space-y-1 list-decimal list-inside">
              <li>Record stock price at recommendation time</li>
              <li>Record price after the recommended hold period (e.g. 15 days)</li>
              <li>Calculate: (Exit Price - Entry Price) / Entry Price × 100</li>
              <li>Average all these returns across stocks</li>
            </ol>
            <p className="text-xs text-gray-500 mt-2">If no hold period is specified, falls back to 1-day return.</p>
          </div>
          <div className={`p-3 ${filteredStats.avgDailyReturn >= 0 ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20'} rounded-lg`}>
            <div className="text-xs text-gray-500 mb-1">Current Average:</div>
            <div className={`text-xl font-bold ${filteredStats.avgDailyReturn >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {filteredStats.avgDailyReturn >= 0 ? '+' : ''}{filteredStats.avgDailyReturn.toFixed(2)}%
            </div>
          </div>
        </div>
      </InfoModal>

      <InfoModal
        isOpen={activeSummaryModal === 'buySignals'}
        onClose={() => setActiveSummaryModal(null)}
        title={summaryMode === 'topPicks' ? 'Top Pick Signals' : 'Buy Signals'}
        icon={<TrendingUp className="w-5 h-5 text-green-600 dark:text-green-400" />}
      >
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
          {summaryMode === 'topPicks' ? (
            <>
              <p><strong>Top Pick Signals</strong> counts all stocks that were selected as "Top Picks" across all tracked days.</p>
              <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
                <div className="font-semibold text-green-800 dark:text-green-200 mb-1">What makes a Top Pick?</div>
                <ul className="text-xs space-y-1 list-disc list-inside">
                  <li>Strong bullish momentum indicators</li>
                  <li>Positive technical analysis signals</li>
                  <li>Favorable risk-reward ratio</li>
                  <li>High confidence BUY recommendation</li>
                </ul>
              </div>
            </>
          ) : (
            <>
              <p><strong>Buy Signals</strong> counts every BUY recommendation issued by the AI across all tracked days and all 50 stocks.</p>
              <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
                <div className="font-semibold text-green-800 dark:text-green-200 mb-1">When is BUY recommended?</div>
                <ul className="text-xs space-y-1 list-disc list-inside">
                  <li>Technical indicators show bullish momentum</li>
                  <li>Positive sentiment in news/fundamentals</li>
                  <li>Expected price appreciation in short term</li>
                </ul>
              </div>
            </>
          )}
          <div className="p-2 bg-gray-100 dark:bg-slate-700 rounded-lg flex justify-between items-center">
            <span>Total {summaryMode === 'topPicks' ? 'Top Pick' : 'Buy'} Signals:</span>
            <strong className="text-green-600 text-lg">{filteredStats.buySignals}</strong>
          </div>
        </div>
      </InfoModal>

      <InfoModal
        isOpen={activeSummaryModal === 'sellSignals'}
        onClose={() => setActiveSummaryModal(null)}
        title="Sell Signals"
        icon={<TrendingDown className="w-5 h-5 text-red-600 dark:text-red-400" />}
      >
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
          <p><strong>Sell Signals</strong> counts every SELL recommendation issued by the AI across all tracked days.</p>
          <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
            <div className="font-semibold text-red-800 dark:text-red-200 mb-1">When is SELL recommended?</div>
            <ul className="text-xs space-y-1 list-disc list-inside">
              <li>Technical indicators show bearish momentum</li>
              <li>Negative sentiment in news/fundamentals</li>
              <li>Expected price decline in short term</li>
              <li>Risk level exceeds acceptable threshold</li>
            </ul>
          </div>
          {summaryMode === 'topPicks' ? (
            <div className="p-2 bg-amber-50 dark:bg-amber-900/20 rounded-lg text-xs">
              <strong>Note:</strong> Top Picks mode only shows BUY recommendations, so sell signals are 0.
            </div>
          ) : (
            <div className="p-2 bg-gray-100 dark:bg-slate-700 rounded-lg flex justify-between items-center">
              <span>Total Sell Signals:</span>
              <strong className="text-red-600 text-lg">{filteredStats.sellSignals}</strong>
            </div>
          )}
        </div>
      </InfoModal>
    </div>
  );
}
