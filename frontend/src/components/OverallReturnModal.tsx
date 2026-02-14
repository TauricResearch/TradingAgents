import { X, Activity } from 'lucide-react';
import { createPortal } from 'react-dom';
import CumulativeReturnChart from './CumulativeReturnChart';
import type { CumulativeReturnPoint } from '../types';

export interface OverallReturnBreakdown {
  dailyReturns: { date: string; return: number; multiplier: number; cumulative: number }[];
  finalMultiplier: number;
  finalReturn: number;
  formula: string;
}

interface OverallReturnModalProps {
  isOpen: boolean;
  onClose: () => void;
  breakdown?: OverallReturnBreakdown;  // Optional prop for real data
  cumulativeData?: CumulativeReturnPoint[];  // Optional prop for chart data
}

export default function OverallReturnModal({ isOpen, onClose, breakdown: propBreakdown, cumulativeData }: OverallReturnModalProps) {
  if (!isOpen) return null;

  const breakdown = propBreakdown || { dailyReturns: [], finalMultiplier: 1, finalReturn: 0, formula: '' };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-white dark:bg-slate-800 rounded-xl shadow-xl max-w-[95vw] sm:max-w-lg w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 flex items-center justify-between p-4 border-b border-gray-100 dark:border-slate-700 bg-white dark:bg-slate-800">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Overall Return Calculation
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors"
          >
            <X className="w-5 h-5 text-gray-500 dark:text-gray-400" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-5">
          {/* Final Result */}
          <div className="p-4 rounded-lg bg-gradient-to-br from-nifty-500 to-nifty-700 text-white">
            <div className="text-sm text-white/80 mb-1">Compound Return</div>
            <div className="text-3xl font-bold">
              {breakdown.finalReturn >= 0 ? '+' : ''}{breakdown.finalReturn.toFixed(1)}%
            </div>
            <div className="text-sm text-white/80 mt-1">
              Multiplier: {breakdown.finalMultiplier.toFixed(4)}x
            </div>
          </div>

          {/* Cumulative Return Chart */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">Portfolio Growth</h3>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50">
              <CumulativeReturnChart height={140} data={cumulativeData} />
            </div>
          </div>

          {/* Method Explanation */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">Why Compound Returns?</h3>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50 text-sm space-y-2">
              <p className="text-gray-700 dark:text-gray-300">
                In real trading, gains and losses <strong>compound</strong> over time. If you start with ₹10,000:
              </p>
              <ul className="text-xs text-gray-600 dark:text-gray-400 ml-4 space-y-1">
                <li>• Day 1: +2% → ₹10,000 × 1.02 = ₹10,200</li>
                <li>• Day 2: +1% → ₹10,200 × 1.01 = ₹10,302</li>
                <li>• Day 3: -1% → ₹10,302 × 0.99 = ₹10,199</li>
              </ul>
              <p className="text-gray-700 dark:text-gray-300 mt-2">
                Simple average would give (2+1-1)/3 = 0.67%, but actual return is +1.99%
              </p>
            </div>
          </div>

          {/* Formula */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">Formula</h3>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50">
              <div className="font-mono text-sm text-gray-700 dark:text-gray-300 mb-2">
                Overall = (1 + r₁) × (1 + r₂) × ... × (1 + rₙ) - 1
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Where r₁, r₂, ... rₙ are the daily weighted returns
              </p>
            </div>
          </div>

          {/* Daily Breakdown */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">Daily Breakdown</h3>

            {/* Desktop Table */}
            <div className="hidden sm:block border border-gray-200 dark:border-slate-600 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 dark:bg-slate-700">
                  <tr>
                    <th className="px-2 sm:px-3 py-1.5 sm:py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400">Date</th>
                    <th className="px-2 sm:px-3 py-1.5 sm:py-2 text-right text-xs font-medium text-gray-500 dark:text-gray-400">Return</th>
                    <th className="px-2 sm:px-3 py-1.5 sm:py-2 text-right text-xs font-medium text-gray-500 dark:text-gray-400">Multiplier</th>
                    <th className="px-2 sm:px-3 py-1.5 sm:py-2 text-right text-xs font-medium text-gray-500 dark:text-gray-400">Cumulative</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-slate-700">
                  {breakdown.dailyReturns.map((day: { date: string; return: number; multiplier: number; cumulative: number }) => (
                    <tr key={day.date} className="hover:bg-gray-50 dark:hover:bg-slate-700/50">
                      <td className="px-2 sm:px-3 py-1.5 sm:py-2 text-gray-700 dark:text-gray-300">
                        {new Date(day.date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })}
                      </td>
                      <td className={`px-2 sm:px-3 py-1.5 sm:py-2 text-right font-medium ${
                        day.return >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                      }`}>
                        {day.return >= 0 ? '+' : ''}{day.return.toFixed(1)}%
                      </td>
                      <td className="px-2 sm:px-3 py-1.5 sm:py-2 text-right text-gray-600 dark:text-gray-400 font-mono text-xs">
                        ×{day.multiplier.toFixed(4)}
                      </td>
                      <td className={`px-2 sm:px-3 py-1.5 sm:py-2 text-right font-medium ${
                        day.cumulative >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                      }`}>
                        {day.cumulative >= 0 ? '+' : ''}{day.cumulative.toFixed(1)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-nifty-50 dark:bg-nifty-900/20">
                  <tr>
                    <td className="px-2 sm:px-3 py-1.5 sm:py-2 font-semibold text-gray-900 dark:text-gray-100">Total</td>
                    <td className="px-2 sm:px-3 py-1.5 sm:py-2 text-right text-gray-500 dark:text-gray-400">-</td>
                    <td className="px-2 sm:px-3 py-1.5 sm:py-2 text-right font-mono text-xs font-semibold text-nifty-600 dark:text-nifty-400">
                      ×{breakdown.finalMultiplier.toFixed(4)}
                    </td>
                    <td className={`px-2 sm:px-3 py-1.5 sm:py-2 text-right font-bold ${
                      breakdown.finalReturn >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                    }`}>
                      {breakdown.finalReturn >= 0 ? '+' : ''}{breakdown.finalReturn.toFixed(1)}%
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>

            {/* Mobile Cards */}
            <div className="sm:hidden space-y-2">
              {breakdown.dailyReturns.map((day: { date: string; return: number; multiplier: number; cumulative: number }) => (
                <div
                  key={day.date}
                  className="flex items-center justify-between p-3 bg-gray-50 dark:bg-slate-700/50 rounded-lg"
                >
                  <div>
                    <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {new Date(day.date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">
                      ×{day.multiplier.toFixed(4)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`text-sm font-bold ${
                      day.return >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                    }`}>
                      {day.return >= 0 ? '+' : ''}{day.return.toFixed(1)}%
                    </div>
                    <div className={`text-xs ${
                      day.cumulative >= 0 ? 'text-green-500 dark:text-green-500' : 'text-red-500 dark:text-red-500'
                    }`}>
                      {day.cumulative >= 0 ? '+' : ''}{day.cumulative.toFixed(1)}% total
                    </div>
                  </div>
                </div>
              ))}
              {/* Total Card */}
              <div className="flex items-center justify-between p-3 bg-nifty-50 dark:bg-nifty-900/20 rounded-lg border border-nifty-200 dark:border-nifty-800">
                <div className="font-semibold text-gray-900 dark:text-gray-100">Total</div>
                <div className="text-right">
                  <div className={`text-lg font-bold ${
                    breakdown.finalReturn >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                  }`}>
                    {breakdown.finalReturn >= 0 ? '+' : ''}{breakdown.finalReturn.toFixed(1)}%
                  </div>
                  <div className="text-xs text-nifty-600 dark:text-nifty-400 font-mono">
                    ×{breakdown.finalMultiplier.toFixed(4)}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Visual Formula */}
          {breakdown.dailyReturns.length > 0 && (
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">Calculation</h3>
              <div className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50 font-mono text-xs text-gray-600 dark:text-gray-400 break-all">
                {breakdown.dailyReturns.map((d: { date: string; return: number }, i: number) => (
                  <span key={d.date}>
                    <span className={d.return >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                      (1 {d.return >= 0 ? '+' : ''} {d.return.toFixed(1)}%)
                    </span>
                    {i < breakdown.dailyReturns.length - 1 && ' × '}
                  </span>
                ))}
                {' = '}
                <span className="font-bold text-nifty-600 dark:text-nifty-400">
                  {breakdown.finalMultiplier.toFixed(4)}
                </span>
                {' → '}
                <span className={`font-bold ${breakdown.finalReturn >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                  {breakdown.finalReturn >= 0 ? '+' : ''}{breakdown.finalReturn.toFixed(1)}%
                </span>
              </div>
            </div>
          )}

          {/* Disclaimer */}
          <div className="p-3 rounded-lg bg-gray-100 dark:bg-slate-700/30 border border-gray-200 dark:border-slate-600">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              <strong>Note:</strong> This compound return represents theoretical portfolio growth
              if all recommendations were followed. Real trading results depend on execution,
              position sizing, and market conditions.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 p-4 border-t border-gray-100 dark:border-slate-700 bg-white dark:bg-slate-800">
          <button
            onClick={onClose}
            className="w-full btn-primary"
          >
            Got it
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
