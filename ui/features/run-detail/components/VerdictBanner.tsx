import type { Decision } from '@/lib/types/agents'

type Props = { verdict: Decision | null; ticker: string; date: string }

const VERDICT_CONFIG: Record<Decision, {
  color: string
  colorBg: string
  colorRing: string
  label: string
  sublabel: string
  arrow: string
}> = {
  BUY: {
    color:     'var(--buy)',
    colorBg:   'var(--buy-bg)',
    colorRing: 'var(--buy-ring)',
    label:     'BUY',
    sublabel:  'Long position recommended',
    arrow:     '↑',
  },
  SELL: {
    color:     'var(--sell)',
    colorBg:   'var(--sell-bg)',
    colorRing: 'var(--sell-ring)',
    label:     'SELL',
    sublabel:  'Exit position recommended',
    arrow:     '↓',
  },
  HOLD: {
    color:     'var(--hold)',
    colorBg:   'var(--hold-bg)',
    colorRing: 'var(--hold-ring)',
    label:     'HOLD',
    sublabel:  'Maintain current position',
    arrow:     '→',
  },
}

export default function VerdictBanner({ verdict, ticker, date }: Props) {
  if (!verdict || !VERDICT_CONFIG[verdict]) return null
  const cfg = VERDICT_CONFIG[verdict]

  return (
    <div
      className="relative overflow-hidden animate-fade-up"
      style={{
        background:   cfg.colorBg,
        border:       `1px solid ${cfg.colorRing}`,
        borderRadius: '12px',
        padding:      '24px 28px',
      }}
    >
      {/* Background glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: `radial-gradient(ellipse at 80% 50%, ${cfg.color}08 0%, transparent 70%)`,
        }}
      />

      <div className="relative flex items-center justify-between gap-4">
        {/* Left: metadata */}
        <div>
          <div
            className="apex-label mb-2"
          >
            Analysis Complete
          </div>
          <div
            className="text-[22px] font-bold tracking-tight mb-1"
            style={{
              color:      'var(--text-high)',
              fontFamily: 'var(--font-manrope)',
              letterSpacing: '-0.03em',
            }}
          >
            {ticker}
          </div>
          <div
            className="text-xs font-mono"
            style={{ color: 'var(--text-mid)' }}
          >
            {date}
          </div>
        </div>

        {/* Divider */}
        <div
          className="hidden sm:block w-px self-stretch"
          style={{ background: cfg.colorRing, opacity: 0.4 }}
        />

        {/* Right: verdict */}
        <div className="flex items-center gap-5">
          <div>
            <div
              className="text-xs font-medium mb-1 text-right"
              style={{ color: cfg.color, opacity: 0.8, fontFamily: 'var(--font-manrope)' }}
            >
              {cfg.sublabel}
            </div>
            <div
              className="text-right"
              style={{
                color:      'var(--text-low)',
                fontSize:   '11px',
              }}
            >
              AI consensus decision
            </div>
          </div>

          {/* Big verdict */}
          <div
            className="flex items-center gap-2 px-5 py-3 rounded-xl"
            style={{
              background: `${cfg.colorRing}`,
              border:     `1px solid ${cfg.colorRing}`,
            }}
          >
            <span
              className="text-2xl font-bold leading-none"
              style={{ color: cfg.color }}
            >
              {cfg.arrow}
            </span>
            <span
              className="text-2xl font-bold tracking-tight leading-none"
              style={{
                color:      cfg.color,
                fontFamily: 'var(--font-manrope)',
                letterSpacing: '0.04em',
              }}
            >
              {cfg.label}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
