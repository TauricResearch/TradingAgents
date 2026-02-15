import { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Calendar, TrendingUp, TrendingDown, Minus, ChevronRight, ChevronDown, BarChart3, Target, HelpCircle, Activity, Calculator, LineChart, PieChart, Shield, Filter, Clock, Zap, Award, ArrowUpRight, ArrowDownRight, Play, Loader2, FileText, MessageSquare, Search, XCircle, AlertTriangle } from 'lucide-react';
import type { ReturnBreakdown } from '../types';
import { DecisionBadge, HoldDaysBadge, RankBadge } from '../components/StockCard';
import Sparkline from '../components/Sparkline';
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
import { useSettings } from '../contexts/SettingsContext';
import type { StockAnalysis, DailyRecommendation, RiskMetrics, ReturnBucket, CumulativeReturnPoint } from '../types';

// Type for batch backtest data (per date, per symbol)
type BacktestByDate = Record<string, Record<string, {
  return_1d?: number;
  return_1w?: number;
  return_1m?: number;
  return_at_hold?: number;
  hold_days?: number;
  prediction_correct?: boolean;
  decision: string;
}>>;

// Helper for consistent positive/negative color classes
function getValueColorClass(value: number): string {
  return value >= 0
    ? 'text-emerald-600 dark:text-emerald-400'
    : 'text-red-500 dark:text-red-400';
}

// Format percentage without negative zero (e.g. "-0.0" becomes "0.0")
function fmtPct(val: number, decimals = 1): string {
  const s = val.toFixed(decimals);
  if (s === '-0.0' || s === '-0.00') return s.replace('-', '');
  return s;
}

