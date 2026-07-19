/**
 * G2 - Debate/verdict timeline.
 *
 * Renders the ordered turn transcript from the live workbench store. Each
 * turn's response text is lazy-loaded from the turn.output_ready artifact
 * (the JSON-serialized business_delta) via extractResponse. Candidate
 * (output_ready, not committed) vs committed (completed) turns are visually
 * distinguished by a gold 候选 tag prepended to the bubble-head.
 */
import { useState } from "react";
import type { Turn } from "../../state/model";
import { ROLE_REGISTRY } from "../../state/model";
import { turnTimeline } from "../../state/selectors";
import { useWorkbenchStore } from "../../state/WorkbenchStore";
import { readArtifactText } from "../../api/client";
import { extractResponse } from "../../domain/responseExtractor";
import { ROLE_LABELS_ZH } from "../../domain/roles";
import { RoleIcon } from "../icons/RoleIcon";

export interface TimelineProps {
  filter: string;
  onTurnSelected: (turn_id: string) => void;
  onFilterChange?: (filter: string) => void;
}

interface LoadedResponse {
  text: string | null;
  badge: string | null;
  loading: boolean;
  error: string | null;
}

const FILTER_BUTTONS: ReadonlyArray<{ label: string; value: string }> = [
  { label: "全部", value: "" },
  { label: "分析师", value: "analysts" },
  { label: "多空辩论", value: "research" },
  { label: "风险", value: "risk" },
  { label: "裁决", value: "portfolio" },
];

function roleDefFor(actor_id: string): { team_id: string; icon_id: string } {
  const def = ROLE_REGISTRY.find((r) => r.actor_id === actor_id);
  return {
    team_id: def?.team_id ?? "",
    icon_id: def?.icon_id ?? "",
  };
}

function tagTextFor(actor_id: string, turn_index: number): string {
  if (actor_id === "manager.research" || actor_id === "manager.portfolio") {
    return "裁决";
  }
  if (actor_id === "evidence.steward") {
    return "Gate";
  }
  return turn_index > 1 ? `第 ${turn_index} 轮` : "第 1 轮";
}

export function Timeline({
  filter,
  onTurnSelected,
  onFilterChange,
}: TimelineProps): JSX.Element {
  const { stream, run_id } = useWorkbenchStore();
  const state = stream.state;
  const activeFilter = filter || "";

  const [loaded, setLoaded] = useState<Record<string, LoadedResponse>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  async function fetchResponse(turn: Turn): Promise<void> {
    if (!turn.artifact_id) return;
    const runId = run_id;
    if (runId === null) return;
    const artifactId = turn.artifact_id;

    setLoaded((prev) => ({
      ...prev,
      [turn.turn_id]: { text: null, badge: null, loading: true, error: null },
    }));

    try {
      const raw = await readArtifactText(runId, artifactId);
      const parsed: unknown = JSON.parse(raw);
      const delta: Record<string, unknown> =
        parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
          ? (parsed as Record<string, unknown>)
          : {};
      const { text, badge } = extractResponse(turn.actor_id, delta);
      setLoaded((prev) => ({
        ...prev,
        [turn.turn_id]: { text, badge, loading: false, error: null },
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setLoaded((prev) => ({
        ...prev,
        [turn.turn_id]: {
          text: null,
          badge: null,
          loading: false,
          error: message,
        },
      }));
    }
  }

  function handleBubbleClick(turn: Turn): void {
    onTurnSelected(turn.turn_id);
    const isExpanded = expanded.has(turn.turn_id);
    if (isExpanded) {
      setExpanded((prev) => {
        const next = new Set(prev);
        next.delete(turn.turn_id);
        return next;
      });
    } else {
      setExpanded((prev) => {
        const next = new Set(prev);
        next.add(turn.turn_id);
        return next;
      });
      const existing = loaded[turn.turn_id];
      if (turn.artifact_id && !existing) {
        void fetchResponse(turn);
      }
    }
  }

  const head = (
    <div className="timeline-head">
      <span className="eyebrow">Live transcript</span>
      <h2>辩论与决策时间线</h2>
      <div className="filters">
        {FILTER_BUTTONS.map((btn) => (
          <button
            key={btn.value || "all"}
            type="button"
            className={activeFilter === btn.value ? "filter active" : "filter"}
            aria-pressed={activeFilter === btn.value}
            onClick={onFilterChange ? () => onFilterChange(btn.value) : undefined}
          >
            {btn.label}
          </button>
        ))}
      </div>
    </div>
  );

  if (state === null) {
    return (
      <section>
        {head}
        <div className="placeholder">发起分析后查看辩论时间线</div>
      </section>
    );
  }

  const turns = turnTimeline(state, activeFilter);
  const hasAnyTurns = Object.keys(state.turns).length > 0;

  return (
    <section>
      {head}
      {turns.length === 0 ? (
        <div className="placeholder">
          {hasAnyTurns ? "当前过滤无条目" : "等待事件流"}
        </div>
      ) : (
        turns.map((turn) => {
          const { team_id, icon_id } = roleDefFor(turn.actor_id);
          const isManager =
            turn.actor_id === "manager.research" ||
            turn.actor_id === "manager.portfolio";
          const isBear = turn.actor_id === "researcher.bear";
          const isCandidate = turn.status === "output_ready";
          const label = ROLE_LABELS_ZH[turn.actor_id] ?? turn.actor_id;
          const tag = tagTextFor(turn.actor_id, turn.turn_index);
          const entry = loaded[turn.turn_id];
          const isExpanded = expanded.has(turn.turn_id);

          let responseContent: string;
          if (!turn.artifact_id) {
            responseContent = "（进行中）";
          } else if (!isExpanded) {
            responseContent = "点击展开";
          } else if (entry?.loading) {
            responseContent = "正在加载";
          } else if (entry?.error) {
            responseContent = `加载失败：${entry.error}`;
          } else if (entry) {
            responseContent = entry.text ?? "（无文本）";
          } else {
            responseContent = "正在加载";
          }

          return (
            <article
              key={turn.turn_id}
              className={isBear ? "event bear" : "event"}
              data-team={team_id}
            >
              <div className="avatar">
                <RoleIcon icon_id={icon_id} size={15} />
              </div>
              <div
                className={isManager ? "bubble manager" : "bubble"}
                onClick={() => handleBubbleClick(turn)}
              >
                <div className="bubble-head">
                  {isCandidate && (
                    <span
                      className="tag candidate"
                      style={{ color: "var(--gold)" }}
                    >
                      候选
                    </span>
                  )}
                  <span>{label}</span>
                  <span className="tag">{tag}</span>
                  {entry?.badge && (
                    <span
                      className={
                        turn.actor_id === "evidence.steward"
                          ? "tag evidence"
                          : "tag"
                      }
                    >
                      {entry.badge}
                    </span>
                  )}
                </div>
                <p>{responseContent}</p>
              </div>
            </article>
          );
        })
      )}
    </section>
  );
}
