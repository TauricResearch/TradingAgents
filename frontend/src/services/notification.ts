/**
 * Notification and Audio Chime Service for TradingAgents Pro
 * Uses Web Audio API for synthetic chimes (no audio asset files needed)
 * and Web Notifications API for desktop background alerts.
 */

export function isSoundEnabled(): boolean {
  return localStorage.getItem('tradingagents_sound_enabled') !== 'false';
}

export function setSoundEnabled(enabled: boolean): void {
  localStorage.setItem('tradingagents_sound_enabled', enabled ? 'true' : 'false');
}

export function isNotificationsEnabled(): boolean {
  return localStorage.getItem('tradingagents_notifications_enabled') !== 'false';
}

export function setNotificationsEnabled(enabled: boolean): void {
  localStorage.setItem('tradingagents_notifications_enabled', enabled ? 'true' : 'false');
  if (enabled && typeof window !== 'undefined' && 'Notification' in window) {
    if (Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }
}

/**
 * Play a synthesizer chime using Web Audio API
 */
export function playChime(type: 'success' | 'alert' = 'success'): void {
  if (!isSoundEnabled() || typeof window === 'undefined') return;

  try {
    const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioCtx) return;

    const ctx = new AudioCtx();
    const now = ctx.currentTime;

    if (type === 'success') {
      // Harmonic Quant Arpeggio: E5 (659.25Hz) -> G#5 (830.61Hz) -> B5 (987.77Hz) -> E6 (1318.51Hz)
      const notes = [659.25, 830.61, 987.77, 1318.51];
      notes.forEach((freq, idx) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, now + idx * 0.08);

        gain.gain.setValueAtTime(0, now + idx * 0.08);
        gain.gain.linearRampToValueAtTime(0.12, now + idx * 0.08 + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.08 + 0.4);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(now + idx * 0.08);
        osc.stop(now + idx * 0.08 + 0.45);
      });
    } else {
      // Alert/Failure double tone
      const notes = [440, 370];
      notes.forEach((freq, idx) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(freq, now + idx * 0.15);

        gain.gain.setValueAtTime(0.15, now + idx * 0.15);
        gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.15 + 0.25);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(now + idx * 0.15);
        osc.stop(now + idx * 0.15 + 0.26);
      });
    }
  } catch (err) {
    console.debug('Audio chime playback omitted:', err);
  }
}

/**
 * Trigger desktop system notification if enabled and supported
 */
export function notifyJobCompleted(ticker: string, signal?: string | null): void {
  if (!isNotificationsEnabled() || typeof window === 'undefined' || !('Notification' in window)) {
    return;
  }

  if (Notification.permission === 'granted') {
    const title = `TradingAgents Pro: ${ticker} Analysis Completed`;
    const options: NotificationOptions = {
      body: signal 
        ? `Verdict: ${signal.toUpperCase()}. Target and risk parameters are ready.`
        : `Analysis report is now available in your terminal.`,
      icon: '/favicon.ico',
      tag: `job-${ticker}-${Date.now()}`,
    };
    new Notification(title, options);
  } else if (Notification.permission === 'default') {
    Notification.requestPermission().then((perm) => {
      if (perm === 'granted') {
        notifyJobCompleted(ticker, signal);
      }
    });
  }
}