// Investment Mode Toggle Component
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
    ? 'px-2.5 py-1 text-[10px]'
    : 'px-3 py-1.5 text-xs';

  return (
    <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-slate-700/80 rounded-lg p-0.5">
      <button
        onClick={() => onChange('all50')}
        className={`${sizeClasses} font-semibold rounded-md transition-all duration-200 ${
          mode === 'all50'
            ? 'bg-white dark:bg-slate-600 text-nifty-600 dark:text-nifty-400 shadow-sm'
            : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
        }`}
      >
        All 50
      </button>
      <button
        onClick={() => onChange('topPicks')}
        className={`${sizeClasses} font-semibold rounded-md transition-all duration-200 ${
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

// Section header with icon and optional right content
function SectionHeader({ icon, title, right, subtitle }: { icon: React.ReactNode; title: string; right?: React.ReactNode; subtitle?: string }) {
  return (
    <div className="flex items-center justify-between mb-4">
      <div className="flex items-center gap-2.5">
        <div className="p-1.5 rounded-lg bg-nifty-50 dark:bg-nifty-900/30">
          {icon}
        </div>
        <div>
          <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">{title}</h2>
          {subtitle && <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {right}
    </div>
  );
}

export default function History() {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [showAccuracyModal, setShowAccuracyModal] = useState(false);
  const [showReturnModal, setShowReturnModal] = useState(false);
  const [returnModalDate, setReturnModalDate] = useState<string | null>(null);
  const [showOverallModal, setShowOverallModal] = useState(false);

  // Investment modes for various sections
  const [dateFilterMode, setDateFilterMode] = useState<InvestmentMode>('all50');
  const [summaryMode, setSummaryMode] = useState<InvestmentMode>('all50');
  const [indexChartMode, setIndexChartMode] = useState<InvestmentMode>('all50');
  const [distributionMode, setDistributionMode] = useState<InvestmentMode>('all50');

  // Performance Summary modal state
  type SummaryModalType = 'daysTracked' | 'avgReturn' | 'buySignals' | 'sellSignals' | null;
  const [activeSummaryModal, setActiveSummaryModal] = useState<SummaryModalType>(null);

  // Backtest feature state
  const [backtestDateInput, setBacktestDateInput] = useState('');
  const [isRunningBacktest, setIsRunningBacktest] = useState(false);
  const [detailedBacktest, setDetailedBacktest] = useState<{
    date: string;
    total_stocks: number;
    stocks: Array<{
      symbol: string; company_name: string; rank?: number;
      decision: string; confidence: string; risk: string;
      hold_days: number; hold_days_elapsed: number; hold_period_active: boolean;
      price_at_prediction: number | null; price_current: number | null; price_at_hold_end: number | null;
      return_current: number | null; return_at_hold: number | null;
      prediction_correct: boolean | null; formula: string; raw_analysis: string;
      agent_summary: Record<string, string>; debate_summary: Record<string, string>;
    }>;
  } | null>(null);
  const [expandedStock, setExpandedStock] = useState<string | null>(null);
  const [activeAgentTab, setActiveAgentTab] = useState<string>('market');
  const [isLoadingDetailed, setIsLoadingDetailed] = useState(false);
  const [backtestMessage, setBacktestMessage] = useState<{ type: 'error' | 'info' | 'progress'; text: string } | null>(null);
  const backtestPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { settings } = useSettings();

  // ==========================================================
  // SINGLE-FETCH: All data loaded in one API call
  // ==========================================================
  const [recommendations, setRecommendations] = useState<DailyRecommendation[]>([]);
  const [batchBacktestByDate, setBatchBacktestByDate] = useState<BacktestByDate>({});
  const [isLoading, setIsLoading] = useState(true);
  const [nifty50Prices, setNifty50Prices] = useState<Record<string, number>>({});
  const [apiAccuracyMetrics, setApiAccuracyMetrics] = useState<{
    overall_accuracy: number;
    total_predictions: number;
    correct_predictions: number;
    by_decision: Record<string, { accuracy: number; total: number; correct: number }>;
  } | null>(null);
  const [loadTimeMs, setLoadTimeMs] = useState<number | null>(null);

  // Single useEffect: fetch the bundle
  useEffect(() => {
    const fetchBundle = async () => {
      setIsLoading(true);
      const t0 = performance.now();
      try {
        const bundle = await api.getHistoryBundle();

        if (bundle.recommendations && bundle.recommendations.length > 0) {
          setRecommendations(bundle.recommendations);
        }

        if (bundle.backtest_by_date) {
          setBatchBacktestByDate(bundle.backtest_by_date);
        }

        if (bundle.accuracy && bundle.accuracy.total_predictions > 0) {
          setApiAccuracyMetrics(bundle.accuracy);
        }

        if (bundle.nifty50_prices && Object.keys(bundle.nifty50_prices).length > 0) {
          setNifty50Prices(bundle.nifty50_prices);
        }

        setLoadTimeMs(Math.round(performance.now() - t0));
      } catch (error) {
        console.error('Failed to fetch history bundle:', error);
        setLoadTimeMs(Math.round(performance.now() - t0));
      } finally {
        setIsLoading(false);
      }
    };
    fetchBundle();
  }, []);

  // If Nifty50 wasn't in the bundle (cache cold), retry once after 3s
  const niftyRetried = useRef(false);
  useEffect(() => {
    if (!isLoading && Object.keys(nifty50Prices).length === 0 && !niftyRetried.current) {
      niftyRetried.current = true;
      const timer = setTimeout(async () => {
        try {
          const data = await api.getNifty50History();
          if (data.prices && Object.keys(data.prices).length > 0) {
            setNifty50Prices(data.prices);
          }
        } catch { /* ignore */ }
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [isLoading, nifty50Prices]);

  const dates = recommendations.map(r => r.date);
  const hasBacktestData = Object.keys(batchBacktestByDate).length > 0;

  // ==========================================================
  // COMPUTED: All chart data derived synchronously from bundle
  // ==========================================================

  // Accuracy metrics
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
    return { total_predictions: 0, correct_predictions: 0, success_rate: 0, buy_accuracy: 0, sell_accuracy: 0, hold_accuracy: 0 };
  }, [apiAccuracyMetrics]);

  // Accuracy trend data
  const accuracyTrendData = useMemo<AccuracyTrendPoint[]>(() => {
    if (!hasBacktestData) return [];

    const sortedDates = [...recommendations]
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
      .map(r => r.date);

    const trendData: AccuracyTrendPoint[] = [];

    for (const date of sortedDates) {
      const rec = recommendations.find(r => r.date === date);
      const dateBacktest = batchBacktestByDate[date];
      if (!rec || !dateBacktest) continue;

      let totalBuy = 0, correctBuy = 0, totalSell = 0, correctSell = 0, totalHold = 0, correctHold = 0;

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
      if (totalPredictions < 3) continue;

      trendData.push({
        date,
        overall: totalPredictions > 0 ? Math.round((totalCorrect / totalPredictions) * 100) : 0,
        buy: totalBuy > 0 ? Math.round((correctBuy / totalBuy) * 100) : 0,
        sell: totalSell > 0 ? Math.round((correctSell / totalSell) * 100) : 0,
        hold: totalHold > 0 ? Math.round((correctHold / totalHold) * 100) : 0,
      });
    }

    return trendData;
  }, [batchBacktestByDate, hasBacktestData, recommendations]);

  // All chart data computed from batch backtest
  const chartData = useMemo(() => {
    if (recommendations.length === 0 || !hasBacktestData) {
      return {
        riskMetrics: undefined as RiskMetrics | undefined,
        returnDistribution: undefined as ReturnBucket[] | undefined,
        cumulativeReturns: undefined as CumulativeReturnPoint[] | undefined,
        overallBreakdown: undefined as OverallReturnBreakdown | undefined,
        topPicksCumulativeReturns: undefined as CumulativeReturnPoint[] | undefined,
        topPicksReturnDistribution: undefined as ReturnBucket[] | undefined,
        dateReturns: {} as Record<string, number>,
        allBacktestData: {} as Record<string, Record<string, number>>,
        dailyReturnsArray: [] as number[],
        topPicksDailyReturns: [] as number[],
      };
    }

    const sortedDates = [...recommendations]
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
      .map(r => r.date);

    // Risk metrics accumulators
    const dailyReturns: number[] = [];
    let wins = 0, losses = 0, totalWinReturn = 0, totalLossReturn = 0;
    let totalCorrect = 0, totalPredictions = 0;

    // Return distribution buckets
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

    // Cumulative returns
    const cumulativeData: CumulativeReturnPoint[] = [];
    let aiMultiplier = 1;

    // Nifty50 price ratio approach: direct comparison to start price
    // This avoids losing Nifty returns on days without backtest data
    const sortedNiftyDates = Object.keys(nifty50Prices).sort();
    const hasNiftyData = sortedNiftyDates.length > 0;
    const niftyStartPrice = hasNiftyData ? nifty50Prices[sortedNiftyDates[0]] : null;

    const getNiftyReturnForDate = (date: string): number => {
      if (!hasNiftyData || !niftyStartPrice) return 0;
      const closestDate = sortedNiftyDates.find(d => d >= date) || sortedNiftyDates[sortedNiftyDates.length - 1];
      if (!closestDate || !nifty50Prices[closestDate]) return 0;
      return ((nifty50Prices[closestDate] / niftyStartPrice) - 1) * 100;
    };

    const dateReturnsMap: Record<string, number> = {};
    const allBacktest: Record<string, Record<string, number>> = {};
    let latestDateWithData: string | null = null;

    for (const date of sortedDates) {
      const rec = recommendations.find(r => r.date === date);
      const dateBacktest = batchBacktestByDate[date];
      if (!rec || !dateBacktest) continue;

      let dateCorrectCount = 0, dateTotalCount = 0, dateCorrectReturn = 0, dateIncorrectReturn = 0;

      for (const symbol of Object.keys(rec.analysis)) {
        const stockAnalysis = rec.analysis[symbol];
        const bt = dateBacktest[symbol];
        const primaryRet = bt?.return_at_hold ?? bt?.return_1d;
        if (!stockAnalysis?.decision || primaryRet === undefined || primaryRet === null) continue;

        if (!allBacktest[date]) allBacktest[date] = {};
        allBacktest[date][symbol] = primaryRet;

        const predictionCorrect = (stockAnalysis.decision === 'BUY' || stockAnalysis.decision === 'HOLD')
          ? primaryRet > 0
          : primaryRet < 0;

        totalPredictions++;
        if (predictionCorrect) {
          totalCorrect++;
          dateCorrectCount++;
          dateCorrectReturn += (stockAnalysis.decision === 'BUY' || stockAnalysis.decision === 'HOLD') ? primaryRet : Math.abs(primaryRet);
        } else {
          dateIncorrectReturn += (stockAnalysis.decision === 'BUY' || stockAnalysis.decision === 'HOLD') ? primaryRet : -Math.abs(primaryRet);
        }
        dateTotalCount++;
      }

      if (dateTotalCount > 0) latestDateWithData = date;

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
        const niftyCumulativeReturn = getNiftyReturnForDate(date);

        cumulativeData.push({
          date,
          value: Math.round(aiMultiplier * 10000) / 100,
          aiReturn: Math.round((aiMultiplier - 1) * 1000) / 10,
          indexReturn: Math.round(niftyCumulativeReturn * 10) / 10,
        });
      }
    }

    // Return distribution from latest date
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

    // Risk metrics
    let riskMetrics: RiskMetrics | undefined;
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
      const avgLoss = losses > 0 ? totalLossReturn / losses : 0;

      riskMetrics = {
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
      };
    }

    // Overall breakdown
    let overallBreakdown: OverallReturnBreakdown | undefined;
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
      overallBreakdown = {
        dailyReturns: breakdownDailyReturns,
        finalMultiplier: Math.round(finalMultiplier * 10000) / 10000,
        finalReturn: Math.round((finalMultiplier - 1) * 1000) / 10,
        formula: '',
      };
    }

    // Top Picks data
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
    let latestTopPicksDateWithData: string | null = null;
    const topPicksDailyReturnsArr: number[] = [];

    for (const date of sortedDates) {
      const rec = recommendations.find(r => r.date === date);
      const dateBacktest = batchBacktestByDate[date];
      if (!rec || !rec.top_picks || !dateBacktest) continue;

      let dateReturn = 0, dateCount = 0;
      for (const pick of rec.top_picks) {
        const bt = dateBacktest[pick.symbol];
        const retVal = bt?.return_at_hold ?? bt?.return_1d;
        if (retVal !== undefined && retVal !== null) { dateReturn += retVal; dateCount++; }
      }

      if (dateCount > 0) latestTopPicksDateWithData = date;

      if (dateCount > 0) {
        const avgReturn = dateReturn / dateCount;
        topPicksDailyReturnsArr.push(avgReturn);
        topPicksMultiplier *= (1 + avgReturn / 100);
        const topPicksNiftyReturn = getNiftyReturnForDate(date);
        topPicksCumulative.push({
          date,
          value: Math.round(topPicksMultiplier * 10000) / 100,
          aiReturn: Math.round((topPicksMultiplier - 1) * 1000) / 10,
          indexReturn: Math.round(topPicksNiftyReturn * 10) / 10,
        });
      }
    }

    if (latestTopPicksDateWithData) {
      const rec = recommendations.find(r => r.date === latestTopPicksDateWithData);
      const dateBacktest = batchBacktestByDate[latestTopPicksDateWithData];
      if (rec && dateBacktest) {
        for (const pick of rec.top_picks) {
          const bt = dateBacktest[pick.symbol];
          const retVal = bt?.return_at_hold ?? bt?.return_1d;
          if (retVal !== undefined && retVal !== null) {
            for (const bucket of topPicksDistribution) {
              if (retVal >= bucket.min && retVal < bucket.max) { bucket.count++; bucket.stocks.push(pick.symbol); break; }
            }
          }
        }
      }
    }

    return {
      riskMetrics,
      returnDistribution: returnBuckets,
      cumulativeReturns: cumulativeData,
      overallBreakdown,
      topPicksCumulativeReturns: topPicksCumulative,
      topPicksReturnDistribution: topPicksDistribution,
      dateReturns: dateReturnsMap,
      allBacktestData: allBacktest,
      dailyReturnsArray: dailyReturns,
      topPicksDailyReturns: topPicksDailyReturnsArr,
    };
  }, [batchBacktestByDate, hasBacktestData, recommendations, nifty50Prices]);

  // Overall stats
  const overallStats = useMemo(() => {
    if (recommendations.length > 0 && chartData.dailyReturnsArray && chartData.dailyReturnsArray.length > 0) {
      const mean = chartData.dailyReturnsArray.reduce((a, b) => a + b, 0) / chartData.dailyReturnsArray.length;
      return {
        totalDays: recommendations.length,
        totalPredictions: accuracyMetrics.total_predictions,
        avgDailyReturn: Math.round(mean * 10) / 10,
        avgMonthlyReturn: 0,
        overallAccuracy: Math.round(accuracyMetrics.success_rate * 100),
        bestDay: null,
        worstDay: null,
      };
    }
    return { totalDays: recommendations.length, totalPredictions: 0, avgDailyReturn: 0, avgMonthlyReturn: 0, overallAccuracy: 0, bestDay: null, worstDay: null };
  }, [recommendations, chartData.dailyReturnsArray, accuracyMetrics]);

  // Filtered stats for Performance Summary
  const filteredStats = useMemo(() => {
    if (summaryMode === 'all50') {
      const signalTotals = recommendations.reduce(
        (acc, r) => ({ buy: acc.buy + r.summary.buy, sell: acc.sell + r.summary.sell, hold: acc.hold + r.summary.hold }),
        { buy: 0, sell: 0, hold: 0 }
      );
      return { totalDays: dates.length, avgDailyReturn: overallStats.avgDailyReturn, buySignals: signalTotals.buy, sellSignals: signalTotals.sell, holdSignals: signalTotals.hold };
    }

    const topPicksMean = chartData.topPicksDailyReturns.length > 0
      ? chartData.topPicksDailyReturns.reduce((a, b) => a + b, 0) / chartData.topPicksDailyReturns.length
      : 0;
    return {
      totalDays: dates.length,
      avgDailyReturn: Math.round(topPicksMean * 10) / 10,
      buySignals: recommendations.reduce((acc, r) => acc + r.top_picks.length, 0),
      sellSignals: 0,
      holdSignals: 0,
    };
  }, [summaryMode, dates.length, overallStats.avgDailyReturn, recommendations, chartData.topPicksDailyReturns]);

  // Date stats
  const dateStatsMap = useMemo(() => {
    return Object.fromEntries(dates.map(date => {
      const rec = recommendations.find(r => r.date === date);
      if (rec) {
        const stocks = Object.values(rec.analysis);
        return [date, {
          date,
          avgReturn1d: chartData.dateReturns[date] ?? 0,
          avgReturn1m: 0,
          totalStocks: stocks.length,
          correctPredictions: 0,
          accuracy: 0,
          buyCount: rec.summary.buy,
          sellCount: rec.summary.sell,
          holdCount: rec.summary.hold,
        }];
      }
      return [date, { date, avgReturn1d: 0, avgReturn1m: 0, totalStocks: 0, correctPredictions: 0, accuracy: 0, buyCount: 0, sellCount: 0, holdCount: 0 }];
    }));
  }, [dates, recommendations, chartData.dateReturns]);

  const getRecommendation = (date: string) => recommendations.find(r => r.date === date);

  const getFilteredStocks = (date: string) => {
    const rec = getRecommendation(date);
    if (!rec) return [];

    let stocks: StockAnalysis[];
    if (dateFilterMode === 'topPicks') {
      stocks = rec.top_picks.map(pick => rec.analysis[pick.symbol]).filter(Boolean);
    } else {
      stocks = Object.values(rec.analysis);
    }
    return [...stocks].sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity));
  };

  // Build ReturnBreakdown for the modal (from already-loaded batch data)
  const buildReturnBreakdown = useCallback((date: string): ReturnBreakdown | null => {
    const rec = recommendations.find(r => r.date === date);
    const dateBacktest = batchBacktestByDate[date];
    if (!rec || !dateBacktest) return null;

    const correctStocks: { symbol: string; decision: string; return1d: number }[] = [];
    const incorrectStocks: { symbol: string; decision: string; return1d: number }[] = [];
    let correctTotal = 0, incorrectTotal = 0;

    for (const symbol of Object.keys(rec.analysis)) {
      const stockAnalysis = rec.analysis[symbol];
      const bt = dateBacktest[symbol];
      const retVal = bt?.return_at_hold ?? bt?.return_1d;
      if (!stockAnalysis?.decision || retVal === undefined || retVal === null) continue;

      const isCorrect = (stockAnalysis.decision === 'BUY' || stockAnalysis.decision === 'HOLD') ? retVal > 0 : retVal < 0;
      const entry = { symbol, decision: stockAnalysis.decision, return1d: retVal };
      if (isCorrect) { correctStocks.push(entry); correctTotal += (stockAnalysis.decision === 'BUY' || stockAnalysis.decision === 'HOLD') ? retVal : Math.abs(retVal); }
      else { incorrectStocks.push(entry); incorrectTotal += (stockAnalysis.decision === 'BUY' || stockAnalysis.decision === 'HOLD') ? retVal : -Math.abs(retVal); }
    }

    const totalCount = correctStocks.length + incorrectStocks.length;
    if (totalCount === 0) return null;

    const correctAvg = correctStocks.length > 0 ? correctTotal / correctStocks.length : 0;
    const incorrectAvg = incorrectStocks.length > 0 ? incorrectTotal / incorrectStocks.length : 0;
    const correctWeight = correctStocks.length / totalCount;
    const incorrectWeight = incorrectStocks.length / totalCount;
    const weightedReturn = (correctAvg * correctWeight) + (incorrectAvg * incorrectWeight);

    correctStocks.sort((a, b) => Math.abs(b.return1d) - Math.abs(a.return1d));
    incorrectStocks.sort((a, b) => Math.abs(b.return1d) - Math.abs(a.return1d));

    return {
      correctPredictions: { count: correctStocks.length, totalReturn: correctTotal, avgReturn: correctAvg, stocks: correctStocks.slice(0, 5) },
      incorrectPredictions: { count: incorrectStocks.length, totalReturn: incorrectTotal, avgReturn: incorrectAvg, stocks: incorrectStocks.slice(0, 5) },
      weightedReturn: Math.round(weightedReturn * 10) / 10,
      formula: `(${correctAvg.toFixed(2)}% x ${correctStocks.length}/${totalCount}) + (${incorrectAvg.toFixed(2)}% x ${incorrectStocks.length}/${totalCount}) = ${weightedReturn.toFixed(2)}%`,
    };
  }, [recommendations, batchBacktestByDate]);

  // Load detailed backtest data for a specific date
  const loadDetailedBacktest = useCallback(async (date: string) => {
    setIsLoadingDetailed(true);
    setDetailedBacktest(null);
    setExpandedStock(null);
    try {
      const data = await api.getDetailedBacktest(date);
      setDetailedBacktest(data);
    } catch (error) {
      console.error('Failed to load detailed backtest:', error);
    } finally {
      setIsLoadingDetailed(false);
    }
  }, []);

  // Cleanup poll on unmount
  useEffect(() => {
    return () => {
      if (backtestPollRef.current) clearInterval(backtestPollRef.current);
    };
  }, []);

  const handleRunBacktest = useCallback(async () => {
    if (!backtestDateInput) return;
    setBacktestMessage(null);
    if (backtestPollRef.current) { clearInterval(backtestPollRef.current); backtestPollRef.current = null; }

    // If date already has data in the loaded bundle, select it and load detailed view
    if (dates.includes(backtestDateInput)) {
      setSelectedDate(backtestDateInput);
      loadDetailedBacktest(backtestDateInput);
      return;
    }

    // Try fetching existing data first
    setIsRunningBacktest(true);
    setBacktestMessage({ type: 'progress', text: 'Checking for existing data...' });
    try {
      const data = await api.getDetailedBacktest(backtestDateInput);
      if (data && data.stocks && data.stocks.length > 0) {
        setSelectedDate(backtestDateInput);
        setDetailedBacktest(data);
        setIsRunningBacktest(false);
        setBacktestMessage(null);
        return;
      }
    } catch {
      // No existing data, proceed to run analysis
    }

    // No data — auto-trigger bulk analysis for this date
    setBacktestMessage({ type: 'progress', text: `Starting analysis for ${backtestDateInput}... This runs all 50 stocks through the AI pipeline.` });
    try {
      await api.runBulkAnalysis(backtestDateInput, {
        deep_think_model: settings.deepThinkModel,
        quick_think_model: settings.quickThinkModel,
        provider: settings.provider,
        api_key: settings.anthropicApiKey || undefined,
        max_debate_rounds: settings.maxDebateRounds,
        parallel_workers: settings.parallelWorkers,
      });

      // Poll for progress
      backtestPollRef.current = setInterval(async () => {
        try {
          const status = await api.getBulkAnalysisStatus();
          const pct = status.total > 0 ? Math.round((status.completed / status.total) * 100) : 0;
          const currentStocks = status.current_symbols?.join(', ') || status.current_symbol || '';

          if (status.status === 'completed' || status.status === 'idle') {
            if (backtestPollRef.current) { clearInterval(backtestPollRef.current); backtestPollRef.current = null; }
            setBacktestMessage({ type: 'progress', text: 'Analysis complete! Loading detailed backtest...' });
            // Load the results
            try {
              const data = await api.getDetailedBacktest(backtestDateInput);
              setSelectedDate(backtestDateInput);
              setDetailedBacktest(data);
              setBacktestMessage(null);
            } catch {
              setBacktestMessage({ type: 'error', text: 'Analysis completed but failed to load results. Try clicking a date card.' });
            }
            setIsRunningBacktest(false);
          } else if (status.status === 'failed' || status.cancelled) {
            if (backtestPollRef.current) { clearInterval(backtestPollRef.current); backtestPollRef.current = null; }
            setIsRunningBacktest(false);
            setBacktestMessage({ type: 'error', text: `Analysis ${status.cancelled ? 'cancelled' : 'failed'}. ${status.completed}/${status.total} stocks completed.` });
          } else {
            setBacktestMessage({
              type: 'progress',
              text: `Analyzing stocks... ${status.completed}/${status.total} done (${pct}%)${currentStocks ? ` — Currently: ${currentStocks}` : ''}`
            });
          }
        } catch {
          // Poll error, keep trying
        }
      }, 3000);
    } catch (error) {
      console.error('Failed to start analysis:', error);
      setIsRunningBacktest(false);
      setBacktestMessage({ type: 'error', text: 'Failed to start analysis. Check that the backend is running.' });
    }
  }, [backtestDateInput, dates, loadDetailedBacktest, settings]);

  const handleCancelBacktest = useCallback(async () => {
    try {
      await api.cancelBulkAnalysis();
    } catch {
      // ignore
    }
    if (backtestPollRef.current) { clearInterval(backtestPollRef.current); backtestPollRef.current = null; }
    setIsRunningBacktest(false);
    setBacktestMessage({ type: 'error', text: 'Analysis cancelled.' });
  }, []);

  // ==========================================================
  // RENDER
  // ==========================================================

  if (isLoading) {
    return (
      <div className="min-h-[50vh] flex items-center justify-center">
        <div className="text-center">
          <div className="relative w-16 h-16 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-4 border-nifty-100 dark:border-nifty-900/40" />
            <div className="absolute inset-0 rounded-full border-4 border-t-nifty-500 animate-spin" />
          </div>
          <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300">Loading historical data...</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Fetching recommendations & backtest results</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Page Header */}
      <section className="card p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-display font-bold text-gray-900 dark:text-gray-100">
              Historical <span className="gradient-text">Performance</span>
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
              AI recommendations with real backtest results and market validation
            </p>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-nifty-50 dark:bg-nifty-900/30">
              <BarChart3 className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />
              <span className="font-bold text-nifty-700 dark:text-nifty-300">{dates.length}</span>
              <span className="text-gray-500 dark:text-gray-400">days</span>
            </div>
            {loadTimeMs !== null && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-900/20">
                <Zap className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                <span className="font-bold text-emerald-700 dark:text-emerald-300">{loadTimeMs}ms</span>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Prediction Accuracy - Hero Card */}
      <section className="card p-5">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-nifty-50 dark:bg-nifty-900/30">
              <Target className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
            </div>
            <div>
              <h2 className="font-bold text-gray-900 dark:text-gray-100">Prediction Accuracy</h2>
              <p className="text-[10px] text-gray-500 dark:text-gray-400">{accuracyMetrics.total_predictions} predictions tracked</p>
            </div>
          </div>
          <button
            onClick={() => setShowAccuracyModal(true)}
            className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-gray-500 dark:text-gray-400 hover:text-nifty-600 dark:hover:text-nifty-400 hover:bg-gray-50 dark:hover:bg-slate-700/60 rounded-lg transition-colors"
          >
            <HelpCircle className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">How it works</span>
          </button>
        </div>

        <div className="flex flex-col sm:flex-row items-center gap-6">
          {/* Circular gauge for Overall accuracy */}
          <div className="flex-shrink-0 text-center">
            <div className="relative w-28 h-28 sm:w-32 sm:h-32">
              <svg className="w-full h-full transform -rotate-90" viewBox="0 0 128 128">
                <circle cx="64" cy="64" r="54" stroke="currentColor" strokeWidth="10" fill="transparent" className="text-gray-100 dark:text-slate-700" />
                <circle cx="64" cy="64" r="54" strokeWidth="10" fill="transparent"
                  strokeDasharray={`${accuracyMetrics.success_rate * 339.29} 339.29`}
                  className="text-nifty-500 dark:text-nifty-400"
                  stroke="currentColor"
                  strokeLinecap="round"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-gray-100 tabular-nums">
                  {(accuracyMetrics.success_rate * 100).toFixed(0)}%
                </span>
                <span className="text-[10px] font-medium text-gray-400 dark:text-gray-500">Overall</span>
              </div>
            </div>
            <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-1.5">
              {accuracyMetrics.correct_predictions}/{accuracyMetrics.total_predictions} correct
            </p>
          </div>

          {/* Progress bars for Buy / Sell / Hold */}
          <div className="flex-1 space-y-3.5 w-full">
            {/* Buy */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <TrendingUp className="w-3.5 h-3.5 text-emerald-500 dark:text-emerald-400" />
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Buy Accuracy</span>
                </div>
                <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400 tabular-nums">
                  {(accuracyMetrics.buy_accuracy * 100).toFixed(0)}%
                </span>
              </div>
              <div className="h-2 bg-gray-100 dark:bg-slate-700 rounded-full overflow-hidden">
                <div className="h-full bg-emerald-500 dark:bg-emerald-400 rounded-full transition-all duration-700"
                  style={{ width: `${Math.max(accuracyMetrics.buy_accuracy * 100, 2)}%` }}
                />
              </div>
            </div>

            {/* Sell */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <TrendingDown className="w-3.5 h-3.5 text-red-500 dark:text-red-400" />
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Sell Accuracy</span>
                </div>
                <span className="text-sm font-bold text-red-600 dark:text-red-400 tabular-nums">
                  {(accuracyMetrics.sell_accuracy * 100).toFixed(0)}%
                </span>
              </div>
              <div className="h-2 bg-gray-100 dark:bg-slate-700 rounded-full overflow-hidden">
                <div className="h-full bg-red-500 dark:bg-red-400 rounded-full transition-all duration-700"
                  style={{ width: `${Math.max(accuracyMetrics.sell_accuracy * 100, 2)}%` }}
                />
              </div>
            </div>

            {/* Hold */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <Minus className="w-3.5 h-3.5 text-amber-500 dark:text-amber-400" />
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Hold Accuracy</span>
                </div>
                <span className="text-sm font-bold text-amber-600 dark:text-amber-400 tabular-nums">
                  {(accuracyMetrics.hold_accuracy * 100).toFixed(0)}%
                </span>
              </div>
              <div className="h-2 bg-gray-100 dark:bg-slate-700 rounded-full overflow-hidden">
                <div className="h-full bg-amber-500 dark:bg-amber-400 rounded-full transition-all duration-700"
                  style={{ width: `${Math.max(accuracyMetrics.hold_accuracy * 100, 2)}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Accuracy Trend Chart */}
      <section className="card p-5">
        <SectionHeader
          icon={<LineChart className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />}
          title="Accuracy Trend"
          subtitle={accuracyTrendData.length > 0 ? `${accuracyTrendData.length} trading days tracked` : undefined}
        />
        <AccuracyTrendChart
          height={200}
          data={accuracyTrendData}
        />
      </section>

      {/* Risk Metrics */}
      <section className="card p-5">
        <SectionHeader
          icon={<Shield className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />}
          title="Risk Metrics"
          subtitle={chartData.riskMetrics ? `${chartData.riskMetrics.totalTrades} trades analyzed` : undefined}
        />
        <RiskMetricsCard metrics={chartData.riskMetrics} />
      </section>

      {/* Portfolio Simulator */}
      <PortfolioSimulator
        recommendations={recommendations}
        nifty50Prices={nifty50Prices}
        allBacktestData={chartData.allBacktestData}
      />

      {/* Date Selector */}
      <div className="card p-5">
        <SectionHeader
          icon={<Calendar className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />}
          title="Select Date"
          right={
            <div className="flex items-center gap-2">
              <Filter className="w-3.5 h-3.5 text-gray-400" />
              <InvestmentModeToggle mode={dateFilterMode} onChange={setDateFilterMode} />
            </div>
          }
        />

        {/* Backtest Date Input */}
        <div className="flex items-center gap-2 mb-4 p-3 rounded-xl bg-gray-50 dark:bg-slate-700/40 border border-gray-100 dark:border-slate-700">
          <Search className="w-4 h-4 text-gray-400 flex-shrink-0" />
          <input
            type="date"
            value={backtestDateInput}
            onChange={(e) => setBacktestDateInput(e.target.value)}
            className="flex-1 px-3 py-1.5 text-sm bg-white dark:bg-slate-600 border border-gray-200 dark:border-slate-500 rounded-lg focus:ring-2 focus:ring-nifty-500 focus:border-transparent outline-none text-gray-900 dark:text-gray-100"
            max={new Date().toISOString().split('T')[0]}
          />
          <button
            onClick={handleRunBacktest}
            disabled={!backtestDateInput || isRunningBacktest}
            className="flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium text-white bg-nifty-600 hover:bg-nifty-700 disabled:bg-gray-300 dark:disabled:bg-slate-600 disabled:cursor-not-allowed rounded-lg transition-colors"
          >
            {isRunningBacktest ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Running...
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5" />
                Run Backtest
              </>
            )}
          </button>
        </div>

        {/* Backtest feedback message */}
        {backtestMessage && (
          <div className={`mb-4 rounded-xl text-sm border ${
            backtestMessage.type === 'error'
              ? 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800'
              : backtestMessage.type === 'progress'
              ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800'
              : 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800'
          }`}>
            <div className="flex items-center gap-2 px-4 py-3">
              {backtestMessage.type === 'progress' && <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" />}
              <span className="flex-1">{backtestMessage.text}</span>
              {backtestMessage.type === 'progress' ? (
                <button
                  onClick={handleCancelBacktest}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors"
                >
                  <XCircle className="w-3.5 h-3.5" />
                  Cancel
                </button>
              ) : (
                <button onClick={() => setBacktestMessage(null)} className="text-current opacity-50 hover:opacity-100 font-bold">×</button>
              )}
            </div>
            {backtestMessage.type === 'progress' && (
              <div className="px-4 pb-3 pt-0 flex items-start gap-1.5 text-xs text-amber-600/70 dark:text-amber-400/60">
                <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                <span>Note: Price data & technical indicators use historical data for the selected date. News & analyst ratings reflect current data (yfinance limitation).</span>
              </div>
            )}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {dates.map((date) => {
            const rec = getRecommendation(date);
            const stats = dateStatsMap[date];
            const avgReturn = stats?.avgReturn1d ?? 0;
            const hasData = chartData.dateReturns[date] !== undefined;
            const isPositive = avgReturn >= 0;

            const filteredSummary = dateFilterMode === 'topPicks'
              ? { buy: rec?.top_picks.length || 0, sell: 0, hold: 0 }
              : rec?.summary || { buy: 0, sell: 0, hold: 0 };

            return (
              <div key={date} className="relative group">
                <button
                  onClick={() => setSelectedDate(selectedDate === date ? null : date)}
                  className={`px-3 py-2.5 rounded-xl text-xs font-medium transition-all min-w-[90px] border ${
                    selectedDate === date
                      ? 'bg-nifty-600 text-white ring-2 ring-nifty-400/50 border-nifty-500 shadow-lg shadow-nifty-500/20'
                      : 'bg-white dark:bg-slate-700/80 text-gray-700 dark:text-gray-200 border-gray-200 dark:border-slate-600 hover:border-nifty-300 dark:hover:border-nifty-700 hover:shadow-md'
                  }`}
                >
                  <div className="font-bold">{new Date(date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })}</div>
                  {!hasData ? (
                    <div className={`text-sm mt-0.5 ${selectedDate === date ? 'text-white/60' : 'text-gray-400 dark:text-gray-500'}`}>
                      Pending
                    </div>
                  ) : (
                    <div className={`text-sm font-bold mt-0.5 ${
                      selectedDate === date ? 'text-white' : getValueColorClass(avgReturn)
                    }`}>
                      {isPositive ? '+' : ''}{fmtPct(avgReturn)}%
                    </div>
                  )}
                  <div className={`text-[10px] mt-0.5 ${selectedDate === date ? 'text-white/80' : 'opacity-60'}`}>
                    {filteredSummary.buy}B/{filteredSummary.sell}S/{filteredSummary.hold}H
                  </div>
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); setReturnModalDate(date); setShowReturnModal(true); }}
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
              className="px-3 py-2.5 rounded-xl text-xs font-medium min-w-[100px] bg-gradient-to-br from-nifty-500 to-nifty-700 text-white hover:from-nifty-600 hover:to-nifty-800 transition-all text-left shadow-lg shadow-nifty-500/20 border border-nifty-400/30"
            >
              <div className="font-bold flex items-center gap-1">
                <Award className="w-3 h-3" />
                Overall
              </div>
              <div className="text-sm font-bold mt-0.5">
                {overallStats.avgDailyReturn >= 0 ? '+' : ''}{fmtPct(overallStats.avgDailyReturn)}%
              </div>
              <div className="text-[10px] mt-0.5 text-white/80">
                {overallStats.overallAccuracy}% accurate
              </div>
            </button>
          </div>
        </div>
      </div>

      {/* Selected Date Details */}
      {selectedDate && (
        <div className="card overflow-hidden">
          <div className="p-4 border-b border-gray-100 dark:border-slate-700 bg-gradient-to-r from-gray-50 to-white dark:from-slate-700/50 dark:to-slate-800">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-3">
                <div className="p-1.5 rounded-lg bg-nifty-100 dark:bg-nifty-900/40">
                  <Calendar className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />
                </div>
                <h2 className="font-bold text-gray-900 dark:text-gray-100">
                  {new Date(selectedDate).toLocaleDateString('en-IN', {
                    weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
                  })}
                </h2>
                <InvestmentModeToggle mode={dateFilterMode} onChange={setDateFilterMode} />
              </div>
              <div className="flex items-center gap-3 text-xs">
                {dateFilterMode === 'all50' ? (
                  <>
                    <span className="flex items-center gap-1 px-2 py-1 rounded-md bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 font-medium">
                      <ArrowUpRight className="w-3 h-3" />
                      {getRecommendation(selectedDate)?.summary.buy} Buy
                    </span>
                    <span className="flex items-center gap-1 px-2 py-1 rounded-md bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 font-medium">
                      <ArrowDownRight className="w-3 h-3" />
                      {getRecommendation(selectedDate)?.summary.sell} Sell
                    </span>
                    <span className="flex items-center gap-1 px-2 py-1 rounded-md bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400 font-medium">
                      <Minus className="w-3 h-3" />
                      {getRecommendation(selectedDate)?.summary.hold} Hold
                    </span>
                  </>
                ) : (
                  <span className="flex items-center gap-1 px-2 py-1 rounded-md bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 font-medium">
                    <TrendingUp className="w-3 h-3" />
                    {getRecommendation(selectedDate)?.top_picks.length} Top Picks (BUY)
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Detailed Backtest Action Bar */}
          <div className="px-4 py-2 border-b border-gray-100 dark:border-slate-700 flex items-center justify-between">
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {detailedBacktest?.date === selectedDate
                ? `Detailed backtest: ${detailedBacktest.total_stocks} stocks with live P&L`
                : 'View live P&L with full explainability'}
            </span>
            <button
              onClick={() => {
                if (detailedBacktest?.date === selectedDate) {
                  setDetailedBacktest(null);
                } else {
                  loadDetailedBacktest(selectedDate);
                }
              }}
              disabled={isLoadingDetailed}
              className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium text-nifty-600 dark:text-nifty-400 hover:bg-nifty-50 dark:hover:bg-nifty-900/20 rounded-lg transition-colors disabled:opacity-50"
            >
              {isLoadingDetailed ? (
                <><Loader2 className="w-3 h-3 animate-spin" /> Loading...</>
              ) : detailedBacktest?.date === selectedDate ? (
                <><ChevronRight className="w-3 h-3" /> Simple View</>
              ) : (
                <><Search className="w-3 h-3" /> View Detailed</>
              )}
            </button>
          </div>

          {detailedBacktest && detailedBacktest.date === selectedDate ? (
            /* Detailed expandable view */
            <div className="divide-y divide-gray-50 dark:divide-slate-700/50 max-h-[70vh] overflow-y-auto">
              {detailedBacktest.stocks.map((stock) => {
                const isExpanded = expandedStock === stock.symbol;
                const returnVal = stock.return_at_hold ?? stock.return_current;
                const isPositiveReturn = returnVal !== null && returnVal >= 0;

                return (
                  <div key={stock.symbol}>
                    {/* Stock Summary Row */}
                    <button
                      onClick={() => setExpandedStock(isExpanded ? null : stock.symbol)}
                      className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50/80 dark:hover:bg-slate-700/30 transition-colors text-left"
                    >
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        <RankBadge rank={stock.rank} size="small" />
                        <span className="font-semibold text-gray-900 dark:text-gray-100 text-sm">{stock.symbol}</span>
                        <DecisionBadge decision={stock.decision} size="small" />
                        <HoldDaysBadge holdDays={stock.hold_days} decision={stock.decision} />
                      </div>
                      <div className="flex items-center gap-3">
                        {stock.price_at_prediction !== null && (
                          <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums hidden sm:inline">
                            ₹{stock.price_at_prediction.toFixed(0)}
                            <span className="mx-1">→</span>
                            ₹{(stock.hold_period_active ? stock.price_current : stock.price_at_hold_end)?.toFixed(0) ?? '—'}
                          </span>
                        )}
                        {returnVal !== null && (
                          <span className={`inline-flex items-center gap-1 text-xs font-bold tabular-nums px-2 py-0.5 rounded-full ${
                            isPositiveReturn
                              ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400'
                              : 'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400'
                          }`}>
                            {isPositiveReturn ? '+' : ''}{returnVal.toFixed(2)}%
                          </span>
                        )}
                        {stock.hold_period_active && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 font-medium">
                            LIVE
                          </span>
                        )}
                        <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                      </div>
                    </button>

                    {/* Expanded Detail */}
                    {isExpanded && (
                      <div className="px-4 pb-4 space-y-4 bg-gray-50/50 dark:bg-slate-800/50 border-t border-gray-100 dark:border-slate-700">

                        {/* P&L Formula */}
                        <div className="mt-3 p-3 rounded-lg bg-white dark:bg-slate-700/60 border border-gray-100 dark:border-slate-600">
                          <div className="flex items-center gap-2 mb-2">
                            <Calculator className="w-3.5 h-3.5 text-nifty-600 dark:text-nifty-400" />
                            <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">P&L Formula</span>
                          </div>
                          <pre className="text-xs text-gray-600 dark:text-gray-300 font-mono whitespace-pre-wrap leading-relaxed">
                            {stock.formula || 'No formula available'}
                          </pre>
                        </div>

                        {/* Hold Period Progress */}
                        <div className="p-3 rounded-lg bg-white dark:bg-slate-700/60 border border-gray-100 dark:border-slate-600">
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <Clock className="w-3.5 h-3.5 text-nifty-600 dark:text-nifty-400" />
                              <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">Hold Period</span>
                            </div>
                            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                              stock.hold_period_active
                                ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
                                : 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300'
                            }`}>
                              {stock.hold_period_active ? 'Active' : 'Completed'}
                            </span>
                          </div>
                          <div className="h-2.5 bg-gray-200 dark:bg-slate-600 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all ${
                                stock.hold_period_active
                                  ? 'bg-amber-500 dark:bg-amber-400'
                                  : 'bg-emerald-500 dark:bg-emerald-400'
                              }`}
                              style={{ width: `${Math.min((stock.hold_days_elapsed / Math.max(stock.hold_days, 1)) * 100, 100)}%` }}
                            />
                          </div>
                          <div className="flex justify-between mt-1 text-[10px] text-gray-500 dark:text-gray-400">
                            <span>{stock.hold_days_elapsed} / {stock.hold_days} days elapsed</span>
                            {stock.prediction_correct !== null && (
                              <span className={stock.prediction_correct ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-500 dark:text-red-400'}>
                                Prediction {stock.prediction_correct ? 'Correct' : 'Incorrect'}
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Decision Reasoning */}
                        <div className="p-3 rounded-lg bg-white dark:bg-slate-700/60 border border-gray-100 dark:border-slate-600">
                          <div className="flex items-center gap-2 mb-2">
                            <FileText className="w-3.5 h-3.5 text-nifty-600 dark:text-nifty-400" />
                            <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">Decision Reasoning</span>
                          </div>
                          <div className="flex items-center gap-2 mb-2">
                            <DecisionBadge decision={stock.decision} size="small" />
                            <span className="text-xs text-gray-500 dark:text-gray-400">
                              {stock.confidence} confidence, {stock.risk} risk
                            </span>
                          </div>
                          <p className="text-xs text-gray-600 dark:text-gray-300 leading-relaxed max-h-32 overflow-y-auto">
                            {stock.raw_analysis || 'No analysis text available'}
                          </p>
                        </div>

                        {/* Agent Reports */}
                        {Object.keys(stock.agent_summary).length > 0 && (
                          <div className="p-3 rounded-lg bg-white dark:bg-slate-700/60 border border-gray-100 dark:border-slate-600">
                            <div className="flex items-center gap-2 mb-3">
                              <MessageSquare className="w-3.5 h-3.5 text-nifty-600 dark:text-nifty-400" />
                              <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">Agent Reports</span>
                            </div>
                            <div className="flex gap-1 mb-3">
                              {Object.keys(stock.agent_summary).map((key) => (
                                <button
                                  key={key}
                                  onClick={(e) => { e.stopPropagation(); setActiveAgentTab(key); }}
                                  className={`px-2.5 py-1 text-[10px] font-medium rounded-md transition-colors capitalize ${
                                    activeAgentTab === key
                                      ? 'bg-nifty-100 dark:bg-nifty-900/40 text-nifty-700 dark:text-nifty-300'
                                      : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-slate-600'
                                  }`}
                                >
                                  {key.replace('_', ' ')}
                                </button>
                              ))}
                            </div>
                            <p className="text-xs text-gray-600 dark:text-gray-300 leading-relaxed max-h-24 overflow-y-auto">
                              {stock.agent_summary[activeAgentTab] || 'No report available for this agent'}
                            </p>
                          </div>
                        )}

                        {/* Debate Summary */}
                        {Object.keys(stock.debate_summary).length > 0 && (
                          <div className="p-3 rounded-lg bg-white dark:bg-slate-700/60 border border-gray-100 dark:border-slate-600">
                            <div className="flex items-center gap-2 mb-2">
                              <Activity className="w-3.5 h-3.5 text-nifty-600 dark:text-nifty-400" />
                              <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">Debate Summary</span>
                            </div>
                            <div className="space-y-2">
                              {Object.entries(stock.debate_summary).map(([type, summary]) => (
                                <div key={type} className="text-xs">
                                  <span className="font-medium text-gray-700 dark:text-gray-200 capitalize">{type}:</span>{' '}
                                  <span className="text-gray-600 dark:text-gray-300">{summary}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Link to full stock detail */}
                        <Link
                          to={`/stock/${stock.symbol}`}
                          className="flex items-center gap-1.5 text-xs font-medium text-nifty-600 dark:text-nifty-400 hover:underline"
                        >
                          View full stock detail
                          <ChevronRight className="w-3 h-3" />
                        </Link>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            /* Simple stock list */
            <div className="divide-y divide-gray-50 dark:divide-slate-700/50 max-h-[60vh] sm:max-h-[400px] overflow-y-auto">
              {getFilteredStocks(selectedDate).map((stock: StockAnalysis) => {
                const bt = batchBacktestByDate[selectedDate]?.[stock.symbol];
                let nextDayReturn: number | null = null;
                let predictionCorrect: boolean | null = null;

                if (bt) {
                  nextDayReturn = bt.return_at_hold ?? bt.return_1d ?? null;
                  if (nextDayReturn !== null) {
                    predictionCorrect = (stock.decision === 'BUY' || stock.decision === 'HOLD')
                      ? nextDayReturn > 0
                      : nextDayReturn < 0;
                  }
                }

                return (
                  <Link
                    key={stock.symbol}
                    to={`/stock/${stock.symbol}`}
                    className="flex items-center justify-between px-4 py-2.5 hover:bg-gray-50/80 dark:hover:bg-slate-700/30 transition-colors group"
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <RankBadge rank={stock.rank} size="small" />
                      <span className="font-semibold text-gray-900 dark:text-gray-100 text-sm">{stock.symbol}</span>
                      <span className="text-xs text-gray-500 dark:text-gray-400 hidden sm:inline truncate">{stock.company_name}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <DecisionBadge decision={stock.decision} size="small" />
                      <HoldDaysBadge holdDays={stock.hold_days} decision={stock.decision} />
                      {nextDayReturn !== null && (
                        <span className={`inline-flex items-center gap-1 text-xs font-semibold tabular-nums px-1.5 py-0.5 rounded-full ${
                          predictionCorrect === true
                            ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400'
                            : predictionCorrect === false
                            ? 'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400'
                            : getValueColorClass(nextDayReturn)
                        }`} title={bt?.hold_days ? `${bt.hold_days}d return` : '1d return'}>
                          {nextDayReturn >= 0 ? '+' : ''}{fmtPct(nextDayReturn)}%
                          {bt?.hold_days && <span className="text-[9px] opacity-60">/{bt.hold_days}d</span>}
                        </span>
                      )}
                      <ChevronRight className="w-4 h-4 text-gray-300 dark:text-gray-600 group-hover:text-nifty-600 dark:group-hover:text-nifty-400 transition-colors" />
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Performance Summary */}
      <div className="card p-5">
        <SectionHeader
          icon={<Activity className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />}
          title="Performance Summary"
          right={<InvestmentModeToggle mode={summaryMode} onChange={setSummaryMode} />}
        />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Days Tracked', value: filteredStats.totalDays.toString(), icon: <Clock className="w-4 h-4" />, color: 'nifty', modal: 'daysTracked' as SummaryModalType },
            { label: 'Avg Return', value: `${filteredStats.avgDailyReturn >= 0 ? '+' : ''}${fmtPct(filteredStats.avgDailyReturn)}%`, icon: <TrendingUp className="w-4 h-4" />, color: filteredStats.avgDailyReturn >= 0 ? 'emerald' : 'red', modal: 'avgReturn' as SummaryModalType },
            { label: summaryMode === 'topPicks' ? 'Top Picks' : 'Buy Signals', value: filteredStats.buySignals.toString(), icon: <ArrowUpRight className="w-4 h-4" />, color: 'emerald', modal: 'buySignals' as SummaryModalType },
            { label: 'Sell Signals', value: filteredStats.sellSignals.toString(), icon: <ArrowDownRight className="w-4 h-4" />, color: 'red', modal: 'sellSignals' as SummaryModalType },
          ].map(({ label, value, icon, color, modal }) => (
            <div
              key={label}
              className="p-4 rounded-xl bg-gray-50/80 dark:bg-slate-700/40 border border-gray-100 dark:border-slate-700 cursor-pointer hover:border-nifty-200 dark:hover:border-nifty-800 hover:shadow-sm transition-all group"
              onClick={() => setActiveSummaryModal(modal)}
            >
              <div className={`text-2xl font-bold tabular-nums text-${color}-600 dark:text-${color}-400`}>{value}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1.5 mt-1">
                <span className="opacity-50">{icon}</span>
                {label}
                <HelpCircle className="w-3 h-3 opacity-0 group-hover:opacity-50 transition-opacity" />
              </div>
            </div>
          ))}
        </div>
        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-3 text-center">
          {summaryMode === 'topPicks'
            ? 'Performance based on Top Picks recommendations only (3 stocks per day)'
            : 'Returns measured over hold period (or 1-day when no hold period specified)'}
        </p>
      </div>

      {/* AI vs Nifty50 Index Comparison */}
      <section className="card p-5">
        <SectionHeader
          icon={<BarChart3 className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />}
          title="AI Strategy vs Nifty50 Index"
          right={<InvestmentModeToggle mode={indexChartMode} onChange={setIndexChartMode} />}
        />
        <IndexComparisonChart
          height={220}
          data={(indexChartMode === 'topPicks' ? chartData.topPicksCumulativeReturns : chartData.cumulativeReturns) ?? []}
        />
        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-2 text-center">
          {(indexChartMode === 'topPicks' ? chartData.topPicksCumulativeReturns : chartData.cumulativeReturns)?.length ? (
            <>Cumulative returns for {indexChartMode === 'topPicks' ? 'Top Picks' : 'All 50 stocks'} over {(indexChartMode === 'topPicks' ? chartData.topPicksCumulativeReturns : chartData.cumulativeReturns)?.length} trading days</>
          ) : (
            <>AI strategy vs Nifty50 index cumulative returns</>
          )}
        </p>
      </section>

      {/* Return Distribution */}
      <section className="card p-5">
        <SectionHeader
          icon={<PieChart className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />}
          title="Return Distribution"
          right={<InvestmentModeToggle mode={distributionMode} onChange={setDistributionMode} />}
        />
        <ReturnDistributionChart
          height={200}
          data={(distributionMode === 'topPicks' ? chartData.topPicksReturnDistribution : chartData.returnDistribution) ?? []}
        />
        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-2 text-center">
          {(distributionMode === 'topPicks' ? chartData.topPicksReturnDistribution : chartData.returnDistribution)?.some(b => b.count > 0) ? (
            <>Distribution of {distributionMode === 'topPicks' ? 'Top Picks' : 'all 50 stocks'} hold-period returns. Click bars to see stocks.</>
          ) : (
            <>Distribution of hold-period returns across all predictions</>
          )}
        </p>
      </section>

      {/* Modals */}
      <AccuracyExplainModal isOpen={showAccuracyModal} onClose={() => setShowAccuracyModal(false)} metrics={accuracyMetrics} />

      <ReturnExplainModal
        isOpen={showReturnModal}
        onClose={() => setShowReturnModal(false)}
        breakdown={returnModalDate ? buildReturnBreakdown(returnModalDate) : null}
        date={returnModalDate || ''}
      />

      <OverallReturnModal
        isOpen={showOverallModal}
        onClose={() => setShowOverallModal(false)}
        breakdown={chartData.overallBreakdown}
        cumulativeData={chartData.cumulativeReturns}
      />

      {/* Performance Summary Modals */}
      <InfoModal isOpen={activeSummaryModal === 'daysTracked'} onClose={() => setActiveSummaryModal(null)} title="Days Tracked" icon={<Calendar className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />}>
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
          <p><strong>Days Tracked</strong> shows the total number of trading days where AI recommendations have been recorded and analyzed.</p>
          <div className="p-3 bg-nifty-50 dark:bg-nifty-900/20 rounded-lg">
            <div className="font-semibold text-nifty-800 dark:text-nifty-200 mb-1">Current Count:</div>
            <div className="text-2xl font-bold text-nifty-600 dark:text-nifty-400">{filteredStats.totalDays} days</div>
          </div>
          <p className="text-xs text-gray-500">Each day includes analysis for {summaryMode === 'topPicks' ? '3 top picks' : 'all 50 Nifty stocks'}.</p>
        </div>
      </InfoModal>

      <InfoModal isOpen={activeSummaryModal === 'avgReturn'} onClose={() => setActiveSummaryModal(null)} title="Average Return" icon={<TrendingUp className="w-5 h-5 text-green-600 dark:text-green-400" />}>
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
          <p><strong>Average Return</strong> measures the mean percentage price change over each stock's recommended hold period.</p>
          <div className="p-3 bg-gray-100 dark:bg-slate-700 rounded-lg">
            <div className="font-semibold mb-1">How it's calculated:</div>
            <ol className="text-xs space-y-1 list-decimal list-inside">
              <li>Record stock price at recommendation time</li>
              <li>Record price after the recommended hold period</li>
              <li>Calculate: (Exit - Entry) / Entry x 100</li>
              <li>Average all returns across stocks</li>
            </ol>
          </div>
          <div className={`p-3 ${filteredStats.avgDailyReturn >= 0 ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20'} rounded-lg`}>
            <div className="text-xs text-gray-500 mb-1">Current Average:</div>
            <div className={`text-xl font-bold ${filteredStats.avgDailyReturn >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {filteredStats.avgDailyReturn >= 0 ? '+' : ''}{filteredStats.avgDailyReturn.toFixed(2)}%
            </div>
          </div>
        </div>
      </InfoModal>

      <InfoModal isOpen={activeSummaryModal === 'buySignals'} onClose={() => setActiveSummaryModal(null)} title={summaryMode === 'topPicks' ? 'Top Pick Signals' : 'Buy Signals'} icon={<TrendingUp className="w-5 h-5 text-green-600 dark:text-green-400" />}>
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
          <p><strong>{summaryMode === 'topPicks' ? 'Top Pick Signals' : 'Buy Signals'}</strong> counts all {summaryMode === 'topPicks' ? 'Top Picks' : 'BUY recommendations'} across all tracked days.</p>
          <div className="p-2 bg-gray-100 dark:bg-slate-700 rounded-lg flex justify-between items-center">
            <span>Total:</span>
            <strong className="text-green-600 text-lg">{filteredStats.buySignals}</strong>
          </div>
        </div>
      </InfoModal>

      <InfoModal isOpen={activeSummaryModal === 'sellSignals'} onClose={() => setActiveSummaryModal(null)} title="Sell Signals" icon={<TrendingDown className="w-5 h-5 text-red-600 dark:text-red-400" />}>
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
          <p><strong>Sell Signals</strong> counts every SELL recommendation issued across all tracked days.</p>
          {summaryMode === 'topPicks' ? (
            <div className="p-2 bg-amber-50 dark:bg-amber-900/20 rounded-lg text-xs">
              <strong>Note:</strong> Top Picks mode only shows BUY recommendations, so sell signals are 0.
            </div>
          ) : (
            <div className="p-2 bg-gray-100 dark:bg-slate-700 rounded-lg flex justify-between items-center">
              <span>Total:</span>
              <strong className="text-red-600 text-lg">{filteredStats.sellSignals}</strong>
            </div>
          )}
        </div>
      </InfoModal>
    </div>
  );
}
