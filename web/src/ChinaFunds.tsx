import { useMemo, useState } from 'react'
import { AlertTriangle, Check, Search, ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { evaluateChinaFund, getChinaFundSnapshot, searchChinaFunds } from './api'
import type { ChinaFundCandidate, ChinaFundEvaluation, ChinaFundSnapshot, Instrument } from './types'

const actions = ['subscribe', 'hold', 'redeem_partial', 'redeem_all', 'convert']
const today = () => new Date().toISOString().slice(0, 10)
const humanize = (value: string) => value.replaceAll('_', ' ')

export default function ChinaFunds({ onUse }: { onUse: (candidate: ChinaFundCandidate, instrument: Instrument) => void }) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('003516')
  const [candidates, setCandidates] = useState<ChinaFundCandidate[]>([])
  const [snapshot, setSnapshot] = useState<ChinaFundSnapshot>()
  const [action, setAction] = useState('hold')
  const [amount, setAmount] = useState('')
  const [fraction, setFraction] = useState('')
  const [units, setUnits] = useState('')
  const [holdingDays, setHoldingDays] = useState('')
  const [minimumKnown, setMinimumKnown] = useState(false)
  const [platform, setPlatform] = useState('')
  const [targetCode, setTargetCode] = useState('')
  const [conversionSupported, setConversionSupported] = useState(false)
  const [evaluation, setEvaluation] = useState<ChinaFundEvaluation>()
  const [adviceVersion, setAdviceVersion] = useState<number>()
  const [error, setError] = useState('')
  const chart = useMemo(
    () => (snapshot?.nav_history ?? []).map(point => ({ date: point.date, nav: Number(point.nav) })),
    [snapshot],
  )

  async function search() {
    setError('')
    setSnapshot(undefined)
    setEvaluation(undefined)
    setAdviceVersion(undefined)
    try {
      setCandidates(await searchChinaFunds(query))
    } catch (value) {
      setCandidates([])
      setError(value instanceof Error ? value.message : t('Fund search failed'))
    }
  }

  async function select(candidate: ChinaFundCandidate) {
    setError('')
    setQuery(candidate.code)
    setEvaluation(undefined)
    setAdviceVersion(undefined)
    try {
      setSnapshot(await getChinaFundSnapshot(candidate.code, today()))
    } catch (value) {
      setError(value instanceof Error ? value.message : t('Fund snapshot unavailable'))
    }
  }

  async function evaluate() {
    if (!snapshot) return
    setError('')
    try {
      const result = await evaluateChinaFund(snapshot.identity.code, {
        intended_action: action,
        amount: amount || undefined,
        unit_fraction: fraction || undefined,
        confirmed_units: units || undefined,
        holding_days: holdingDays ? Number(holdingDays) : undefined,
        minimum_holding_known: minimumKnown,
        sales_platform: platform || undefined,
        conversion_supported: conversionSupported,
        target_code: targetCode || undefined,
      })
      setSnapshot(result.snapshot)
      setEvaluation(result.evaluation)
      setAdviceVersion(result.formal_advice?.version)
    } catch (value) {
      setError(value instanceof Error ? value.message : t('Fund evaluation unavailable'))
    }
  }

  const identity = snapshot?.identity
  return <div className="china-fund-layout">
    <section className="tool-panel china-search">
      <header><div><span className="eyebrow">{t('China public funds')}</span><h2><Search size={18}/>{t('Fund search')}</h2></div></header>
      <div className="china-search-row">
        <label><span className="field-label">{t('Fund name or code')}</span><input aria-label={t('China fund search')} value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => event.key === 'Enter' && void search()}/></label>
        <button className="secondary-button" onClick={() => void search()}><Search size={16}/>{t('Search')}</button>
      </div>
      {error && <p className="inline-error">{error}</p>}
      {candidates.length > 0 && <div className="fund-candidates">{candidates.map(candidate => <button key={candidate.code} className={identity?.code === candidate.code ? 'active' : ''} onClick={() => void select(candidate)}><strong>{candidate.display_name}</strong><span>{candidate.code} · {candidate.share_class} · {t(`market.${candidate.market_scope}`, { defaultValue: humanize(candidate.market_scope) })}</span></button>)}</div>}
    </section>
    {!snapshot ? <section className="empty-state compact-empty"><h2>{t('Search and select a fund')}</h2><p>{t('Choose an exact six-digit share class before retrieving public fund data.')}</p></section> : <>
      <section className="fund-identity">
        <div><span className="eyebrow">{t('Resolved instrument')}</span><h2>{snapshot.identity.display_name}</h2><p>{snapshot.identity.code} · {snapshot.identity.share_class} · {humanize(snapshot.identity.vehicle_type)} · {humanize(snapshot.identity.strategy_type)}</p></div>
        <div className="fund-identity-tags"><span className="status-badge trusted">{t(`market.${snapshot.identity.market_scope}`, { defaultValue: snapshot.identity.market_scope })}</span><span>{snapshot.identity.currency}</span><button className="secondary-button" onClick={() => onUse(snapshot.identity, { requested_symbol: snapshot.identity.code, canonical_symbol: snapshot.identity.code, asset_type: 'fund', fund_type: 'mutual_fund', quote_type: 'CHINA_PUBLIC_FUND', name: snapshot.identity.display_name, exchange: 'China off-exchange', currency: snapshot.identity.currency, warnings: snapshot.identity.warnings })}>{t('Use in analysis')}</button></div>
      </section>
      <section className="metrics-grid">{snapshot.metrics.map(metric => <div className="metric" key={metric.name}><span>{t(`metric.${metric.name}`, { defaultValue: humanize(metric.name) })}</span><strong>{metric.value == null ? 'N/A' : `${(Number(metric.value) * 100).toFixed(2)}%`}</strong><small>{metric.window ?? metric.reason_if_unavailable ?? t('available history')}</small></div>)}</section>
      <section className="chart-panel"><header><div><span className="eyebrow">{t('NAV history')}</span><h2>{t('Net asset value through {{date}}', { date: snapshot.analysis_date })}</h2></div><span>{snapshot.retrieved_at.slice(0, 19)}</span></header><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={chart}><CartesianGrid stroke="#e5e9e7" vertical={false}/><XAxis dataKey="date" tick={{ fontSize: 11 }}/><YAxis tick={{ fontSize: 11 }} width={48}/><Tooltip/><Area isAnimationActive={false} type="monotone" dataKey="nav" stroke="#156b52" fill="#dbece5" strokeWidth={2}/></AreaChart></ResponsiveContainer></div></section>
      <section className="tool-panel fund-context">
        <header><div><span className="eyebrow">{t('Comparison context')}</span><h2>{t('Benchmark and market cutoff')}</h2></div></header>
        <div className="fund-status-grid"><div><span>{t('Disclosed benchmark')}</span><strong>{snapshot.benchmark?.selected_name ?? snapshot.benchmark?.disclosed_text ?? t('unavailable')}</strong></div><div><span>{t('Selected benchmark code')}</span><strong>{snapshot.benchmark?.selected_code ?? t('unavailable')}</strong></div>{snapshot.identity.market_scope === 'qdii' && <><div><span>{t('Overseas market cutoff')}</span><strong>{String(snapshot.qdii_context.overseas_market_cutoff ?? t('unknown'))}</strong></div><div><span>{t('FX context')}</span><strong>{String(snapshot.qdii_context.fx_context ?? t('unknown'))}</strong></div></>}</div>
        {!snapshot.benchmark?.selected_code && <div className="notice"><AlertTriangle size={16}/><p>{t('Relative benchmark series is unavailable; no substitute benchmark was invented.')}</p></div>}
      </section>
      <section className="tool-panel fund-status">
        <header><div><span className="eyebrow">{t('Current data')}</span><h2>{t('Transaction status and trust')}</h2></div><span className={`status-badge ${snapshot.trust.level}`}>{snapshot.trust.executable ? t('operation eligible') : t('observation only')}</span></header>
        <div className="fund-status-grid"><div><span>{t('Subscription')}</span><strong>{snapshot.transaction_status?.subscription ?? t('unknown')}</strong></div><div><span>{t('Redemption')}</span><strong>{snapshot.transaction_status?.redemption ?? t('unknown')}</strong></div><div><span>{t('Observed')}</span><strong>{snapshot.transaction_status?.observed_at?.slice(0, 19) ?? t('unknown')}</strong></div><div><span>{t('NAV lag')}</span><strong>{t('{{count}} trading days', { count: snapshot.trust.nav_lag_trading_days ?? 0 })}</strong></div></div>
        {snapshot.identity.market_scope === 'qdii' && <div className="notice"><AlertTriangle size={16}/><p>{t('QDII published NAV can lag overseas markets. The displayed move is not an execution NAV.')}</p></div>}
        {snapshot.trust.reason_codes.map(code => <div className="reason-list" key={code}><span>{code}</span></div>)}
        {snapshot.trust.warnings.map(warning => <div className="notice" key={warning}><AlertTriangle size={16}/><p>{t(warning)}</p></div>)}
      </section>
      <section className="tool-panel fund-operation">
        <header><div><span className="eyebrow">{t('Deterministic operation gate')}</span><h2><ShieldCheck size={18}/>{t('Fund operation')}</h2></div></header>
        <div className="operation-form">
          <label><span className="field-label">{t('Intended action')}</span><select aria-label={t('Fund action')} value={action} onChange={event => setAction(event.target.value)}>{actions.map(value => <option key={value} value={value}>{t(`fundAction.${value}`)}</option>)}</select></label>
          <label><span className="field-label">{t('Subscription amount (CNY)')}</span><input aria-label={t('Subscription amount')} inputMode="decimal" value={amount} onChange={event => setAmount(event.target.value)}/></label>
          <label><span className="field-label">{t('Partial redemption fraction')}</span><input aria-label={t('Redemption fraction')} inputMode="decimal" placeholder="0.25" value={fraction} onChange={event => setFraction(event.target.value)}/></label>
          <label><span className="field-label">{t('Confirmed units')}</span><input aria-label={t('Confirmed units')} inputMode="decimal" value={units} onChange={event => setUnits(event.target.value)}/></label>
          <label><span className="field-label">{t('Holding days')}</span><input aria-label={t('Holding days')} type="number" min="0" value={holdingDays} onChange={event => setHoldingDays(event.target.value)}/></label>
          <label><span className="field-label">{t('Sales platform')}</span><input aria-label={t('Sales platform')} value={platform} onChange={event => setPlatform(event.target.value)}/></label>
          <label><span className="field-label">{t('Conversion target code')}</span><input aria-label={t('Conversion target code')} inputMode="numeric" maxLength={6} value={targetCode} onChange={event => setTargetCode(event.target.value)}/></label>
          <label className="check-row"><input type="checkbox" checked={minimumKnown} onChange={event => setMinimumKnown(event.target.checked)}/><span>{t('Minimum holding rule confirmed')}</span></label>
          <label className="check-row"><input type="checkbox" checked={conversionSupported} onChange={event => setConversionSupported(event.target.checked)}/><span>{t('Platform confirms conversion')}</span></label>
          <button className="primary-button" onClick={() => void evaluate()}>{t('Evaluate operation')}</button>
        </div>
        {evaluation && <div className={`operation-result ${evaluation.executable ? 'eligible' : 'blocked'}`}><Check size={18}/><div><strong>{evaluation.executable ? t('Executable proposal') : t('Observation only')}</strong><p>{t(evaluation.reason)}</p>{!evaluation.executable && (evaluation.blocked_actions[evaluation.action] ?? []).length > 0 && <small>{t(`fundAction.${evaluation.action}`, { defaultValue: humanize(evaluation.action) })}: {evaluation.blocked_actions[evaluation.action].join(', ')}</small>}{(evaluation.supporting_evidence ?? []).length > 0 && <small>{t('Supporting evidence')}: {evaluation.supporting_evidence.join(', ')}</small>}{(evaluation.opposing_evidence ?? []).length > 0 && <small>{t('Opposing evidence')}: {evaluation.opposing_evidence.join(', ')}</small>}{(evaluation.friction ?? []).map((item, index) => <small key={`${item.action}-${item.condition}-${index}`}>{t('Friction')}: {item.action} · {item.condition} · {item.rate}</small>)}{adviceVersion && <small>{t('Formal advice version {{version}} recorded.', { version: adviceVersion })}</small>}</div></div>}
      </section>
      <section className="tool-panel fund-provenance">
        <header><div><span className="eyebrow">{t('Traceability')}</span><h2>{t('Provider coverage and sources')}</h2></div></header>
        <div className="table-scroll"><table><thead><tr><th>{t('Capability')}</th><th>{t('Coverage')}</th></tr></thead><tbody>{Object.entries(snapshot.capability_status).map(([name, value]) => <tr key={name}><td>{t(`capability.${name}`, { defaultValue: humanize(name) })}</td><td><span className={`status-badge ${value}`}>{t(`coverage.${value}`, { defaultValue: value })}</span></td></tr>)}</tbody></table></div>
        <div className="source-list">{snapshot.evidence.map(item => <a key={`${item.name}-${item.source_reference}`} href={item.source_reference} target="_blank" rel="noreferrer">{item.name} · {item.effective_at ?? t('date unavailable')}</a>)}</div>
      </section>
    </>}
  </div>
}
