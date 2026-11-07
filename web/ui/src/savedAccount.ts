// The account this browser last selected, so a reload opens the same one.

const KEY = 'ta.account'

export function savedAccountId(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function saveAccountId(id: string): void {
  try {
    localStorage.setItem(KEY, id)
  } catch {
    // Storage blocked: the first account is selected again next visit.
  }
}
