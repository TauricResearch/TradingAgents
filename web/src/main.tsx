import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Activity,
  BarChart3,
  Bot,
  CheckCircle2,
  ChevronRight,
  Circle,
  Database,
  Download,
  History,
  KeyRound,
  LogOut,
  MessageSquareQuote,
  Moon,
  Play,
  RefreshCw,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  Trash2,
} from 'lucide-react';
import { api, type AnalysisRequest, type CompanySuggestion, type RunSummary, type SettingsPayload } from './lib/api';
import { AGENT_GROUPS, createRunView, getConclusionEvents, getTimelineEvents, reduceRunEvent, type RunEvent, type RunView } from './lib/runEvents';
import { getSettingsSectionVisibility, type SettingsCategory } from './lib/settingsTabs';
import './styles.css';

type Page = 'research' | 'chat' | 'history' | 'settings';

const defaultSettings: SettingsPayload = {
  llm_provider: 'openai',
  deep_think_llm: 'gpt-5.4',
  quick_think_llm: 'gpt-5.4-mini',
  backend_url: null,
  output_language: 'Chinese',
  max_debate_rounds: 1,
  max_risk_discuss_rounds: 1,
  checkpoint_enabled: false,
  data_vendors: {
    core_stock_apis: 'yfinance',
    technical_indicators: 'yfinance',
    fundamental_data: 'yfinance',
    news_data: 'yfinance',
  },
};

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(' ');
}

const statusLabels: Record<string, string> = {
  queued: '排队中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  pending: '待处理',
};

const agentLabels: Record<string, string> = {
  'Market Analyst': '市场分析师',
  'Social Analyst': '社媒分析师',
  'News Analyst': '新闻分析师',
  'Fundamentals Analyst': '基本面分析师',
  'Bull Researcher': '多头研究员',
  'Bear Researcher': '空头研究员',
  'Research Manager': '研究经理',
  Trader: '交易员',
  'Aggressive Analyst': '进取型风险分析师',
  'Neutral Analyst': '中性风险分析师',
  'Conservative Analyst': '保守型风险分析师',
  'Portfolio Manager': '组合经理',
  Agent: '智能体',
};

const vendorLabels: Record<string, string> = {
  core_stock_apis: '核心行情接口',
  technical_indicators: '技术指标',
  fundamental_data: '基本面数据',
  news_data: '新闻数据',
};

const researchDepthOptions = [
  { value: 1, label: '1 · 快速研究（1 轮多空辩论 + 1 轮风控讨论）' },
  { value: 2, label: '2 · 标准研究（2 轮多空辩论 + 2 轮风控讨论）' },
  { value: 3, label: '3 · 深度研究（3 轮多空辩论 + 3 轮风控讨论）' },
  { value: 4, label: '4 · 强化研究（4 轮多空辩论 + 4 轮风控讨论）' },
  { value: 5, label: '5 · 最深研究（5 轮多空辩论 + 5 轮风控讨论）' },
];

function formatStatus(status: string) {
  return statusLabels[status] ?? status;
}

function formatAgent(agent: string) {
  return agentLabels[agent] ?? agent;
}

function formatVendor(key: string) {
  return vendorLabels[key] ?? key;
}

function displayRunName(run: RunSummary) {
  return run.company_name ? `${run.company_name} · ${run.ticker}` : `${run.ticker} · 自动识别中`;
}

function buildRunView(runId: string, events: RunEvent[]) {
  return events.reduce((view, event) => reduceRunEvent(view, event), createRunView(runId));
}

function downloadTextFile(filename: string, content: string) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function sanitizeTickerInput(value: string) {
  let cleaned = value.toUpperCase().trim();
  cleaned = cleaned.replace(/\.(SS|SZ|SH|HK)$/i, '');
  return cleaned.replace(/[^A-Z0-9]/g, '');
}

function normalizeSearchInput(value: string) {
  return value.replace(/[^\u4e00-\u9fffA-Za-z0-9.\s-]/g, '').trimStart();
}

