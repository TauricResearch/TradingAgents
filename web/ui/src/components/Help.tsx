import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { HELP, type HelpKey } from '../content/help'
import { fill } from '../content/vars'
import { useVars } from '../strategy'

/** Look of the `?` mark; the welcome banner draws the one in its copy with it. */
export const MARK_CLASS =
  'inline-flex shrink-0 items-center justify-center rounded-full border border-current font-sans font-medium leading-none'

const SIZE = {
  sm: 'size-[14px] text-[9px]',
  /** Table headers. */
  xs: 'size-[12px] text-[8px]',
} as const

interface Props {
  k: HelpKey
  /** `end` lines the bubble's right edge up with the mark, for marks near the right edge. */
  align?: 'start' | 'end'
  size?: keyof typeof SIZE
  className?: string
}

const MARGIN = 8

interface Pos {
  top: number
  left: number
  /** The bubble opens upwards because there is no room below. */
  above: boolean
}

/**
 * A `?` mark that explains the figure next to it on hover or focus, with a link into the
 * guide. A click (touch) pins the bubble until Esc or a click elsewhere. The bubble is
 * fixed-positioned so scrolling tables and clipped strips do not cut it off; its visual gap
 * to the mark is transparent padding, so the pointer can cross into it without a leave.
 */
export function Help({ k, align = 'start', size = 'sm', className = '' }: Props) {
  const vars = useVars()
  const id = useId()
  const root = useRef<HTMLSpanElement>(null)
  const bubble = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [pinned, setPinned] = useState(false)
  const [pos, setPos] = useState<Pos | null>(null)
  const { text, section } = HELP[k]

  const hide = useCallback(() => {
    setOpen(false)
    setPos(null)
  }, [])
  const close = useCallback(() => {
    hide()
    setPinned(false)
  }, [hide])
  const toggle = () => {
    const next = !pinned
    setPinned(next)
    if (next) setOpen(true)
    else hide()
  }

  // Below the mark, or above when there is no room; kept inside the viewport. Follows scrolling.
  useLayoutEffect(() => {
    if (!open) return
    const place = () => {
      const mark = root.current?.getBoundingClientRect()
      const box = bubble.current?.getBoundingClientRect()
      if (!mark || !box) return
      const left = align === 'end' ? mark.right - box.width : mark.left
      const above = mark.bottom + box.height > window.innerHeight
      setPos({
        top: above ? mark.top - box.height : mark.bottom,
        left: Math.max(MARGIN, Math.min(left, window.innerWidth - box.width - MARGIN)),
        above,
      })
    }
    place()
    window.addEventListener('scroll', place, { capture: true, passive: true })
    window.addEventListener('resize', place)
    return () => {
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [open, align])

  // Pinned: a tap elsewhere or Esc closes, even when the mark never took focus (iOS, Safari).
  useEffect(() => {
    if (!pinned) return
    const onPointerDown = (e: PointerEvent) => {
      if (e.target instanceof Node && !root.current?.contains(e.target)) close()
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [pinned, close])

  const body = fill(text, vars).trim()

  return (
    <span
      ref={root}
      className={`relative inline-flex ${className}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => {
        if (!pinned) hide()
      }}
      onFocus={() => setOpen(true)}
      onBlur={(e) => {
        if (!root.current?.contains(e.relatedTarget)) close()
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') close()
      }}
    >
      <button
        type="button"
        aria-label="说明"
        aria-describedby={open ? id : undefined}
        onClick={toggle}
        className={`${MARK_CLASS} ${SIZE[size]} cursor-help text-muted hover:text-accent focus-visible:text-accent focus-visible:outline-none`}
      >
        ?
      </button>
      {open && (
        <div
          ref={bubble}
          id={id}
          role="tooltip"
          style={pos ? { top: pos.top, left: pos.left } : { top: 0, left: 0, visibility: 'hidden' }}
          className={`fixed z-30 w-max max-w-[280px] text-left font-sans text-[12px] leading-relaxed font-normal tracking-normal whitespace-normal normal-case text-fg ${
            pos?.above ? 'pb-1' : 'pt-1'
          }`}
        >
          <div className="rounded-sm border border-border bg-panel-2 px-2.5 py-2">
            {body && <div>{body}</div>}
            <Link
              to={`/guide#${section}`}
              onClick={close}
              className={`inline-block text-[11px] text-accent hover:underline ${body ? 'mt-1' : ''}`}
            >
              查看指南 →
            </Link>
          </div>
        </div>
      )}
    </span>
  )
}
