import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Search, Filter, ChevronRight, Building2 } from 'lucide-react';
import { NIFTY_50_STOCKS } from '../types';
import { getLatestRecommendation } from '../data/recommendations';
import { DecisionBadge, ConfidenceBadge } from '../components/StockCard';

export default function Stocks() {
  const [search, setSearch] = useState('');
  const [sectorFilter, setSectorFilter] = useState<string>('ALL');

  const recommendation = getLatestRecommendation();

  const sectors = useMemo(() => {
    const sectorSet = new Set(NIFTY_50_STOCKS.map(s => s.sector).filter(Boolean));
    return ['ALL', ...Array.from(sectorSet).sort()];
  }, []);

  const filteredStocks = useMemo(() => {
    return NIFTY_50_STOCKS.filter(stock => {
      const matchesSearch =
        stock.symbol.toLowerCase().includes(search.toLowerCase()) ||
        stock.company_name.toLowerCase().includes(search.toLowerCase());

      const matchesSector = sectorFilter === 'ALL' || stock.sector === sectorFilter;

      return matchesSearch && matchesSector;
    });
  }, [search, sectorFilter]);

  const getStockAnalysis = (symbol: string) => {
    return recommendation?.analysis[symbol];
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <section className="text-center py-8">
        <h1 className="text-4xl font-display font-bold text-gray-900 mb-4">
          All <span className="gradient-text">Nifty 50 Stocks</span>
        </h1>
        <p className="text-lg text-gray-600 max-w-2xl mx-auto">
          Browse all 50 stocks in the Nifty index with their latest AI recommendations.
        </p>
      </section>

      {/* Search and Filter */}
      <div className="card p-6">
        <div className="flex flex-col md:flex-row gap-4">
          {/* Search */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              placeholder="Search by symbol or company name..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-gray-200 focus:border-nifty-500 focus:ring-2 focus:ring-nifty-500/20 outline-none transition-all"
            />
          </div>

          {/* Sector Filter */}
          <div className="flex items-center gap-2">
            <Filter className="w-5 h-5 text-gray-400" />
            <select
              value={sectorFilter}
              onChange={(e) => setSectorFilter(e.target.value)}
              className="px-4 py-2.5 rounded-lg border border-gray-200 focus:border-nifty-500 focus:ring-2 focus:ring-nifty-500/20 outline-none bg-white"
            >
              {sectors.map((sector) => (
                <option key={sector} value={sector}>
                  {sector === 'ALL' ? 'All Sectors' : sector}
                </option>
              ))}
            </select>
          </div>
        </div>

        <p className="text-sm text-gray-500 mt-4">
          Showing {filteredStocks.length} of {NIFTY_50_STOCKS.length} stocks
        </p>
      </div>

      {/* Stocks Grid */}
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredStocks.map((stock) => {
          const analysis = getStockAnalysis(stock.symbol);
          return (
            <Link
              key={stock.symbol}
              to={`/stock/${stock.symbol}`}
              className="card-hover p-4 group"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-bold text-lg text-gray-900">{stock.symbol}</h3>
                  <p className="text-sm text-gray-500">{stock.company_name}</p>
                </div>
                <ChevronRight className="w-5 h-5 text-gray-400 group-hover:text-nifty-600 transition-colors" />
              </div>

              <div className="flex items-center gap-2 mb-3">
                <Building2 className="w-4 h-4 text-gray-400" />
                <span className="text-sm text-gray-600">{stock.sector}</span>
              </div>

              {analysis && (
                <div className="pt-3 border-t border-gray-100">
                  <div className="flex items-center justify-between">
                    <DecisionBadge decision={analysis.decision} />
                    <div className="flex items-center gap-2">
                      <ConfidenceBadge confidence={analysis.confidence} />
                    </div>
                  </div>
                </div>
              )}
            </Link>
          );
        })}
      </div>

      {filteredStocks.length === 0 && (
        <div className="card p-12 text-center">
          <Search className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-700 mb-2">No stocks found</h3>
          <p className="text-gray-500">Try adjusting your search or filter criteria.</p>
        </div>
      )}
    </div>
  );
}
