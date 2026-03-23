import Link from 'next/link'
import type { RunSummary } from '@/lib/types/run'

type Props = { runs: RunSummary[] }

function DecisionBadge({ decision }: { decision: string }) {
  const lower = decision.toLowerCase()
  if (lower === 'buy') return <span className="badge-buy">{decision}</span>
  if (lower === 'sell') return <span className="badge-sell">{decision}</span>
  if (lower === 'hold') return <span className="badge-hold">{decision}</span>
  return (
    <span
      className="px-2.5 py-1 rounded-full text-xs font-semibold"
      style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--text-mid)' }}
    >
      {decision}
    </span>
  )
}

export default function RunHistoryTable({ runs }: Props) {
  if (runs.length === 0) {
    return (
      <div
        className="rounded-lg px-6 py-12 text-center"
        style={{ backgroundColor: 'var(--bg-card)' }}
      >
        <p className="text-sm" style={{ color: 'var(--text-low)' }}>
          No runs yet. Start a new analysis.
        </p>
      </div>
    )
  }
  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border)' }}
    >
      <table className="w-full text-sm">
        <thead>
          <tr style={{ backgroundColor: 'var(--bg-elevated)' }}>
            <th
              className="apex-label px-5 py-3 text-left"
              style={{ fontFamily: 'var(--font-manrope)' }}
            >
              Ticker
            </th>
            <th
              className="apex-label px-5 py-3 text-left"
              style={{ fontFamily: 'var(--font-manrope)' }}
            >
              Date
            </th>
            <th
              className="apex-label px-5 py-3 text-left"
              style={{ fontFamily: 'var(--font-manrope)' }}
            >
              Decision
            </th>
            <th
              className="apex-label px-5 py-3 text-left"
              style={{ fontFamily: 'var(--font-manrope)' }}
            >
              Created
            </th>
            <th className="px-5 py-3" />
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr
              key={run.id}
              className="transition-colors duration-100"
              style={{ borderTop: '1px solid var(--border)' }}
              onMouseEnter={(e) =>
                (e.currentTarget.style.backgroundColor = 'var(--bg-hover)')
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.backgroundColor = '')
              }
            >
              <td
                className="px-5 py-4 font-mono font-semibold tracking-wider"
                style={{ color: 'var(--text-high)' }}
              >
                {run.ticker}
              </td>
              <td className="px-5 py-4" style={{ color: 'var(--text-mid)' }}>
                {run.date}
              </td>
              <td className="px-5 py-4">
                {run.decision ? (
                  <DecisionBadge decision={run.decision} />
                ) : (
                  <span style={{ color: 'var(--text-low)' }}>—</span>
                )}
              </td>
              <td className="px-5 py-4 text-xs" style={{ color: 'var(--text-mid)' }}>
                {new Date(run.created_at).toLocaleString()}
              </td>
              <td className="px-5 py-4">
                <Link
                  href={`/runs/${run.id}`}
                  className="text-xs font-medium transition-colors"
                  style={{ color: 'var(--accent)' }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.color = 'var(--accent-light)')
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.color = 'var(--accent)')
                  }
                >
                  View Report →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
