export type NotifyType = 'error' | 'warning' | 'success' | 'info'

export interface Notification {
  id: string
  type: NotifyType
  message: string
  title?: string
}

/** Fire a global toast notification. Works from anywhere — no context needed. */
export function notify(type: NotifyType, message: string, title?: string) {
  window.dispatchEvent(
    new CustomEvent<Notification>('ta-notify', {
      detail: { id: crypto.randomUUID(), type, message, title },
    })
  )
}