function Shell({
  page,
  setPage,
  dark,
  setDark,
  onLogout,
  children,
}: {
  page: Page;
  setPage: (page: Page) => void;
  dark: boolean;
  setDark: (dark: boolean) => void;
  onLogout: () => void;
  children: React.ReactNode;
}) {
  const items = [
    { key: 'research' as const, label: '研究台', icon: BarChart3 },
    { key: 'chat' as const, label: '对话', icon: MessageSquareQuote },
    { key: 'history' as const, label: '历史', icon: History },
    { key: 'settings' as const, label: '设置', icon: Settings2 },
  ];

  return (
    <div className="app-shell">
      <aside className="side-nav">
        <div className="brand-mark">
          <Activity size={22} />
          <span>TA</span>
        </div>
        <nav>
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                className={cx('nav-item', page === item.key && 'active')}
                onClick={() => setPage(item.key)}
                aria-label={item.label}
              >
                <Icon size={20} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="nav-footer">
          <button className="icon-button" onClick={() => setDark(!dark)} aria-label="切换主题">
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button className="icon-button" aria-label="退出登录" onClick={onLogout}>
            <LogOut size={18} />
          </button>
        </div>
      </aside>
      <main className="page-frame">{children}</main>
    </div>
  );
}

function ResearchPage({
  runs,
  activeRun,
  runView,
  onStart,
  onSelectRun,
  onDeleteRun,
  onExportRun,
  onQuoteRun,
}: {
  runs: RunSummary[];
  activeRun: RunSummary | null;
  runView: RunView | null;
  onStart: (payload: AnalysisRequest) => void;
  onSelectRun: (run: RunSummary) => void;
  onDeleteRun: (run: RunSummary) => void;
  onExportRun: (run: RunSummary) => void;
  onQuoteRun: (run: RunSummary) => void;
}) {
  const [ticker, setTicker] = useState('');
  const [selectedCompany, setSelectedCompany] = useState<CompanySuggestion | null>(null);
  const [suggestions, setSuggestions] = useState<CompanySuggestion[]>([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [highlightedSuggestion, setHighlightedSuggestion] = useState(-1);
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [depth, setDepth] = useState(1);
  const [analysts, setAnalysts] = useState(['market', 'social', 'news', 'fundamentals']);
  const [showFullConversation, setShowFullConversation] = useState(false);
  const reportStreamRef = useRef<HTMLDivElement | null>(null);

  const toggleAnalyst = (key: string) => {
    setAnalysts((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key]);
  };

  const isCompletedRun = activeRun?.status === 'completed' || runView?.status === 'completed';
  const timelineEvents = useMemo(() => {
    if (!runView) return [];
    if (isCompletedRun && !showFullConversation) return getConclusionEvents(runView);
    return getTimelineEvents(runView);
  }, [isCompletedRun, runView, showFullConversation]);

  useEffect(() => {
    setShowFullConversation(false);
  }, [activeRun?.id]);

  useEffect(() => {
    if (reportStreamRef.current) {
      reportStreamRef.current.scrollTop = 0;
    }
  }, [activeRun?.id, showFullConversation]);

  useEffect(() => {
    const query = ticker.trim();
    if (!query) {
      setSelectedCompany(null);
      setSuggestions([]);
      setSuggestionsOpen(false);
      return;
    }
    let cancelled = false;
    const timeout = window.setTimeout(() => {
      void api.searchCompanies(query)
        .then((result) => {
          if (cancelled) return;
          setSuggestions(result.items);
          setSuggestionsOpen(result.items.length > 0);
          setHighlightedSuggestion(-1);
          setSelectedCompany((current) => {
            if (current && result.items.some((item) => item.ticker === current.ticker)) {
              return current;
            }
            return result.items[0] ?? null;
          });
        })
        .catch(() => {
          if (cancelled) return;
          setSelectedCompany(null);
          setSuggestions([]);
          setSuggestionsOpen(false);
        });
    }, 450);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [ticker]);

  const selectSuggestion = (suggestion: CompanySuggestion) => {
    const nextTicker = suggestion.ticker ?? suggestion.code ?? '';
    setTicker(nextTicker);
    setSelectedCompany(suggestion);
    setSuggestionsOpen(false);
  };

  const searchValue = ticker.trim().toLowerCase();
  const selectedMatchesInput = selectedCompany ? [
    selectedCompany.ticker,
    selectedCompany.code,
    selectedCompany.company_name,
  ].some((value) => {
    const normalized = value?.toLowerCase();
    return Boolean(normalized && (normalized.includes(searchValue) || searchValue.includes(normalized)));
  }) : false;
  const submitTicker = selectedMatchesInput ? selectedCompany?.ticker ?? sanitizeTickerInput(ticker) : sanitizeTickerInput(ticker);
  const submitCompanyName = selectedMatchesInput ? selectedCompany?.company_name ?? undefined : undefined;

  return (
    <div className="workspace-grid">
      <section className="main-column">
        <div className="composer glass-card">
          <div className="field-row">
            <label className="stock-search-field">
              <span>股票代码或名称</span>
              <div className="stock-search">
                <input
                  value={ticker}
                  onChange={(event) => setTicker(normalizeSearchInput(event.target.value))}
                  onFocus={() => setSuggestionsOpen(suggestions.length > 0)}
                  onBlur={() => window.setTimeout(() => setSuggestionsOpen(false), 180)}
                  onKeyDown={(event) => {
                    if (!suggestionsOpen || suggestions.length === 0) return;
                    if (event.key === 'ArrowDown') {
                      event.preventDefault();
                      setHighlightedSuggestion((index) => index >= suggestions.length - 1 ? 0 : index + 1);
                    }
                    if (event.key === 'ArrowUp') {
                      event.preventDefault();
                      setHighlightedSuggestion((index) => index <= 0 ? suggestions.length - 1 : index - 1);
                    }
                    if (event.key === 'Enter' && highlightedSuggestion >= 0) {
                      event.preventDefault();
                      selectSuggestion(suggestions[highlightedSuggestion]);
                    }
                    if (event.key === 'Escape') {
                      setSuggestionsOpen(false);
                    }
                  }}
                  placeholder="输入 688160、寒武纪、NVDA、英伟达"
                  inputMode="text"
                  autoCapitalize="characters"
                  role="combobox"
                  aria-expanded={suggestionsOpen}
                />
                {suggestionsOpen ? (
                  <div className="stock-suggestions" role="listbox">
                    {suggestions.map((suggestion, index) => (
                      <button
                        key={`${suggestion.ticker}-${suggestion.company_name}`}
                        type="button"
                        className={cx('stock-suggestion', highlightedSuggestion === index && 'active')}
                        onMouseEnter={() => setHighlightedSuggestion(index)}
                        onMouseDown={(event) => {
                          event.preventDefault();
                          selectSuggestion(suggestion);
                        }}
                      >
                        <span className="market-pill">{suggestion.market ?? '市场'}</span>
                        <span>
                          <strong>{suggestion.company_name ?? suggestion.ticker}</strong>
                          <small>{suggestion.ticker ?? suggestion.code}</small>
                        </span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </label>
            <label>
              <span>分析日期</span>
              <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
            </label>
            <label>
              <span>研究深度</span>
              <select value={depth} onChange={(event) => setDepth(Number(event.target.value))}>
                {researchDepthOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <button
              className="btn-primary"
              onClick={() => onStart({
                ticker: submitTicker,
                company_name: submitCompanyName,
                analysis_date: date,
                analysts,
                research_depth: depth,
                output_language: 'Chinese',
                checkpoint_enabled: false,
                use_mock_stream: false,
              })}
              disabled={!submitTicker.trim()}
            >
              <Play size={16} /> 开始研究
            </button>
          </div>
          <div className="chip-row">
            {[
              ['market', '市场'],
              ['social', '社媒'],
              ['news', '新闻'],
              ['fundamentals', '基本面'],
            ].map(([key, label]) => (
              <label key={key} className={cx('check-chip', analysts.includes(key) && 'selected')}>
                <input type="checkbox" checked={analysts.includes(key)} onChange={() => toggleAnalyst(key)} />
                {label}
              </label>
            ))}
          </div>
        </div>

        <div className="result-panel glass-card">
          <PanelHeader title={activeRun ? activeRun.title : '研究结果'} subtitle={runView ? `状态：${formatStatus(runView.status)}` : '等待启动研究'} />
          {runView ? (
            <>
            {isCompletedRun ? (
              <div className="result-toolbar">
                <span>{showFullConversation ? '正在查看完整对话' : '默认仅展示最终结论'}</span>
                <button className="btn-secondary compact" onClick={() => setShowFullConversation((value) => !value)}>
                  {showFullConversation ? '收起完整对话' : '查看完整对话'}
                </button>
              </div>
            ) : null}
            <div className="report-layout">
              <DecisionCard view={runView} />
              <div className="report-stream" ref={reportStreamRef}>
                {timelineEvents.length > 0 ? (
                  timelineEvents.map((event) => (
                    <AnalysisEventCard key={event.id} event={event} />
                  ))
                ) : (
                  <Empty title="分析正在排队" description="启动后会在这里显示最新的阶段报告。" />
                )}
              </div>
            </div>
            </>
          ) : (
            <Empty title="开始一次研究" description="运行结果、报告摘要和最终决策会在这里实时出现。" />
          )}
        </div>
      </section>

      <aside className="right-rail">
        <TaskRail runs={runs} activeRun={activeRun} onSelectRun={onSelectRun} onDeleteRun={onDeleteRun} onExportRun={onExportRun} onQuoteRun={onQuoteRun} />
        <AgentTimeline view={runView} />
      </aside>
    </div>
  );
}

function formatPayloadArgs(payload: Record<string, unknown>) {
  const args = payload.args;
  if (!args || typeof args !== 'object') return '';
  try {
    return JSON.stringify(args, null, 2);
  } catch {
    return String(args);
  }
}

function AnalysisEventCard({ event }: { event: RunEvent }) {
  const time = new Date(event.createdAt).toLocaleTimeString();
  if (event.type === 'tool_call') {
    const args = formatPayloadArgs(event.payload);
    return (
      <article className="timeline-card tool-card">
        <div className="report-meta">
          <span>工具调用 · {event.content}</span>
          <small>{time}</small>
        </div>
        {args ? <pre>{args}</pre> : <p>正在获取数据...</p>}
      </article>
    );
  }

  if (event.type === 'message') {
    return (
      <article className="timeline-card message-card">
        <div className="report-meta">
          <span>模型消息</span>
          <small>{time}</small>
        </div>
        <Markdown remarkPlugins={[remarkGfm]}>{event.content ?? ''}</Markdown>
      </article>
    );
  }

  if (event.type === 'report') {
    return (
      <article className="timeline-card markdown-card">
        <div className="report-meta">
          <span>{formatAgent(event.agent ?? 'Agent')}</span>
          <small>{time}</small>
        </div>
        <Markdown remarkPlugins={[remarkGfm]}>{event.content ?? ''}</Markdown>
      </article>
    );
  }

  if (event.type === 'decision') {
    return (
      <article className="timeline-card decision-event-card">
        <div className="report-meta">
          <span>最终组合决策</span>
          <small>{time}</small>
        </div>
        <Markdown remarkPlugins={[remarkGfm]}>{event.content ?? ''}</Markdown>
      </article>
    );
  }

  return (
    <article className="timeline-card status-event-card">
      <div className="report-meta">
        <span>运行状态</span>
        <small>{time}</small>
      </div>
      <p>{event.content ?? formatStatus(event.status ?? '')}</p>
    </article>
  );
}

function ChatPage({
  runs,
  selectedRun,
  runView,
  onSelectRun,
}: {
  runs: RunSummary[];
  selectedRun: RunSummary | null;
  runView: RunView | null;
  onSelectRun: (run: RunSummary) => void;
}) {
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const reports = runView ? Object.values(runView.reports) : [];
  const decision = runView?.decision?.label ?? selectedRun?.decision ?? '暂无结论';

  const sendQuestion = () => {
    const cleaned = question.trim();
    if (!cleaned || !selectedRun) return;
    setMessages((current) => [
      ...current,
      { role: 'user', content: cleaned },
      {
        role: 'assistant',
        content: `已引用「${displayRunName(selectedRun)}」的研究记录。当前结论：${decision}。\n\n完整追问生成需要接入后续对话模型接口；你可以先在左侧研究记录中切换引用对象。`,
      },
    ]);
    setQuestion('');
  };

  return (
    <div className="chat-page glass-card">
      <PanelHeader title="研究追问" subtitle="选择一条研究任务或历史记录后，再基于完整事件和结论继续提问" />
      <div className="chat-context-bar">
        <select value={selectedRun?.id ?? ''} onChange={(event) => {
          const run = runs.find((item) => item.id === event.target.value);
          if (run) onSelectRun(run);
        }}>
          <option value="">选择要引用的研究记录</option>
          {runs.map((run) => <option key={run.id} value={run.id}>{displayRunName(run)} · {run.analysis_date}</option>)}
        </select>
      </div>
      <div className="chat-scroll">
        {!selectedRun ? (
          <Empty title="请选择研究记录" description="这个模块用于引用某次研究结果后继续追问，不会默认绑定当前研究。" />
        ) : (
          <>
            <div className="message ai"><span>AI</span><div><small>引用对象</small><p>{displayRunName(selectedRun)}，分析日期 {selectedRun.analysis_date}，当前结论：{decision}</p></div></div>
            {reports.map((report) => (
              <div key={report.section} className="message ai">
                <span>AI</span>
                <div>
                  <small>{formatAgent(report.agent)}</small>
                  <Markdown remarkPlugins={[remarkGfm]}>{report.content}</Markdown>
                </div>
              </div>
            ))}
            {messages.map((message, index) => (
              <div key={`${message.role}-${index}`} className={cx('message', message.role === 'user' ? 'user' : 'ai')}>
                <span>{message.role === 'user' ? 'U' : 'AI'}</span>
                <p>{message.content}</p>
              </div>
            ))}
          </>
        )}
      </div>
      <div className="chat-input">
        <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="例如：基于这次研究，继续分析最大的下行风险是什么？" rows={1} />
        <button className="btn-primary" disabled={!selectedRun || !question.trim()} onClick={sendQuestion}>发送</button>
      </div>
    </div>
  );
}

function HistoryPage({
  runs,
  onSelectRun,
  onDeleteRun,
  onExportRun,
  onQuoteRun,
}: {
  runs: RunSummary[];
  onSelectRun: (run: RunSummary) => void;
  onDeleteRun: (run: RunSummary) => void;
  onExportRun: (run: RunSummary) => void;
  onQuoteRun: (run: RunSummary) => void;
}) {
  return (
    <div className="glass-card page-card">
      <PanelHeader title="历史研究" subtitle="回看每次分析的状态、日期和最终判断" />
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>公司</th><th>代码</th><th>日期</th><th>状态</th><th>决策</th><th>创建时间</th><th /></tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id}>
                <td>{run.company_name ?? '自动识别中'}</td>
                <td className="ticker">{run.ticker}</td>
                <td>{run.analysis_date}</td>
                <td><StatusBadge status={run.status} /></td>
                <td>{run.decision ?? '-'}</td>
                <td>{new Date(run.created_at).toLocaleString()}</td>
                <td>
                  <div className="row-actions">
                    <button className="icon-action" title="查看" onClick={() => onSelectRun(run)}><ChevronRight size={15} /></button>
                    <button className="icon-action" title="追问" onClick={() => onQuoteRun(run)}><MessageSquareQuote size={15} /></button>
                    <button className="icon-action" title="导出" onClick={() => onExportRun(run)}><Download size={15} /></button>
                    <button className="icon-action danger" title="删除" onClick={() => onDeleteRun(run)}><Trash2 size={15} /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SettingsPage() {
  const [settings, setSettings] = useState<SettingsPayload>(defaultSettings);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState('');

  useEffect(() => {
    void api.getSettings().then((response) => {
      setSettings(response.settings);
      setApiKeys(response.api_keys);
    });
  }, []);

  const save = async () => {
    await api.saveSettings(settings);
    setSaved('配置已保存');
    window.setTimeout(() => setSaved(''), 2500);
  };

  return (
    <div className="settings-grid">
      <aside className="settings-nav glass-card">
        {[
          ['模型配置', Bot],
          ['API Key', KeyRound],
          ['数据源', Database],
          ['鉴权安全', ShieldCheck],
        ].map(([label, Icon]) => {
          const TypedIcon = Icon as typeof Bot;
          return <button key={String(label)} className="settings-nav-item"><TypedIcon size={18} />{String(label)}</button>;
        })}
      </aside>
      <section className="settings-content">
        <div className="glass-card settings-section">
          <PanelHeader title="模型配置" subtitle="管理 TradingAgents 的服务商、深度模型、快速模型和运行参数" />
          <div className="settings-form">
            <label><span>服务商</span><input value={settings.llm_provider} onChange={(e) => setSettings({ ...settings, llm_provider: e.target.value })} /></label>
            <label><span>深度思考模型</span><input value={settings.deep_think_llm} onChange={(e) => setSettings({ ...settings, deep_think_llm: e.target.value })} /></label>
            <label><span>快速思考模型</span><input value={settings.quick_think_llm} onChange={(e) => setSettings({ ...settings, quick_think_llm: e.target.value })} /></label>
            <label><span>接口地址</span><input value={settings.backend_url ?? ''} onChange={(e) => setSettings({ ...settings, backend_url: e.target.value || null })} /></label>
          </div>
          <div className="action-row">
            <button className="btn-primary" onClick={save}><SlidersHorizontal size={16} /> 保存配置</button>
            {saved ? <span className="success-text">{saved}</span> : null}
          </div>
        </div>
        <div className="glass-card settings-section">
          <PanelHeader title="API Key 保险箱" subtitle="密钥只显示脱敏值；保存后写入当前服务进程环境变量" />
          <div className="key-grid">
            {Object.entries(apiKeys).map(([provider, masked]) => (
              <ApiKeyRow key={provider} provider={provider} masked={masked} onSaved={(next) => setApiKeys({ ...apiKeys, [provider]: next })} />
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function ApiKeyRow({ provider, masked, onSaved }: { provider: string; masked: string; onSaved: (masked: string) => void }) {
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <div className="key-row">
      <div>
        <strong>{provider}</strong>
        <small>{masked || '未配置'}</small>
      </div>
      <input type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder="输入新的 API Key" />
      <button
        className="btn-secondary compact"
        disabled={!value || busy}
        onClick={async () => {
          setBusy(true);
          const result = await api.saveApiKey(provider, value);
          onSaved(result.masked);
          setValue('');
          setBusy(false);
        }}
      >保存</button>
    </div>
  );
}

function SettingsPageFixed() {
  const [settings, setSettings] = useState<SettingsPayload>(defaultSettings);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState('');
  const [activeCategory, setActiveCategory] = useState<SettingsCategory>('models');
  const visible = getSettingsSectionVisibility(activeCategory);

  useEffect(() => {
    void api.getSettings().then((response) => {
      setSettings(response.settings);
      setApiKeys(response.api_keys);
    });
  }, []);

  const save = async () => {
    await api.saveSettings(settings);
    setSaved('设置已保存');
    window.setTimeout(() => setSaved(''), 2500);
  };

  const categories: Array<{ key: SettingsCategory; label: string; icon: typeof Bot; description: string }> = [
    { key: 'models', label: '模型配置', icon: Bot, description: '服务商与运行模型' },
    { key: 'apiKeys', label: 'API Key', icon: KeyRound, description: '密钥保险箱' },
    { key: 'data', label: '数据源', icon: Database, description: '行情与新闻供应商' },
    { key: 'auth', label: '用户鉴权', icon: ShieldCheck, description: '访问控制设置' },
  ];

  return (
    <div className="settings-grid">
      <aside className="settings-nav glass-card">
        {categories.map(({ key, label, icon: Icon, description }) => (
          <button
            key={key}
            type="button"
            className={cx('settings-nav-item', activeCategory === key && 'active')}
            onClick={() => setActiveCategory(key)}
            aria-pressed={activeCategory === key}
          >
            <Icon size={18} />
            <span>
              <strong>{label}</strong>
              <small>{description}</small>
            </span>
          </button>
        ))}
      </aside>

      <section className="settings-content">
        {visible.models ? (
          <div className="glass-card settings-section">
            <PanelHeader title="模型配置" subtitle="管理服务商、深度模型、快速模型和运行参数。" />
            <div className="settings-form">
              <label><span>服务商</span><input value={settings.llm_provider} onChange={(e) => setSettings({ ...settings, llm_provider: e.target.value })} /></label>
              <label><span>深度思考模型</span><input value={settings.deep_think_llm} onChange={(e) => setSettings({ ...settings, deep_think_llm: e.target.value })} /></label>
              <label><span>快速思考模型</span><input value={settings.quick_think_llm} onChange={(e) => setSettings({ ...settings, quick_think_llm: e.target.value })} /></label>
              <label><span>接口地址</span><input value={settings.backend_url ?? ''} onChange={(e) => setSettings({ ...settings, backend_url: e.target.value || null })} /></label>
            </div>
            <div className="action-row">
              <button className="btn-primary" onClick={save}><SlidersHorizontal size={16} /> 保存设置</button>
              {saved ? <span className="success-text">{saved}</span> : null}
            </div>
          </div>
        ) : null}

        {visible.apiKeys ? (
          <div className="glass-card settings-section">
            <PanelHeader title="API Key 保险箱" subtitle="密钥仅显示脱敏值；保存后会写入当前 API 进程环境变量。" />
            <div className="key-grid">
              {Object.entries(apiKeys).map(([provider, masked]) => (
                <ApiKeyRow key={provider} provider={provider} masked={masked} onSaved={(next) => setApiKeys({ ...apiKeys, [provider]: next })} />
              ))}
            </div>
          </div>
        ) : null}

        {visible.data ? (
          <div className="glass-card settings-section">
            <PanelHeader title="数据源" subtitle="选择价格数据、技术指标、基本面和新闻的供应商。" />
            <div className="settings-form">
              {Object.entries(settings.data_vendors).map(([key, value]) => (
                <label key={key}>
                  <span>{formatVendor(key)}</span>
                  <select
                    value={value}
                    onChange={(event) => setSettings({
                      ...settings,
                      data_vendors: { ...settings.data_vendors, [key]: event.target.value },
                    })}
                  >
                    <option value="yfinance">yfinance</option>
                    <option value="alpha_vantage">alpha_vantage</option>
                  </select>
                </label>
              ))}
            </div>
            <div className="action-row">
              <button className="btn-primary" onClick={save}><SlidersHorizontal size={16} /> 保存数据源</button>
              {saved ? <span className="success-text">{saved}</span> : null}
            </div>
          </div>
        ) : null}

        {visible.auth ? (
          <div className="glass-card settings-section">
            <PanelHeader title="用户鉴权" subtitle="本地 MVP 鉴权已在 API 边界启用，后续可以继续补充角色管理。" />
            <div className="auth-placeholder">
              <ShieldCheck size={28} />
              <h3>本地访问模式</h3>
              <p>当前网页版使用轻量本地会话。API 已提供登录、退出和鉴权状态接口，下一步可以接入完整用户体系。</p>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function PanelHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="panel-header">
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
    </div>
  );
}

function TaskRail({
  runs,
  activeRun,
  onSelectRun,
  onDeleteRun,
  onExportRun,
  onQuoteRun,
}: {
  runs: RunSummary[];
  activeRun: RunSummary | null;
  onSelectRun: (run: RunSummary) => void;
  onDeleteRun: (run: RunSummary) => void;
  onExportRun: (run: RunSummary) => void;
  onQuoteRun: (run: RunSummary) => void;
}) {
  return (
    <div className="glass-card rail-card">
      <PanelHeader title="任务与历史" subtitle={`${runs.length} 条研究记录`} />
      <div className="run-list">
        {runs.length === 0 ? <Empty title="暂无历史" description="启动研究后会自动记录。" compact /> : runs.map((run) => (
          <div key={run.id} className={cx('run-item', activeRun?.id === run.id && 'active')} role="button" tabIndex={0} onClick={() => onSelectRun(run)} onKeyDown={(event) => event.key === 'Enter' && onSelectRun(run)}>
            <span className="run-indicator" />
            <span><strong>{displayRunName(run)}</strong><small>{run.analysis_date} · {formatStatus(run.status)}</small></span>
            <div className="run-actions" onClick={(event) => event.stopPropagation()}>
              <button className="icon-action" title="追问" onClick={() => onQuoteRun(run)}><MessageSquareQuote size={14} /></button>
              <button className="icon-action" title="导出" onClick={() => onExportRun(run)}><Download size={14} /></button>
              <button className="icon-action danger" title="删除" onClick={() => onDeleteRun(run)}><Trash2 size={14} /></button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AgentTimeline({ view }: { view: RunView | null }) {
  return (
    <div className="glass-card rail-card">
      <PanelHeader title="智能体进度" subtitle="团队状态实时更新" />
      <div className="agent-groups">
        {AGENT_GROUPS.map((group) => (
          <div key={group.team} className="agent-group">
            <h3>{group.label}</h3>
            {group.agents.map((agent) => {
              const status = view?.agentStatuses[agent] ?? 'pending';
              return (
                <div key={agent} className="agent-row">
                  {status === 'completed' ? <CheckCircle2 size={15} /> : status === 'running' ? <RefreshCw size={15} className="spin" /> : <Circle size={15} />}
                  <span>{formatAgent(agent)}</span>
                  <small>{formatStatus(status)}</small>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function DecisionCard({ view }: { view: RunView }) {
  return (
    <div className="decision-card">
      <p className="eyebrow">组合决策</p>
      <h3>{view.decision?.label ?? '等待最终决策'}</h3>
      <div className="metric-row">
        <span>置信度</span><strong>{view.decision?.confidence ? `${Math.round(view.decision.confidence * 100)}%` : '--'}</strong>
      </div>
      <div className="metric-row">
        <span>风险</span><strong>{view.decision?.risk ?? '--'}</strong>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  return <span className={cx('status-badge', status)}>{formatStatus(status)}</span>;
}

function Empty({ title, description, compact = false }: { title: string; description: string; compact?: boolean }) {
  return (
    <div className={cx('empty-state', compact && 'compact')}>
      <Bot size={compact ? 20 : 28} />
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('admin');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      await api.login(username, password);
      onLogin();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : '登录失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-screen">
      <div className="glass-card login-card">
        <PanelHeader title="登录 TradingAgents" subtitle="默认本地账号为 admin / admin，可通过环境变量修改" />
        <label><span>用户名</span><input value={username} onChange={(event) => setUsername(event.target.value)} /></label>
        <label><span>密码</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        {error ? <p className="error-text">{error}</p> : null}
        <button className="btn-primary" disabled={busy || !username || !password} onClick={submit}>登录</button>
      </div>
    </div>
  );
}

function App() {
  const [page, setPage] = useState<Page>('research');
  const [dark, setDark] = useState(() => localStorage.getItem('tradingagents-theme') !== 'light');
  const [authChecked, setAuthChecked] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [activeRun, setActiveRun] = useState<RunSummary | null>(null);
  const [runView, setRunView] = useState<RunView | null>(null);
  const [chatRun, setChatRun] = useState<RunSummary | null>(null);
  const [chatRunView, setChatRunView] = useState<RunView | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('tradingagents-theme', dark ? 'dark' : 'light');
  }, [dark]);

  useEffect(() => {
    void api.authStatus().then((status) => setLoggedIn(status.logged_in)).finally(() => setAuthChecked(true));
  }, []);

  useEffect(() => {
    if (!loggedIn) return;
    void api.listRuns().then((response) => setRuns(response.runs)).catch(() => undefined);
  }, [loggedIn]);

  const loadRun = async (run: RunSummary, target: 'research' | 'chat' = 'research') => {
    const detail = await api.getRun(run.id);
    const view = buildRunView(run.id, detail.events);
    if (target === 'chat') {
      setChatRun(detail.run);
      setChatRunView(view);
      setPage('chat');
      return;
    }
    setActiveRun(detail.run);
    setRunView(view);
    setPage('research');
  };

  const startRun = async (payload: AnalysisRequest) => {
    const response = await api.createRun(payload);
    setActiveRun(response.run);
    setRuns((current) => [response.run, ...current.filter((item) => item.id !== response.run.id)]);
    setRunView(createRunView(response.run.id));
    const source = api.openRunEvents(response.run.id);
    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as RunEvent;
      setRunView((current) => reduceRunEvent(current ?? createRunView(response.run.id), event));
      if (event.type === 'run_status' && event.status) {
        setActiveRun((current) => current?.id === response.run.id ? { ...current, status: event.status ?? current.status, updated_at: event.createdAt } : current);
        setRuns((current) => current.map((item) => item.id === response.run.id ? { ...item, status: event.status ?? item.status, updated_at: event.createdAt } : item));
      }
      if (event.type === 'decision' && event.content) {
        setActiveRun((current) => current?.id === response.run.id ? { ...current, decision: event.content } : current);
        setRuns((current) => current.map((item) => item.id === response.run.id ? { ...item, decision: event.content } : item));
      }
      if (event.type === 'run_status' && event.status === 'completed') {
        source.close();
        void api.listRuns().then((next) => setRuns(next.runs));
      }
    };
    source.addEventListener('close', () => source.close());
  };

  const selectRun = (run: RunSummary) => {
    void loadRun(run, 'research');
  };

  const quoteRun = (run: RunSummary) => {
    void loadRun(run, 'chat');
  };

  const deleteRun = async (run: RunSummary) => {
    if (!window.confirm(`确认删除「${displayRunName(run)}」这条研究记录吗？`)) return;
    await api.deleteRun(run.id);
    setRuns((current) => current.filter((item) => item.id !== run.id));
    if (activeRun?.id === run.id) {
      setActiveRun(null);
      setRunView(null);
    }
    if (chatRun?.id === run.id) {
      setChatRun(null);
      setChatRunView(null);
    }
  };

  const exportRun = async (run: RunSummary) => {
    const content = await api.exportRun(run.id);
    downloadTextFile(`${run.ticker}-${run.analysis_date}-研究报告.md`, content);
  };

  const logout = async () => {
    await api.logout();
    setLoggedIn(false);
    setActiveRun(null);
    setRunView(null);
    setChatRun(null);
    setChatRunView(null);
  };

  if (!authChecked) {
    return <div className="login-screen"><div className="glass-card login-card"><Empty title="正在检查登录状态" description="请稍候..." compact /></div></div>;
  }

  if (!loggedIn) {
    return <LoginPage onLogin={() => setLoggedIn(true)} />;
  }

  return (
    <Shell page={page} setPage={setPage} dark={dark} setDark={setDark} onLogout={logout}>
      {page === 'research' ? <ResearchPage runs={runs} activeRun={activeRun} runView={runView} onStart={startRun} onSelectRun={selectRun} onDeleteRun={deleteRun} onExportRun={exportRun} onQuoteRun={quoteRun} /> : null}
      {page === 'chat' ? <ChatPage runs={runs} selectedRun={chatRun} runView={chatRunView} onSelectRun={(run) => { void loadRun(run, 'chat'); }} /> : null}
      {page === 'history' ? <HistoryPage runs={runs} onSelectRun={selectRun} onDeleteRun={deleteRun} onExportRun={exportRun} onQuoteRun={quoteRun} /> : null}
      {page === 'settings' ? <SettingsPageFixed /> : null}
    </Shell>
  );
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
