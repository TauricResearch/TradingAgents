import type { Decision } from '@/lib/types/agents'

type Props = { verdict: Decision | null; ticker: string; date: string }

const VERDICT_CONFIG: Record<Decision, {
  color: string
  colorBg: string
  colorRing: string
  colorGlow: string
  label: string
  sublabel: string
  symbol: string
  description: string
}> = {
  BUY: {
    color:       'var(--buy)',
    colorBg:     'var(--buy-bg)',
    colorRing:   'var(--buy-ring)',
    colorGlow:   'rgba(0, 224, 120, 0.15)',
    label:       'BUY',
    sublabel:    'Long Position',
    symbol:      '↑',
    description: 'AI consensus recommends entering a long position',
  },
  SELL: {
    color:       'var(--sell)',
    colorBg:     'var(--sell-bg)',
    colorRing:   'var(--sell-ring)',
    colorGlow:   'rgba(255, 31, 76, 0.15)',
    label:       'SELL',
    sublabel:    'Exit Position',
    symbol:      '↓',
    description: 'AI consensus recommends exiting the position',
  },
  HOLD: {
    color:       'var(--hold)',
    colorBg:     'var(--hold-bg)',
    colorRing:   'var(--hold-ring)',
    colorGlow:   'rgba(255, 180, 0, 0.15)',
    label:       'HOLD',
    sublabel:    'Maintain Position',
    symbol:      '→',
    description: 'AI consensus recommends maintaining current exposure',
  },
}

export default function VerdictBanner({ verdict, ticker, date }: Props) {
  if (!verdict || !VERDICT_CONFIG[verdict]) return null
  const cfg = VERDICT_CONFIG[verdict]

  return (
    <div
      className="relative overflow-hidden"
      style={{
        background: cfg.colorBg,
        border: `1px solid ${cfg.colorRing}`,
        borderRadius: '16px',
        animation: 'verdict-reveal 0.55s cubic-bezier(0.16,1,0.3,1) both',
      }}
    >
      {/* Background glow blobs */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: `radial-gradient(ellipse 70% 80% at 100% 50%, ${cfg.colorGlow} 0%, transparent 65%)`,
        }}
      />
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: `radial-gradient(ellipse 40% 60% at 0% 50%, ${cfg.colorBg} 0%, transparent 70%)`,
        }}
      />

      {/* Scanline shimmer on active color */}
      <div
        className="absolute top-0 left-0 right-0 h-px pointer-events-none"
        style={{
          background: `linear-gradient(90deg, transparent 5%, ${cfg.color}60 50%, transparent 95%)`,
        }}
      />

      {/* Corner decorative mark */}
      <div
        className="absolute top-4 right-4 opacity-10 pointer-events-none"
        style={{ color: cfg.color, fontFamily: 'var(--font-syne)', fontSize: '120px', fontWeight: 800, lineHeight: 1, letterSpacing: '-0.06em' }}
      >
        {cfg.symbol}
      </div>

      {/* Main content */}
      <div className="relative px-7 py-6">
        {/* Top row: label + meta */}
        <div className="flex items-center justify-between mb-5">
          <div className="apex-label" style={{ color: cfg.color, opacity: 0.7 }}>
            Analysis Complete
          </div>
          <div
            className="flex items-center gap-2 px-3 py-1 rounded-full text-[10px] font-bold"
            style={{
              fontFamily: 'var(--font-mono)',
              letterSpacing: '0.1em',
              background: `${cfg.colorRing}`,
              color: cfg.color,
              border: `1px solid ${cfg.colorRing}`,
            }}
          >
            AI CONSENSUS
          </div>
        </div>

        {/* Main verdict row */}
        <div className="flex items-end justify-between gap-6">
          {/* Left: ticker + description */}
          <div className="flex-1 min-w-0">
            <div
              className="flex items-baseline gap-3 mb-2"
            >
              <span
                className="terminal-text font-bold"
                style={{
                  fontSize: '42px',
                  lineHeight: 1,
                  letterSpacing: '-0.02em',
                  color: 'var(--text-high)',
                }}
              >
                {ticker}
              </span>
              <span
                className="terminal-text text-sm font-medium"
                style={{ color: 'var(--text-mid)', letterSpacing: '0.02em' }}
              >
                {date}
              </span>
            </div>
            <p
              className="text-sm"
              style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-manrope)', lineHeight: 1.5 }}
            >
              {cfg.description}
            </p>
          </div>

          {/* Right: big verdict badge */}
          <div className="shrink-0 flex flex-col items-center gap-2">
            <div
              style={{
                fontSize: '11px',
                fontFamily: 'var(--font-mono)',
                fontWeight: 700,
                letterSpacing: '0.12em',
                color: cfg.color,
                opacity: 0.7,
                textTransform: 'uppercase',
              }}
            >
              {cfg.sublabel}
            </div>
            <div
              className="flex items-center justify-center gap-2"
              style={{
                padding: '14px 32px',
                borderRadius: '12px',
                background: `${cfg.colorBg}`,
                border: `2px solid ${cfg.color}`,
                boxShadow: `0 0 32px ${cfg.colorGlow}, 0 0 64px ${cfg.colorBg}, inset 0 1px 0 rgba(255,255,255,0.06)`,
              }}
            >
              <span
                className="terminal-text"
                style={{
                  fontSize: '48px',
                  fontWeight: 700,
                  lineHeight: 1,
                  color: cfg.color,
                  letterSpacing: '-0.02em',
                }}
              >
                {cfg.symbol}
              </span>
              <span
                style={{
                  fontFamily: 'var(--font-syne)',
                  fontSize: '48px',
                  fontWeight: 800,
                  lineHeight: 1,
                  color: cfg.color,
                  letterSpacing: '-0.02em',
                  textShadow: `0 0 30px ${cfg.color}80`,
                }}
              >
                {cfg.label}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
