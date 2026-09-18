import React, { useState } from 'react';
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
  Download
} from 'lucide-react';
import { downloadReportMarkdown } from '../services/api';

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

  const handleDownloadMarkdown = () => {
    if (!report) return;
    const content = getActiveTabContent();
    downloadReportMarkdown(report.job_id, report.ticker, report.trade_date, activeTab, content);
    setDownloaded(true);
    setTimeout(() => setDownloaded(false), 2000);
  };

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
          className="mt-4 px-3 py-1.5 rounded-lg bg-dark-800 border border-dark-700 text-xs font-mono text-brand-cyan hover:bg-dark-750"
        >
          Return to Live Arena
        </button>
      </div>
    );
  }

  const recommendation = report.recommendation?.toUpperCase() || 'HOLD';
  const isBuy = recommendation.includes('BUY') || recommendation.includes('OVERWEIGHT');
  const isSell = recommendation.includes('SELL') || recommendation.includes('UNDERWEIGHT');

  const handleCopyMarkdown = () => {
    const textToCopy = report.complete_report_md || report.executive_summary || '';
    navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handlePrint = () => {
    window.print();
  };

  return (
    <div id="report-printable-area" className="flex-1 flex flex-col h-full bg-dark-950 overflow-y-auto">

      {/* Top Banner: Verdict & Metrics */}
      <div className="p-6 border-b border-dark-700/60 bg-gradient-to-b from-dark-900 to-dark-950">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center space-x-4">
            <div
              className={`w-14 h-14 rounded-2xl flex items-center justify-center shadow-2xl border-2 ${
                isBuy
                  ? 'bg-brand-emerald/20 border-brand-emerald text-brand-emerald glow-emerald'
                  : isSell
                  ? 'bg-brand-rose/20 border-brand-rose text-brand-rose glow-rose'
                  : 'bg-brand-amber/20 border-brand-amber text-brand-amber'
              }`}
            >
              <Award className="w-8 h-8" />
            </div>

            <div>
              <div className="flex items-center space-x-2.5">
                <span className="text-xl font-bold font-mono tracking-wide text-slate-100">
                  {report.ticker}
                </span>
                <span className="text-xs font-mono text-slate-400">
                  Trade Date: {report.trade_date}
                </span>
              </div>
              <div className="flex items-center space-x-2 mt-1">
                <span className="text-xs text-slate-400 font-medium">Final Rating:</span>
                <span
                  className={`text-xs font-mono font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wider ${
                    isBuy
                      ? 'bg-brand-emerald text-dark-950'
                      : isSell
                      ? 'bg-brand-rose text-white'
                      : 'bg-brand-amber text-dark-950'
                  }`}
                >
                  {recommendation}
                </span>
              </div>
            </div>
          </div>

          {/* Target Levels & Actions */}
          <div className="flex flex-wrap items-center gap-3">
            {report.entry_price && (
              <div className="px-3 py-1.5 rounded-lg bg-dark-850 border border-dark-700/80 font-mono text-xs">
                <div className="text-[10px] text-slate-400 flex items-center space-x-1">
                  <DollarSign className="w-3 h-3 text-brand-cyan" />
                  <span>Entry Target</span>
                </div>
                <div className="font-bold text-slate-100">${report.entry_price}</div>
              </div>
            )}

            {report.stop_loss && (
              <div className="px-3 py-1.5 rounded-lg bg-dark-850 border border-dark-700/80 font-mono text-xs">
                <div className="text-[10px] text-slate-400 flex items-center space-x-1">
                  <ShieldAlert className="w-3 h-3 text-brand-rose" />
                  <span>Stop Loss</span>
                </div>
                <div className="font-bold text-brand-rose">${report.stop_loss}</div>
              </div>
            )}

            {report.target_price && (
              <div className="px-3 py-1.5 rounded-lg bg-dark-850 border border-dark-700/80 font-mono text-xs">
                <div className="text-[10px] text-slate-400 flex items-center space-x-1">
                  <Target className="w-3 h-3 text-brand-emerald" />
                  <span>Price Target</span>
                </div>
                <div className="font-bold text-brand-emerald tabular-nums">${report.target_price}</div>
              </div>
            )}

            <div className="flex items-center space-x-2 no-print">
              <button
                onClick={handleDownloadMarkdown}
                title="Download Report as Markdown (.md) File"
                className="flex items-center space-x-1.5 px-3 py-2 rounded-lg bg-dark-800 hover:bg-dark-700 border border-brand-emerald/40 text-xs font-mono text-brand-emerald transition-colors active:scale-95 shadow-sm"
              >
                {downloaded ? <Check className="w-3.5 h-3.5 text-brand-emerald" /> : <Download className="w-3.5 h-3.5" />}
                <span>{downloaded ? 'Downloaded' : 'Download MD'}</span>
              </button>

              <button
                onClick={handlePrint}
                title="Print or Save Institutional PDF Report"
                className="flex items-center space-x-1.5 px-3 py-2 rounded-lg bg-dark-800 hover:bg-dark-700 border border-dark-600 text-xs font-mono text-slate-200 transition-colors active:scale-95"
              >
                <Printer className="w-3.5 h-3.5 text-brand-cyan" />
                <span>Export PDF</span>
              </button>

              <button
                onClick={handleCopyMarkdown}
                title="Copy Full Report Markdown to Clipboard"
                className="flex items-center space-x-1.5 px-3 py-2 rounded-lg bg-dark-800 hover:bg-dark-700 border border-dark-600 text-xs font-mono text-slate-200 transition-colors active:scale-95"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-brand-emerald" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? 'Copied' : 'Copy MD'}</span>
              </button>
            </div>
          </div>
        </div>

        {/* Executive Summary Card */}
        {report.executive_summary && (
          <div className="mt-4 p-4 rounded-xl bg-dark-850/80 border border-dark-700/80 shadow-inner">
            <h4 className="text-xs font-bold text-slate-300 uppercase font-mono tracking-wider mb-1.5 flex items-center space-x-1.5">
              <span>Portfolio Manager Executive Thesis</span>
            </h4>
            <p className="text-xs text-slate-200 leading-relaxed whitespace-pre-line font-sans">
              {report.executive_summary}
            </p>
          </div>
        )}
      </div>

      {/* Report Tabs Navigation */}
      <div className="px-6 border-b border-dark-700/60 bg-dark-900 flex space-x-2 no-print">
        {[
          { id: 'overview', label: 'Complete Report', icon: <FileText className="w-3.5 h-3.5" /> },
          { id: 'market', label: 'Technicals & Indicators', icon: <TrendingUp className="w-3.5 h-3.5" /> },
          { id: 'sentiment', label: 'Social Sentiment', icon: <Smile className="w-3.5 h-3.5" /> },
          { id: 'news', label: 'Macro & Prediction', icon: <Globe className="w-3.5 h-3.5" /> },
          { id: 'fundamentals', label: 'Financial Statements', icon: <BarChart3 className="w-3.5 h-3.5" /> },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id as any)}
            className={`flex items-center space-x-1.5 px-4 py-3 text-xs font-semibold border-b-2 transition-all ${
              activeTab === t.id
                ? 'border-brand-emerald text-brand-emerald'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            {t.icon}
            <span>{t.label}</span>
          </button>
        ))}
      </div>


      {/* Tab Content Display */}
      <div className="p-6 font-sans">
        <div className="max-w-4xl mx-auto glass-panel p-6 rounded-xl border border-dark-700/80 leading-relaxed text-slate-200 text-xs">
          {activeTab === 'overview' && <MarkdownRenderer content={report.complete_report_md || ''} />}
          {activeTab === 'market' && <MarkdownRenderer content={report.market_report_md || ''} />}
          {activeTab === 'sentiment' && <MarkdownRenderer content={report.sentiment_report_md || ''} />}
          {activeTab === 'news' && <MarkdownRenderer content={report.news_report_md || ''} />}
          {activeTab === 'fundamentals' && <MarkdownRenderer content={report.fundamentals_report_md || ''} />}
        </div>
      </div>
    </div>
  );
};

const MarkdownRenderer: React.FC<{ content: string }> = ({ content }) => {
  if (!content || !content.trim()) {
    return <div className="text-slate-500 italic py-4">No report content recorded for this section.</div>;
  }

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ node, ...props }) => (
          <h1 className="text-base font-bold text-slate-100 border-b border-dark-700 pb-2 mb-4 mt-6 first:mt-0 font-mono flex items-center gap-2" {...props} />
        ),
        h2: ({ node, ...props }) => (
          <h2 className="text-sm font-bold text-brand-emerald mb-3 mt-5 font-mono" {...props} />
        ),
        h3: ({ node, ...props }) => (
          <h3 className="text-xs font-bold text-brand-cyan mb-2 mt-4 font-mono uppercase tracking-wider" {...props} />
        ),
        h4: ({ node, ...props }) => (
          <h4 className="text-xs font-semibold text-slate-300 mb-1.5 mt-3 font-mono" {...props} />
        ),
        p: ({ node, ...props }) => (
          <p className="mb-3 leading-relaxed text-slate-300 text-xs font-sans" {...props} />
        ),
        ul: ({ node, ...props }) => (
          <ul className="list-disc list-inside space-y-1 mb-3 text-slate-300 text-xs font-sans" {...props} />
        ),
        ol: ({ node, ...props }) => (
          <ol className="list-decimal list-inside space-y-1 mb-3 text-slate-300 text-xs font-sans" {...props} />
        ),
        li: ({ node, ...props }) => (
          <li className="text-slate-300 leading-relaxed" {...props} />
        ),
        table: ({ node, ...props }) => (
          <div className="overflow-x-auto my-4 rounded-lg border border-dark-700/80 shadow-sm">
            <table className="min-w-full divide-y divide-dark-700 text-xs font-mono" {...props} />
          </div>
        ),
        thead: ({ node, ...props }) => (
          <thead className="bg-dark-800 text-slate-200" {...props} />
        ),
        th: ({ node, ...props }) => (
          <th className="px-3 py-2 text-left font-bold border-b border-dark-700 text-[11px] tracking-wider uppercase text-slate-400" {...props} />
        ),
        td: ({ node, ...props }) => (
          <td className="px-3 py-2 border-b border-dark-800/60 text-slate-300 text-[11px]" {...props} />
        ),
        blockquote: ({ node, ...props }) => (
          <blockquote className="border-l-2 border-brand-cyan bg-dark-850/60 px-3 py-2 my-3 text-xs italic text-slate-300 rounded-r" {...props} />
        ),
        code: ({ node, inline, ...props }: any) => (
          inline ? (
            <code className="px-1.5 py-0.5 rounded bg-dark-800 text-brand-cyan font-mono text-[11px]" {...props} />
          ) : (
            <pre className="p-3 my-3 rounded-lg bg-dark-900 border border-dark-700 font-mono text-[11px] text-slate-200 overflow-x-auto" {...props} />
          )
        ),
        strong: ({ node, ...props }) => (
          <strong className="font-bold text-slate-100" {...props} />
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
};

export const ReportViewer = React.memo(ReportViewerComponent);
