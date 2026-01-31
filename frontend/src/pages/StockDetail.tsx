import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Building2, TrendingUp, TrendingDown, Minus, AlertTriangle, Info, Calendar, Activity } from 'lucide-react';
import { NIFTY_50_STOCKS } from '../types';
import { sampleRecommendations, getStockHistory } from '../data/recommendations';
import { DecisionBadge, ConfidenceBadge, RiskBadge } from '../components/StockCard';

export default function StockDetail() {
  const { symbol } = useParams<{ symbol: string }>();

  const stock = NIFTY_50_STOCKS.find(s => s.symbol === symbol);
  const latestRecommendation = sampleRecommendations[0];
  const analysis = latestRecommendation?.analysis[symbol || ''];
  const history = symbol ? getStockHistory(symbol) : [];

  if (!stock) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="w-12 h-12 text-amber-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-gray-700 mb-2">Stock Not Found</h2>
          <p className="text-gray-500 mb-4">The stock "{symbol}" was not found in Nifty 50.</p>
          <Link to="/stocks" className="btn-primary">
            View All Stocks
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
    <div className="space-y-8">
      {/* Back Button */}
      <div>
        <Link
          to="/stocks"
          className="inline-flex items-center gap-2 text-gray-600 hover:text-nifty-600 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to All Stocks
        </Link>
      </div>

      {/* Stock Header */}
      <section className="card overflow-hidden">
        <div className={`bg-gradient-to-r ${bgGradient} p-6 text-white`}>
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <h1 className="text-3xl font-display font-bold">{stock.symbol}</h1>
                {analysis?.decision && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-white/20 backdrop-blur-sm">
                    <DecisionIcon className="w-4 h-4" />
                    {analysis.decision}
                  </span>
                )}
              </div>
              <p className="text-white/90 text-lg">{stock.company_name}</p>
              <div className="flex items-center gap-2 mt-3 text-white/80">
                <Building2 className="w-4 h-4" />
                <span>{stock.sector || 'N/A'}</span>
              </div>
            </div>
            <div className="text-right">
              <div className="text-sm text-white/80 mb-1">Latest Analysis</div>
              <div className="flex items-center gap-2 text-white/90">
                <Calendar className="w-4 h-4" />
                {latestRecommendation?.date ? new Date(latestRecommendation.date).toLocaleDateString('en-IN', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                }) : 'N/A'}
              </div>
            </div>
          </div>
        </div>

        {/* Analysis Details */}
        <div className="p-6">
          {analysis ? (
            <div className="grid md:grid-cols-3 gap-6">
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Decision</h3>
                <DecisionBadge decision={analysis.decision} />
              </div>
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Confidence</h3>
                <ConfidenceBadge confidence={analysis.confidence} />
              </div>
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Risk Level</h3>
                <RiskBadge risk={analysis.risk} />
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-3 text-gray-500">
              <Info className="w-5 h-5" />
              <span>No analysis available for this stock yet.</span>
            </div>
          )}
        </div>
      </section>

      {/* Quick Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card p-4 text-center">
          <div className="text-2xl font-bold text-gray-900">{history.length}</div>
          <div className="text-sm text-gray-500">Total Analyses</div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-2xl font-bold text-green-600">
            {history.filter(h => h.decision === 'BUY').length}
          </div>
          <div className="text-sm text-gray-500">Buy Signals</div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-2xl font-bold text-amber-600">
            {history.filter(h => h.decision === 'HOLD').length}
          </div>
          <div className="text-sm text-gray-500">Hold Signals</div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-2xl font-bold text-red-600">
            {history.filter(h => h.decision === 'SELL').length}
          </div>
          <div className="text-sm text-gray-500">Sell Signals</div>
        </div>
      </div>

      {/* Analysis History */}
      <section className="card">
        <div className="p-6 border-b border-gray-100">
          <h2 className="section-title">Recommendation History</h2>
        </div>

        {history.length > 0 ? (
          <div className="divide-y divide-gray-100">
            {history.map((entry, idx) => (
              <div key={idx} className="p-4 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="text-sm text-gray-500">
                    {new Date(entry.date).toLocaleDateString('en-IN', {
                      weekday: 'short',
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                    })}
                  </div>
                </div>
                <DecisionBadge decision={entry.decision} />
              </div>
            ))}
          </div>
        ) : (
          <div className="p-12 text-center">
            <Calendar className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-700 mb-2">No History Yet</h3>
            <p className="text-gray-500">Recommendation history will appear here as we analyze this stock daily.</p>
          </div>
        )}
      </section>

      {/* Top Pick / Avoid Status */}
      {latestRecommendation && (
        <>
          {latestRecommendation.top_picks.some(p => p.symbol === symbol) && (
            <section className="card bg-gradient-to-r from-green-50 to-emerald-50 border-green-200">
              <div className="p-6">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-xl bg-green-100 flex items-center justify-center">
                    <TrendingUp className="w-6 h-6 text-green-600" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-green-800 mb-2">Top Pick</h3>
                    <p className="text-green-700">
                      {latestRecommendation.top_picks.find(p => p.symbol === symbol)?.reason}
                    </p>
                  </div>
                </div>
              </div>
            </section>
          )}

          {latestRecommendation.stocks_to_avoid.some(s => s.symbol === symbol) && (
            <section className="card bg-gradient-to-r from-red-50 to-rose-50 border-red-200">
              <div className="p-6">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-xl bg-red-100 flex items-center justify-center">
                    <AlertTriangle className="w-6 h-6 text-red-600" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-red-800 mb-2">Stock to Avoid</h3>
                    <p className="text-red-700">
                      {latestRecommendation.stocks_to_avoid.find(s => s.symbol === symbol)?.reason}
                    </p>
                  </div>
                </div>
              </div>
            </section>
          )}
        </>
      )}

      {/* Disclaimer */}
      <section className="card p-6 bg-gray-50">
        <div className="flex items-start gap-3">
          <Info className="w-5 h-5 text-gray-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-gray-600">
            <strong>Disclaimer:</strong> This AI-generated recommendation is for educational purposes only.
            It should not be considered as financial advice. Always do your own research and consult with
            a qualified financial advisor before making investment decisions.
          </p>
        </div>
      </section>
    </div>
  );
}
