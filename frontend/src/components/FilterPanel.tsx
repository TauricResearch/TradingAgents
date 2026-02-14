import { SlidersHorizontal, ArrowUpDown } from 'lucide-react';
import { NIFTY_50_STOCKS } from '../types';
import type { FilterState } from '../types';

interface FilterPanelProps {
  filters: FilterState;
  onFilterChange: (filters: FilterState) => void;
  className?: string;
}

export default function FilterPanel({ filters, onFilterChange, className = '' }: FilterPanelProps) {
  const sectors = ['All', ...Array.from(new Set(NIFTY_50_STOCKS.map(s => s.sector).filter(Boolean))).sort()];

  const decisions: Array<FilterState['decision']> = ['ALL', 'BUY', 'SELL', 'HOLD'];
  const sortOptions: Array<{ value: FilterState['sortBy']; label: string }> = [
    { value: 'symbol', label: 'Symbol' },
    { value: 'return', label: 'Return' },
    { value: 'accuracy', label: 'Accuracy' },
  ];

  const handleDecisionChange = (decision: FilterState['decision']) => {
    onFilterChange({ ...filters, decision });
  };

  const handleSectorChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onFilterChange({ ...filters, sector: e.target.value });
  };

  const handleSortChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onFilterChange({ ...filters, sortBy: e.target.value as FilterState['sortBy'] });
  };

  const toggleSortOrder = () => {
    onFilterChange({ ...filters, sortOrder: filters.sortOrder === 'asc' ? 'desc' : 'asc' });
  };

  return (
    <div className={`flex flex-wrap items-center gap-3 p-3 bg-gray-50 dark:bg-slate-700/50 rounded-lg ${className}`}>
      <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
        <SlidersHorizontal className="w-4 h-4" />
        <span className="text-xs font-medium">Filters:</span>
      </div>

      {/* Decision Toggle */}
      <div className="flex rounded-lg overflow-hidden border border-gray-200 dark:border-slate-600">
        {decisions.map(decision => (
          <button
            key={decision}
            onClick={() => handleDecisionChange(decision)}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
              filters.decision === decision
                ? decision === 'BUY'
                  ? 'bg-green-500 text-white'
                  : decision === 'SELL'
                  ? 'bg-red-500 text-white'
                  : decision === 'HOLD'
                  ? 'bg-amber-500 text-white'
                  : 'bg-nifty-600 text-white'
                : 'bg-white dark:bg-slate-800 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-slate-700'
            }`}
          >
            {decision}
          </button>
        ))}
      </div>

      {/* Sector Dropdown */}
      <select
        value={filters.sector}
        onChange={handleSectorChange}
        className="px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-700 dark:text-gray-300 focus:ring-2 focus:ring-nifty-500 focus:border-transparent"
      >
        <option value="">All Sectors</option>
        {sectors.map(sector => (
          <option key={sector} value={sector}>{sector}</option>
        ))}
      </select>

      {/* Sort */}
      <div className="flex items-center gap-1 ml-auto">
        <select
          value={filters.sortBy}
          onChange={handleSortChange}
          className="px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-700 dark:text-gray-300 focus:ring-2 focus:ring-nifty-500 focus:border-transparent"
        >
          {sortOptions.map(opt => (
            <option key={opt.value} value={opt.value}>Sort: {opt.label}</option>
          ))}
        </select>
        <button
          onClick={toggleSortOrder}
          className="p-1.5 rounded-lg border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-slate-700"
          title={filters.sortOrder === 'asc' ? 'Ascending' : 'Descending'}
        >
          <ArrowUpDown className={`w-4 h-4 transition-transform ${filters.sortOrder === 'desc' ? 'rotate-180' : ''}`} />
        </button>
      </div>
    </div>
  );
}
