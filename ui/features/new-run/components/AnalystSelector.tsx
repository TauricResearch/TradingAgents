'use client'

const ANALYSTS = [
  {
    id:    'market',
    label: 'Market',
    full:  'Market Analyst',
    desc:  'Price action & technicals',
    accent: '#00C4E8',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <polyline points="1,14 5,9 8,11 12,6 17,3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
        <circle cx="17" cy="3" r="1.4" fill="currentColor"/>
      </svg>
    ),
  },
  {
    id:    'news',
    label: 'News',
    full:  'News Analyst',
    desc:  'Sentiment & headlines',
    accent: '#A78BFA',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <rect x="2" y="3" width="14" height="3" rx="1.5" fill="currentColor" opacity=".9"/>
        <rect x="2" y="8" width="10" height="2.5" rx="1.25" fill="currentColor" opacity=".65"/>
        <rect x="2" y="12.5" width="12" height="2.5" rx="1.25" fill="currentColor" opacity=".8"/>
      </svg>
    ),
  },
  {
    id:    'fundamentals',
    label: 'Fundamentals',
    full:  'Fundamentals Analyst',
    desc:  'Earnings & financials',
    accent: '#00E078',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <rect x="3" y="11" width="3" height="5" rx="1" fill="currentColor" opacity=".7"/>
        <rect x="7.5" y="7" width="3" height="9" rx="1" fill="currentColor" opacity=".85"/>
        <rect x="12" y="3" width="3" height="13" rx="1" fill="currentColor"/>
      </svg>
    ),
  },
  {
    id:    'social',
    label: 'Social',
    full:  'Social Analyst',
    desc:  'Social media signals',
    accent: '#FFB400',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <circle cx="9" cy="5" r="2.5" stroke="currentColor" strokeWidth="1.4"/>
        <circle cx="3.5" cy="12" r="2" stroke="currentColor" strokeWidth="1.4" opacity=".7"/>
        <circle cx="14.5" cy="12" r="2" stroke="currentColor" strokeWidth="1.4" opacity=".7"/>
        <path d="M5.5 11C6.5 8.5 11.5 8.5 12.5 11" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" opacity=".5"/>
      </svg>
    ),
  },
]

type Props = {
  selected: string[]
  onChange: (selected: string[]) => void
}

export default function AnalystSelector({ selected, onChange }: Props) {
  const toggle = (id: string) => {
    onChange(selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id])
  }

  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
      {ANALYSTS.map(({ id, label, desc, accent, icon, full }) => {
        const active = selected.includes(id)

        return (
          <button
            key={id}
            type="button"
            title={full}
            onClick={() => toggle(id)}
            className="relative flex flex-col items-start p-4 text-left transition-all duration-200"
            style={{
              background: active
                ? `linear-gradient(145deg, ${accent}0F 0%, ${accent}06 100%)`
                : 'var(--bg-elevated)',
              border: `1px solid ${active ? accent + '35' : 'var(--border-raised)'}`,
              borderRadius: '12px',
              transform: active ? 'none' : 'none',
              boxShadow: active ? `0 0 20px ${accent}12, 0 0 0 1px ${accent}20` : 'none',
            }}
            onMouseEnter={(e) => {
              if (!active) {
                (e.currentTarget as HTMLElement).style.background = 'var(--bg-hover)'
                ;(e.currentTarget as HTMLElement).style.borderColor = `${accent}20`
              }
            }}
            onMouseLeave={(e) => {
              if (!active) {
                (e.currentTarget as HTMLElement).style.background = 'var(--bg-elevated)'
                ;(e.currentTarget as HTMLElement).style.borderColor = 'var(--border-raised)'
              }
            }}
          >
            {/* Icon */}
            <div
              className="mb-3 w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200"
              style={{
                background: active ? `${accent}18` : 'var(--bg-active)',
                border: `1px solid ${active ? accent + '30' : 'var(--border)'}`,
                color: active ? accent : 'var(--text-low)',
                boxShadow: active ? `0 0 12px ${accent}20` : 'none',
              }}
            >
              {icon}
            </div>

            {/* Checkmark */}
            {active && (
              <div
                className="absolute top-3 right-3 w-4 h-4 rounded-full flex items-center justify-center"
                style={{
                  background: accent,
                  boxShadow: `0 0 8px ${accent}60`,
                  animation: 'step-complete 0.35s cubic-bezier(0.16,1,0.3,1) both',
                }}
              >
                <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                  <polyline points="1.5,4 3,5.5 6.5,2" stroke="var(--bg-base)" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
            )}

            <div
              className="text-sm font-semibold mb-0.5"
              style={{
                color: active ? 'var(--text-high)' : 'var(--text-mid)',
                fontFamily: 'var(--font-manrope)',
              }}
            >
              {label}
            </div>
            <div
              className="text-[10px] leading-snug"
              style={{
                color: active ? `${accent}B0` : 'var(--text-low)',
                fontFamily: 'var(--font-mono)',
                letterSpacing: '0.03em',
              }}
            >
              {desc}
            </div>
          </button>
        )
      })}
    </div>
  )
}
