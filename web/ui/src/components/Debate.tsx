import { useMemo } from 'react'
import { SPEAKERS, splitDebate } from '../debate'
import { Markdown } from './Markdown'

/** A debate transcript rendered as coloured speaker turns. */
export function Debate({ history }: { history: string }) {
  const turns = useMemo(() => splitDebate(history), [history])
  if (turns.length === 0) return <div className="text-muted">（没有辩论记录）</div>
  return (
    <ol className="flex flex-col gap-2">
      {turns.map((t, i) => {
        const who = t.speaker ? SPEAKERS[t.speaker] : null
        const color = who?.color ?? 'var(--color-border)'
        return (
          <li
            key={i}
            className="rounded-sm border border-border bg-bg/40 pl-3"
            style={{ borderLeft: `3px solid ${color}` }}
          >
            <div className="flex flex-wrap items-baseline gap-x-2 pt-1.5 pr-3 text-[11px]">
              <span className="font-medium" style={{ color }}>
                {who?.label ?? '未标注'}
              </span>
              {t.speaker && <span className="num text-muted">{t.speaker}</span>}
              {t.round > 0 && <span className="num ml-auto text-muted">第 {t.round} 轮</span>}
            </div>
            <div className="pr-3 pb-2">
              <Markdown text={t.text} />
            </div>
          </li>
        )
      })}
    </ol>
  )
}
