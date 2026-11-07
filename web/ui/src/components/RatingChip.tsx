import type { CoinState } from '../api'
import { truncate } from '../format'

/** Chip colours by rating; unknown ratings fall back to the REVIEW style. */
function ratingClass(rating: string): string {
  switch (rating) {
    case 'Buy':
    case 'Overweight':
      return 'border-up/50 bg-up/15 text-up'
    case 'Hold':
      return 'border-border bg-panel-2 text-muted'
    case 'Underweight':
    case 'Sell':
      return 'border-down/50 bg-down/15 text-down'
    default:
      return 'border-accent/60 bg-accent/15 text-accent'
  }
}

interface Props {
  rating: string | null
  /** Research state of the day; only `done` has a rating. */
  state?: CoinState
  error?: string | null
  size?: 'sm' | 'lg'
}

export function RatingChip({ rating, state = 'done', error = null, size = 'sm' }: Props) {
  const sizing =
    size === 'lg'
      ? 'px-3 py-1 text-[15px] font-semibold tracking-wide'
      : 'px-1.5 py-px text-[11px] font-medium'
  const base = `inline-flex max-w-full items-center rounded-sm border num leading-5 ${sizing}`

  if (state === 'pending') {
    return <span className={`${base} animate-pulse border-border bg-panel-2 text-muted`}>研判中</span>
  }
  if (state === 'failed') {
    return (
      <span className={`${base} border-down/50 bg-down/10 text-down`} title={error ?? undefined}>
        <span className="shrink-0">失败</span>
        {error && <span className="ml-1.5 truncate font-sans font-normal text-fg/80">{truncate(error, 60)}</span>}
      </span>
    )
  }
  if (rating === null) {
    return <span className={`${base} border-border bg-panel-2 text-muted`}>无评级</span>
  }
  return <span className={`${base} ${ratingClass(rating)}`}>{rating}</span>
}
