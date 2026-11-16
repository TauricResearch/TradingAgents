import { useLayoutEffect, useRef } from 'react'
import { NavLink } from 'react-router-dom'
import { useAccount } from '../account'
import { fmtDrawdown, fmtTime, fmtTimeFull, fmtUsdt } from '../format'
import { ACCOUNT_LABEL } from '../llmSettings'
import { Help } from './Help'
import { StaleNote } from './Status'

const NAV = [
  { to: '/', label: '总览', end: true },
  { to: '/research', label: '研判', end: false },
  { to: '/history', label: '历史', end: false },
  { to: '/guide', label: '指南', end: false },
  { to: '/settings', label: '设置', end: false },
]

/** The hourly signals, listed right after the research: the intraday account's own, an exchange account's followed ones. */
const SIGNALS_NAV = { to: '/signals', label: '信号', end: false }

export function TopBar() {
  const { account, accounts, select, overview, execution } = useAccount()
  const nav =
    account.intraday || account.exchange ? NAV.flatMap((n) => (n.to === '/research' ? [n, SIGNALS_NAV] : [n])) : NAV
  const ov = overview.data
  const halted = ov?.halted ?? account.halted
  // An exchange account's pause, from its last reconciliation; a halt says more and stands alone.
  const ex = execution.data
  const paused = !halted && ex?.paused
  const bar = useRef<HTMLElement>(null)

  // The bar wraps to more lines on narrow screens; anchors and sticky elements below it
  // offset themselves by `--topbar-h` (see index.css for the default). Measured in a layout
  // effect so a page's own mount effects (the guide's anchor scroll) already see the value.
  useLayoutEffect(() => {
    const el = bar.current
    if (!el) return
    const update = () => document.documentElement.style.setProperty('--topbar-h', `${el.offsetHeight}px`)
    update()
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <header
      ref={bar}
      className={`sticky top-0 z-20 bg-bg/95 backdrop-blur ${account.live ? 'border-b-2 border-down' : 'border-b border-border'}`}
    >
      <div className="mx-auto flex max-w-[1500px] flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5">
        <div className="flex items-center gap-2">
          <span className="font-semibold tracking-wide">TradingAgents {account.live ? '实盘' : '模拟盘'}</span>
          {accounts.length > 1 ? (
            <div role="group" aria-label="账户" className="flex items-center gap-1">
              {accounts.map((a) => {
                const on = a.id === account.id
                // The real-money account stands out before it is chosen.
                const tone = a.live
                  ? on
                    ? 'border-down bg-down/15 text-down'
                    : 'border-down/50 bg-panel text-down/80 hover:text-down'
                  : on
                    ? 'border-accent bg-accent/15 text-accent'
                    : 'border-border bg-panel text-muted hover:text-fg'
                return (
                  <button
                    key={a.id}
                    type="button"
                    aria-pressed={on}
                    onClick={() => select(a.id)}
                    title={a.live ? '真钱账户：OKX 正式环境' : undefined}
                    className={`rounded-sm border px-1.5 text-[11px] ${tone}`}
                  >
                    {ACCOUNT_LABEL[a.id] ?? a.id}
                  </button>
                )
              })}
            </div>
          ) : (
            <span className="num rounded-sm border border-border bg-panel px-1.5 text-[11px] text-muted" title={account.kind}>
              {account.id}
            </span>
          )}
          {account.live && (
            <span className="rounded-sm bg-down px-1.5 py-px text-[11px] font-semibold text-bg" title="live 账户：OKX 正式环境，盈亏都是真的">
              真钱
            </span>
          )}
        </div>

        <nav className="flex items-center gap-1 text-[13px]">
          {nav.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `border-b-2 px-2 py-1 ${
                  isActive ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-fg'
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px]">
          {halted && (
            <span className="rounded-sm border border-accent bg-accent/20 px-2 py-px font-semibold text-accent">
              {account.live ? '已熔断' : '熔断中'}
            </span>
          )}
          {paused && (
            <span className="rounded-sm border border-accent/60 bg-accent/10 px-2 py-px font-semibold text-accent">
              {ex?.shadow_run ? '影子运行' : '暂停中'}
            </span>
          )}
          <span className="text-muted">
            净值 <span className="num text-fg">{fmtUsdt(ov?.equity)}</span>
          </span>
          <span className="text-muted">
            回撤
            <Help k="drawdown" align="end" className="mx-1" />
            <span className={`num ${ov?.drawdown != null && ov.drawdown > 0 ? 'text-down' : 'text-fg'}`}>
              {fmtDrawdown(ov?.drawdown)}
            </span>
          </span>
          <span className="num text-muted" title={ov?.processed_to ? fmtTimeFull(ov.processed_to) : undefined}>
            数据截至
            <Help k="processed_to" align="end" className="mx-1" />
            {fmtTime(ov?.processed_to)}
          </span>
          <StaleNote error={ov ? overview.error : null} />
        </div>
      </div>
    </header>
  )
}
