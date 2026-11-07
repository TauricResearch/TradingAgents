import { useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

interface Props {
  title: string
  confirmLabel: string
  /** The confirmed action is running: buttons disabled, Esc and the backdrop do nothing. */
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
  children: ReactNode
}

const FOCUSABLE =
  'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'

/**
 * Modal confirmation, mounted while open. Focus starts on 取消 and Tab cycles inside the
 * dialog; Esc or a click on the backdrop cancels. Focus returns to the opener on close.
 */
export function ConfirmDialog({ title, confirmLabel, busy = false, onConfirm, onCancel, children }: Props) {
  const id = useId()
  const box = useRef<HTMLDivElement>(null)
  const cancel = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const opener = document.activeElement
    cancel.current?.focus()
    return () => {
      if (opener instanceof HTMLElement) opener.focus()
    }
  }, [])

  // On the document, so a Tab still lands inside when focus fell to <body> (a click on the
  // backdrop, or a button disabled while busy).
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (!busy) onCancel()
        return
      }
      const root = box.current
      if (e.key !== 'Tab' || !root) return
      const items = [...root.querySelectorAll<HTMLElement>(FOCUSABLE)]
      const at = items.findIndex((el) => el === document.activeElement)
      if (items.length === 0) {
        e.preventDefault()
        root.focus()
      } else if (e.shiftKey ? at <= 0 : at === -1 || at === items.length - 1) {
        e.preventDefault()
        items[e.shiftKey ? items.length - 1 : 0].focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [busy, onCancel])

  return createPortal(
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-3"
      onMouseDown={(e) => {
        if (e.target !== e.currentTarget) return
        e.preventDefault()
        if (!busy) onCancel()
      }}
    >
      <div
        ref={box}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-title`}
        aria-describedby={`${id}-body`}
        tabIndex={-1}
        className="flex max-h-full w-full max-w-[480px] flex-col rounded-sm border border-border bg-panel outline-none"
      >
        <h2 id={`${id}-title`} className="border-b border-border px-3 py-2 font-semibold">
          {title}
        </h2>
        <div id={`${id}-body`} className="flex flex-col gap-2 overflow-y-auto px-3 py-3 leading-relaxed">
          {children}
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-3 py-2 text-[12px]">
          <button
            ref={cancel}
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-sm border border-border px-3 py-1 text-muted hover:border-muted hover:text-fg disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="rounded-sm border border-accent bg-accent px-3 py-1 font-semibold text-bg hover:bg-accent/85 disabled:opacity-60"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
