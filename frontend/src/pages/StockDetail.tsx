import { useParams, Link } from 'react-router-dom';
import { useMemo } from 'react';
import { ArrowLeft, Building2, TrendingUp, TrendingDown, Minus, AlertTriangle, Calendar, Activity, LineChart } from 'lucide-react';
import { NIFTY_50_STOCKS } from '../types';
import { sampleRecommendations, getStockHistory, getExtendedPriceHistory, getPredictionPointsWithPrices, getRawAnalysis } from '../data/recommendations';
import { DecisionBadge, ConfidenceBadge, RiskBadge } from '../components/StockCard';
import AIAnalysisPanel from '../components/AIAnalysisPanel';
import StockPriceChart from '../components/StockPriceChart';

export default function StockDetail() {
  const { symbol } = useParams<{ symbol: string }>();

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

      {/* Top Pick / Avoid Status - Compact */}
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
