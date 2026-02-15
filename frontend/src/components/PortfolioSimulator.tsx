import { useState, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Legend, BarChart, Bar, Cell, LabelList } from 'recharts';
import { Calculator, ChevronDown, ChevronUp, IndianRupee, Settings2, BarChart3, Info, TrendingUp, TrendingDown, ArrowRightLeft, Wallet, PiggyBank, Receipt, HelpCircle } from 'lucide-react';
import { calculateBrokerage, formatINR, type BrokerageBreakdown } from '../utils/brokerageCalculator';
import InfoModal, { InfoButton } from './InfoModal';
import type { Decision, DailyRecommendation } from '../types';

interface PortfolioSimulatorProps {
  className?: string;
  recommendations?: DailyRecommendation[];
  nifty50Prices?: Record<string, number>;
  allBacktestData?: Record<string, Record<string, number>>;
}

export type InvestmentMode = 'all50' | 'topPicks';

interface TradeRecord {
  symbol: string;
  entryDate: string;
  entryPrice: number;
  exitDate: string;
  exitPrice: number;
  quantity: number;
  brokerage: BrokerageBreakdown;
  profitLoss: number;
}

interface TradeStats {
  totalTrades: number;
  buyTrades: number;
  sellTrades: number;
  brokerageBreakdown: BrokerageBreakdown;
  trades: TradeRecord[];
}

