import React, { useState, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { JobReport } from '../types';
import { 
  Award, 
  Target, 
  ShieldAlert, 
  DollarSign, 
  Copy, 
  Check, 
  FileText, 
  TrendingUp, 
  Smile, 
  Globe, 
  BarChart3,
  Printer,
  Download,
  Percent,
  Scale
} from 'lucide-react';
import { downloadReportMarkdown } from '../services/api';
import { toast } from './Toast';

interface ReportViewerProps {
  report: JobReport | null;
  loading: boolean;
  onBackToArena: () => void;
}

const ReportViewerComponent: React.FC<ReportViewerProps> = ({ report, loading, onBackToArena }) => {
  const [activeTab, setActiveTab] = useState<'overview' | 'market' | 'sentiment' | 'news' | 'fundamentals'>('overview');
  const [copied, setCopied] = useState(false);
  const [downloaded, setDownloaded] = useState(false);

  const getActiveTabContent = () => {
    if (!report) return '';
    switch (activeTab) {
      case 'market':
        return report.market_report_md || '';
      case 'sentiment':
        return report.sentiment_report_md || '';
      case 'news':
        return report.news_report_md || '';
      case 'fundamentals':
        return report.fundamentals_report_md || '';
      case 'overview':
      default:
        return report.complete_report_md || report.executive_summary || '';
    }
  };

  const activeContent = getActiveTabContent();

  const handleDownloadMarkdown = () => {
    if (!report) return;
    downloadReportMarkdown(report.job_id, report.ticker, report.trade_date, activeTab, activeContent);
    setDownloaded(true);
    toast.success(`Downloaded ${activeTab} report as Markdown`);
    setTimeout(() => setDownloaded(false), 2000);
  };

  const handleCopyMarkdown = () => {
    if (!activeContent) return;
    navigator.clipboard.writeText(activeContent);
    setCopied(true);
    toast.success(`Copied ${activeTab} report section to clipboard`);
    setTimeout(() => setCopied(false), 2000);
  };

  const handlePrint = () => {
    window.print();
  };

  // Quantitative calculations for financial metrics
  const financialMetrics = useMemo(() => {
    if (!report) return null;
    const entry = typeof report.entry_price === 'number' ? report.entry_price : parseFloat(String(report.entry_price || ''));
    const target = typeof report.target_price === 'number' ? report.target_price : parseFloat(String(report.target_price || ''));
    const stop = typeof report.stop_loss === 'number' ? report.stop_loss : parseFloat(String(report.stop_loss || ''));

    let upsidePct: number | null = null;
    let riskPct: number | null = null;
    let riskRewardRatio: string | null = null;

    if (!isNaN(entry) && !isNaN(target) && entry > 0) {
      upsidePct = ((target - entry) / entry) * 100;
    }
    if (!isNaN(entry) && !isNaN(stop) && entry > 0) {
      riskPct = (Math.abs(entry - stop) / entry) * 100;
    }
    if (upsidePct !== null && riskPct !== null && riskPct > 0) {
      const reward = Math.abs(target - entry);
      const risk = Math.abs(entry - stop);
      riskRewardRatio = (reward / risk).toFixed(2);
    }

    return { entry, target, stop, upsidePct, riskPct, riskRewardRatio };
  }, [report]);

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-dark-950">
        <div className="w-10 h-10 border-3 border-brand-emerald border-t-transparent rounded-full animate-spin mb-3" />
        <span className="text-xs font-mono text-slate-400">Loading analysis report...</span>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-dark-950">
        <FileText className="w-12 h-12 text-slate-600 mb-3" />
        <h3 className="text-sm font-bold text-slate-300">No Report Available</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-sm">
          This analysis is either currently in progress or encountered an error before generating reports.
        </p>
        <button
          onClick={onBackToArena}
          className="mt-4 px-3.5 py-1.5 rounded-lg bg-dark-800 border border-dark-700 text-xs font-mono text-brand-cyan hover:bg-dark-750 transition-colors"
        >
          Return to Live Arena
        </button>
      </div>
    );
  }

  const recommendation = report.recommendation?.toUpperCase() || 'HOLD';
  const isBuy = recommendation.includes('BUY') || recommendation.includes('OVERWEIGHT');
  const isSell = recommendation.includes('SELL') || recommendation.includes('UNDERWEIGHT');

  const reportTabs = [
    { key: 'overview', label: 'Complete Report', icon: <FileText className="w-3.5 h-3.5" />, hasData: !!report.complete_report_md },
    { key: 'market', label: 'Technicals & Indicators', icon: <TrendingUp className="w-3.5 h-3.5" />, hasData: !!report.market_report_md },
    { key: 'sentiment', label: 'Social Sentiment', icon: <Smile className="w-3.5 h-3.5" />, hasData: !!report.sentiment_report_md },
    { key: 'news', label: 'Macro & Prediction', icon: <Globe className="w-3.5 h-3.5" />, hasData: !!report.news_report_md },
    { key: 'fundamentals', label: 'Financial Statements', icon: <BarChart3 className="w-3.5 h-3.5" />, hasData: !!report.fundamentals_report_md },
  ];

  return (
    <div id="report-printable-area" className="flex-1 flex flex-col h-full bg-dark-950 overflow-y-auto font-sans">
      {/* Top Banner: Verdict & Metrics */}
      <div className="p-3 sm:p-6 border-b border-dark-700/60 bg-gradient-to-b from-dark-900 to-dark-950 shrink-0">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="flex items-center space-x-3 sm:space-x-4">
            <div
              className={`w-12 h-12 sm:w-14 sm:h-14 rounded-2xl flex items-center justify-center shadow-2xl border-2 shrink-0 ${
                isBuy
                  ? 'bg-brand-emerald/20 border-brand-emerald text-brand-emerald glow-emerald'
                  : isSell
                  ? 'bg-brand-rose/20 border-brand-rose text-brand-rose glow-rose'
                  : 'bg-brand-amber/20 border-brand-amber text-brand-amber'
              }`}
            >
              <Award className="w-6 h-6 sm:w-8 sm:h-8" />
            </div>

            <div>
              <div className="flex items-center space-x-2 sm:space-x-2.5">
                <span className="text-lg sm:text-2xl font-bold font-mono tracking-wide text-slate-100">
                  {report.ticker}
                </span>
                <span className="text-xs font-mono text-slate-400 bg-dark-800 px-2 py-0.5 rounded border border-dark-700">
                  {report.trade_date}
                </span>
              </div>
              <div className="flex items-center space-x-2 mt-1.5">
                <span className="text-xs text-slate-400 font-medium">Verdict:</span>
                <span
                  className={`text-xs font-mono font-bold px-3 py-0.5 rounded-full uppercase tracking-wider ${
                    isBuy
                      ? 'bg-brand-emerald text-dark-950 shadow-sm shadow-brand-emerald/30'
                      : isSell
                      ? 'bg-brand-rose text-white shadow-sm shadow-brand-rose/30'
                      : 'bg-brand-amber text-dark-950 shadow-sm shadow-brand-amber/30'
                  }`}
                >
                  {recommendation}
                </span>
              </div>
            </div>
          </div>

          {/* Target Levels & Derived Financial Metrics */}
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            {financialMetrics?.entry && (
              <div className="px-3 py-1.5 rounded-xl bg-dark-850 border border-dark-700 font-mono text-xs shadow-sm">
                <div className="text-[10px] text-slate-400 flex items-center space-x-1">
                  <DollarSign className="w-3 h-3 text-brand-cyan" />
                  <span>Entry Target</span>
                </div>
                <div className="font-bold text-slate-100 tabular-nums">${financialMetrics.entry}</div>
              </div>
            )}

            {financialMetrics?.stop && (
              <div className="px-3 py-1.5 rounded-xl bg-dark-850 border border-dark-700 font-mono text-xs shadow-sm">
                <div className="text-[10px] text-slate-400 flex items-center space-x-1">
                  <ShieldAlert className="w-3 h-3 text-brand-rose" />
                  <span>Stop Loss</span>
                </div>
                <div className="font-bold text-brand-rose tabular-nums">${financialMetrics.stop}</div>
              </div>
            )}

            {financialMetrics?.target && (
              <div className="px-3 py-1.5 rounded-xl bg-dark-850 border border-dark-700 font-mono text-xs shadow-sm">
                <div className="text-[10px] text-slate-400 flex items-center space-x-1">
                  <Target className="w-3 h-3 text-brand-emerald" />
                  <span>Price Target</span>
                </div>
                <div className="font-bold text-brand-emerald tabular-nums">${financialMetrics.target}</div>
              </div>
            )}

            {financialMetrics && financialMetrics.upsidePct !== null && (
              <div className="px-3 py-1.5 rounded-xl bg-dark-850 border border-brand-emerald/30 font-mono text-xs shadow-sm">
                <div className="text-[10px] text-slate-400 flex items-center space-x-1">
                  <Percent className="w-3 h-3 text-brand-emerald" />
                  <span>Return Target</span>
                </div>
                <div className={`font-bold tabular-nums ${financialMetrics.upsidePct >= 0 ? 'text-brand-emerald' : 'text-brand-rose'}`}>
                  {financialMetrics.upsidePct >= 0 ? `+${financialMetrics.upsidePct.toFixed(1)}%` : `${financialMetrics.upsidePct.toFixed(1)}%`}
                </div>
              </div>
            )}

            {financialMetrics && financialMetrics.riskRewardRatio && (
              <div className="px-3 py-1.5 rounded-xl bg-dark-850 border border-brand-amber/30 font-mono text-xs shadow-sm">
                <div className="text-[10px] text-slate-400 flex items-center space-x-1">
                  <Scale className="w-3 h-3 text-brand-amber" />
                  <span>R:R Ratio</span>
                </div>
                <div className="font-bold text-brand-amber tabular-nums">{financialMetrics.riskRewardRatio}x</div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex flex-wrap items-center gap-1.5 sm:space-x-1.5 no-print ml-auto sm:ml-0">
              <button
                onClick={handleDownloadMarkdown}
                title="Download Report as Markdown (.md) File"
                className="flex items-center space-x-1 px-2.5 sm:px-3 py-1.5 rounded-lg bg-dark-800 hover:bg-dark-750 border border-dark-700 text-slate-300 hover:text-brand-cyan text-xs font-mono transition-colors active:scale-95"
              >
                {downloaded ? <Check className="w-3.5 h-3.5 text-brand-emerald" /> : <Download className="w-3.5 h-3.5" />}
                <span className="hidden md:inline">{downloaded ? 'Downloaded' : 'Download MD'}</span>
              </button>

              <button
                onClick={handlePrint}
                title="Print or Export Institutional PDF"
                className="flex items-center space-x-1 px-2.5 sm:px-3 py-1.5 rounded-lg bg-dark-800 hover:bg-dark-750 border border-dark-700 text-slate-300 hover:text-slate-100 text-xs font-mono transition-colors active:scale-95"
              >
                <Printer className="w-3.5 h-3.5" />
                <span className="hidden md:inline">Export PDF</span>
              </button>

              <button
                onClick={handleCopyMarkdown}
                title="Copy Active Section to Clipboard"
                className="flex items-center space-x-1 px-2.5 sm:px-3 py-1.5 rounded-lg bg-dark-800 hover:bg-dark-750 border border-dark-700 text-slate-300 hover:text-slate-100 text-xs font-mono transition-colors active:scale-95"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-brand-emerald" /> : <Copy className="w-3.5 h-3.5" />}
                <span className="hidden md:inline">{copied ? 'Copied' : 'Copy MD'}</span>
              </button>
            </div>
          </div>
        </div>

        {/* Executive Thesis Callout */}
        {report.executive_summary && (
          <div className="mt-4 p-4 rounded-xl bg-dark-850/80 border border-dark-700/80">
            <h4 className="text-[11px] font-mono font-bold text-slate-400 uppercase tracking-wider mb-1">
              Portfolio Manager Executive Thesis
            </h4>
            <p className="text-xs sm:text-sm text-slate-200 leading-relaxed font-sans">
              {report.executive_summary}
            </p>
          </div>
        )}
      </div>

      {/* Sub-Report Navigation Tabs */}
      <div className="px-3 sm:px-6 pt-3 border-b border-dark-700/60 bg-dark-900 flex items-center space-x-1 sm:space-x-2 overflow-x-auto no-scrollbar shrink-0 no-print">
        {reportTabs.map((t) => {
          const isActive = activeTab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key as any)}
              className={`flex items-center space-x-1.5 px-3 py-2 border-b-2 text-xs font-medium transition-all shrink-0 ${
                isActive
                  ? 'border-brand-emerald text-brand-emerald bg-brand-emerald/5'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-dark-600'
              }`}
            >
              {t.icon}
              <span>{t.label}</span>
              {t.hasData && (
                <span className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-brand-emerald' : 'bg-slate-600'}`} />
              )}
            </button>
          );
        })}
      </div>

      {/* Report Markdown Content */}
      <div className="flex-1 p-4 sm:p-8 max-w-5xl mx-auto w-full">
        {activeContent ? (
          <div className="glass-panel p-6 sm:p-8 rounded-2xl border border-dark-700/80 shadow-xl printable-content">
            <div className="markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {activeContent}
              </ReactMarkdown>
            </div>
          </div>
        ) : (
          <div className="text-center py-20 text-xs font-mono text-slate-500">
            No specific analysis notes recorded for this section.
          </div>
        )}
      </div>
    </div>
  );
};

export const ReportViewer = React.memo(ReportViewerComponent);
