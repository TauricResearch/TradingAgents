import { TrendingUp, TrendingDown, Activity, Target } from 'lucide-react';
import { useState } from 'react';
import InfoModal, { InfoButton } from './InfoModal';
import type { RiskMetrics } from '../types';

export interface RiskMetricsCardProps {
  className?: string;
  metrics?: RiskMetrics;
}

type MetricModal = 'sharpe' | 'drawdown' | 'winloss' | 'winrate' | null;

const defaultMetrics: RiskMetrics = {
  sharpeRatio: 0, maxDrawdown: 0, winLossRatio: 0, winRate: 0, volatility: 0, totalTrades: 0,
};

export default function RiskMetricsCard({ className = '', metrics: propMetrics }: RiskMetricsCardProps) {
  const [activeModal, setActiveModal] = useState<MetricModal>(null);
  const metrics = propMetrics || defaultMetrics;

  // Color classes for metric values
  const COLOR_GOOD = 'text-green-600 dark:text-green-400';
  const COLOR_NEUTRAL = 'text-amber-600 dark:text-amber-400';
  const COLOR_BAD = 'text-red-600 dark:text-red-400';

  function getColor(metric: string, value: number): string {
    // Thresholds for each metric: [good, neutral] - values below neutral are bad
    const thresholds: Record<string, { good: number; neutral: number; inverted?: boolean }> = {
      sharpe: { good: 1, neutral: 0 },
      drawdown: { good: 5, neutral: 15, inverted: true }, // Lower is better
      winloss: { good: 1.5, neutral: 1 },
      winrate: { good: 70, neutral: 50 },
    };

    const config = thresholds[metric];
    if (!config) return 'text-gray-700 dark:text-gray-300';

    if (config.inverted) {
      // For drawdown: lower is better
      if (value <= config.good) return COLOR_GOOD;
      if (value <= config.neutral) return COLOR_NEUTRAL;
      return COLOR_BAD;
    }

    // For other metrics: higher is better
    if (value >= config.good) return COLOR_GOOD;
    if (value >= config.neutral) return COLOR_NEUTRAL;
    return COLOR_BAD;
  }

  const cards = [
    {
      id: 'sharpe',
      label: 'Sharpe Ratio',
      value: metrics.sharpeRatio.toFixed(2),
      icon: Activity,
      color: getColor('sharpe', metrics.sharpeRatio),
    },
    {
      id: 'drawdown',
      label: 'Max Drawdown',
      value: `${metrics.maxDrawdown.toFixed(1)}%`,
      icon: TrendingDown,
      color: getColor('drawdown', metrics.maxDrawdown),
    },
    {
      id: 'winloss',
      label: 'Win/Loss Ratio',
      value: metrics.winLossRatio.toFixed(2),
      icon: TrendingUp,
      color: getColor('winloss', metrics.winLossRatio),
    },
    {
      id: 'winrate',
      label: 'Win Rate',
      value: `${metrics.winRate}%`,
      icon: Target,
      color: getColor('winrate', metrics.winRate),
    },
  ];

  return (
    <>
      <div className={`grid grid-cols-2 sm:grid-cols-4 gap-3 ${className}`}>
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.id}
              className="relative p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50 text-center group"
            >
              <div className="flex items-center justify-center gap-1 mb-1">
                <Icon className={`w-4 h-4 ${card.color}`} />
                <span className={`text-xl font-bold ${card.color}`}>{card.value}</span>
              </div>
              <div className="flex items-center justify-center gap-1">
                <span className="text-xs text-gray-500 dark:text-gray-400">{card.label}</span>
                <InfoButton onClick={() => setActiveModal(card.id as MetricModal)} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Sharpe Ratio Modal */}
      <InfoModal
        isOpen={activeModal === 'sharpe'}
        onClose={() => setActiveModal(null)}
        title="Sharpe Ratio"
        icon={<Activity className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />}
      >
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-400">
          <p>
            The <strong className="text-gray-900 dark:text-gray-100">Sharpe Ratio</strong> measures risk-adjusted returns
            by comparing the excess return of an investment to its standard deviation (volatility).
          </p>

          {/* Current Value Display */}
          <div className={`p-3 rounded-lg ${getColor('sharpe', metrics.sharpeRatio).replace('text-', 'bg-').replace('-600', '-50').replace('-400', '-900/20')}`}>
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Current Sharpe Ratio</div>
            <div className={`text-2xl font-bold ${getColor('sharpe', metrics.sharpeRatio)}`}>{metrics.sharpeRatio.toFixed(2)}</div>
          </div>

          {/* Formula and Calculation */}
          <div className="bg-gray-50 dark:bg-slate-700 p-3 rounded-lg space-y-3">
            <div>
              <p className="font-medium text-gray-900 dark:text-gray-100 mb-2">Formula:</p>
              <div className="font-mono text-sm bg-white dark:bg-slate-800 p-2 rounded border border-gray-200 dark:border-slate-600">
                Sharpe Ratio = (R̄ − Rf) / σ
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Where R̄ = Mean Return, Rf = Risk-Free Rate, σ = Standard Deviation
              </p>
            </div>

            {metrics.meanReturn !== undefined && (
              <div>
                <p className="font-medium text-gray-900 dark:text-gray-100 mb-2">Your Values:</p>
                <div className="text-xs space-y-1 mb-3">
                  <p>• Mean Daily Return (R̄) = <span className="text-nifty-600 dark:text-nifty-400 font-medium">{metrics.meanReturn}%</span></p>
                  <p>• Risk-Free Rate (Rf) = <span className="text-gray-700 dark:text-gray-300 font-medium">{metrics.riskFreeRate}%</span> <span className="text-gray-400">(daily)</span></p>
                  <p>• Volatility (σ) = <span className="text-amber-600 dark:text-amber-400 font-medium">{metrics.volatility}%</span></p>
                </div>

                <p className="font-medium text-gray-900 dark:text-gray-100 mb-2">Calculation:</p>
                <div className="font-mono text-xs bg-white dark:bg-slate-800 p-2 rounded border border-gray-200 dark:border-slate-600 space-y-1">
                  <p>= ({metrics.meanReturn} − {metrics.riskFreeRate}) / {metrics.volatility}</p>
                  <p>= {(metrics.meanReturn - (metrics.riskFreeRate || 0)).toFixed(2)} / {metrics.volatility}</p>
                  <p className={`font-bold ${getColor('sharpe', metrics.sharpeRatio)}`}>= {metrics.sharpeRatio.toFixed(2)}</p>
                </div>
              </div>
            )}
          </div>

          <div>
            <p className="font-medium text-gray-900 dark:text-gray-100 mb-1">Interpretation:</p>
            <ul className="space-y-1 ml-4 list-disc">
              <li><span className="text-green-600 dark:text-green-400 font-medium">&gt; 1.0:</span> Good risk-adjusted returns</li>
              <li><span className="text-green-600 dark:text-green-400 font-medium">&gt; 2.0:</span> Excellent performance</li>
              <li><span className="text-amber-600 dark:text-amber-400 font-medium">0 - 1.0:</span> Acceptable but not optimal</li>
              <li><span className="text-red-600 dark:text-red-400 font-medium">&lt; 0:</span> Returns below risk-free rate</li>
            </ul>
          </div>
          <p className="text-xs italic">
            Higher Sharpe Ratio indicates better compensation for the risk taken.
          </p>
        </div>
      </InfoModal>

      {/* Max Drawdown Modal */}
      <InfoModal
        isOpen={activeModal === 'drawdown'}
        onClose={() => setActiveModal(null)}
        title="Maximum Drawdown"
        icon={<TrendingDown className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />}
      >
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-400">
          <p>
            <strong className="text-gray-900 dark:text-gray-100">Maximum Drawdown (MDD)</strong> measures the largest
            peak-to-trough decline in portfolio value before a new peak is reached.
          </p>

          {/* Current Value Display */}
          <div className={`p-3 rounded-lg ${getColor('drawdown', metrics.maxDrawdown).replace('text-', 'bg-').replace('-600', '-50').replace('-400', '-900/20')}`}>
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Maximum Drawdown</div>
            <div className={`text-2xl font-bold ${getColor('drawdown', metrics.maxDrawdown)}`}>{metrics.maxDrawdown.toFixed(1)}%</div>
          </div>

          {/* Formula and Calculation */}
          <div className="bg-gray-50 dark:bg-slate-700 p-3 rounded-lg space-y-3">
            <div>
              <p className="font-medium text-gray-900 dark:text-gray-100 mb-2">Formula:</p>
              <div className="font-mono text-sm bg-white dark:bg-slate-800 p-2 rounded border border-gray-200 dark:border-slate-600">
                MDD = (Vpeak − Vtrough) / Vpeak × 100%
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Where Vpeak = Peak Portfolio Value, Vtrough = Lowest Value after Peak
              </p>
            </div>

            {metrics.peakValue !== undefined && metrics.troughValue !== undefined && (
              <div>
                <p className="font-medium text-gray-900 dark:text-gray-100 mb-2">Your Values:</p>
                <div className="text-xs space-y-1 mb-3">
                  <p>• Peak Value (Vpeak) = <span className="text-green-600 dark:text-green-400 font-medium">₹{metrics.peakValue.toFixed(2)}</span> <span className="text-gray-400">(normalized from ₹100)</span></p>
                  <p>• Trough Value (Vtrough) = <span className="text-red-600 dark:text-red-400 font-medium">₹{metrics.troughValue.toFixed(2)}</span></p>
                </div>

                <p className="font-medium text-gray-900 dark:text-gray-100 mb-2">Calculation:</p>
                <div className="font-mono text-xs bg-white dark:bg-slate-800 p-2 rounded border border-gray-200 dark:border-slate-600 space-y-1">
                  <p>= ({metrics.peakValue.toFixed(2)} − {metrics.troughValue.toFixed(2)}) / {metrics.peakValue.toFixed(2)} × 100</p>
                  <p>= {(metrics.peakValue - metrics.troughValue).toFixed(2)} / {metrics.peakValue.toFixed(2)} × 100</p>
                  <p className={`font-bold ${getColor('drawdown', metrics.maxDrawdown)}`}>= {metrics.maxDrawdown.toFixed(1)}%</p>
                </div>
              </div>
            )}
          </div>

          <div>
            <p className="font-medium text-gray-900 dark:text-gray-100 mb-1">Interpretation:</p>
            <ul className="space-y-1 ml-4 list-disc">
              <li><span className="text-green-600 dark:text-green-400 font-medium">&lt; 5%:</span> Very low risk</li>
              <li><span className="text-amber-600 dark:text-amber-400 font-medium">5% - 15%:</span> Moderate risk</li>
              <li><span className="text-red-600 dark:text-red-400 font-medium">&gt; 15%:</span> Higher risk exposure</li>
            </ul>
          </div>
          <p className="text-xs italic">
            Lower drawdown indicates better capital preservation during market downturns.
          </p>
        </div>
      </InfoModal>

      {/* Win/Loss Ratio Modal */}
      <InfoModal
        isOpen={activeModal === 'winloss'}
        onClose={() => setActiveModal(null)}
        title="Win/Loss Ratio"
        icon={<TrendingUp className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />}
      >
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-400">
          <p>
            The <strong className="text-gray-900 dark:text-gray-100">Win/Loss Ratio</strong> compares the average
            profit from winning trades to the average loss from losing trades.
          </p>

          {/* Current Value Display */}
          <div className={`p-3 rounded-lg ${getColor('winloss', metrics.winLossRatio).replace('text-', 'bg-').replace('-600', '-50').replace('-400', '-900/20')}`}>
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Win/Loss Ratio</div>
            <div className={`text-2xl font-bold ${getColor('winloss', metrics.winLossRatio)}`}>{metrics.winLossRatio.toFixed(2)}</div>
          </div>

          {/* Formula and Calculation */}
          <div className="bg-gray-50 dark:bg-slate-700 p-3 rounded-lg space-y-3">
            <div>
              <p className="font-medium text-gray-900 dark:text-gray-100 mb-2">Formula:</p>
              <div className="font-mono text-sm bg-white dark:bg-slate-800 p-2 rounded border border-gray-200 dark:border-slate-600">
                Win/Loss Ratio = R̄w / |R̄l|
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Where R̄w = Avg Winning Return, R̄l = Avg Losing Return (absolute value)
              </p>
            </div>

            {metrics.winningTrades !== undefined && metrics.losingTrades !== undefined && (
              <div>
                <p className="font-medium text-gray-900 dark:text-gray-100 mb-2">Your Values:</p>
                <div className="text-xs space-y-1 mb-3">
                  <p>• Winning Predictions = <span className="text-green-600 dark:text-green-400 font-medium">{metrics.winningTrades}</span> days</p>
                  <p>• Losing Predictions = <span className="text-red-600 dark:text-red-400 font-medium">{metrics.losingTrades}</span> days</p>
                  <p>• Avg Winning Return (R̄w) = <span className="text-green-600 dark:text-green-400 font-medium">+{metrics.avgWinReturn?.toFixed(2)}%</span></p>
                  <p>• Avg Losing Return (R̄l) = <span className="text-red-600 dark:text-red-400 font-medium">−{metrics.avgLossReturn?.toFixed(2)}%</span></p>
                </div>

                <p className="font-medium text-gray-900 dark:text-gray-100 mb-2">Calculation:</p>
                <div className="font-mono text-xs bg-white dark:bg-slate-800 p-2 rounded border border-gray-200 dark:border-slate-600 space-y-1">
                  <p>= {metrics.avgWinReturn?.toFixed(2)} / {metrics.avgLossReturn?.toFixed(2)}</p>
                  <p className={`font-bold ${getColor('winloss', metrics.winLossRatio)}`}>= {metrics.winLossRatio.toFixed(2)}</p>
                </div>
              </div>
            )}
          </div>

          <div>
            <p className="font-medium text-gray-900 dark:text-gray-100 mb-1">Interpretation:</p>
            <ul className="space-y-1 ml-4 list-disc">
              <li><span className="text-green-600 dark:text-green-400 font-medium">&gt; 1.5:</span> Strong profit potential</li>
              <li><span className="text-amber-600 dark:text-amber-400 font-medium">1.0 - 1.5:</span> Balanced trades</li>
              <li><span className="text-red-600 dark:text-red-400 font-medium">&lt; 1.0:</span> Losses exceed wins on average</li>
            </ul>
          </div>
          <p className="text-xs italic">
            A ratio above 1.0 means your winning trades are larger than your losing ones on average.
          </p>
        </div>
      </InfoModal>

      {/* Win Rate Modal */}
      <InfoModal
        isOpen={activeModal === 'winrate'}
        onClose={() => setActiveModal(null)}
        title="Win Rate"
        icon={<Target className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />}
      >
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-400">
          <p>
            <strong className="text-gray-900 dark:text-gray-100">Win Rate</strong> is the percentage of predictions
            that were correct (BUY/HOLD with positive return, or SELL with negative return).
          </p>

          {/* Current Value Display */}
          <div className={`p-3 rounded-lg ${getColor('winrate', metrics.winRate).replace('text-', 'bg-').replace('-600', '-50').replace('-400', '-900/20')}`}>
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Win Rate</div>
            <div className={`text-2xl font-bold ${getColor('winrate', metrics.winRate)}`}>{metrics.winRate}%</div>
          </div>

          {/* Formula and Calculation */}
          <div className="bg-gray-50 dark:bg-slate-700 p-3 rounded-lg space-y-3">
            <div>
              <p className="font-medium text-gray-900 dark:text-gray-100 mb-2">Formula:</p>
              <div className="font-mono text-sm bg-white dark:bg-slate-800 p-2 rounded border border-gray-200 dark:border-slate-600">
                Win Rate = (Ncorrect / Ntotal) × 100%
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Where Ncorrect = Correct Predictions, Ntotal = Total Predictions
              </p>
            </div>

            {metrics.winningTrades !== undefined && (
              <div>
                <p className="font-medium text-gray-900 dark:text-gray-100 mb-2">Your Values:</p>
                <div className="text-xs space-y-1 mb-3">
                  <p>• Correct Predictions (Ncorrect) = <span className="text-green-600 dark:text-green-400 font-medium">{metrics.winningTrades}</span></p>
                  <p>• Total Predictions (Ntotal) = <span className="text-gray-700 dark:text-gray-300 font-medium">{metrics.totalTrades}</span></p>
                </div>

                <p className="font-medium text-gray-900 dark:text-gray-100 mb-2">Calculation:</p>
                <div className="font-mono text-xs bg-white dark:bg-slate-800 p-2 rounded border border-gray-200 dark:border-slate-600 space-y-1">
                  <p>= ({metrics.winningTrades} / {metrics.totalTrades}) × 100</p>
                  <p>= {(metrics.winningTrades / metrics.totalTrades).toFixed(4)} × 100</p>
                  <p className={`font-bold ${getColor('winrate', metrics.winRate)}`}>= {metrics.winRate}%</p>
                </div>
              </div>
            )}
          </div>

          <div>
            <p className="font-medium text-gray-900 dark:text-gray-100 mb-1">Interpretation:</p>
            <ul className="space-y-1 ml-4 list-disc">
              <li><span className="text-green-600 dark:text-green-400 font-medium">&gt; 70%:</span> Excellent accuracy</li>
              <li><span className="text-amber-600 dark:text-amber-400 font-medium">50% - 70%:</span> Above average</li>
              <li><span className="text-red-600 dark:text-red-400 font-medium">&lt; 50%:</span> Below random chance</li>
            </ul>
          </div>
          <p className="text-xs italic">
            Note: Win rate alone doesn't determine profitability. A 40% win rate can still be profitable with a high Win/Loss ratio.
          </p>
        </div>
      </InfoModal>
    </>
  );
}
