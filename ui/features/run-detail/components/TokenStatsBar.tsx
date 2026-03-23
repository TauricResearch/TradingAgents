import type { TokenCount } from '../types'

function formatTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}

type Props = {
  tokensTotal: TokenCount
  status: string
}

export default function TokenStatsBar({ tokensTotal }: Props) {
  if (tokensTotal.in === 0 && tokensTotal.out === 0) return null

  const total = tokensTotal.in + tokensTotal.out

  return (
    <div
      className="flex items-center gap-4 px-4 py-2.5 rounded-xl"
      style={{
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border-raised)',
      }}
    >
      <div className="flex flex-col gap-0.5">
        <span
          className="text-[8px] uppercase tracking-widest"
          style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-mono)' }}
        >
          Total
        </span>
        <span
          className="text-[11px] font-bold"
          style={{ color: 'var(--text-high)', fontFamily: 'var(--font-mono)' }}
        >
          {formatTokens(total)}
        </span>
      </div>

      <div className="w-px h-6 shrink-0" style={{ background: 'var(--text-low)', opacity: 0.35 }} />

      <div className="flex flex-col gap-0.5">
        <span
          className="text-[8px] uppercase tracking-widest"
          style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-mono)' }}
        >
          Input ↑
        </span>
        <span
          className="text-[11px] font-bold"
          style={{ color: 'var(--accent-light)', fontFamily: 'var(--font-mono)' }}
        >
          {formatTokens(tokensTotal.in)}
        </span>
      </div>

      <div className="flex flex-col gap-0.5">
        <span
          className="text-[8px] uppercase tracking-widest"
          style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-mono)' }}
        >
          Output ↓
        </span>
        <span
          className="text-[11px] font-bold"
          style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-mono)' }}
        >
          {formatTokens(tokensTotal.out)}
        </span>
      </div>
    </div>
  )
}
