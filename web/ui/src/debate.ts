// Splitting a debate transcript into speaker turns. The agents append
// "<Speaker>: <text>" paragraphs to `history`, separated by newlines.

export type Speaker =
  | 'Bull Analyst'
  | 'Bear Analyst'
  | 'Aggressive Analyst'
  | 'Conservative Analyst'
  | 'Neutral Analyst'

export interface Turn {
  /** null for text that precedes the first recognised prefix. */
  speaker: Speaker | null
  /** 1-based turn number of this speaker. */
  round: number
  text: string
}

export const SPEAKERS: Record<Speaker, { label: string; color: string }> = {
  'Bull Analyst': { label: '多头研究员', color: 'var(--color-up)' },
  'Bear Analyst': { label: '空头研究员', color: 'var(--color-down)' },
  'Aggressive Analyst': { label: '激进', color: 'var(--color-line-btc)' },
  'Conservative Analyst': { label: '保守', color: 'var(--color-line-equal)' },
  'Neutral Analyst': { label: '中立', color: 'var(--color-muted)' },
}

const PREFIX = /^(Bull Analyst|Bear Analyst|Aggressive Analyst|Conservative Analyst|Neutral Analyst):[ \t]*/gm

const isSpeaker = (s: string): s is Speaker => s in SPEAKERS

export function splitDebate(history: string): Turn[] {
  const matches = [...history.matchAll(PREFIX)]
  const turns: Turn[] = []
  const rounds = new Map<Speaker, number>()

  const lead = (matches.length ? history.slice(0, matches[0].index) : history).trim()
  if (lead) turns.push({ speaker: null, round: 0, text: lead })

  matches.forEach((m, i) => {
    const name = m[1]
    if (!isSpeaker(name)) return
    const start = m.index + m[0].length
    const end = i + 1 < matches.length ? matches[i + 1].index : history.length
    const round = (rounds.get(name) ?? 0) + 1
    rounds.set(name, round)
    turns.push({ speaker: name, round, text: history.slice(start, end).trim() })
  })
  return turns
}
