'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV = [
  {
    href: '/new-run',
    label: 'New Analysis',
    tag: 'RUN',
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <polygon points="4,3 13,8 4,13" fill="currentColor" opacity=".9"/>
      </svg>
    ),
  },
  {
    href: '/history',
    label: 'Run History',
    tag: 'LOG',
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <rect x="2" y="2" width="12" height="2.5" rx="1.25" fill="currentColor" opacity=".9"/>
        <rect x="2" y="6.75" width="8"  height="2.5" rx="1.25" fill="currentColor" opacity=".65"/>
        <rect x="2" y="11.5" width="10" height="2.5" rx="1.25" fill="currentColor" opacity=".8"/>
      </svg>
    ),
  },
  {
    href: '/settings',
    label: 'Settings',
    tag: 'CFG',
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.4"/>
        <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.42 1.42M11.53 11.53l1.42 1.42M12.95 3.05l-1.42 1.42M4.47 11.53l-1.42 1.42" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
      </svg>
    ),
  },
]

export default function Sidebar() {
  const path = usePathname()

  return (
    <aside
      className="w-[240px] min-h-screen flex flex-col shrink-0 relative"
      style={{
        background: 'var(--bg-sidebar)',
        borderRight: '1px solid var(--border)',
      }}
    >
      {/* Subtle dot grid texture */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: 'radial-gradient(circle, rgba(80,80,200,0.08) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
        }}
      />

      {/* Top glow */}
      <div
        className="absolute top-0 left-0 right-0 h-px pointer-events-none"
        style={{
          background: 'linear-gradient(90deg, transparent 10%, var(--accent) 50%, transparent 90%)',
          opacity: 0.3,
        }}
      />

      {/* Logo */}
      <div className="relative px-5 pt-6 pb-5" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="flex items-center gap-3">
          {/* Logo mark */}
          <div
            className="relative w-9 h-9 rounded-xl shrink-0 flex items-center justify-center overflow-hidden"
            style={{
              background: 'var(--accent-dim)',
              border: '1px solid rgba(0,196,232,0.35)',
              boxShadow: '0 0 20px rgba(0,196,232,0.15), inset 0 1px 0 rgba(255,255,255,0.06)',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <polyline
                points="1,13 5,8 9,10 13,5 17,2"
                stroke="var(--accent)"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <circle cx="17" cy="2" r="1.5" fill="var(--accent-light)"/>
            </svg>
            {/* Inner glow */}
            <div
              className="absolute inset-0"
              style={{
                background: 'radial-gradient(ellipse at 50% 0%, rgba(0,196,232,0.15) 0%, transparent 60%)',
              }}
            />
          </div>

          <div>
            <div
              className="font-bold leading-none tracking-tight"
              style={{
                fontFamily: 'var(--font-syne)',
                fontSize: '15px',
                color: 'var(--text-high)',
                letterSpacing: '-0.02em',
              }}
            >
              TradingAgents
            </div>
            <div
              className="mt-1 flex items-center gap-1.5"
              style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: '9px', letterSpacing: '0.12em' }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full inline-block"
                style={{ background: 'var(--buy)', boxShadow: '0 0 5px var(--buy)', animation: 'shimmer 2s ease-in-out infinite' }}
              />
              MULTI-AGENT AI
            </div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <div className="relative px-3 pt-5 flex-1">
        <div className="apex-label px-2 mb-3">Workspace</div>

        <nav className="flex flex-col gap-0.5">
          {NAV.map(({ href, label, tag, icon }) => {
            const active = path === href || path.startsWith(href + '/')

            return (
              <Link
                key={href}
                href={href}
                className="group relative flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200"
                style={
                  active
                    ? {
                        background: 'var(--accent-glow)',
                        color: 'var(--accent-light)',
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
                {/* Active indicator */}
                {active && (
                  <div
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 rounded-r"
                    style={{
                      height: '60%',
                      background: 'var(--accent)',
                      boxShadow: '0 0 8px var(--accent)',
                    }}
                  />
                )}

                {/* Icon */}
                <span
                  className="shrink-0 w-4 h-4 flex items-center justify-center transition-opacity"
                  style={{ opacity: active ? 1 : 0.5 }}
                >
                  {icon}
                </span>

                {/* Label */}
                <span
                  className="flex-1 text-[13px] font-medium"
                  style={{ fontFamily: 'var(--font-manrope)' }}
                >
                  {label}
                </span>

                {/* Tag */}
                <span
                  className="shrink-0 px-1.5 py-0.5 rounded text-[9px] font-bold"
                  style={{
                    fontFamily: 'var(--font-mono)',
                    letterSpacing: '0.08em',
                    background: active ? 'rgba(0,196,232,0.15)' : 'var(--bg-elevated)',
                    color: active ? 'var(--accent)' : 'var(--text-low)',
                    border: `1px solid ${active ? 'rgba(0,196,232,0.25)' : 'var(--border)'}`,
                  }}
                >
                  {tag}
                </span>
              </Link>
            )
          })}
        </nav>
      </div>

      {/* Divider */}
      <div className="mx-3 h-px" style={{ background: 'var(--border)' }} />

      {/* Footer */}
      <div className="relative px-5 py-4">
        <div className="flex items-center gap-2.5">
          <div
            className="w-6 h-6 rounded-lg flex items-center justify-center shrink-0"
            style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-raised)' }}
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <rect x="1" y="1" width="10" height="10" rx="2" stroke="var(--text-low)" strokeWidth="1.2"/>
              <circle cx="6" cy="6" r="1.5" fill="var(--text-low)"/>
            </svg>
          </div>
          <div>
            <div
              className="text-[11px] font-semibold"
              style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-manrope)' }}
            >
              Local Instance
            </div>
            <div
              className="text-[9px] flex items-center gap-1"
              style={{ color: 'var(--text-low)', fontFamily: 'var(--font-mono)', letterSpacing: '0.06em' }}
            >
              <span
                className="w-1 h-1 rounded-full inline-block"
                style={{ background: 'var(--buy)', animation: 'shimmer 3s ease-in-out infinite' }}
              />
              DEV · PORT 8000
            </div>
          </div>
        </div>
      </div>
    </aside>
  )
}
