const PREF_KEY = 'ta_browser_notify'

export function isBrowserNotifyEnabled(): boolean {
  return localStorage.getItem(PREF_KEY) === 'true' && Notification.permission === 'granted'
}

export async function requestBrowserNotifyPermission(): Promise<boolean> {
  if (!('Notification' in window)) return false
  const result = await Notification.requestPermission()
  const granted = result === 'granted'
  localStorage.setItem(PREF_KEY, granted ? 'true' : 'false')
  return granted
}

export function setBrowserNotifyPref(enabled: boolean): void {
  localStorage.setItem(PREF_KEY, enabled ? 'true' : 'false')
}

export function sendBrowserNotification(title: string, body: string, icon = '/favicon.ico'): void {
  if (!isBrowserNotifyEnabled()) return
  if (document.visibilityState === 'visible') return  // already in focus
  try {
    new Notification(title, { body, icon })
  } catch { /* ignore */ }
}
