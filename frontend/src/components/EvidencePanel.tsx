/** Evidence with provenance: each claim's data refs resolve in a
 * popover — source, raw value. Quarantined feeds surface as security
 * badges, never silently dropped. */
import { ShieldAlert } from "lucide-react";

import { DirectionBadge } from "./DirectionBadge";
import { Badge } from "./ui/badge";
import { Tip } from "./ui/tooltip";
import type { EvidencePanels } from "@/lib/api/types";

export function EvidencePanel({
  panels,
  missingFeeds = [],
}: {
  panels: EvidencePanels;
  missingFeeds?: string[];
}) {
  const quarantined = missingFeeds.filter((f) => f.startsWith("news:quarantined"));
  const degraded = missingFeeds.filter((f) => !f.startsWith("news:quarantined"));

  return (
    <div className="space-y-3.5" data-testid="evidence-panel">
      {quarantined.length > 0 && (
        <div className="flex items-center gap-2 rounded-md border border-bear/40 bg-bear-muted px-3 py-2 text-sm">
          <ShieldAlert size={16} className="text-bear" aria-hidden="true" />
          <span>
            {quarantined.length} external item(s) quarantined as suspected prompt
            injection before reaching any agent.
          </span>
        </div>
      )}
      {degraded.length > 0 && (
        <div className="text-xs text-fg-muted">
          This decision was made without:{" "}
          {degraded.map((feed) => (
            <Badge key={feed} variant="stale" className="mr-1">
              {feed}
            </Badge>
          ))}
        </div>
      )}
      {Object.entries(panels).map(([team, items]) => (
        <section key={team}>
          <h3 className="mb-[5px] text-[10px] font-bold uppercase tracking-[0.08em] text-fg-subtle">
            {team} ({items.length})
          </h3>
          <ul className="space-y-[7px]">
            {items.map((item, i) => (
              <li key={`${item.agent_id}-${i}`} className="text-[13px]">
                <DirectionBadge value={item.direction} showWord={false} />{" "}
                <span className="font-bold">{item.agent_id}</span>{" "}
                <span className="text-[11px] text-fg-subtle">
                  {item.direction} {item.confidence}
                </span>
                : <span className="text-fg-muted">{item.claim}</span>
                {(item.data_refs ?? []).length > 0 && (
                  <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">
                    {(item.data_refs ?? []).slice(0, 6).map((ref, j) => (
                      <Tip
                        key={j}
                        content={
                          <div className="font-mono text-[11px]">
                            <div className="font-semibold">{ref.name}</div>
                            <div>{JSON.stringify(ref.value)}</div>
                          </div>
                        }
                      >
                        <span className="cursor-help rounded-[7px] bg-surface-2 px-2 py-px font-mono text-[10px] text-fg-muted">
                          {ref.name}
                        </span>
                      </Tip>
                    ))}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
