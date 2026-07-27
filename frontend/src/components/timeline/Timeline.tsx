/**
 * G2 - Debate/verdict timeline.
 *
 * Renders the ordered turn transcript from the live workbench store. Each
 * turn's response text is eagerly fetched from the turn.output_ready artifact
 * (the JSON-serialized business_delta) via useTurnResponses. Candidate
 * (output_ready, not committed) vs committed (completed) turns are visually
 * distinguished by a gold 候选 tag prepended to the bubble-head.
 *
 * Turn bodies render as prose markdown via SafeMarkdown. Turns beyond the
 * eager fetch window carry an excerpt and an expand control.
 */
import { useMemo } from "react";
import { ROLE_REGISTRY } from "../../state/model";
import { turnTimeline } from "../../state/selectors";
import { useWorkbenchStore } from "../../state/WorkbenchStore";
import { useTurnResponses } from "../../hooks/useTurnResponses";
import { SafeMarkdown } from "../shared/SafeMarkdown";
import { ROLE_LABELS_ZH } from "../../domain/roles";
import { RoleIcon } from "../icons/RoleIcon";

export interface TimelineProps {
  filter: string;
  onTurnSelected: (turn_id: string) => void;
  onFilterChange?: (filter: string) => void;
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

  const turns = useMemo(
    () => (state ? turnTimeline(state, activeFilter) : []),
    [state, activeFilter],
  );

  const { responses, expand } = useTurnResponses({
    run_id,
    turns,
    eagerWindow: 12,
    excerptBudget: 800,
  });

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

  if (run_id === null || !state || state.meta.run_id === "") {
    return (
      <section>
        {head}
        <div className="placeholder">发起分析后查看辩论时间线</div>
      </section>
    );
  }

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
          const entry = responses[turn.turn_id];

          let bodyContent: JSX.Element;
          if (!turn.artifact_id) {
            bodyContent = (
              <div className="turn-body-placeholder">（进行中）</div>
            );
          } else if (entry?.loading) {
            bodyContent = (
              <div className="turn-body-placeholder">正在加载…</div>
            );
          } else if (entry?.error) {
            bodyContent = (
              <div className="turn-body-placeholder error">
                加载失败：{entry.error}
              </div>
            );
          } else if (entry?.text) {
            bodyContent = (
              <>
                <SafeMarkdown content={entry.text} mode="prose" />
                {!entry.fullyLoaded && entry.text.length >= 800 && (
                  <button
                    type="button"
                    className="expand-link"
                    onClick={() => expand(turn.turn_id)}
                  >
                    展开全文
                  </button>
                )}
              </>
            );
          } else {
            bodyContent = (
              <div className="turn-body-placeholder">（无文本）</div>
            );
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
                onClick={() => onTurnSelected(turn.turn_id)}
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
                <div className="bubble-body">{bodyContent}</div>
              </div>
            </article>
          );
        })
      )}
    </section>
  );
}
