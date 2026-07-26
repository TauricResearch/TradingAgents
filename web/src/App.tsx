import { useEffect, useMemo, useReducer, useState } from 'react'
import {
  AlertTriangle, ArchiveRestore, Check, DatabaseBackup, Download, Gauge, GitCompareArrows,
  History, Languages, Menu, MessageSquare, Play, RefreshCw, RotateCcw, Send, ShieldCheck, Square, X,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { useTranslation } from 'react-i18next'
import { Area, AreaChart, CartesianGrid, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  cancelAnalysis, commitRestore, createAnalysis, createBackup, createConversation, getAnalysis,
  getOptions, getTrust, getUsage, listAnalyses, listBackups, listVersions, previewRestore,
  reevaluate, resolveInstrument, retryAnalysis, sendMessage,
  resumeAnalysis,
} from './api'
import { analysisReducer, initialAnalysisState } from './analysisReducer'
import ChinaFunds from './ChinaFunds'
import { setUiLanguage } from './i18n'
import type {
  AdviceVersion, AnalysisEvent, AnalysisJob, AssetMode, BackupPreview, ConversationMessage,
  Instrument, Metric, Snapshot, TrustAssessment, UsageSummary,
} from './types'

const analysts = ['market', 'social', 'news', 'fundamentals']
const agentOrder = ['Market Analyst', 'Sentiment Analyst', 'News Analyst', 'Fundamentals Analyst']
const tabs = ['overview', 'reports', 'debate', 'decision', 'chinaFunds', 'history', 'quality', 'usage', 'advice', 'chat', 'backup'] as const
type Tab = typeof tabs[number]
const eventTypes = ['analysis.started', 'agent.started', 'agent.completed', 'agent.skipped', 'report.updated', 'analysis.completed', 'analysis.failed', 'analysis.cancelled', 'analysis.interrupted', 'analysis.budget_exhausted', 'analysis.provider_rate_limited', 'analysis.provider_timed_out']
const terminal = ['completed', 'failed', 'cancelled', 'interrupted', 'budget_exhausted', 'provider_rate_limited', 'provider_timed_out']

function today() { return new Date().toISOString().slice(0, 10) }
function humanize(value: string) { return value.replaceAll('_', ' ') }
function pct(value: number | null | undefined) { return value == null ? 'N/A' : `${(value * 100).toFixed(1)}%` }
function locale(language: string) { return language.startsWith('zh') ? 'zh-CN' : 'en-US' }

export default function App() {
  const { t, i18n } = useTranslation()
  const [mode, setMode] = useState<AssetMode>('auto')
  const [symbol, setSymbol] = useState('SPY')
  const [date, setDate] = useState(today())
  const [benchmark, setBenchmark] = useState('SPY')
  const [selected, setSelected] = useState(['market', 'social', 'news', 'fundamentals'])
  const [provider, setProvider] = useState('openai')
  const [quickModel, setQuickModel] = useState('gpt-5.4-mini')
  const [deepModel, setDeepModel] = useState('gpt-5.5')
  const [depth, setDepth] = useState(1)
  const [outputLanguage, setOutputLanguage] = useState('English')
  const [instrument, setInstrument] = useState<Instrument>()
  const [resolveError, setResolveError] = useState('')
  const [resolving, setResolving] = useState(false)
  const [tab, setTab] = useState<Tab>('overview')
  const [drawer, setDrawer] = useState(false)
  const [budget, setBudget] = useState<{ limits: Record<string, number>; historical_estimate?: { requests: number; tokens: number; basis: number } | null; daily_usage: { requests: number; tokens: number } }>()
  const [state, dispatch] = useReducer(analysisReducer, initialAnalysisState)

  const active = ['queued', 'running', 'cancelling'].includes(state.status)
  const snapshot = state.result?.fund_snapshot

  useEffect(() => { getOptions().then(value => setBudget(value.budget)).catch(() => undefined) }, [])
  useEffect(() => {
    if (!state.jobId || !['queued', 'running', 'cancelling'].includes(state.status)) return
    const source = new EventSource(`/api/analyses/${state.jobId}/events`)
    source.onopen = () => dispatch({ type: 'connected', value: true })
    source.onerror = () => {
      dispatch({ type: 'connected', value: false })
      if (!terminal.includes(state.status)) source.close()
    }
    for (const type of eventTypes) {
      source.addEventListener(type, (raw) => dispatch({ type: 'event', event: JSON.parse((raw as MessageEvent).data) as AnalysisEvent }))
    }
    return () => source.close()
  }, [state.jobId, state.status])
  useEffect(() => {
    if (!state.jobId || !['queued', 'running', 'cancelling'].includes(state.status)) return
    const jobId = state.jobId
    const timer = window.setInterval(() => {
      getAnalysis(jobId).then(job => {
        if (terminal.includes(job.status)) dispatch({ type: 'loaded', job })
      }).catch(() => undefined)
    }, 400)
    return () => window.clearInterval(timer)
  }, [state.jobId, state.status])

  async function resolve() {
    setResolving(true); setResolveError('')
    try { setInstrument(await resolveInstrument(symbol, mode)) }
    catch (error) { setInstrument(undefined); setResolveError(error instanceof Error ? error.message : t('Unable to resolve symbol')) }
    finally { setResolving(false) }
  }

  async function start() {
    if (!selected.length) return
    try {
      const job = await createAnalysis({ symbol: instrument?.canonical_symbol ?? symbol, asset_type: mode, analysis_date: date, benchmark_symbol: benchmark, analysts: selected, research_depth: depth, llm_provider: provider, quick_model: quickModel, deep_model: deepModel, output_language: outputLanguage })
      dispatch({ type: 'created', jobId: job.job_id }); setDrawer(false); setTab('overview')
    } catch (error) { dispatch({ type: 'error', message: error instanceof Error ? error.message : t('Unable to start analysis') }) }
  }

  async function cancel() {
    if (!state.jobId) return
    dispatch({ type: 'cancelling' })
    try { await cancelAnalysis(state.jobId) } catch (error) { dispatch({ type: 'error', message: error instanceof Error ? error.message : t('Cancellation failed') }) }
  }

  async function retry(jobId = state.jobId) {
    if (!jobId) return
    try {
      const job = await retryAnalysis(jobId)
      dispatch({ type: 'created', jobId: job.job_id })
      setTab('overview')
    } catch (error) {
      dispatch({ type: 'error', message: error instanceof Error ? error.message : t('Retry could not be created') })
    }
  }

  async function openHistory(job: AnalysisJob) {
    const value = await getAnalysis(job.job_id)
    dispatch({ type: 'loaded', job: value })
    const request = value.request
    setSymbol(String(request.symbol ?? value.result?.company_of_interest ?? ''))
    setDate(String(request.analysis_date ?? value.result?.trade_date ?? today()))
    setBenchmark(String(request.benchmark_symbol ?? value.result?.benchmark_symbol ?? 'SPY'))
    setMode((request.asset_type as AssetMode) ?? 'auto')
    setProvider(String(request.llm_provider ?? 'openai'))
    setQuickModel(String(request.quick_model ?? 'gpt-5.4-mini'))
    setDeepModel(String(request.deep_model ?? 'gpt-5.5'))
    setDepth(Number(request.research_depth ?? 1))
    setOutputLanguage(String(request.output_language ?? 'English'))
    setTab('overview')
  }

  const reports = useMemo(() => Object.entries(state.reports), [state.reports])
  const exportReady = Boolean(state.reportId && ['completed', 'budget_exhausted'].includes(state.status))
  return <div className="app-shell">
    <header className="topbar">
      <button className="icon-button menu-button" aria-label={t('Open configuration')} title={t('Configuration')} onClick={() => setDrawer(true)}><Menu size={19}/></button>
      <div className="brand"><span className="brand-mark">TA</span><strong>TradingAgents</strong><span className="edition">{t('Research Workspace')}</span></div>
      <div className="instrument-title"><strong>{instrument?.canonical_symbol ?? state.result?.company_of_interest ?? t('No instrument')}</strong><span>{instrument?.name ?? t('Local research history and analysis')}</span></div>
      <label className="language-picker" title={t('Interface language')}><Languages size={16}/><span className="sr-only">{t('Interface language')}</span><select aria-label={t('Interface language')} value={i18n.resolvedLanguage?.startsWith('zh') ? 'zh' : 'en'} onChange={event => void setUiLanguage(event.target.value as 'en' | 'zh')}><option value="en">{t('English interface')}</option><option value="zh">{t('Chinese interface')}</option></select></label>
      <div className={`connection ${state.connected ? 'online' : ''}`}><span/>{state.connected ? t('Live') : t(`status.${state.status}`, { defaultValue: humanize(state.status) })}</div>
    </header>

    <div className="workspace">
      {drawer && <button className="drawer-backdrop" aria-label={t('Close configuration')} onClick={() => setDrawer(false)}/>}
      <aside className={`sidebar ${drawer ? 'open' : ''}`} aria-label={t('Analysis configuration')}>
        <div className="sidebar-heading"><div><span className="eyebrow">{t('Configuration')}</span><h2>{t('Analysis setup')}</h2></div><button className="icon-button drawer-close" aria-label={t('Close configuration')} onClick={() => setDrawer(false)}><X size={18}/></button></div>
        <label className="field-label">{t('Asset mode')}</label>
        <div className="segmented" role="group" aria-label={t('Asset mode')}>{(['auto','stock','fund','crypto'] as AssetMode[]).map(value => <button key={value} className={mode === value ? 'active' : ''} onClick={() => { setMode(value); setInstrument(undefined) }}>{t(`mode.${value}`)}</button>)}</div>
        <label className="field-label" htmlFor="symbol">{t('Symbol')}</label>
        <div className="resolve-row"><input id="symbol" value={symbol} onChange={event => { setSymbol(event.target.value.toUpperCase()); setInstrument(undefined) }} onKeyDown={event => event.key === 'Enter' && resolve()} /><button className="secondary-button" onClick={resolve} disabled={resolving}>{resolving ? t('Resolving') : t('Resolve')}</button></div>
        {resolveError && <p className="inline-error">{resolveError}</p>}
        {instrument && <div className="identity-block"><div><strong>{instrument.canonical_symbol}</strong><span>{instrument.asset_type}{instrument.fund_type ? ` · ${instrument.fund_type.replace('_',' ')}` : ''}</span></div><Check size={17}/><p>{instrument.name}</p><small>{[instrument.exchange, instrument.currency, instrument.quote_type].filter(Boolean).join(' · ')}</small></div>}
        <div className="field-grid"><label><span className="field-label">{t('Analysis date')}</span><input type="date" value={date} max={today()} onChange={event => setDate(event.target.value)}/></label><label><span className="field-label">{t('Benchmark')}</span><input value={benchmark} onChange={event => setBenchmark(event.target.value.toUpperCase())}/></label></div>
        <fieldset><legend>{t('Analysts')}</legend>{analysts.map(value => <label className="check-row" key={value}><input type="checkbox" checked={selected.includes(value)} onChange={() => setSelected(items => items.includes(value) ? items.filter(item => item !== value) : [...items, value])}/><span>{t(`analyst.${value}`)}</span></label>)}</fieldset>
        <div className="field-grid"><label><span className="field-label">{t('Provider')}</span><select value={provider} onChange={event => setProvider(event.target.value)}><option value="openai">OpenAI</option><option value="ciii">CIII</option><option value="ollama">Ollama</option></select></label><label><span className="field-label">{t('Depth')}</span><select value={depth} onChange={event => setDepth(Number(event.target.value))}><option value="1">{t('Quick')}</option><option value="2">{t('Standard')}</option><option value="3">{t('Deep')}</option></select></label></div>
        <div className="field-grid"><label><span className="field-label">{t('Quick model')}</span><input value={quickModel} onChange={event => setQuickModel(event.target.value)}/></label><label><span className="field-label">{t('Deep model')}</span><input value={deepModel} onChange={event => setDeepModel(event.target.value)}/></label></div>
        <label><span className="field-label">{t('Report language')}</span><select aria-label={t('Report language')} value={outputLanguage} onChange={event => setOutputLanguage(event.target.value)}><option value="English">{t('English')}</option><option value="Chinese">{t('Chinese')}</option><option value="Spanish">{t('Spanish')}</option></select></label>
        {budget && <div className="budget-brief"><span>{t('Analysis ceiling')}</span><strong>{budget.limits.max_requests_per_analysis} {t('requests')} · {budget.limits.max_total_tokens_per_analysis.toLocaleString(locale(i18n.language))} {t('tokens')}</strong><small>{budget.historical_estimate ? `${t('Typical')} ${budget.historical_estimate.requests} ${t('requests')} / ${budget.historical_estimate.tokens.toLocaleString(locale(i18n.language))} ${t('tokens')}` : t('No historical estimate yet')}</small></div>}
        <div className="sidebar-actions">{active ? <button className="danger-button" onClick={cancel}><Square size={16}/>{t('Cancel analysis')}</button> : <button className="primary-button" onClick={start} disabled={selected.length === 0}><Play size={17}/>{t('Start analysis')}</button>}</div>
      </aside>

      <main className="main-content">
        <section className="summary-band">
          <div><span>{t('Instrument')}</span><strong>{instrument?.canonical_symbol ?? state.result?.company_of_interest ?? '—'}</strong><small>{instrument?.asset_type ?? state.result?.asset_type ?? t('Not resolved')}</small></div>
          <div><span>{t('Analysis date')}</span><strong>{date}</strong><small>{t('Price cutoff')}</small></div>
          <div><span>{t('Benchmark')}</span><strong>{benchmark}</strong><small>{t('User selected')}</small></div>
          <div><span>{t('Job')}</span><strong className="capitalize">{t(`status.${state.status}`, { defaultValue: humanize(state.status) })}</strong><small>{state.jobId ? state.jobId.slice(0,8) : t('Not started')}</small></div>
        </section>

        {(resolveError || (state.error && !['provider_rate_limited', 'provider_timed_out'].includes(state.status))) && <section className="notice error-notice"><AlertTriangle size={19}/><div><strong>{state.status === 'budget_exhausted' ? t('Budget exhausted') : t('Analysis unavailable')}</strong><p>{state.error ?? resolveError}</p></div><button className="icon-button" aria-label={t('Reset error')} title={t('Reset')} onClick={() => dispatch({ type:'reset' })}><RotateCcw size={17}/></button></section>}
        {state.status === 'interrupted' && <section className="notice"><AlertTriangle size={18}/><p>{t('This run was interrupted by a service restart. It is not active and will not spend tokens automatically.')}</p></section>}
        {state.status === 'provider_rate_limited' && <ProviderRateLimitNotice value={state.providerRateLimit} onRetry={() => retry()}/>}
        {state.status === 'provider_timed_out' && <ProviderTimeoutNotice value={state.providerTimeout} onRetry={() => retry()}/>}
        {instrument?.warnings.map(warning => <section className="notice" key={warning}><AlertTriangle size={18}/><p>{warning}</p></section>)}

        <section className="progress-strip" aria-label={t('Agent progress')}>{agentOrder.map(agent => { const status = state.agents[agent] ?? (active ? 'pending' : 'idle'); return <div key={agent} className={`agent-step ${status}`}><span>{status === 'completed' ? <Check size={14}/> : ''}</span><div><strong>{t(`agent.${agent}`)}</strong><small>{t(`status.${status}`, { defaultValue: status })}</small></div></div> })}</section>

        <nav className="tabs" aria-label={t('Report views')}>{tabs.map(name => <button key={name} className={tab === name ? 'active' : ''} onClick={() => setTab(name)}>{t(`tab.${name}`)}</button>)}<a className={`export-button ${!exportReady ? 'disabled' : ''}`} aria-label={t('Download Markdown report')} title={t('Download report')} href={state.jobId ? `/api/analyses/${state.jobId}/report.md` : undefined}><Download size={17}/><span>{t('Export')}</span></a></nav>

        <section className="report-view">
          {tab === 'overview' && <Overview snapshot={snapshot} instrument={instrument} status={state.status}/>}
          {tab === 'reports' && <ReportList reports={reports.filter(([key]) => key.endsWith('_report'))}/>}
          {tab === 'debate' && <ReportList reports={reports.filter(([key]) => ['investment_plan','trader_investment_plan'].includes(key))}/>}
          {tab === 'decision' && <ReportList reports={reports.filter(([key]) => key === 'final_trade_decision')}/>}
          {tab === 'chinaFunds' && <ChinaFunds onUse={(candidate, value) => { setSymbol(candidate.code); setMode('fund'); setInstrument(value); setTab('overview') }}/>}
          {tab === 'history' && <HistoryPanel onOpen={openHistory} onRetry={jobId => retry(jobId)}/>}
          {tab === 'quality' && <TrustPanel jobId={state.jobId}/>}
          {tab === 'usage' && <UsagePanel jobId={state.jobId} budget={budget}/>}
          {tab === 'advice' && <AdvicePanel reportId={state.reportId}/>}
          {tab === 'chat' && <ChatPanel key={state.reportId ?? 'empty-chat'} reportId={state.reportId}/>}
          {tab === 'backup' && <BackupPanel/>}
        </section>
      </main>
    </div>
  </div>
}

function ProviderRateLimitNotice({ value, onRetry }: { value?: import('./types').ProviderRateLimitError; onRetry: () => Promise<void> }) {
  const { t } = useTranslation()
  const cache = value?.cache_status === 'hit' ? t('A freshness-qualified cache entry is available.') : value?.cache_status === 'expired' ? t('A cached entry exists but is expired and was not used as current data.') : t('No freshness-qualified cache entry is available.')
  return <section className="notice error-notice"><AlertTriangle size={19}/><div><strong>{t('Yahoo Finance rate limited')}</strong><p>{value?.message ?? t('Yahoo Finance is temporarily rate limited. Try again later.')}</p><small>{cache} {t('CIII usage: 0 requests, 0 tokens, 0 retries.')}</small>{value?.retry_after && <small>{t('Provider Retry-After')}: {value.retry_after}</small>}</div><button className="secondary-button" onClick={() => void onRetry()}><RefreshCw size={16}/>{t('Retry later')}</button></section>
}

function ProviderTimeoutNotice({ value, onRetry }: { value?: import('./types').ProviderTimeoutError; onRetry: () => Promise<void> }) {
  const { t } = useTranslation()
  const cache = value?.cache_status === 'hit' ? t('A freshness-qualified cache entry is available.') : value?.cache_status === 'expired' ? t('A cached entry exists but is expired and was not used as current data.') : t('No freshness-qualified cache entry is available.')
  return <section className="notice error-notice"><AlertTriangle size={19}/><div><strong>{t('Yahoo Finance timed out')}</strong><p>{value?.message ?? t('Yahoo Finance did not respond in time. Retry when you are ready.')}</p><small>{cache} {t('Request timeout')}: {value?.timeout_seconds ?? 10}s. {t('CIII usage: 0 requests, 0 tokens, 0 retries.')}</small></div><button className="secondary-button" onClick={() => void onRetry()}><RefreshCw size={16}/>{t('Retry')}</button></section>
}

function HistoryPanel({ onOpen, onRetry }: { onOpen: (job: AnalysisJob) => Promise<void>; onRetry: (jobId: string) => Promise<void> }) {
  const { t, i18n } = useTranslation()
  const [items, setItems] = useState<AnalysisJob[]>([])
  const [error, setError] = useState('')
  useEffect(() => { listAnalyses().then(setItems).catch(value => setError(String(value))) }, [])
  async function resume(job: AnalysisJob) { try { await resumeAnalysis(job.job_id); setItems(await listAnalyses()) } catch (value) { setError(value instanceof Error ? value.message : String(value)) } }
  return <section className="tool-panel"><header><div><span className="eyebrow">{t('Persistent workspace')}</span><h2><History size={18}/>{t('Analysis history')}</h2></div><span>{items.length} {t('runs')}</span></header>{error && <p className="inline-error">{error}</p>}{items.length ? <div className="table-scroll"><table><thead><tr><th>{t('Created')}</th><th>{t('Instrument')}</th><th>{t('Status')}</th><th>{t('Recovery')}</th><th>{t('Report')}</th></tr></thead><tbody>{items.map(job => <tr key={job.job_id}><td>{new Date(job.created_at).toLocaleString(locale(i18n.language))}</td><td><strong>{String(job.request.symbol ?? '—')}</strong><small>{String(job.request.asset_type ?? '')}</small></td><td><span className={`status-badge ${job.status}`}>{t(`status.${job.status}`, { defaultValue: humanize(job.status) })}</span></td><td>{job.resumable ? <button className="text-command" onClick={() => resume(job)}>{t('Resume')}</button> : ['provider_rate_limited', 'provider_timed_out'].includes(job.status) ? <button className="text-command" onClick={() => void onRetry(job.job_id)}>{t('Retry')}</button> : <small>{job.status === 'interrupted' ? t('Not resumable') : '—'}</small>}</td><td><button className="text-command" onClick={() => onOpen(job)} disabled={!job.result}>{t('Open')}</button></td></tr>)}</tbody></table></div> : <Empty title={t('No persisted analyses')} text={t('Completed and interrupted runs appear here.')}/>}</section>
}

function TrustPanel({ jobId }: { jobId?: string }) {
  const { t, i18n } = useTranslation()
  const [trust, setTrust] = useState<TrustAssessment>()
  const [error, setError] = useState('')
  useEffect(() => { if (jobId) getTrust(jobId).then(setTrust).catch(value => setError(value instanceof Error ? value.message : String(value))) }, [jobId])
  if (!jobId) return <Empty title={t('No data quality assessment')} text={t('Open a completed analysis to inspect its evidence.')}/>
  if (!trust) return <Empty title={error || t('Loading data quality')} text={error ? t('The selected run has no persisted trust assessment.') : t('Reading persisted evidence.')}/>
  return <div className="quality-layout"><section className="trust-summary"><ShieldCheck size={24}/><div><span className="eyebrow">{t('Deterministic trust gate')}</span><h2>{t(`status.${trust.level}`, { defaultValue: humanize(trust.level) })}</h2><p>{trust.executable ? t('Eligible for an executable recommendation.') : t('Observation-only; critical or warning-level evidence prevents execution.')}</p></div><span className={`status-badge ${trust.level}`}>{trust.executable ? t('executable') : t('observation only')}</span></section><section className="tool-panel"><header><div><span className="eyebrow">{t('Reason codes')}</span><h2>{t('Assessment details')}</h2></div><span>{new Date(trust.assessed_at).toLocaleString(locale(i18n.language))}</span></header><div className="reason-list">{trust.reason_codes.length ? trust.reason_codes.map(code => <span key={code}>{code}</span>) : <span>NO_BLOCKING_REASONS</span>}</div>{trust.warnings.map(warning => <div className="notice" key={warning}><AlertTriangle size={16}/><p>{warning}</p></div>)}</section><section className="tool-panel"><header><div><span className="eyebrow">{t('Traceability')}</span><h2>{t('Evidence fields')}</h2></div><span>{trust.evidence.length} {t('fields')}</span></header><div className="table-scroll"><table><thead><tr><th>{t('Field')}</th><th>{t('Value')}</th><th>{t('Freshness')}</th><th>{t('Effective')}</th><th>{t('Source')}</th></tr></thead><tbody>{trust.evidence.map(item => <tr key={item.name}><td><strong>{item.name.replaceAll('_',' ')}</strong></td><td>{typeof item.value === 'object' ? (item.value ? t('available') : t('missing')) : String(item.value ?? t('missing'))}</td><td><span className={`status-badge ${item.freshness_status}`}>{t(`status.${item.freshness_status}`, { defaultValue: item.freshness_status })}</span></td><td>{item.effective_at ?? t('unknown')}</td><td>{item.source_reference}</td></tr>)}</tbody></table></div></section></div>
}

function UsagePanel({ jobId, budget }: { jobId?: string; budget?: { limits: Record<string, number>; historical_estimate?: { requests: number; tokens: number; basis: number } | null; daily_usage: { requests: number; tokens: number } } }) {
  const { t, i18n } = useTranslation()
  const [usage, setUsage] = useState<UsageSummary>()
  useEffect(() => { if (jobId) getUsage(jobId).then(value => setUsage(value.summary)).catch(() => setUsage(undefined)) }, [jobId])
  const values = usage ? [['Requests', usage.requests], ['Input tokens', usage.input_tokens], ['Output tokens', usage.output_tokens], ['Retries', usage.retries]] as const : []
  return <div className="quality-layout"><section className="tool-panel"><header><div><span className="eyebrow">{t('Preflight')}</span><h2><Gauge size={18}/>{t('Configured budget')}</h2></div><span>{t('Cost unknown')}</span></header>{budget ? <div className="usage-grid"><div><span>{t('Analysis requests')}</span><strong>{budget.limits.max_requests_per_analysis}</strong></div><div><span>{t('Analysis tokens')}</span><strong>{budget.limits.max_total_tokens_per_analysis.toLocaleString(locale(i18n.language))}</strong></div><div><span>{t('Daily requests used')}</span><strong>{budget.daily_usage.requests}</strong></div><div><span>{t('Daily tokens used')}</span><strong>{budget.daily_usage.tokens.toLocaleString(locale(i18n.language))}</strong></div></div> : <p className="missing">{t('Budget preflight unavailable.')}</p>}</section><section className="tool-panel"><header><div><span className="eyebrow">{t('Selected run')}</span><h2>{t('Recorded usage')}</h2></div><span>{usage?.token_usage_complete === false ? t('Token usage incomplete') : t('Provider reported')}</span></header>{usage ? <div className="usage-grid">{values.map(([label,value]) => <div key={label}><span>{t(label)}</span><strong>{Number(value).toLocaleString(locale(i18n.language))}</strong></div>)}</div> : <Empty title={t('No usage record')} text={t('Open a completed analysis or start a new run.')}/>} {usage?.warnings.map(warning => <div className="notice" key={warning}><AlertTriangle size={16}/><p>{warning}</p></div>)}</section></div>
}

function AdvicePanel({ reportId }: { reportId?: string }) {
  const { t } = useTranslation()
  const [items, setItems] = useState<AdviceVersion[]>([])
  const [left, setLeft] = useState(0)
  const [right, setRight] = useState(0)
  useEffect(() => { if (reportId) listVersions(reportId).then(values => { setItems(values); setLeft(Math.max(0, values.length - 2)); setRight(Math.max(0, values.length - 1)) }).catch(() => setItems([])) }, [reportId])
  if (!reportId) return <Empty title={t('No formal advice')} text={t('Open a completed report to compare immutable advice versions.')}/>
  if (!items.length) return <Empty title={t('Loading advice versions')} text={t('Reading the formal recommendation lineage.')}/>
  return <section className="tool-panel"><header><div><span className="eyebrow">{t('Immutable lineage')}</span><h2><GitCompareArrows size={18}/>{t('Advice version comparison')}</h2></div><span>{items.length} {t('versions')}</span></header><div className="compare-controls"><label>{t('Baseline')}<select value={left} onChange={event => setLeft(Number(event.target.value))}>{items.map((item,index) => <option value={index} key={item.id}>{t('Version')} {item.version}</option>)}</select></label><label>{t('Compare')}<select value={right} onChange={event => setRight(Number(event.target.value))}>{items.map((item,index) => <option value={index} key={item.id}>{t('Version')} {item.version}</option>)}</select></label></div><div className="version-compare"><AdviceVersionView value={items[left]}/><AdviceVersionView value={items[right]}/></div></section>
}

function AdviceVersionView({ value }: { value: AdviceVersion }) {
  const { t, i18n } = useTranslation()
  return <article><span className="eyebrow">{t('Version')} {value.version}</span><h2>{value.action}</h2><dl><dt>{t('Eligibility')}</dt><dd>{value.eligibility.replace('_',' ')}</dd><dt>{t('Confidence')}</dt><dd>{value.confidence}</dd><dt>{t('Created')}</dt><dd>{new Date(value.created_at).toLocaleString(locale(i18n.language))}</dd><dt>{t('Parent')}</dt><dd>{value.parent_id ? value.parent_id.slice(0,8) : t('Original')}</dd></dl><p>{value.reason}</p></article>
}

function ChatPanel({ reportId }: { reportId?: string }) {
  const { t } = useTranslation()
  const [conversationId, setConversationId] = useState('')
  const [messages, setMessages] = useState<ConversationMessage[]>([])
  const [content, setContent] = useState('')
  const [refresh, setRefresh] = useState(false)
  const [candidate, setCandidate] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [newVersion, setNewVersion] = useState<AdviceVersion>()
  if (!reportId) return <Empty title={t('Report Q&A unavailable')} text={t('Open a completed report before starting a persisted conversation.')}/>
  async function begin() { setBusy(true); setError(''); try { setConversationId((await createConversation(reportId!)).id) } catch (value) { setError(value instanceof Error ? value.message : String(value)) } finally { setBusy(false) } }
  async function submit() { if (!conversationId || !content.trim()) return; setBusy(true); setError(''); try { const result = await sendMessage(conversationId, content, refresh, candidate); setMessages(items => [...items, result.user, result.assistant]); setContent('') } catch (value) { setError(value instanceof Error ? value.message : String(value)) } finally { setBusy(false) } }
  async function formalize() { const triggers = messages.filter(item => item.candidate_adjustment).slice(-2).map(item => item.id); if (!triggers.length) return; setBusy(true); try { setNewVersion(await reevaluate(conversationId, triggers)) } catch (value) { setError(value instanceof Error ? value.message : String(value)) } finally { setBusy(false) } }
  return <section className="chat-layout"><header><div><span className="eyebrow">{t('Persisted conversation')}</span><h2><MessageSquare size={18}/>{t('Report Q&A')}</h2></div>{!conversationId && <button className="secondary-button" onClick={begin} disabled={busy}>{t('Start conversation')}</button>}</header>{error && <div className="notice error-notice"><AlertTriangle size={16}/><p>{error}</p></div>}{conversationId && <><div className="message-list">{messages.length ? messages.map(message => <article className={message.role} key={message.id}><header><strong>{message.role === 'user' ? t('You') : t('Research assistant')}</strong><span>{message.refreshed_data ? t('Refreshed data') : message.candidate_adjustment ? t('Candidate only') : t('Report evidence')}</span></header><ReactMarkdown skipHtml>{message.content}</ReactMarkdown>{message.source_references.length > 0 && <small>{message.source_references.length} {t('persisted source reference')}</small>}</article>) : <Empty title={t('No messages yet')} text={t('Ask about the report or explicitly request current data.')}/>}</div><div className="chat-compose"><textarea aria-label={t('Question')} value={content} onChange={event => setContent(event.target.value)} placeholder={t('Ask about this report')}/><div><label className="check-row"><input type="checkbox" checked={refresh} onChange={event => setRefresh(event.target.checked)}/><span>{t('Retrieve current data')}</span></label><label className="check-row"><input type="checkbox" checked={candidate} onChange={event => setCandidate(event.target.checked)}/><span>{t('Candidate adjustment')}</span></label><button className="primary-button compact-button" onClick={submit} disabled={busy || !content.trim()}><Send size={16}/>{t('Send')}</button></div></div>{messages.some(item => item.candidate_adjustment) && <div className="reevaluate-bar"><div><strong>{t('Formal advice is unchanged')}</strong><span>{t('Re-evaluation creates a new immutable version with its own usage snapshot.')}</span></div><button className="secondary-button" onClick={formalize} disabled={busy}><RefreshCw size={16}/>{t('Re-evaluate')}</button></div>}{newVersion && <div className="notice success-notice"><Check size={16}/><p>{t('Formal advice version {{version}} created with parent {{parent}}.', { version: newVersion.version, parent: newVersion.parent_id?.slice(0,8) })}</p></div>}</>}</section>
}

function BackupPanel() {
  const { t, i18n } = useTranslation()
  const [items, setItems] = useState<BackupPreview[]>([])
  const [selected, setSelected] = useState<BackupPreview>()
  const [preview, setPreview] = useState<BackupPreview>()
  const [status, setStatus] = useState('')
  const refresh = () => listBackups().then(setItems).catch(value => setStatus(String(value)))
  useEffect(() => { refresh() }, [])
  async function backup() { setStatus(t('Creating backup')); const value = await createBackup(); setStatus(t('Backup created')); setSelected(value); await refresh() }
  async function inspect() { if (!selected) return; setPreview(await previewRestore(selected.backup_id)); setStatus(t('Restore preview complete')) }
  async function restore() { if (!preview?.valid || !preview.compatible) return; await commitRestore(preview.backup_id); setStatus(t('Restore completed')); setPreview(undefined) }
  return <section className="tool-panel"><header><div><span className="eyebrow">{t('Local recovery')}</span><h2><DatabaseBackup size={18}/>{t('Backup and restore')}</h2></div><button className="secondary-button" onClick={backup}><DatabaseBackup size={16}/>{t('Create backup')}</button></header>{status && <div className="notice success-notice"><Check size={16}/><p>{status}</p></div>}<div className="backup-layout"><div><h3>{t('Available backups')}</h3>{items.length ? items.map(item => <button key={item.backup_id} className={`backup-row ${selected?.backup_id === item.backup_id ? 'active' : ''}`} onClick={() => { setSelected(item); setPreview(undefined) }}><strong>{new Date(item.created_at ?? '').toLocaleString(locale(i18n.language))}</strong><span>Schema v{item.schema_version} · {Math.ceil((item.size_bytes ?? 0)/1024)} KB</span></button>) : <p className="missing">{t('No backups have been created.')}</p>}</div><div className="restore-panel"><h3>{t('Restore preflight')}</h3>{selected ? <><dl><dt>{t('Backup ID')}</dt><dd>{selected.backup_id.slice(0,13)}…</dd><dt>{t('Integrity')}</dt><dd>{selected.valid ? t('Valid') : selected.reason}</dd><dt>{t('Compatibility')}</dt><dd>{selected.compatible ? t('Compatible') : t('Rejected')}</dd></dl><button className="secondary-button" onClick={inspect}><ArchiveRestore size={16}/>{t('Preview restore')}</button>{preview && <button className="danger-button" onClick={restore} disabled={!preview.valid || !preview.compatible}>{t('Commit restore')}</button>}</> : <p className="missing">{t('Select a backup to inspect it before restoration.')}</p>}</div></div></section>
}

function Empty({ title, text }: { title: string; text: string }) { return <div className="empty-state compact-empty"><h2>{title}</h2><p>{text}</p></div> }

function Overview({ snapshot, instrument, status }: { snapshot?: Snapshot | null; instrument?: Instrument; status: string }) {
  const { t } = useTranslation()
  if (!snapshot) return <div className="empty-state"><div className="empty-chart"/><h2>{status === 'running' ? t('Analysis in progress') : t('No analysis results yet')}</h2><p>{instrument ? t('Start the analysis to populate metrics, charts, and holdings.') : t('Resolve an instrument from the configuration panel or open a persisted run.')}</p></div>
  const metrics = snapshot.metrics ?? []
  const drawdown = snapshot.price_series.map((point) => ({ ...point, drawdown: point.adjusted_close / Math.max(...snapshot.price_series.filter(item => item.date <= point.date).map(item => item.adjusted_close)) - 1 }))
  const metricLabel = (metric: Metric) => {
    const labels: Record<string, string> = { total_return: t('Total return'), annualized_volatility: t('Volatility'), maximum_drawdown: t('Max drawdown'), tracking_error: t('Tracking error') }
    return `${labels[metric.name] ?? metric.name}${metric.window ? ` · ${metric.window}` : ''}`
  }
  return <div className="overview-grid">
    <section className="metrics-grid">{metrics.slice(0,5).map((metric) => <div className="metric" key={`${metric.name}-${metric.window}`}><span>{metricLabel(metric)}</span><strong>{metric.value == null ? 'N/A' : metric.unit === 'percent' ? pct(metric.value) : metric.value.toFixed(2)}</strong><small>{metric.reason_if_unavailable ?? t('As of analysis date')}</small></div>)}</section>
    {snapshot.warnings?.map(warning => <section className="notice" key={warning}><AlertTriangle size={18}/><p>{warning}</p></section>)}
    <section className="chart-panel"><header><div><span className="eyebrow">{t('Performance')}</span><h2>{t('Adjusted price vs benchmark')}</h2></div><span className="legend"><i/>{t('Fund')} <i/>{t('Benchmark')}</span></header><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={snapshot.price_series}><CartesianGrid stroke="#e5e9e7" vertical={false}/><XAxis dataKey="date" tick={{fontSize:11}}/><YAxis tick={{fontSize:11}} width={44}/><Tooltip/><Area isAnimationActive={false} type="monotone" dataKey="adjusted_close" stroke="#156b52" fill="#dbece5" strokeWidth={2}/><Line isAnimationActive={false} type="monotone" dataKey="benchmark" stroke="#c45b31" strokeWidth={2} dot={false}/></AreaChart></ResponsiveContainer></div></section>
    <section className="chart-panel"><header><div><span className="eyebrow">{t('Risk')}</span><h2>{t('Drawdown')}</h2></div></header><div className="chart-wrap compact"><ResponsiveContainer width="100%" height="100%"><AreaChart data={drawdown}><CartesianGrid stroke="#e5e9e7" vertical={false}/><XAxis dataKey="date" tick={{fontSize:11}}/><YAxis tickFormatter={value => `${Math.round(value*100)}%`} tick={{fontSize:11}} width={44}/><Tooltip formatter={(value) => pct(Number(value))}/><Area isAnimationActive={false} type="monotone" dataKey="drawdown" stroke="#b94b3b" fill="#f3deda" strokeWidth={2}/></AreaChart></ResponsiveContainer></div></section>
    <section className="data-panel"><header><span className="eyebrow">{t('Composition')}</span><h2>{t('Top holdings')}</h2></header>{snapshot.top_holdings.length ? <div className="table-scroll"><table><thead><tr><th>{t('Symbol')}</th><th>{t('Holding')}</th><th>{t('Weight')}</th></tr></thead><tbody>{snapshot.top_holdings.map(item => <tr key={item.symbol ?? item.name}><td><strong>{item.symbol ?? '—'}</strong></td><td>{item.name}</td><td>{pct(item.weight)}</td></tr>)}</tbody></table></div> : <p className="missing">{t('Holdings unavailable from the provider.')}</p>}</section>
    <section className="data-panel"><header><span className="eyebrow">{t('Allocation')}</span><h2>{t('Sector exposure')}</h2></header><div className="allocation-list">{Object.entries(snapshot.sectors).map(([name,value]) => <div key={name}><span>{name}</span><strong>{pct(value)}</strong><i><b style={{width:pct(value)}}/></i></div>)}</div></section>
  </div>
}

function ReportList({ reports }: { reports: Array<[string,string]> }) {
  const { t } = useTranslation()
  if (!reports.length) return <div className="empty-state"><h2>{t('No report content yet')}</h2><p>{t('Sections appear here as agents complete their work.')}</p></div>
  const titles: Record<string,string> = { market_report:t('Market Analysis'), sentiment_report:t('Sentiment Analysis'), news_report:t('News Analysis'), fundamentals_report:t('Fund Analysis'), investment_plan:t('Research Decision'), trader_investment_plan:t('Trading Plan'), final_trade_decision:t('Final Decision') }
  return <div className="report-list">{reports.map(([key,content]) => <article key={key}><header><span className="eyebrow">{t('Agent report')}</span><h2>{titles[key] ?? key}</h2></header><div className="markdown"><ReactMarkdown skipHtml>{content}</ReactMarkdown></div></article>)}</div>
}
