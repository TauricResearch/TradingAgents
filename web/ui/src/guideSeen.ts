// Whether this browser has seen the guide: set when /guide opens or the welcome banner is dismissed.

const KEY = 'ta.guide.seen'

export function guideSeen(): boolean {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

export function markGuideSeen(): void {
  try {
    localStorage.setItem(KEY, '1')
  } catch {
    // Storage blocked: the banner simply comes back next visit.
  }
}
