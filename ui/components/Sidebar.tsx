'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV = [
  {
    href: '/new-run',
    label: 'New Analysis',
    icon: (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.2"/>
        <path d="M7 4v3l2 2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    href: '/history',
    label: 'Run History',
    icon: (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <rect x="1" y="2" width="12" height="2" rx="1" fill="currentColor" opacity=".9"/>
        <rect x="1" y="6" width="8"  height="2" rx="1" fill="currentColor" opacity=".6"/>
        <rect x="1" y="10" width="10" height="2" rx="1" fill="currentColor" opacity=".75"/>
      </svg>
    ),
  },
  {
    href: '/settings',
    label: 'Settings',
    icon: (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <circle cx="7" cy="7" r="2.2" stroke="currentColor" strokeWidth="1.2"/>
        <path d="M7 1v1.5M7 11.5V13M1 7h1.5M11.5 7H13M2.5 2.5l1 1M10.5 10.5l1 1M11.5 2.5l-1 1M3.5 10.5l-1 1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
      </svg>
    ),
  },
]

export default function Sidebar() {
  const path = usePathname()

  return (
    <aside
      className="w-[220px] min-h-screen flex flex-col shrink-0"
      style={{
        background: 'var(--bg-sidebar)',
        borderRight: '1px solid var(--border)',
      }}
    >
      {/* Logo */}
      <div
        className="px-5 py-5"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2.5">
          {/* Geometric logo mark */}
          <div
            className="relative w-7 h-7 rounded-lg shrink-0 flex items-center justify-center"
            style={{
              background: 'var(--accent-dim)',
              border: '1px solid var(--accent)',
            }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <polyline points="1,10 4,6 7,8 10,4 13,2" stroke="var(--accent-light)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
              <circle cx="13" cy="2" r="1.2" fill="var(--accent-light)"/>
            </svg>
          </div>
          <div>
            <div
              className="text-sm font-bold tracking-tight leading-none"
              style={{ color: 'var(--text-high)', fontFamily: 'var(--font-manrope)' }}
            >
              TradingAgents
            </div>
            <div
              className="text-[9px] mt-0.5 font-medium tracking-widest uppercase"
              style={{ color: 'var(--text-low)' }}
            >
              Multi-Agent AI
            </div>
          </div>
        </div>
      </div>

      {/* Nav section */}
      <div className="px-2.5 pt-4 flex-1">
        <div
          className="apex-label px-2.5 mb-2"
        >
          Navigation
        </div>
        <nav className="flex flex-col gap-0.5">
          {NAV.map(({ href, label, icon }) => {
            const active = path === href || path.startsWith(href + '/')
            return (
              <Link
                key={href}
                href={href}
                className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] font-medium transition-all duration-150"
                style={
                  active
                    ? {
                        background: 'var(--accent-glow)',
                        color: 'var(--accent-light)',
                        borderLeft: '2px solid var(--accent)',
                        paddingLeft: '9px',
                      }
                    : {
                        color: 'var(--text-mid)',
                      }
                }
                onMouseEnter={(e) => {
                  if (!active) {
                    (e.currentTarget as HTMLElement).style.background = 'var(--bg-hover)'
                    ;(e.currentTarget as HTMLElement).style.color = 'var(--text-high)'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!active) {
                    (e.currentTarget as HTMLElement).style.background = ''
                    ;(e.currentTarget as HTMLElement).style.color = 'var(--text-mid)'
                  }
                }}
              >
                <span className="shrink-0 opacity-70">{icon}</span>
                <span style={{ fontFamily: 'var(--font-manrope)' }}>{label}</span>
              </Link>
            )
          })}
        </nav>
      </div>

      {/* Footer */}
      <div
        className="px-5 py-4"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: 'var(--buy)', boxShadow: '0 0 4px var(--buy)' }}
          />
          <span
            className="text-[10px] font-medium"
            style={{ color: 'var(--text-low)', fontFamily: 'var(--font-manrope)' }}
          >
            Local · Development
          </span>
        </div>
      </div>
    </aside>
  )
}
