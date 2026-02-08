import { useState } from 'react';
import {
  Database, ChevronDown, ChevronUp, CheckCircle,
  XCircle, Clock, Server, Copy, Check, Maximize2, Minimize2
} from 'lucide-react';
import type { DataSourceLog } from '../../types/pipeline';

interface DataSourcesPanelProps {
  dataSources: DataSourceLog[];
  isLoading?: boolean;
}

const SOURCE_TYPE_COLORS: Record<string, { bg: string; text: string }> = {
  market_data: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-300' },
  news: { bg: 'bg-purple-100 dark:bg-purple-900/30', text: 'text-purple-700 dark:text-purple-300' },
  fundamentals: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-300' },
  social_media: { bg: 'bg-pink-100 dark:bg-pink-900/30', text: 'text-pink-700 dark:text-pink-300' },
  indicators: { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-700 dark:text-amber-300' },
  default: { bg: 'bg-slate-100 dark:bg-slate-800', text: 'text-slate-700 dark:text-slate-300' }
};

// Raw data viewer with copy, expand/collapse, and formatted display
function RawDataViewer({ data, error }: { data: unknown; error?: string | null }) {
  const [isFullHeight, setIsFullHeight] = useState(false);
  const [copied, setCopied] = useState(false);

  if (error) {
    return (
      <div className="px-4 pb-4 border-t border-slate-100 dark:border-slate-800">
        <div className="mt-3 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
          <p className="text-sm text-red-600 dark:text-red-400">
            <strong>Error:</strong> {error}
          </p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="px-4 pb-4 border-t border-slate-100 dark:border-slate-800">
        <p className="mt-3 text-sm text-slate-500">No data details available</p>
      </div>
    );
  }

  const rawText = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
  const dataSize = rawText.length;

  const handleCopy = () => {
    navigator.clipboard.writeText(rawText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="px-4 pb-4 border-t border-slate-100 dark:border-slate-800">
      {/* Toolbar */}
      <div className="mt-3 flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
            Raw Data
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400">
            {dataSize > 1000 ? `${(dataSize / 1000).toFixed(1)}KB` : `${dataSize} chars`}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 px-2 py-1 text-[10px] rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 transition-colors"
            title="Copy raw data"
          >
            {copied ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button
            onClick={() => setIsFullHeight(!isFullHeight)}
            className="flex items-center gap-1 px-2 py-1 text-[10px] rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 transition-colors"
            title={isFullHeight ? 'Collapse' : 'Expand'}
          >
            {isFullHeight ? <Minimize2 className="w-3 h-3" /> : <Maximize2 className="w-3 h-3" />}
            {isFullHeight ? 'Collapse' : 'Expand'}
          </button>
        </div>
      </div>

      {/* Raw data content */}
      <div className={`bg-slate-900 dark:bg-slate-950 rounded-lg overflow-hidden ${isFullHeight ? '' : 'max-h-80'}`}>
        <pre className={`p-3 text-xs text-green-400 font-mono whitespace-pre-wrap break-words overflow-auto ${isFullHeight ? 'max-h-[80vh]' : 'max-h-72'}`}>
          {rawText}
        </pre>
      </div>
    </div>
  );
}


export function DataSourcesPanel({ dataSources, isLoading }: DataSourcesPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [expandedSources, setExpandedSources] = useState<Set<number>>(new Set());

  const hasData = dataSources.length > 0;
  const successCount = dataSources.filter(s => s.success).length;
  const errorCount = dataSources.filter(s => !s.success).length;

  const toggleSourceExpanded = (index: number) => {
    const newSet = new Set(expandedSources);
    if (newSet.has(index)) {
      newSet.delete(index);
    } else {
      newSet.add(index);
    }
    setExpandedSources(newSet);
  };

  const getSourceColors = (sourceType: string) => {
    return SOURCE_TYPE_COLORS[sourceType] || SOURCE_TYPE_COLORS.default;
  };

  const formatTimestamp = (timestamp?: string) => {
    if (!timestamp) return 'Unknown';
    try {
      return new Date(timestamp).toLocaleString();
    } catch {
      return timestamp;
    }
  };

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800/50 cursor-pointer"
        onClick={() => hasData && setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3">
          <div className="p-2 bg-slate-100 dark:bg-slate-700 rounded-lg">
            <Database className="w-5 h-5 text-slate-600 dark:text-slate-300" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-800 dark:text-slate-200">
              Data Sources
            </h3>
            <p className="text-xs text-slate-500">
              Raw data fetched for analysis
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {hasData ? (
            <div className="flex items-center gap-2">
              <span className="flex items-center gap-1 px-2 py-1 bg-green-100 dark:bg-green-900/40 rounded text-xs text-green-700 dark:text-green-300">
                <CheckCircle className="w-3 h-3" />
                {successCount}
              </span>
              {errorCount > 0 && (
                <span className="flex items-center gap-1 px-2 py-1 bg-red-100 dark:bg-red-900/40 rounded text-xs text-red-700 dark:text-red-300">
                  <XCircle className="w-3 h-3" />
                  {errorCount}
                </span>
              )}
            </div>
          ) : isLoading ? (
            <div className="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
          ) : (
            <span className="px-2 py-1 bg-slate-100 dark:bg-slate-800 rounded text-xs text-slate-500">
              No Data
            </span>
          )}
          {hasData && (
            isExpanded ? <ChevronUp className="w-5 h-5 text-slate-400" /> : <ChevronDown className="w-5 h-5 text-slate-400" />
          )}
        </div>
      </div>

      {/* Expanded content */}
      {isExpanded && hasData && (
        <div className="border-t border-slate-200 dark:border-slate-700">
          <div className="divide-y divide-slate-200 dark:divide-slate-700">
            {dataSources.map((source, index) => {
              const colors = getSourceColors(source.source_type);
              const isSourceExpanded = expandedSources.has(index);

              return (
                <div key={index} className="bg-white dark:bg-slate-900">
                  {/* Source header */}
                  <div
                    className="flex items-center justify-between p-3 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50"
                    onClick={() => toggleSourceExpanded(index)}
                  >
                    <div className="flex items-center gap-3">
                      <Server className="w-4 h-4 text-slate-400" />
                      <div>
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text}`}>
                            {source.source_type}
                          </span>
                          <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                            {source.source_name}
                          </span>
                        </div>
                        {source.method && (
                          <div className="flex items-center gap-1.5 mt-1 text-xs">
                            <span className="font-mono font-semibold text-amber-600 dark:text-amber-400">
                              {source.method}()
                            </span>
                            {source.args && (
                              <span className="font-mono text-slate-500 dark:text-slate-400 truncate max-w-xs">
                                {source.args}
                              </span>
                            )}
                          </div>
                        )}
                        <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
                          <Clock className="w-3 h-3" />
                          {formatTimestamp(source.fetch_timestamp)}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      {source.success ? (
                        <CheckCircle className="w-4 h-4 text-green-500" />
                      ) : (
                        <XCircle className="w-4 h-4 text-red-500" />
                      )}
                      {isSourceExpanded ? (
                        <ChevronUp className="w-4 h-4 text-slate-400" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-slate-400" />
                      )}
                    </div>
                  </div>

                  {/* Source details (expanded) — full raw data viewer */}
                  {isSourceExpanded && (
                    <RawDataViewer
                      data={source.data_fetched}
                      error={source.error_message}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default DataSourcesPanel;
