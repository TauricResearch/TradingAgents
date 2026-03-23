'use client'

const ANALYSTS = [
  {
    id:    'market',
    label: 'Market',
    full:  'Market Analyst',
    desc:  'Price action & technicals',
    dot:   '#4480FF',
  },
  {
    id:    'news',
    label: 'News',
    full:  'News Analyst',
    desc:  'Sentiment & headlines',
    dot:   '#A78BFA',
  },
  {
    id:    'fundamentals',
    label: 'Fundamentals',
    full:  'Fundamentals Analyst',
    desc:  'Earnings & financials',
    dot:   '#00CE68',
  },
  {
    id:    'social',
    label: 'Social',
    full:  'Social Analyst',
    desc:  'Social media signals',
    dot:   '#F59E0B',
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
      {ANALYSTS.map(({ id, label, desc, dot, full }) => {
        const active = selected.includes(id)
        return (
          <button
            key={id}
            type="button"
            title={full}
            onClick={() => toggle(id)}
            className="relative p-4 text-left transition-all duration-200"
            style={{
              background:   active ? 'var(--bg-active)' : 'var(--bg-elevated)',
              border:       active ? `1px solid ${dot}40` : '1px solid var(--border)',
              borderTop:    active ? `2px solid ${dot}` : '1px solid var(--border)',
              borderRadius: '10px',
            }}
          >
            {/* Color dot */}
            <div
              className="w-2 h-2 rounded-full mb-3"
              style={{
                background:  dot,
                boxShadow:   active ? `0 0 6px ${dot}80` : 'none',
              }}
            />

            {/* Check */}
            {active && (
              <div
                className="absolute top-3 right-3 w-4 h-4 rounded-full flex items-center justify-center"
                style={{ background: dot, opacity: 0.9 }}
              >
                <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                  <polyline points="1.5,4 3,5.5 6.5,2" stroke="white" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
            )}

            <div
              className="text-sm font-semibold mb-0.5"
              style={{
                color:      active ? 'var(--text-high)' : 'var(--text-mid)',
                fontFamily: 'var(--font-manrope)',
              }}
            >
              {label}
            </div>
            <div
              className="text-[11px] leading-snug"
              style={{ color: 'var(--text-low)' }}
            >
              {desc}
            </div>
          </button>
        )
      })}
    </div>
  )
}