// Smart trade counting logic using Zerodha brokerage for Equity Delivery
function calculateSmartTrades(
  recommendations: DailyRecommendation[],
  mode: InvestmentMode,
  startingAmount: number,
  nifty50Prices?: Record<string, number>,
  allBacktestData?: Record<string, Record<string, number>>
): {
  portfolioData: Array<{ date: string; rawDate: string; value: number; niftyValue: number; return: number; cumulative: number }>;
  stats: TradeStats;
  openPositions: Record<string, { entryDate: string; entryPrice: number; decision: Decision }>;
} {
  const hasRealNifty = nifty50Prices && Object.keys(nifty50Prices).length > 0;
  const sortedRecs = [...recommendations].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

  // Precompute real Nifty start price for comparison
  const sortedNiftyDates = hasRealNifty ? Object.keys(nifty50Prices).sort() : [];
  const niftyStartPrice = hasRealNifty && sortedNiftyDates.length > 0
    ? nifty50Prices[sortedNiftyDates[0]]
    : null;

  // Track open positions per stock
  const openPositions: Record<string, { entryDate: string; entryPrice: number; decision: Decision }> = {};
  const completedTrades: TradeRecord[] = [];
  let buyTrades = 0;
  let sellTrades = 0;

  const getStocksToTrack = (rec: typeof recommendations[0]) => {
    if (mode === 'topPicks') {
      return rec.top_picks.map(p => p.symbol);
    }
    return Object.keys(rec.analysis);
  };

  const stockCount = mode === 'topPicks' ? 3 : 50;
  const investmentPerStock = startingAmount / stockCount;

  let portfolioValue = startingAmount;
  let niftyValue = startingAmount;

  const portfolioData = sortedRecs.map((rec) => {
    const stocks = getStocksToTrack(rec);
    let dayReturn = 0;
    let stocksTracked = 0;

    stocks.forEach(symbol => {
      const analysis = rec.analysis[symbol];
      if (!analysis || !analysis.decision) return;

      const decision = analysis.decision;
      const prevPosition = openPositions[symbol];

      const currentPrice = 1000; // Nominal price for position sizing
      const quantity = Math.floor(investmentPerStock / currentPrice);

      if (decision === 'BUY') {
        if (!prevPosition) {
          openPositions[symbol] = { entryDate: rec.date, entryPrice: currentPrice, decision };
          buyTrades++;
        } else if (prevPosition.decision === 'SELL') {
          buyTrades++;
          openPositions[symbol] = { entryDate: rec.date, entryPrice: currentPrice, decision };
        } else {
          openPositions[symbol].decision = decision;
        }
        // Use real backtest return if available, otherwise 0 (neutral)
        const realBuyReturn = allBacktestData?.[rec.date]?.[symbol];
        dayReturn += realBuyReturn !== undefined ? realBuyReturn : 0;
        stocksTracked++;
      } else if (decision === 'HOLD') {
        if (prevPosition) {
          openPositions[symbol].decision = decision;
        }
        // Use real backtest return if available, otherwise 0 (neutral)
        const realHoldReturn = allBacktestData?.[rec.date]?.[symbol];
        dayReturn += realHoldReturn !== undefined ? realHoldReturn : 0;
        stocksTracked++;
      } else if (decision === 'SELL') {
        if (prevPosition && (prevPosition.decision === 'BUY' || prevPosition.decision === 'HOLD')) {
          sellTrades++;

          // Use real backtest return for exit price if available, otherwise break-even
          const realSellReturn = allBacktestData?.[rec.date]?.[symbol];
          const exitPrice = realSellReturn !== undefined
            ? currentPrice * (1 + realSellReturn / 100)
            : currentPrice;
          const brokerage = calculateBrokerage({
            buyPrice: prevPosition.entryPrice,
            sellPrice: exitPrice,
            quantity,
            tradeType: 'delivery',
          });

          const grossProfit = (exitPrice - prevPosition.entryPrice) * quantity;
          const profitLoss = grossProfit - brokerage.totalCharges;

          completedTrades.push({
            symbol,
            entryDate: prevPosition.entryDate,
            entryPrice: prevPosition.entryPrice,
            exitDate: rec.date,
            exitPrice,
            quantity,
            brokerage,
            profitLoss,
          });

          delete openPositions[symbol];
        }
        // SELL exits position to cash — don't count in stocksTracked
        // since no capital is deployed and return is 0
      }
    });

    const avgDayReturn = stocksTracked > 0 ? dayReturn / stocksTracked : 0;
    portfolioValue = portfolioValue * (1 + avgDayReturn / 100);

    // Use real Nifty50 prices if available, otherwise use mock history
    if (hasRealNifty && niftyStartPrice) {
      const closestDate = sortedNiftyDates.find(d => d >= rec.date) || sortedNiftyDates[sortedNiftyDates.length - 1];
      if (closestDate && nifty50Prices[closestDate]) {
        niftyValue = startingAmount * (nifty50Prices[closestDate] / niftyStartPrice);
      }
    }

    return {
      date: new Date(rec.date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' }),
      rawDate: rec.date,
      value: Math.round(portfolioValue),
      niftyValue: Math.round(niftyValue),
      return: avgDayReturn,
      cumulative: ((portfolioValue - startingAmount) / startingAmount) * 100,
    };
  });

  const totalBrokerage = completedTrades.reduce<BrokerageBreakdown>(
    (acc, trade) => ({
      brokerage: acc.brokerage + trade.brokerage.brokerage,
      stt: acc.stt + trade.brokerage.stt,
      exchangeCharges: acc.exchangeCharges + trade.brokerage.exchangeCharges,
      sebiCharges: acc.sebiCharges + trade.brokerage.sebiCharges,
      gst: acc.gst + trade.brokerage.gst,
      stampDuty: acc.stampDuty + trade.brokerage.stampDuty,
      totalCharges: acc.totalCharges + trade.brokerage.totalCharges,
      netProfit: acc.netProfit + trade.brokerage.netProfit,
      turnover: acc.turnover + trade.brokerage.turnover,
    }),
    { brokerage: 0, stt: 0, exchangeCharges: 0, sebiCharges: 0, gst: 0, stampDuty: 0, totalCharges: 0, netProfit: 0, turnover: 0 }
  );

  return {
    portfolioData,
    stats: {
      totalTrades: buyTrades + sellTrades,
      buyTrades,
      sellTrades,
      brokerageBreakdown: totalBrokerage,
      trades: completedTrades,
    },
    openPositions,
  };
}

// Helper for consistent positive/negative color classes
function getValueColorClass(value: number): string {
  return value >= 0
    ? 'text-green-600 dark:text-green-400'
    : 'text-red-600 dark:text-red-400';
}

export default function PortfolioSimulator({
  className = '',
  recommendations = [],
  nifty50Prices,
  allBacktestData,
}: PortfolioSimulatorProps) {
  const [startingAmount, setStartingAmount] = useState(100000);
  const [showBreakdown, setShowBreakdown] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showBrokerageDetails, setShowBrokerageDetails] = useState(false);
  const [showTradeWaterfall, setShowTradeWaterfall] = useState(false);
  const [investmentMode, setInvestmentMode] = useState<InvestmentMode>('all50');
  const [includeBrokerage, setIncludeBrokerage] = useState(true);

  // Modal state - single state for all modals instead of 7 separate booleans
  type ModalType = 'totalTrades' | 'buyTrades' | 'sellTrades' | 'portfolioValue' | 'profitLoss' | 'comparison' | null;
  const [activeModal, setActiveModal] = useState<ModalType>(null);

  const { portfolioData, stats, openPositions } = useMemo(() => {
    return calculateSmartTrades(
      recommendations,
      investmentMode,
      startingAmount,
      nifty50Prices,
      allBacktestData
    );
  }, [recommendations, investmentMode, startingAmount, nifty50Prices, allBacktestData]);

  const lastDataPoint = portfolioData[portfolioData.length - 1];
  const currentValue = lastDataPoint?.value ?? startingAmount;
  const niftyValue = lastDataPoint?.niftyValue ?? startingAmount;

  const totalCharges = includeBrokerage ? stats.brokerageBreakdown.totalCharges : 0;
  const finalValue = currentValue - totalCharges;
  const totalReturn = ((finalValue - startingAmount) / startingAmount) * 100;
  const profitLoss = finalValue - startingAmount;
  const isPositive = profitLoss >= 0;

  const niftyReturn = ((niftyValue - startingAmount) / startingAmount) * 100;
  const outperformance = totalReturn - niftyReturn;

  // Calculate Y-axis domain with padding
  const yAxisDomain = useMemo(() => {
    if (portfolioData.length === 0) return [0, startingAmount * 1.2];

    const allValues = portfolioData.flatMap(d => [d.value, d.niftyValue]);
    const minValue = Math.min(...allValues);
    const maxValue = Math.max(...allValues);
    const padding = (maxValue - minValue) * 0.1;

    return [Math.floor((minValue - padding) / 1000) * 1000, Math.ceil((maxValue + padding) / 1000) * 1000];
  }, [portfolioData, startingAmount]);

  const handleAmountChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseInt(e.target.value.replace(/,/g, ''), 10);
    if (!isNaN(value) && value >= 0) {
      setStartingAmount(value);
    }
  };

  const openPositionsCount = Object.keys(openPositions).length;

  return (
    <div className={`card p-4 ${className}`}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Calculator className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">Portfolio Simulator</h2>
        </div>
        <button
          onClick={() => setShowSettings(!showSettings)}
          className={`p-1.5 rounded-lg transition-colors ${
            showSettings
              ? 'bg-nifty-100 text-nifty-600 dark:bg-nifty-900/30 dark:text-nifty-400'
              : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
          }`}
          title="Settings"
        >
          <Settings2 className="w-4 h-4" />
        </button>
      </div>

      {/* Settings Panel */}
      {showSettings && (
        <div className="mb-4 p-3 bg-gray-50 dark:bg-slate-700/50 rounded-lg space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">
              Investment Strategy
            </label>
            <div className="flex gap-2">
              <button
                onClick={() => setInvestmentMode('all50')}
                className={`flex-1 px-3 py-2 text-xs font-medium rounded-lg transition-all ${
                  investmentMode === 'all50'
                    ? 'bg-nifty-600 text-white'
                    : 'bg-white dark:bg-slate-600 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-slate-500 hover:bg-gray-50 dark:hover:bg-slate-500'
                }`}
              >
                All 50 Stocks
              </button>
              <button
                onClick={() => setInvestmentMode('topPicks')}
                className={`flex-1 px-3 py-2 text-xs font-medium rounded-lg transition-all ${
                  investmentMode === 'topPicks'
                    ? 'bg-nifty-600 text-white'
                    : 'bg-white dark:bg-slate-600 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-slate-500 hover:bg-gray-50 dark:hover:bg-slate-500'
                }`}
              >
                Top Picks Only
              </button>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={includeBrokerage}
                onChange={(e) => setIncludeBrokerage(e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 text-nifty-600 focus:ring-nifty-500"
              />
              <span className="text-xs text-gray-600 dark:text-gray-400">Include Zerodha Equity Delivery Charges</span>
            </label>
          </div>
        </div>
      )}

      {/* Input Section */}
      <div className="mb-4">
        <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
          Starting Investment
        </label>
        <div className="relative">
          <IndianRupee className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={startingAmount.toLocaleString('en-IN')}
            onChange={handleAmountChange}
            className="w-full pl-9 pr-4 py-2 rounded-lg border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-nifty-500 focus:border-transparent"
          />
        </div>
        <div className="flex gap-2 mt-2">
          {[10000, 50000, 100000, 500000].map(amount => (
            <button
              key={amount}
              onClick={() => setStartingAmount(amount)}
              className={`px-2 py-1 text-xs rounded ${
                startingAmount === amount
                  ? 'bg-nifty-600 text-white'
                  : 'bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-slate-600'
              }`}
            >
              {formatINR(amount, 0)}
            </button>
          ))}
        </div>
      </div>

      {/* Results Section */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50 relative">
          <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 mb-1">
            <span>Final Portfolio Value</span>
            <InfoButton onClick={() => setActiveModal('portfolioValue')} />
          </div>
          <div className={`text-xl font-bold ${getValueColorClass(profitLoss)}`}>
            {formatINR(finalValue, 0)}
          </div>
        </div>
        <div className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50">
          <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 mb-1">
            <span>Net Profit/Loss</span>
            <InfoButton onClick={() => setActiveModal('profitLoss')} />
          </div>
          <div className={`text-xl font-bold ${getValueColorClass(profitLoss)}`}>
            {isPositive ? '+' : ''}{formatINR(profitLoss, 0)}
            <span className="text-sm ml-1">({isPositive ? '+' : ''}{totalReturn.toFixed(1)}%)</span>
          </div>
        </div>
      </div>

      {/* Trade Stats with Info Buttons */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        <div
          className="p-2 rounded-lg bg-blue-50 dark:bg-blue-900/20 text-center cursor-pointer hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors"
          onClick={() => setActiveModal('totalTrades')}
        >
          <div className="text-lg font-bold text-blue-600 dark:text-blue-400">{stats.totalTrades}</div>
          <div className="text-[10px] text-blue-600/70 dark:text-blue-400/70 flex items-center justify-center gap-0.5">
            Total Trades <HelpCircle className="w-2.5 h-2.5" />
          </div>
        </div>
        <div
          className="p-2 rounded-lg bg-green-50 dark:bg-green-900/20 text-center cursor-pointer hover:bg-green-100 dark:hover:bg-green-900/30 transition-colors"
          onClick={() => setActiveModal('buyTrades')}
        >
          <div className="text-lg font-bold text-green-600 dark:text-green-400">{stats.buyTrades}</div>
          <div className="text-[10px] text-green-600/70 dark:text-green-400/70 flex items-center justify-center gap-0.5">
            Buy Trades <HelpCircle className="w-2.5 h-2.5" />
          </div>
        </div>
        <div
          className="p-2 rounded-lg bg-red-50 dark:bg-red-900/20 text-center cursor-pointer hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
          onClick={() => setActiveModal('sellTrades')}
        >
          <div className="text-lg font-bold text-red-600 dark:text-red-400">{stats.sellTrades}</div>
          <div className="text-[10px] text-red-600/70 dark:text-red-400/70 flex items-center justify-center gap-0.5">
            Sell Trades <HelpCircle className="w-2.5 h-2.5" />
          </div>
        </div>
        <div
          className="p-2 rounded-lg bg-amber-50 dark:bg-amber-900/20 text-center cursor-pointer hover:bg-amber-100 dark:hover:bg-amber-900/30 transition-colors"
          onClick={() => setShowBrokerageDetails(!showBrokerageDetails)}
          title="Click for detailed breakdown"
        >
          <div className="text-lg font-bold text-amber-600 dark:text-amber-400">{formatINR(totalCharges, 0)}</div>
          <div className="text-[10px] text-amber-600/70 dark:text-amber-400/70 flex items-center justify-center gap-0.5">
            Total Charges <Info className="w-2.5 h-2.5" />
          </div>
        </div>
      </div>

      {/* Open Positions Badge */}
      {openPositionsCount > 0 && (
        <div className="mb-4 p-2 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800/30">
          <div className="flex items-center justify-between text-xs">
            <span className="text-purple-700 dark:text-purple-300 flex items-center gap-1">
              <Wallet className="w-3.5 h-3.5" />
              Open Positions (not yet sold)
            </span>
            <span className="font-bold text-purple-600 dark:text-purple-400">{openPositionsCount} stocks</span>
          </div>
        </div>
      )}

      {/* Brokerage Breakdown */}
      {showBrokerageDetails && includeBrokerage && (
        <div className="mb-4 p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800/30">
          <div className="flex items-center gap-2 mb-2">
            <Receipt className="w-4 h-4 text-amber-600 dark:text-amber-400" />
            <span className="text-xs font-semibold text-amber-800 dark:text-amber-300">Zerodha Equity Delivery Charges</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Brokerage:</span>
              <span className="font-medium text-gray-800 dark:text-gray-200">{formatINR(stats.brokerageBreakdown.brokerage)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">STT:</span>
              <span className="font-medium text-gray-800 dark:text-gray-200">{formatINR(stats.brokerageBreakdown.stt)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Exchange Charges:</span>
              <span className="font-medium text-gray-800 dark:text-gray-200">{formatINR(stats.brokerageBreakdown.exchangeCharges)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">SEBI Charges:</span>
              <span className="font-medium text-gray-800 dark:text-gray-200">{formatINR(stats.brokerageBreakdown.sebiCharges)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">GST (18%):</span>
              <span className="font-medium text-gray-800 dark:text-gray-200">{formatINR(stats.brokerageBreakdown.gst)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Stamp Duty:</span>
              <span className="font-medium text-gray-800 dark:text-gray-200">{formatINR(stats.brokerageBreakdown.stampDuty)}</span>
            </div>
          </div>
          <div className="mt-2 pt-2 border-t border-amber-200 dark:border-amber-700 flex justify-between">
            <span className="text-xs font-semibold text-amber-800 dark:text-amber-300">Total Turnover:</span>
            <span className="text-xs font-bold text-amber-800 dark:text-amber-300">{formatINR(stats.brokerageBreakdown.turnover, 0)}</span>
          </div>
        </div>
      )}

      {/* Comparison with Nifty */}
      <div
        className="mb-4 p-3 rounded-lg bg-gradient-to-r from-nifty-50 to-blue-50 dark:from-nifty-900/20 dark:to-blue-900/20 border border-nifty-100 dark:border-nifty-800/30 cursor-pointer hover:shadow-md transition-shadow"
        onClick={() => setActiveModal('comparison')}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-nifty-600 dark:text-nifty-400" />
            <span className="text-xs font-medium text-gray-700 dark:text-gray-300">vs Nifty 50 Index</span>
          </div>
          <HelpCircle className="w-3.5 h-3.5 text-gray-400" />
        </div>
        <div className="grid grid-cols-3 gap-3 text-center">
          <div>
            <div className={`text-sm font-bold ${getValueColorClass(totalReturn)}`}>
              {totalReturn >= 0 ? '+' : ''}{totalReturn.toFixed(1)}%
            </div>
            <div className="text-[10px] text-gray-500">AI Strategy</div>
          </div>
          <div>
            <div className={`text-sm font-bold ${getValueColorClass(niftyReturn)}`}>
              {niftyReturn >= 0 ? '+' : ''}{niftyReturn.toFixed(1)}%
            </div>
            <div className="text-[10px] text-gray-500">Nifty 50</div>
          </div>
          <div>
            <div className={`text-sm font-bold ${outperformance >= 0 ? 'text-nifty-600 dark:text-nifty-400' : 'text-red-600 dark:text-red-400'}`}>
              {outperformance >= 0 ? '+' : ''}{outperformance.toFixed(1)}%
            </div>
            <div className="text-[10px] text-gray-500">Outperformance</div>
          </div>
        </div>
      </div>

      {/* Chart with Nifty Comparison - Fixed Y-axis */}
      {portfolioData.length > 0 && (
        <div className="h-48 mb-4">
          <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
            <LineChart data={portfolioData} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-slate-700" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10 }}
                className="text-gray-500 dark:text-gray-400"
              />
              <YAxis
                tick={{ fontSize: 10 }}
                tickFormatter={(v) => formatINR(v, 0).replace('₹', '')}
                className="text-gray-500 dark:text-gray-400"
                width={60}
                domain={yAxisDomain}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--tooltip-bg, #fff)',
                  border: '1px solid var(--tooltip-border, #e5e7eb)',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
                formatter={(value, name) => [
                  formatINR(Number(value) || 0, 0),
                  name === 'value' ? 'AI Strategy' : 'Nifty 50'
                ]}
              />
              <Legend
                wrapperStyle={{ fontSize: '10px' }}
                formatter={(value) => value === 'value' ? 'AI Strategy' : 'Nifty 50'}
              />
              <ReferenceLine
                y={startingAmount}
                stroke="#94a3b8"
                strokeDasharray="5 5"
                label={{ value: 'Start', fontSize: 10, fill: '#94a3b8' }}
              />
              <Line
                type="monotone"
                dataKey="value"
                name="value"
                stroke={isPositive ? '#22c55e' : '#ef4444'}
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="niftyValue"
                name="niftyValue"
                stroke="#6366f1"
                strokeWidth={2}
                strokeDasharray="4 4"
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Trade Waterfall Toggle */}
      <button
        onClick={() => setShowTradeWaterfall(!showTradeWaterfall)}
        className="flex items-center justify-between w-full px-3 py-2 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-slate-700/50 rounded-lg transition-colors mb-2"
      >
        <span className="flex items-center gap-2">
          <ArrowRightLeft className="w-4 h-4" />
          Trade Timeline ({stats.trades.length} completed trades)
        </span>
        {showTradeWaterfall ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>

      {/* Trade Waterfall Chart */}
      {showTradeWaterfall && stats.trades.length > 0 && (
        <div className="mb-4 p-3 bg-gray-50 dark:bg-slate-700/30 rounded-lg">
          <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">
            Each bar represents a trade from buy to sell. Green = Profit, Red = Loss.
          </div>
          <div className="h-64 overflow-y-auto">
            <div style={{ height: Math.max(200, stats.trades.length * 28) }}>
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                <BarChart
                  data={stats.trades.map((t, i) => ({
                    ...t,
                    idx: i,
                    displayName: `${t.symbol}`,
                    duration: `${new Date(t.entryDate).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })} → ${new Date(t.exitDate).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })}`,
                  }))}
                  layout="vertical"
                  margin={{ top: 5, right: 60, bottom: 5, left: 70 }}
                >
                  <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-slate-700" horizontal={false} />
                  <XAxis
                    type="number"
                    tick={{ fontSize: 9 }}
                    tickFormatter={(v) => formatINR(v, 0)}
                    domain={['dataMin', 'dataMax']}
                  />
                  <YAxis
                    type="category"
                    dataKey="displayName"
                    tick={{ fontSize: 10 }}
                    width={65}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--tooltip-bg, #fff)',
                      border: '1px solid var(--tooltip-border, #e5e7eb)',
                      borderRadius: '8px',
                      fontSize: '11px',
                    }}
                    formatter={(value) => [formatINR(Number(value) || 0, 2), 'P/L']}
                    labelFormatter={(_, payload) => {
                      if (payload && payload[0]) {
                        const d = payload[0].payload;
                        return `${d.symbol}: ${d.duration}`;
                      }
                      return '';
                    }}
                  />
                  <Bar dataKey="profitLoss" radius={[0, 4, 4, 0]}>
                    {stats.trades.map((trade, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={trade.profitLoss >= 0 ? '#22c55e' : '#ef4444'}
                      />
                    ))}
                    <LabelList
                      dataKey="profitLoss"
                      position="right"
                      formatter={(v) => formatINR(Number(v) || 0, 0)}
                      style={{ fontSize: 9, fill: '#6b7280' }}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Daily Breakdown (Collapsible) */}
      <button
        onClick={() => setShowBreakdown(!showBreakdown)}
        className="flex items-center justify-between w-full px-3 py-2 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-slate-700/50 rounded-lg transition-colors"
      >
        <span>Daily Breakdown</span>
        {showBreakdown ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>

      {showBreakdown && (
        <div className="mt-2 border border-gray-200 dark:border-slate-600 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-slate-700">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400">Date</th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 dark:text-gray-400">Return</th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 dark:text-gray-400">AI Value</th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 dark:text-gray-400">Nifty</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-slate-700">
              {portfolioData.map((day, idx) => (
                <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-slate-700/50">
                  <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{day.date}</td>
                  <td className={`px-3 py-2 text-right font-medium ${getValueColorClass(day.return)}`}>
                    {day.return >= 0 ? '+' : ''}{day.return.toFixed(1)}%
                  </td>
                  <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">
                    {formatINR(day.value, 0)}
                  </td>
                  <td className="px-3 py-2 text-right text-indigo-600 dark:text-indigo-400">
                    {formatINR(day.niftyValue, 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-3 text-center">
        Simulated using Zerodha Equity Delivery rates (0% brokerage, STT 0.1%, Exchange 0.00345%, SEBI 0.0001%, Stamp 0.015%).
        {investmentMode === 'topPicks' ? ' Investing in Top Picks only.' : ' Investing in all 50 stocks.'}
        {includeBrokerage ? ` Total Charges: ${formatINR(totalCharges, 0)}` : ''}
      </p>

      {/* Info Modals */}
      <InfoModal
        isOpen={activeModal === 'totalTrades'}
        onClose={() => setActiveModal(null)}
        title="Total Trades"
        icon={<ArrowRightLeft className="w-5 h-5 text-blue-600 dark:text-blue-400" />}
      >
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
          <p><strong>Total Trades</strong> represents the sum of all buy and sell transactions executed during the simulation period.</p>
          <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
            <div className="font-semibold text-blue-800 dark:text-blue-200 mb-1">Calculation:</div>
            <code className="text-xs">Total Trades = Buy Trades + Sell Trades</code>
            <div className="mt-2 text-xs">= {stats.buyTrades} + {stats.sellTrades} = <strong>{stats.totalTrades}</strong></div>
          </div>
          <p className="text-xs text-gray-500">Note: A complete round-trip trade (buy then sell) counts as 2 trades.</p>
        </div>
      </InfoModal>

      <InfoModal
        isOpen={activeModal === 'buyTrades'}
        onClose={() => setActiveModal(null)}
        title="Buy Trades"
        icon={<TrendingUp className="w-5 h-5 text-green-600 dark:text-green-400" />}
      >
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
          <p><strong>Buy Trades</strong> counts when a new position is opened based on AI's BUY recommendation.</p>
          <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
            <div className="font-semibold text-green-800 dark:text-green-200 mb-2">When is a Buy Trade counted?</div>
            <ul className="text-xs space-y-1 list-disc list-inside">
              <li>When AI recommends BUY and no position exists</li>
              <li>When AI recommends BUY after a previous SELL</li>
            </ul>
          </div>
          <p className="text-xs text-gray-500">Note: If AI recommends BUY while already holding (from previous BUY or HOLD), no new buy trade is counted - the position is simply carried forward.</p>
        </div>
      </InfoModal>

      <InfoModal
        isOpen={activeModal === 'sellTrades'}
        onClose={() => setActiveModal(null)}
        title="Sell Trades"
        icon={<TrendingDown className="w-5 h-5 text-red-600 dark:text-red-400" />}
      >
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
          <p><strong>Sell Trades</strong> counts when a position is closed based on AI's SELL recommendation.</p>
          <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
            <div className="font-semibold text-red-800 dark:text-red-200 mb-2">When is a Sell Trade counted?</div>
            <ul className="text-xs space-y-1 list-disc list-inside">
              <li>When AI recommends SELL while holding a position</li>
              <li>Position must have been opened via BUY or carried via HOLD</li>
            </ul>
          </div>
          <p className="text-xs text-gray-500">Note: Brokerage is calculated when a sell trade completes a round-trip transaction.</p>
        </div>
      </InfoModal>

      <InfoModal
        isOpen={activeModal === 'portfolioValue'}
        onClose={() => setActiveModal(null)}
        title="Final Portfolio Value"
        icon={<PiggyBank className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />}
      >
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
          <p><strong>Final Portfolio Value</strong> is the total worth of your investments at the end of the simulation period.</p>
          <div className="p-3 bg-nifty-50 dark:bg-nifty-900/20 rounded-lg">
            <div className="font-semibold text-nifty-800 dark:text-nifty-200 mb-1">Calculation:</div>
            <code className="text-xs">Final Value = Portfolio Value - Total Charges</code>
            <div className="mt-2 text-xs">
              = {formatINR(currentValue, 0)} - {formatINR(totalCharges, 0)} = <strong>{formatINR(finalValue, 0)}</strong>
            </div>
          </div>
          <p className="text-xs text-gray-500">This includes all realized gains/losses from completed trades and deducts Zerodha brokerage charges.</p>
        </div>
      </InfoModal>

      <InfoModal
        isOpen={activeModal === 'profitLoss'}
        onClose={() => setActiveModal(null)}
        title="Net Profit/Loss"
        icon={<Calculator className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />}
      >
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
          <p><strong>Net Profit/Loss</strong> shows your actual earnings or losses after all charges.</p>
          <div className="p-3 bg-gray-100 dark:bg-slate-700 rounded-lg">
            <div className="font-semibold mb-1">Calculation:</div>
            <code className="text-xs">Net P/L = Final Value - Starting Investment</code>
            <div className="mt-2 text-xs">
              = {formatINR(finalValue, 0)} - {formatINR(startingAmount, 0)} = <strong className={profitLoss >= 0 ? 'text-green-600' : 'text-red-600'}>{formatINR(profitLoss, 0)}</strong>
            </div>
            <div className="mt-2 text-xs">
              Return = ({formatINR(profitLoss, 0)} / {formatINR(startingAmount, 0)}) × 100 = <strong>{totalReturn.toFixed(2)}%</strong>
            </div>
          </div>
        </div>
      </InfoModal>

      <InfoModal
        isOpen={activeModal === 'comparison'}
        onClose={() => setActiveModal(null)}
        title="vs Nifty 50 Index"
        icon={<BarChart3 className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />}
      >
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
          <p>This compares the AI strategy's performance against simply investing in the Nifty 50 index.</p>
          <div className="space-y-2">
            <div className="p-2 bg-green-50 dark:bg-green-900/20 rounded-lg flex justify-between items-center">
              <span>AI Strategy Return:</span>
              <strong className={totalReturn >= 0 ? 'text-green-600' : 'text-red-600'}>{totalReturn.toFixed(2)}%</strong>
            </div>
            <div className="p-2 bg-indigo-50 dark:bg-indigo-900/20 rounded-lg flex justify-between items-center">
              <span>Nifty 50 Return:</span>
              <strong className={niftyReturn >= 0 ? 'text-green-600' : 'text-red-600'}>{niftyReturn.toFixed(2)}%</strong>
            </div>
            <div className="p-2 bg-nifty-50 dark:bg-nifty-900/20 rounded-lg flex justify-between items-center">
              <span>Outperformance (Alpha):</span>
              <strong className={outperformance >= 0 ? 'text-nifty-600' : 'text-red-600'}>{outperformance.toFixed(2)}%</strong>
            </div>
          </div>
          <p className="text-xs text-gray-500">
            {outperformance >= 0
              ? `The AI strategy beat the Nifty 50 index by ${outperformance.toFixed(2)} percentage points.`
              : `The AI strategy underperformed the Nifty 50 index by ${Math.abs(outperformance).toFixed(2)} percentage points.`
            }
          </p>
        </div>
      </InfoModal>
    </div>
  );
}

// Export the type for use in other components
export { type InvestmentMode as PortfolioInvestmentMode };
