export interface DebateAttributionGuard {
  text: string | null;
  hasForeignAttribution: boolean;
  foreignLabels: string[];
}

const LABELS: ReadonlyArray<{ label: string; actor_id: string | null }> = [
  { label: "Moderator", actor_id: null },
  { label: "Bull Analyst", actor_id: "researcher.bull" },
  { label: "Bull Researcher", actor_id: "researcher.bull" },
  { label: "Bear Analyst", actor_id: "researcher.bear" },
  { label: "Bear Researcher", actor_id: "researcher.bear" },
  { label: "Aggressive Analyst", actor_id: "risk.aggressive" },
  { label: "Aggressive Risk Analyst", actor_id: "risk.aggressive" },
  { label: "Neutral Analyst", actor_id: "risk.neutral" },
  { label: "Neutral Risk Analyst", actor_id: "risk.neutral" },
  { label: "Conservative Analyst", actor_id: "risk.conservative" },
  { label: "Conservative Risk Analyst", actor_id: "risk.conservative" },
  { label: "Research Manager", actor_id: "manager.research" },
  { label: "Portfolio Manager", actor_id: "manager.portfolio" },
];

const LABEL_BY_NORMALIZED = new Map(
  LABELS.map((entry) => [entry.label.toLocaleLowerCase(), entry]),
);

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const ATTRIBUTION_RE = new RegExp(
  String.raw`(?:#{1,6}\s*)?(?:\*{1,2}|_{1,2})?(` +
    LABELS.map((entry) => escapeRegex(entry.label)).join("|") +
    String.raw`)\s*:(?:\*{1,2}|_{1,2})?`,
  "gi",
);

interface AttributionMatch {
  index: number;
  end: number;
  label: string;
  actor_id: string | null;
}

function findAttributions(text: string): AttributionMatch[] {
  const matches: AttributionMatch[] = [];
  ATTRIBUTION_RE.lastIndex = 0;
  for (
    let match = ATTRIBUTION_RE.exec(text);
    match;
    match = ATTRIBUTION_RE.exec(text)
  ) {
    const entry = LABEL_BY_NORMALIZED.get(match[1].toLocaleLowerCase());
    if (!entry) continue;
    matches.push({
      index: match.index,
      end: match.index + match[0].length,
      label: entry.label,
      actor_id: entry.actor_id,
    });
  }
  return matches;
}

/**
 * Protect lane authorship when opening immutable historical runs.
 *
 * Clean turns render unchanged except for a redundant leading self label. If a
 * body attributes speech to another participant, only explicitly self-labelled
 * spans are safe to show in the author's lane; the defect remains visible via
 * the returned audit metadata instead of being silently repaired.
 */
export function guardDebateAttribution(
  actor_id: string,
  text: string,
): DebateAttributionGuard {
  const matches = findAttributions(text);
  const foreign = matches.filter((match) => match.actor_id !== actor_id);

  if (foreign.length === 0) {
    const leadingSelf = matches.find(
      (match) =>
        match.actor_id === actor_id && text.slice(0, match.index).trim() === "",
    );
    return {
      text: (leadingSelf ? text.slice(leadingSelf.end) : text).trim() || null,
      hasForeignAttribution: false,
      foreignLabels: [],
    };
  }

  const selfSections = matches.flatMap((match, index) => {
    if (match.actor_id !== actor_id) return [];
    const end = matches[index + 1]?.index ?? text.length;
    const section = text.slice(match.end, end).trim();
    return section ? [section] : [];
  });

  return {
    text: selfSections.length > 0 ? selfSections.join("\n\n") : null,
    hasForeignAttribution: true,
    foreignLabels: [...new Set(foreign.map((match) => match.label))],
  };
}
