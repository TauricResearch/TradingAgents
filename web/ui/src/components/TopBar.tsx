import { useLayoutEffect, useRef } from 'react'
import { NavLink } from 'react-router-dom'
import { useAccount } from '../account'
import { fmtDrawdown, fmtTime, fmtUsdt } from '../format'
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

/** The hourly signals, listed right after the research: the intraday account's own, the demo account's followed ones. */
const SIGNALS_NAV = { to: '/signals', label: '信号', end: false }

export function TopBar() {
  const { account, accounts, select, overview } = useAccount()
  const nav =
    account.intraday || account.demo ? NAV.flatMap((n) => (n.to === '/research' ? [n, SIGNALS_NAV] : [n])) : NAV
  const ov = overview.data
  const halted = ov?.halted ?? account.halted
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
    <header ref={bar} className="sticky top-0 z-20 border-b border-border bg-bg/95 backdrop-blur">
      <div className="mx-auto flex max-w-[1500px] flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5">
        <div className="flex items-center gap-2">
          <span className="font-semibold tracking-wide">TradingAgents 模拟盘</span>
          {accounts.length > 1 ? (
            <div role="group" aria-label="账户" className="flex items-center gap-1">
              {accounts.map((a) => {
                const on = a.id === account.id
                return (
                  <button
                    key={a.id}
                    type="button"
                    aria-pressed={on}
                    onClick={() => select(a.id)}
                    className={`rounded-sm border px-1.5 text-[11px] ${
                      on ? 'border-accent bg-accent/15 text-accent' : 'border-border bg-panel text-muted hover:text-fg'
                    }`}
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
              熔断中
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
          <span className="num text-muted" title={ov?.processed_to ?? undefined}>
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
