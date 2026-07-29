/**
 * Structured debate/verdict transcript.
 *
 * The selector owns narrative order; this component only renders linear turns,
 * opposed debate rounds, and full-width convergence verdicts. Turn artifacts
 * are loaded eagerly and historical multi-speaker payloads are guarded at the
 * presentation boundary without rewriting immutable run data.
 */
import { useMemo } from "react";
import { guardDebateAttribution } from "../../domain/debateAttribution";
import { ROLE_LABELS_ZH } from "../../domain/roles";
import { useTurnResponses, type LoadedResponse } from "../../hooks/useTurnResponses";
import { ROLE_REGISTRY, type Turn } from "../../state/model";
import {
  debateScript,
  type DebateBlock,
  type DebateLaneId,
  type DebateStage,
} from "../../state/selectors";
import { useWorkbenchStore } from "../../state/WorkbenchStore";
import { RoleIcon } from "../icons/RoleIcon";
import { SafeMarkdown } from "../shared/SafeMarkdown";

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

const LANE_LABELS: Record<DebateLaneId, string> = {
  bull: "多方",
  bear: "空方",
  aggressive: "激进",
  neutral: "中性",
  conservative: "保守",
};

const STAGE_LABELS: Record<DebateStage, string> = {
  research: "多空研究辩论",
  risk: "风险观点辩论",
};

function roleDefFor(actor_id: string): { team_id: string; icon_id: string } {
  const def = ROLE_REGISTRY.find((role) => role.actor_id === actor_id);
  return {
    team_id: def?.team_id ?? "",
    icon_id: def?.icon_id ?? "",
  };
}

function tagTextFor(turn: Turn): string {
  if (turn.actor_id === "manager.research" || turn.actor_id === "manager.portfolio") {
    return "裁决";
  }
  if (turn.actor_id === "evidence.steward") return "Gate";
  return `第 ${turn.turn_index} 轮`;
}

function flattenTurns(blocks: DebateBlock[]): Turn[] {
  return blocks.flatMap((block) => {
    if (block.kind === "round") {
      return block.lanes.flatMap((lane) => lane.turns);
    }
    return [block.turn];
  });
}

interface TurnCardProps {
  turn: Turn;
  response: LoadedResponse | undefined;
  variant: "linear" | "lane" | "verdict";
  guardBody?: boolean;
  onSelect: (turn_id: string) => void;
  onExpand: (turn_id: string) => void;
}

