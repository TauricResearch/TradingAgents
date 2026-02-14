import { X, CheckCircle, XCircle, Calculator } from 'lucide-react';
import { createPortal } from 'react-dom';
import type { ReturnBreakdown } from '../types';

interface ReturnExplainModalProps {
  isOpen: boolean;
  onClose: () => void;
  breakdown: ReturnBreakdown | null;
  date: string;
}

export default function ReturnExplainModal({ isOpen, onClose, breakdown, date }: ReturnExplainModalProps) {
  if (!isOpen || !breakdown) return null;

  const formattedDate = new Date(date).toLocaleDateString('en-IN', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

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
            <Calculator className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Return Calculation
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
          {/* Date & Result */}
          <div className="p-4 rounded-lg bg-nifty-50 dark:bg-nifty-900/20 border border-nifty-100 dark:border-nifty-800">
            <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">{formattedDate}</div>
            <div className={`text-3xl font-bold ${breakdown.weightedReturn >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
              {breakdown.weightedReturn >= 0 ? '+' : ''}{breakdown.weightedReturn.toFixed(1)}%
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              Weighted Average Return
            </p>
          </div>

          {/* Method Explanation */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">Calculation Method</h3>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50 text-sm space-y-2">
              <p className="text-gray-700 dark:text-gray-300">
                <strong>1. Correct Predictions</strong> → Contribute <span className="text-green-600 dark:text-green-400">positively</span>
              </p>
              <ul className="text-xs text-gray-600 dark:text-gray-400 ml-4 space-y-1">
                <li>• BUY that went up → add the gain</li>
                <li>• SELL that went down → add the avoided loss</li>
                <li>• HOLD that stayed flat → small positive</li>
              </ul>
              <p className="text-gray-700 dark:text-gray-300 mt-2">
                <strong>2. Incorrect Predictions</strong> → Contribute <span className="text-red-600 dark:text-red-400">negatively</span>
              </p>
              <ul className="text-xs text-gray-600 dark:text-gray-400 ml-4 space-y-1">
                <li>• BUY that went down → subtract the loss</li>
                <li>• SELL that went up → subtract missed gain</li>
                <li>• HOLD that moved → subtract missed opportunity</li>
              </ul>
              <p className="text-gray-700 dark:text-gray-300 mt-2">
                <strong>3. Weighted Average</strong>
              </p>
              <div className="p-2 bg-white dark:bg-slate-800 rounded border border-gray-200 dark:border-slate-600 font-mono text-xs">
                (Correct Avg × Correct Weight) + (Incorrect Avg × Incorrect Weight)
              </div>
            </div>
          </div>

          {/* Correct Predictions Breakdown */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle className="w-4 h-4 text-green-600 dark:text-green-400" />
              <h3 className="font-semibold text-green-800 dark:text-green-300">Correct Predictions</h3>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                ({breakdown.correctPredictions.count} stocks)
              </span>
            </div>
            <div className="p-3 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-100 dark:border-green-800">
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Average Return</div>
                  <div className="text-lg font-bold text-green-600 dark:text-green-400">
                    +{breakdown.correctPredictions.avgReturn.toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Weight</div>
                  <div className="text-lg font-bold text-green-600 dark:text-green-400">
                    {breakdown.correctPredictions.count}/{breakdown.correctPredictions.count + breakdown.incorrectPredictions.count}
                  </div>
                </div>
              </div>
              {breakdown.correctPredictions.stocks.length > 0 && (
                <div className="border-t border-green-200 dark:border-green-700 pt-2">
                  <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Top performers:</div>
                  <div className="space-y-1">
                    {breakdown.correctPredictions.stocks.map((stock: { symbol: string; decision: string; return1d: number }) => (
                      <div key={stock.symbol} className="flex items-center justify-between text-xs">
                        <span className="font-medium text-gray-700 dark:text-gray-300">
                          {stock.symbol}
                          <span className={`ml-1 ${
                            stock.decision === 'BUY' ? 'text-green-600 dark:text-green-400' :
                            stock.decision === 'SELL' ? 'text-red-600 dark:text-red-400' :
                            'text-amber-600 dark:text-amber-400'
                          }`}>
                            ({stock.decision})
                          </span>
                        </span>
                        <span className="text-green-600 dark:text-green-400">+{stock.return1d.toFixed(1)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Incorrect Predictions Breakdown */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <XCircle className="w-4 h-4 text-red-600 dark:text-red-400" />
              <h3 className="font-semibold text-red-800 dark:text-red-300">Incorrect Predictions</h3>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                ({breakdown.incorrectPredictions.count} stocks)
              </span>
            </div>
            <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-800">
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Average Return</div>
                  <div className="text-lg font-bold text-red-600 dark:text-red-400">
                    {breakdown.incorrectPredictions.avgReturn.toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Weight</div>
                  <div className="text-lg font-bold text-red-600 dark:text-red-400">
                    {breakdown.incorrectPredictions.count}/{breakdown.correctPredictions.count + breakdown.incorrectPredictions.count}
                  </div>
                </div>
              </div>
              {breakdown.incorrectPredictions.stocks.length > 0 && (
                <div className="border-t border-red-200 dark:border-red-700 pt-2">
                  <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Worst performers:</div>
                  <div className="space-y-1">
                    {breakdown.incorrectPredictions.stocks.map((stock: { symbol: string; decision: string; return1d: number }) => (
                      <div key={stock.symbol} className="flex items-center justify-between text-xs">
                        <span className="font-medium text-gray-700 dark:text-gray-300">
                          {stock.symbol}
                          <span className={`ml-1 ${
                            stock.decision === 'BUY' ? 'text-green-600 dark:text-green-400' :
                            stock.decision === 'SELL' ? 'text-red-600 dark:text-red-400' :
                            'text-amber-600 dark:text-amber-400'
                          }`}>
                            ({stock.decision})
                          </span>
                        </span>
                        <span className="text-red-600 dark:text-red-400">{stock.return1d.toFixed(1)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Final Calculation */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">Final Calculation</h3>
            <div className="p-3 rounded-lg bg-gray-50 dark:bg-slate-700/50">
              <div className="font-mono text-xs text-gray-600 dark:text-gray-400 break-all">
                {breakdown.formula}
              </div>
            </div>
          </div>

          {/* Disclaimer */}
          <div className="p-3 rounded-lg bg-gray-100 dark:bg-slate-700/30 border border-gray-200 dark:border-slate-600">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              <strong>Note:</strong> This weighted return represents the theoretical gain/loss
              if you followed all predictions for the day. Actual results may vary based on
              execution timing, transaction costs, and market conditions.
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
