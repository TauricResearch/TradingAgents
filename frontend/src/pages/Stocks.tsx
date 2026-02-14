import { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Search, Building2 } from 'lucide-react';
import { NIFTY_50_STOCKS } from '../types';
import type { DailyRecommendation } from '../types';
import { DecisionBadge, ConfidenceBadge } from '../components/StockCard';
import { api } from '../services/api';

export default function Stocks() {
  const [search, setSearch] = useState('');
  const [sectorFilter, setSectorFilter] = useState<string>('ALL');
  const [recommendation, setRecommendation] = useState<DailyRecommendation | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const rec = await api.getLatestRecommendation();
        if (rec && rec.analysis && Object.keys(rec.analysis).length > 0) {
          setRecommendation(rec);
        }
      } catch (err) {
        console.error('Failed to fetch recommendations:', err);
      }
    };
    fetchData();
  }, []);

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
    <div className="space-y-4">
      {/* Combined Header + Search */}
      <div className="card p-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 mb-3">
          <div>
            <h1 className="text-xl font-display font-bold text-gray-900">
              All <span className="gradient-text">Nifty 50 Stocks</span>
            </h1>
            <p className="text-sm text-gray-500">
              {filteredStocks.length} of {NIFTY_50_STOCKS.length} stocks
            </p>
          </div>
        </div>

        {/* Search and Filter - inline */}
        <div className="flex flex-col sm:flex-row gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search symbol or company..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-sm rounded-md border border-gray-200 focus:border-nifty-500 focus:ring-1 focus:ring-nifty-500/20 outline-none"
            />
          </div>
          <select
            value={sectorFilter}
            onChange={(e) => setSectorFilter(e.target.value)}
            className="px-3 py-1.5 text-sm rounded-md border border-gray-200 focus:border-nifty-500 focus:ring-1 focus:ring-nifty-500/20 outline-none bg-white"
          >
            {sectors.map((sector) => (
              <option key={sector} value={sector}>
                {sector === 'ALL' ? 'All Sectors' : sector}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Compact Stocks Grid */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
        {filteredStocks.map((stock) => {
          const analysis = getStockAnalysis(stock.symbol);
          return (
            <Link
              key={stock.symbol}
              to={`/stock/${stock.symbol}`}
              className="card-hover p-3 group"
            >
              <div className="flex items-center justify-between mb-1">
                <h3 className="font-semibold text-sm text-gray-900">{stock.symbol}</h3>
                {analysis && <DecisionBadge decision={analysis.decision} size="small" />}
              </div>
              <p className="text-xs text-gray-500 truncate mb-1.5">{stock.company_name}</p>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1">
                  <Building2 className="w-3 h-3 text-gray-400" />
                  <span className="text-xs text-gray-500 truncate">{stock.sector}</span>
                </div>
                {analysis && <ConfidenceBadge confidence={analysis.confidence} />}
              </div>
            </Link>
          );
        })}
      </div>

      {filteredStocks.length === 0 && (
        <div className="card p-8 text-center">
          <Search className="w-8 h-8 text-gray-300 mx-auto mb-2" />
          <h3 className="font-semibold text-gray-700 mb-1">No stocks found</h3>
          <p className="text-sm text-gray-500">Try adjusting your search.</p>
        </div>
      )}
    </div>
  );
}
