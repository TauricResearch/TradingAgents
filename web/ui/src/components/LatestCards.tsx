import { Link } from 'react-router-dom'
import type { Latest, LatestCoin } from '../api'
import { coinLabel, fmtAbsQty, fmtUsd, fmtUsdt } from '../format'
import { researchHref } from '../routes'
import { RatingChip } from './RatingChip'

function fillsText(coin: LatestCoin): string {
  if (coin.fills.length === 0) return '不调仓'
  return coin.fills
    .map((f) => `${f.qty > 0 ? '买入' : '卖出'} ${fmtAbsQty(f.qty)} @ ${fmtUsdt(f.price)}`)
    .join('；')
}

function CardBody({ coin }: { coin: LatestCoin }) {
  return (
    <>
      <div className="flex min-w-0 items-center gap-2">
        <span className="num w-10 shrink-0 text-[14px] font-semibold" title={coin.coin}>
          {coinLabel(coin.coin)}
        </span>
        <RatingChip rating={coin.rating} state={coin.state} error={coin.error} />
        <span className="num ml-auto shrink-0 text-[11px] text-muted" title="该币当日 LLM 费用">
          {fmtUsd(coin.cost_usd)}
        </span>
      </div>
      <div className={`num pl-12 text-[12px] ${coin.fills.length ? 'text-fg' : 'text-muted'}`}>
        {fillsText(coin)}
      </div>
    </>
  )
}

/** The latest trade date's research per coin; finished ones open the record. */
export function LatestCards({ latest }: { latest: Latest }) {
  if (latest.coins.length === 0) return <div className="px-3 py-6 text-center text-muted">暂无研判</div>
  return (
    <ul className="flex flex-col">
      {latest.coins.map((c) => {
        const cls = 'flex flex-col gap-1 px-3 py-2'
        return (
          <li key={c.coin} className="border-b border-border/60 last:border-b-0">
            {c.state === 'done' ? (
              <Link to={researchHref(c.coin, latest.trade_date)} className={`${cls} hover:bg-panel-2/60`}>
                <CardBody coin={c} />
              </Link>
            ) : (
              <div className={cls}>
                <CardBody coin={c} />
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
