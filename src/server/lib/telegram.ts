/**
 * Telegram dispatch — sends alert notifications via the Bot API.
 *
 * Config (env vars):
 *   TELEGRAM_BOT_TOKEN  — Botfather token (e.g. 123456789:ABCdef...)
 *   TELEGRAM_CHAT_ID   — Target chat (e.g. -100123456789)
 */

import type { TriggeredAlert } from "./types.ts"

// ── Config ───────────────────────────────────────────────────────────────────

function getBotToken(): string | undefined {
  return process.env.TELEGRAM_BOT_TOKEN
}

function getChatId(): string | undefined {
  return process.env.TELEGRAM_CHAT_ID
}

// ── Escape ───────────────────────────────────────────────────────────────────

/**
 * Telegram MarkdownV2 escape — escapes special chars.
 * Must escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
 */
function escapeMarkdownV2(text: string): string {
  return text.replace(/[_*[\]()~`>#+\-=|{}.!]/g, "\\$&")
}

// ── Send ─────────────────────────────────────────────────────────────────────

export interface TelegramSendOptions {
  text: string
  parse_mode?: "MarkdownV2" | "HTML"
  disable_notification?: boolean
}

export async function sendTelegramMessage(options: TelegramSendOptions): Promise<boolean> {
  const token = getBotToken()
  const chatId = getChatId()

  if (!token || !chatId) {
    console.error("[telegram] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping")
    return false
  }

  const url = `https://api.telegram.org/bot${token}/sendMessage`
  const body: Record<string, string | boolean | undefined> = {
    chat_id: chatId,
    text: options.parse_mode === "MarkdownV2" ? escapeMarkdownV2(options.text) : options.text,
    parse_mode: options.parse_mode,
    disable_notification: options.disable_notification,
  }

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      const err = await response.text()
      console.error(`[telegram] send failed: ${response.status} ${err}`)
      return false
    }

    return true
  } catch (err) {
    console.error(`[telegram] fetch error: ${err}`)
    return false
  }
}

// ── Alert Formatting ─────────────────────────────────────────────────────────

function formatSeverityEmoji(severity: string): string {
  switch (severity) {
    case "critical":
      return "🔴"
    case "warning":
      return "🟡"
    case "info":
      return "🔵"
    default:
      return "⚪"
  }
}

function formatAlertForTelegram(alert: TriggeredAlert): string {
  const { alert: rule, currentPrice, pctChange, message } = alert
  const severity = formatSeverityEmoji(rule.severity)

  const lines: string[] = [
    `${severity} *ALERT — ${rule.severity.toUpperCase()}*`,
    `📛 ${rule.name}`,
    `📈 ${rule.ticker ?? "(portfolio)"}`,
    "",
    message,
  ]

  if (currentPrice != null) {
    lines.push("")
    lines.push(`Current price: £${currentPrice.toFixed(2)}`)
  }

  if (pctChange != null) {
    const arrow = pctChange >= 0 ? "↑" : "↓"
    lines.push(`${arrow} ${Math.abs(pctChange).toFixed(1)}% change`)
  }

  lines.push("")
  lines.push(`🕐 ${new Date().toISOString()}`)

  return lines.join("\n")
}

// ── Dispatch ─────────────────────────────────────────────────────────────────

export interface DispatchResult {
  sent: boolean
  channel: string
  alertName: string
  error?: string
}

/**
 * Sends a triggered alert via its configured channel.
 * Returns a result record for each dispatch attempt.
 */
export async function dispatchAlert(alert: TriggeredAlert): Promise<DispatchResult> {
  const { alert: rule } = alert

  if (rule.channel === "none") {
    return { sent: true, channel: "none", alertName: rule.name }
  }

  if (rule.channel === "telegram") {
    const text = formatAlertForTelegram(alert)
    const sent = await sendTelegramMessage({ text, parse_mode: "MarkdownV2" })
    return {
      sent,
      channel: "telegram",
      alertName: rule.name,
      error: sent ? undefined : "telegram send failed",
    }
  }

  if (rule.channel === "email" || rule.channel === "webhook") {
    // Stretch goal — stub for now
    console.warn(`[telegram] channel "${rule.channel}" not implemented — skipping`)
    return { sent: false, channel: rule.channel, alertName: rule.name, error: "not implemented" }
  }

  return { sent: false, channel: rule.channel, alertName: rule.name, error: "unknown channel" }
}

/**
 * Dispatches a batch of triggered alerts.
 */
export async function dispatchAlerts(alerts: TriggeredAlert[]): Promise<DispatchResult[]> {
  return Promise.all(alerts.map(dispatchAlert))
}
