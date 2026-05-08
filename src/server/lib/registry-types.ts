/**
 * Registry type definitions for briefs, debriefs, and playbook indexes.
 *
 * Each registry is a JSONL file (one JSON object per line). Every entry
 * has a `file` field pointing to the markdown source. Objects use the
 * JSONL convention: append-only, no trailing commas, one line per record.
 *
 * Validation is done at commit time via jq in `just check`. These types
 * document the expected shape for both agents and human contributors.
 */

// ── Briefs Index: briefs/INDEX.jsonl ─────────────────────────────────────

export interface BriefEntry {
  /** Relative filename within briefs/ directory */
  file: string
  /** Current status */
  status: "open" | "done"
  /** Date brief was created or last updated (YYYY-MM-DD) */
  date: string
  /** Parent epic td-* ID, or null if standalone */
  epic: string | null
  /** One-line summary of what the brief covers */
  summary: string
}

// ── Debriefs Index: debriefs/INDEX.jsonl ─────────────────────────────────

export interface DebriefEntry {
  /** Relative filename within debriefs/ directory */
  file: string
  /** Date the session occurred (YYYY-MM-DD) */
  date: string
  /** td session ID, or null if unknown */
  session: string | null
  /** Parent epic td-* ID this debrief relates to, or null */
  epic: string | null
  /** The single most important decision or takeaway from this debrief */
  decision: string
  /** Comma-separated ADR filenames this debrief produced, or null */
  adr: string | null
}

// ── Decisions Index: decisions/INDEX.jsonl ───────────────────────────────

export interface DecisionEntry {
  /** Relative filename within decisions/ directory */
  file: string
  /** Date the decision was recorded (YYYY-MM-DD) */
  date: string
  /** Current status */
  status: "Proposed" | "Accepted" | "Superseded"
  /** ADR this decision supersedes, or null */
  supersedes: string | null
  /** ADR that supersedes this one, or null */
  superseded_by: string | null
  /** One-line summary of the decision */
  summary: string
}

// ── Playbooks Registry: playbooks/REGISTRY.jsonl ──────────────────────────

export interface PlaybookEntry {
  /** Relative filename within playbooks/ directory */
  file: string
  /** true = patterns are reusable across projects; false = TradingAgents-specific */
  canonical: boolean
  /** Project of origin (only meaningful when canonical is true) */
  source: string | null
  /** One-line description of what the playbook covers */
  covers: string
  /** true = this playbook contains patterns worth extracting to canonical */
  mining_candidate: boolean
  /** Hint about what to extract, or null */
  mining_note: string | null
  /** When the playbook was last mined for canonical knowledge (YYYY-MM-DD) */
  last_mined: string | null
}
