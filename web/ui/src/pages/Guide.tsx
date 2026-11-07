import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAccount } from '../account'
import { Markdown } from '../components/Markdown'
import { GUIDE, type GuideSectionId } from '../content/guide'
import { fill } from '../content/vars'
import { markGuideSeen } from '../guideSeen'
import { useVars } from '../strategy'

const pad2 = (n: number): string => String(n).padStart(2, '0')

/** The section whose top has passed the sticky top bar; the last one once scrolled to the bottom. */
function currentSection(): GuideSectionId {
  const first = document.getElementById(GUIDE[0].id)
  if (!first) return GUIDE[0].id
  if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) {
    return GUIDE[GUIDE.length - 1].id
  }
  const line = parseFloat(getComputedStyle(first).scrollMarginTop) + 4
  let current = GUIDE[0].id
  for (const s of GUIDE) {
    const el = document.getElementById(s.id)
    if (el && el.getBoundingClientRect().top <= line) current = s.id
  }
  return current
}

export function Guide() {
  const vars = useVars()
  const { hash, key } = useLocation()
  const { overview } = useAccount()
  const [active, setActive] = useState<GuideSectionId>(GUIDE[0].id)

  useEffect(() => {
    markGuideSeen()
  }, [])

  // `/guide#sizing`: jump to the section on entry and whenever the hash changes (or is clicked
  // again). Also once the overview feed lands on a cold start: its figures can wrap the top
  // bar onto another line, which moves the anchor offset.
  const barSettled = !overview.loading
  useEffect(() => {
    const id = decodeURIComponent(hash.slice(1))
    if (id) document.getElementById(id)?.scrollIntoView()
  }, [hash, key, barSettled])

  useEffect(() => {
    const onScroll = () => setActive(currentSection())
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [])

  return (
    <div className="lg:grid lg:grid-cols-[200px_minmax(0,1fr)] lg:items-start lg:gap-4">
      {/* Narrow: a scrollable row of chips. Wide: a sticky table of contents. */}
      <nav aria-label="章节" className="mb-3 lg:sticky lg:top-[calc(var(--topbar-h)+10px)] lg:mb-0">
        <ol className="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:gap-0 lg:border-l lg:border-border lg:pb-0">
          {GUIDE.map((s, i) => {
            const on = s.id === active
            return (
              <li key={s.id} className="shrink-0">
                <Link
                  to={{ hash: s.id }}
                  aria-current={on ? 'location' : undefined}
                  className={`flex items-baseline gap-1.5 whitespace-nowrap rounded-sm border px-2 py-0.5 text-[12px] lg:-ml-px lg:rounded-none lg:border-0 lg:border-l-2 lg:py-1 ${
                    on
                      ? 'border-accent text-accent lg:border-l-accent'
                      : 'border-border text-muted hover:text-fg lg:border-l-transparent'
                  }`}
                >
                  <span className="num text-[11px] opacity-70">{pad2(i + 1)}</span>
                  {s.title}
                </Link>
              </li>
            )
          })}
        </ol>
      </nav>

      <div className="flex min-w-0 flex-col gap-3">
        {GUIDE.map((s, i) => (
          <section
            key={s.id}
            id={s.id}
            className="scroll-mt-[calc(var(--topbar-h)+10px)] rounded-sm border border-border bg-panel px-4 py-3"
          >
            <h2 className="mb-2 flex items-baseline gap-2 border-b border-border pb-1.5 text-[15px] font-semibold">
              <span className="num text-[11px] text-muted">{pad2(i + 1)}</span>
              {s.title}
            </h2>
            <Markdown text={fill(s.body, vars)} />
          </section>
        ))}
      </div>
    </div>
  )
}
