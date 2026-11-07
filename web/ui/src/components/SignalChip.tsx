import type { SignalName } from '../api'

/** Chip colours by signal: Long up, Short down, Flat muted. */
const SIGNAL_CLASS: Record<SignalName, string> = {
  Long: 'border-up/50 bg-up/15 text-up',
  Short: 'border-down/50 bg-down/15 text-down',
  Flat: 'border-border bg-panel-2 text-muted',
}

interface Props {
  /** Null when the call failed or the answer had no usable signal. */
  signal: SignalName | null
  error?: string | null
}

export function SignalChip({ signal, error = null }: Props) {
  const base = 'inline-flex max-w-full items-center rounded-sm border num leading-5 px-1.5 py-px text-[11px] font-medium'
  if (signal === null) {
    return (
      <span className={`${base} border-down/50 bg-down/10 text-down`} title={error ?? undefined}>
        失败
      </span>
    )
  }
  return <span className={`${base} ${SIGNAL_CLASS[signal]}`}>{signal}</span>
}
