import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { ResearchDetail as Detail, ResearchSummary, RunSettings } from '../api'
import { researchPath } from '../api'
import { Debate } from '../components/Debate'
import { Help } from '../components/Help'
import { Markdown } from '../components/Markdown'
import { Panel } from '../components/Panel'
import { RatingChip } from '../components/RatingChip'
import { ResearchList } from '../components/ResearchList'
import { Section } from '../components/Section'
import { ErrorBox, Loading } from '../components/Status'
import type { HelpKey } from '../content/help'
import { useFetch } from '../hooks'
import { researchKey } from '../routes'

interface Step {
  id: string
  title: string
  field: string
  help: HelpKey
  /** Text of the section; hidden entirely when `hideIfEmpty` and blank. */
  text: (d: Detail) => string
  kind: 'report' | 'debate'
  hideIfEmpty?: boolean
  defaultOpen?: boolean
}

// The research pipeline in running order.
const STEPS: Step[] = [
  {
    id: 'market',
    title: '市场分析',
    field: 'market_report',
    help: 's_market',
    text: (d) => d.market_report,
    kind: 'report',
  },
  {
    id: 'sentiment',
    title: '社媒情绪',
    field: 'sentiment_report',
    help: 's_sentiment',
    text: (d) => d.sentiment_report,
    kind: 'report',
  },
  { id: 'news', title: '新闻与宏观', field: 'news_report', help: 's_news', text: (d) => d.news_report, kind: 'report' },
  {
    id: 'fundamentals',
    title: '基本面',
    field: 'fundamentals_report',
    help: 's_fundamentals',
    text: (d) => d.fundamentals_report,
    kind: 'report',
    hideIfEmpty: true,
  },
  {
    id: 'debate',
    title: '多空辩论',
    field: 'investment_debate_state.history',
    help: 's_debate',
    text: (d) => d.investment_debate_state.history,
    kind: 'debate',
    defaultOpen: true,
  },
  {
    id: 'plan',
    title: '研究经理结论',
    field: 'investment_plan',
    help: 's_plan',
    text: (d) => d.investment_plan,
    kind: 'report',
  },
  {
    id: 'trader',
    title: '交易员方案',
    field: 'trader_investment_plan',
    help: 's_trader',
    text: (d) => d.trader_investment_plan,
    kind: 'report',
  },
  {
    id: 'risk',
    title: '风险辩论',
    field: 'risk_debate_state.history',
    help: 's_risk',
    text: (d) => d.risk_debate_state.history,
    kind: 'debate',
  },
  {
    id: 'final',
    title: '组合经理决定',
    field: 'final_trade_decision',
    help: 's_decision',
    text: (d) => d.final_trade_decision,
    kind: 'report',
    defaultOpen: true,
  },
]

const DEFAULT_OPEN: Record<string, boolean> = Object.fromEntries(STEPS.map((s) => [s.id, s.defaultOpen === true]))

function SettingsTags({ s }: { s: RunSettings }) {
  const tags: [string, string][] = [
    ['深度模型', s.deep_think_llm],
    ['快速模型', s.quick_think_llm],
    ['provider', s.llm_provider],
    ['分析师', s.analysts.join(', ')],
    ['辩论轮数', `${s.max_debate_rounds} / 风险 ${s.max_risk_discuss_rounds}`],
    ['语言', s.output_language],
    ['版本', String(s.version)],
  ]
  return (
    <div className="flex flex-wrap gap-1.5">
      {tags.map(([k, v]) => (
        <span key={k} className="num rounded-sm border border-border bg-panel px-1.5 py-px text-[11px] text-muted">
          {k} <span className="text-fg">{v}</span>
        </span>
      ))}
    </div>
  )
}

function Body({ detail, coin, date }: { detail: Detail; coin: string; date: string }) {
  const [open, setOpen] = useState<Record<string, boolean>>(DEFAULT_OPEN)
  const steps = useMemo(() => STEPS.filter((s) => !(s.hideIfEmpty && s.text(detail).trim() === '')), [detail])
  const setAll = (value: boolean) => setOpen(Object.fromEntries(steps.map((s) => [s.id, value])))

  return (
    <div className="flex flex-col gap-3">
      <header className="flex flex-col gap-2 rounded-sm border border-border bg-panel p-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="num text-[22px] leading-7 font-semibold">{coin}</h1>
          <span className="num text-muted">研判日 {date}</span>
          <span className="flex items-center gap-1.5">
            <RatingChip rating={detail.final_rating} size="lg" />
            <Help k="rating" />
          </span>
          <span className="num text-[11px] text-muted">{detail.company_of_interest}</span>
          <div className="ml-auto flex gap-1 text-[11px]">
            <button type="button" onClick={() => setAll(true)} className="rounded-sm border border-border px-2 py-px text-muted hover:text-fg">
              全部展开
            </button>
            <button type="button" onClick={() => setAll(false)} className="rounded-sm border border-border px-2 py-px text-muted hover:text-fg">
              全部折叠
            </button>
          </div>
        </div>
        <SettingsTags s={detail.run_settings} />
      </header>

      {steps.map((s, i) => {
        const text = s.text(detail)
        return (
          <Section
            key={s.id}
            index={i + 1}
            title={s.title}
            field={s.field}
            help={s.help}
            open={open[s.id] ?? false}
            onToggle={() => setOpen((o) => ({ ...o, [s.id]: !(o[s.id] ?? false) }))}
            meta={`${text.length.toLocaleString('en-US')} 字`}
          >
            {s.kind === 'debate' ? <Debate history={text} /> : <Markdown text={text} />}
          </Section>
        )
      })}
    </div>
  )
}

export function ResearchDetail() {
  const { coin = '', date = '' } = useParams()
  const detail = useFetch<Detail>(coin && date ? researchPath(coin, date) : null)
  const list = useFetch<ResearchSummary[]>('/api/research')

  return (
    <div className="grid gap-3 xl:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="hidden xl:block">
        <Panel
          title={<Link to="/research" className="hover:text-fg">← 全部研判</Link>}
          flush
          className="sticky top-12 max-h-[calc(100dvh-4rem)] overflow-y-auto"
        >
          {list.data ? (
            <ResearchList items={list.data} activeKey={researchKey(coin, date)} compact />
          ) : list.error ? (
            <ErrorBox error={list.error} onRetry={list.refresh} />
          ) : (
            <Loading />
          )}
        </Panel>
      </aside>

      <div className="min-w-0">
        <Link to="/research" className="mb-2 inline-block text-[12px] text-muted hover:text-fg xl:hidden">
          ← 全部研判
        </Link>
        {detail.error && !detail.data ? (
          <ErrorBox error={detail.error} onRetry={detail.refresh} />
        ) : !detail.data ? (
          <Loading />
        ) : (
          <Body key={researchKey(coin, date)} detail={detail.data} coin={coin} date={date} />
        )}
      </div>
    </div>
  )
}