function TurnCard({
  turn,
  response,
  variant,
  guardBody = false,
  onSelect,
  onExpand,
}: TurnCardProps): JSX.Element {
  const { team_id, icon_id } = roleDefFor(turn.actor_id);
  const isCandidate = turn.status === "output_ready";
  const label = ROLE_LABELS_ZH[turn.actor_id] ?? turn.actor_id;
  const guarded =
    guardBody && response?.text
      ? guardDebateAttribution(turn.actor_id, response.text)
      : {
          text: response?.text ?? null,
          hasForeignAttribution: false,
          foreignLabels: [] as string[],
        };

  let bodyContent: JSX.Element;
  if (!turn.artifact_id) {
    bodyContent = <div className="turn-body-placeholder">（进行中）</div>;
  } else if (response?.loading) {
    bodyContent = <div className="turn-body-placeholder">正在加载…</div>;
  } else if (response?.error) {
    bodyContent = (
      <div className="turn-body-placeholder error">加载失败：{response.error}</div>
    );
  } else if (guarded.text) {
    bodyContent = <SafeMarkdown content={guarded.text} mode="prose" />;
  } else if (guarded.hasForeignAttribution) {
    bodyContent = (
      <div className="turn-body-placeholder">未找到可安全归属于当前角色的正文</div>
    );
  } else {
    bodyContent = <div className="turn-body-placeholder">（无文本）</div>;
  }

  return (
    <article
      className={`turn-card turn-card-${variant}`}
      data-team={team_id}
      data-actor-id={turn.actor_id}
      data-turn-status={turn.status}
      onClick={() => onSelect(turn.turn_id)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(turn.turn_id);
        }
      }}
      tabIndex={0}
      aria-label={`查看 ${label} 的回合详情`}
    >
      <div className="avatar">
        <RoleIcon icon_id={icon_id} size={15} />
      </div>
      <div className={variant === "verdict" ? "bubble manager" : "bubble"}>
        <div className="bubble-head">
          {isCandidate && <span className="tag candidate">候选</span>}
          <span>{label}</span>
          <span className="tag">{tagTextFor(turn)}</span>
          {response?.badge && (
            <span className={turn.actor_id === "evidence.steward" ? "tag evidence" : "tag"}>
              {response.badge}
            </span>
          )}
        </div>
        {guarded.hasForeignAttribution && (
          <div className="attribution-warning" role="status">
            历史正文包含其他发言者归属：{guarded.foreignLabels.join("、")}
          </div>
        )}
        <div className="bubble-body">
          {bodyContent}
          {response?.text && !response.fullyLoaded && response.text.length >= 800 && (
            <button
              type="button"
              className="expand-link"
              onClick={(event) => {
                event.stopPropagation();
                onExpand(turn.turn_id);
              }}
            >
              展开全文
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

export function Timeline({
  filter,
  onTurnSelected,
  onFilterChange,
}: TimelineProps): JSX.Element {
  const { stream, run_id } = useWorkbenchStore();
  const state = stream.state;
  const activeFilter = filter || "";

  const blocks = useMemo(
    () => (state ? debateScript(state, activeFilter) : []),
    [state, activeFilter],
  );
  const turns = useMemo(() => flattenTurns(blocks), [blocks]);
  const { responses, expand } = useTurnResponses({
    run_id,
    turns,
    eagerWindow: 12,
    excerptBudget: 800,
  });

  const head = (
    <div className="timeline-head">
      <div>
        <span className="eyebrow">Live transcript</span>
        <h2>辩论与决策时间线</h2>
      </div>
      <div className="filters">
        {FILTER_BUTTONS.map((button) => (
          <button
            key={button.value || "all"}
            type="button"
            className={activeFilter === button.value ? "filter active" : "filter"}
            aria-pressed={activeFilter === button.value}
            onClick={onFilterChange ? () => onFilterChange(button.value) : undefined}
          >
            {button.label}
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
      {blocks.length === 0 ? (
        <div className="placeholder">{hasAnyTurns ? "当前过滤无条目" : "等待事件流"}</div>
      ) : (
        <div className="debate-script">
          {blocks.map((block, blockIndex) => {
            if (block.kind === "round") {
              const budget =
                block.stage === "research"
                  ? state.meta.max_debate_rounds
                  : state.meta.max_risk_discuss_rounds;
              return (
                <section
                  key={`${block.stage}-round-${block.index}`}
                  className={`debate-round debate-round-${block.stage}`}
                  data-stage={block.stage}
                  data-round={block.index}
                >
                  <div className="round-separator">
                    <span>{STAGE_LABELS[block.stage]}</span>
                    <strong>第 {block.index} 轮 / 计划 {budget} 轮</strong>
                  </div>
                  <div className={`debate-lanes debate-lanes-${block.stage}`}>
                    {block.lanes.map((lane) => (
                      <div key={lane.id} className="debate-lane" data-lane={lane.id}>
                        <div className="lane-label">{LANE_LABELS[lane.id]}</div>
                        {lane.turns.map((turn) => (
                          <TurnCard
                            key={turn.turn_id}
                            turn={turn}
                            response={responses[turn.turn_id]}
                            variant="lane"
                            guardBody
                            onSelect={onTurnSelected}
                            onExpand={expand}
                          />
                        ))}
                      </div>
                    ))}
                  </div>
                </section>
              );
            }

            if (block.kind === "verdict") {
              return (
                <section
                  key={block.turn.turn_id}
                  className="convergence-block"
                  aria-label="辩论收敛裁决"
                >
                  <div className="convergence-label">观点收敛</div>
                  <TurnCard
                    turn={block.turn}
                    response={responses[block.turn.turn_id]}
                    variant="verdict"
                    onSelect={onTurnSelected}
                    onExpand={expand}
                  />
                </section>
              );
            }

            return (
              <TurnCard
                key={`${block.turn.turn_id}-${blockIndex}`}
                turn={block.turn}
                response={responses[block.turn.turn_id]}
                variant="linear"
                onSelect={onTurnSelected}
                onExpand={expand}
              />
            );
          })}
        </div>
      )}
    </section>
  );
}
