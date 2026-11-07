import { tone } from '../format'

const toneClass = { up: 'text-up', down: 'text-down', flat: 'text-fg' } as const

interface Props {
  value: number | null | undefined
  /** Formatter deciding sign and precision. */
  fmt: (x: number | null | undefined) => string
  /** Colour by the sign of a different number (e.g. direction by qty). */
  by?: number | null
  className?: string
}

/** A number coloured green/red by sign, in the monospace face. */
export function Num({ value, fmt, by, className = '' }: Props) {
  const key = tone(by === undefined ? value : by)
  return <span className={`num ${toneClass[key]} ${className}`}>{fmt(value)}</span>
}

/** Long/short marker derived from a signed quantity. */
export function Side({ qty }: { qty: number }) {
  if (qty > 0) return <span className="font-medium text-up">多</span>
  if (qty < 0) return <span className="font-medium text-down">空</span>
  return <span className="text-muted">—</span>
}
